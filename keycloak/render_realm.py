#!/usr/bin/env python3
"""Render keycloak/realm-export.json for a non-localhost stand (P0-2 fix).

The stock export pins ``http://localhost:3000`` in the public client's
``redirectUris``/``webOrigins``. Run this BEFORE ``docker compose up`` on a
jury/remote host so Keycloak accepts the real frontend origin::

    FRONTEND_ORIGIN=http://192.168.1.10:3000 python3 keycloak/render_realm.py
    docker compose up --build

Formatting-preserving: only the two URI occurrences of client
``rtk-frontend`` are rewritten in place (no JSON round-trip), so the diff
stays minimal and reviewable. Idempotent.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "realm-export.json")

origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").rstrip("/")

with open(PATH, encoding="utf-8") as fh:
    text = fh.read()

# Scope the replacement to the rtk-frontend client block: from its
# "clientId" marker to the next top-level client entry.
start = text.find('"clientId" : "rtk-frontend"')
if start == -1:
    start = text.find('"clientId": "rtk-frontend"')
if start == -1:
    sys.exit("[render_realm] ERROR: rtk-frontend client not found")

head, tail = text[:start], text[start:]
changed = 0
subs = [
    # (regex, replacement): scoped to the rtk-frontend client block.
    (r'"redirectUris": \["[^"]+"\]', f'"redirectUris": ["{origin}/*"]'),
    (r'"webOrigins": \["[^"]+"\]', f'"webOrigins": ["{origin}"]'),
    (r'"post\.logout\.redirect\.uris": "[^"]+"', f'"post.logout.redirect.uris": "{origin}/*"'),
]
for pattern, repl in subs:
    tail, n = re.subn(pattern, repl, tail, count=1)
    changed += n

if changed:
    with open(PATH, "w", encoding="utf-8") as fh:
        fh.write(head + tail)

print(f"[render_realm] FRONTEND_ORIGIN={origin} replaced={changed}")
sys.exit(0)
