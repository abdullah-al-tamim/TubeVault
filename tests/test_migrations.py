from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from tubevault.db import Database, Base


def test_initial_migration_creates_complete_schema(tmp_path, monkeypatch):
    from tubevault.config import config
    monkeypatch.setattr(config, 'data_dir', tmp_path)
    command.upgrade(Config('alembic.ini'), 'head')
    db = Database(tmp_path / 'tubevault.db')
    assert set(Base.metadata.tables).issubset(set(inspect(db.engine).get_table_names()))
    command.upgrade(Config('alembic.ini'), 'head')
    db.engine.dispose()
