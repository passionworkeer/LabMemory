"""
主编排器 - Pipeline Orchestrator
串联整个主链路：妙记 → Aily 编译 → 提交平台 → 发送卡片
"""
from typing import Optional

from core.config import Config
from core.utils import now_iso, generate_id
from core.state_machine import state_machine, MeetingState
from core.platform_client import platform_client
from adapters.minutes_adapter import minutes_adapter
from adapters.aily_adapter import aily_adapter
from adapters.im_card_adapter import im_card_adapter
from reliability.idempotency import idempotency_guard
from reliability.integration_log import integration_log


class PipelineOrchestrator:
    """主链路编排器"""

    def __init__(self):
        self.mock_mode = Config.is_mock_mode()

    def run_from_minutes_url(self, minutes_url: str, reviewer_id: str = "") -> dict:
        """
        从妙记链接运行完整流程
        :param minutes_url: 妙记链接
        :param reviewer_id: 复核人 ID
        :return: 运行结果
        """
        print(f"[Pipeline] 开始处理妙记: {minutes_url}")

        try:
            # Step 1: 获取妙记详情
            print("[Pipeline] Step 1: 获取妙记详情...")
            minutes_detail = minutes_adapter.get_by_url(minutes_url)
            meeting_package = minutes_adapter.to_meeting_package(minutes_detail)

            source_id = meeting_package["source_object_id"]
            meeting_title = meeting_package["title"]

            # 幂等检查
            idempotency_key = f"pipeline:{source_id}"
            cached = idempotency_guard.check(idempotency_key)
            if cached:
                print("[Pipeline] 检测到重复处理，直接返回缓存结果")
                return cached

            # 更新状态
            state_machine.set_state(
                f"minutes:{source_id}",
                MeetingState.MINUTES_READY,
                extra={"meeting_title": meeting_title}
            )

            # Step 2: Aily 编译
            print("[Pipeline] Step 2: Aily 决策编译...")
            state_machine.set_state(
                f"minutes:{source_id}",
                MeetingState.COMPILING,
                extra={"meeting_title": meeting_title}
            )

            candidate_package = aily_adapter.compile(meeting_package)

            print(f"[Pipeline] 编译完成，识别到 {len(candidate_package['candidates'])} 个候选决策")

            # Step 3: 提交平台
            print("[Pipeline] Step 3: 提交到 LabMemory 平台...")
            state_machine.set_state(
                f"minutes:{source_id}",
                MeetingState.SUBMITTED,
                extra={
                    "meeting_title": meeting_title,
                    "candidate_count": len(candidate_package["candidates"]),
                }
            )

            submit_result = platform_client.submit_candidates(candidate_package)
            print(f"[Pipeline] 提交成功，状态: {submit_result.get('status')}")

            # Step 4: 发送复核卡片
            if reviewer_id:
                print("[Pipeline] Step 4: 发送复核卡片...")
                candidates = candidate_package.get("candidates", [])
                for i, candidate in enumerate(candidates[:3]):  # 最多发3张
                    message_id = im_card_adapter.send_review_card(
                        receive_id=reviewer_id,
                        candidate=candidate,
                        meeting_title=meeting_title,
                        source_url=minutes_detail.source_url or "",
                    )
                    print(f"[Pipeline] 已发送卡片 {i+1}/{len(candidates)}: {candidate.get('title', '')[:30]}")

                state_machine.set_state(
                    f"minutes:{source_id}",
                    MeetingState.REVIEWING,
                    extra={
                        "meeting_title": meeting_title,
                        "reviewer_id": reviewer_id,
                    }
                )

            # 汇总结果
            result = {
                "status": "success",
                "source_id": source_id,
                "meeting_title": meeting_title,
                "candidate_count": len(candidate_package.get("candidates", [])),
                "risk_count": len(candidate_package.get("risks", [])),
                "action_count": len(candidate_package.get("action_items", [])),
                "submit_result": submit_result,
                "review_cards_sent": bool(reviewer_id),
                "completed_at": now_iso(),
            }

            # 标记幂等
            idempotency_guard.mark(idempotency_key, result)

            # 更新最终状态
            if reviewer_id:
                final_state = MeetingState.REVIEWING
            else:
                final_state = MeetingState.SUBMITTED

            state_machine.set_state(
                f"minutes:{source_id}",
                final_state,
                extra=result
            )

            print("[Pipeline] ✅ 流程执行成功!")
            return result

        except Exception as e:
            print(f"[Pipeline] ❌ 流程失败: {e}")

            # 更新状态
            source_id = minutes_url
            state_machine.set_state(
                f"minutes:{source_id}",
                MeetingState.FAILED,
                extra={"error": str(e)}
            )

            raise

    def run_from_minutes_token(self, minute_token: str, reviewer_id: str = "") -> dict:
        """从 minute_token 运行流程"""
        url = f"https://bytedance.larkoffice.com/minutes/{minute_token}"
        return self.run_from_minutes_url(url, reviewer_id)

    def run_from_text(self, text: str, title: str = "手动输入", reviewer_id: str = "") -> dict:
        """
        从纯文本运行流程（人工兜底）
        :param text: 会议文本
        :param title: 会议标题
        :param reviewer_id: 复核人 ID
        """
        print(f"[Pipeline] 从文本运行: {title}")

        # 构造 MeetingPackage
        meeting_package = {
            "schema_version": "1.0.0",
            "source": "manual_upload",
            "source_object_id": generate_id("manual"),
            "meeting_id": "",
            "title": title,
            "start_time": now_iso(),
            "end_time": now_iso(),
            "organizer": "manual",
            "participants": [],
            "content": {
                "transcript": [
                    {
                        "speaker": "未知",
                        "start_offset_sec": 0,
                        "end_offset_sec": len(text),
                        "text": text,
                    }
                ],
                "chapters": [],
                "summary": "",
                "action_items": [],
            },
            "source_url": "",
            "captured_at": now_iso(),
            "metadata": {"source": "manual_input"},
        }

        source_id = meeting_package["source_object_id"]

        # 幂等检查
        idempotency_key = f"pipeline:{source_id}"
        cached = idempotency_guard.check(idempotency_key)
        if cached:
            return cached

        try:
            # Aily 编译
            print("[Pipeline] Aily 决策编译...")
            candidate_package = aily_adapter.compile(meeting_package)

            # 提交平台
            print("[Pipeline] 提交到平台...")
            submit_result = platform_client.submit_candidates(candidate_package)

            # 发送卡片
            if reviewer_id:
                print("[Pipeline] 发送复核卡片...")
                candidates = candidate_package.get("candidates", [])
                for candidate in candidates[:3]:
                    im_card_adapter.send_review_card(
                        receive_id=reviewer_id,
                        candidate=candidate,
                        meeting_title=title,
                        source_url="",
                    )

            result = {
                "status": "success",
                "source_id": source_id,
                "meeting_title": title,
                "candidate_count": len(candidate_package.get("candidates", [])),
                "risk_count": len(candidate_package.get("risks", [])),
                "action_count": len(candidate_package.get("action_items", [])),
                "submit_result": submit_result,
                "review_cards_sent": bool(reviewer_id),
                "completed_at": now_iso(),
            }

            idempotency_guard.mark(idempotency_key, result)
            print("[Pipeline] ✅ 流程执行成功!")
            return result

        except Exception as e:
            print(f"[Pipeline] ❌ 流程失败: {e}")
            state_machine.set_state(
                f"manual:{source_id}",
                MeetingState.FAILED,
                extra={"error": str(e)}
            )
            raise

    def get_status(self, source_id: str) -> Optional[dict]:
        """获取流程状态"""
        return state_machine.get_state(f"minutes:{source_id}")

    def list_pipelines(self, limit: int = 20) -> list:
        """列出最近的流程"""
        return state_machine.get_all_states(limit=limit)


# 单例
pipeline_orchestrator = PipelineOrchestrator()
