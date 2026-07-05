"""Add idempotency_key to tool_calls for safe resume/retry persistence."""

import sqlalchemy as sa
from alembic import op

revision = "0003_tool_calls_idempotency_key"
down_revision = "0002_readonly_sql_demo_dataset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tool_calls", sa.Column("idempotency_key", sa.String(length=256), nullable=True))
    op.execute("UPDATE tool_calls SET idempotency_key = id::text WHERE idempotency_key IS NULL")
    op.alter_column("tool_calls", "idempotency_key", nullable=False)
    op.create_unique_constraint("uq_tool_calls_idempotency_key", "tool_calls", ["idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_tool_calls_idempotency_key", "tool_calls", type_="unique")
    op.drop_column("tool_calls", "idempotency_key")
