# 反向代理配置参考

> 本目录提供部署 LabMemory MCP SSE 时反向代理层的最小可行配置片段；
> 平台侧只暴露 10 个 MCP 工具的反向代理，**不动其它 `/v1/*` 与 `/api/*` 路由**。

## Nginx（推荐生产）

文件：[`nginx-labmemory-mcp.conf`](./nginx-labmemory-mcp.conf)

要点：
- `/mcp/` 仅放行 Aily 出口 IP 段（按飞书官方文档定期更新）
- SSE 必须 `proxy_buffering off; proxy_read_timeout 86400s;`
- Bearer Token 透传：`proxy_set_header Authorization $http_authorization;`

## Cloudflare Tunnel

文件：[`cloudflared-config.yml`](./cloudflared-config.yml)

要点：
- 用 Cloudflare WAF 自定义规则限制来源 IP
- SSE 长连接：`connectTimeout: 30s`，`noHappyEyeballs: true`
- 关闭 http2（部分场景 SSE 兼容问题）

## 部署前 checklist

- [ ] Aily 出口 IP 段已加入白名单（参考 [`scripts/check_aily_ip_allowlist.py`](../scripts/check_aily_ip_allowlist.py)）
- [ ] `PLATFORM_API_KEY` 已生成（≥32 字节随机串）并配入平台 `.env`
- [ ] 平台 `MCP_ENABLED=true`（C1 修复后已无 `MCP_ALLOW_INSECURE_USER_HEADER` 设置——MCP 是机器对机器）
- [ ] SSL 证书就绪（Let's Encrypt 或企业 CA）
- [ ] `/mcp/manifest` 端点能被 Aily 出口 IP 命中 200 OK
- [ ] Webhook 推送目标 URL（飞书机器人回调）已配入平台 `AILY_WEBHOOK_BASE_URL`
- [ ] Webhook 签名密钥（`AILY_WEBHOOK_SECRET`）已在两端一致

## Aily 出口 IP（截至 2026-08，需定期核对）

```
203.166.190.0/24
203.166.191.0/24
```

以飞书官方文档为准：<https://open.feishu.cn/document/server-docs/aily-v3/guide/aily-network-ip>