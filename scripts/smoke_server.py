"""Local browser-test server using real services and an isolated data directory."""
import os
import secrets
from pathlib import Path
import uvicorn
from tubevault.config import Config
from tubevault.db import Database, Base
from tubevault.api import create_app

root = Path('data/smoke').resolve()
root.mkdir(parents=True, exist_ok=True)
password_path = root / 'password.txt'
password_path.write_text(secrets.token_urlsafe(32), encoding='utf-8')
config = Config(data_dir=root, password=password_path.read_text(), port=8766,
                origins='http://127.0.0.1:8766,http://localhost:8766')
db = Database(root / 'smoke.db')
Base.metadata.create_all(db.engine)
uvicorn.run(create_app(config, db), host='127.0.0.1', port=8766, access_log=False)
