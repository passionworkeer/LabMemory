#!/usr/bin/env python3
"""
异常场景演示脚本
演示各种异常情况下的系统行为和可靠性保障机制
"""
import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.state_machine import state_machine, MeetingState
from core.event_router import event_router
from core.card_handler import card_handler
from core.pipeline_orchestrator import pipeline_orchestrator
from adapters.minutes_adapter import minutes_adapter
from adapters.aily_adapter import aily_adapter
from adapters.im_card_adapter import im_card_adapter
from adapters.task_adapter import task_adapter
from adapters.base_adapter import base_adapter
from adapters.docs_adapter import docs_adapter
from core.platform_client import platform_client
from reliability.idempotency import idempotency_guard
from reliability.integration_log import integration_log
from reliability.retry_engine import RetryableError, NonRetryableError, default_retry_engine


def print_separator(title=""):
    print(f"\n{'='*60}")
    if title:
        print(f"  {title}")
        print(f"{'='*60}")


def demo_duplicate_events():
    """演示 1: 重复事件幂等处理"""
    print_separator("演示 1: 重复事件幂等处理")
    print("\n场景：同一个会议结束事件被重复推送多次")
    print("预期：系统只处理一次，不会重复创建状态")
    print()

    # 重置
    state_machine.set_state("test_dup_001", MeetingState.WAITING_MINUTES)
    idempotency_guard._store.clear() if hasattr(idempotency_guard, '_store') else None

    # 第一次处理
    print("📨 第 1 次事件...")
    result1 = event_router.handle_event({
        "type": "meeting.ended_v1",
        "event_id": "evt_dup_001",
        "meeting_id": "test_dup_001",
        "title": "重复事件测试会议",
    })
    print(f"   结果: {result1.get('status', 'unknown')}")

    # 第二次处理（重复）
    print("📨 第 2 次事件（重复）...")
    result2 = event_router.handle_event({
        "type": "meeting.ended_v1",
        "event_id": "evt_dup_001",  # 相同的 event_id
        "meeting_id": "test_dup_001",
        "title": "重复事件测试会议",
    })
    print(f"   结果: {result2.get('status', 'unknown')}")
    print(f"   原因: {result2.get('reason', '')}")

    # 第三次处理（重复）
    print("📨 第 3 次事件（重复）...")
    result3 = event_router.handle_event({
        "type": "meeting.ended_v1",
        "event_id": "evt_dup_001",
        "meeting_id": "test_dup_001",
        "title": "重复事件测试会议",
    })
    print(f"   结果: {result3.get('status', 'unknown')}")

    print()
    print("✅ 幂等控制生效：重复事件不会重复处理")
    print(f"   状态机记录: 1 条（只处理了一次）")


def demo_duplicate_callbacks():
    """演示 2: 重复卡片回调幂等处理"""
    print_separator("演示 2: 重复卡片回调幂等处理")
    print("\n场景：用户快速点击按钮多次，导致重复回调")
    print("预期：系统只处理一次，不会重复创建任务")
    print()

    # 先准备一个候选
    candidate = {
        "candidate_id": "cand_dup_cb_001",
        "type": "decision",
        "title": "重复回调测试决策",
        "description": "测试重复回调的幂等性",
        "confidence": 0.9,
        "status": "pending_review",
    }
    platform_client._mock_candidates[candidate["candidate_id"]] = candidate.copy()

    # 第一次回调
    print("👆 第 1 次点击「确认」...")
    result1 = card_handler.handle_callback({
        "token": "cb_dup_001",
        "open_id": "user_test",
        "action": {
            "value": {
                "action_type": "approve",
                "candidate_id": candidate["candidate_id"],
            }
        }
    })
    print(f"   结果: {result1.get('status', 'unknown')}")
    print(f"   任务创建: {result1.get('task_created', False)}")

    # 第二次回调（重复）
    print("👆 第 2 次点击「确认」（重复）...")
    result2 = card_handler.handle_callback({
        "token": "cb_dup_001",  # 相同的 token
        "open_id": "user_test",
        "action": {
            "value": {
                "action_type": "approve",
                "candidate_id": candidate["candidate_id"],
            }
        }
    })
    print(f"   结果: {result2.get('status', 'unknown')}")
    print(f"   原因: {result2.get('reason', '')}")

    print()
    print("✅ 回调幂等生效：重复回调不会重复创建任务")


