"""Demo dataset + read-only DB role for the `readonly_sql` MCP tool (Day 7).

`kb_articles` is deliberately separate from the operational tables created in
`0001_initial` (AGENTS.md section 10: tools must not expose internal schema).
The `ainative_readonly` role only ever gets `SELECT` on this one table, and
`mcp-server` connects to it via a dedicated `READONLY_SQL_DSN` distinct from
the application's read-write `POSTGRES_*` DSN.
"""

import os
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_readonly_sql_demo_dataset"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

READONLY_ROLE = os.environ.get("READONLY_SQL_DB_USER", "ainative_readonly")
READONLY_PASSWORD = os.environ.get("READONLY_SQL_DB_PASSWORD", "ainative_readonly")


def upgrade() -> None:
    op.create_table(
        "kb_articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("published_year", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_kb_articles_category", "kb_articles", ["category"])

    kb_articles = sa.table(
        "kb_articles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("title", sa.String),
        sa.column("category", sa.String),
        sa.column("summary", sa.Text),
        sa.column("published_year", sa.Integer),
    )
    op.bulk_insert(
        kb_articles,
        [
            {
                "id": uuid.uuid4(),
                "title": "Dapr Workflow Durable Execution",
                "category": "dapr",
                "summary": (
                    "Dapr Workflow checkpoints every activity result to state storage so a "
                    "task can resume from the last completed step after a worker restart."
                ),
                "published_year": 2024,
            },
            {
                "id": uuid.uuid4(),
                "title": "LangGraph State Machines",
                "category": "langgraph",
                "summary": (
                    "LangGraph models agent workflows as a graph of nodes and conditional "
                    "edges over a shared, checkpointable state object."
                ),
                "published_year": 2024,
            },
            {
                "id": uuid.uuid4(),
                "title": "CrewAI Role-Based Agent Teams",
                "category": "crewai",
                "summary": (
                    "CrewAI organizes agents by role, goal, and backstory, then coordinates "
                    "them through a Crew that executes a sequence of Tasks."
                ),
                "published_year": 2024,
            },
            {
                "id": uuid.uuid4(),
                "title": "Model Context Protocol Tool Discovery",
                "category": "mcp",
                "summary": (
                    "MCP servers expose tools with a JSON schema so clients can discover "
                    "and call them dynamically at runtime without hardcoding tool contracts."
                ),
                "published_year": 2025,
            },
            {
                "id": uuid.uuid4(),
                "title": "OpenTelemetry Distributed Tracing",
                "category": "observability",
                "summary": (
                    "OpenTelemetry instruments a call chain with spans that can be exported "
                    "to backends such as Jaeger for end-to-end latency analysis."
                ),
                "published_year": 2023,
            },
        ],
    )

    # `IF NOT EXISTS` on `CREATE ROLE` needs a DO block: Postgres has no
    # `CREATE ROLE IF NOT EXISTS` clause. Re-running this migration (e.g. in
    # CI against a fresh DB every time) must stay idempotent.
    op.execute(
        sa.text(
            """
            DO $do$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :role_name) THEN
                    EXECUTE format(
                        'CREATE ROLE %I LOGIN PASSWORD %L',
                        :role_name,
                        :password
                    );
                END IF;
            END
            $do$;
            """
        ).bindparams(
            sa.bindparam("role_name", READONLY_ROLE),
            sa.bindparam("password", READONLY_PASSWORD),
        )
    )
    op.execute(
        sa.text(
            """
            DO $do$
            BEGIN
                EXECUTE format(
                    'GRANT CONNECT ON DATABASE %I TO %I',
                    current_database(),
                    :role_name
                );
                EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', :role_name);
                EXECUTE format('GRANT SELECT ON kb_articles TO %I', :role_name);
                EXECUTE format(
                    'REVOKE ALL ON tasks, task_steps, task_messages, tool_calls, '
                    'audit_events, user_preferences FROM %I',
                    :role_name
                );
            END
            $do$;
            """
        ).bindparams(sa.bindparam("role_name", READONLY_ROLE))
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $do$
            BEGIN
                EXECUTE format('REVOKE ALL ON kb_articles FROM %I', :role_name);
                EXECUTE format('REVOKE USAGE ON SCHEMA public FROM %I', :role_name);
            END
            $do$;
            """
        ).bindparams(sa.bindparam("role_name", READONLY_ROLE))
    )
    op.drop_table("kb_articles")
