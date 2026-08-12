"""可信规则引擎：候选→主张发布前的六道闸门 + 冲突检测 + 语义栅栏。

规则来源：PRD §10.1（六道闸门）、§10.5（冲突检测规则）、line 854（语义栅栏）。
与「行动前审计」(_run_checks) 职责分离：本模块管候选能否「发布为 current」，_run_checks 管任务能否「执行」。
"""
from __future__ import annotations

from typing import Any

# PRD line 854：不得把「可以试试、建议、可能、暂定」等表达转换为当前有效参数
SEMANTIC_HEDGE_KEYWORDS = ["可以试试", "建议", "可能", "暂定", "试试", "或许", "考虑"]

# 发布状态（Claim.status 取值）
STATUS_CURRENT = "current"
STATUS_SUPERSEDED = "superseded"
STATUS_PENDING_SUPPLEMENT = "pending_supplement"  # 待补充：对象/参数/范围/责任缺失
STATUS_PENDING_VALIDATION = "pending_validation"  # 待验证：证据/语义不足


def pick_candidate(candidate_row) -> dict | None:
    """从 Candidate.candidates JSON 选主张对象：优先 parameter_change，否则首个。与 _build_claim 一致。"""
    candidates = (candidate_row.candidates if candidate_row is not None else None) or []
    chosen = next((c for c in candidates if c.get("type") == "parameter_change"), None)
    if chosen is None and candidates:
        chosen = candidates[0]
    return chosen


def _params(candidate: dict | None, modifications: dict | None) -> list[dict]:
    if modifications and modifications.get("parameters"):
        return modifications["parameters"] or []
    return (candidate or {}).get("parameters") or []


def _scope(candidate: dict | None, modifications: dict | None):
    if modifications and modifications.get("scope"):
        return modifications["scope"]
    return (candidate or {}).get("scope")


def _scope_eq(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: v for k, v in a.items() if v is not None} == {k: v for k, v in b.items() if v is not None}
    return str(a) == str(b)


def _value_key(v) -> float | str:
    """归一化参数值用于冲突比较：数值统一转 float（使 70 == 70.0 == "70"），
    非数值（字符串 scope/类别等）退回 str。避免同值不同 JSON 类型被 str() 误判为冲突。
    """
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def run_six_gates(
    candidate: dict | None,
    modifications: dict | None,
    experiment: Any,
    reviewer: Any,
) -> dict:
    """六道闸门（PRD §10.1）。返回 {gates, failed, publish_status, passed, report}。

    发布状态：对象/参数/范围/责任门失败→pending_supplement；证据/状态门失败→pending_validation；全过→current。
    """
    gates: dict[str, dict] = {}
    failed: list[tuple[str, str]] = []
    candidate = candidate or {}

    # 1) 对象门
    exp_ref = candidate.get("experiment_ref") or (experiment.experiment_id if experiment else None)
    obj_ok = bool(exp_ref)
    gates["object"] = {"status": "passed" if obj_ok else "blocked", "experiment_ref": exp_ref}
    if not obj_ok:
        failed.append(("object", "对象门：实验/样品/项目不明确"))

    # 2) 参数门
    params = _params(candidate, modifications)
    params_ok = len(params) > 0 and all(p.get("name") and "value" in p for p in params)
    gates["parameter"] = {"status": "passed" if params_ok else "blocked", "count": len(params)}
    if not params_ok:
        failed.append(("parameter", "参数门：数值/单位/名称不完整"))

    # 3) 证据门
    evidence = candidate.get("evidence") or []
    evidence_ok = len(evidence) > 0 and all(e.get("text") for e in evidence)
    gates["evidence"] = {"status": "passed" if evidence_ok else "blocked", "count": len(evidence)}
    if not evidence_ok:
        failed.append(("evidence", "证据门：缺少可定位证据（妙记片段/结果/文件）"))

    # 4) 范围门
    scope = _scope(candidate, modifications)
    scope_ok = bool(scope)
    gates["scope"] = {"status": "passed" if scope_ok else "blocked", "scope": scope}
    if not scope_ok:
        failed.append(("scope", "范围门：材料/浓度/设备/批次等边界不明确"))

    # 5) 状态门（语义栅栏，PRD line 854）
    text_blob = " ".join(filter(None, [candidate.get("title", ""), candidate.get("description", "")]))
    hedge_hit = [kw for kw in SEMANTIC_HEDGE_KEYWORDS if kw in text_blob]
    gates["status"] = {"status": "passed" if not hedge_hit else "needs_review", "hedge_keywords": hedge_hit}
    if hedge_hit:
        failed.append(("status", f"状态门：含暂定/建议表达 {hedge_hit}，不得成为当前有效参数"))

    # 6) 责任门
    resp_ok = reviewer is not None
    gates["responsibility"] = {"status": "passed" if resp_ok else "blocked",
                               "reviewer_id": getattr(reviewer, "id", None)}
    if not resp_ok:
        failed.append(("responsibility", "责任门：提出人/审核人不明确"))

    # 发布状态（PRD §10.2）
    hard_gates = {"object", "parameter", "scope", "responsibility"}
    soft_gates = {"evidence", "status"}
    if any(g in hard_gates for g, _ in failed):
        publish_status = STATUS_PENDING_SUPPLEMENT
    elif any(g in soft_gates for g, _ in failed):
        publish_status = STATUS_PENDING_VALIDATION
    else:
        publish_status = STATUS_CURRENT

    return {
        "gates": gates,
        "failed": failed,
        "publish_status": publish_status,
        "passed": publish_status == STATUS_CURRENT,
        "report": [f"{g}: {msg}" for g, msg in failed],
    }


def detect_conflicts(
    db,
    experiment_id: int,
    new_params: list[dict],
    new_scope,
    reviewer: Any,
) -> list[dict]:
    """6 类冲突检测（PRD §10.5）。返回冲突清单（数值冲突为高风险冻结）。

    版本/范围/语义/证据/责任冲突复用六闸门或任务审计结论；本函数聚焦跨主张的数值冲突 + 责任冲突。
    """
    from app.db.models import Claim
    conflicts: list[dict] = []

    existing = (
        db.query(Claim)
        .filter(Claim.experiment_id == experiment_id, Claim.status == STATUS_CURRENT)
        .all()
    )

    # 数值冲突：同 scope 同参数名已有 current 不同值 → 冻结发布
    for ex in existing:
        ex_pv = ex.parameter_version or {}
        ex_scope = ex_pv.get("scope")
        if new_scope and ex_scope and _scope_eq(new_scope, ex_scope):
            ex_params = {p.get("name"): p.get("value") for p in ex_pv.get("parameters", [])}
            for p in new_params:
                name, val = p.get("name"), p.get("value")
                if name in ex_params and val is not None and _value_key(ex_params[name]) != _value_key(val):
                    conflicts.append({
                        "type": "numeric",
                        "severity": "high",
                        "message": f"数值冲突：参数 {name} 已有 current 值 {ex_params[name]}，新值 {val}（scope={new_scope}）",
                        "existing_claim": ex.claim_id,
                    })

    # 责任冲突：reviewer 无权限/未识别（与责任门互补）
    if reviewer is None:
        conflicts.append({"type": "responsibility", "severity": "high", "message": "责任冲突：操作者无权限/未识别"})

    return conflicts
