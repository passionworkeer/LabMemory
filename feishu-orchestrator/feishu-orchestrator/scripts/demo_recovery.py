#!/usr/bin/env python3
"""
演示恢复脚本
重置状态、清理日志，准备好演示环境
"""
import sys
import os
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config


def reset_state():
    """重置状态"""
    state_dir = Config.DATA_DIR / "state"
    if state_dir.exists():
        shutil.rmtree(state_dir)
        state_dir.mkdir(exist_ok=True)
        print("✅ 状态已重置")
    else:
        state_dir.mkdir(parents=True, exist_ok=True)
        print("✅ 状态目录已创建")


def reset_idempotency():
    """重置幂等记录"""
    idemp_dir = Config.DATA_DIR / "idempotency"
    if idemp_dir.exists():
        shutil.rmtree(idemp_dir)
        idemp_dir.mkdir(exist_ok=True)
        print("✅ 幂等记录已重置")
    else:
        idemp_dir.mkdir(parents=True, exist_ok=True)
        print("✅ 幂等目录已创建")


def reset_logs():
    """重置集成日志"""
    log_dir = Config.LOG_DIR / "integration_logs"
    if log_dir.exists():
        shutil.rmtree(log_dir)
        log_dir.mkdir(exist_ok=True)
        print("✅ 集成日志已重置")
    else:
        log_dir.mkdir(parents=True, exist_ok=True)
        print("✅ 日志目录已创建")


def verify_demo_data():
    """验证演示数据"""
    mock_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/mock"
    sample_file = os.path.join(mock_dir, "sample_aily_output.json")
    if os.path.exists(sample_file):
        print("✅ 演示数据已就绪")
        return True
    else:
        print("❌ 演示数据缺失")
        return False


def main():
    print("=" * 60)
    print("  LabMemory 飞书编排系统 - 演示环境重置")
    print("=" * 60)
    print()

    print("🔄 正在重置演示环境...")
    print()

    # 确保目录存在
    Config.ensure_dirs()

    # 重置各模块
    reset_state()
    reset_idempotency()
    reset_logs()
    verify_demo_data()

    print()
    print("=" * 60)
    print("  ✅ 演示环境已准备就绪")
    print("=" * 60)
    print()
    print("运行演示：")
    print("  python scripts/run_pipeline.py --demo")
    print()
    print("健康检查：")
    print("  python scripts/health_check.py")
    print()


if __name__ == "__main__":
    main()
