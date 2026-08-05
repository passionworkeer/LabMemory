#!/usr/bin/env python3
"""
LabMemory 飞书编排系统 - 统一演示入口
提供多种演示场景选择
"""
import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config


def print_header():
    """打印头部"""
    print()
    print("=" * 70)
    print("  LabMemory 飞书编排与 AI 接入子系统 - 演示中心")
    print("=" * 70)
    print(f"  运行模式: {'Mock 模式（演示用）' if Config.is_mock_mode() else 'Real 模式（真实调用）'}")
    print("=" * 70)


def print_menu():
    """打印演示菜单"""
    print()
    print("【演示场景】")
    print()
    print("  🎯 基础演示")
    print("    1. 基础主链路演示（妙记 → 编译 → 提交 → 卡片）")
    print("    2. 端到端完整演示（事件驱动 + 任务闭环）")
    print()
    print("  🔧 可靠性演示")
    print("    3. 异常场景演示（幂等 / 重试 / 延迟 / 阻断等 8 个场景）")
    print()
    print("  📊 功能演示")
    print("    4. 多维表格台账演示")
    print("    5. 知识发布演示")
    print("    6. Mock Server 联调演示")
    print()
    print("  🛠️  工具")
    print("    7. 健康检查")
    print("    8. 重置演示环境")
    print("    9. 管理控制台（人工兜底/重放）")
    print()
    print("  0. 退出")
    print()


def run_demo_1():
    """基础主链路演示"""
    print()
    print("=" * 70)
    print("  演示 1: 基础主链路演示")
    print("=" * 70)
    print()
    print("  演示内容:")
    print("    - 从示例妙记开始")
    print("    - Aily 编译生成候选决策")
    print("    - 提交到 LabMemory 平台")
    print("    - 发送复核卡片")
    print()
    input("  按回车开始演示...")

    os.system(f"{sys.executable} scripts/run_pipeline.py --demo")


def run_demo_2():
    """端到端完整演示"""
    print()
    print("=" * 70)
    print("  演示 2: 端到端完整演示")
    print("=" * 70)
    print()
    print("  演示内容（7 步完整流程）:")
    print("    1. 会议结束事件 → 状态机: WAITING_MINUTES")
    print("    2. 妙记生成事件 → 状态机: MINUTES_READY")
    print("    3. Aily 编译 → 识别 3 个候选决策")
    print("    4. 平台提交 → 状态: submitted")
    print("    5. 发送复核卡片 → 3 张卡片")
    print("    6. 用户点击「确认」按钮 → 平台审批")
    print("    7. 创建飞书任务 → 任务闭环")
    print()
    input("  按回车开始演示...")

    os.system(f"{sys.executable} scripts/demo_end_to_end.py")


def run_demo_3():
    """异常场景演示"""
    print()
    print("=" * 70)
    print("  演示 3: 异常场景演示")
    print("=" * 70)
    print()
    print("  演示内容（8 个场景）:")
    print("    1. 重复事件幂等处理")
    print("    2. 重复卡片回调幂等")
    print("    3. 妙记延迟场景")
    print("    4. 平台阻断场景")
    print("    5. 重试机制")
    print("    6. 集成日志可追溯")
    print("    7. 多维表格台账")
    print("    8. 知识发布")
    print()
    input("  按回车开始演示...")

    os.system(f"{sys.executable} scripts/demo_exceptional_cases.py")


