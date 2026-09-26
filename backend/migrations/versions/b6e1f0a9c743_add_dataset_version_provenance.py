"""add dataset version provenance"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e1f0a9c743"
down_revision: Union[str, None] = "7c3d9f2a41b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("dataset_versions") as batch:
        batch.add_column(sa.Column("created_by", sa.Integer(), nullable=True))
        batch.create_index("ix_dataset_versions_created_by", ["created_by"])
        batch.create_foreign_key(
            "fk_dataset_versions_created_by_users",
            "users",
            ["created_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("analysis_runs") as batch:
        batch.add_column(
            sa.Column("dataset_version_id", sa.Integer(), nullable=True)
        )
        batch.create_index(
            "ix_analysis_runs_dataset_version_id", ["dataset_version_id"]
        )
        batch.create_foreign_key(
            "fk_analysis_runs_dataset_version_id_versions",
            "dataset_versions",
            ["dataset_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("charts") as batch:
        batch.add_column(
            sa.Column("dataset_version_id", sa.Integer(), nullable=True)
        )
        batch.create_index("ix_charts_dataset_version_id", ["dataset_version_id"])
        batch.create_foreign_key(
            "fk_charts_dataset_version_id_versions",
            "dataset_versions",
            ["dataset_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("exported_reports") as batch:
        batch.add_column(
            sa.Column("dataset_version_id", sa.Integer(), nullable=True)
        )
        batch.create_index(
            "ix_exported_reports_dataset_version_id", ["dataset_version_id"]
        )
        batch.create_foreign_key(
            "fk_exported_reports_dataset_version_id_versions",
            "dataset_versions",
            ["dataset_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.execute(
        """
        INSERT INTO dataset_versions (
            dataset_id,
            version,
            parent_version,
            storage_path,
            file_format,
            row_count,
            column_count,
            is_current,
            label,
            created_by,
            created_at
        )
        SELECT
            datasets.id,
            1,
            NULL,
            datasets.storage_path,
            'source',
            datasets.row_count,
            datasets.column_count,
            1,
            'original upload',
            datasets.user_id,
            CURRENT_TIMESTAMP
        FROM datasets
        WHERE EXISTS (
            SELECT 1
            FROM charts
            WHERE charts.dataset_id = datasets.id
        )
          AND NOT EXISTS (
            SELECT 1
            FROM dataset_versions
            WHERE dataset_versions.dataset_id = datasets.id
        )
        """
    )
    op.execute(
        """
        UPDATE dataset_versions
        SET created_by = (
            SELECT datasets.user_id
            FROM datasets
            WHERE datasets.id = dataset_versions.dataset_id
        )
        WHERE version = 1
        """
    )
    op.execute(
        """
        UPDATE analysis_runs
        SET dataset_version_id = (
            SELECT dataset_versions.id
            FROM dataset_versions
            WHERE dataset_versions.dataset_id = analysis_runs.dataset_id
              AND dataset_versions.version = analysis_runs.dataset_version
        )
        WHERE EXISTS (
            SELECT 1
            FROM dataset_versions
            WHERE dataset_versions.dataset_id = analysis_runs.dataset_id
              AND dataset_versions.version = analysis_runs.dataset_version
        )
        """
    )
    op.execute(
        """
        UPDATE charts
        SET dataset_version_id = (
            SELECT dataset_versions.id
            FROM dataset_versions
            WHERE dataset_versions.dataset_id = charts.dataset_id
              AND dataset_versions.version = 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM dataset_versions
            WHERE dataset_versions.dataset_id = charts.dataset_id
              AND dataset_versions.version = 1
        )
        """
    )
    op.execute(
        "UPDATE exported_reports SET error_message = NULL "
        "WHERE error_message IS NOT NULL"
    )


def downgrade() -> None:
    referenced_source_versions = op.get_bind().execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM dataset_versions
            WHERE file_format = 'source'
              AND (
                EXISTS (
                    SELECT 1
                    FROM dataset_operations
                    WHERE dataset_operations.dataset_version_id = dataset_versions.id
                       OR (
                            dataset_operations.dataset_id = dataset_versions.dataset_id
                            AND dataset_operations.source_version = dataset_versions.version
                       )
                )
                OR EXISTS (
                    SELECT 1
                    FROM exported_reports
                    WHERE exported_reports.dataset_version_id = dataset_versions.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM analysis_runs
                    WHERE analysis_runs.dataset_version_id = dataset_versions.id
                )
              )
            """
        )
    ).scalar_one()
    if referenced_source_versions:
        raise RuntimeError(
            "Cannot downgrade provenance migration after source versions have been used"
        )

    op.execute(
        """
        UPDATE charts
        SET dataset_version_id = NULL
        WHERE dataset_version_id IN (
            SELECT id
            FROM dataset_versions
            WHERE file_format = 'source'
        )
        """
    )
    op.execute("DELETE FROM dataset_versions WHERE file_format = 'source'")

    with op.batch_alter_table("exported_reports") as batch:
        batch.drop_index("ix_exported_reports_dataset_version_id")
        batch.drop_constraint(
            "fk_exported_reports_dataset_version_id_versions", type_="foreignkey"
        )
        batch.drop_column("dataset_version_id")

    with op.batch_alter_table("charts") as batch:
        batch.drop_index("ix_charts_dataset_version_id")
        batch.drop_constraint(
            "fk_charts_dataset_version_id_versions", type_="foreignkey"
        )
        batch.drop_column("dataset_version_id")

    with op.batch_alter_table("analysis_runs") as batch:
        batch.drop_index("ix_analysis_runs_dataset_version_id")
        batch.drop_constraint(
            "fk_analysis_runs_dataset_version_id_versions", type_="foreignkey"
        )
        batch.drop_column("dataset_version_id")

    with op.batch_alter_table("dataset_versions") as batch:
        batch.drop_index("ix_dataset_versions_created_by")
        batch.drop_constraint(
            "fk_dataset_versions_created_by_users", type_="foreignkey"
        )
        batch.drop_column("created_by")
