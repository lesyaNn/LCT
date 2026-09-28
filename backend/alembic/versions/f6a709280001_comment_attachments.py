"""Link existing workflow attachments to comments.

Revision ID: f6a709280001
"""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "f6a709280001"
down_revision: str | Sequence[str] | None = "e5f607030001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workflow_attachments") as batch:
        batch.add_column(sa.Column("comment_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_workflow_attachments_comment_id_workflow_comments",
            "workflow_comments", ["comment_id"], ["id"], ondelete="SET NULL",
        )
        batch.create_index("ix_workflow_attachments_comment_id", ["comment_id"])


def downgrade() -> None:
    with op.batch_alter_table("workflow_attachments") as batch:
        batch.drop_index("ix_workflow_attachments_comment_id")
        batch.drop_constraint("fk_workflow_attachments_comment_id_workflow_comments", type_="foreignkey")
        batch.drop_column("comment_id")
