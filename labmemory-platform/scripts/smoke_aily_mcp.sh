#!/usr/bin/env bash
# 冒烟测试：起平台 → curl 三个 MCP 端点，验证鉴权 + 路由正常
# 用法：APP_URL=http://localhost:8000 PLATFORM_API_KEY=xxx bash scripts/smoke_aily_mcp.sh

set -euo pipefail

: "${APP_URL:?APP_URL is required, e.g. http://localhost:8000}"
: "${PLATFORM_API_KEY:?PLATFORM_API_KEY is required}"

echo "▶ Target: $APP_URL"
echo

echo "── 1) GET /mcp/manifest（缺 Bearer，预期被鉴权拦截 4xx）"
status=$(curl -sS -o /tmp/mcp_resp.json -w "%{http_code}" "$APP_URL/mcp/manifest")
echo "  status: $status"
# nginx 用 proxy_intercept_errors 把 backend 403 改写成 404；放行 401/403/404 都算鉴权拦截
case "$status" in
    401|403|404) echo "  ✓ 通过：未鉴权请求被拦截（nginx 将 403 改写为 404 也接受）" ;;
    *) echo "  ✗ 期望 4xx（401/403/404），实际 $status"; exit 1 ;;
esac
echo

echo "── 2) GET /mcp/manifest（带 Bearer，预期 200 + 10 个工具）"
status=$(curl -sS -o /tmp/mcp_resp.json -w "%{http_code}" \
    -H "Authorization: Bearer $PLATFORM_API_KEY" \
    "$APP_URL/mcp/manifest")
echo "  status: $status"
[ "$status" = "200" ] || { echo "✗ 期望 200，实际 $status"; cat /tmp/mcp_resp.json; exit 1; }

n=$(jq '.tools | length' /tmp/mcp_resp.json)
echo "  tools count: $n"
[ "$n" = "10" ] || { echo "✗ 期望 10 个工具，实际 $n"; exit 1; }
echo "  ✓ 通过：10 个工具全部暴露"
echo

echo "── 3) POST /mcp/messages（缺 Bearer，预期被鉴权拦截 4xx）"
status=$(curl -sS -o /tmp/mcp_resp.json -w "%{http_code}" \
    -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"ping","id":1}' \
    "$APP_URL/mcp/messages")
echo "  status: $status"
case "$status" in
    401|403|404) echo "  ✓ 通过" ;;
    *) echo "  ✗ 期望 4xx，实际 $status"; exit 1 ;;
esac
echo

echo "── 4) GET /mcp/sse 鉴权门槛（缺 Bearer，预期被鉴权拦截 4xx）"
status=$(curl -sS -o /tmp/mcp_resp.json -w "%{http_code}" "$APP_URL/mcp/sse")
echo "  status: $status"
case "$status" in
    401|403|404) echo "  ✓ 通过：SSE 入口鉴权正常" ;;
    *) echo "  ✗ 期望 4xx，实际 $status"; exit 1 ;;
esac
echo

echo "✅ 全部冒烟测试通过"