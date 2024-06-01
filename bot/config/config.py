from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    IS_DEV_MODE: bool = False

    REFERRAL_CODES: Optional[list[str]] = None

    USE_PROXY_FROM_FILE: bool = False


settings = Settings()
