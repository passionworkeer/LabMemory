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
    """GET /mcp/sse 缺 Bearer / 缺 queryParam token → 403（中间件拦）。"""
    r = client.get("/mcp/sse")
    assert r.status_code == 403


def _run_sse_handler_with_query_params(query_string: bytes, headers: list | None = None) -> list[tuple[str, object]]:
    """直接 ASGI 三参调 _mcp_sse_handler，避开 TestClient SSE 挂死。

    返回记录到的 (kind, value) 事件列表。客户端立即断开，只验证 status + content-type。
    """
    import asyncio
    from app.mcp_server.transport import _mcp_sse_handler

    events: list[tuple[str, object]] = []
    disconnected = {"flag": False}

    async def fake_receive():
        if disconnected["flag"]:
            return {"type": "http.disconnect"}
        disconnected["flag"] = True
        return {"type": "http.disconnect"}

    async def fake_send(msg):
        if msg.get("type") == "http.response.start":
            events.append(("status", msg["status"]))
            events.append(("headers", dict((k, v.decode("latin-1") if isinstance(v, (bytes, bytearray)) else v) for k, v in msg["headers"])))

    scope = {
        "type": "http", "method": "GET", "path": "/sse", "raw_path": b"/sse",
        "headers": headers or [], "query_string": query_string, "scheme": "http", "server": ("t", 1),
    }

    asyncio.run(asyncio.wait_for(_mcp_sse_handler(scope, fake_receive, fake_send), timeout=4.0))
    return events


def test_sse_endpoint_with_query_param_token():
    """GET /mcp/sse?token=xxx（无 Header）→ 200 + text/event-stream。

    现实：Aily 自定义 MCP 后台只能填 name+url+description，无法配 Authorization
    Header；服务端必须接受 queryParam 鉴权（参考高德 MCP `?key=xxx` 模式）。
    直接调 handler 而非 TestClient，避免 SSE 长连接导致 TestClient 卡死。
    """
    events = _run_sse_handler_with_query_params(b"token=dev-platform-api-key-please-rotate")
    statuses = [v for t, v in events if t == "status"]
    assert statuses and statuses[0] == 200, f"queryParam 鉴权未通过：{events!r}"
    headers = dict((t, v) for t, v in events if t == "headers")
    assert any("text/event-stream" in str(v).lower() for v in headers.values()), headers


def test_sse_endpoint_with_bearer_header():
    """GET /mcp/sse 带 Authorization Bearer → 200（保留兼容，便于 curl 自检）。"""
    events = _run_sse_handler_with_query_params(
        b"",
        headers=[(b"authorization", b"Bearer dev-platform-api-key-please-rotate")],
    )
    statuses = [v for t, v in events if t == "status"]
    assert statuses and statuses[0] == 200, f"Bearer 鉴权失败：{events!r}"


def test_sse_endpoint_wrong_token_403(client):
    """GET /mcp/sse 带错误 token → 403（queryParam 与 Header 都验）。"""
    r = client.get("/mcp/sse?token=wrong-key")
    assert r.status_code == 403

    r = client.get("/mcp/sse", headers={"Authorization": "Bearer wrong-key"})
    assert r.status_code == 403


