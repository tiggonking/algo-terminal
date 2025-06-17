from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from src.config.types import AlphaNumStr
import pendulum

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
    

class ReportingConfig(BaseModel):
    """
    This model encapsulates all the configuration for report timing settings.
    These times determine when various reports and files are generated during the trading day.
    The sequence must be: RTOutputFileTime -> OrderTime -> DailyReportTime.
    Note that these should also be cross validated against the market open and close times of the market you are trading in.
    """
    RTOutputFileTime: pendulum.DateTime = Field(
        description="The time when RT output files should be generated. Must be the earliest time."
    )
    OrderTime: pendulum.DateTime = Field(
        description="The time when orders should be processed. Must be after RTOutputFileTime but before DailyReportTime."
    )
    DailyReportTime: pendulum.DateTime = Field(
        description="The time when daily reports should be generated. Must be the latest time."
    )

    @field_validator('OrderTime', mode='before')
    @classmethod
    def validate_order_time(cls, value: pendulum.DateTime, info) -> pendulum.DateTime:
        rt_output_time = info.data.get('RTOutputFileTime')
        if rt_output_time and value <= rt_output_time:
            raise ValueError("OrderTime must be after RTOutputFileTime")
        return value

    @field_validator('DailyReportTime', mode='before')
    @classmethod
    def validate_daily_report_time(cls, value: pendulum.DateTime, info) -> pendulum.DateTime:
        order_time = info.data.get('OrderTime')
        if order_time and value <= order_time:
            raise ValueError("DailyReportTime must be after OrderTime")
        return value
    
