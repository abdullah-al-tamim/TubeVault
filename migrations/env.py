from alembic import context
from tubevault.config import config
from tubevault.db import Database, Base
config.data_dir.mkdir(parents=True, exist_ok=True)
db = Database(config.data_dir / "tubevault.db")
with db.engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
