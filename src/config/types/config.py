from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from src.config.types import AlphaNumStr

class TradingMode(Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"

class Platform(Enum):
    TWS = "TWS"
    IBKR = "IBKR"

class StrategyDirection(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    # NEUTRAL = "NEUTRAL"

class InteractiveBrokersConfig(BaseModel):
    """
    This model encapsulates all the configuration for the Interactive Brokers API.
    These have one to one correspondece with fields relevant in the API.
    """
    Platform: Platform = Field(
        description="The platform for the IB API. Needs To Match The TWS Settings for account.",
        default=Platform.TWS
    )
    Port: int = Field(
        description="The port number for the IB API. Needs To Match The TWS Settings for account.",
        default=7497,
        gt=1024,
        lt=65535
    )
    ClientID: Optional[int] = Field(
        description="An optional client ID for the IB API.",
        default=None
    )
    TradingMode: TradingMode = Field(
        description="The trading mode for the IB API. Needs To Match The TWS Settings for account.",
        default=TradingMode.PAPER
    )
    

class AccountConfig(BaseModel):
    """
    This base model encapsulates all the account level configuration for the OMS.
    """
    AccountID: AlphaNumStr = Field(
        description="The account ID that wil execute the actual trades."
    )
    AccountAlias: AlphaNumStr = Field(
        description="The alias for the account. Not a 100% sure if this is optional."
    )
    ParentAccountID: Optional[AlphaNumStr] = Field(
        description="The parent account ID for the account. This is used to link the account to a parent account."
    )

class StrategyConfig(BaseModel):
    """
    This module will contain the configuration for the strategy.
    This includes things like the name, allocation, etc..
    The actual order strategy itself is container in separate order files.
    """
    StrategyId: AlphaNumStr = Field(
        description="The name of the strategy."
    )
    Allocation: float = Field(
        description="The allocation for the strategy. Must be more than % or less than 100 percent.",
        ge=0.0,
        le=100.0
    )
    Direction: StrategyDirection = Field(
        description="The direction of the strategy."
    )
    PrimarySecurity: AlphaNumStr = Field(
        description="The primary security for the strategy."
    )
    SecondarySecurity: Optional[AlphaNumStr] = Field(
        description="The secondary security for the strategy. Only used for some trading strategies."
    )
    