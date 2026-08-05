"""
LabMemory 平台 Mock Server
供飞书侧开发和联调使用，模拟平台 API
支持：提交候选、卡片回调、任务状态更新、状态查询等
"""
import json
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from core.utils import now_iso, generate_id, compute_hash


# ==================== Mock 状态管理 ====================

class MockPlatformState:
    """Mock 平台状态管理"""

    def __init__(self):
        self.candidates = {}  # candidate_id -> candidate data
        self.callbacks = []  # 回调记录
        self.task_updates = []  # 任务更新记录
        self.submissions = []  # 提交记录

    def reset(self):
        """重置所有状态"""
        self.candidates.clear()
        self.callbacks.clear()
        self.task_updates.clear()
        self.submissions.clear()

    def submit_candidates(self, candidate_package: dict) -> dict:
        """提交候选决策"""
        submission_id = generate_id("sub")
        candidates = candidate_package.get("candidates", [])

        results = []
        for cand in candidates:
            candidate_id = cand.get("candidate_id", generate_id("cand"))
            cand_data = {
                **cand,
                "candidate_id": candidate_id,
                "status": "pending_review",
                "submitted_at": now_iso(),
                "task_guid": None,
                "review_result": None,
            }
            self.candidates[candidate_id] = cand_data
            results.append({
                "candidate_id": candidate_id,
                "status": "pending_review",
                "needs_review": cand.get("needs_review", True),
            })

        self.submissions.append({
            "submission_id": submission_id,
            "package": candidate_package,
            "results": results,
            "created_at": now_iso(),
        })

        return {
            "submission_id": submission_id,
            "results": results,
            "message": "Candidates submitted successfully",
        }

    def handle_card_callback(self, callback_data: dict) -> dict:
        """处理卡片回调"""
        candidate_id = callback_data.get("candidate_id", "")
        action_type = callback_data.get("action_type", "")

        # 规范化 action_type
        action = action_type.lower()
        if action in ("approve", "approved", "confirm", "pass"):
            status = "approved"
            action_audit = "pass"
        elif action in ("reject", "rejected", "deny"):
            status = "rejected"
            action_audit = "reject"
        elif action in ("revise", "pending_revision", "modify"):
            status = "pending_revision"
            action_audit = "revise"
        elif action in ("block", "blocked"):
            status = "blocked"
            action_audit = "block"
        else:
            status = "received"
            action_audit = "unknown"

        # 更新候选状态
        if candidate_id in self.candidates:
            self.candidates[candidate_id]["status"] = status
            self.candidates[candidate_id]["review_result"] = {
                "action": action_type,
                "reviewed_at": now_iso(),
                "reviewer": callback_data.get("reviewer_id", "unknown"),
            }

        # 记录回调
        callback_record = {
            "callback_id": generate_id("cb"),
            "candidate_id": candidate_id,
            "action_type": action_type,
            "status": status,
            "action_audit": action_audit,
            "received_at": now_iso(),
        }
        self.callbacks.append(callback_record)

        return {
            "status": status,
            "action_audit": action_audit,
            "candidate_id": candidate_id,
            "message": f"Callback processed: {status}",
        }

    def update_task_status(self, candidate_id: str, task_guid: str, status: str, extra: dict = None) -> dict:
        """更新任务状态"""
        if candidate_id in self.candidates:
            self.candidates[candidate_id]["task_guid"] = task_guid
            self.candidates[candidate_id]["task_status"] = status

        update_record = {
            "update_id": generate_id("tsk"),
            "candidate_id": candidate_id,
            "task_guid": task_guid,
            "status": status,
            "extra": extra or {},
            "updated_at": now_iso(),
        }
        self.task_updates.append(update_record)

        return {
            "success": True,
            "candidate_id": candidate_id,
            "task_guid": task_guid,
            "status": status,
            "message": "Task status updated",
        }

    def get_candidate(self, candidate_id: str) -> Optional[dict]:
        """获取候选详情"""
        return self.candidates.get(candidate_id)

    def get_state_summary(self) -> dict:
        """获取状态摘要"""
        status_counts = {}
        for cand in self.candidates.values():
            status = cand.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "total_candidates": len(self.candidates),
            "status_counts": status_counts,
            "total_submissions": len(self.submissions),
            "total_callbacks": len(self.callbacks),
            "total_task_updates": len(self.task_updates),
        }


# 全局状态
mock_state = MockPlatformState()


# ==================== HTTP 请求处理器 ====================

