"""MCP Server 单元 + 集成测试。

覆盖：
1. manifest.build_manifest 输出 10 个工具、name/description/schema
2. tools._invoke 分发到 10 个 aily endpoint（直接调用，无 HTTP）
3. to_call_result 业务异常转 CallToolResult(isError=True)
4. transport.mount_mcp 挂载到 FastAPI 后 /mcp/manifest 可访问
5. /mcp/manifest 鉴权：缺 Bearer → 403
6. mcp_server.request_handlers 已注册 ListToolsRequest/CallToolRequest
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# === 1. Manifest 静态导出 ===

EXPECTED_TOOL_NAMES = {
    "labmemory_submit_transcript",
    "labmemory_submit_extraction",
    "labmemory_create_review",
    "labmemory_submit_verdict",
    "labmemory_issue_version",
    "labmemory_preflight_check",
    "labmemory_submit_execution",
    "labmemory_update_passport",
    "labmemory_publish_knowledge",
    "labmemory_create_reverify",
}


@pytest.fixture(scope="module", autouse=True)
def _init_db():
    """共用 DB：建表 + 演示数据，确保 _invoke() 落到 aily endpoint 时有数据可查。"""
    from app.db.base import Base
    from app.db.session import engine
    from scripts.seed_demo import main as seed_main

    Base.metadata.create_all(bind=engine)
    seed_main()


def test_manifest_has_10_tools():
    from app.mcp_server.manifest import build_manifest

    data = build_manifest()
    assert data["server"]["name"] == "labmemory"
    assert data["transport"] == "sse"
    names = {t["name"] for t in data["tools"]}
    assert names == EXPECTED_TOOL_NAMES, f"工具清单不匹配：缺 {EXPECTED_TOOL_NAMES - names}，多 {names - EXPECTED_TOOL_NAMES}"
    # schema 必备字段
    for t in data["tools"]:
        assert t["inputSchema"]["type"] == "object"
        assert "properties" in t["inputSchema"]
        assert t["description"]
    # update_passport 设计为局部更新，允许 required 缺失；其它工具都应有 required
    for t in data["tools"]:
        if t["name"] != "labmemory_update_passport":
            assert "required" in t["inputSchema"], f"{t['name']} 缺 required 字段"


# === 2. 工具分发：返回精简版 + jump_url ===

def test_invoke_submit_transcript_missing_meeting_id():
    """meeting_id 缺失应被 aily_api.receive_transcript 拒为 NotFoundError。"""
    from app.core.errors import NotFoundError
    from app.mcp_server.tools import _invoke

    with pytest.raises(NotFoundError):
        _invoke("labmemory_submit_transcript", {})


def test_invoke_submit_transcript_ok():
    from app.mcp_server.tools import _invoke

    result = _invoke(
        "labmemory_submit_transcript",
        {"meeting_id": "MCP-TEST-001", "experiment_id": "EXP-DEMO-001", "segments": []},
    )
    assert "transcript_id" in result or "meeting_id" in result
    assert "jump_url" in result


def test_invoke_unknown_tool():
    from app.core.errors import NotFoundError
    from app.mcp_server.tools import _invoke

    with pytest.raises(NotFoundError):
        _invoke("labmemory_nope", {})


# === 3. 异常 → CallToolResult(isError=True) ===

def test_to_call_result_business_error():
    from app.mcp_server.tools import to_call_result

    res = to_call_result("labmemory_submit_transcript", {})  # meeting_id 缺失
    assert res.isError is True
    assert res.content and len(res.content) == 1
    import json

    err = json.loads(res.content[0].text)
    assert err["tool"] == "labmemory_submit_transcript"
    assert "code" in err and "message" in err


def test_to_call_result_unknown_tool():
    from app.mcp_server.tools import to_call_result

    res = to_call_result("labmemory_nope", {})
    assert res.isError is True
    import json

    err = json.loads(res.content[0].text)
    assert err["code"] == "not_found"


# === 4. mcp_server handlers 已注册 ===

def test_server_handlers_registered():
    """Server 实例已注册 ListToolsRequest / CallToolRequest handler（装饰器副作用）。"""
    import app.mcp_server as pkg
    import mcp.types as types

    server = pkg.mcp_server
    assert types.ListToolsRequest in server.request_handlers, "list_tools 装饰器未生效"
    assert types.CallToolRequest in server.request_handlers, "call_tool 装饰器未生效"


# === 5/6. HTTP 挂载与鉴权 ===

@pytest.fixture(scope="module")
def client():
    """启动 FastAPI TestClient（与现有 e2e 共用 in-memory DB）。"""
    from app.db.base import Base
    from app.db.session import engine
    from app.main import app

    Base.metadata.create_all(bind=engine)
    return TestClient(app)


def test_manifest_endpoint_requires_auth(client):
    """缺 Bearer → 403。"""
    r = client.get("/mcp/manifest")
    assert r.status_code == 403, r.text


def test_manifest_endpoint_with_auth(client):
    """带 Bearer → 200 + 10 个工具。"""
    r = client.get("/mcp/manifest", headers={"Authorization": "Bearer dev-platform-api-key-please-rotate"})
    assert r.status_code == 200
    data = r.json()
    assert data["server"]["name"] == "labmemory"
    names = {t["name"] for t in data["tools"]}
    assert len(names) == 10


def test_sse_endpoint_requires_auth(client):
    """GET /mcp/sse 缺 Bearer → 403（中间件拦）。"""
    r = client.get("/mcp/sse")
    assert r.status_code == 403


def test_messages_endpoint_requires_auth(client):
    """POST /mcp/messages 缺 Bearer → 403。"""
    r = client.post("/mcp/messages", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    assert r.status_code == 403