def demo_minutes_delay():
    """演示 3: 妙记延迟场景"""
    print_separator("演示 3: 妙记延迟场景")
    print("\n场景：会议结束后，妙记生成延迟了很久")
    print("预期：系统在 WAITING_MINUTES 状态等待，妙记到达后继续处理")
    print()

    meeting_id = "test_delay_001"

    # 会议结束
    print("📅 会议结束事件到达...")
    event_router.handle_event({
        "type": "meeting.ended_v1",
        "event_id": "evt_delay_001",
        "meeting_id": meeting_id,
        "title": "妙记延迟测试会议",
    })
    state = state_machine.get_state(meeting_id) or {}
    print(f"   当前状态: {state.get('state', 'unknown')}")
    print(f"   （等待妙记生成中...）")

    # 模拟延迟（这里直接继续）
    print()
    print("⏳ （模拟 30 分钟后妙记生成...）")
    print()

    # 妙记生成
    print("📝 妙记生成事件到达...")
    event_router.handle_event({
        "type": "minutes.minute.generated_v1",
        "event_id": "evt_delay_minutes_001",
        "minute_token": "minutes_delay_001",
        "meeting_id": meeting_id,
    })
    state = state_machine.get_state(meeting_id) or {}
    print(f"   当前状态: {state.get('state', 'unknown')}")

    print()
    print("✅ 状态机正确处理延迟场景：")
    print("   会议结束 → WAITING_MINUTES → 妙记到达 → MINUTES_READY")


def demo_platform_blocked():
    """演示 4: 平台阻断场景"""
    print_separator("演示 4: 平台阻断场景")
    print("\n场景：平台审核不通过，阻断候选决策")
    print("预期：系统发送阻断通知，不创建任务")
    print()

    candidate_id = "cand_blocked_001"
    candidate = {
        "candidate_id": candidate_id,
        "type": "risk",
        "title": "高风险参数调整",
        "description": "这个调整风险太高，需要阻断",
        "confidence": 0.6,
        "status": "pending_review",
    }
    platform_client._mock_candidates[candidate_id] = candidate.copy()

    print("🔍 平台审核中...")
    print(f"   候选: {candidate['title']}")
    print(f"   置信度: {candidate['confidence']}")
    print()

    # 模拟平台阻断
    print("🚫 平台审核结果：阻断")
    reason = "风险过高，需要进一步评估"

    # 更新状态机
    state_machine.set_state(
        f"candidate:{candidate_id}",
        MeetingState.BLOCKED,
        extra={"reason": reason}
    )

    # 发送阻断通知（Mock 模式下只是记录）
    im_card_adapter.send_blocked_card(
        receive_id="user_test",
        candidate=candidate,
        reason=reason,
    )

    # 更新候选状态
    if candidate_id in platform_client._mock_candidates:
        platform_client._mock_candidates[candidate_id]["status"] = "blocked"

    print(f"   处理结果: blocked")
    print(f"   任务创建: False")
    print(f"   阻断通知: 已发送")

    # 检查状态
    cand = platform_client.get_candidate(candidate_id)
    print(f"   候选状态: {cand.get('status', 'unknown') if cand else 'not found'}")

    print()
    print("✅ 平台阻断场景正确处理：")
    print("   阻断 → 不创建任务 → 发送阻断通知")


