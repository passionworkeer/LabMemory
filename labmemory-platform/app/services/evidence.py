"""证据有效性校验（PRD §13.1 证据失效降级）。

demo 阶段证据为结构化锚点（speaker+text），无真实 URL；本模块做结构化校验。
真实 URL 可达性探活需飞书文档权限，作为后续增强（见 AUDIT.md）。
"""
from __future__ import annotations

from typing import Any


def validate_evidence(claim: Any) -> dict:
    """校验主张证据有效性。返回 {valid, reason, count}。

    有效 = evidence 列表非空且每条含 text（可定位妙记片段/结果/文件）。
    """
    evidence = []
    if claim is not None:
        content = getattr(claim, "content", None) or {}
        evidence = content.get("evidence") or []

    if not evidence:
        return {"valid": False, "reason": "evidence_empty", "count": 0}
    invalid = [i for i, e in enumerate(evidence) if not e.get("text")]
    if invalid:
        return {"valid": False, "reason": "evidence_missing_text", "count": len(evidence) - len(invalid)}
    return {"valid": True, "reason": None, "count": len(evidence)}
