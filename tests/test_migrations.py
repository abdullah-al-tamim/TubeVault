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


def test_upgrade_existing_job_table_preserves_rows(tmp_path):
    import sqlite3
    path=tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE upload_jobs (id TEXT PRIMARY KEY, state TEXT)")
        conn.execute("INSERT INTO upload_jobs VALUES ('existing','PAUSED')")
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        conn.execute("INSERT INTO alembic_version VALUES ('0001')")
    config=Config('alembic.ini')
    config.attributes['database_path']=path
    command.upgrade(config,'head')
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT id,state,control_requested FROM upload_jobs').fetchone()==('existing','PAUSED','')
