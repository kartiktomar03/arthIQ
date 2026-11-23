from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env", extra="ignore"
    )

    analytics_dsn: SecretStr | None = None
    olist_analytics_dsn: SecretStr | None = None
    workspace_dsn: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-20b"
    query_timeout_ms: int = Field(default=3000, ge=100, le=10000)
    max_rows: int = Field(default=200, ge=1, le=500)
    max_response_bytes: int = Field(default=262144, ge=1024, le=1048576)
    schema_mode: Literal["rag", "full"] = "rag"
    schema_top_k: int = Field(default=4, ge=1, le=8)
    schema_min_similarity: float = Field(default=0.43, ge=0, le=1)
    schema_datasource_id: str = Field(default="demo-shop", min_length=1, max_length=80)
    qdrant_path: Path = Path(__file__).resolve().parents[1] / ".qdrant"
    embedding_local_files_only: bool = False
