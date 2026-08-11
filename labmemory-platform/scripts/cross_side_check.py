"""真跨侧联动验证：以编排器同款 urllib + Authorization: Bearer 直打平台 /api/v1/* 路由。

证明 feishu-orchestrator 的 4 个出站契约调用模式（candidates / card-callback / task-status / get-candidate）
能对真实 labmemory-platform 跑通，无需真飞书/Aily 凭证。

前置：已 `seed_demo`（实验 EXP-DEMO-001 存在），平台服务在 8081。
运行：python -m scripts.cross_side_check
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from urllib import error, request

BASE_URL = "http://127.0.0.1:8081"
PLATFORM_API_KEY = "dev-platform-api-key-please-rotate"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}{path}"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {PLATFORM_API_KEY}"},
    )
    with request.urlopen(req, timeout=15) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def _get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = request.Request(url, method="GET", headers={"Authorization": f"Bearer {PLATFORM_API_KEY}"})
    with request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    steps: list[tuple[str, bool, str]] = []
    meeting_id = f"meet_cross_{uuid.uuid4().hex[:10]}"
    candidate_id = "cand_cross_001"

    # 0) 健康检查
    try:
        h = _get("/health")
        steps.append(("health", h.get("status") == "ok", f"status={h.get('status')} data_source={h.get('data_source')}"))
    except Exception as e:  # noqa: BLE001
        print(f"✗ 平台未就绪：{e}", file=sys.stderr)
        print("请先起服务：cd labmemory-platform && python -m uvicorn app.main:app --port 8081", file=sys.stderr)
        return 1

    # 1) 提交会议 + 候选（编排器 pipeline Step 3 的 /api/v1/candidates）
    meeting_payload = {
        "schema_version": "1.0.0", "source": "feishu_minutes",
        "source_object_id": f"minute_{meeting_id}", "meeting_id": meeting_id,
        "title": "跨侧联动验证会议", "organizer": "陈博士", "participants": ["陈博士", "王工"],
        "content": {"transcript": [
            {"speaker": "陈博士", "start_offset_sec": 0, "end_offset_sec": 10, "text": "70℃ 收率更好"}
        ], "summary": "70℃ 复现"}, "source_url": f"https://feishu.example.com/minutes/{meeting_id}",
        "captured_at": _now_iso(), "metadata": {"experiment_id": "EXP-DEMO-001", "project_id": "PROJ-DEMO-001"},
    }
    _post("/api/v1/meetings", meeting_payload)

    cand_payload = {
        "schema_version": "1.0.0", "source_package_id": meeting_id,
        "aily_skill_version": "aily-labmemory-v1.0", "model_version": "aily-pro-2026",
        "candidates": [{
            "candidate_id": candidate_id, "type": "parameter_change",
            "title": "温度 70℃ 复现", "description": "70℃ 收率优于 80℃",
            "experiment_ref": "EXP-DEMO-001",
            "parameters": [{"name": "temperature", "value": "70", "unit": "℃"}],
            "confidence": 0.92,
            "evidence": [{"speaker": "陈博士", "text": "70℃ 收率更好", "start_offset_sec": 0}],
            "status": "pending_review", "needs_review": True,
        }],
        "risks": [], "action_items": [], "open_questions": [], "compiled_at": _now_iso(),
    }
    r = _post("/api/v1/candidates", cand_payload)
    ok1 = r.get("status") == "submitted" and r.get("created") is True
    steps.append(("POST /api/v1/candidates", ok1, f"status={r.get('status')} created={r.get('created')} review_count={r.get('review_count')}"))

    # 2) GET 候选详情（编排器 card_handler._handle_approved 调用）
    g = _get(f"/api/v1/candidates/{candidate_id}")
    ok2 = g.get("candidate_id") == candidate_id and "meeting_title" in g and "data" not in g
    steps.append(("GET /api/v1/candidates/{id}", ok2,
                  f"candidate_id={g.get('candidate_id')} meeting_title={g.get('meeting_title')!r} 扁平={'data' not in g}"))

    # 3) 卡片回调（编排器 /api/v1/card/callback 转发嵌套信封，approve）
    token = f"tok_{uuid.uuid4().hex[:8]}"
    cb = _post("/api/v1/card/callback", {
        "token": token, "open_id": "ou_cross_test",
        "action": {"value": {"action_type": "approve", "candidate_id": candidate_id}, "tag": "button"},
    })
    ok3 = "status" in cb and "action_audit" in cb and cb.get("candidate_id") == candidate_id
    steps.append(("POST /api/v1/card/callback", ok3,
                  f"status={cb.get('status')} action_audit={cb.get('action_audit')} msg={cb.get('message')!r}"))

    # 4) 回写任务状态（编排器 /api/v1/task/status）
    ts = _post("/api/v1/task/status", {
        "candidate_id": candidate_id, "feishu_task_guid": "ftask_cross_demo_001", "status": "success",
    })
    ok4 = ts.get("ok") is True and bool(ts.get("task_id"))
    steps.append(("POST /api/v1/task/status", ok4,
                  f"ok={ts.get('ok')} task_id={ts.get('task_id')} feishu_task_guid={ts.get('feishu_task_guid')}"))

    # 汇总
    print("=" * 64)
    print("跨侧联动验证（编排器 → 平台 /api/v1/* 契约路由）")
    print("=" * 64)
    for name, ok, detail in steps:
        print(f"  {'✓' if ok else '✗'} {name:28} {detail}")
    allok = all(ok for _n, ok, _d in steps)
    print("-" * 64)
    print(f"{'✓ 全部通过' if allok else '✗ 存在失败'}  ({sum(1 for _n, ok, _d in steps if ok)}/{len(steps)})")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
