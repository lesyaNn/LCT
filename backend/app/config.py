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
    max_upload_mb: int = 50
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if self.frontend_origin and self.frontend_origin not in origins:
            origins.append(self.frontend_origin)
        return origins


settings = Settings()
