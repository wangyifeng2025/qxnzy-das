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
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = ["http://localhost:3000"]
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    upload_dir: Path = Path("./storage/uploads")
    max_upload_size_mb: int = 20

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