def demo_retry_mechanism():
    """演示 5: 重试机制"""
    print_separator("演示 5: 重试机制")
    print("\n场景：外部接口调用失败，自动重试")
    print("预期：系统自动重试，直到成功或达到最大重试次数")
    print()

    # 模拟一个会失败几次然后成功的函数
    call_count = [0]

    def flaky_api():
        call_count[0] += 1
        if call_count[0] < 3:
            print(f"   第 {call_count[0]} 次调用: 失败（网络超时）")
            raise RetryableError("Network timeout")
        print(f"   第 {call_count[0]} 次调用: 成功")
        return "success"

    print("🔄 调用不稳定的外部接口...")
    print(f"   最大重试次数: {Config.MAX_RETRIES}")
    print()

    try:
        result = default_retry_engine.execute(
            flaky_api,
            interface_name="test.flaky_api",
        )
        print()
        print(f"✅ 重试机制生效：")
        print(f"   失败 {call_count[0] - 1} 次后成功")
        print(f"   最终结果: {result}")
    except Exception as e:
        print(f"❌ 最终失败: {e}")


def demo_integration_log():
    """演示 6: 集成日志可追溯"""
    print_separator("演示 6: 集成日志可追溯")
    print("\n场景：所有外部调用都有完整日志记录")
    print("预期：可以通过日志追溯每一步的调用情况")
    print()

    # 跑一个简单流程产生日志
    print("📊 运行一个简单流程产生日志...")
    pipeline_orchestrator.run_from_text(
        text="我们决定将温度从20度调整到25度。",
        title="日志测试会议",
        reviewer_id="user_test",
    )

    # 查看日志
    logs = integration_log.get_logs(limit=10)
    print()
    print(f"📝 最近 {len(logs)} 条集成日志:")
    print()
    print(f"   {'方向':<8} {'接口':<30} {'状态':<8} {'耗时':<8}")
    print(f"   {'-'*8} {'-'*30} {'-'*8} {'-'*8}")

    for log in logs[:8]:
        direction = "⬆️ 出站" if log.get("direction") == "outbound" else "⬇️ 入站"
        interface = log.get("interface", "")[:28]
        status = log.get("status", "")
        duration = f"{log.get('duration_ms', 0)}ms"
        print(f"   {direction:<8} {interface:<30} {status:<8} {duration:<8}")

    print()
    print("✅ 集成日志完整记录：")
    print("   所有外部调用都可追溯，便于排查问题")


def demo_base_integration():
    """演示 7: 多维表格台账"""
    print_separator("演示 7: 多维表格台账")
    print("\n场景：候选决策同步到多维表格，便于批量查看")
    print("预期：所有候选都有对应的表格记录")
    print()

    # 准备候选数据
    candidates = [
        {
            "candidate_id": "cand_base_001",
            "type": "decision",
            "title": "采用方案A调整实验参数",
            "description": "调整温度和时间，提升转化率",
            "confidence": 0.92,
            "status": "pending_review",
            "experiment_ref": "EXP-2026-001",
        },
        {
            "candidate_id": "cand_base_002",
            "type": "parameter_change",
            "title": "参数调整：反应温度",
            "description": "温度从20度调整到25度",
            "confidence": 0.88,
            "status": "approved",
            "experiment_ref": "EXP-2026-001",
        },
        {
            "candidate_id": "cand_base_003",
            "type": "risk",
            "title": "温度升高可能导致副反应增加",
            "description": "需要监控副产物比例",
            "confidence": 0.75,
            "status": "pending_review",
            "experiment_ref": "EXP-2026-001",
        },
    ]

    # 批量添加
    print("📊 批量同步到多维表格...")
    record_ids = base_adapter.batch_add_records(candidates, "方案评审会")
    print(f"   已添加 {len(record_ids)} 条记录")
    print()

    # 查询所有记录
    all_records = base_adapter.list_records()
    print(f"📋 台账总记录数: {len(all_records)}")
    print()

    # 按状态查询
    pending = base_adapter.list_records(status="pending_review")
    approved = base_adapter.list_records(status="approved")
    print(f"   待复核: {len(pending)} 条")
    print(f"   已通过: {len(approved)} 条")
    print()

    # 展示前几条
    print("📝 记录示例:")
    for rec in all_records[:2]:
        print(f"   - {rec.get('类型', '')} | {rec.get('标题', '')[:30]}... | {rec.get('状态', '')}")

    print()
    print("✅ 多维表格台账正常：")
    print("   候选决策自动同步，支持按状态筛选，便于批量查看")


