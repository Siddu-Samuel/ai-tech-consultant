"""Environment-backed settings for the Knowledge Brain service."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    app_env: str = "demo"
    service_name: str = "knowledge-brain"
    database_url: str = "postgresql://consultant:consultant@localhost:5432/consultant"
    anthropic_api_key: str = ""
    claude_model_primary: str = ""
    claude_model_comparison: str = ""
    claude_vision_model: str = ""
    embedding_provider: str = "local-test"
    embedding_model: str = ""
    embedding_dimensions: int = 64
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    retrieval_min_score: float = 0.12
    retrieval_limit: int = 6
    admin_api_token: str = ""
    task1_service_token: str = ""
    crawl_manifest_path: Path = Path("data/knowledge_manifest.json")
    crawl_user_agent: str = "AITechConsultantBot/0.1 (AI Tech Consultant knowledge ingestion)"
    crawl_delay_seconds: float = 1.0
    crawl_max_retries: int = 3
    daily_refresh_utc_hour: int = 2

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore", case_sensitive=False)

    @property
    def demo_mode(self) -> bool:
        return self.app_env.lower() in {"demo", "test"} or not self.anthropic_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