def run_demo_4():
    """多维表格台账演示"""
    print()
    print("=" * 70)
    print("  演示 4: 多维表格台账演示")
    print("=" * 70)
    print()
    print("  演示内容:")
    print("    - 候选决策自动同步到多维表格")
    print("    - 支持按状态、类型筛选")
    print("    - 便于批量查看和协作")
    print()
    input("  按回车开始演示...")

    # 先跑一个基础流程生成数据
    from core.pipeline_orchestrator import pipeline_orchestrator
    from adapters.base_adapter import base_adapter

    print()
    print("  🚀 运行主链路生成候选决策...")
    result = pipeline_orchestrator.run_from_text(
        text="""
        张三：今天我们来评审一下 EXP-2026-001 的实验方案。
        李四：我建议把温度从 20 度调整到 25 度，反应时间从 30 分钟改成 45 分钟。
        王五：我同意，这样预计转化率能提升 15%。
        赵六：不过要注意温度升高可能导致副反应增加。
        张三：好，那就采用方案A。李四负责安排小试，王五负责检测监控。
        """,
        title="实验方案评审会",
        reviewer_id="user_demo",
    )

    print(f"  ✅ 生成了 {result.get('candidate_count', 0)} 个候选决策")
    print()

    # 批量添加到多维表格
    print("  📊 同步到多维表格台账...")
    candidates = result.get("candidates", [])
    record_ids = base_adapter.batch_add_records(candidates, "实验方案评审会")
    print(f"  ✅ 已添加 {len(record_ids)} 条记录")
    print()

    # 查询所有记录
    records = base_adapter.list_records()
    print(f"  📋 台账总记录数: {len(records)}")
    print()

    # 按状态统计
    status_counts = {}
    for r in records:
        s = r.get("状态", "unknown")
        status_counts[s] = status_counts.get(s, 0) + 1

    print("  状态分布:")
    for status, count in status_counts.items():
        bar = "█" * min(count * 5, 30)
        print(f"    {status:<18} {count:>2} 条  {bar}")

    print()
    print("  记录详情:")
    print(f"  {'类型':<14} {'标题':<30} {'状态':<16} {'置信度'}")
    print("  " + "-" * 68)

    for record in records:
        type_label = record.get("类型", "")[:12]
        title = record.get("标题", "")[:28]
        status = record.get("状态", "")[:14]
        conf = record.get("置信度", "-")
        print(f"  {type_label:<14} {title:<30} {status:<16} {conf}")

    print()
    print("=" * 70)
    print("  ✅ 多维表格台账演示完成！")
    print("=" * 70)
    print()
    input("  按回车返回...")


