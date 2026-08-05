"""
卡片回调处理器 - CardHandler
处理交互卡片的回调，转发到平台并执行后续动作
"""
from typing import Optional

from core.config import Config
from core.utils import now_iso
from core.platform_client import platform_client
from adapters.im_card_adapter import im_card_adapter
from adapters.task_adapter import task_adapter
from core.state_machine import state_machine, MeetingState
from reliability.idempotency import idempotency_guard
from reliability.integration_log import integration_log


class CardHandler:
    """卡片回调处理器"""

    def __init__(self):
        self.mock_mode = Config.is_mock_mode()

    def handle_callback(self, callback_data: dict) -> dict:
        """
        处理卡片回调
        :param callback_data: 回调数据
        :return: 处理结果
        """
        action = callback_data.get("action", {})
        value = action.get("value", {})
        action_type = value.get("action_type", "")
        candidate_id = value.get("candidate_id", "")
        callback_token = callback_data.get("token", "")

        # 幂等检查
        idempotency_key = f"card_callback:{callback_token}"
        if callback_token and idempotency_guard.is_processed(idempotency_key):
            return {"status": "duplicate", "message": "重复回调，已跳过"}

        integration_log.log(
            direction="inbound",
            interface="card.callback",
            input_data={
                "action_type": action_type,
                "candidate_id": candidate_id,
            },
            status="start"
        )

        try:
            # 转发到平台
            platform_result = platform_client.forward_card_callback(callback_data)

            # 根据平台返回结果执行后续动作
            status = platform_result.get("status", "")

            if status == "approved" and platform_result.get("action_audit") == "pass":
                # 已批准，创建任务
                self._handle_approved(candidate_id, platform_result, callback_data)
            elif status == "rejected":
                # 已驳回
                self._handle_rejected(candidate_id, platform_result, callback_data)
            elif status == "blocked":
                # 已阻断
                self._handle_blocked(candidate_id, platform_result, callback_data)

            # 标记幂等
            if callback_token:
                idempotency_guard.mark(idempotency_key, {"result": "processed"})

            integration_log.log(
                direction="inbound",
                interface="card.callback",
                input_data={"action_type": action_type, "candidate_id": candidate_id},
                output_data=platform_result,
                status="success"
            )

            return platform_result

        except Exception as e:
            integration_log.log(
                direction="inbound",
                interface="card.callback",
                input_data={"action_type": action_type, "candidate_id": candidate_id},
                error=str(e),
                status="failed"
            )
            raise

    def _handle_approved(self, candidate_id: str, platform_result: dict, callback_data: dict):
        """处理已批准"""
        # 更新状态
        state_machine.set_state(
            f"candidate:{candidate_id}",
            MeetingState.APPROVED,
            extra={"platform_result": platform_result}
        )

        # 获取候选详情
        try:
            candidate = platform_client.get_candidate(candidate_id)
        except Exception:
            candidate = {"candidate_id": candidate_id, "title": "已批准的候选"}

        # 创建任务
        try:
            task_guid = task_adapter.create_from_candidate(
                candidate=candidate,
                meeting_title=candidate.get("meeting_title", "未知会议"),
                source_url=candidate.get("source_url", ""),
            )

            # 回写平台
            platform_client.update_task_status(
                candidate_id=candidate_id,
                task_guid=task_guid,
                status="success",
            )

            # 更新状态为完成
            state_machine.set_state(
                f"candidate:{candidate_id}",
                MeetingState.COMPLETED,
                extra={"task_guid": task_guid}
            )

            # 发送已批准卡片
            user_id = callback_data.get("open_id", "")
            if user_id:
                task_url = f"https://bytedance.larkoffice.com/task/{task_guid}"
                im_card_adapter.send_approved_card(
                    receive_id=user_id,
                    candidate=candidate,
                    task_url=task_url,
                )

        except Exception as e:
            # 任务创建失败
            platform_client.update_task_status(
                candidate_id=candidate_id,
                task_guid="",
                status="failed",
                extra={"error": str(e)},
            )
            raise

    def _handle_rejected(self, candidate_id: str, platform_result: dict, callback_data: dict):
        """处理已驳回"""
        state_machine.set_state(
            f"candidate:{candidate_id}",
            MeetingState.FAILED,
            extra={
                "platform_result": platform_result,
                "reason": "rejected",
            }
        )

    def _handle_blocked(self, candidate_id: str, platform_result: dict, callback_data: dict):
        """处理已阻断"""
        state_machine.set_state(
            f"candidate:{candidate_id}",
            MeetingState.BLOCKED,
            extra={"platform_result": platform_result}
        )

        # 发送阻断卡片
        user_id = callback_data.get("open_id", "")
        if user_id:
            reason = platform_result.get("message", "")
            im_card_adapter.send_blocked_card(
                receive_id=user_id,
                candidate={"candidate_id": candidate_id, "title": "候选决策"},
                reason=reason,
            )


# 单例
card_handler = CardHandler()
