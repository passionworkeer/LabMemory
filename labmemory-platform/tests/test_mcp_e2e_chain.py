"""MCP 10-工具端到端链路测试。

模拟一次完整实验决策流：妙记→抽取→复核→通过→签版本→执行前自检→执行→护照→知识→复验。
每一跳都拿上一跳的 ID；任一失败立刻抛错中断。

运行：
    APP_ENV=development pytest tests/test_mcp_e2e_chain.py -v -s
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.db.base import Base
    from app.db.session import engine
    from app.main import app
    from scripts.seed_demo import main as seed_main

    Base.metadata.create_all(bind=engine)
    seed_main()
    return TestClient(app)


HEADERS = {"Authorization": "Bearer dev-platform-api-key-please-rotate"}


def _call(client, name: str, args: dict, *, expect_ok: bool = True) -> dict:
    """通过 TestClient 模拟 Aily 调 MCP 工具。

    用 /mcp/manifest 路由只读校验用；要真正调工具需走 SSE 协议，
    这里直接调底层的 aily_api.* endpoint（绕过 MCP 协议层但跑通业务链路）。
    """
    from app.db.session import SessionLocal
    from app.mcp_server.tools import _invoke as mcp_invoke

    db = SessionLocal()
    try:
        result = mcp_invoke(name, args)
        if expect_ok:
            assert "jump_url" in result or name in (
                "labmemory_update_passport",
            ), f"{name} 应含 jump_url；got {result}"
        return result
    except Exception as e:
        return {"_error": type(e).__name__, "_msg": str(e)}
    finally:
        db.close()


def test_e2e_10_tool_chain(client):
    """完整链路：10 工具串联，验证业务数据流。"""
    t0 = time.time()
    prefix = f"MCP-E2E-{int(time.time())}"

    # ── 1. 提交逐字稿 ──
    r1 = _call(
        client,
        "labmemory_submit_transcript",
        {
            "meeting_id": f"{prefix}-MTG-01",
            "experiment_id": "EXP-DEMO-001",
            "speakers": ["alice", "bob"],
            "segments": [
                {"start": 0, "end": 30, "speaker": "alice", "text": "我们应该把温度从 80 降到 70"},
                {"start": 30, "end": 60, "speaker": "bob", "text": "同意，但时间要延长到 4h"},
            ],
            "title": "参数讨论会议",
            "summary": "讨论 70℃ 替代 80℃ 的方案",
        },
    )
    assert "_error" not in r1, f"submit_transcript 失败：{r1}"
    assert r1.get("transcript_id") == f"{prefix}-MTG-01"
    print(f"  [1] submit_transcript OK → transcript_id={r1['transcript_id']}")

    # ── 2. 提交抽取 ──
    extraction_id = f"{prefix}-EXT-01"
    r2 = _call(
        client,
        "labmemory_submit_extraction",
        {
            "transcript_id": f"{prefix}-MTG-01",
            "extraction_id": extraction_id,
            "params": [
                {"name": "temperature", "value": "70", "unit": "℃", "evidence_segment_idx": 0},
                {"name": "duration", "value": "4", "unit": "h", "evidence_segment_idx": 1},
            ],
            "disputes": [],
            "risks": [],
            "task_candidates": [],
            "evidence": [
                {"type": "transcript_segment", "ref_id": "seg-0", "text": "我们应该把温度从 80 降到 70"},
                {"type": "transcript_segment", "ref_id": "seg-1", "text": "同意，但时间要延长到 4h"},
            ],
            "scope": {
                "material": "Compound-A",
                "concentration": "0.5 M",
                "equipment": "R-201",
                "batch": "B-001",
            },
        },
    )
    assert "_error" not in r2, f"submit_extraction 失败：{r2}"
    assert r2.get("extraction_id") == extraction_id
    print(f"  [2] submit_extraction OK → extraction_id={r2['extraction_id']}")

    # ── 3. 创建复核项 ──
    r3 = _call(
        client,
        "labmemory_create_review",
        {"extraction_id": extraction_id, "assignee": "alice"},
    )
    assert "_error" not in r3, f"create_review 失败：{r3}"
    decision_id = r3["decision_id"]
    assert decision_id
    print(f"  [3] create_review OK → decision_id={decision_id}")

    # ── 4. 复核通过（verdict=pass）──
    r4 = _call(
        client,
        "labmemory_submit_verdict",
        {"decision_id": decision_id, "verdict": "pass", "reviewer": "alice", "comment": "OK"},
    )
    assert "_error" not in r4, f"submit_verdict 失败：{r4}"
    assert r4["verdict"] == "pass", f"verdict 不对：{r4}"
    version_id = r4.get("version_id")
    task_id = r4.get("task_id")
    # 注：task_id 可能为 None（六道闸门某项未通过时合法），但 version_id 必须有
    assert version_id, f"verdict pass 应生成 version_id；got {r4}"
    print(
        f"  [4] submit_verdict OK → verdict={r4['verdict']} version_id={version_id} task_id={task_id} publish_status={r4.get('publish_status')}"
    )
    if r4.get("gate_report"):
        print(f"      gate_report (前 3 条): {r4['gate_report'][:3]}")

    # ── 5. 执行前自检 ──
    r5 = _call(
        client,
        "labmemory_preflight_check",
        {"version_id": version_id, "executor": "bob"},
    )
    assert "_error" not in r5, f"preflight_check 失败：{r5}"
    print(f"  [5] preflight_check OK → verdict={r5.get('verdict')}")

    # ── 6. 提交执行结果（必须在自检通过路径上；但这里即使 blocked 也跑流程）──
    # 用实际参数，确保 planned_keys 完整
    r6 = _call(
        client,
        "labmemory_submit_execution",
        {
            "version_id": version_id,
            "actual_params": {"temperature": 70, "duration": 4},
            "results": {"yield_pct": 78.5},
            "executor": "bob",
        },
    )
    assert "_error" not in r6, f"submit_execution 失败：{r6}"
    execution_id = r6.get("execution_id")
    assert execution_id, "submit_execution 应返回 execution_id"
    print(f"  [6] submit_execution OK → execution_id={execution_id}")

    # ── 7. 更新护照（标记为部分支持）──
    r7 = _call(
        client,
        "labmemory_update_passport",
        {
            "passport_id": "EXP-DEMO-001",
            "status": "completed",
            "claim_state": "partial_support",
        },
    )
    assert "_error" not in r7, f"update_passport 失败：{r7}"
    print(f"  [7] update_passport OK → updated={r7.get('updated')}")

    # ── 8. 发布知识 ──
    r8 = _call(
        client,
        "labmemory_publish_knowledge",
        {
            "passport_id": "EXP-DEMO-001",
            "title": "70℃ 4h 工艺验证",
            "summary": "降温和延长时间后产率达 78.5%",
            "claim_state": "partial_support",
        },
    )
    assert "_error" not in r8, f"publish_knowledge 失败：{r8}"
    knowledge_id = r8.get("knowledge_id")
    assert knowledge_id, "publish_knowledge 应返回 knowledge_id"
    print(f"  [8] publish_knowledge OK → knowledge_id={knowledge_id}")

    # ── 8b. M4 幂等：再次调用 publish_knowledge 应返回相同 knowledge_id 且 idempotent=True ──
    r8b = _call(
        client,
        "labmemory_publish_knowledge",
        {
            "passport_id": "EXP-DEMO-001",
            "title": "70℃ 4h 工艺验证",
            "summary": "降温和延长时间后产率达 78.5%",
            "claim_state": "partial_support",
        },
    )
    assert "_error" not in r8b, f"publish_knowledge 二次调用失败：{r8b}"
    assert r8b.get("knowledge_id") == knowledge_id, (
        f"M4 幂等失败：首次 {knowledge_id}，二次 {r8b.get('knowledge_id')}"
    )
    assert r8b.get("idempotent") is True, f"M4 幂等标志位缺失：{r8b}"
    print(f"  [8b] publish_knowledge 幂等 OK → idempotent={r8b.get('idempotent')}")

    # ── 9. 创建复验任务 ──
    r9 = _call(
        client,
        "labmemory_create_reverify",
        {
            "passport_id": "EXP-DEMO-001",
            "assignee": "alice",
            "due_at": "2026-12-01T00:00:00Z",
            "criteria": ["temperature=70", "yield>75%"],
        },
    )
    assert "_error" not in r9, f"create_reverify 失败：{r9}"
    reverify_id = r9.get("reverify_id")
    assert reverify_id
    print(f"  [9] create_reverify OK → reverify_id={reverify_id}")

    # ── 10. 重复签版本（幂等）──
    r10 = _call(
        client,
        "labmemory_issue_version",
        {"decision_id": decision_id},
    )
    assert "_error" not in r10, f"issue_version 失败：{r10}"
    assert r10.get("version_id") == version_id, f"幂等失败：旧 {version_id}，新 {r10.get('version_id')}"
    print(f"  [10] issue_version 幂等 OK → version_id={r10['version_id']}")

    print(f"\n✅ 10 工具链路通过；耗时 {time.time() - t0:.2f}s")


def test_e2e_compact_response_size():
    """确保 MCP 返回值精简，不含 transcript 全文等大字段。"""
    from app.mcp_server.tools import to_call_result

    res = to_call_result(
        "labmemory_submit_transcript",
        {
            "meeting_id": "COMPACT-TEST",
            "experiment_id": "EXP-DEMO-001",
            "segments": [{"start": 0, "end": 1, "speaker": "x", "text": "y" * 50000}],
        },
    )
    assert not res.isError
    body = json.loads(res.content[0].text)
    # 关键字段存在；segment 全文不应进精简返回值
    assert "jump_url" in body
    assert "transcript_id" in body
    # body 不应包含 segments / transcript 等大字段
    assert "segments" not in body
    assert "transcript" not in body


def test_e2e_business_error_translation():
    """业务异常翻译：未知 meeting_id → NotFoundError → isError=true code=not_found。"""
    from app.mcp_server.tools import to_call_result

    res = to_call_result("labmemory_submit_extraction", {"transcript_id": "NONEXISTENT-XXX"})
    assert res.isError
    body = json.loads(res.content[0].text)
    assert body["code"] == "not_found"
    assert "NONEXISTENT" in body["message"] or "逐字稿" in body["message"]