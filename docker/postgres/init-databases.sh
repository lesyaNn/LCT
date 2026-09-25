#!/bin/sh
# PostgreSQL bootstrap: create the Keycloak database + role on FIRST init.
#
# Executed by the postgres image entrypoint from /docker-entrypoint-initdb.d/
# ONLY when pgdata is fresh (new data directory). For an already-initialized
# volume use the one-time SQL in README (CREATE ROLE/DATABASE IF NOT EXISTS
# equivalent) instead — this script never runs there.
#
# Env (all optional, dev defaults match project style; no prod secrets here):
#   POSTGRES_USER / POSTGRES_DB  - app superuser/db, managed by the image itself
#   KEYCLOAK_DB                  - Keycloak database name (default: keycloak)
#   KEYCLOAK_DB_USER             - Keycloak role name      (default: keycloak)
#   KEYCLOAK_DB_PASSWORD         - Keycloak role password  (default: change-me)
set -eu

APP_DB="${POSTGRES_DB:-rtk}"
KC_DB="${KEYCLOAK_DB:-keycloak}"
KC_USER="${KEYCLOAK_DB_USER:-keycloak}"
KC_PASSWORD="${KEYCLOAK_DB_PASSWORD:-change-me}"

# Fail closed on suspicious identifiers (avoid SQL injection via env).
valid_ident() { case "$1" in ''|*[!a-zA-Z0-9_]* ) return 1;; *) return 0;; esac; }
valid_ident "$KC_DB" || { echo "[init-databases] ERROR: invalid KEYCLOAK_DB='$KC_DB'" >&2; exit 1; }
valid_ident "$KC_USER" || { echo "[init-databases] ERROR: invalid KEYCLOAK_DB_USER='$KC_USER'" >&2; exit 1; }

# Escape single quotes for the SQL string literal.
KC_PASSWORD_ESCAPED=$(printf "%s" "$KC_PASSWORD" | sed "s/'/''/g")

if [ "$KC_USER" = "$POSTGRES_USER" ]; then
  echo "[init-databases] KEYCLOAK_DB_USER equals POSTGRES_USER; skipping role creation."
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
SELECT 'CREATE DATABASE "$KC_DB"' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$KC_DB')\gexec
EOSQL
else
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$KC_USER') THEN
    CREATE ROLE "$KC_USER" WITH LOGIN PASSWORD '$KC_PASSWORD_ESCAPED';
  ELSE
    ALTER ROLE "$KC_USER" WITH LOGIN PASSWORD '$KC_PASSWORD_ESCAPED';
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE "$KC_DB" OWNER "$KC_USER"' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '$KC_DB')\gexec
GRANT ALL PRIVILEGES ON DATABASE "$KC_DB" TO "$KC_USER";
EOSQL
fi

# Least privilege by design: the Keycloak role owns only the Keycloak database.
# It is NOT owner of the app database ($APP_DB) and owns no tables there.
echo "[init-databases] ensured database \"$KC_DB\" for role \"$KC_USER\" (app db \"$APP_DB\" untouched)"
