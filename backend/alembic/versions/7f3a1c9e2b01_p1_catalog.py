"""P1 migration 1/3 (base): catalog + core (P1-01-01).

universities, it_directions, it_programs, vendors, it_products, contracts,
licenses, responsibles, university_responsibles.

Revision ID: 7f3a1c9e2b01 (base of the P1 chain).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7f3a1c9e2b01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "universities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("city", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_universities"),
        sa.UniqueConstraint("name", name="uq_universities_name"),
    )
    op.create_index("ix_universities_name", "universities", ["name"],
                    if_not_exists=True)
    op.create_index("ix_universities_city", "universities", ["city"],
                    if_not_exists=True)

    op.create_table(
        "it_directions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_it_directions"),
        sa.UniqueConstraint("code", name="uq_it_directions_code"),
    )

    op.create_table(
        "it_programs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("direction_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=False,
                  server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["it_directions.id"],
            name="fk_it_programs_direction_id_it_directions", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_it_programs"),
    )
    op.create_index("ix_it_programs_direction_id", "it_programs",
                    ["direction_id"], if_not_exists=True)

    op.create_table(
        "vendors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_vendors"),
        sa.UniqueConstraint("name", name="uq_vendors_name"),
    )

    op.create_table(
        "it_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("version", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["vendor_id"], ["vendors.id"],
            name="fk_it_products_vendor_id_vendors", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_it_products"),
        sa.UniqueConstraint("vendor_id", "name", "version",
                            name="uq_it_products_vendor_name_version"),
    )
    op.create_index("ix_it_products_vendor_id", "it_products", ["vendor_id"],
                    if_not_exists=True)

    op.create_table(
        "contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("contract_number", sa.String(256), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("signed_at", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status_raw", sa.String(32), nullable=False,
                  server_default="signed"),
        sa.Column("transfer_status_raw", sa.String(32), nullable=False,
                  server_default="pending"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_contracts_university_id_universities", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["it_products.id"],
            name="fk_contracts_product_id_it_products", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_contracts"),
        sa.UniqueConstraint("contract_number", name="uq_contracts_contract_number"),
    )
    op.create_index("ix_contracts_university_id", "contracts", ["university_id"],
                    if_not_exists=True)
    op.create_index("ix_contracts_expires_at", "contracts", ["expires_at"],
                    if_not_exists=True)

    op.create_table(
        "licenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("license_number", sa.String(256), nullable=False),
        sa.Column("signed_at", sa.Date(), nullable=False),
        sa.Column("expires_at", sa.Date(), nullable=False),
        sa.Column("transfer_status_raw", sa.String(32), nullable=False,
                  server_default="pending"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_licenses_university_id_universities", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["product_id"], ["it_products.id"],
            name="fk_licenses_product_id_it_products", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contracts.id"],
            name="fk_licenses_contract_id_contracts", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_licenses"),
    )
    op.create_index("ix_licenses_university_id", "licenses", ["university_id"],
                    if_not_exists=True)
    op.create_index("ix_licenses_product_id", "licenses", ["product_id"],
                    if_not_exists=True)
    op.create_index("ix_licenses_expires_at", "licenses", ["expires_at"],
                    if_not_exists=True)
    op.create_index("ix_licenses_transfer_status_raw", "licenses",
                    ["transfer_status_raw"], if_not_exists=True)
    op.create_index("ix_licenses_univ_expires", "licenses",
                    ["university_id", "expires_at"], if_not_exists=True)

    op.create_table(
        "responsibles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(512), nullable=False),
        sa.Column("email", sa.String(512), nullable=False),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("role", sa.String(256), nullable=False, server_default=""),
        sa.Column("keycloak_sub", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_responsibles"),
        sa.UniqueConstraint("email", name="uq_responsibles_email"),
        sa.UniqueConstraint("keycloak_sub", name="uq_responsibles_keycloak_sub"),
    )

    op.create_table(
        "university_responsibles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("university_id", sa.Uuid(), nullable=False),
        sa.Column("responsible_id", sa.Uuid(), nullable=False),
        sa.Column("role_in_university", sa.String(64), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["university_id"], ["universities.id"],
            name="fk_university_responsibles_university_id_universities",
            ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["responsible_id"], ["responsibles.id"],
            name="fk_university_responsibles_responsible_id_responsibles",
            ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_university_responsibles"),
        sa.UniqueConstraint("university_id", "responsible_id",
                            name="uq_university_responsibles_uni_resp"),
    )
    op.create_index("ix_university_responsibles_university_id",
                    "university_responsibles", ["university_id"], if_not_exists=True)
    op.create_index("ix_university_responsibles_responsible_id",
                    "university_responsibles", ["responsible_id"], if_not_exists=True)


def downgrade() -> None:
    op.drop_table("university_responsibles")
    op.drop_table("responsibles")
    op.drop_table("licenses")
    op.drop_table("contracts")
    op.drop_table("it_products")
    op.drop_table("vendors")
    op.drop_table("it_programs")
    op.drop_table("it_directions")
    op.drop_table("universities")


_ = postgresql.JSONB
