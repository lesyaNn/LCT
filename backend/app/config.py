"""Application settings (ENV / Docker Secrets friendly).

MINIMAL AUTH STAGE: auth does NOT depend on PostgreSQL/Redis/MinIO.
Domain DB settings stay for the next stage but are unused at runtime.
"""
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
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "rtk-files"
    # P2-05 file storage: "local" (production default, persistent volume)
    # or "s3" (MinIO/S3 seam, same service code path).
    storage_backend: str = "local"
    # Production object root. Mounted as a persistent volume in compose.
    storage_root: str = "/app/storage"
    max_upload_mb: int = 50
    cors_origins: str = "http://localhost:3000"

    # --- Health Score (P2-07-03) ---
    # CSV обязательных типов документов для компонента D.
    # Дефолт ТЗ: contract,license,act,protocol.
    health_required_doc_types: str = "contract,license,act,protocol"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.frontend_origin and self.frontend_origin not in origins:
            origins.append(self.frontend_origin)
        return origins


settings = Settings()
