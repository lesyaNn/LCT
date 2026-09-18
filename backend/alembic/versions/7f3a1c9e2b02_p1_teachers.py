"""P1 migration 2/3: teachers (P1-01-02).

teachers, teacher_qualifications, teacher_certificates, teacher_programs.

Revision ID: 7f3a1c9e2b02. Depends on 7f3a1c9e2b01.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f3a1c9e2b02"
down_revision: str | Sequence[str] | None = "7f3a1c9e2b01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teachers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("email", sa.String(512), nullable=False),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("position", sa.String(256), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_teachers_university_id_universities", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_teachers"),
        sa.UniqueConstraint("email", name="uq_teachers_email"),
    )
    op.create_index("ix_teachers_university_id", "teachers", ["university_id"],
                    if_not_exists=True)

    op.create_table(
        "teacher_qualifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("qualification_name", sa.String(512), nullable=False),
        sa.Column("obtained_at", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("document_ref", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["teachers.id"],
            name="fk_teacher_qualifications_teacher_id_teachers",
            ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_qualifications"),
    )
    op.create_index("ix_teacher_qualifications_teacher_id",
                    "teacher_qualifications", ["teacher_id"], if_not_exists=True)

    op.create_table(
        "teacher_certificates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("certificate_name", sa.String(512), nullable=False),
        sa.Column("issued_by", sa.String(512), nullable=False, server_default=""),
        sa.Column("issued_at", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("program_id", sa.Uuid(), nullable=True),
        sa.Column("document_ref", sa.String(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["teachers.id"],
            name="fk_teacher_certificates_teacher_id_teachers",
            ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["program_id"], ["it_programs.id"],
            name="fk_teacher_certificates_program_id_it_programs",
            ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_certificates"),
    )
    op.create_index("ix_teacher_certificates_teacher_id", "teacher_certificates",
                    ["teacher_id"], if_not_exists=True)
    op.create_index("ix_teacher_certificates_expires_at", "teacher_certificates",
                    ["expires_at"], if_not_exists=True)
    op.create_index("ix_teacher_certificates_mandatory", "teacher_certificates",
                    ["is_mandatory", "expires_at"], if_not_exists=True)

    op.create_table(
        "teacher_programs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("teacher_id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("can_teach", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("assigned_at", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["teacher_id"], ["teachers.id"],
            name="fk_teacher_programs_teacher_id_teachers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["program_id"], ["it_programs.id"],
            name="fk_teacher_programs_program_id_it_programs",
            ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_teacher_programs"),
        sa.UniqueConstraint("teacher_id", "program_id",
                            name="uq_teacher_programs_teacher_program"),
    )
    op.create_index("ix_teacher_programs_teacher_id", "teacher_programs",
                    ["teacher_id"], if_not_exists=True)
    op.create_index("ix_teacher_programs_program_id", "teacher_programs",
                    ["program_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("teacher_programs")
    op.drop_table("teacher_certificates")
    op.drop_table("teacher_qualifications")
    op.drop_table("teachers")
