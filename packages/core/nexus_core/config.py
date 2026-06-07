from functools import lru_cache

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "nexus"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_base_url: str = "http://localhost:8000"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: PostgresDsn = Field(
        "postgresql+asyncpg://nexus:nexus@localhost:5432/nexus",
        alias="DATABASE_URL",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: RedisDsn = Field("redis://localhost:6379/0", alias="REDIS_URL")

    # ── Kafka ─────────────────────────────────────────────────────────────────
    kafka_brokers: str = Field("localhost:9092", alias="KAFKA_BROKERS")
    kafka_topic_changes: str = "nexus.change_events"
    kafka_topic_dlq: str = "nexus.change_events.dlq"
    kafka_consumer_group: str = "nexus-ingestion"

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_url: str = Field("http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str | None = None
    qdrant_collection_prefix: str = "tenant"

    # ── Elasticsearch ─────────────────────────────────────────────────────────
    elasticsearch_url: str = Field("http://localhost:9200", alias="ELASTICSEARCH_URL")
    elasticsearch_api_key: str | None = None
    elasticsearch_index_prefix: str = "nexus"

    # ── AI / Models ───────────────────────────────────────────────────────────
    openai_api_key: str = Field("dev-openai-key", alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(None, alias="ANTHROPIC_API_KEY")
    cohere_api_key: str = Field("dev-cohere-key", alias="COHERE_API_KEY")
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    generation_model: str = "claude-sonnet-4-20250514"
    embedding_batch_size: int = 32

    # ── Ingestion ─────────────────────────────────────────────────────────────
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64
    max_ingest_workers: int = 4
    raw_content_ttl_hours: int = 48

    # ── Query ─────────────────────────────────────────────────────────────────
    retrieval_top_k: int = 40
    rerank_top_k: int = 20
    final_top_k: int = 8
    query_cache_ttl_seconds: int = 300
    hyde_enabled: bool = True
    multi_query_enabled: bool = True

    # ── Security ──────────────────────────────────────────────────────────────
    jwt_secret: str = Field(
        "dev-jwt-secret-minimum-32-characters",
        alias="JWT_SECRET",
    )
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    encryption_key_id: str = Field("local", alias="ENCRYPTION_KEY_ID")
    webhook_signing_secret: str = Field(
        "dev-webhook-secret",
        alias="WEBHOOK_SIGNING_SECRET",
    )

    # ── Celery ───────────────────────────────────────────────────────────────
    celery_broker_url: str = Field("redis://localhost:6379/1", alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field(
        "redis://localhost:6379/2",
        alias="CELERY_RESULT_BACKEND",
    )

    # ── S3 ────────────────────────────────────────────────────────────────────
    s3_bucket: str = Field("nexus-raw-dev", alias="S3_BUCKET")
    aws_region: str = "us-east-1"

    # ── OAuth Connectors ─────────────────────────────────────────────────────
    google_client_id: str = Field("", alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field("", alias="GOOGLE_CLIENT_SECRET")
    notion_client_id: str = Field("", alias="NOTION_CLIENT_ID")
    notion_client_secret: str = Field("", alias="NOTION_CLIENT_SECRET")
    clickup_client_id: str = Field("", alias="CLICKUP_CLIENT_ID")
    clickup_client_secret: str = Field("", alias="CLICKUP_CLIENT_SECRET")
    slack_client_id: str = Field("", alias="SLACK_CLIENT_ID")
    slack_client_secret: str = Field("", alias="SLACK_CLIENT_SECRET")
    slack_signing_secret: str = Field("", alias="SLACK_SIGNING_SECRET")
    confluence_client_id: str = Field("", alias="CONFLUENCE_CLIENT_ID")
    confluence_client_secret: str = Field("", alias="CONFLUENCE_CLIENT_SECRET")
    github_app_id: str = Field("", alias="GITHUB_APP_ID")
    github_app_private_key_path: str = Field("", alias="GITHUB_APP_PRIVATE_KEY_PATH")
    linear_client_id: str = Field("", alias="LINEAR_CLIENT_ID")
    linear_client_secret: str = Field("", alias="LINEAR_CLIENT_SECRET")

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_url(cls, v: str) -> str:
        # Replace postgres:// with postgresql+asyncpg:// for async driver
        return v.replace("postgres://", "postgresql+asyncpg://", 1)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def kafka_broker_list(self) -> list[str]:
        return [b.strip() for b in self.kafka_brokers.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()
