"""Assign seeded demo universities to the existing manager and user in Keycloak."""

import os

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.catalog import University
from app.modules.admin_users.keycloak_client import KeycloakAdminClient
from app.scripts.seed_demo import UNIVERSITIES


def main() -> None:
    if os.getenv("DEMO_MODE") != "true":
        raise SystemExit("Demo scope provisioning requires DEMO_MODE=true")

    names = [name for name, _ in UNIVERSITIES[:3]]
    with Session(create_engine(settings.database_url)) as db:
        rows = db.execute(select(University).where(University.name.in_(names))).scalars().all()
    ids = {row.name: str(row.id) for row in rows}
    if len(ids) != len(names):
        raise SystemExit("Seed demo universities before provisioning demo scope")

    kc = KeycloakAdminClient()
    kc.ensure_scope_mapper()
    for username, role, assigned in (
        ("manager", "manager", names),
        ("user", "user", names[:1]),
    ):
        matches = [item for item in kc.users(search=username) if item.get("username") == username]
        if len(matches) != 1:
            raise SystemExit(f"Expected one existing demo account: {username}")
        account = kc.user(matches[0]["id"])
        actual_roles = {item["name"] for item in kc.user_roles(account["id"])}
        if account.get("email") != f"{username}@example.local" or role not in actual_roles:
            raise SystemExit(f"Unexpected demo account identity or role: {username}")
        attributes = dict(account.get("attributes") or {})
        attributes["university_ids"] = [ids[name] for name in assigned]
        kc.update_user(account["id"], {**account, "attributes": attributes})
        print(f"{username}: {len(assigned)} demo universities assigned")


if __name__ == "__main__":
    main()
