"""Persist cooperative queue controls across restarts."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"

def upgrade():
    # 0001 creates current metadata for a fresh installation.
    if "control_requested" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("upload_jobs")}:
        op.add_column("upload_jobs", sa.Column("control_requested", sa.String(), nullable=False, server_default=""))

def downgrade():
    raise RuntimeError("Restore a verified database backup instead")