def run_demo_5():
    """知识发布演示"""
    print()
    print("=" * 70)
    print("  演示 5: 知识发布演示")
    print("=" * 70)
    print()
    print("  演示内容:")
    print("    - 通过审核的决策自动发布为知识文档")
    print("    - 3 种文档类型：成功案例 / 失败边界 / 待验证")
    print("    - 结构化内容，便于阅读和检索")
    print()
    input("  按回车开始演示...")

    from adapters.docs_adapter import docs_adapter

    print()
    print("  📄 发布成功案例...")
    result1 = docs_adapter.publish_success_case(
        candidate={
            "candidate_id": "cand_demo_success_001",
            "type": "decision",
            "title": "采用方案A调整实验参数",
            "description": "将温度从 20℃ 调整到 25℃，反应时间从 30 分钟增加到 45 分钟，预计转化率提升 15%",
            "confidence": 0.92,
            "experiment_ref": "EXP-2026-001",
            "parameters": [
                {"name": "反应温度", "old_value": "20", "new_value": "25", "unit": "℃"},
                {"name": "反应时间", "old_value": "30", "new_value": "45", "unit": "分钟"},
            ],
            "evidence": [
                {"speaker": "李四", "text": "我建议把温度从 20 度调整到 25 度"},
                {"speaker": "王五", "text": "我同意，这样预计转化率能提升 15%"},
            ],
        },
        meeting_title="实验方案评审会",
    )
    print(f"  ✅ 成功案例已发布: {result1['title']}")
    print(f"     文档链接: {result1['url']}")

    print()
    print("  ❌ 发布失败边界...")
    result2 = docs_adapter.publish_failure_case(
        candidate={
            "candidate_id": "cand_demo_failure_001",
            "type": "risk",
            "title": "温度过高导致副反应增加",
            "description": "当温度超过 30℃ 时，副反应发生率显著上升，产率下降",
            "confidence": 0.78,
            "experiment_ref": "EXP-2026-001",
        },
        meeting_title="实验方案评审会",
        reason="温度超过安全阈值，副反应风险过高",
    )
    print(f"  ✅ 失败边界已发布: {result2['title']}")
    print(f"     文档链接: {result2['url']}")

    print()
    print("  ⏳ 发布待验证...")
    result3 = docs_adapter.publish_pending_case(
        candidate={
            "candidate_id": "cand_demo_pending_001",
            "type": "conclusion",
            "title": "催化剂浓度优化方案",
            "description": "初步测试显示催化剂浓度提升 20% 可能加快反应速度，需进一步验证",
            "confidence": 0.65,
            "experiment_ref": "EXP-2026-002",
        },
        meeting_title="催化剂优化讨论会",
    )
    print(f"  ✅ 待验证已发布: {result3['title']}")
    print(f"     文档链接: {result3['url']}")

    print()
    print("  📚 已发布文档统计:")
    docs = docs_adapter.list_docs()
    type_counts = {}
    for d in docs:
        t = d.get("doc_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    for doc_type, count in type_counts.items():
        label = {"success": "✅ 成功案例", "failure": "❌ 失败边界", "pending": "⏳ 待验证"}.get(doc_type, doc_type)
        print(f"    {label}: {count} 篇")

    print()
    print("=" * 70)
    print("  ✅ 知识发布演示完成！")
    print("=" * 70)
    print()
    input("  按回车返回...")


def run_demo_6():
    """Mock Server 联调演示"""
    print()
    print("=" * 70)
    print("  演示 6: Mock Server 联调演示")
    print("=" * 70)
    print()
    print("  演示内容:")
    print("    - Mock Platform Server 功能介绍")
    print("    - 如何启动和使用")
    print("    - 可用接口列表")
    print()
    print("  📖 使用方法:")
    print()
    print("  1. 启动 Mock Server:")
    print("     python -m mock.mock_server 8081")
    print()
    print("  2. 修改环境变量:")
    print("     export PLATFORM_API_BASE=http://localhost:8081")
    print("     export PLATFORM_API_KEY=mock-key")
    print()
    print("  3. 运行飞书编排系统")
    print()
    print("  🔌 可用接口:")
    print("     GET  /health                    健康检查")
    print("     POST /api/v1/candidates         提交候选")
    print("     POST /api/v1/card/callback      卡片回调")
    print("     POST /api/v1/task/status        任务状态更新")
    print("     GET  /api/v1/candidates/{id}    获取候选详情")
    print("     GET  /api/v1/mock/state         状态摘要")
    print("     GET  /api/v1/mock/state/detail  状态详情")
    print("     POST /api/v1/mock/reset         重置状态")
    print()
    print("  💡 用途:")
    print("    - 平台侧开发时，用 Mock Server 模拟飞书侧")
    print("    - 飞书侧开发时，用 Mock Server 模拟平台侧")
    print("    - 联调测试时，两边都可以用 Mock 先跑通流程")
    print()
    print("=" * 70)
    print()
    input("  按回车返回...")


def run_demo_7():
    """健康检查"""
    os.system(f"{sys.executable} scripts/health_check.py")


def run_demo_8():
    """重置演示环境"""
    os.system(f"{sys.executable} scripts/demo_recovery.py")


def run_demo_9():
    """管理控制台"""
    os.system(f"{sys.executable} scripts/admin_cli.py")


def main():
    """主循环"""
    # 确保目录存在
    Config.ensure_dirs()

    while True:
        print_header()
        print_menu()

        choice = input("  请选择演示场景: ").strip()

        if choice == "0":
            print()
            print("  感谢使用！再见！")
            print()
            break
        elif choice == "1":
            run_demo_1()
        elif choice == "2":
            run_demo_2()
        elif choice == "3":
            run_demo_3()
        elif choice == "4":
            run_demo_4()
        elif choice == "5":
            run_demo_5()
        elif choice == "6":
            run_demo_6()
        elif choice == "7":
            run_demo_7()
        elif choice == "8":
            run_demo_8()
        elif choice == "9":
            run_demo_9()
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
