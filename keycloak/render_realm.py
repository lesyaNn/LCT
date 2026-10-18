#!/usr/bin/env python3
"""Configure frontend and Swagger callback URLs without changing other clients.

FRONTEND_ORIGIN=https://crm.example \\
SWAGGER_PUBLIC_URL=https://api.example python3 keycloak/render_realm.py

This prepares a realm import. Existing Keycloak realms must be updated separately;
Keycloak skips imports for realms that already exist.
"""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit


def public_url(value: str, *, allow_path: bool = False) -> str:
    value = value.rstrip("/")
    parts = urlsplit(value)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment
            or "*" in value or (parts.path and not allow_path)):
        raise ValueError("Expected an HTTP(S) public URL without credentials, query or fragment")
    return value


def configure_realm(realm: dict, frontend_origin: str, swagger_public_url: str) -> dict:
    frontend_origin = public_url(frontend_origin)
    swagger_public_url = public_url(swagger_public_url, allow_path=True)
    parts = urlsplit(swagger_public_url)
    swagger_origin = f"{parts.scheme}://{parts.netloc}"
    client = next((item for item in realm["clients"] if item["clientId"] == "rtk-frontend"), None)
    if client is None:
        raise ValueError("rtk-frontend client not found")
    client["redirectUris"] = [frontend_origin + "/*", swagger_public_url + "/docs/oauth2-redirect.html"]
    client["webOrigins"] = list(dict.fromkeys([frontend_origin, swagger_origin]))
    client.setdefault("attributes", {}).update({
        "post.logout.redirect.uris": frontend_origin + "/*",
        "pkce.code.challenge.method": "S256",
    })
    return realm


def main() -> None:
    path = Path(__file__).with_name("realm-export.json")
    frontend = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
    swagger = os.environ.get("SWAGGER_PUBLIC_URL") or (
        "http://localhost:8000" if frontend.rstrip("/") == "http://localhost:3000" else frontend
    )
    realm = json.loads(path.read_text(encoding="utf-8"))
    configure_realm(realm, frontend, swagger)
    path.write_text(json.dumps(realm, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[render_realm] configured frontend={frontend} swagger={swagger}")


if __name__ == "__main__":
    main()