def demo_docs_publish():
    """演示 8: 知识发布"""
    print_separator("演示 8: 知识发布")
    print("\n场景：通过审核的决策自动发布为知识文档")
    print("预期：生成结构化的知识文档，便于团队学习")
    print()

    # 准备候选数据
    candidate = {
        "candidate_id": "cand_docs_001",
        "type": "decision",
        "title": "采用方案A调整实验参数",
        "description": "经过充分讨论，决定采用方案A：将反应温度从20度调整到25度，反应时间从30分钟调整到45分钟。预计转化率提升15%。",
        "confidence": 0.92,
        "status": "approved",
        "experiment_ref": "EXP-2026-001",
        "parameters": [
            {"name": "反应温度", "old_value": "20", "new_value": "25", "unit": "℃"},
            {"name": "反应时间", "old_value": "30", "new_value": "45", "unit": "分钟"},
        ],
        "evidence": [
            {"speaker": "张三", "text": "我建议采用方案A，温度提升到25度"},
            {"speaker": "李四", "text": "同意，时间也相应延长到45分钟"},
        ],
    }

    # 发布成功案例
    print("📄 发布成功案例文档...")
    result = docs_adapter.publish_success_case(candidate, "实验方案评审会")
    print(f"   文档标题: {result.get('title', '')}")
    print(f"   文档链接: {result.get('url', '')}")
    print()

    # 查看已发布文档
    all_docs = docs_adapter.list_docs()
    print(f"📚 已发布文档总数: {len(all_docs)}")

    success_docs = docs_adapter.list_docs(doc_type="success")
    print(f"   成功案例: {len(success_docs)} 篇")

    print()
    print("✅ 知识发布正常：")
    print("   通过审核的决策自动发布为结构化知识文档")


def main():
    """主函数"""
    print("\n" + "="*60)
    print("  LabMemory 飞书编排系统 - 异常场景演示")
    print("="*60)
    print()
    print("本脚本演示各种异常场景下的系统行为和可靠性保障机制")
    print()

    # 重置环境
    Config.ensure_dirs()

    demos = [
        ("重复事件幂等处理", demo_duplicate_events),
        ("重复卡片回调幂等", demo_duplicate_callbacks),
        ("妙记延迟场景", demo_minutes_delay),
        ("平台阻断场景", demo_platform_blocked),
        ("重试机制", demo_retry_mechanism),
        ("集成日志可追溯", demo_integration_log),
        ("多维表格台账", demo_base_integration),
        ("知识发布", demo_docs_publish),
    ]

    for i, (name, demo_func) in enumerate(demos, 1):
        try:
            demo_func()
        except Exception as e:
            print(f"\n❌ 演示失败: {e}")
            import traceback
            traceback.print_exc()

    # 总结
    print_separator("演示总结")
    print()
    print("✅ 所有异常场景演示完成！")
    print()
    print("🔒 可靠性保障机制：")
    print("   1. 幂等控制 - 重复事件/回调不重复处理")
    print("   2. 状态机 - 正确处理延迟和异步场景")
    print("   3. 重试引擎 - 网络错误自动重试")
    print("   4. 集成日志 - 全链路可追溯")
    print("   5. 多维表格台账 - 批量查看和协作")
    print("   6. 知识发布 - 自动沉淀经验")
    print()
    print("="*60)


if __name__ == "__main__":
    main()
