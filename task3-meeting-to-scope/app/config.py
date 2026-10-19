"""Environment-backed settings for the Meeting-to-Scope service."""

from functools import lru_cache
from pathlib import Path

from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "demo"
    service_name: str = "meeting-to-scope"
    anthropic_api_key: str = ""
    claude_model_primary: str = ""
    knowledge_brain_url: str = "http://localhost:8001"
    database_url: str = ""
    storage_mode: Literal["sqlite", "postgres"] = "sqlite"
    task1_service_token: str = ""
    admin_api_token: str = ""
    hourly_rate: float = 0
    currency: str = "USD"
    claude_input_cost_per_mtok: float | None = None
    claude_output_cost_per_mtok: float | None = None

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore", case_sensitive=False)

    @model_validator(mode="after")
    def production_requires_postgres(self):
        if self.app_env.lower() == "production" and self.storage_mode != "postgres":
            raise ValueError("Production requires STORAGE_MODE=postgres")
        return self

    @property
    def demo_mode(self) -> bool:
        return self.app_env.lower() in {"demo", "test"} or not self.anthropic_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
