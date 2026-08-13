"""平台 → 飞书编排器 反向联动客户端。

组装并发送 `FeishuActionRequest`（契约 `contracts/feishu-action-request.schema.json`）到
`{FEISHU_ORCHESTRATOR_BASE_URL}/webhook/platform`。

- `FEISHU_ORCHESTRATOR_MODE != "real"` 时不做真实 HTTP 调用（记日志返回跳过）。
- 真实调用为 fire-and-forget：超时/失败只记录日志并返回错误字典，绝不向上抛，避免阻断主业务。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from app.config import settings
from app.core.security import new_id

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.1.0"


def actor_user_id_for(user: Any) -> str:
    """平台用户 → 飞书动作责任人标识。优先 feishu_user_id，回退 username（mock 通路可接受）。"""
    return (getattr(user, "feishu_user_id", None) or getattr(user, "username", "") or "")


def candidate_dict_from_candidates(candidates: list[dict] | None) -> dict | None:
    """从候选 JSON 列表挑 `parameter_change`（否则第一个），返回扁平候选 dict；空返回 None。"""
    if not candidates:
        return None
    chosen = next((c for c in candidates if c.get("type") == "parameter_change"), candidates[0])
    return {
        "candidate_id": chosen.get("candidate_id"),
        "type": chosen.get("type"),
        "title": chosen.get("title"),
        "description": chosen.get("description"),
        "experiment_ref": chosen.get("experiment_ref"),
        "parameters": chosen.get("parameters", []),
        "confidence": chosen.get("confidence"),
        "evidence": chosen.get("evidence", []),
        "status": chosen.get("status"),
        "needs_review": chosen.get("needs_review"),
    }


def send_feishu_action(
    action_type: str,
    actor_user_id: str,
    candidate_id: str | None,
    payload: dict,
    idempotency_key: str | None = None,
) -> dict:
    """发送一条 FeishuActionRequest。非阻断：任何失败只返回错误字典，不抛异常。"""
    body = {
        "schema_version": SCHEMA_VERSION,
        "action_id": new_id("FA"),
        "action_type": action_type,
        "idempotency_key": idempotency_key or new_id("IK"),
        "actor_user_id": actor_user_id,
        "candidate_id": candidate_id,
        "payload": payload,
    }

    if settings.FEISHU_ORCHESTRATOR_MODE != "real":
        logger.info(
            "飞书编排器反向联动（mock）跳过：action_type=%s idempotency_key=%s",
            action_type, body["idempotency_key"],
        )
        return {"status": "skipped", "mode": settings.FEISHU_ORCHESTRATOR_MODE, "action_type": action_type}

    url = f"{settings.FEISHU_ORCHESTRATOR_BASE_URL.rstrip('/')}/webhook/platform"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.PLATFORM_API_KEY}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        logger.warning("飞书编排器出站失败 action_type=%s url=%s err=%s", action_type, url, e)
        return {"status": "error", "action_type": action_type, "error": str(e)}
