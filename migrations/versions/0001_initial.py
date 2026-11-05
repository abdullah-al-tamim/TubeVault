"""Initial normalized archive schema."""
from alembic import op
from tubevault.db import Base
revision = "0001"
down_revision = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    raise RuntimeError("Destructive downgrade disabled: restore a verified database backup instead")
