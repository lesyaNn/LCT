"""Server-only Keycloak 26 Admin REST adapter. No credentials reach the browser."""

from __future__ import annotations

from urllib.parse import quote

import httpx

from app.config import settings
from app.core.errors import BusinessException, ConflictError
from app.schemas.errors import ErrorCode


class KeycloakAdminClient:
    def __init__(self) -> None:
        self.base = settings.keycloak_admin_base_url.rstrip("/")
        self.realm = quote(settings.keycloak_realm, safe="")
        self._token: str | None = None

    def _access_token(self) -> str:
        if self._token:
            return self._token
        if not settings.keycloak_admin_username or not settings.keycloak_admin_password:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
        try:
            response = httpx.post(
                f"{self.base}/realms/master/protocol/openid-connect/token",
                data={"client_id": "admin-cli", "grant_type": "password",
                      "username": settings.keycloak_admin_username,
                      "password": settings.keycloak_admin_password},
                timeout=5,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if not isinstance(token, str) or not token:
                raise ValueError("missing token")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE) from exc
        self._token = token
        return token

    def request(self, method: str, path: str, *, params: dict | None = None, data=None):
        try:
            response = httpx.request(
                method, f"{self.base}/admin/realms/{self.realm}{path}",
                params=params, json=data,
                headers={"Authorization": f"Bearer {self._access_token()}"}, timeout=8,
            )
        except httpx.HTTPError as exc:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE) from exc
        if response.status_code == 404:
            raise BusinessException(ErrorCode.NOT_FOUND)
        if response.status_code == 409:
            raise ConflictError()
        if response.status_code >= 400:
            # Never pass the provider's response body (which can contain PII)
            # through the public API or application logs.
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE) from exc

    def users(self, *, search: str = "", first: int = 0, maximum: int = 100) -> list[dict]:
        params = {"first": first, "max": maximum}
        if search:
            params["search"] = search
        return self.request("GET", "/users", params=params)

    def users_count(self, *, search: str = "") -> int:
        params = {"search": search} if search else None
        return int(self.request("GET", "/users/count", params=params))

    def user(self, user_id: str) -> dict:
        return self.request("GET", f"/users/{quote(user_id, safe='')}")

    def role(self, name: str) -> dict:
        return self.request("GET", f"/roles/{quote(name, safe='')}")

    def role_users(self, name: str, first: int = 0, maximum: int = 100) -> list[dict]:
        return self.request("GET", f"/roles/{quote(name, safe='')}/users",
                            params={"first": first, "max": maximum})

    def user_roles(self, user_id: str) -> list[dict]:
        return self.request("GET", f"/users/{quote(user_id, safe='')}/role-mappings/realm")

    def assign_role(self, user_id: str, role: dict) -> None:
        self.request("POST", f"/users/{quote(user_id, safe='')}/role-mappings/realm", data=[role])

    def remove_role(self, user_id: str, role: dict) -> None:
        self.request("DELETE", f"/users/{quote(user_id, safe='')}/role-mappings/realm", data=[role])

    def update_user(self, user_id: str, payload: dict) -> None:
        self.request("PUT", f"/users/{quote(user_id, safe='')}", data=payload)

    def create_user(self, payload: dict) -> str:
        try:
            response = httpx.post(
                f"{self.base}/admin/realms/{self.realm}/users", json=payload,
                headers={"Authorization": f"Bearer {self._access_token()}"}, timeout=8,
            )
        except httpx.HTTPError as exc:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE) from exc
        if response.status_code == 409:
            # Keycloak reports the same status for duplicate email and username.
            raise ConflictError()
        if response.status_code != 201:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
        user_id = response.headers.get("Location", "").rstrip("/").rsplit("/", 1)[-1]
        if not user_id:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
        return user_id

    def delete_user(self, user_id: str) -> None:
        self.request("DELETE", f"/users/{quote(user_id, safe='')}")

    def logout(self, user_id: str) -> None:
        self.request("POST", f"/users/{quote(user_id, safe='')}/logout")

    def execute_actions_email(self, user_id: str, actions: list[str]) -> None:
        self.request("PUT", f"/users/{quote(user_id, safe='')}/execute-actions-email", data=actions)

    def ensure_scope_mapper(self) -> None:
        # Keycloak 26 silently discards attributes that are absent from its
        # User Profile. Keep this one administrator-owned field managed while
        # preserving every existing realm profile attribute and group.
        profile = self.request("GET", "/users/profile")
        attributes = profile.get("attributes") or []
        if not any(item.get("name") == "university_ids" for item in attributes):
            self.request("PUT", "/users/profile", data={
                **profile,
                "attributes": [*attributes, {
                    "name": "university_ids", "displayName": "University IDs",
                    "multivalued": True,
                    "permissions": {"view": ["admin"], "edit": ["admin"]},
                }],
            })
        clients = self.request("GET", "/clients", params={"clientId": "rtk-frontend"})
        if len(clients) != 1:
            raise BusinessException(ErrorCode.EXTERNAL_SOURCE_UNAVAILABLE)
        client_id = clients[0]["id"]
        path = f"/clients/{quote(client_id, safe='')}/protocol-mappers/models"
        if any(item.get("name") == "rtk university ids" for item in self.request("GET", path)):
            return
        self.request("POST", path, data={
            "name": "rtk university ids", "protocol": "openid-connect",
            "protocolMapper": "oidc-usermodel-attribute-mapper",
            "config": {"user.attribute": "university_ids", "claim.name": "university_ids",
                       "jsonType.label": "String", "multivalued": "true",
                       "access.token.claim": "true", "id.token.claim": "false",
                       "userinfo.token.claim": "false"},
        })


def get_keycloak_admin_client() -> KeycloakAdminClient:
    return KeycloakAdminClient()
