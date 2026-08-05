#!/usr/bin/env python3
"""
LabMemory 飞书编排系统 - 管理 CLI
人工兜底 / 重放 / 调试 命令行界面
"""
import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.state_machine import state_machine, MeetingState
from core.pipeline_orchestrator import pipeline_orchestrator
from reliability.integration_log import integration_log
from reliability.idempotency import idempotency_guard
from adapters.minutes_adapter import minutes_adapter
from adapters.aily_adapter import aily_adapter
from adapters.base_adapter import base_adapter
from adapters.docs_adapter import docs_adapter


def print_header():
    """打印头部"""
    print()
    print("=" * 60)
    print("  LabMemory 飞书编排系统 - 管理控制台")
    print("=" * 60)
    print(f"  运行模式: {'Mock' if Config.is_mock_mode() else 'Real'}")
    print(f"  数据目录: {Config.DATA_DIR}")
    print("=" * 60)


def print_menu():
    """打印主菜单"""
    print()
    print("【主菜单】")
    print()
    print("  1. 查看流程列表")
    print("  2. 查看流程详情")
    print("  3. 重放指定流程")
    print("  4. 手动触发流程（妙记链接）")
    print("  5. 手动触发流程（文本输入）")
    print("  6. 查看集成日志")
    print("  7. 查看状态机状态")
    print("  8. 查看多维表格台账")
    print("  9. 查看知识文档")
    print("  10. 重置演示环境")
    print("  0. 退出")
    print()


def view_pipelines():
    """查看流程列表"""
    print()
    print("-" * 60)
    print("  流程列表")
    print("-" * 60)

    states = state_machine.get_all_states(limit=20)

    if not states:
        print("  暂无流程记录")
        return

    print(f"  共 {len(states)} 条记录（最近 20 条）:")
    print()
    print(f"  {'序号':<4} {'对象 ID':<30} {'状态':<20} {'更新时间'}")
    print("  " + "-" * 56)

    for i, state in enumerate(states, 1):
        obj_id = state.get("object_id", "unknown")[:28]
        status = state.get("state", "unknown")
        updated = state.get("updated_at", "")[:19]
        print(f"  {i:<4} {obj_id:<30} {status:<20} {updated}")

    print()
    choice = input("  输入序号查看详情（回车返回）: ").strip()

    if choice and choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(states):
            view_pipeline_detail(states[idx]["object_id"])


def view_pipeline_detail(object_id):
    """查看流程详情"""
    print()
    print("-" * 60)
    print(f"  流程详情: {object_id}")
    print("-" * 60)

    state = state_machine.get_state(object_id)

    if not state:
        print("  未找到该流程")
        return

    print(f"  状态: {state.get('state')}")
    print(f"  创建时间: {state.get('created_at', '')}")
    print(f"  更新时间: {state.get('updated_at', '')}")
    print()

    extra = state.get("extra", {})
    if extra:
        print("  附加信息:")
        for key, value in extra.items():
            if isinstance(value, (dict, list)):
                print(f"    {key}: {type(value).__name__} ({len(value)} 项)")
            else:
                value_str = str(value)[:50]
                print(f"    {key}: {value_str}")

    history = state.get("history", [])
    if history:
        print()
        print("  状态流转历史:")
        for h in history:
            print(f"    {h.get('timestamp', '')[:19]}  {h.get('from_state', '-'):<18} → {h.get('to_state', '')}")

    print()
    input("  按回车返回...")


def replay_pipeline():
    """重放指定流程"""
    print()
    print("-" * 60)
    print("  重放流程")
    print("-" * 60)

    states = state_machine.get_all_states(limit=10)

    if not states:
        print("  暂无流程可重放")
        return

    print(f"  可选流程（最近 10 条）:")
    print()
    for i, state in enumerate(states, 1):
        obj_id = state.get("object_id", "unknown")[:30]
        status = state.get("state", "unknown")
        print(f"  {i}. {obj_id} ({status})")

    print()
    choice = input("  输入序号重放（回车返回）: ").strip()

    if not choice or not choice.isdigit():
        return

    idx = int(choice) - 1
    if idx < 0 or idx >= len(states):
        print("  无效序号")
        return

    object_id = states[idx]["object_id"]
    state = state_machine.get_state(object_id)

    print()
    print(f"  正在重放流程: {object_id}")
    print(f"  当前状态: {state.get('state')}")
    print()

    # 检查是否有妙记链接
    extra = state.get("extra", {})
    source_url = extra.get("source_url")
    source_type = extra.get("source_type", "minutes")

    if source_type == "text":
        text = extra.get("text", "")
        title = extra.get("title", "重放 - " + object_id)
        reviewer_id = extra.get("reviewer_id", "user_demo")

        print("  从文本重放...")
        result = pipeline_orchestrator.run_from_text(text, title, reviewer_id)
    elif source_url:
        reviewer_id = extra.get("reviewer_id", "user_demo")

        print("  从妙记链接重放...")
        result = pipeline_orchestrator.run_from_minutes_url(source_url, reviewer_id)
    else:
        print("  无法重放：缺少来源信息")
        return

    print()
    print(f"  重放结果:")
    print(f"    状态: {result.get('status')}")
    print(f"    候选数: {result.get('candidate_count', 0)}")
    print(f"    风险数: {result.get('risk_count', 0)}")
    print(f"    行动项数: {result.get('action_count', 0)}")
    print(f"    已发送卡片: {result.get('review_cards_sent', 0)}")

    print()
    input("  按回车返回...")


