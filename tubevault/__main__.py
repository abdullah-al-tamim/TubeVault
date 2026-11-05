import uvicorn
from filelock import FileLock
from alembic import command
from alembic.config import Config as AlembicConfig
from .config import config


def main():
    config.data_dir.mkdir(parents=True, exist_ok=True)
    with FileLock(str(config.data_dir / "tubevault.lock"), timeout=0):
        command.upgrade(AlembicConfig("alembic.ini"), "head")
        from .api import create_app
        uvicorn.run(create_app(), host=config.host, port=config.port, access_log=False)


if __name__ == "__main__":
    main()
