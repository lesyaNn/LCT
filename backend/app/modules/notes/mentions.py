"""Resolve references against existing scoped CRM search and Keycloak services."""

from uuid import UUID
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app.core.permissions import user_permissions
from app.core.security import CurrentUser
from app.modules.admin_users import service as users
from app.modules.admin_users.keycloak_client import get_keycloak_admin_client
from app.modules.admin_users.router import live_user_scope_actor
from app.modules.notes.schemas import Mention


def user_mentions(actor: CurrentUser, q: str, target_id: str | None) -> list[Mention]:
    # Ordinary users have no directory permission; their own identity is safe.
    if "user_university.manage" not in user_permissions(actor):
        title = actor.name or actor.username or "Мой профиль"
        if (target_id is None or target_id == actor.id) and (
            not q or q.casefold() in f"{title} {actor.email or ''}".casefold()
        ):
            return [Mention(kind="user", id=actor.id, title=title)]
        return []
    kc = get_keycloak_admin_client()
    _, scope = live_user_scope_actor(actor, kc)
    rows = ([users.get_user(kc, str(UUID(target_id)), manager_ids=scope)] if target_id else
            users.list_users(kc, search=q, role=None, page=1, page_size=15,
                             manager_ids=scope).items)
    return [Mention(kind="user", id=str(row.id), title=row.name or row.username,
                    href=(f"/admin/users?user={row.id}" if "admin.users" in user_permissions(actor)
                          else f"/admin/university-assignments?user={row.id}"))
            for row in rows if row.status == "active"]


def entity_mentions(db: Session, actor: CurrentUser, kind: str, q: str,
                    target_id: str | None = None, university_id: UUID | None = None) -> list[Mention]:
    from app.modules.search import search
    from app.modules.catalog.repository import list_universities

    if kind == "user":
        return user_mentions(actor, q, target_id)
    if kind in {"direction", "program", "vendor", "product", "responsible"} and not university_id:
        return catalog_mentions(db, actor, kind, q, target_id)
    if kind == "agreements" and not target_id:
        return agreement_mentions(db, actor, q)
    if kind == "university" and not target_id:
        if "university.read" not in user_permissions(actor):
            return []
        rows, _ = list_universities(db, page=1, page_size=15, search=q or None, city=None,
                                    responsible_id=None, sort_by="name", sort_order="asc", user=actor)
        return [Mention(kind="university", id=str(row.id), title=row.name,
                        subtitle=row.city or "", href=f"/universities/{row.id}") for row in rows]
    # Exact resolution uses the same scopes as the canonical detail endpoints,
    # including after an entity was renamed or removed.
    if target_id:
        return resolve_record(db, actor, kind, UUID(target_id), university_id)
    if len(q.strip()) < 2:
        return []
    found = search(db, actor, q)
    mapping = {
        "university": (found.universities, None), "workflow": (found.workflows, None),
        "document": (found.documents, "documents"), "contract": (found.contracts, "documents"),
        "product": (found.products, "products"), "responsible": (found.responsibles, "responsibles"),
    }
    return [Mention(kind=key, id=str(row.id), title=row.title, subtitle=row.subtitle or "",
                    university_id=row.university_id,
                    href=(f"/universities/{row.university_id}?tab={tab}" if tab else
                          f"/workflows/{row.id}" if key == "workflow" else f"/universities/{row.id}"))
            for key, (rows, tab) in mapping.items() if kind in {"entity", key}
            for row in rows][:20]


