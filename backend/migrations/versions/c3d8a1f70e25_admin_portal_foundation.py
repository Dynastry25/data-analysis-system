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
    inspector = sa.inspect(op.get_bind())
    existing_users = {c["name"] for c in inspector.get_columns("users")}

    # A development database may already have been built by ``create_all()`` on
    # startup, which creates new tables but never alters existing ones. Adding a
    # column that is already there fails, so each one is checked.
    with op.batch_alter_table("users") as batch:
        if "system_role" not in existing_users:
            batch.add_column(sa.Column("system_role", sa.String(length=20), nullable=True))
        if "status" not in existing_users:
            batch.add_column(
                sa.Column("status", sa.String(length=20), nullable=False, server_default="active")
            )
        if "suspended_at" not in existing_users:
            batch.add_column(sa.Column("suspended_at", sa.DateTime(), nullable=True))
        if "suspended_reason" not in existing_users:
            batch.add_column(
                sa.Column("suspended_reason", sa.String(length=500), nullable=True)
            )
        if "last_active_at" not in existing_users:
            batch.add_column(sa.Column("last_active_at", sa.DateTime(), nullable=True))

    user_indexes = {i["name"] for i in inspector.get_indexes("users")}
    with op.batch_alter_table("users") as batch:
        if "ix_users_system_role" not in user_indexes:
            batch.create_index("ix_users_system_role", ["system_role"])
        if "ix_users_status" not in user_indexes:
            batch.create_index("ix_users_status", ["status"])

    existing_tables = set(inspector.get_table_names())
    if "audit_logs" in existing_tables:
        # Already present from ``create_all()``. Its shape comes from the same
        # model, so the columns and indexes are already correct; only the
        # indexes are verified here. A table that exists but was never stamped
        # is not evidence of a partial migration, so nothing is dropped.
        audit_indexes = {i["name"] for i in inspector.get_indexes("audit_logs")}
        for name, column in (
            ("ix_audit_logs_user_id", "user_id"),
            ("ix_audit_logs_organization_id", "organization_id"),
            ("ix_audit_logs_action", "action"),
            ("ix_audit_logs_resource", "resource"),
            ("ix_audit_logs_result", "result"),
            ("ix_audit_logs_created_at", "created_at"),
        ):
            if name not in audit_indexes:
                op.create_index(name, "audit_logs", [column])
    else:
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
                ["user_id"],
                ["users.id"],
                name="fk_audit_logs_user_id_users",
                ondelete="SET NULL",
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
    inspector = sa.inspect(op.get_bind())
    existing_users = {c["name"] for c in inspector.get_columns("users")}
    user_indexes = {i["name"] for i in inspector.get_indexes("users")}

    if "audit_logs" in set(inspector.get_table_names()):
        op.drop_table("audit_logs")

    with op.batch_alter_table("users") as batch:
        if "ix_users_status" in user_indexes:
            batch.drop_index("ix_users_status")
        if "ix_users_system_role" in user_indexes:
            batch.drop_index("ix_users_system_role")
        for column in (
            "last_active_at",
            "suspended_reason",
            "suspended_at",
            "status",
            "system_role",
        ):
            if column in existing_users:
                batch.drop_column(column)
