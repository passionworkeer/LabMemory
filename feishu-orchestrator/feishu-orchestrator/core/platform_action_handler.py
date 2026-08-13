"""
平台动作处理器 - PlatformActionHandler

处理平台通过 POST /webhook/platform 下发的 FeishuActionRequest，
按 action_type 分派到既有飞书适配器，并用 idempotency_key 幂等。
"""
from typing import Optional

from adapters.base_adapter import base_adapter
from adapters.docs_adapter import docs_adapter
from adapters.im_card_adapter import im_card_adapter
from adapters.task_adapter import task_adapter
from core.platform_client import platform_client
from reliability.idempotency import idempotency_guard
from reliability.integration_log import integration_log

REQUIRED_FIELDS = ["action_id", "action_type", "idempotency_key", "actor_user_id", "payload"]


class PlatformActionHandler:
    """平台动作处理器"""

    def handle_action(self, request: dict) -> dict:
        """
        处理平台下发的 FeishuActionRequest
        :param request: 平台动作请求
        :return: 处理结果
        """
        action_id = request.get("action_id")
        action_type = request.get("action_type", "")
        idempotency_key = request.get("idempotency_key", "")

        # 契约必填字段校验
        missing = [f for f in REQUIRED_FIELDS if not request.get(f)]
        if missing:
            return {"ok": False, "status": "invalid", "error": f"缺少必填字段: {', '.join(missing)}"}

        # 幂等：以 platform_action:{idempotency_key} 为键，重复请求只执行一次
        guard_key = f"platform_action:{idempotency_key}"
        previous = idempotency_guard.check(guard_key)
        if previous is not None:
            integration_log.log(
                direction="inbound",
                interface="platform.action",
                input_data={"action_id": action_id, "action_type": action_type},
                output_data=previous,
                status="duplicate",
            )
            return {"ok": True, "status": "duplicate", "result": previous}

        if not idempotency_guard.acquire(guard_key):
            return {"ok": True, "status": "processing", "message": "相同幂等键正在处理中"}

        integration_log.log(
            direction="inbound",
            interface="platform.action",
            input_data={"action_id": action_id, "action_type": action_type},
            status="start",
        )

        try:
            result = self._dispatch(action_type, request.get("payload") or {})
            idempotency_guard.mark(guard_key, {"action_id": action_id, "result": result})
            integration_log.log(
                direction="inbound",
                interface="platform.action",
                input_data={"action_id": action_id, "action_type": action_type},
                output_data=result,
                status="success",
            )
            return {"ok": True, "status": "success", "action_type": action_type, "result": result}
        except Exception as e:
            idempotency_guard.release(guard_key)
            integration_log.log(
                direction="inbound",
                interface="platform.action",
                input_data={"action_id": action_id, "action_type": action_type},
                error=str(e),
                status="failed",
            )
            return {"ok": False, "status": "failed", "action_type": action_type, "error": str(e)}

    def _dispatch(self, action_type: str, payload: dict) -> dict:
        """按 action_type 分派到既有适配器。"""
        if action_type == "send_card":
            return self._send_card(payload)
        if action_type == "create_task":
            return self._create_task(payload)
        if action_type == "publish_doc":
            return self._publish_doc(payload)
        if action_type == "notify":
            return self._notify(payload)
        if action_type == "update_base":
            return self._update_base(payload)
        raise ValueError(f"不支持的 action_type: {action_type}")

    def _send_card(self, payload: dict) -> dict:
        receive_id = payload.get("receive_id")
        if not receive_id:
            raise ValueError("send_card 缺少 receive_id")
        candidate = payload.get("candidate") or {}
        message_id = im_card_adapter.send_review_card(
            receive_id=receive_id,
            candidate=candidate,
            meeting_title=payload.get("meeting_title", ""),
            source_url=payload.get("source_url", ""),
        )
        return {"message_id": message_id}

    def _create_task(self, payload: dict) -> dict:
        candidate = payload.get("candidate") or {}
        task_guid = task_adapter.create_from_candidate(
            candidate=candidate,
            meeting_title=payload.get("meeting_title", ""),
            source_url=payload.get("source_url", ""),
        )
        # 回写平台 feishu_task_guid；回写失败不抹掉已建任务，仅在结果里如实标记
        writeback: dict = {}
        candidate_id = candidate.get("candidate_id")
        if candidate_id:
            try:
                writeback = platform_client.update_task_status(
                    candidate_id=candidate_id,
                    task_guid=task_guid,
                    status="success",
                )
            except Exception as e:  # noqa: BLE001
                writeback = {"error": str(e)}
        return {"task_guid": task_guid, "writeback": writeback}

    def _publish_doc(self, payload: dict) -> dict:
        candidate = payload.get("candidate") or {}
        doc_type = payload.get("doc_type", "success")
        if doc_type not in ("success", "failure", "pending"):
            doc_type = "pending"
        return docs_adapter.publish_knowledge(
            candidate=candidate,
            meeting_title=payload.get("meeting_title", ""),
            doc_type=doc_type,
        )

    def _notify(self, payload: dict) -> dict:
        receive_id = payload.get("receive_id")
        if not receive_id:
            raise ValueError("notify 缺少 receive_id")
        message_id = im_card_adapter.send_alert_card(
            receive_id=receive_id,
            title=payload.get("title", "通知"),
            error=payload.get("reason") or payload.get("error", ""),
            retry_action=payload.get("retry_action"),
        )
        return {"message_id": message_id}

    def _update_base(self, payload: dict) -> dict:
        candidates = payload.get("candidates") or []
        record_ids = base_adapter.batch_add_records(candidates, payload.get("meeting_title", ""))
        return {"record_ids": record_ids}


# 单例
platform_action_handler = PlatformActionHandler()
