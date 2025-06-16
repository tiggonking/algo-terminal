from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

class TradingMode(Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"

class Platform(Enum):
    TWS = "TWS"
    IBKR = "IBKR"

class InteractiveBrokersConfig(BaseModel):
    """
    This model encapsulates all the configuration for the Interactive Brokers API.
    These have one to one correspondece with fields relevant in the API.
    """
    Platform: Platform 
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
    

class OMSAccountLevelConfig(BaseModel):
    """
    This base model encapsulates all the account level configuration for the OMS.
    """
    AccountID: str
    AccountAlias: str
    ParentAccountID: Optional[str] = None