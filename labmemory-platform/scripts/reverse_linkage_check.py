"""反向联动验证：直打 feishu-orchestrator 的 POST /webhook/platform 端点。

证明平台 → 飞书编排器的 FeishuActionRequest 通路可用（编排器 RUN_MODE=mock 即可，无需真飞书凭证）。
覆盖 4 个动作类型（send_card / create_task / publish_doc / notify）+ 幂等 + 缺字段拒绝。

前置：编排器服务在 8080（cd feishu-orchestrator/feishu-orchestrator && python -m core.webhook_server）
运行：python -m scripts.reverse_linkage_check
"""
from __future__ import annotations

import json
import sys
import uuid
from urllib import error, request

# Windows 控制台默认 cp1252 下中文 print 会抛 UnicodeEncodeError，统一重配为 utf-8
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

BASE_URL = "http://127.0.0.1:8080"


def _post(path: str, payload: dict) -> dict:
    url = f"{BASE_URL}{path}"
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except error.HTTPError as e:
        return {"_http_error": e.code, "body": e.read().decode("utf-8", "ignore")}


def _get(path: str) -> dict:
    with request.urlopen(f"{BASE_URL}{path}", timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _action(action_type: str, candidate_id: str | None, payload: dict, idem: str | None = None) -> dict:
    return {
        "schema_version": "1.1.0",
        "action_id": f"fa_{uuid.uuid4().hex[:8]}",
        "action_type": action_type,
        "idempotency_key": idem or f"ik_{uuid.uuid4().hex[:8]}",
        "actor_user_id": "ou_demo",
        "candidate_id": candidate_id,
        "payload": payload,
    }


def main() -> int:
    steps: list[tuple[str, bool, str]] = []

    # 0) 编排器健康检查
    try:
        h = _get("/health")
        steps.append(("orchestrator /health", h.get("status") == "ok", f"service={h.get('service')}"))
    except Exception as e:  # noqa: BLE001
        print(f"✗ 编排器未就绪：{e}", file=sys.stderr)
        print("请先起编排器：cd feishu-orchestrator/feishu-orchestrator && python -m core.webhook_server", file=sys.stderr)
        return 1

    cand = {
        "candidate_id": "cand_rev_001", "type": "parameter_change", "title": "温度 70℃",
        "description": "70℃ 复现", "experiment_ref": "EXP-DEMO-001",
        "parameters": [{"name": "temperature", "value": "70", "unit": "℃"}],
        "confidence": 0.9, "evidence": [{"speaker": "陈博士", "text": "70℃ 收率更好", "start_offset_sec": 0}],
    }

    # 1) send_card
    idem = f"ik_card_{uuid.uuid4().hex[:6]}"
    r = _post("/webhook/platform", _action("send_card", cand["candidate_id"], {
        "receive_id": "ou_demo", "candidate": cand, "meeting_title": "反向联动验证会议", "source_url": "",
    }, idem))
    ok = r.get("ok") is True and bool(r.get("result", {}).get("message_id"))
    steps.append(("send_card", ok, f"status={r.get('status')} message_id={r.get('result', {}).get('message_id')!r}"))

    # 2) create_task
    r = _post("/webhook/platform", _action("create_task", cand["candidate_id"], {
        "candidate": cand, "meeting_title": "反向联动验证会议", "source_url": "",
    }))
    ok = r.get("ok") is True and bool(r.get("result", {}).get("task_guid"))
    steps.append(("create_task", ok, f"status={r.get('status')} task_guid={r.get('result', {}).get('task_guid')!r}"))

    # 3) publish_doc
    r = _post("/webhook/platform", _action("publish_doc", cand["candidate_id"], {
        "candidate": cand, "meeting_title": "反向联动验证会议", "doc_type": "success",
    }))
    ok = r.get("ok") is True and bool(r.get("result", {}).get("doc_token"))
    steps.append(("publish_doc", ok, f"status={r.get('status')} doc_token={r.get('result', {}).get('doc_token')!r}"))

    # 4) notify
    r = _post("/webhook/platform", _action("notify", None, {
        "receive_id": "ou_demo", "title": "行动前审计阻断", "reason": "版本门阻断",
    }))
    ok = r.get("ok") is True and bool(r.get("result", {}).get("message_id"))
    steps.append(("notify", ok, f"status={r.get('status')} message_id={r.get('result', {}).get('message_id')!r}"))

    # 5) 幂等：重复 send_card 相同 idempotency_key
    r2 = _post("/webhook/platform", _action("send_card", cand["candidate_id"], {
        "receive_id": "ou_demo", "candidate": cand, "meeting_title": "反向联动验证会议", "source_url": "",
    }, idem))
    ok = r2.get("ok") is True and r2.get("status") == "duplicate"
    steps.append(("幂等（重复 idempotency_key）", ok, f"status={r2.get('status')}"))

    # 6) 缺必填字段拒绝
    bad = _action("send_card", cand["candidate_id"], {"receive_id": "ou_demo"})
    bad.pop("idempotency_key")
    r = _post("/webhook/platform", bad)
    ok = r.get("ok") is False and r.get("status") == "invalid"
    steps.append(("缺 idempotency_key 拒绝", ok, f"status={r.get('status')} error={r.get('error')!r}"))

    # 汇总
    print("=" * 64)
    print("反向联动验证（平台 → 编排器 POST /webhook/platform）")
    print("=" * 64)
    for name, ok, detail in steps:
        print(f"  {'✓' if ok else '✗'} {name:28} {detail}")
    allok = all(ok for _n, ok, _d in steps)
    print("-" * 64)
    print(f"{'✓ 全部通过' if allok else '✗ 存在失败'}  ({sum(1 for _n, ok, _d in steps if ok)}/{len(steps)})")
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