class MockPlatformHandler(BaseHTTPRequestHandler):
    """Mock 平台 HTTP 请求处理器"""

    def _send_json(self, data: dict, status_code: int = 200):
        """发送 JSON 响应"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))

    def _read_json_body(self) -> dict:
        """读取 JSON 请求体"""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _verify_auth(self) -> bool:
        """验证 API Key（简化实现）"""
        auth_header = self.headers.get("Authorization", "")
        # Mock 模式下，只要有 Authorization 头就通过，或者完全不验证
        return True  # 简化：Mock 模式不做严格验证

    # ==================== GET 请求 ====================

    def do_GET(self):
        """处理 GET 请求"""
        path = self.path.split("?")[0]  # 去掉 query string

        # 健康检查
        if path == "/health":
            self._send_json({
                "status": "ok",
                "service": "LabMemory Mock Platform",
                "version": "1.0.0",
                "time": now_iso(),
            })
            return

        # 获取候选详情
        if path.startswith("/api/v1/candidates/"):
            candidate_id = path.split("/")[-1]
            if not self._verify_auth():
                self._send_json({"error": "Unauthorized"}, 401)
                return

            cand = mock_state.get_candidate(candidate_id)
            if cand:
                self._send_json({"data": cand})
            else:
                self._send_json({"error": "Candidate not found"}, 404)
            return

        # Mock 状态摘要（调试用）
        if path == "/api/v1/mock/state":
            self._send_json({
                "data": mock_state.get_state_summary(),
            })
            return

        # Mock 状态详情（调试用）
        if path == "/api/v1/mock/state/detail":
            self._send_json({
                "data": {
                    "candidates": mock_state.candidates,
                    "submissions": mock_state.submissions,
                    "callbacks": mock_state.callbacks,
                    "task_updates": mock_state.task_updates,
                }
            })
            return

        # 404
        self._send_json({"error": "Not found", "path": path}, 404)

    # ==================== POST 请求 ====================

    def do_POST(self):
        """处理 POST 请求"""
        path = self.path.split("?")[0]

        if not self._verify_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return

        body = self._read_json_body()

        # 提交候选
        if path == "/api/v1/candidates":
            result = mock_state.submit_candidates(body)
            self._send_json(result, 201)
            return

        # 卡片回调
        if path == "/api/v1/card/callback":
            result = mock_state.handle_card_callback(body)
            self._send_json(result)
            return

        # 任务状态更新
        if path == "/api/v1/task/status":
            candidate_id = body.get("candidate_id", "")
            task_guid = body.get("task_guid", "")
            status = body.get("status", "")
            extra = body.get("extra", {})
            result = mock_state.update_task_status(candidate_id, task_guid, status, extra)
            self._send_json(result)
            return

        # 重置 Mock 状态（调试用）
        if path == "/api/v1/mock/reset":
            mock_state.reset()
            self._send_json({"message": "Mock state reset successfully"})
            return

        # 404
        self._send_json({"error": "Not found", "path": path}, 404)

    # ==================== 日志输出 ====================

    def log_message(self, format, *args):
        """简化日志输出"""
        print(f"[MockPlatform] {self.address_string()} - {format % args}")


# ==================== 启动服务器 ====================

def start_mock_server(host: str = "0.0.0.0", port: int = 8081):
    """
    启动 Mock 平台服务器
    :param host: 监听地址
    :param port: 监听端口
    """
    server = HTTPServer((host, port), MockPlatformHandler)
    print(f"\n{'='*60}")
    print(f"🚀 LabMemory Mock Platform Server 启动成功")
    print(f"{'='*60}")
    print(f"📡 监听地址: http://{host}:{port}")
    print(f"")
    print(f"📋 可用接口:")
    print(f"   GET  /health                          - 健康检查")
    print(f"   POST /api/v1/candidates               - 提交候选")
    print(f"   POST /api/v1/card/callback            - 卡片回调")
    print(f"   POST /api/v1/task/status              - 任务状态更新")
    print(f"   GET  /api/v1/candidates/{{id}}         - 获取候选详情")
    print(f"")
    print(f"🔧 调试接口:")
    print(f"   GET  /api/v1/mock/state               - 状态摘要")
    print(f"   GET  /api/v1/mock/state/detail        - 状态详情")
    print(f"   POST /api/v1/mock/reset               - 重置状态")
    print(f"")
    print(f"💡 使用方式:")
    print(f"   设置环境变量 PLATFORM_API_BASE=http://localhost:{port}")
    print(f"   设置环境变量 PLATFORM_API_KEY=mock-key")
    print(f"   然后运行飞书编排系统即可联调")
    print(f"{'='*60}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Mock Server 已停止")
        server.server_close()


if __name__ == "__main__":
    import sys
    port = 8081
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    start_mock_server(port=port)
