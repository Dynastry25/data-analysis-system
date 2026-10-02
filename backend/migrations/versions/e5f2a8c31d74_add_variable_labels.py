"""add variable and value labels to dataset columns

Stata (.dta) and SPSS (.sav) files describe their own columns: a variable label
naming the question the column answers, and value labels mapping stored codes to
the words the author wrote (1 = Male, 2 = Female). The platform was reading those
files with the codes intact and throwing the labels away, so a labelled survey
arrived as a column called ``gender`` containing 1 and 2.

Both columns are nullable. A NULL label means the file did not carry one, which
is the honest answer and is different from an empty string or an empty object.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f2a8c31d74"
down_revision: Union[str, None] = "c3d8a1f70e25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("dataset_columns") as batch:
        batch.add_column(sa.Column("variable_label", sa.String(500), nullable=True))
        # sa.JSON maps to JSONB on PostgreSQL and TEXT on SQLite, so the same
        # migration serves both the dev database and production.
        batch.add_column(sa.Column("value_labels", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("dataset_columns") as batch:
        batch.drop_column("value_labels")
        batch.drop_column("variable_label")
