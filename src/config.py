"""
Centralized configuration.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Razorpay ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # --- OpenAI LLM Backend ---
    openai_api_key: Optional[str] = None
    llm_model: str = "gpt-4o"

    # --- Twilio (SMS Only) ---
    twilio_account_sid: Optional[str] = None
    twilio_auth_token: Optional[str] = None
    twilio_sms_from: Optional[str] = None

    # --- App ---
    base_url: str = "http://localhost:8000"
    database_path: str = "contextpulse.db"
    baseline_dunning_recovery_rate: float = 0.08

    def razorpay_configured(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)

    def webhook_secret_configured(self) -> bool:
        return bool(self.razorpay_webhook_secret)

    def llm_configured(self) -> bool:
        return bool(self.openai_api_key)

    def twilio_configured(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token)


settings = Settings()