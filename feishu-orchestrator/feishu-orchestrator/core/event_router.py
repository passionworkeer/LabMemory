"""
事件路由 - Event Router
处理飞书事件的接收、去重和路由
"""
from typing import Optional

from core.config import Config
from core.utils import now_iso
from core.state_machine import state_machine, MeetingState
from reliability.idempotency import idempotency_guard
from reliability.integration_log import integration_log


class EventRouter:
    """事件路由器"""

    def __init__(self):
        self.handlers = {}

    def register_handler(self, event_type: str, handler):
        """注册事件处理器"""
        self.handlers[event_type] = handler

    def handle_event(self, event: dict) -> dict:
        """
        处理事件
        :param event: 事件数据
        :return: 处理结果
        """
        event_type = event.get("type", event.get("event_type", "unknown"))
        event_id = event.get("event_id", event.get("uuid", ""))
        # 空 event_id 时用 (event_type, hash(payload)) 兜底，避免重复推送无幂等保护
        if not event_id:
            import hashlib
            payload_hash = hashlib.md5(str(event).encode()).hexdigest()[:16]
            event_id = f"derived:{event_type}:{payload_hash}"

        # 记录入站日志
        integration_log.log(
            direction="inbound",
            interface=f"event.{event_type}",
            input_data={"event_id": event_id},
            status="start"
        )

        try:
            # 幂等检查
            idempotency_key = f"event:{event_id}"
            if event_id and idempotency_guard.is_processed(idempotency_key):
                integration_log.log(
                    direction="inbound",
                    interface=f"event.{event_type}",
                    input_data={"event_id": event_id},
                    output_data={"result": "duplicate_skipped"},
                    status="success"
                )
                return {"status": "duplicate", "message": "重复事件，已跳过"}

            # 路由到对应处理器
            handler = self.handlers.get(event_type)
            if not handler:
                # 尝试模糊匹配
                for key, h in self.handlers.items():
                    if key in event_type:
                        handler = h
                        break

            if not handler:
                result = {"status": "ignored", "message": f"未注册的事件类型: {event_type}"}
                integration_log.log(
                    direction="inbound",
                    interface=f"event.{event_type}",
                    input_data={"event_id": event_id},
                    output_data=result,
                    status="success"
                )
                return result

            # 执行处理
            result = handler(event)

            # 标记幂等
            if event_id:
                idempotency_guard.mark(idempotency_key, {"result": "processed"})

            integration_log.log(
                direction="inbound",
                interface=f"event.{event_type}",
                input_data={"event_id": event_id},
                output_data=result,
                status="success"
            )

            return result

        except Exception as e:
            integration_log.log(
                direction="inbound",
                interface=f"event.{event_type}",
                input_data={"event_id": event_id},
                error=str(e),
                status="failed"
            )
            raise

    def handle_meeting_ended(self, event: dict) -> dict:
        """处理会议结束事件"""
        meeting_id = event.get("meeting_id", "")
        if not meeting_id:
            return {"status": "error", "message": "缺少 meeting_id"}

        # 设置状态：等待妙记
        state_machine.set_state(
            f"meeting:{meeting_id}",
            MeetingState.WAITING_MINUTES,
            extra={
                "meeting_id": meeting_id,
                "event": event,
            }
        )

        return {
            "status": "accepted",
            "meeting_id": meeting_id,
            "next_state": MeetingState.WAITING_MINUTES.value,
            "message": "会议已结束，等待妙记生成",
        }

    def handle_minutes_generated(self, event: dict) -> dict:
        """处理妙记生成事件"""
        minute_token = event.get("minute_token", "")
        meeting_id = event.get("meeting_id", "")

        if not minute_token:
            return {"status": "error", "message": "缺少 minute_token"}

        object_id = meeting_id or minute_token

        # 尝试关联会议
        if meeting_id:
            # 检查是否在等待妙记状态
            meeting_state = state_machine.get_state(f"meeting:{meeting_id}")
            if meeting_state and meeting_state.get("state") == MeetingState.WAITING_MINUTES.value:
                # 关联成功，更新状态
                state_machine.transition(
                    f"meeting:{meeting_id}",
                    MeetingState.WAITING_MINUTES,
                    MeetingState.MINUTES_READY,
                    extra={"minute_token": minute_token}
                )
            else:
                # 没有对应的会议记录，直接创建
                state_machine.set_state(
                    f"minutes:{minute_token}",
                    MeetingState.MINUTES_READY,
                    extra={"minute_token": minute_token, "meeting_id": meeting_id}
                )
        else:
            # 没有 meeting_id，直接创建
            state_machine.set_state(
                f"minutes:{minute_token}",
                MeetingState.MINUTES_READY,
                extra={"minute_token": minute_token}
            )

        return {
            "status": "accepted",
            "minute_token": minute_token,
            "meeting_id": meeting_id,
            "next_state": MeetingState.MINUTES_READY.value,
            "message": "妙记已就绪，可以开始编译",
        }

    def handle_card_callback(self, event: dict) -> dict:
        """处理卡片回调事件"""
        # 由 CardHandler 处理
        from core.card_handler import card_handler
        return card_handler.handle_callback(event)


# 单例
event_router = EventRouter()

# 注册默认处理器
event_router.register_handler("meeting.ended_v1", event_router.handle_meeting_ended)
event_router.register_handler("minutes.minute.generated_v1", event_router.handle_minutes_generated)
event_router.register_handler("card.action_triggered", event_router.handle_card_callback)
