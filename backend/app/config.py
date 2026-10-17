"""Application settings (ENV / Docker Secrets friendly).

MINIMAL AUTH STAGE: auth does NOT depend on PostgreSQL/Redis/MinIO.
Domain DB settings stay for the next stage but are unused at runtime.
"""
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_BYPASS_ENVIRONMENTS = frozenset({"dev", "development", "local", "test", "testing"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "RTK EdTech CRM"
    app_env: str = "dev"

    # --- Auth (Keycloak) ---
    # External issuer as seen by the browser (goes into JWT `iss`).
    keycloak_issuer: str = "http://localhost:8081/realms/rtk"
    # Internal JWKS URL as seen from inside Docker network.
    keycloak_jwks_url: str = "http://keycloak:8080/realms/rtk/protocol/openid-connect/certs"
    keycloak_realm: str = "rtk"
    keycloak_audience: str = "rtk-api"
    # Server-only Keycloak Admin API credentials. Never exposed as NEXT_PUBLIC.
    keycloak_admin_base_url: str = "http://keycloak:8080"
    keycloak_admin_username: str = ""
    keycloak_admin_password: str = ""
    # Fail-closed dev bypass: real compose runs with false. Tests may enable it.
    auth_dev_bypass: bool = False

    frontend_origin: str = "http://localhost:3000"

    # Email is an optional delivery channel for persisted notifications.
    email_notifications_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_from_email: str = ""
    smtp_from_name: str = "RTK EdTech CRM"
    smtp_security: str = "starttls"  # starttls or ssl; plaintext is unsupported
    smtp_timeout_seconds: float = Field(default=10, ge=1, le=60)
    email_max_attempts: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def validate_email(self) -> "Settings":
        if self.smtp_security not in {"starttls", "ssl"}:
            raise ValueError("SMTP_SECURITY must be starttls or ssl")
        if self.email_notifications_enabled and (not self.smtp_host or not self.smtp_from_email):
            raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required when email is enabled")
        return self

    # --- Domain stage (NOT used by minimal auth stack) ---
    database_url: str = "sqlite:///./dev.db"
    # M5: explicit DB pool/timeout knobs (PostgreSQL only; SQLite ignores them).
    # Defaults fit uvicorn sync workers + one report worker; raise MAX_OVERFLOW
    # for import-heavy deployments (H1 batches hold connections briefly).
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30
    db_statement_timeout_ms: int = 30000
    # KeyDB (wire-совместим с Redis, тот же RESP-протокол и redis-py клиент).
    # Схема URL остаётся ``redis://`` — это схема протокола, а не вендора.
    # KEYDB_URL — primary, REDIS_URL — legacy fallback для старых .env.
    redis_url: str = "redis://localhost:6379/0"
    keydb_url: str | None = None
    s3_endpoint: str = "http://localhost:9000"
    # Credentials are intentionally empty by default.  They are required from
    # the environment when S3/MinIO is selected; the old demo credential
    # fallback was unsafe in a production process.
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "rtk-files"
    # P2-05 file storage: "local" (production default, persistent volume)
    # or "s3" (MinIO/S3 seam, same service code path).
    storage_backend: str = "local"
    # Production object root. Mounted as a persistent volume in compose.
    storage_root: str = "/app/storage"
    max_upload_mb: int = 50
    # P2-05-01: optional upload allowlist (comma-separated extensions,
    # e.g. "pdf,docx,xlsx"). Empty = open (no contract from the customer
    # yet); non-empty = 415 on other extensions. MIME types are recorded
    # as declared, never allowlisted (no MIME contract).
    upload_allowed_extensions: str = ""
    cors_origins: str = "http://localhost:3000"

    # --- Rate limiting (M10, heavy endpoints only) ---
    # 0 disables the limiter (tests); default 120 req/min per token/IP.
    rate_limit_per_minute: int = 120

    # Documentation assistant. Models are downloaded explicitly, never by an API request.
    assistant_enabled: bool = False
    assistant_ollama_url: str = "http://localhost:11434"
    assistant_model: str = Field(default="qwen3:4b", min_length=1, max_length=128)
    assistant_embedding_model: str = Field(default="qwen3-embedding:0.6b", min_length=1,
                                           max_length=128)
    assistant_docs_root: str = str(
        Path(__file__).resolve().parents[2] / "frontend" / "public" / "docs"
    )
    assistant_index_path: str = "var/assistant/index.json"
    assistant_timeout_seconds: float = Field(default=60, ge=1, le=300)
    assistant_rate_limit_per_minute: int = Field(default=10, ge=1, le=120)
    assistant_max_concurrent: int = Field(default=2, ge=1, le=8)
    assistant_history_turns: int = Field(default=3, ge=0, le=6)
    assistant_max_turns: int = Field(default=100, ge=1, le=500)
    assistant_retention_days: int = Field(default=30, ge=1, le=365)

    @model_validator(mode="after")
    def validate_assistant(self) -> "Settings":
        target = urlsplit(self.assistant_ollama_url)
        if (target.scheme not in {"http", "https"} or not target.hostname
                or target.username or target.password or target.query or target.fragment
                or target.path not in {"", "/"}):
            raise ValueError("ASSISTANT_OLLAMA_URL must be an HTTP(S) origin")
        for model in (self.assistant_model, self.assistant_embedding_model):
            if not model.strip() or "cloud" in model.lower() or "://" in model:
                raise ValueError("Assistant requires explicit local model names")
        return self

    # --- Analytics reports (P4-06-01) ---
    # Filesystem root for generated xlsx/pdf/json reports. Mounted as a
    # persistent named volume in compose; never the public static root and
    # never mixed with workflow attachment keys.
    # ``REPORTS_DIR`` is honored as a legacy alias (existing exporters read
    # it); ``REPORTS_ROOT`` wins when both are set.
    reports_root: str = "/app/reports"

    # Explicit offline adapter; never enabled automatically after a real error.
    # No live provider contract/credentials are configured in this release.
    external_adapter_mode: str = "disabled"

    # --- Health Score (P2-07-03) ---
    # CSV обязательных типов документов для компонента D.
    # Дефолт ТЗ: contract,license,act,protocol.
    health_required_doc_types: str = "contract,license,act,protocol"

    @model_validator(mode="after")
    def validate_security_baseline(self) -> "Settings":
        """Fail closed for settings that would weaken a production process."""
        environment = self.app_env.strip().lower()
        production = environment in {"prod", "production"}
        origins = {origin.strip() for origin in self.cors_origins.split(",") if origin.strip()}
        if self.auth_dev_bypass and environment not in DEV_BYPASS_ENVIRONMENTS:
            raise ValueError(
                "AUTH_DEV_BYPASS is allowed only in explicit local development/test environments"
            )
        if production:
            if self.external_adapter_mode != "disabled":
                raise ValueError("External mock adapter is forbidden in production")
            if "*" in origins or "*" in self.cors_origin_list:
                raise ValueError("CORS wildcard is not allowed in production")
            if self.storage_backend.lower() in {"s3", "minio"} and (
                not self.s3_access_key.strip() or not self.s3_secret_key.strip()
            ):
                raise ValueError("S3 credentials must be supplied through environment in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.frontend_origin and self.frontend_origin not in origins:
            origins.append(self.frontend_origin)
        return origins

    @property
    def cache_url(self) -> str:
        """Активный URL кеша: KEYDB_URL, иначе legacy REDIS_URL."""
        return self.keydb_url or self.redis_url


settings = Settings()
