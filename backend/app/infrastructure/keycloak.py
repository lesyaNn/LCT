"""Keycloak JWKS placeholder (prod verification point)."""
import httpx

from app.config import settings


async def fetch_jwks() -> dict:
    url = f"{settings.keycloak_issuer}/protocol/openid-connect/certs"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
