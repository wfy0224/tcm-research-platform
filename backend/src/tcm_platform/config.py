from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TCM_", extra="ignore")

    database_url: str = "postgresql+psycopg://tcm:tcm_dev_only@127.0.0.1:5432/tcm_platform"
    data_root: Path = Path("data")
    max_import_bytes: int = 100 * 1024 * 1024


settings = Settings()

