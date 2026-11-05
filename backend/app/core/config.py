from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/qxnzy_das"
    # 日志：默认同时写控制台和 storage/logs/<service>.log
    log_level: str = "INFO"
    log_to_file: bool = True
    log_dir: Path = Path("./storage/logs")
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    # 模型输出解析失败时是否记录原文片段，含业务数据时可在环境里关掉
    log_failed_model_output: bool = True
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    ai_base_url: str = ""
    ai_api_key: str | None = None
    ai_model: str = ""
    ai_provider: str = "deepseek"
    ai_timeout_seconds: int = 60
    ai_max_concurrency: int = 4
    ai_max_chunk_chars: int = 6000
    ai_max_tokens: int = 4096
    # 推理模型的思考 token 也计入 max_tokens，结构计划很容易被思考过程耗尽、正文为空
    ai_disable_thinking: bool = False
    ai_redact_fields: list[str] = []
    upload_dir: Path = Path("./storage/uploads")
    max_upload_size_mb: int = 20
    ingest_max_pdf_pages: int = 500
    ingest_max_cells: int = 500_000
    ingest_file_retention_days: int = 30
    ingest_llm_budget: int = 80
    ingest_auto_complete: bool = True
    ingest_template_global_scope: bool = True

    # 认证
    jwt_secret_key: str = "dev-only-secret-change-me-before-deploying-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 12 * 60

    # 初始化数据
    school_code: str = "4152014251"
    school_name: str = "黔西南民族职业技术学院"
    initial_admin_account: str = "admin"
    initial_admin_name: str = "系统管理员"
    initial_admin_password: str = "Admin@2026"


settings = Settings()


def resolved_ai() -> tuple[str, str, str, str]:
    """返回提供方、地址、密钥和模型。新变量优先，兼容已有的 DEEPSEEK_*。"""
    key = settings.ai_api_key or settings.deepseek_api_key or ""
    base = settings.ai_base_url or settings.deepseek_base_url
    model = settings.ai_model or settings.deepseek_model
    return settings.ai_provider, base.rstrip("/"), key, model