def trigger_from_minutes():
    """手动触发流程（妙记链接）"""
    print()
    print("-" * 60)
    print("  手动触发流程 - 妙记链接")
    print("-" * 60)

    minutes_url = input("  请输入妙记链接: ").strip()

    if not minutes_url:
        print("  链接不能为空")
        return

    reviewer_id = input("  请输入复核人 ID (默认 user_demo): ").strip() or "user_demo"

    print()
    print("  正在处理...")

    try:
        result = pipeline_orchestrator.run_from_minutes_url(minutes_url, reviewer_id)

        print()
        print(f"  ✅ 处理完成!")
        print(f"    状态: {result.get('status')}")
        print(f"    候选数: {result.get('candidate_count', 0)}")
        print(f"    风险数: {result.get('risk_count', 0)}")
        print(f"    行动项数: {result.get('action_count', 0)}")
        print(f"    已发送卡片: {result.get('review_cards_sent', 0)}")

        candidates = result.get("candidates", [])
        if candidates:
            print()
            print("  候选决策:")
            for cand in candidates[:5]:
                cand_type = cand.get("type", "")
                title = cand.get("title", "")[:40]
                conf = cand.get("confidence", 0)
                print(f"    - [{cand_type}] {title} (置信度: {conf})")

    except Exception as e:
        print(f"  ❌ 处理失败: {e}")

    print()
    input("  按回车返回...")


def trigger_from_text():
    """手动触发流程（文本输入）"""
    print()
    print("-" * 60)
    print("  手动触发流程 - 文本输入")
    print("-" * 60)
    print("  请输入会议内容（空行结束）:")
    print()

    lines = []
    while True:
        line = input("  ")
        if not line.strip():
            break
        lines.append(line)

    if not lines:
        print("  内容不能为空")
        return

    text = "\n".join(lines)
    title = input("  请输入会议标题: ").strip() or "手动输入会议"
    reviewer_id = input("  请输入复核人 ID (默认 user_demo): ").strip() or "user_demo"

    print()
    print("  正在处理...")

    try:
        result = pipeline_orchestrator.run_from_text(text, title, reviewer_id)

        print()
        print(f"  ✅ 处理完成!")
        print(f"    状态: {result.get('status')}")
        print(f"    候选数: {result.get('candidate_count', 0)}")
        print(f"    风险数: {result.get('risk_count', 0)}")
        print(f"    行动项数: {result.get('action_count', 0)}")
        print(f"    已发送卡片: {result.get('review_cards_sent', 0)}")

        candidates = result.get("candidates", [])
        if candidates:
            print()
            print("  候选决策:")
            for cand in candidates[:5]:
                cand_type = cand.get("type", "")
                title = cand.get("title", "")[:40]
                conf = cand.get("confidence", 0)
                print(f"    - [{cand_type}] {title} (置信度: {conf})")

    except Exception as e:
        print(f"  ❌ 处理失败: {e}")

    print()
    input("  按回车返回...")


def view_integration_logs():
    """查看集成日志"""
    print()
    print("-" * 60)
    print("  集成日志")
    print("-" * 60)

    logs = integration_log.get_logs(limit=20)

    if not logs:
        print("  暂无日志记录")
        return

    print(f"  共 {len(logs)} 条（最近 20 条）:")
    print()
    print(f"  {'时间':<20} {'方向':<6} {'接口':<25} {'状态':<10} {'耗时'}")
    print("  " + "-" * 70)

    for log in logs:
        time_str = log.get("timestamp", "")[:19]
        direction = "↓入站" if log.get("direction") == "inbound" else "↑出站"
        interface = log.get("interface", "")[:23]
        status = log.get("status", "")[:8]
        duration = log.get("duration_ms", "-")
        if duration is not None:
            duration = f"{duration}ms"
        print(f"  {time_str:<20} {direction:<6} {interface:<25} {status:<10} {duration}")

    print()
    input("  按回车返回...")


