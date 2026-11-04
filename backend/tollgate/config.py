from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOLLGATE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tollgate.db"

    # Vultr Serverless Inference (OpenAI-compatible)
    inference_base_url: str = "https://api.vultrinference.com/v1"
    inference_api_key: str = ""
    model_vision: str = "qwen3.8-27b"
    model_reasoning: str = "glm-5.3"
    model_safety: str = "nemotron-3.5-content-safety"
    llm_timeout_s: float = 120.0

    # Vultr Object Storage (S3-compatible). Empty endpoint -> local filesystem.
    s3_endpoint: str = ""
    s3_bucket: str = "tollgate-invoices"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    local_storage_dir: str = "./storage"

    # Gmail (SMTP send + IMAP receive) with an app password
    gmail_address: str = ""
    gmail_app_password: str = ""
    mail_poll_interval_s: int = 30
    mail_enabled: bool = False

    # Agent policy
    price_tolerance_pct: float = 2.0
    auto_pay_limit: float = 10_000.0
    controller_limit: float = 50_000.0
    vendor_followup_hours: float = 24.0
    agent_max_steps: int = 8

    # Public demo guard rails
    demo_mode: bool = True
    max_uploads_per_hour: int = 30
    cors_origins: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
