"""Application settings (ENV / Docker Secrets friendly).

MINIMAL AUTH STAGE: auth does NOT depend on PostgreSQL/Redis/MinIO.
Domain DB settings stay for the next stage but are unused at runtime.
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    # Fail-closed dev bypass: real compose runs with false. Tests may enable it.
    auth_dev_bypass: bool = False

    frontend_origin: str = "http://localhost:3000"

    # --- Domain stage (NOT used by minimal auth stack) ---
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"
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

    # --- Analytics reports (P4-06-01) ---
    # Filesystem root for generated xlsx/pdf/json reports. Mounted as a
    # persistent named volume in compose; never the public static root and
    # never mixed with workflow attachment keys.
    # ``REPORTS_DIR`` is honored as a legacy alias (existing exporters read
    # it); ``REPORTS_ROOT`` wins when both are set.
    reports_root: str = "/app/reports"

    # --- Health Score (P2-07-03) ---
    # CSV обязательных типов документов для компонента D.
    # Дефолт ТЗ: contract,license,act,protocol.
    health_required_doc_types: str = "contract,license,act,protocol"

    @model_validator(mode="after")
    def validate_security_baseline(self) -> "Settings":
        """Fail closed for settings that would weaken a production process."""
        production = self.app_env.lower() in {"prod", "production"}
        origins = {origin.strip() for origin in self.cors_origins.split(",") if origin.strip()}
        if production:
            if self.auth_dev_bypass:
                raise ValueError("AUTH_DEV_BYPASS must be false in production")
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


settings = Settings()
