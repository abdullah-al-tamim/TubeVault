from alembic import context
from tubevault.config import config
from tubevault.db import Database, Base
from pathlib import Path
database_path = Path(context.config.attributes.get("database_path", config.data_dir / "tubevault.db"))
database_path.parent.mkdir(parents=True, exist_ok=True)
db = Database(database_path)
with db.engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
