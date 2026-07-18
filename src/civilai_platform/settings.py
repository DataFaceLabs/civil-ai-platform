from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CIVILAI_",
        extra="ignore",
        env_file=(".env.local", ".env"),
        env_file_encoding="utf-8",
    )

    environment: str = "dev"
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("aws_region", "AWS_REGION"),
    )
    aws_profile: str | None = Field(
        default=None,
        validation_alias=AliasChoices("aws_profile", "AWS_PROFILE"),
    )

    # DynamoDB
    dynamodb_table: str = "civilai-app-dev"
    dynamodb_endpoint_url: str | None = Field(
        default=None,
        description="Optional local DynamoDB endpoint, e.g. http://localhost:8002",
    )
    store_backend: str = Field(
        default="memory",
        description="memory | file | dynamodb",
    )
    file_store_path: str = Field(
        default=".local/platform-store",
        description="Root directory when store_backend=file",
    )

    # S3 app bucket
    app_bucket: str | None = None
    artifact_backend: str = Field(default="memory", description="memory | s3")

    # Agent training-corpus bucket (feedback capture). Empty/None => capture disabled.
    agent_corpus_bucket: str | None = None
    # Defensive PII key denylist for the corpus (mirrors the data catalog sensitivity:pii
    # set; comma-separated override). The field_context already arrives redacted upstream.
    corpus_pii_keys: str = "owner_name"

    # Cognito JWT validation
    cognito_user_pool_id: str | None = None
    cognito_app_client_id: str | None = None
    dev_auth: bool = Field(
        default=True,
        description="Accept X-Dev-User-Id / X-Dev-Tenant-Id headers when true",
    )

    # Data API proxy (Pillar F)
    data_api_base: str = Field(default="http://localhost:8000")
    data_service_key: str | None = None

    # Agent runtime
    agent_dry_run: bool = Field(
        default=True,
        description="When true, Strands agent returns dry-run responses without Bedrock.",
    )

    # CORS
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"],
        description="Exact origins in production; dev_auth uses localhost:* regex instead",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value  # type: ignore[return-value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