def view_state_machine():
    """查看状态机状态"""
    print()
    print("-" * 60)
    print("  状态机统计")
    print("-" * 60)

    all_states = state_machine.get_all_states()

    if not all_states:
        print("  暂无状态记录")
        return

    # 统计各状态数量
    status_counts = {}
    for s in all_states:
        status = s.get("state", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    print(f"  总记录数: {len(all_states)}")
    print()
    print("  状态分布:")
    for status, count in sorted(status_counts.items()):
        bar = "█" * min(count, 30)
        print(f"    {status:<20} {count:>4}  {bar}")

    print()
    print(f"  最近 5 条记录:")
    print()
    for s in all_states[:5]:
        obj_id = s.get("object_id", "unknown")[:30]
        status = s.get("state", "")
        updated = s.get("updated_at", "")[:19]
        print(f"    {obj_id:<32} {status:<20} {updated}")

    print()
    input("  按回车返回...")


def view_base_records():
    """查看多维表格台账"""
    print()
    print("-" * 60)
    print("  多维表格台账")
    print("-" * 60)

    records = base_adapter.list_records(limit=20)

    if not records:
        print("  暂无记录")
        return

    print(f"  共 {len(records)} 条记录（最近 20 条）:")
    print()
    print(f"  {'类型':<12} {'标题':<30} {'状态':<16} {'置信度'}")
    print("  " + "-" * 65)

    for record in records:
        type_label = record.get("类型", "")[:10]
        title = record.get("标题", "")[:28]
        status = record.get("状态", "")[:14]
        conf = record.get("置信度", "-")
        print(f"  {type_label:<12} {title:<30} {status:<16} {conf}")

    # 统计
    status_counts = {}
    for r in records:
        s = r.get("状态", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    print()
    print("  状态统计:")
    for status, count in status_counts.items():
        print(f"    {status}: {count} 条")

    print()
    input("  按回车返回...")


def view_docs():
    """查看知识文档"""
    print()
    print("-" * 60)
    print("  知识文档")
    print("-" * 60)

    docs = docs_adapter.list_docs(limit=20)

    if not docs:
        print("  暂无文档")
        return

    print(f"  共 {len(docs)} 篇文档（最近 20 篇）:")
    print()
    print(f"  {'类型':<12} {'标题':<35} {'创建时间'}")
    print("  " + "-" * 65)

    for doc in docs:
        doc_type = doc.get("doc_type", "")
        type_label = {"success": "✅ 成功案例", "failure": "❌ 失败边界", "pending": "⏳ 待验证"}.get(doc_type, doc_type)
        title = doc.get("title", "")[:33]
        created = doc.get("created_at", "")[:19]
        print(f"  {type_label:<12} {title:<35} {created}")

    # 统计
    type_counts = {}
    for d in docs:
        t = d.get("doc_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    print()
    print("  类型统计:")
    for doc_type, count in type_counts.items():
        label = {"success": "成功案例", "failure": "失败边界", "pending": "待验证"}.get(doc_type, doc_type)
        print(f"    {label}: {count} 篇")

    print()
    input("  按回车返回...")


def reset_demo():
    """重置演示环境"""
    print()
    print("-" * 60)
    print("  重置演示环境")
    print("-" * 60)
    print()
    print("  这将清除:")
    print("    - 所有状态机状态")
    print("    - 所有幂等记录")
    print("    - 所有集成日志")
    print()

    confirm = input("  确认重置？(y/N): ").strip().lower()

    if confirm != "y":
        print("  已取消")
        return

    print()
    print("  正在重置...")

    # 清理状态
    state_machine.cleanup_old(days=0)

    # 清理幂等记录
    idempotency_guard.cleanup_expired()

    # 清理日志（删除今天的日志文件）
    log_dir = os.path.join(Config.DATA_DIR, "integration_logs")
    if os.path.exists(log_dir):
        for f in os.listdir(log_dir):
            if f.endswith(".jsonl"):
                os.remove(os.path.join(log_dir, f))

    # 清理多维表格 mock 数据
    if hasattr(base_adapter, '_mock_records'):
        base_adapter._mock_records.clear()

    # 清理文档 mock 数据
    if hasattr(docs_adapter, '_mock_docs'):
        docs_adapter._mock_docs.clear()

    print()
    print("  ✅ 演示环境已重置")
    print()
    input("  按回车返回...")


def main():
    """主循环"""
    # 确保目录存在
    Config.ensure_dirs()

    while True:
        print_header()
        print_menu()

        choice = input("  请选择操作: ").strip()

        if choice == "0":
            print()
            print("  再见！")
            print()
            break
        elif choice == "1":
            view_pipelines()
        elif choice == "2":
            obj_id = input("  请输入对象 ID: ").strip()
            if obj_id:
                view_pipeline_detail(obj_id)
        elif choice == "3":
            replay_pipeline()
        elif choice == "4":
            trigger_from_minutes()
        elif choice == "5":
            trigger_from_text()
        elif choice == "6":
            view_integration_logs()
        elif choice == "7":
            view_state_machine()
        elif choice == "8":
            view_base_records()
        elif choice == "9":
            view_docs()
        elif choice == "10":
            reset_demo()
        else:
            print()
            print("  无效选择，请重新输入")
            input("  按回车继续...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("  已退出")
        print()
