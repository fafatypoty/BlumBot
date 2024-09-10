from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, AliasPath, field_validator, AliasChoices


class AuthResponse(BaseModel):
    access_token: str = Field(None, validation_alias=AliasChoices(AliasPath("token", "access"), AliasPath("access")))
    refresh_token: str = Field(None, validation_alias=AliasChoices(AliasPath("token", "refresh"), AliasPath("refresh")))
    user_id: str = Field(None, validation_alias=AliasPath("token", "user", "id", "id"))
    username: str = Field(None, validation_alias=AliasPath("token", "user", "username"))


class Farming(BaseModel):
    start: int = Field(..., alias="startTime")
    end: int = Field(..., alias="endTime")
    earn_per_second: float = Field(..., alias="earningsRate")
    balance: float = Field(..., alias="balance")


class BalanceResponse(BaseModel):
    balance: float = Field(..., alias="availableBalance")
    game_passes: int = Field(..., alias="playPasses")
    now_timestamp: int = Field(..., alias="timestamp")
    farming: Optional["Farming"] = None

    @field_validator('balance')
    def convert_balance_to_float(cls, v):
        try:
            return float(v)
        except ValueError as e:
            raise ValueError(f"Unable to convert balance to float: {e}")


class ClaimFarmingResponse(BaseModel):
    balance: float = Field(..., alias="availableBalance")
    games_played: int = Field(..., alias="playPasses")
    now_timestamp: int = Field(..., alias="timestamp")


class StartGameResponse(BaseModel):
    game_id: str = Field(..., alias="gameId")


class Task(BaseModel):
    id: str
    kind: Optional["Kind"] = None
    type: "Type"
    status: "Status"
    subSection: Optional[str] = None
    iconFileKey: str
    bannerFileKey: Optional[str] = None
    title: str
    productName: Optional[str] = None
    description: Optional[str] = None 
    reward: str
    socialSubscription: Optional["SocialSubscription"] = None
    isHidden: bool
    isDisclaimerRequired: bool

    class SocialSubscription(BaseModel):
        openInTelegram: bool
        url: str

    class Kind(str, Enum):
        ongoing: str = "ONGOING"
        initial: str = "INITIAL"

    class Status(str, Enum):
        finished: str = "FINISHED"
        not_started: str = "NOT_STARTED"
        started: str = "STARTED"
        ready_for_claim: str = "READY_FOR_CLAIM"

    class Type(str, Enum):
        social_subscription: str = "SOCIAL_SUBSCRIPTION"
        progress_target: str = "PROGRESS_TARGET"
        application_launch: str = "APPLICATION_LAUNCH"
        wallet_connection: str = "WALLET_CONNECTION"
        internal: str = "INTERNAL"
