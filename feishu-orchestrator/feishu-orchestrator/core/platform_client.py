"""
LabMemory 平台客户端 - PlatformClient
负责与 LabMemory 平台的接口对接
"""
import json
import urllib.request
import urllib.error
from typing import Optional

from core.config import Config
from core.utils import now_iso, generate_id
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry, RetryableError, NonRetryableError


class PlatformClient:
    """LabMemory 平台客户端"""

    def __init__(self):
        self.api_base = Config.PLATFORM_API_BASE
        self.api_key = Config.PLATFORM_API_KEY
        self.mock_mode = Config.is_mock_mode()
        # Mock 模式下的内存状态
        self._mock_candidates = {}  # candidate_id -> candidate data

    @with_retry(interface_name="platform.submit_candidates")
    def submit_candidates(self, candidate_package: dict) -> dict:
        """
        提交候选决策到平台
        :param candidate_package: CandidatePackage
        :return: 提交结果
        """
        integration_log.log(
            direction="outbound",
            interface="platform.submit_candidates",
            input_data={
                "source_package_id": candidate_package.get("source_package_id"),
                "candidate_count": len(candidate_package.get("candidates", [])),
            },
            status="start"
        )

        try:
            if self.mock_mode:
                result = self._mock_submit_candidates(candidate_package)
            else:
                result = self._real_submit_candidates(candidate_package)

            integration_log.log(
                direction="outbound",
                interface="platform.submit_candidates",
                input_data={"source_package_id": candidate_package.get("source_package_id")},
                output_data=result,
                status="success"
            )
            return result

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="platform.submit_candidates",
                input_data={"source_package_id": candidate_package.get("source_package_id")},
                error=str(e),
                status="failed"
            )
            raise

    def forward_card_callback(self, callback_data: dict) -> dict:
        """
        转发卡片回调到平台
        :param callback_data: 卡片回调数据
        :return: 平台返回结果
        """
        integration_log.log(
            direction="inbound",
            interface="platform.card_callback",
            input_data={"action": callback_data.get("action", {}).get("value", {}).get("action_type")},
            status="start"
        )

        try:
            if self.mock_mode:
                result = self._mock_card_callback(callback_data)
            else:
                result = self._real_card_callback(callback_data)

            integration_log.log(
                direction="inbound",
                interface="platform.card_callback",
                input_data={"action": callback_data.get("action", {}).get("value", {}).get("action_type")},
                output_data=result,
                status="success"
            )
            return result

        except Exception as e:
            integration_log.log(
                direction="inbound",
                interface="platform.card_callback",
                input_data={"action": callback_data.get("action", {}).get("value", {}).get("action_type")},
                error=str(e),
                status="failed"
            )
            raise

    def update_task_status(self, candidate_id: str, task_guid: str, status: str, extra: Optional[dict] = None):
        """
        更新任务状态到平台
        :param candidate_id: 候选 ID
        :param task_guid: 飞书任务 GUID
        :param status: 状态：pending / success / failed
        :param extra: 额外信息
        """
        integration_log.log(
            direction="outbound",
            interface="platform.update_task_status",
            input_data={"candidate_id": candidate_id, "task_guid": task_guid, "status": status},
            status="start"
        )

        try:
            if self.mock_mode:
                result = self._mock_update_task_status(candidate_id, task_guid, status, extra)
            else:
                result = self._real_update_task_status(candidate_id, task_guid, status, extra)

            integration_log.log(
                direction="outbound",
                interface="platform.update_task_status",
                input_data={"candidate_id": candidate_id, "task_guid": task_guid, "status": status},
                output_data=result,
                status="success"
            )
            return result

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="platform.update_task_status",
                input_data={"candidate_id": candidate_id, "task_guid": task_guid, "status": status},
                error=str(e),
                status="failed"
            )
            raise

    def get_candidate(self, candidate_id: str) -> dict:
        """获取候选详情"""
        if self.mock_mode:
            return self._mock_get_candidate(candidate_id)
        return self._real_get_candidate(candidate_id)

    def submit_meeting(self, meeting_package: dict) -> dict:
        """提交会议包到平台（POST /v1/meetings），使平台能按 source_package_id 反查会议。"""
        if self.mock_mode:
            return self._mock_submit_meeting(meeting_package)
        return self._real_submit_meeting(meeting_package)

    # ==================== Mock 实现 ====================

    def _mock_submit_meeting(self, meeting_package: dict) -> dict:
        """Mock 提交会议包"""
        return {"meeting_id": meeting_package.get("meeting_id"), "created": True}

    def _mock_submit_candidates(self, candidate_package: dict) -> dict:
        """Mock 提交候选"""
        # 模拟平台审核：所有候选都进入待复核状态
        candidates = candidate_package.get("candidates", [])
        results = []

        for cand in candidates:
            candidate_id = cand.get("candidate_id")
            # 保存到内存
            self._mock_candidates[candidate_id] = {
                **cand,
                "status": "pending_review",
                "submitted_at": now_iso(),
                "task_guid": None,
            }
            results.append({
                "candidate_id": candidate_id,
                "status": "pending_review",
                "review_url": f"https://labmemory.example.com/review/{candidate_id}",
            })

        return {
            "status": "submitted",
            "submitted_at": now_iso(),
            "results": results,
            "review_count": len(results),
            "message": "候选已提交，等待复核",
        }

    def _mock_card_callback(self, callback_data: dict) -> dict:
        """Mock 卡片回调"""
        action = callback_data.get("action", {}).get("value", {})
        action_type = action.get("action_type", "")
        candidate_id = action.get("candidate_id", "")

        # 卡片动作类型统一为 approve/revise/reject（对齐平台 Literal，删过去式别名）
        is_approved = action_type == "approve"
        is_rejected = action_type == "reject"
        is_revise = action_type == "revise"

        if is_approved:
            # 更新内存状态
            if candidate_id in self._mock_candidates:
                self._mock_candidates[candidate_id]["status"] = "approved"
            return {
                "status": "approved",
                "candidate_id": candidate_id,
                "action_audit": "pass",
                "message": "已批准，将创建任务",
            }
        elif is_rejected:
            if candidate_id in self._mock_candidates:
                self._mock_candidates[candidate_id]["status"] = "rejected"
            return {
                "status": "rejected",
                "candidate_id": candidate_id,
                "message": "已驳回",
            }
        elif is_revise:
            if candidate_id in self._mock_candidates:
                self._mock_candidates[candidate_id]["status"] = "pending_revision"
            return {
                "status": "pending_revision",
                "candidate_id": candidate_id,
                "message": "待修改",
            }
        else:
            return {
                "status": "received",
                "candidate_id": candidate_id,
                "message": "回调已接收",
            }

    def _mock_update_task_status(self, candidate_id: str, task_guid: str, status: str, extra: Optional[dict] = None):
        """Mock 更新任务状态"""
        if candidate_id in self._mock_candidates:
            self._mock_candidates[candidate_id]["task_guid"] = task_guid
            self._mock_candidates[candidate_id]["task_status"] = status
            if status == "success":
                self._mock_candidates[candidate_id]["status"] = "completed"
        return {"status": "ok"}

    def _mock_get_candidate(self, candidate_id: str) -> dict:
        """Mock 获取候选详情"""
        if candidate_id in self._mock_candidates:
            return self._mock_candidates[candidate_id]
        return {
            "candidate_id": candidate_id,
            "type": "decision",
            "title": "示例决策",
            "status": "pending_review",
            "description": "这是一个示例决策",
        }

    # ==================== 真实实现 ====================

    def _real_submit_meeting(self, meeting_package: dict) -> dict:
        """真实提交会议包到平台"""
        url = f"{self.api_base}/v1/meetings"
        return self._http_post(url, meeting_package)

    def _real_submit_candidates(self, candidate_package: dict) -> dict:
        """真实提交候选到平台"""
        url = f"{self.api_base}/v1/candidates"
        return self._http_post(url, candidate_package)

    def _real_card_callback(self, callback_data: dict) -> dict:
        """真实转发卡片回调"""
        url = f"{self.api_base}/v1/card/callback"
        return self._http_post(url, callback_data)

    def _real_update_task_status(self, candidate_id: str, task_guid: str, status: str, extra: Optional[dict] = None) -> dict:
        """真实更新任务状态"""
        url = f"{self.api_base}/v1/task/status"
        data = {
            "candidate_id": candidate_id,
            "feishu_task_guid": task_guid,
            "status": status,
        }
        if extra:
            data.update(extra)
        return self._http_post(url, data)

    def _real_get_candidate(self, candidate_id: str) -> dict:
        """真实获取候选详情"""
        url = f"{self.api_base}/v1/candidates/{candidate_id}"
        return self._http_get(url)

    def _http_post(self, url: str, data: dict) -> dict:
        """HTTP POST 请求"""
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            msg = f"HTTP {e.code}: {error_body}"
            # 按可恢复性分类：429/5xx 可重试，4xx 不可重试（保留 code，不靠字面串判定）
            if e.code == 429 or 500 <= e.code < 600:
                raise RetryableError(msg) from e
            raise NonRetryableError(msg) from e
        except urllib.error.URLError as e:
            raise RetryableError(f"连接失败: {e}") from e

    def _http_get(self, url: str) -> dict:
        """HTTP GET 请求"""
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
            },
            method="GET"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="ignore")
            msg = f"HTTP {e.code}: {error_body}"
            # 按可恢复性分类：429/5xx 可重试，4xx 不可重试（保留 code，不靠字面串判定）
            if e.code == 429 or 500 <= e.code < 600:
                raise RetryableError(msg) from e
            raise NonRetryableError(msg) from e
        except urllib.error.URLError as e:
            raise RetryableError(f"连接失败: {e}") from e


# 单例
platform_client = PlatformClient()
