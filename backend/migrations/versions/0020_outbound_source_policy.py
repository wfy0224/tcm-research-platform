"""Default existing sources to local-only outbound policy.

Revision ID: 0020_outbound_source_policy
Revises: 0019_local_session_api
"""

import sqlalchemy as sa
from alembic import op

revision = "0020_outbound_source_policy"
down_revision = "0019_local_session_api"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_document", sa.Column(
        "data_level", sa.String(30), nullable=False, server_default="RESTRICTED"
    ), schema="source")
    op.add_column("source_document", sa.Column(
        "outbound_authorized", sa.Boolean(), nullable=False, server_default=sa.false()
    ), schema="source")
    op.create_check_constraint("ck_source_data_level", "source_document",
                               "data_level IN ('PUBLIC', 'RESTRICTED', 'SENSITIVE')",
                               schema="source")
    op.alter_column("model_invocation", "task_id", nullable=True, schema="research")
    op.add_column("model_invocation", sa.Column("policy_hash", sa.String(64)),
                  schema="research")
    op.add_column("model_invocation", sa.Column("policy_version", sa.String(50)),
                  schema="research")
    op.add_column("model_invocation", sa.Column("transport_retry_count", sa.Integer()),
                  schema="research")


def downgrade() -> None:
    granted = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM source.source_document "
        "WHERE outbound_authorized OR data_level <> 'RESTRICTED'"
    )).scalar_one()
    if granted:
        raise RuntimeError("cannot downgrade while source outbound grants or labels exist")
    remaining = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM research.model_invocation WHERE task_id IS NULL"
    )).scalar_one()
    if remaining:
        raise RuntimeError("cannot downgrade while taskless outbound audit records exist")
    op.drop_column("model_invocation", "transport_retry_count", schema="research")
    op.drop_column("model_invocation", "policy_version", schema="research")
    op.drop_column("model_invocation", "policy_hash", schema="research")
    op.alter_column("model_invocation", "task_id", nullable=False, schema="research")
    op.drop_constraint("ck_source_data_level", "source_document", schema="source")
    op.drop_column("source_document", "outbound_authorized", schema="source")
    op.drop_column("source_document", "data_level", schema="source")
