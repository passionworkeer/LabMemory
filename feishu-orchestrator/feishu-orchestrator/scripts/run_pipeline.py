#!/usr/bin/env python3
"""
一键跑通主链路脚本
用法：
  python scripts/run_pipeline.py --minutes-url <url>
  python scripts/run_pipeline.py --text "会议内容..." --title "会议标题"
  python scripts/run_pipeline.py --demo  # 使用内置示例数据
"""
import sys
import os
import argparse

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.pipeline_orchestrator import pipeline_orchestrator
from core.config import Config


def main():
    parser = argparse.ArgumentParser(description="LabMemory 飞书编排 - 一键跑通")
    parser.add_argument("--minutes-url", type=str, help="妙记链接")
    parser.add_argument("--text", type=str, help="会议文本（手动输入）")
    parser.add_argument("--title", type=str, default="手动输入会议", help="会议标题")
    parser.add_argument("--reviewer-id", type=str, default="", help="复核人 ID")
    parser.add_argument("--demo", action="store_true", help="使用内置示例数据演示")
    parser.add_argument("--mode", type=str, default="", choices=["mock", "real"], help="运行模式")

    args = parser.parse_args()

    # 设置运行模式
    if args.mode:
        os.environ["RUN_MODE"] = args.mode

    print("=" * 60)
    print("  LabMemory 飞书编排系统 - 主链路演示")
    print("=" * 60)
    print(f"运行模式: {'Mock' if Config.is_mock_mode() else 'Real'}")
    print()

    try:
        if args.demo or (not args.minutes_url and not args.text):
            # 演示模式：使用内置示例
            print("📋 使用内置示例数据演示...")
            print()
            demo_text = """
今天我们开个实验方案评审会，主要讨论 EXP-2026-001 这个实验的调整方案。

张三：我建议采用方案A，温度调到25度，时间延长到45分钟，这样转化率应该能提升15%左右。
李四：同意方案A，这个调整幅度比较稳妥，风险可控。
王五：我有点担心温度升高后副反应会不会增加，这个需要验证一下。
张三：这个顾虑有道理，那我们先安排小试看看效果吧。
李四：好的，我来负责安排小试，这周就能出结果。
王五：那我负责检测监控，重点关注产物纯度的变化。
赵六：我来跟进成本核算，评估一下调整后的成本变化。
张三：好，那就这么定了，采用方案A，大家分头行动。
            """
            result = pipeline_orchestrator.run_from_text(
                text=demo_text.strip(),
                title="实验方案评审会 - 演示",
                reviewer_id=args.reviewer_id,
            )

        elif args.minutes_url:
            print(f"📋 处理妙记: {args.minutes_url}")
            print()
            result = pipeline_orchestrator.run_from_minutes_url(
                minutes_url=args.minutes_url,
                reviewer_id=args.reviewer_id,
            )

        elif args.text:
            print(f"📋 处理文本: {args.title}")
            print()
            result = pipeline_orchestrator.run_from_text(
                text=args.text,
                title=args.title,
                reviewer_id=args.reviewer_id,
            )

        # 输出结果
        print()
        print("=" * 60)
        print("  ✅ 执行结果")
        print("=" * 60)
        print(f"状态: {result.get('status')}")
        print(f"会议标题: {result.get('meeting_title')}")
        print(f"候选决策数: {result.get('candidate_count')}")
        print(f"风险数: {result.get('risk_count')}")
        print(f"行动项数: {result.get('action_count')}")
        print(f"已发送复核卡片: {'是' if result.get('review_cards_sent') else '否'}")
        print(f"完成时间: {result.get('completed_at')}")
        print()

        submit_result = result.get('submit_result', {})
        print(f"平台提交状态: {submit_result.get('status')}")
        print(f"平台消息: {submit_result.get('message')}")
        print()

        print("=" * 60)
        print("  📊 候选决策列表")
        print("=" * 60)

        # 重新获取候选列表（从编译结果）
        from adapters.aily_adapter import aily_adapter
        from adapters.minutes_adapter import minutes_adapter

        if args.demo or args.text:
            # 演示模式，重新编译一次获取详情
            meeting_package = {
                "schema_version": "1.0.0",
                "source": "manual_upload",
                "source_object_id": "demo",
                "title": result.get("meeting_title", ""),
                "content": {
                    "transcript": [{"speaker": "未知", "start_offset_sec": 0, "end_offset_sec": 100, "text": args.text or demo_text}],
                    "chapters": [],
                    "summary": "",
                    "action_items": [],
                },
                "source_url": "",
                "captured_at": "",
                "metadata": {},
            }
            candidate_package = aily_adapter.compile(meeting_package)

            for i, cand in enumerate(candidate_package.get("candidates", []), 1):
                type_labels = {
                    "decision": "🟢 决策",
                    "conclusion": "🔵 结论",
                    "risk": "🟠 风险",
                    "action_item": "🟡 行动项",
                    "question": "❓ 疑问",
                    "parameter_change": "📊 参数变更",
                }
                type_label = type_labels.get(cand.get("type"), cand.get("type"))
                confidence = int(cand.get("confidence", 0) * 100)

                print(f"\n{i}. {type_label} | 置信度: {confidence}%")
                print(f"   标题: {cand.get('title')}")
                print(f"   描述: {cand.get('description', '')[:80]}...")

                params = cand.get("parameters", [])
                if params:
                    print(f"   参数:")
                    for p in params:
                        print(f"     - {p.get('name')}: {p.get('value')} {p.get('unit', '')}")

        print()
        print("=" * 60)
        print("  📝 集成日志（最近 5 条）")
        print("=" * 60)

        from reliability.integration_log import integration_log
        logs = integration_log.get_logs(limit=5)
        for log in logs[:5]:
            status_icon = {"success": "✅", "failed": "❌", "start": "⏳", "retrying": "🔄"}.get(log.get("status", ""), "❓")
            direction_icon = {"inbound": "⬇️", "outbound": "⬆️"}.get(log.get("direction", ""), "➡️")
            interface = log.get("interface", "unknown")[:30].ljust(30)
            status = (log.get("status", "unknown") or "unknown")[:10].ljust(10)
            duration = log.get("duration_ms", 0) or 0
            print(f"  {status_icon} {direction_icon} {interface} {status} {duration:>6}ms")

        print()
        print("🎉 演示完成！")
        print()
        print("下一步可以：")
        print("  1. 配置真实凭证，切换到 real 模式")
        print("  2. 运行 health_check.py 检查各模块健康状态")
        print("  3. 查看 data/ 目录下的日志和状态文件")

    except Exception as e:
        print(f"\n❌ 执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
