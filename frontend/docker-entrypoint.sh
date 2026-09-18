#!/bin/sh
# Runtime config for the SPA (P0-2): the same image runs on any host.
# Values come from environment (compose maps them 1:1); empty API_URL
# means "same origin" -> the nginx /api/ proxy (see nginx.conf).
set -e

CONFIG_DIR=/usr/share/nginx/html
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:8081}"
KEYCLOAK_REALM="${KEYCLOAK_REALM:-rtk}"
KEYCLOAK_CLIENT_ID="${KEYCLOAK_CLIENT_ID:-rtk-frontend}"
API_URL="${API_URL:-}"

cat > "${CONFIG_DIR}/config.json" <<EOF
{
  "keycloakUrl": "${KEYCLOAK_URL}",
  "keycloakRealm": "${KEYCLOAK_REALM}",
  "keycloakClientId": "${KEYCLOAK_CLIENT_ID}",
  "apiUrl": "${API_URL}"
}
EOF
echo "[entrypoint] wrote ${CONFIG_DIR}/config.json (apiUrl='${API_URL:-<same-origin>}')"

exec "$@"
