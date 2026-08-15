"""应用配置 - 单一来源。"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_SECRETS = {
    "JWT_SECRET": "dev-jwt-secret-please-rotate",
    "PLATFORM_API_KEY": "dev-platform-api-key-please-rotate",
}


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
    # 默认本地开发白名单；禁 `*`+credentials 共存（main.py 兜底降级）
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8081"

    # 部署环境：production 下默认密钥将硬失败（防弱密钥上生产）；默认 development 保 dev/test 可运行
    APP_ENV: str = "development"

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

    # === Aily 集成契约（/v1/* 入站 + 出站 webhook）===
    # 出站 webhook 目标地址（Aily 侧接收端点基址）；未开启时不真调
    AILY_WEBHOOK_BASE_URL: str = "http://localhost:9000"
    AILY_WEBHOOK_SECRET: str = "dev-aily-webhook-secret-please-rotate"
    # "true" 才真实推送 webhook；否则仅记录跳过（默认关闭，避免本地误发）
    AILY_INTEGRATION_ENABLED: str = "false"
    # /v1/transcripts 缺少 experiment_id 时的回退实验
    AILY_DEFAULT_EXPERIMENT_ID: str = "EXP-DEMO-001"

    # === Aily MCP Server（同进程 SSE 暴露 10 个工具）===
    # 总开关：false 时 /mcp/sse 不挂载（与 /v1/* HTTP 契约解耦）
    MCP_ENABLED: bool = True
    # SSE 端点路径（生产建议加随机 token 防扫描，如 /mcp/sse/<random>）
    MCP_SSE_PATH: str = "/mcp/sse"
    # MCP POST 消息端点路径（SSE 客户端回传用）
    MCP_MESSAGES_PATH: str = "/mcp/messages"
    # 鉴权开关：Aily 后台只能填 name+url+desc 三字段（不支持 Header/queryParam），
    # 设为 false 时跳过 Bearer / token 校验；公网部署需配合 nginx IP rate limit
    # 与 reverse proxy 网络层防护。默认 true（开发/自检场景保留鉴权）。
    # 详见 AILY_MCP.md §2「Aily 后台三字段限制的现实」
    MCP_REQUIRE_AUTH: bool = True
    # 注：原 MCP_ALLOW_INSECURE_USER_HEADER 已被删除（C1 修复）—— MCP 是机器对机器，
    # 详细见 openspec/changes/add-aily-mcp-server 与 AILY_MCP.md §1

    # === 可信知识问答 RAG 配置 ===
    # Qwen 嵌入（DashScope API）。未配置 key 时降级到 hash 伪向量。
    QWEN_API_KEY: str = ""
    QWEN_EMBEDDING_MODEL: str = "text-embedding-v3"
    QWEN_EMBEDDING_DIM: int = 1024
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # DeepSeek 对话（兼容 OpenAI SDK）。未配置 key 或 RAG_ENABLE_LLM=false 时降级到模板。
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_CHAT_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    RAG_ENABLE_LLM: bool = True
    # 知识问答生成的 max_tokens。推理型模型（如 deepseek-v4-flash）的 reasoning_tokens 计入
    # completion_tokens，预算不足时 content 会被截断为空串（finish_reason=length），须给足。
    DEEPSEEK_MAX_TOKENS: int = 4000

    # RAG 检索参数
    RAG_TOP_K: int = 5
    RAG_MIN_SCORE: float = 0.25
    RAG_RECALL_TOP: int = 20
    RAG_BM25_WEIGHT: float = 0.35
    RAG_VECTOR_WEIGHT: float = 0.35
    RAG_RECENCY_WEIGHT: float = 0.15
    RAG_STATUS_WEIGHT: float = 0.15

    # 可信问答会话与历史
    # 传给回答 agent 的历史轮数上限（1 轮 = user+assistant 一对，10 轮 = 20 条消息）
    QA_HISTORY_TURNS: int = 10
    # 单会话详情响应返回的最大消息数（最旧不返回但仍在库）
    QA_SESSION_MAX_MESSAGES: int = 200
    # 会话列表默认分页大小
    QA_SESSION_LIST_DEFAULT_LIMIT: int = 20
    # 意图识别 agent 总开关；false 时所有问题都走 RAG（向后兼容降级）
    QA_ENABLE_LLM_INTENT: bool = True
    # 意图 agent 模型（默认沿用 DEEPSEEK_CHAT_MODEL）
    QA_INTENT_MODEL: str = ""
    # 摘要正文存库硬上限（字符数）
    QA_SUMMARY_MAX_CHARS: int = 600

    PROJECT_ROOT: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1])

    @property
    def contracts_dir(self) -> Path:
        return self.PROJECT_ROOT / "app" / "contracts"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        """默认密钥：APP_ENV=production 下硬失败；其余环境告警（保 dev/test 可运行性）。"""
        offenders = [k for k, d in _DEFAULT_SECRETS.items() if getattr(self, k) == d]
        if not offenders:
            return self
        if self.APP_ENV == "production":
            raise ValueError(
                "APP_ENV=production 下禁止使用代码默认密钥（存在伪造/越权风险），"
                f"请覆盖：{', '.join(offenders)}"
            )
        for key in offenders:
            logging.warning(
                "⚠️ %s 为代码默认值——生产部署 MUST 覆盖为强随机值，否则存在伪造/越权风险。", key,
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
