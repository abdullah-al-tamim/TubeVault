"""Keep archive visibility separate from upload and deduplication evidence."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"


def upgrade():
    if "history_hidden" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("upload_jobs")}:
        op.add_column("upload_jobs", sa.Column("history_hidden", sa.Boolean(), nullable=False, server_default="0"))


def downgrade():
    raise RuntimeError("Restore a verified database backup instead")
