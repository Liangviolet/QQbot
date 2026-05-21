"""Pydantic 配置模型 — 加载 config.yml + .env"""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PersonaConfig(BaseModel):
    name: str = "Bot"
    greeting_style: str = "normal"
    reply_tone: str = "friendly"


class LLMRetryConfig(BaseModel):
    max_attempts: int = 3
    min_wait: int = 1
    max_wait: int = 10


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    base_url: str = ""
    max_tokens: int = 1024
    temperature: float = 0.7
    retry: LLMRetryConfig = LLMRetryConfig()
    daily_budget_usd: float = 5.0


class QAConfig(BaseModel):
    enabled: bool = True
    knowledge_base_path: str = "data/knowledge_base.yml"
    match_threshold: int = 75


class BilibiliConfig(BaseModel):
    enabled: bool = True
    max_bv_per_message: int = 3
    video_cache_ttl: int = 3600
    summary_context_ttl: int = 300


class SummaryConfig(BaseModel):
    enabled: bool = True
    cron: str = "0 22 * * *"
    timezone: str = "Asia/Shanghai"
    silent_if_no_messages: bool = False


class ProfileConfig(BaseModel):
    enabled: bool = True
    min_messages_for_profile: int = 10
    message_retention_days: int = 90


class PluginConfig(BaseModel):
    qa: QAConfig = QAConfig()
    bilibili: BilibiliConfig = BilibiliConfig()
    summary: SummaryConfig = SummaryConfig()
    profile: ProfileConfig = ProfileConfig()


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///data/bot.db"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "logs/bot.log"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 7


class BotConfig(BaseModel):
    persona: PersonaConfig = PersonaConfig()


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot: BotConfig = BotConfig()
    llm: LLMConfig = LLMConfig()
    plugins: PluginConfig = PluginConfig()
    database: DatabaseConfig = DatabaseConfig()
    logging: LoggingConfig = LoggingConfig()
    superusers: list[int] = Field(default_factory=lambda: [])

    # 从 .env 加载的密钥
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    bot_qq_account: Optional[int] = None


def load_config() -> AppConfig:
    """加载 config.yml 后与 .env 合并"""
    config_path = Path("config.yml")
    overrides = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)
        if yaml_data:
            overrides = yaml_data
    return AppConfig(**overrides)
