from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TCM_", extra="ignore")

    database_url: str = "postgresql+psycopg://tcm:tcm_dev_only@127.0.0.1:5432/tcm_platform"
    data_root: Path = Path("data")
    max_import_bytes: int = 100 * 1024 * 1024
    bootstrap_secret: SecretStr | None = None
    bootstrap_ttl_seconds: int = Field(default=300, ge=30, le=3600)
    session_ttl_seconds: int = Field(default=8 * 3600, ge=300, le=24 * 3600)
    local_allowed_origins: str = "http://127.0.0.1:5173,http://127.0.0.1:8000"
    secure_session_cookie: bool = False
    preview_corpus: Literal["none", "shanghanlun_taiyang_upper"] = "none"


settings = Settings()

