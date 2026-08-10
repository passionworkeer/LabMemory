"""
配置加载模块
"""
import os
import sys
from dotenv import load_dotenv
from pathlib import Path

# Windows 默认控制台编码(cp1252)下，中文 print 会抛 UnicodeEncodeError。
# 在进程启动早期将 stdout/stderr 统一为 utf-8，避免本地/演示运行报错。
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


# 加载 .env 文件
env_path = Path(__file__).parent.parent / "config" / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Config:
    """全局配置"""

    # 飞书应用
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_TENANT_ACCESS_TOKEN = os.getenv("FEISHU_TENANT_ACCESS_TOKEN", "")
    FEISHU_USER_ACCESS_TOKEN = os.getenv("FEISHU_USER_ACCESS_TOKEN", "")

    # Aily
    AILY_API_BASE = os.getenv("AILY_API_BASE", "https://aily.feishu.cn/api")
    AILY_SKILL_ID = os.getenv("AILY_SKILL_ID", "")
    AILY_API_KEY = os.getenv("AILY_API_KEY", "")

    # LabMemory 平台
    PLATFORM_API_BASE = os.getenv("PLATFORM_API_BASE", "https://labmemory.example.com/api")
    PLATFORM_API_KEY = os.getenv("PLATFORM_API_KEY", "")

    # 多维表格
    BASE_APP_TOKEN = os.getenv("BASE_APP_TOKEN", "")
    BASE_TABLE_ID = os.getenv("BASE_TABLE_ID", "")

    # 卡片回调
    CARD_CALLBACK_VERIFICATION_TOKEN = os.getenv("CARD_CALLBACK_VERIFICATION_TOKEN", "")
    CARD_CALLBACK_ENCRYPT_KEY = os.getenv("CARD_CALLBACK_ENCRYPT_KEY", "")

    # 服务
    SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # 运行模式
    RUN_MODE = os.getenv("RUN_MODE", "mock")  # real / mock

    # 重试
    MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
    RETRY_BASE_DELAY = int(os.getenv("RETRY_BASE_DELAY", "1"))

    # 数据目录
    DATA_DIR = Path(__file__).parent.parent / "data"
    LOG_DIR = Path(__file__).parent.parent / "logs"

    @classmethod
    def is_mock_mode(cls) -> bool:
        return cls.RUN_MODE == "mock"

    @classmethod
    def ensure_dirs(cls):
        """确保必要目录存在"""
        cls.DATA_DIR.mkdir(exist_ok=True)
        cls.LOG_DIR.mkdir(exist_ok=True)
        (cls.DATA_DIR / "integration_logs").mkdir(exist_ok=True)
        (cls.DATA_DIR / "idempotency").mkdir(exist_ok=True)
        (cls.DATA_DIR / "state").mkdir(exist_ok=True)


# 初始化
Config.ensure_dirs()
