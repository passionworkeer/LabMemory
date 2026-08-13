"""
Webhook 事件接收服务
接收飞书事件订阅和卡片回调，转发给 EventRouter
"""
import json
import hmac
import hashlib
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from core.config import Config
from core.event_router import event_router
from core.platform_action_handler import platform_action_handler
from reliability.integration_log import integration_log


# 签名时间窗（秒）：超出该窗口的请求视为重放，直接拒绝
SIGNATURE_MAX_AGE_SECONDS = 300


class WebhookHandler(BaseHTTPRequestHandler):
    """Webhook 请求处理器"""

    def do_POST(self):
        """处理 POST 请求"""
        path = urlparse(self.path).path

        if path == "/webhook/event":
            self._handle_event()
        elif path == "/webhook/card":
            self._handle_card_callback()
        elif path == "/webhook/platform":
            self._handle_platform_action()
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_GET(self):
        """处理 GET 请求（健康检查）"""
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "ok", "service": "feishu-orchestrator"})
        else:
            self._send_json(404, {"error": "Not Found"})

    def _handle_event(self):
        """处理飞书事件订阅"""
        try:
            # 读取请求体
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            # URL 验证（飞书事件订阅的验证挑战）
            if data.get("type") == "url_verification":
                challenge = data.get("challenge", "")
                self._send_json(200, {"challenge": challenge})
                return

            # 验签（mock 模式跳过；real 模式失败即 401，不进入事件路由）
            if not self._verify_request(body, "webhook.event"):
                return

            # 记录入站日志
            integration_log.log(
                direction="inbound",
                interface="webhook.event",
                input_data={"event_type": data.get("type", "unknown")},
                status="start"
            )

            # 路由到事件处理器
            # 飞书事件格式：{ "schema": "2.0", "header": {...}, "event": {...} }
            event_type = data.get("header", {}).get("event_type", "")
            event_id = data.get("header", {}).get("event_id", "")
            event_data = data.get("event", {})

            # 构造统一的事件格式
            event = {
                "type": event_type,
                "event_id": event_id,
                **event_data,
            }

            result = event_router.handle_event(event)

            integration_log.log(
                direction="inbound",
                interface="webhook.event",
                input_data={"event_type": event_type},
                output_data=result,
                status="success"
            )

            self._send_json(200, {"code": 0, "msg": "success", "data": result})

        except Exception as e:
            integration_log.log(
                direction="inbound",
                interface="webhook.event",
                input_data={},
                error=str(e),
                status="failed"
            )
            self._send_json(500, {"error": str(e)})

    def _handle_card_callback(self):
        """处理卡片回调"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            # URL 验证
            if data.get("type") == "url_verification":
                challenge = data.get("challenge", "")
                self._send_json(200, {"challenge": challenge})
                return

            # 验签（mock 模式跳过；real 模式失败即 401，不进入卡片处理）
            if not self._verify_request(body, "webhook.card_callback"):
                return

            # 记录入站日志
            integration_log.log(
                direction="inbound",
                interface="webhook.card_callback",
                input_data={"action": data.get("action", {})},
                status="start"
            )

            # 路由到卡片处理器
            result = event_router.handle_card_callback(data)

            integration_log.log(
                direction="inbound",
                interface="webhook.card_callback",
                input_data={"action": data.get("action", {})},
                output_data=result,
                status="success"
            )

            self._send_json(200, result)

        except Exception as e:
            integration_log.log(
                direction="inbound",
                interface="webhook.card_callback",
                input_data={},
                error=str(e),
                status="failed"
            )
            self._send_json(500, {"error": str(e)})

    def _handle_platform_action(self):
        """处理平台下发的 FeishuActionRequest（反向联动）。"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)

            # 鉴权：mock 模式限 localhost；real 模式校验 Bearer {PLATFORM_API_KEY}
            if not self._verify_platform_key():
                return

            integration_log.log(
                direction="inbound",
                interface="webhook.platform_action",
                input_data={"action_id": data.get("action_id"), "action_type": data.get("action_type")},
                status="start"
            )

            result = platform_action_handler.handle_action(data)

            integration_log.log(
                direction="inbound",
                interface="webhook.platform_action",
                input_data={"action_id": data.get("action_id")},
                output_data=result,
                status="success"
            )

            self._send_json(200, result)

        except Exception as e:
            integration_log.log(
                direction="inbound",
                interface="webhook.platform_action",
                input_data={},
                error=str(e),
                status="failed"
            )
            self._send_json(500, {"ok": False, "error": str(e)})

    def _verify_platform_key(self) -> bool:
        """平台动作请求鉴权：mock 仅 localhost；real 校验 Authorization: Bearer {PLATFORM_API_KEY}。"""
        if Config.is_mock_mode():
            client_ip = (getattr(self, "client_address", None) or ("",))[0]
            if client_ip not in ("127.0.0.1", "::1", "localhost"):
                self._send_json(403, {"ok": False, "error": "RUN_MODE=mock 仅允许本地访问；生产请设 RUN_MODE=real"})
                return False
            return True

        expected = Config.PLATFORM_API_KEY
        if not expected:
            self._send_json(500, {"ok": False, "error": "未配置 PLATFORM_API_KEY"})
            return False

        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:].strip()
            if hmac.compare_digest(token, expected):
                return True

        self._send_json(401, {"ok": False, "error": "invalid platform api key"})
        return False

    def _verify_request(self, body: bytes, interface: str) -> bool:
        """
        校验请求签名。

        mock 模式跳过；real 模式验签失败时直接返回 401，调用方必须立即 return，
        不得继续进入事件路由或卡片处理。
        """
        if Config.is_mock_mode():
            # mock 模式：限 localhost，拒绝远端（防未设 RUN_MODE=real 即暴露导致验签旁路）
            client_ip = (getattr(self, "client_address", None) or ("",))[0]
            if client_ip not in ("127.0.0.1", "::1", "localhost"):
                self._send_json(403, {"error": "RUN_MODE=mock 仅允许本地访问；生产请设 RUN_MODE=real"})
                return False
            return True

        if verify_signature(
            Config.CARD_CALLBACK_ENCRYPT_KEY,
            body,
            self.headers.get("X-Lark-Request-Timestamp", ""),
            self.headers.get("X-Lark-Request-Nonce", ""),
            self.headers.get("X-Lark-Signature", ""),
        ):
            return True

        integration_log.log(
            direction="inbound",
            interface=interface,
            input_data={},
            error="signature verification failed",
            status="failed"
        )
        self._send_json(401, {"code": 401, "msg": "signature verification failed"})
        return False

    def _send_json(self, status_code, data):
        """发送 JSON 响应"""
        response = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, format, *args):
        """覆盖默认日志，使用我们的日志系统"""
        # 静默处理，避免污染 stdout
        pass


