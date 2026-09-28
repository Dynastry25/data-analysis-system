"""admin portal foundation: platform roles, account status, audit log

Adds the storage an operations center needs before any admin screen can be
built honestly:

* ``users.system_role`` carries platform-wide authority, separate from the
  organization ladder, and is NULL for ordinary users;
* ``users.status`` allows an administrator to suspend an account without
  deleting it, so the ownership history stays intact;
* ``audit_logs`` records security-relevant actions, including attempts by
  people who are not authenticated.

The organization membership table is deliberately untouched: an org ``admin``
must not inherit any platform permission through this migration.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d8a1f70e25"
down_revision: Union[str, None] = "b6e1f0a9c743"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("system_role", sa.String(length=20), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active")
        )
        batch.add_column(sa.Column("suspended_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column("suspended_reason", sa.String(length=500), nullable=True)
        )
        batch.add_column(sa.Column("last_active_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_users_system_role", ["system_role"])
        batch.create_index("ix_users_status", ["status"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("actor_email", sa.String(length=150), nullable=True),
        sa.Column("action", sa.String(length=60), nullable=False),
        sa.Column("resource", sa.String(length=60), nullable=True),
        sa.Column("resource_id", sa.String(length=80), nullable=True),
        sa.Column(
            "result", sa.String(length=20), nullable=False, server_default="success"
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_audit_logs_user_id_users", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_audit_logs_organization_id_organizations",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_resource", "audit_logs", ["resource"])
    op.create_index("ix_audit_logs_result", "audit_logs", ["result"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_status")
        batch.drop_index("ix_users_system_role")
        batch.drop_column("last_active_at")
        batch.drop_column("suspended_reason")
        batch.drop_column("suspended_at")
        batch.drop_column("status")
        batch.drop_column("system_role")
