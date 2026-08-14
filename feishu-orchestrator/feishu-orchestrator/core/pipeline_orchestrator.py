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


def _normalize_meeting_package(meeting_package: dict) -> dict:
    """归一化 MeetingPackage：meeting_id 与 source_object_id 统一、metadata 含 experiment_id。

    平台按 CandidatePackage.source_package_id == MeetingPackage.meeting_id 反查会议，
    而 aily_adapter 以 source_object_id 作为 source_package_id，故三者必须一致。
    """
    if not meeting_package.get("meeting_id"):
        meeting_package["meeting_id"] = meeting_package.get("source_object_id", "")
    meeting_package.setdefault("metadata", {})
    meeting_package["metadata"].setdefault("experiment_id", Config.EXPERIMENT_ID)
    return meeting_package


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

        source_id = None
        idempotency_key = None

        try:
            # Step 1: 获取妙记详情
            print("[Pipeline] Step 1: 获取妙记详情...")
            minutes_detail = minutes_adapter.get_by_url(minutes_url)
            meeting_package = _normalize_meeting_package(minutes_adapter.to_meeting_package(minutes_detail))

            source_id = meeting_package["source_object_id"]
            meeting_title = meeting_package["title"]

            # 幂等检查（已处理过的直接返回缓存结果）
            idempotency_key = f"pipeline:{source_id}"
            cached = idempotency_guard.check(idempotency_key)
            if cached:
                print("[Pipeline] 检测到重复处理，直接返回缓存结果")
                return cached

            # 原子抢占处理权：并发/重试到达时只执行一次，其余跳过
            if not idempotency_guard.acquire(idempotency_key):
                print("[Pipeline] 检测到并发/重复处理，跳过")
                return {"status": "duplicate", "source_id": source_id, "message": "重复或正在处理的妙记，已跳过"}

            # 更新状态
            state_machine.set_state(
                f"minutes:{source_id}",
                MeetingState.MINUTES_READY,
                extra={"meeting_title": meeting_title}
            )

            # Step 2: Aily 编译
            print("[Pipeline] Step 2: Aily 决策编译...")
            # 先注册会议到平台（供 candidate 反查；失败则整条链路提前失败，不静默继续）
            platform_client.submit_meeting(meeting_package)
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
                "status": "submitted",
                "source_id": source_id,
                "meeting_title": meeting_title,
                "candidate_count": len(candidate_package.get("candidates", [])),
                "risk_count": len(candidate_package.get("risks", [])),
                "action_count": len(candidate_package.get("action_items", [])),
                "submit_result": submit_result,
                "review_cards_sent": bool(reviewer_id),
                "submitted_at": now_iso(),
            }

            # 标记幂等（此后不再释放占位，防止误删已标记结果）
            idempotency_guard.mark(idempotency_key, result)
            idempotency_key = None

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
            # 失败释放幂等占位，允许后续重试（尚未抢占时无副作用）
            if idempotency_key:
                idempotency_guard.release(idempotency_key)
            # 失败告警（PRD §13：异常可降级可见；best-effort，不阻断抛出）
            if reviewer_id:
                try:
                    im_card_adapter.send_alert_card(
                        receive_id=reviewer_id, title="妙记流水线失败",
                        error=str(e), retry_action={"source": minutes_url},
                    )
                except Exception:
                    pass

            # 更新状态（优先用真实 source_id；妙记解析失败时才回退到 URL）
            state_key_source = source_id or minutes_url
            state_machine.set_state(
                f"minutes:{state_key_source}",
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
        meeting_package = _normalize_meeting_package(meeting_package)

        source_id = meeting_package["source_object_id"]

        # 幂等检查（已处理过的直接返回缓存结果）
        idempotency_key = f"pipeline:{source_id}"
        cached = idempotency_guard.check(idempotency_key)
        if cached:
            return cached

        # 原子抢占处理权：并发/重试到达时只执行一次，其余跳过
        if not idempotency_guard.acquire(idempotency_key):
            print("[Pipeline] 检测到并发/重复处理，跳过")
            return {"status": "duplicate", "source_id": source_id, "message": "重复或正在处理的文本，已跳过"}

        try:
            # 注册会议到平台（供 candidate 反查）
            platform_client.submit_meeting(meeting_package)

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
                "status": "submitted",
                "source_id": source_id,
                "meeting_title": title,
                "candidate_count": len(candidate_package.get("candidates", [])),
                "risk_count": len(candidate_package.get("risks", [])),
                "action_count": len(candidate_package.get("action_items", [])),
                "submit_result": submit_result,
                "review_cards_sent": bool(reviewer_id),
                "submitted_at": now_iso(),
            }

            # 标记幂等（此后不再释放占位，防止误删已标记结果）
            idempotency_guard.mark(idempotency_key, result)
            idempotency_key = None
            print("[Pipeline] ✅ 流程执行成功!")
            return result

        except Exception as e:
            print(f"[Pipeline] ❌ 流程失败: {e}")
            # 失败释放幂等占位，允许后续重试
            if idempotency_key:
                idempotency_guard.release(idempotency_key)
            if reviewer_id:
                try:
                    im_card_adapter.send_alert_card(
                        receive_id=reviewer_id, title="文本流水线失败",
                        error=str(e), retry_action={"source": source_id},
                    )
                except Exception:
                    pass
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
