from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str

    # JWT
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "audio-quiz-files"
    r2_public_url: str = ""

    # First admin
    admin_email: str = "admin@company.com"
    admin_password: str = "changeme123"

    # MySQL — Панель менеджера
    manager_db_host: str = "localhost"
    manager_db_port: int = 3306
    manager_db_user: str = ""
    manager_db_password: str = ""
    manager_db_name: str = "centerper"
    manager_integration_enabled: bool = False

    @property
    def manager_db_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.manager_db_user}:"
            f"{self.manager_db_password}@{self.manager_db_host}:"
            f"{self.manager_db_port}/{self.manager_db_name}"
            f"?charset=utf8mb4"
        )


settings = Settings()
