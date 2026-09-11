"""Validated runtime configuration. Secrets are never printed or persisted."""

from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")
    llm_model: str = Field(default="openai/gpt-oss-120b", validation_alias="LLM_MODEL")
    llm_base_url: HttpUrl = Field(
        default="https://api.groq.com/openai/v1", validation_alias="LLM_BASE_URL"
    )
    llm_timeout_seconds: float = Field(default=15, ge=1, le=30)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_device: str = "cpu"
    data_dir: Path = Path("./data")
    active_kb_version: str = "biodiversity-v1"
    api_base_url: str = "http://127.0.0.1:8000"
    enable_weather_enrichment: bool = False
    app_mode: str = "live"
    log_level: str = "INFO"

    @property
    def provider_configured(self) -> bool:
        return self.groq_api_key is not None and bool(self.groq_api_key.get_secret_value())


import os

def get_settings() -> Settings:
    if not os.getenv("GROQ_API_KEY"):
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "GROQ_API_KEY" in st.secrets:
                os.environ["GROQ_API_KEY"] = str(st.secrets["GROQ_API_KEY"])
        except Exception:
            pass
    return Settings()