def catalog_mentions(db: Session, actor: CurrentUser, kind: str, q: str,
                     target_id: str | None) -> list[Mention]:
    from app.models.catalog import ITDirection, ITProduct, ITProgram, Responsible, Vendor
    from app.modules.catalog import repository

    if "university.read" not in user_permissions(actor):
        return []
    models = {"direction": ITDirection, "program": ITProgram, "vendor": Vendor,
              "product": ITProduct, "responsible": Responsible}
    tabs = {"direction": "directions", "program": "programs", "vendor": "vendors",
            "product": "products", "responsible": "responsibles"}
    if target_id:
        row = db.get(models[kind], UUID(target_id))
        rows = [row] if row else []
    else:
        params = dict(page=1, page_size=20, search=q or None, sort_order="asc")
        if kind == "direction":
            rows, _ = repository.list_directions(db, **params, sort_by="name")
        elif kind == "program":
            found, _ = repository.list_programs(db, **params, direction_id=None, sort_by="name")
            rows = [row for row, _ in found]
        elif kind == "vendor":
            rows, _ = repository.list_vendors(db, **params, sort_by="name")
        elif kind == "product":
            found, _ = repository.list_products(db, **params, vendor_id=None, sort_by="name")
            rows = [row for row, _, _ in found]
        else:
            rows, _ = repository.list_responsibles(db, **params, role=None,
                                                   university_id=None, sort_by="full_name")
    result = []
    for row in rows:
        title = row.full_name if kind == "responsible" else row.name
        subtitle = (row.code if kind == "direction" else row.version if kind == "product" else
                    row.email if kind == "responsible" else "")
        href = ("/admin/catalogs?" + urlencode({"type": tabs[kind], "search": title})
                if "catalog.manage" in user_permissions(actor) else None)
        result.append(Mention(kind=kind, id=str(row.id), title=title,
                              subtitle=subtitle or "", href=href))
    return result


def agreement_mentions(db: Session, actor: CurrentUser, q: str) -> list[Mention]:
    from app.modules.catalog import repository

    if "university.read" not in user_permissions(actor):
        return []
    params = dict(page=1, page_size=20, search=q or None, university_id=None,
                  product_id=None, status=None, sort_order="asc", user=actor)
    contracts, _ = repository.list_contracts(db, **params, sort_by="contract_number")
    licenses, _ = repository.list_licenses(db, **params, sort_by="license_number")
    rows = [Mention(kind=kind, id=str(row.id), title=title, subtitle=label,
                    university_id=row.university_id,
                    href=f"/universities/{row.university_id}?tab=documents")
            for kind, label, items in [("contract", "Договор", contracts), ("license", "Лицензия", licenses)]
            for row in items
            for title in [row.contract_number if kind == "contract" else row.license_number]]
    return sorted(rows, key=lambda item: (item.title.casefold(), item.kind, item.id))[:40]


def resolve_record(db: Session, actor: CurrentUser, kind: str, target_id: UUID,
                   university_id: UUID | None) -> list[Mention]:
    from sqlalchemy import select
    from app.core.policies import apply_university_scope
    from app.models.catalog import Contract, ITProduct, License, Responsible, University, UniversityResponsible
    from app.models.interactions import Document, UniversityProduct
    from app.models.workflow_instances import WorkflowInstance

    permission = "workflow.read" if kind == "workflow" else "university.read"
    if permission not in user_permissions(actor):
        return []
    if kind == "university":
        stmt = select(University.id, University.name, University.id).where(University.id == target_id)
        scope_column, tab = University.id, None
    elif kind == "workflow":
        stmt = (select(WorkflowInstance.id, University.name, WorkflowInstance.university_id)
                .join(University, University.id == WorkflowInstance.university_id)
                .where(WorkflowInstance.id == target_id, WorkflowInstance.status != "archived"))
        scope_column, tab = WorkflowInstance.university_id, None
    elif kind in {"document", "contract", "license"}:
        model, title = {"document": (Document, Document.title),
                        "contract": (Contract, Contract.contract_number),
                        "license": (License, License.license_number)}[kind]
        tab = "documents"
        stmt = select(model.id, title, model.university_id).where(model.id == target_id)
        scope_column = model.university_id
    elif kind in {"product", "responsible"}:
        model, relation, fk, title, tab = (
            (ITProduct, UniversityProduct, UniversityProduct.product_id, ITProduct.name, "products")
            if kind == "product" else
            (Responsible, UniversityResponsible, UniversityResponsible.responsible_id,
             Responsible.full_name, "responsibles"))
        stmt = select(model.id, title, relation.university_id).join(relation, fk == model.id).where(model.id == target_id)
        scope_column = relation.university_id
        if university_id:
            stmt = stmt.where(relation.university_id == university_id)
    else:
        return []
    rows = db.execute(apply_university_scope(stmt, scope_column, actor).limit(1))
    return [Mention(kind=kind, id=str(id), title=title, university_id=uni,
                    href=f"/universities/{uni}?tab={tab}" if tab else
                    f"/workflows/{id}" if kind == "workflow" else f"/universities/{id}")
            for id, title, uni in rows]
