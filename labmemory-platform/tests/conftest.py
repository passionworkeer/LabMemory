"""pytest 配置：在 app 模块导入前设置测试环境变量。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 测试专用环境变量（必须在 app.* 任何 import 之前设置）
# APP_ENV 钉在 development：测试套件注入的是 dev 默认密钥，若放行 .env 的
# APP_ENV=production 会触发 Settings 默认密钥硬校验导致整个套件崩掉
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("PLATFORM_API_KEY", "dev-platform-api-key-please-rotate")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-please-rotate-32chars-min")
os.environ.setdefault("FEISHU_ORCHESTRATOR_MODE", "mock")
os.environ.setdefault("FEISHU_OAUTH_MODE", "mock")  # 测试锁定 mock，避免受本地 .env real 影响
os.environ.setdefault("LOG_LEVEL", "WARNING")

# 让 tests/ 能 import app 与 scripts
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
