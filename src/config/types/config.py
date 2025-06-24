from pydantic import BaseModel, Field, NonNegativeFloat, field_validator, model_validator, ConfigDict, ValidationError
from typing import Optional, Any
from enum import Enum
from src.config.types.general import AlphaNumStr, AlphaNumDashStr
from src.config.types.trading import SecurityType, IBAlgo, SUPPORTED_SECURITY_TYPES, SUPPORTED_ALGOS
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
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    platform: Platform = Field(
        description="The platform for the IB API. Needs To Match The TWS Settings for account.",
        default=Platform.TWS
    )
    port: int = Field(
        description="The port number for the IB API. Needs To Match The TWS Settings for account.",
        default=7497,
        gt=1024,
        lt=65535
    )
    client_id: Optional[int] = Field(
        description="An optional client ID for the IB API.",
        default=None
    )
    trading_mode: TradingMode = Field(
        description="The trading mode for the IB API. Needs To Match The TWS Settings for account.",
        default=TradingMode.PAPER
    )

    @field_validator('platform', mode='before')
    @classmethod
    def validate_platform(cls, value) -> Platform:
        """Validate and convert platform string to Platform enum with custom error message"""
        if isinstance(value, Platform):
            return value
        
        if isinstance(value, str):
            value = value.strip().upper()
            try:
                return Platform(value)
            except ValueError:
                valid_platforms = [p.value for p in Platform]
                raise ValueError(f"Invalid platform '{value}'. Must be one of: {', '.join(valid_platforms)}")
        
        raise ValueError(f"Platform must be a string, got {type(value).__name__}")

    @field_validator('trading_mode', mode='before')
    @classmethod
    def validate_trading_mode(cls, value) -> TradingMode:
        """Validate and convert trading mode string to TradingMode enum with custom error message"""
        if isinstance(value, TradingMode):
            return value
        
        if isinstance(value, str):
            value = value.strip().upper()
            try:
                return TradingMode(value)
            except ValueError:
                valid_modes = [m.value for m in TradingMode]
                raise ValueError(f"Invalid trading mode '{value}'. Must be one of: {', '.join(valid_modes)}")
        
        raise ValueError(f"Trading mode must be a string, got {type(value).__name__}")

