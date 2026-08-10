"""应用配置 - 单一来源。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8081
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "*"

    # SQLite 默认；可在 .env 切换为 postgresql://...
    DATABASE_URL: str = "sqlite:///./data/labmemory.db"

    # 飞书编排器集成鉴权
    PLATFORM_API_KEY: str = "dev-platform-api-key-please-rotate"

    # 平台用户 JWT
    JWT_SECRET: str = "dev-jwt-secret-please-rotate"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # 飞书编排器回调地址（用于平台请求飞书侧执行 create_task 等动作）
    FEISHU_ORCHESTRATOR_BASE_URL: str = "http://localhost:8080"
    FEISHU_ORCHESTRATOR_MODE: str = "mock"

    PROJECT_ROOT: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])

    @property
    def contracts_dir(self) -> Path:
        return self.PROJECT_ROOT / "app" / "contracts"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
