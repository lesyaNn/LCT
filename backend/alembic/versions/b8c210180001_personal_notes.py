"""Private folders and notes with optimistic revisions and indexed search.

Revision ID: b8c210180001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8c210180001"
down_revision: str | Sequence[str] | None = "a7b210160001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "note_folders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_sub", sa.String(256), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_sub", "name", name="uq_note_folders_owner_name"),
    )
    op.create_table(
        "personal_notes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_sub", sa.String(256), nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("search_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("folder_id", sa.Uuid(), sa.ForeignKey("note_folders.id", ondelete="SET NULL")),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("revision >= 0", name="ck_personal_notes_revision"),
    )
    op.create_index("ix_personal_notes_owner_updated", "personal_notes", ["owner_sub", "updated_at"])
    op.create_index("ix_personal_notes_owner_folder", "personal_notes", ["owner_sub", "folder_id"])
    op.create_index("ix_personal_notes_owner_deleted", "personal_notes", ["owner_sub", "deleted_at"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute("CREATE INDEX ix_personal_notes_search_trgm ON personal_notes USING gin (search_text gin_trgm_ops)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_personal_notes_search_trgm")
    op.drop_index("ix_personal_notes_owner_deleted", table_name="personal_notes")
    op.drop_index("ix_personal_notes_owner_folder", table_name="personal_notes")
    op.drop_index("ix_personal_notes_owner_updated", table_name="personal_notes")
    op.drop_table("personal_notes")
    op.drop_table("note_folders")