class AccountConfig(BaseModel):
    """
    This base model encapsulates all the account level configuration for the OMS.
    """
    AccountID: AlphaNumStr = Field(
        description="The account ID that wil execute the actual trades."
    )
    AccountAlias: AlphaNumDashStr = Field(
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
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    Account: AlphaNumStr = Field(
        description="The account ID that will execute this strategy."
    )
    StrategyId: AlphaNumStr = Field(
        description="The name of the strategy."
    )
    Direction: StrategyDirection = Field(
        description="The direction of the strategy."
    )
    Allocation: float = Field(
        description="The allocation for the strategy. Must be more than 0% or less than 100 percent.",
        ge=0.0,
        le=100.0
    )
    MaxShortMargin: Optional[float] = Field(
        description="Maximum short margin allowed for this strategy.",
        default=None,
        ge=0.0
    )
    MaxShortFeeRate: Optional[float] = Field(
        description="Maximum short fee rate for this strategy.",
        default=None,
        ge=0.0
    )
    PrimarySecurity: SecurityType = Field(
        description="The primary security for the strategy."
    )
    SecondarySecurity: Optional[SecurityType] = Field(
        description="The secondary security for the strategy. Only used for some trading strategies.",
        default=None
    )
    IBAlgo: Optional[IBAlgo] = Field(
        description="The IB algorithm to use for order execution.",
        default=None
    )
    OrderTime: Optional[pendulum.DateTime] = Field(
        description="The time when orders for this strategy should be processed.",
        default=None
    )

    @field_validator('Allocation', mode='before')
    @classmethod
    def validate_allocation(cls, value) -> float:
        """Convert percentage string to float and validate"""
        if isinstance(value, str):
            # Remove % sign and convert to float
            value = value.replace('%', '').strip()
            try:
                value = float(value)
            except ValueError:
                raise ValueError(f"Invalid allocation value: {value}. Must be a number between 0 and 100")
        
        if not isinstance(value, (int, float)):
            raise ValueError(f"Allocation must be a number, got {type(value).__name__}")
        
        # Excel always stores percentages as decimals (0.25 = 25%), so always multiply by 100
        value = value * 100
        
        if value < 0 or value > 100:
            raise ValueError(f"Allocation must be between 0 and 100, got {value}")
        
        return float(value)

    @field_validator('MaxShortMargin', 'MaxShortFeeRate', mode='before')
    @classmethod
    def validate_optional_float(cls, value) -> Optional[float]:
        """Convert empty strings to None and validate float values"""
        if value is None or value == '' or str(value).strip() == '':
            return None
        
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                raise ValueError(f"Invalid value: {value}. Must be a number")
        
        if not isinstance(value, (int, float)):
            raise ValueError(f"Value must be a number, got {type(value).__name__}")
        
        if value < 0:
            raise ValueError(f"Value must be non-negative, got {value}")
        
        return float(value)

    @field_validator('OrderTime', mode='before')
    @classmethod
    def validate_order_time(cls, value) -> Optional[pendulum.DateTime]:
        """Convert time string to pendulum DateTime - requires timezone information"""
        if value is None or value == '' or str(value).strip() == '':
            return None
        
        if isinstance(value, str):
            try:
                # Parse time strings like "09:00:00 US/Eastern"
                if ' ' in value:
                    time_part, timezone_part = value.rsplit(' ', 1)
                    # Parse the time part
                    dt = pendulum.parse(time_part, tz=timezone_part)
                else:
                    # No timezone provided - this is an error
                    raise ValueError(f"Time must include timezone information. Expected format: 'HH:MM:SS Timezone' (e.g., '09:00:00 US/Eastern')")
                return dt
            except Exception as e:
                if "Time must include timezone" in str(e):
                    raise e
                raise ValueError(f"Invalid time format: {value}. Expected format: 'HH:MM:SS Timezone' (e.g., '09:00:00 US/Eastern')")
        
        return value

    @field_validator('PrimarySecurity', 'SecondarySecurity', mode='before')
    @classmethod
    def validate_security_type(cls, value) -> Optional[SecurityType]:
        """Convert string to SecurityType enum and validate against supported types"""
        if value is None or value == '' or str(value).strip() == '':
            return None
        
        if isinstance(value, str):
            value = value.strip().upper()
            try:
                security_type = SecurityType(value)
                # Check if this security type is supported
                if security_type not in SUPPORTED_SECURITY_TYPES:
                    supported_types = [st.value for st in SUPPORTED_SECURITY_TYPES]
                    raise ValueError(f"Security type '{value}' is not supported. Supported types are: {', '.join(supported_types)}")
                return security_type
            except ValueError as e:
                if "is not supported" in str(e):
                    raise e
                valid_types = [st.value for st in SecurityType]
                raise ValueError(f"Invalid security type '{value}'. Must be one of: {', '.join(valid_types)}")
        
        if isinstance(value, SecurityType):
            # Check if this security type is supported
            if value not in SUPPORTED_SECURITY_TYPES:
                supported_types = [st.value for st in SUPPORTED_SECURITY_TYPES]
                raise ValueError(f"Security type '{value.value}' is not supported. Supported types are: {', '.join(supported_types)}")
            return value
        
        raise ValueError(f"Security type must be a string, got {type(value).__name__}")

    @field_validator('IBAlgo', mode='before')
    @classmethod
    def validate_ib_algo(cls, value) -> Optional[IBAlgo]:
        """Convert string to IBAlgo enum and validate against supported algorithms"""
        if value is None or value == '' or str(value).strip() == '':
            return None
        
        if isinstance(value, str):
            value = value.strip().upper()
            try:
                ib_algo = IBAlgo(value)
                # Check if this algorithm is supported
                if ib_algo not in SUPPORTED_ALGOS:
                    supported_algos = [algo.value for algo in SUPPORTED_ALGOS]
                    raise ValueError(f"IB algorithm '{value}' is not supported. Supported algorithms are: {', '.join(supported_algos)}")
                return ib_algo
            except ValueError as e:
                if "is not supported" in str(e):
                    raise e
                valid_algos = [algo.value for algo in IBAlgo]
                raise ValueError(f"Invalid IB algorithm '{value}'. Must be one of: {', '.join(valid_algos)}")
        
        if isinstance(value, IBAlgo):
            # Check if this algorithm is supported
            if value not in SUPPORTED_ALGOS:
                supported_algos = [algo.value for algo in SUPPORTED_ALGOS]
                raise ValueError(f"IB algorithm '{value.value}' is not supported. Supported algorithms are: {', '.join(supported_algos)}")
            return value
        
        raise ValueError(f"IB algorithm must be a string, got {type(value).__name__}")

    @field_validator('Direction', mode='before')
    @classmethod
    def validate_direction(cls, value) -> StrategyDirection:
        """Convert string to StrategyDirection enum with case-insensitive handling"""
        if isinstance(value, StrategyDirection):
            return value
        
        if isinstance(value, str):
            value = value.strip().upper()
            try:
                return StrategyDirection(value)
            except ValueError:
                valid_directions = [d.value for d in StrategyDirection]
                raise ValueError(f"Invalid direction '{value}'. Must be one of: {', '.join(valid_directions)}")
        
        raise ValueError(f"Direction must be a string, got {type(value).__name__}")

class ReportingConfig(BaseModel):
    """
    This model encapsulates all the configuration for report timing settings.
    These times determine when various reports and files are generated during the trading day.
    The sequence must be: RTOutputFileTime -> OrderTime -> DailyReportTime.
    Note that these should also be cross validated against the market open and close times of the market you are trading in.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
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

class IgnoredPositionConfig(BaseModel):
    """
    This model encapsulates the configuration for positions that should be ignored by the OMS.
    These positions are typically pre-existing or managed outside the system but need to be tracked
    to ensure accurate position calculations and risk management.
    """
    AccountID: AlphaNumStr = Field(
        description="The account ID where the ignored position exists."
    )
    ContractID: int = Field(
        description="The contract ID of the ignored position.",
        gt=0
    )
    Symbol: AlphaNumStr = Field(
        description="The trading symbol of the ignored position."
    )
    IgnoredPositionSize: float = Field(
        description="The size of the position to be ignored. Can be positive for long positions or negative for short positions."
    )
    

class FundsConfig(BaseModel):
    """
    This model encapsulates the configuration for tracking account funds movements.
    This includes deposits and withdrawals for each account, with their respective dates.
    Used for accurate capital tracking and performance calculations.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    Account: AlphaNumStr = Field(
        description="The account ID where the funds movement occurred."
    )
    Date: pendulum.DateTime = Field(
        description="The date when the funds movement occurred."
    )
    Deposit: NonNegativeFloat = Field(
        description="The amount deposited into the account. Must be non-negative.",
        default=0.0
    )
    Withdrawal: NonNegativeFloat = Field(
        description="The amount withdrawn from the account. Must be non-negative.",
        default=0.0
    )

    @field_validator('Withdrawal', 'Deposit', mode='before')
    @classmethod
    def validate_amounts(cls, value: float) -> float:
        """Ensure amounts are rounded to 2 decimal places"""
        return round(value, 2)

    @field_validator('Date', mode='before')
    @classmethod
    def validate_date(cls, value: pendulum.DateTime) -> pendulum.DateTime:
        """Ensure date is not in the future"""
        # TODO: We should have a specific way of handling the "current time" of the machine, we should force the config to be explicit on all time zones.
        if value > pendulum.now():
            raise ValueError("Date cannot be in the future")
        return value

    @model_validator(mode='after')
    def validate_transaction(self) -> 'FundsConfig':
        """Ensure at least one of Deposit or Withdrawal is non-zero, but not both"""
        if self.Deposit > 0 and self.Withdrawal > 0:
            raise ValueError("Cannot have both deposit and withdrawal in the same transaction")
        if self.Deposit == 0 and self.Withdrawal == 0:
            raise ValueError("Must specify either a deposit or withdrawal amount")
        return self

# Custom error message handler following Pydantic documentation pattern
def convert_validation_errors(e: ValidationError) -> list[dict[str, Any]]:
    """
    Convert Pydantic validation errors to use custom error messages.
    Based on the Pydantic documentation pattern for customizing error messages.
    """
    custom_messages = {
        'string_pattern_mismatch': {
            'accountalias': 'Account alias should only contain letters, numbers, hyphens (-), or underscores (_)',
            'accountid': 'Account ID should only contain letters, numbers, hyphens (-), or underscores (_)',
        }
    }
    
    new_errors = []
    for error in e.errors():
        error_type = error.get('type', '')
        field_name = error.get('loc', [''])[-1] if error.get('loc') else ''
        
        # Check if we have a custom message for this error type and field
        if error_type in custom_messages:
            field_lower = field_name.lower()
            for field_pattern, custom_message in custom_messages[error_type].items():
                if field_pattern in field_lower:
                    error['msg'] = custom_message
                    break
        
        new_errors.append(error)
    
    return new_errors

def get_suggested_value_for_field(field_name: str, model_class: type[BaseModel] = None) -> Optional[str]:
    """
    Get suggested value for a field based on its default value in the Pydantic model.
    
    Args:
        field_name: Name of the field that failed validation
        model_class: The Pydantic model class to check for defaults (defaults to InteractiveBrokersConfig)
        
    Returns:
        Suggested value as string, or None if no default is available
    """
    if model_class is None:
        model_class = InteractiveBrokersConfig
    
    try:
        field_info = model_class.model_fields.get(field_name)
        if field_info and field_info.default is not None:
            default_value = field_info.default
            # Handle enum values
            if hasattr(default_value, 'value'):
                return str(default_value.value)
            return str(default_value)
    except (KeyError, AttributeError):
        pass
    
    return None

def handle_validation_error(e: ValidationError, account_id: str, account_alias: str) -> list[dict[str, Any]]:
    """
    Handle validation errors and return structured error information.
    
    Args:
        e: Pydantic ValidationError
        account_id: Account ID for error reporting
        account_alias: Account alias for error reporting
        
    Returns:
        List of error dictionaries with structured information
    """
    # Use custom error handler to get improved error messages
    converted_errors = convert_validation_errors(e)
    
    structured_errors = []
    for error in converted_errors:
        field_name = error['loc'][-1] if error['loc'] else 'Unknown field'
        value = error.get('input', 'Unknown value')
        message = error.get('msg', 'Validation error')
        
        structured_errors.append({
            'account_id': account_id,
            'account_alias': account_alias,
            'field_name': field_name,
            'value': str(value),
            'error_message': message,
            'suggested_value': get_suggested_value_for_field(field_name)
        })
    
    return structured_errors
    