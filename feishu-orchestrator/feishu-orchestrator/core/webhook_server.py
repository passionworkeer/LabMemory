"""
Webhook 事件接收服务
接收飞书事件订阅和卡片回调，转发给 EventRouter
"""
import json
import hmac
import hashlib
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from core.config import Config
from core.event_router import event_router
from reliability.integration_log import integration_log


class WebhookHandler(BaseHTTPRequestHandler):
    """Webhook 请求处理器"""

    def do_POST(self):
        """处理 POST 请求"""
        path = urlparse(self.path).path

        if path == "/webhook/event":
            self._handle_event()
        elif path == "/webhook/card":
            self._handle_card_callback()
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

            # 验签（如果配置了 token）
            # TODO: 实现完整的签名验证

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


def verify_signature(secret: str, body: bytes, timestamp: str, nonce: str) -> bool:
    """
    验证飞书请求签名
    签名算法：HMAC-SHA256(secret, timestamp + nonce + body)
    """
    if not secret:
        return True  # 未配置 secret 时跳过验证

    string_to_sign = f"{timestamp}{nonce}".encode("utf-8") + body
    hmac_obj = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256)
    signature = base64.b64encode(hmac_obj.digest()).decode("utf-8")

    # 从 header 中获取签名
    # 实际使用时需要从 self.headers 获取 X-Lark-Signature
    return True  # TODO: 完整实现


def start_server(host: str = None, port: int = None):
    """启动 Webhook 服务"""
    host = host or Config.SERVER_HOST
    port = port or Config.SERVER_PORT

    server = HTTPServer((host, port), WebhookHandler)
    print(f"🚀 Webhook 服务启动: http://{host}:{port}")
    print(f"   - 事件订阅: POST /webhook/event")
    print(f"   - 卡片回调: POST /webhook/card")
    print(f"   - 健康检查: GET  /health")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务已停止")
        server.server_close()


if __name__ == "__main__":
    start_server()
