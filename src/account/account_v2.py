from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import os.path
import pendulum


class IBAccountType(Enum):
    """Interactive Brokers account types"""
    FUND_ADVISORY = "FUND ADVISORY"
    MANAGED = "MANAGED"
    TRADING = "TRADING"


class IBPlatform(Enum):
    """Interactive Brokers platform types"""
    TWS = "TWS"
    IBG = "IBG"


class IBAlgo(Enum):
    """Interactive Brokers algorithm types"""
    DARKICE = "DARKICE"
    EMPTY = ""  # Empty string for no algorithm


class ValidPorts(Enum):
    """Valid port numbers for IB connections"""
    IB_GATEWAY_LIVE = 4001
    IB_GATEWAY_PAPER = 4002
    TWS_LIVE = 7496
    TWS_PAPER = 7497


class AccountV2(BaseModel):
    """
    AccountV2 class using Pydantic v2 for better validation and type safety.
    Replaces the dataclass-based Account class with proper enums and validation.
    """
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    # Core account fields
    id: int = Field(description="Unique account identifier")
    alias: str = Field(description="Account alias/name")
    ib_type: IBAccountType = Field(description="Interactive Brokers account type")
    ib_algo: IBAlgo = Field(description="Interactive Brokers algorithm type", default=IBAlgo.EMPTY)
    ib_platform: IBPlatform = Field(description="Interactive Brokers platform")
    ib_port: int = Field(description="Interactive Brokers connection port")
    ib_client_id: int = Field(description="Interactive Brokers client ID")
    
    # Strategy configuration
    strategy_allocations: Dict[str, float] = Field(
        description="Strategy allocations as {strategy_id: allocation} with allocation between 0 and 1"
    )
    strategy_security_types: Dict[str, List[str]] = Field(
        description="Strategy security types as {strategy_id: [primary_instrument, secondary_instrument]}"
    )
    
    # Optional fields
    ignored_positions: List[Any] = Field(default_factory=list, description="List of ignored positions")
    parent_account: Optional[str] = Field(default=None, description="Parent account for managed accounts")
    log: Optional[Any] = Field(default=None, description="Logging object")
    directory: Optional[str] = Field(default=None, description="Account directory path")
    
    # Runtime tracking fields
    exit_results: List[Any] = Field(default_factory=list, description="Exit order results")
    entry_results: List[Any] = Field(default_factory=list, description="Entry order results")
    runtime_errors: List[Any] = Field(default_factory=list, description="Runtime errors")
    last_nav_write: Optional[Any] = Field(
        default=None, 
        description="Tracks the last time NAV was recorded for this account. None means no record."
    )
    
    # Internal state
    initial_nav_write_complete: bool = Field(default=False, description="Internal NAV write tracking")

    @field_validator('ib_port')
    @classmethod
    def validate_ib_port(cls, v: int) -> int:
        """Validate IB port number"""
        valid_ports = [port.value for port in ValidPorts]
        if v not in valid_ports and (v < 49152 or v > 65535):
            raise ValueError(
                f'INVALID PORT {v}. Port numbers must be:\n'
                f'4001 (IB Gateway Live)\n'
                f'4002 (IB Gateway Paper)\n'
                f'7496 (TWS Live)\n'
                f'7497 (TWS Paper)\n'
                f'or a number from 49152 to 65535.'
            )
        return v

    @field_validator('strategy_allocations')
    @classmethod
    def validate_strategy_allocations(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validate strategy allocations are between 0 and 1"""
        for strategy_id, allocation in v.items():
            if allocation < 0 or allocation > 1:
                raise ValueError(
                    f'INVALID PCT ALLOCATION ({allocation}) specified for strategy {strategy_id}. '
                    f'Allocation must be entered as a fraction between 0 and 1.'
                )
        return v

    @field_validator('strategy_security_types')
    @classmethod
    def validate_strategy_security_types(cls, v: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """Validate security types are valid IB security types"""
        # Import here to avoid circular imports
        from src.config.globals.trading import TGL
        
        for strategy_id, security_types in v.items():
            for sec_type in security_types:
                if sec_type and sec_type not in TGL.valid_ib_security_types:
                    raise ValueError(
                        f'INVALID SECURITY TYPES ({security_types}) specified for strategy {strategy_id}. '
                        f'Valid types are: {", ".join(TGL.valid_ib_security_types)}'
                    )
        return v

    @field_validator('directory')
    @classmethod
    def validate_directory(cls, v: Optional[str]) -> Optional[str]:
        """Validate directory exists if provided"""
        if v and not os.path.isdir(v):
            raise NotADirectoryError(f'INVALID DIRECTORY {v} specified in config file')
        return v

    @model_validator(mode='after')
    def validate_account_rules(self) -> 'AccountV2':
        """Validate account-specific business rules"""
        # FUND ADVISORY accounts must have client_id = 0
        if self.ib_type == IBAccountType.FUND_ADVISORY and self.ib_client_id != 0:
            raise ValueError(f'FUND ADVISORY ACCOUNT {self.alias} must have IB CLIENT ID = 0')
        
        # MANAGED accounts must have a parent account
        if self.ib_type == IBAccountType.MANAGED and not self.parent_account:
            raise ValueError(
                f'MANAGED ACCOUNT {self.alias} does not have PARENT FUND ADVISORY ACCOUNT specified in config file'
            )
        
        return self

    def __setstate__(self, state):
        """Handle unpickling - set object state and reset internal flags"""
        for k, v in state.items():
            if hasattr(self, k):
                setattr(self, k, v)
        
        # Reset internal state on unpickling
        self.initial_nav_write_complete = False

    def valid(self) -> bool:
        """
        Legacy validation method for backward compatibility.
        In Pydantic v2, validation happens automatically, but this method
        can be used for additional runtime checks if needed.
        """
        # All validation is now handled by Pydantic validators
        # This method is kept for backward compatibility
        return True

    def __str__(self) -> str:
        """String representation of the account"""
        return f"AccountV2(id={self.id}, alias='{self.alias}', type={self.ib_type.value})"

    def __repr__(self) -> str:
        """Detailed string representation"""
        return (f"AccountV2(id={self.id}, alias='{self.alias}', ib_type={self.ib_type.value}, "
                f"platform={self.ib_platform.value}, port={self.ib_port})") 