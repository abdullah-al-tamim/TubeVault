"""Consistent SQLite backup. Does not copy secrets or footage."""
import sqlite3
from datetime import datetime, timezone
from tubevault.config import config

target = config.data_dir / 'backups'
target.mkdir(parents=True, exist_ok=True)
destination = target / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.db')
with sqlite3.connect(config.data_dir / 'tubevault.db') as source, sqlite3.connect(destination) as output:
    source.backup(output)
print(f'Database backup created: {destination}')
