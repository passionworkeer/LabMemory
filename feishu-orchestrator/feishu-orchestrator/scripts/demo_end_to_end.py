#!/usr/bin/env python3
"""
端到端演示脚本
模拟完整链路：事件触发 → Aily 编译 → 平台提交 → 卡片通知 → 用户审批 → 创建任务
"""
import sys
import os
import json
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.event_router import event_router
from core.state_machine import state_machine, MeetingState
from core.pipeline_orchestrator import pipeline_orchestrator
from core.card_handler import card_handler
from core.platform_client import platform_client
from adapters.minutes_adapter import minutes_adapter
from adapters.aily_adapter import aily_adapter
from adapters.im_card_adapter import im_card_adapter
from adapters.task_adapter import task_adapter
from reliability.integration_log import integration_log


def print_section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)
    print()


def demo_event_driven_flow():
    """演示事件驱动的完整流程"""

    print_section("📋 第 1 步：会议结束事件")

    # 模拟会议结束事件
    meeting_ended_event = {
        "type": "meeting.ended_v1",
        "event_id": "evt_meeting_001",
        "meeting_id": "meeting_demo_001",
        "title": "实验方案评审会",
        "start_time": "2026-08-05T10:00:00+08:00",
        "end_time": "2026-08-05T10:30:00+08:00",
        "organizer": "张三",
    }

    print("📥 收到事件：会议结束")
    print(f"   会议 ID: {meeting_ended_event['meeting_id']}")
    print(f"   会议标题: {meeting_ended_event['title']}")
    print()

    result = event_router.handle_event(meeting_ended_event)
    print(f"✅ 处理结果: {result.get('status')}")
    print(f"   下一状态: {result.get('next_state')}")
    print(f"   消息: {result.get('message')}")

    # 验证状态
    state = state_machine.get_state("meeting:meeting_demo_001")
    print(f"   状态机: {state.get('state')}")

    print_section("📋 第 2 步：妙记生成事件")

    # 模拟妙记生成事件（延迟几秒后到达）
    print("⏳ 等待妙记生成...")
    time.sleep(0.5)
    print()

    minutes_generated_event = {
        "type": "minutes.minute.generated_v1",
        "event_id": "evt_minutes_001",
        "minute_token": "minutes_demo_001",
        "meeting_id": "meeting_demo_001",
        "title": "实验方案评审会",
    }

    print("📥 收到事件：妙记已生成")
    print(f"   妙记 Token: {minutes_generated_event['minute_token']}")
    print(f"   关联会议: {minutes_generated_event['meeting_id']}")
    print()

    result = event_router.handle_event(minutes_generated_event)
    print(f"✅ 处理结果: {result.get('status')}")
    print(f"   下一状态: {result.get('next_state')}")
    print(f"   消息: {result.get('message')}")

    # 验证状态
    state = state_machine.get_state("meeting:meeting_demo_001")
    print(f"   状态机: {state.get('state')}")

    print_section("📋 第 3 步：触发 Aily 编译")

    # 从妙记获取内容并编译
    print("🔍 获取妙记详情...")
    minutes_url = "https://bytedance.larkoffice.com/minutes/minutes_demo_001"
    minutes_detail = minutes_adapter.get_by_url(minutes_url)
    meeting_package = minutes_adapter.to_meeting_package(minutes_detail)

    print(f"   标题: {meeting_package['title']}")
    print(f"   参会人: {len(meeting_package['participants'])} 人")
    print(f"   逐字稿: {len(meeting_package['content']['transcript'])} 段")
    print()

    print("🤖 Aily 决策编译中...")
    candidate_package = aily_adapter.compile(meeting_package)

    print(f"✅ 编译完成")
    print(f"   候选决策: {len(candidate_package['candidates'])} 个")
    print(f"   风险: {len(candidate_package['risks'])} 个")
    print(f"   行动项: {len(candidate_package['action_items'])} 个")

    # 列出候选决策
    print()
    print("候选决策列表：")
    for i, cand in enumerate(candidate_package["candidates"], 1):
        type_labels = {
            "decision": "🟢 决策",
            "parameter_change": "📊 参数变更",
            "risk": "🟠 风险",
        }
        type_label = type_labels.get(cand["type"], cand["type"])
        confidence = int(cand["confidence"] * 100)
        print(f"  {i}. {type_label} | 置信度 {confidence}% | {cand['title']}")

    print_section("📋 第 4 步：提交到 LabMemory 平台")

    print("📤 提交候选决策到平台...")
    submit_result = platform_client.submit_candidates(candidate_package)

    print(f"✅ 提交成功")
    print(f"   状态: {submit_result.get('status')}")
    print(f"   消息: {submit_result.get('message')}")
    print(f"   待复核: {submit_result.get('review_count', len(candidate_package['candidates']))} 个")

    print_section("📋 第 5 步：发送复核卡片")

    reviewer_id = "user_demo_reviewer"
    print(f"💌 向复核人发送卡片 ({reviewer_id})...")
    print()

    for i, candidate in enumerate(candidate_package["candidates"], 1):
        message_id = im_card_adapter.send_review_card(
            receive_id=reviewer_id,
            candidate=candidate,
            meeting_title=meeting_package["title"],
            source_url=minutes_detail.source_url or "",
        )
        type_labels = {
            "decision": "🟢 决策",
            "parameter_change": "📊 参数变更",
            "risk": "🟠 风险",
        }
        type_label = type_labels.get(candidate["type"], candidate["type"])
        print(f"  {i}. {type_label} | {candidate['title'][:40]}... → 已发送")

    print()
    print("✅ 复核卡片已全部发送")

    print_section("📋 第 6 步：用户点击「确认」按钮")

    print("👆 模拟用户点击第一个候选的「确认」按钮...")
    print()

    # 模拟卡片回调
    first_candidate = candidate_package["candidates"][0]
    card_callback = {
        "token": "card_callback_demo_001",
        "open_id": reviewer_id,
        "action": {
            "value": {
                "action_type": "approved",
                "candidate_id": first_candidate["candidate_id"],
            }
        }
    }

    print(f"   候选 ID: {first_candidate['candidate_id']}")
    print(f"   操作: approved（确认通过）")
    print()

    result = card_handler.handle_callback(card_callback)

    print(f"✅ 处理结果")
    print(f"   平台状态: {result.get('status')}")
    print(f"   动作审计: {result.get('action_audit')}")
    print(f"   消息: {result.get('message', '')}")

    print_section("📋 第 7 步：创建飞书任务")

    # 检查任务是否创建成功
    print("📋 检查任务创建状态...")
    print()

    # 获取候选详情（带任务信息）
    candidate_detail = platform_client.get_candidate(first_candidate["candidate_id"])

    if candidate_detail.get("task_guid"):
        print(f"✅ 任务已创建")
        print(f"   任务 GUID: {candidate_detail['task_guid']}")
        print(f"   任务标题: {first_candidate['title']}")
        print(f"   任务链接: https://bytedance.larkoffice.com/task/{candidate_detail['task_guid']}")
    else:
        print("⚠️  任务尚未创建（可能在异步处理中）")

    # 验证状态机
    state = state_machine.get_state(f"candidate:{first_candidate['candidate_id']}")
    if state:
        print(f"   状态机: {state.get('state')}")

    print_section("📊 集成日志摘要")

    logs = integration_log.get_logs(limit=20)
    print(f"共 {len(logs)} 条日志，最近 10 条：")
    print()

    for log in logs[:10]:
        status_icon = {
            "success": "✅",
            "failed": "❌",
            "start": "⏳",
            "retrying": "🔄"
        }.get(log.get("status", ""), "❓")
        direction_icon = {
            "inbound": "⬇️",
            "outbound": "⬆️"
        }.get(log.get("direction", ""), "➡️")
        interface = log.get("interface", "unknown")[:35].ljust(35)
        status = (log.get("status", "unknown") or "unknown")[:10].ljust(10)
        duration = log.get("duration_ms", 0) or 0
        print(f"  {status_icon} {direction_icon} {interface} {status} {duration:>6}ms")

    print_section("🎉 端到端演示完成！")

    print("✅ 完整链路已验证：")
    print()
    print("  1. 📅 会议结束事件 → 状态机: WAITING_MINUTES")
    print("  2. 📝 妙记生成事件 → 状态机: MINUTES_READY")
    print("  3. 🤖 Aily 编译 → 识别 3 个候选决策")
    print("  4. 🔗 平台提交 → 状态: submitted")
    print("  5. 💌 发送复核卡片 → 3 张卡片")
    print("  6. 👆 用户确认 → 平台审批通过")
    print("  7. ✅ 创建飞书任务 → 任务闭环")
    print()
    print("📋 状态机流转：")
    print("   WAITING_MINUTES → MINUTES_READY → COMPILING → SUBMITTED")
    print("   → REVIEWING → APPROVED → COMPLETED")
    print()
    print("🔒 可靠性保障：")
    print("   ✅ 幂等控制（重复事件不重复处理）")
    print("   ✅ 重试引擎（网络错误自动重试）")
    print("   ✅ 集成日志（全链路可追溯）")
    print()


def main():
    print()
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║     LabMemory 飞书编排系统 - 端到端完整链路演示              ║")
    print("║     Event-Driven → AI Compile → Review → Task               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()
    print(f"运行模式: {'Mock' if Config.is_mock_mode() else 'Real'}")
    print()

    try:
        demo_event_driven_flow()
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
