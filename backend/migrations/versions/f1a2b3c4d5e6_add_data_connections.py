"""add data connections and their sync history

The strategy's "connect an organisational database" claim had nothing
behind it: ingest was files and scraping only. These two tables add
the ingest path -- Postgres, MySQL, or a REST endpoint returning JSON
-- as an alternative way a dataset arrives, not as a second kind of
data. A sync pulls a frame and writes it as a new immutable dataset
version through the same ``create_version`` the cleaning studio uses,
so the version history, the lineage view, the remediation and the
analysis cache all work unchanged.

``data_connections.secret`` holds the credential encrypted with a key
derived from SECRET_KEY (see ``app.services.connection_secrets``), and
it is never returned by any endpoint. ``config`` holds everything
else: host/port/database/table for a database, URL and headers for
REST.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e5f2a8c31d74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("secret", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="never_run",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("dataset_id", sa.Integer(), nullable=True),
        sa.Column("sync_every_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_data_connections_user_id", "data_connections", ["user_id"])
    op.create_index("ix_data_connections_project_id", "data_connections", ["project_id"])
    op.create_index("ix_data_connections_dataset_id", "data_connections", ["dataset_id"])

    op.create_table(
        "data_connection_syncs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("column_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dataset_version", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["connection_id"], ["data_connections.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_data_connection_syncs_connection_id",
        "data_connection_syncs",
        ["connection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_connection_syncs_connection_id", table_name="data_connection_syncs"
    )
    op.drop_table("data_connection_syncs")
    op.drop_index("ix_data_connections_dataset_id", table_name="data_connections")
    op.drop_index("ix_data_connections_project_id", table_name="data_connections")
    op.drop_index("ix_data_connections_user_id", table_name="data_connections")
    op.drop_table("data_connections")