def verify_signature(
    encrypt_key: str,
    body: bytes,
    timestamp: str,
    nonce: str,
    signature: str,
    max_age_seconds: int = SIGNATURE_MAX_AGE_SECONDS,
) -> bool:
    """
    验证飞书请求签名

    签名算法（飞书事件订阅 / 卡片回调）：
        sha256(timestamp + nonce + encrypt_key + raw_body) 的小写十六进制摘要
    请求头：X-Lark-Request-Timestamp / X-Lark-Request-Nonce / X-Lark-Signature

    :return: 验签是否通过。缺少任一要素、时间戳超出窗口或摘要不匹配均返回 False
    """
    if not (encrypt_key and timestamp and nonce and signature):
        return False

    # 时间窗校验，防止签名被截获后重放
    try:
        if abs(time.time() - int(timestamp)) > max_age_seconds:
            return False
    except (TypeError, ValueError):
        return False

    sha256 = hashlib.sha256()
    sha256.update(f"{timestamp}{nonce}{encrypt_key}".encode("utf-8") + body)

    # 常量时间比较，避免计时攻击
    return hmac.compare_digest(sha256.hexdigest(), signature.strip().lower())


def start_server(host: str = None, port: int = None):
    """启动 Webhook 服务"""
    host = host or Config.SERVER_HOST
    port = port or Config.SERVER_PORT

    server = HTTPServer((host, port), WebhookHandler)
    print(f"🚀 Webhook 服务启动: http://{host}:{port}")
    print(f"   - 事件订阅: POST /webhook/event")
    print(f"   - 卡片回调: POST /webhook/card")
    print(f"   - 平台动作: POST /webhook/platform")
    print(f"   - 健康检查: GET  /health")
    if Config.is_mock_mode():
        print(f"   ⚠️  验签已跳过（RUN_MODE=mock，仅供本地演示）")
    elif not Config.CARD_CALLBACK_ENCRYPT_KEY:
        print(f"   ⚠️  未配置 CARD_CALLBACK_ENCRYPT_KEY，所有请求将被拒绝（401）")
    else:
        print(f"   - 验签: 已启用（sha256 + {SIGNATURE_MAX_AGE_SECONDS}s 时间窗）")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
        server.server_close()


if __name__ == "__main__":
    start_server()
