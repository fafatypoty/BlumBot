from typing import List

from pydantic import BaseModel, field_validator


class TelegramWebData(BaseModel):
    tgWebAppData: str
    tgWebAppVersion: List[str]
    tgWebAppPlatform: List[str]
    tgWebAppSideMenuUnavail: List[str]

    @field_validator("tgWebAppData", mode="before")
    def convert_tg_data(cls, v) -> str:
        return v[0]
