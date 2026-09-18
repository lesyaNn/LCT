"""P1 migration 3/3 (head): students, links, history (P1-01-03, P1-07-01).

students, university_programs, university_products, meetings,
meeting_documents, documents, interaction_notes.

Includes meeting_documents (P1-07-01 decision) — no separate migration.

Revision ID: 7f3a1c9e2b03. Depends on 7f3a1c9e2b02.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7f3a1c9e2b03"
down_revision: str | Sequence[str] | None = "7f3a1c9e2b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("group_name", sa.String(256), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("started_at", sa.Date(), nullable=False),
        sa.Column("finished_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_students_university_id_universities", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["program_id"], ["it_programs.id"],
            name="fk_students_program_id_it_programs", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_students"),
        sa.UniqueConstraint("external_id", name="uq_students_external_id"),
    )
    op.create_index("ix_students_university_id", "students", ["university_id"],
                    if_not_exists=True)
    op.create_index("ix_students_program_id", "students", ["program_id"],
                    if_not_exists=True)
    op.create_index("ix_students_status", "students", ["status"],
                    if_not_exists=True)

    op.create_table(
        "university_programs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default="planned"),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("responsible_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_university_programs_university_id_universities",
            ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["program_id"], ["it_programs.id"],
            name="fk_university_programs_program_id_it_programs",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["responsible_id"], ["responsibles.id"],
            name="fk_university_programs_responsible_id_responsibles",
            ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_university_programs"),
        sa.UniqueConstraint("university_id", "program_id",
                            name="uq_university_programs_uni_prog"),
    )
    op.create_index("ix_univ_programs_university_id", "university_programs",
                    ["university_id"], if_not_exists=True)
    op.create_index("ix_univ_programs_program_id", "university_programs",
                    ["program_id"], if_not_exists=True)
    op.create_index("ix_univ_programs_status", "university_programs", ["status"],
                    if_not_exists=True)

    op.create_table(
        "university_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("license_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False,
                  server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_university_products_university_id_universities",
            ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["it_products.id"],
            name="fk_university_products_product_id_it_products",
            ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["license_id"], ["licenses.id"],
            name="fk_university_products_license_id_licenses",
            ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_university_products"),
        sa.UniqueConstraint("university_id", "product_id",
                            name="uq_university_products_uni_prod"),
    )
    op.create_index("ix_univ_products_university_id", "university_products",
                    ["university_id"], if_not_exists=True)
    op.create_index("ix_univ_products_product_id", "university_products",
                    ["product_id"], if_not_exists=True)

    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("meeting_type", sa.String(32), nullable=False,
                  server_default="online"),
        sa.Column("subject", sa.String(1024), nullable=False),
        sa.Column("participants",
                  postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
                  nullable=False, server_default="[]"),
        sa.Column("outcome", sa.Text(), nullable=True),
        sa.Column("next_action", sa.Text(), nullable=True),
        sa.Column("next_action_due", sa.Date(), nullable=True),
        sa.Column("meeting_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_keycloak_sub", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_meetings_university_id_universities", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_meetings"),
    )
    op.create_index("ix_meetings_university_id", "meetings", ["university_id"],
                    if_not_exists=True)
    op.create_index("ix_meetings_meeting_at", "meetings", ["meeting_at"],
                    if_not_exists=True)
    op.create_index("ix_meetings_univ_meeting_at", "meetings",
                    ["university_id", "meeting_at"], if_not_exists=True)

    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(1024), nullable=False),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mime_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("license_id", sa.Uuid(), nullable=True),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("signed_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status_raw", sa.String(32), nullable=False,
                  server_default="draft"),
        sa.Column("uploaded_by_keycloak_sub", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_documents_university_id_universities", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["license_id"], ["licenses.id"],
            name="fk_documents_license_id_licenses", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contracts.id"],
            name="fk_documents_contract_id_contracts", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.CheckConstraint(
            "NOT (license_id IS NOT NULL AND contract_id IS NOT NULL)",
            name="ck_documents_single_link"),
    )
    op.create_index("ix_documents_university_id", "documents", ["university_id"],
                    if_not_exists=True)
    op.create_index("ix_documents_status_raw", "documents", ["status_raw"],
                    if_not_exists=True)
    op.create_index("ix_documents_license_id", "documents", ["license_id"],
                    if_not_exists=True)
    op.create_index("ix_documents_contract_id", "documents", ["contract_id"],
                    if_not_exists=True)
    op.create_index("ix_documents_expires_at", "documents", ["expires_at"],
                    if_not_exists=True)

    op.create_table(
        "interaction_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("author_keycloak_sub", sa.String(256), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_interaction_notes_university_id_universities",
            ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_interaction_notes"),
    )
    op.create_index("ix_interaction_notes_university_id", "interaction_notes",
                    ["university_id"], if_not_exists=True)
    op.create_index("ix_interaction_notes_created_at", "interaction_notes",
                    ["created_at"], if_not_exists=True)

    op.create_table(
        "meeting_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meetings.id"],
            name="fk_meeting_documents_meeting_id_meetings", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"],
            name="fk_meeting_documents_document_id_documents",
            ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_meeting_documents"),
        sa.UniqueConstraint("meeting_id", "document_id",
                            name="uq_meeting_documents_meeting_document"),
    )
    op.create_index("ix_meeting_documents_meeting_id", "meeting_documents",
                    ["meeting_id"], if_not_exists=True)
    op.create_index("ix_meeting_documents_document_id", "meeting_documents",
                    ["document_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("meeting_documents")
    op.drop_table("interaction_notes")
    op.drop_table("documents")
    op.drop_table("meetings")
    op.drop_table("university_products")
    op.drop_table("university_programs")
    op.drop_table("students")
