from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOLLGATE_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tollgate.db"

    # Vultr Serverless Inference (OpenAI-compatible)
    inference_base_url: str = "https://api.vultrinference.com/v1"
    inference_api_key: str = ""
    model_vision: str = "qwen3.8-27b"
    # Transcription does not benefit from a reasoning trace; turning it off cuts
    # extraction from ~3.5s to ~1.6s per page with the same fields.
    vision_thinking: bool = False
    model_reasoning: str = "deepseek-v4.1-flash-1017"
    # The policy guard, not the model's chain of thought, is what keeps actions
    # safe; without thinking a plan takes ~2s instead of 10-40s and never
    # exhausts its token budget before answering.
    reasoning_thinking: bool = False
    # A different model from the planner, so the second opinion is independent.
    model_critic: str = "glm-5.3-flash"
    model_safety: str = "nemotron-3.5-content-safety"
    llm_timeout_s: float = 120.0
    # Hard ceiling on inference spend (USD, all time). Above it the agent stops
    # calling models and uses the text-layer reader and rule-based planner.
    inference_budget_usd: float = 25.0

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
    # Everything Tollgate sends or reads uses plus-addresses with this tag, so a
    # personal Gmail can host the demo: the agent only ever reads mail sent to
    # <user>+<tag>@..., never the rest of the inbox.
    mail_tag: str = "tollgate"

    # Agent policy
    price_tolerance_pct: float = 2.0
    auto_pay_limit: float = 10_000.0
    controller_limit: float = 50_000.0
    vendor_followup_hours: float = 24.0
    agent_max_steps: int = 8

    # Treasury, for payment runs
    cash_balance_usd: float = 63_500.0
    cash_floor_usd: float = 60_000.0
    run_horizon_days: int = 7

    # Public demo guard rails
    demo_mode: bool = True
    # Rate limits count documents sent into the pipeline (the demo inbox is ten).
    intake_per_ip_per_hour: int = 40
    intake_global_per_hour: int = 300
    resets_per_ip_per_hour: int = 12
    # Arbitrary uploads stop this close to the inference cap, so the guided demo
    # keeps real model output for the last few dollars.
    public_reserve_usd: float = 3.0
    # Ardent Partners, AP Metrics That Matter 2025: best-in-class cost per invoice.
    benchmark_cost_per_invoice_usd: float = 2.78
    cors_origins: str = "http://localhost:3000"


    @field_validator("gmail_app_password")
    @classmethod
    def _no_spaces(cls, v: str) -> str:
        return v.replace(" ", "")  # Google shows app passwords in groups of four

    def alias(self, suffix: str = "") -> str:
        """<user>+<tag>[-suffix]@domain for the configured mailbox."""
        if not self.gmail_address or "@" not in self.gmail_address:
            return ""
        user, domain = self.gmail_address.split("@", 1)
        return f"{user.split('+')[0]}+{self.mail_tag}{('-' + suffix) if suffix else ''}@{domain}"

    @property
    def ap_address(self) -> str:
        return self.alias() or "ap@halden.example.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
