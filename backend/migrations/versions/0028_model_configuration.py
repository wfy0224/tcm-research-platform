"""Persist model configuration in the database."""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0028_model_configuration"
down_revision = "0027_report_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("model_configuration", sa.Column("id", sa.Integer(), primary_key=True),
                    sa.Column("payload", JSONB(), nullable=False),
                    sa.CheckConstraint("id = 1"), schema="governance")


def downgrade() -> None:
    op.drop_table("model_configuration", schema="governance")
