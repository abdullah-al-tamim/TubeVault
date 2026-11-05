from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TUBEVAULT_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    host: str = "127.0.0.1"
    port: int = 8765
    password: str = ""
    client_secret: Path = Path("data/client_secret.json")
    allowed_hosts: str = "localhost,127.0.0.1"
    origins: str = "http://127.0.0.1:8765,http://localhost:8765"
    secure_cookie: bool = False


config = Config()
