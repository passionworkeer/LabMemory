#!/usr/bin/env python3
"""
健康检查脚本
检查各模块是否正常工作
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config


def check_module(name, import_path):
    """检查模块是否能正常导入"""
    try:
        __import__(import_path)
        return True, ""
    except Exception as e:
        return False, str(e)


def check_minutes_adapter():
    """检查妙记适配器"""
    try:
        from adapters.minutes_adapter import minutes_adapter
        # Mock 模式下直接测试
        if Config.is_mock_mode():
            result = minutes_adapter.search("测试")
            return True, f"Mock 模式正常，搜索结果: {len(result)} 条"
        return True, "已加载（真实模式需配置凭证）"
    except Exception as e:
        return False, str(e)


def check_aily_adapter():
    """检查 Aily 适配器"""
    try:
        from adapters.aily_adapter import aily_adapter
        return True, f"已加载，Skill 版本: {aily_adapter.SKILL_VERSION}"
    except Exception as e:
        return False, str(e)


def check_platform_client():
    """检查平台客户端"""
    try:
        from core.platform_client import platform_client
        return True, f"已加载，API Base: {Config.PLATFORM_API_BASE}"
    except Exception as e:
        return False, str(e)


def check_im_card():
    """检查交互卡片适配器"""
    try:
        from adapters.im_card_adapter import im_card_adapter
        return True, "已加载"
    except Exception as e:
        return False, str(e)


def check_task_adapter():
    """检查任务适配器"""
    try:
        from adapters.task_adapter import task_adapter
        return True, "已加载"
    except Exception as e:
        return False, str(e)


def check_state_machine():
    """检查状态机"""
    try:
        from core.state_machine import state_machine
        states = state_machine.get_all_states(limit=5)
        return True, f"正常，当前状态记录: {len(states)} 条"
    except Exception as e:
        return False, str(e)


def check_idempotency():
    """检查幂等控制"""
    try:
        from reliability.idempotency import idempotency_guard
        return True, "正常"
    except Exception as e:
        return False, str(e)


def check_integration_log():
    """检查集成日志"""
    try:
        from reliability.integration_log import integration_log
        logs = integration_log.get_logs(limit=5)
        return True, f"正常，日志条数: {len(logs)}"
    except Exception as e:
        return False, str(e)


def check_retry_engine():
    """检查重试引擎"""
    try:
        from reliability.retry_engine import default_retry_engine
        return True, f"正常，最大重试次数: {Config.MAX_RETRIES}"
    except Exception as e:
        return False, str(e)


def check_pipeline():
    """检查主编排器"""
    try:
        from core.pipeline_orchestrator import pipeline_orchestrator
        return True, "已加载"
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 60)
    print("  LabMemory 飞书编排系统 - 健康检查")
    print("=" * 60)
    print(f"运行模式: {'Mock' if Config.is_mock_mode() else 'Real'}")
    print(f"数据目录: {Config.DATA_DIR}")
    print(f"日志目录: {Config.LOG_DIR}")
    print()

    checks = [
        ("📚 配置加载", lambda: (True, f"FEISHU_APP_ID: {Config.FEISHU_APP_ID[:8]}..." if Config.FEISHU_APP_ID else "未配置")),
        ("📝 妙记适配器", check_minutes_adapter),
        ("🤖 Aily 适配器", check_aily_adapter),
        ("🔗 平台客户端", check_platform_client),
        ("💳 交互卡片", check_im_card),
        ("📋 任务适配器", check_task_adapter),
        ("⚙️  状态机", check_state_machine),
        ("🔄 幂等控制", check_idempotency),
        ("📊 集成日志", check_integration_log),
        ("🔁 重试引擎", check_retry_engine),
        ("🚀 主编排器", check_pipeline),
    ]

    passed = 0
    failed = 0

    for name, check_func in checks:
        try:
            ok, detail = check_func()
            if ok:
                print(f"✅ {name:20s} {detail}")
                passed += 1
            else:
                print(f"❌ {name:20s} {detail}")
                failed += 1
        except Exception as e:
            print(f"❌ {name:20s} 异常: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"  检查结果: {passed} 通过 / {failed} 失败 / 共 {len(checks)} 项")
    print("=" * 60)

    if failed == 0:
        print()
        print("🎉 所有检查通过！系统运行正常。")
        print()
        print("快速开始：")
        print("  python scripts/run_pipeline.py --demo")
        return 0
    else:
        print()
        print(f"⚠️  有 {failed} 项检查未通过，请检查配置。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
