"""Aily 出站 webhook 客户端（HMAC-SHA256 签名 + 幂等键）。

签名：`X-LabMemory-Signature = hex(hmac_sha256(secret, timestamp + nonce + raw_body))`
附带 `X-LabMemory-Timestamp` / `X-LabMemory-Nonce` / `X-LabMemory-Idempotency-Key`。
`AILY_INTEGRATION_ENABLED != "true"` 时不真调（只记日志返回 skipped），fire-and-forget。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.error
import urllib.request

from app.config import settings

logger = logging.getLogger(__name__)


def sign(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), f"{timestamp}{nonce}".encode("utf-8") + body, hashlib.sha256)
    return mac.hexdigest()


def emit_event(event: str, payload: dict, idempotency_key: str | None = None) -> dict:
    """推送一条出站 webhook 事件。非阻断：失败只返回错误字典，不抛异常。"""
    if settings.AILY_INTEGRATION_ENABLED != "true":
        logger.info("Aily 出站 webhook（未启用）跳过：event=%s", event)
        return {"status": "skipped", "event": event}

    base = settings.AILY_WEBHOOK_BASE_URL.rstrip("/")
    url = f"{base}/webhooks/{event}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(8)
    idem = idempotency_key or f"{event}:{nonce}"
    signature = sign(settings.AILY_WEBHOOK_SECRET, timestamp, nonce, body)

    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-LabMemory-Signature": signature,
            "X-LabMemory-Timestamp": timestamp,
            "X-LabMemory-Nonce": nonce,
            "X-LabMemory-Idempotency-Key": idem,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"status": "ok", "event": event, "http": resp.status}
    except Exception as e:  # noqa: BLE001
        logger.warning("Aily 出站 webhook 失败 event=%s url=%s err=%s", event, url, e)
        return {"status": "error", "event": event, "error": str(e)}
