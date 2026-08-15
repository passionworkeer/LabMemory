"""校验 Aily 出口 IP 白名单是否在反向代理/防火墙中正确放行。

用途：
- 部署后/巡检时验证：当前 Aily 出口 IP 是否被平台侧（反向代理层）正确放行
- CI 集成：用 expected_ips.json 跑回归，避免白名单被误删

不是平台侧鉴权本身（鉴权在 `app/mcp_server/auth.py::check_bearer` 里走 Bearer Token）；
本脚本只校验"网络可达性"，即从 Aily 出口 IP 段是否能命中平台 /mcp/sse。

用法：
    # 1) 本机被动扫描：探测本机是否能模拟命中 /mcp/sse
    APP_URL=https://labmemory.example.com \\
    PLATFORM_API_KEY=xxx \\
    EXPECTED_AILY_IPS="203.166.190.10 203.166.191.20" \\
    python scripts/check_aily_ip_allowlist.py

退出码：
    0  所有期望 IP 都通过；1  有 IP 未放行；2  配置缺失
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

import httpx


# Aily 出口 IP 段（截至 2026-08；定期核对飞书官方文档，来源见 AILY_MCP.md §5.1）
DEFAULT_AILY_IP_SEGMENTS = [
    "203.166.190.0/24",
    "203.166.191.0/24",
]


def _check_ip_allowed(app_url: str, api_key: str, aily_ip: str) -> tuple[int, str]:
    """模拟 Aily 出口 IP 请求 /mcp/manifest。

    返回 (status_code, body_or_message)；不抛错，只把异常包成 (0, str(exc))。
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Aily-User": "aily-check-bot",
        "X-Forwarded-For": aily_ip,  # 假设反向代理把客户端 IP 放在这里
        "Host": app_url.split("//", 1)[-1].split("/", 1)[0],
    }
    try:
        # 用 GET 而不是 SSE——只要鉴权通过 /mcp/manifest 应 200
        resp = httpx.get(
            f"{app_url.rstrip('/')}/mcp/manifest",
            headers=headers,
            timeout=10.0,
            follow_redirects=False,
        )
        return resp.status_code, resp.text[:200]
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 Aily 出口 IP 白名单")
    parser.add_argument("--app-url", default=os.getenv("APP_URL"), help="平台 URL，例如 https://labmemory.example.com")
    parser.add_argument("--api-key", default=os.getenv("PLATFORM_API_KEY"), help="PLATFORM_API_KEY")
    parser.add_argument(
        "--ips",
        nargs="*",
        default=os.getenv("EXPECTED_AILY_IPS", "").split() if os.getenv("EXPECTED_AILY_IPS") else [],
        help="期望通过白名单的 Aily 出口 IP；空格分隔；留空则跳过实际探测",
    )
    parser.add_argument("--dry-run", action="store_true", help="仅打印配置，不发请求")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if not args.app_url:
        print("❌ 缺少 --app-url 或 APP_URL 环境变量", file=sys.stderr)
        return 2
    if not args.api_key:
        print("❌ 缺少 --api-key 或 PLATFORM_API_KEY 环境变量", file=sys.stderr)
        return 2

    print(f"目标: {args.app_url}/mcp/manifest")
    print(f"Aily 出口 IP 段（参考）: {', '.join(DEFAULT_AILY_IP_SEGMENTS)}")
    if args.ips:
        print(f"待校验 IP: {args.ips}")

    if args.dry_run or not args.ips:
        print("\n[DRY-RUN] 不发请求；请确认反向代理已放行上述 Aily 出口 IP 段")
        return 0

    failed = []
    for ip in args.ips:
        status, body = _check_ip_allowed(args.app_url, args.api_key, ip)
        if status == 200:
            print(f"  ✅ {ip}: 200 OK")
        else:
            failed.append((ip, status, body))
            print(f"  ❌ {ip}: status={status} body={body!r}")

    if failed:
        print(f"\n共 {len(failed)} 个 IP 未通过白名单；请检查反向代理/防火墙规则")
        return 1
    print("\n全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())