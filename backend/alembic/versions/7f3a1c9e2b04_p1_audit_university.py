"""P1-04-05: own the audit_events table + per-university attribution.

The legacy P5 audit table was never managed by Alembic (env.py only imports
``app.models``), so this migration creates it from scratch, mirroring
``app.modules.audit.models.AuditEvent`` exactly, plus the additive nullable
``university_id`` UUID column (FK -> universities.id, SET NULL) with
indexes for the passport ``recent_audit`` block
(``WHERE university_id = ? ORDER BY created_at DESC LIMIT 5``).

Why a new column instead of reusing entity_type/entity_id: those are
``Integer`` legacy columns incompatible with UUID universities, and
filtering "all universities' events in Python" is explicitly forbidden
(P1-04-05 §5). The column is nullable and ``AuditService.log`` keeps a
backward-compatible signature, so existing writers are unaffected.

Revision ID: 7f3a1c9e2b04. Depends on 7f3a1c9e2b03.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f3a1c9e2b04"
down_revision: str | Sequence[str] | None = "7f3a1c9e2b03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("before_data", sa.Text(), server_default="{}", nullable=False),
        sa.Column("after_data", sa.Text(), server_default="{}", nullable=False),
        sa.Column("ip_address", sa.String(64), server_default="", nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["university_id"],
            ["universities.id"],
            name="fk_audit_events_university_id_universities",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(
        "ix_audit_events_university_id", "audit_events", ["university_id"], if_not_exists=True
    )
    op.create_index(
        "ix_audit_events_univ_created",
        "audit_events",
        ["university_id", "created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_univ_created", table_name="audit_events")
    op.drop_index("ix_audit_events_university_id", table_name="audit_events")
    op.drop_table("audit_events")
