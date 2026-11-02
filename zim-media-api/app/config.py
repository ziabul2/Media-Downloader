"""Environment-backed settings. Invalid production defaults fail startup."""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PEPPER = "dev-pepper-change-me"
DEFAULT_PREFIXES = (
    "youtube,vimeo,soundcloud,dailymotion,archive.org,ted,bandcamp,peertube,wikimedia.org,npr"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ZIM Media API"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_prefix: str = "/api/v1"
    public_base_url: str = ""

    database_url: str = "sqlite:///./data/zim.db"
    redis_url: str = ""
    redis_required: bool = False
    auto_create_schema: bool = True

    api_key_required: bool = True
    api_key_pepper: str = DEFAULT_PEPPER
    dev_api_key: str = ""

    default_ticket_ttl_seconds: int = 900
    metadata_cache_ttl_seconds: int = 300
    ticket_one_time: bool = False

    extraction_timeout_seconds: int = 45
    extraction_socket_timeout_seconds: int = 15
    max_concurrent_extractions: int = 2
    max_concurrent_streams: int = 5
    extraction_backend: str = "local"

    proxy_enabled: bool = False
    max_proxy_duration_seconds: int = 1800
    max_proxy_bytes: int = 1_073_741_824
    proxy_connect_timeout_seconds: float = 10.0
    proxy_read_timeout_seconds: float = 30.0

    ffmpeg_convert_enabled: bool = False
    ffmpeg_merge_enabled: bool = False

    requests_per_minute: int = 60
    requests_per_day: int = 5000

    max_url_length: int = 2048
    max_body_bytes: int = 65_536

    log_level: str = "INFO"
    allowed_extractor_prefixes: str = DEFAULT_PREFIXES
    allow_generic_extractor: bool = False
    cors_origins: str = ""
    data_dir: str = "./data"

    @field_validator("extraction_backend")
    @classmethod
    def _backend(cls, value: str) -> str:
        if value not in {"local", "queue"}:
            raise ValueError("extraction_backend must be local or queue")
        return value

    @field_validator("api_prefix")
    @classmethod
    def _prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("api_prefix must start with /")
        return value.rstrip("/") or "/"

    def extractor_prefixes(self) -> list[str]:
        return [part.strip().lower() for part in self.allowed_extractor_prefixes.split(",") if part.strip()]

    def cors_origin_list(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]

    def validate_runtime(self) -> None:
        if self.default_ticket_ttl_seconds < 30 or self.default_ticket_ttl_seconds > 86_400:
            raise ValueError("DEFAULT_TICKET_TTL_SECONDS must be between 30 and 86400")
        if self.metadata_cache_ttl_seconds < 30:
            raise ValueError("METADATA_CACHE_TTL_SECONDS must be at least 30")
        if self.extraction_timeout_seconds < 5:
            raise ValueError("EXTRACTION_TIMEOUT_SECONDS must be at least 5")
        if self.max_concurrent_extractions < 1 or self.max_concurrent_streams < 1:
            raise ValueError("concurrency limits must be at least 1")
        if self.max_proxy_bytes < 1 or self.max_proxy_duration_seconds < 1:
            raise ValueError("proxy limits must be positive")
        if self.requests_per_minute < 1 or self.requests_per_day < 1:
            raise ValueError("rate limits must be positive")
        if self.app_env == "production":
            if self.api_key_pepper == DEFAULT_PEPPER:
                raise ValueError("production refuses the example API_KEY_PEPPER")
            if not self.api_key_required:
                raise ValueError("production requires API_KEY_REQUIRED=true")
            if "change-me" in self.database_url or "sqlite" in self.database_url:
                raise ValueError("production requires a real DATABASE_URL")
            if self.redis_url == "":
                raise ValueError("production requires REDIS_URL")


def load_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