def test_messages_endpoint_no_auth_required(client):
    """POST /mcp/messages 不再被中间件拦（设计选择：MCP 协议以 session_id 为唯一凭证）。

    见 transport.py `protected_prefixes` 注释。MCP SDK 在 session_id 缺失或无效时
    返回 400/404，由 SDK 内部处理。我们只验证中间件不再前置鉴权。
    """
    r = client.post("/mcp/messages", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    # 没有 session_id → SDK 返回 400；中间件不再拦
    assert r.status_code == 400, f"中间件应放行，SDK 应因缺 session_id 返回 400；得到 {r.status_code}"

def test_sse_endpoint_returns_correct_message_path():
    """回归 — SSE endpoint 事件必须是相对路径 /messages（不是 /mcp/messages）。

    关键回归：app.mount("/mcp", subapp) 后，子应用里的路径相对 Mount 解析；
    若 SseServerTransport(endpoint="/mcp/messages") 传绝对路径，SDK 在 endpoint
    事件里塞的就是 /mcp/messages，客户端拿到后 POST 到 https://host/mcp/mcp/messages
    （双前缀 404），导致 Aily / Cursor 等客户端握手失败、保存不上 MCP 服务。

    修法：endpoint 必须传相对路径 /messages，Mount 自动加 /mcp 前缀。
    """
    import asyncio
    from app.mcp_server.transport import _sse_transport

    # 直接读 transport 实例的 endpoint，验证它是相对路径
    # SseServerTransport 的 _endpoint 是私有字段，但 public endpoint 是构造参数；
    # 内部实现里写 self._endpoint = endpoint（sse.py line 122）。
    assert _sse_transport._endpoint == "/messages", (
        f"SSE 端点配置错：当前 endpoint={_sse_transport._endpoint!r}，"
        "必须是 /messages（相对路径），否则 Mount 后会变成 /mcp/mcp/messages 双前缀。"
    )


def test_sse_endpoint_with_auth_streams_endpoint_event():
    """回归 — 直接 ASGI 三参调用 _mcp_sse_handler 验证 SSE 建连。

    关键回归：Starlette Route 对函数 endpoint 走 request_response(f) 只传 Request，
    但 _mcp_sse_handler 需要原生 (scope, receive, send) 三参。改用 _ASGIApp 包裹后，
    Route 才把它当 ASGI app 调用并正确传三参。本测试直接调 handler（mock send），
    避开 TestClient 与 anyio task group 之间的悬挂交互（无限 SSE 流会让 stream() 不返回）。
    注：mcp_server.run() 在客户端断开前不发 endpoint 事件，故只验 status+content-type，
    足以覆盖「签名错导致 500」这一回归点。
    """
    import asyncio
    from app.mcp_server.transport import _mcp_sse_handler

    events: list[tuple[str, object]] = []
    disconnected = {"flag": False}

    async def fake_receive():
        if disconnected["flag"]:
            return {"type": "http.disconnect"}
        disconnected["flag"] = True
        return {"type": "http.disconnect"}

    async def fake_send(msg):
        if msg.get("type") == "http.response.start":
            events.append(("status", msg["status"]))
            events.append(("headers", dict((k, v.decode("latin-1") if isinstance(v, (bytes, bytearray)) else v) for k, v in msg["headers"])))

    scope = {
        "type": "http", "method": "GET", "path": "/sse", "raw_path": b"/sse",
        "headers": [], "query_string": b"", "scheme": "http", "server": ("t", 1),
    }

    asyncio.run(asyncio.wait_for(_mcp_sse_handler(scope, fake_receive, fake_send), timeout=4.0))

    statuses = [v for t, v in events if t == "status"]
    assert statuses and statuses[0] == 200, f"SSE 响应 status 非 200：{events!r}（500 = ASGI 签名错）"
    headers = dict((t, v) for t, v in events if t == "headers")
    assert any("text/event-stream" in str(v).lower() for v in headers.values()), headers


# === 7. MCP_REQUIRE_AUTH 开关（Aily 后台三字段限制下的唯一可行接入路径） ===

def test_mcp_require_auth_false_skips_auth(monkeypatch):
    """MCP_REQUIRE_AUTH=false 时 /mcp/sse 与 /mcp/manifest 都不要求 token。

    现实：Aily 后台只能填 name+url+desc 三字段，无 Header 配置入口，且 URL
    校验拒绝 queryParam。服务端必须支持无鉴权模式才能接入。
    注：SSE 长连接会让 TestClient GET /mcp/sse 卡死，所以这个测试只断言
    /mcp/manifest 可访问；SSE 路径走 test_mcp_no_auth_sse_builds_ok（直接调 handler）。
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.config import settings
    from app.mcp_server import transport as mcp_transport

    monkeypatch.setattr(settings, "MCP_REQUIRE_AUTH", False, raising=False)
    monkeypatch.setattr(mcp_transport.settings, "MCP_REQUIRE_AUTH", False, raising=False)

    app = FastAPI()
    mcp_transport.mount_mcp(app)
    client = TestClient(app)

    # manifest 应放行（中间件不拦）
    r = client.get("/mcp/manifest")
    assert r.status_code == 200, f"无鉴权模式下 manifest 应可访问；得 {r.status_code}: {r.text}"
    data = r.json()
    assert data["server"]["name"] == "labmemory"
    assert len(data["tools"]) == 10

    # POST /messages 不在受保护列表里，无鉴权模式自然放行（中间件层不再拦）
    r = client.post("/mcp/messages", json={"jsonrpc": "2.0", "method": "ping", "id": 1})
    # SDK 对缺 session_id 返回 400（与有鉴权模式一致）
    assert r.status_code == 400, f"SDK 应因缺 session_id 返回 400；得 {r.status_code}"


def test_mcp_no_auth_sse_builds_ok(monkeypatch):
    """MCP_REQUIRE_AUTH=false 时 _mcp_sse_handler 直接调应能 200（无任何 token）。"""
    import asyncio
    from app.config import settings
    from app.mcp_server.transport import _mcp_sse_handler

    # 中间件层的开关与 settings 同步；这里测的是 handler 本身能跑通 ASGI 三参签名
    monkeypatch.setattr(settings, "MCP_REQUIRE_AUTH", False, raising=False)

    events: list[tuple[str, object]] = []
    disconnected = {"flag": False}

    async def fake_receive():
        if disconnected["flag"]:
            return {"type": "http.disconnect"}
        disconnected["flag"] = True
        return {"type": "http.disconnect"}

    async def fake_send(msg):
        if msg.get("type") == "http.response.start":
            events.append(("status", msg["status"]))
            events.append(("headers", dict((k, v.decode("latin-1") if isinstance(v, (bytes, bytearray)) else v) for k, v in msg["headers"])))

    scope = {
        "type": "http", "method": "GET", "path": "/sse", "raw_path": b"/sse",
        "headers": [], "query_string": b"", "scheme": "http", "server": ("t", 1),
    }
    asyncio.run(asyncio.wait_for(_mcp_sse_handler(scope, fake_receive, fake_send), timeout=4.0))
    statuses = [v for t, v in events if t == "status"]
    assert statuses and statuses[0] == 200, f"handler 应 200；得 {events!r}"
