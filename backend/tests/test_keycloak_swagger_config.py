"""Exercise realm URL rendering on real exports without writing the export."""

import copy
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
configure_realm = runpy.run_path(str(ROOT / "keycloak/render_realm.py"))["configure_realm"]


def test_remote_frontend_and_swagger_urls_replace_all_localhost_entries():
    realm = json.loads((ROOT / "keycloak/realm-export.json").read_text())
    realm["clients"].append({"clientId": "other", "redirectUris": ["https://other.example/*"]})
    other = copy.deepcopy(realm["clients"][-1])
    configure_realm(realm, "https://crm.example", "https://api.example/backend/")
    client = next(c for c in realm["clients"] if c["clientId"] == "rtk-frontend")
    assert client["redirectUris"] == [
        "https://crm.example/*", "https://api.example/backend/docs/oauth2-redirect.html",
    ]
    assert client["webOrigins"] == ["https://crm.example", "https://api.example"]
    assert client["attributes"]["pkce.code.challenge.method"] == "S256"
    assert realm["clients"][-1] == other
    snapshot = copy.deepcopy(realm)
    assert configure_realm(realm, "https://crm.example", "https://api.example/backend") == snapshot


@pytest.mark.parametrize("url", ["*", "https://*.example", "https://user:secret@crm.example",
                                    "javascript:alert(1)", "https://crm.example/?redirect=evil"])
def test_render_rejects_unsafe_public_urls(url):
    realm = {"clients": [{"clientId": "rtk-frontend"}]}
    with pytest.raises(ValueError):
        configure_realm(realm, url, "https://api.example")


def test_cli_uses_public_urls_and_is_idempotent(tmp_path):
    script = tmp_path / "render_realm.py"
    script.write_text((ROOT / "keycloak/render_realm.py").read_text())
    export = tmp_path / "realm-export.json"
    export.write_text((ROOT / "keycloak/realm-export.json").read_text())
    env = {**os.environ, "FRONTEND_ORIGIN": "https://crm.example",
           "SWAGGER_PUBLIC_URL": "https://crm.example/backend"}
    subprocess.run([sys.executable, str(script)], env=env, check=True, capture_output=True)
    rendered = export.read_text()
    client = next(c for c in json.loads(rendered)["clients"] if c["clientId"] == "rtk-frontend")
    assert client["webOrigins"] == ["https://crm.example"]
    assert client["redirectUris"][-1] == "https://crm.example/backend/docs/oauth2-redirect.html"
    subprocess.run([sys.executable, str(script)], env=env, check=True, capture_output=True)
    assert export.read_text() == rendered
