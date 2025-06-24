import os
import sys
# Get the directory containing this file
current_dir = os.path.dirname(os.path.abspath(__file__))
# Navigate up to the project root (Algo_Terminal directory)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.config.types.config import AccountConfig, InteractiveBrokersConfig
from pydantic import EmailStr, BaseModel, Field, ValidationError, ConfigDict
from enum import Enum
from typing import Dict, List, Optional, Any, Type, TypeVar
from abc import ABC, abstractmethod
import pandas as pd
from typing import Dict, List, Optional, Any
from src.config.types.config import (
    AccountConfig, 
    InteractiveBrokersConfig, 
    StrategyConfig, 
    IgnoredPositionConfig, 
    FundsConfig,
    Platform,
    TradingMode,
    convert_validation_errors,
    get_suggested_value_for_field,
    handle_validation_error
)
from src.config.types.general import AlphaNumStr
import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import print as rprint

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set up Rich console for pretty printing
console = Console()

# Type variable for generic tab data
T = TypeVar('T', bound='BaseTabData')

class BaseTabData(BaseModel, ABC):
    """Abstract base class for all tab data types with validation error handling"""
    
    @classmethod
    def handle_validation_errors(cls, e: ValidationError, context_info: dict[str, str]) -> list[dict[str, Any]]:
        """
        Handle validation errors using the config module's error handler.
        
        Args:
            e: Pydantic ValidationError
            context_info: Dictionary with context information (e.g., account_id, account_alias)
            
        Returns:
            List of structured error dictionaries
        """
        account_id = context_info.get('account_id', 'Unknown')
        account_alias = context_info.get('account_alias', 'No alias')
        
        return handle_validation_error(e, account_id, account_alias)

class AccountTab(BaseModel):
    """
    This class represents the data found in the account tab of
    config file V2.
    """
    AccountConfig: AccountConfig
    InteractiveBrokersConfig: InteractiveBrokersConfig
    send_from_email: EmailStr


class RequiredTabs(Enum):
    """Enum for required Excel tabs"""
    ACCOUNTS = "Accounts"
    STRATEGIES = "Strategies"
    IGNORED_POSITIONS = "Ignored Positions"
    FUNDS = "Funds"


class TabValidationResult(BaseModel):
    """Pydantic model for tab validation results"""
    tab_name: str
    exists: bool
    error_message: Optional[str] = None


class ExcelValidationResult(BaseModel):
    """Pydantic model for overall Excel validation results"""
    file_path: str
    required_tabs: List[RequiredTabs]
    validation_results: List[TabValidationResult]
    is_valid: bool = Field(default=False)
    missing_tabs: List[str] = Field(default_factory=list)
    
    def __init__(self, **data):
        super().__init__(**data)
        self.missing_tabs = [
            result.tab_name for result in self.validation_results 
            if not result.exists
        ]
        self.is_valid = len(self.missing_tabs) == 0


class AccountValidationError(BaseModel):
    """Model for account validation errors"""
    account_id: str = Field(description="Account ID that failed validation")
    account_alias: Optional[str] = Field(default=None, description="Account alias if available")
    field_name: str = Field(description="Name of the field that failed validation")
    value: str = Field(description="Invalid value that was provided")
    error_message: str = Field(description="Human-readable error message")
    suggested_value: Optional[str] = Field(default=None, description="Suggested correct value if applicable")


class AccountValidationResult(BaseModel):
    """Model for account validation results"""
    is_valid: bool = Field(description="Whether the account is valid")
    account_entry: Optional['AccountTabEntry'] = Field(default=None, description="Valid account entry if validation passed")
    errors: List[AccountValidationError] = Field(default_factory=list, description="List of validation errors")
    
    def add_error(self, account_id: str, account_alias: Optional[str], field_name: str, value: str, error_message: str, suggested_value: Optional[str] = None) -> None:
        """Add a validation error"""
        self.errors.append(AccountValidationError(
            account_id=account_id,
            account_alias=account_alias,
            field_name=field_name,
            value=value,
            error_message=error_message,
            suggested_value=suggested_value
        ))
        self.is_valid = False


class AccountTabEntry(BaseTabData):
    """Pydantic model for a single account entry in the accounts tab"""
    account_config: AccountConfig = Field(description="Account configuration using existing AccountConfig type")
    ib_config: InteractiveBrokersConfig = Field(description="IB configuration using existing InteractiveBrokersConfig type")
    account_type: str = Field(description="The type of account")
    email_address: Optional[EmailStr] = Field(default=None, description="Email address for reporting")
    
    @classmethod
    def from_excel_data(cls, account_data: Dict[str, str]) -> Optional['AccountTabEntry']:
        """Create AccountTabEntry from Excel data using existing config types"""
        try:
            # Create AccountConfig
            account_config = AccountConfig(
                AccountID=account_data.get('Account ID', ''),
                AccountAlias=account_data.get('Alias', ''),
                ParentAccountID=account_data.get('Parent Account') if account_data.get('Parent Account') else None
            )
            
            # Create InteractiveBrokersConfig
            platform_str = account_data.get('IB Platform', 'TWS')
            platform_map = {
                'TWS': Platform.TWS,
                'IBKR': Platform.IBKR
            }
            
            ib_port = 7497  # Default
            if 'IB Port' in account_data and account_data['IB Port']:
                try:
                    ib_port = int(account_data['IB Port'])
                except ValueError:
                    pass
            
            ib_client_id = None
            if 'IB Client #' in account_data and account_data['IB Client #']:
                try:
                    ib_client_id = int(account_data['IB Client #'])
                except ValueError:
                    pass
            
            ib_config = InteractiveBrokersConfig(
                platform=platform_map.get(platform_str, Platform.TWS),
                port=ib_port,
                client_id=ib_client_id
            )
            
            # Let EmailStr handle email validation
            email_val = account_data.get('Email Address for Reporting', '').strip()
            email_address = email_val if email_val else None
            logger.debug(f"Email parsing for account {account_config.AccountID}: raw='{email_val}', processed='{email_address}'")
            
            return cls(
                account_config=account_config,
                ib_config=ib_config,
                account_type=account_data.get('Account Type', ''),
                email_address=email_address
            )
            
        except ValidationError as e:
            print(f"Validation error creating AccountTabEntry: {e}")
            return None

    @classmethod
    def create_from_excel_data(cls, account_data: Dict[str, str]) -> AccountValidationResult:
        """
        Create AccountTabEntry from Excel data using Pydantic's native validation.
        
        Args:
            account_data: Dictionary of field names to values from Excel
            
        Returns:
            AccountValidationResult with validation status and errors
        """
        result = AccountValidationResult(is_valid=True)
        
        # Get basic account info for error reporting
        account_id = account_data.get('Account ID', 'Unknown')
        account_alias = account_data.get('Alias', 'No alias')
        
        # Validate required fields
        if not account_id or account_id.strip() == '':
            result.add_error(
                account_id=account_id,
                account_alias=account_alias,
                field_name='Account ID',
                value=account_id,
                error_message="Account ID is required and cannot be empty"
            )
            return result
        
        # Create the account entry using Pydantic's native validation
        try:
            # Let Pydantic handle all validation through the composed types
            account_config = AccountConfig(
                AccountID=account_id,
                AccountAlias=account_alias,
                ParentAccountID=account_data.get('Parent Account') if account_data.get('Parent Account') else None
            )
            
            # Let InteractiveBrokersConfig handle all its own validation (platform, port ranges, etc.)
            ib_config = InteractiveBrokersConfig(
                platform=account_data.get('IB Platform') if account_data.get('IB Platform') else None,
                port=account_data.get('IB Port') if account_data.get('IB Port') else None,
                client_id=account_data.get('IB Client #') if account_data.get('IB Client #') else None
            )
            
            # Let EmailStr handle email validation
            email_val = account_data.get('Email Address for Reporting', '').strip()
            email_address = email_val if email_val else None
            logger.debug(f"Email parsing for account {account_id}: raw='{email_val}', processed='{email_address}'")
            
            result.account_entry = cls(
                account_config=account_config,
                ib_config=ib_config,
                account_type=account_data.get('Account Type', ''),
                email_address=email_address
            )
            
        except ValidationError as e:
            # Use the abstract validation error handler
            context_info = {'account_id': account_id, 'account_alias': account_alias}
            structured_errors = AccountTabEntry.handle_validation_errors(e, context_info)
            
            for error_info in structured_errors:
                result.add_error(
                    account_id=error_info['account_id'],
                    account_alias=error_info['account_alias'],
                    field_name=error_info['field_name'],
                    value=error_info['value'],
                    error_message=error_info['error_message'],
                    suggested_value=error_info['suggested_value']
                )
        
        return result


class AccountTabData(BaseModel):
    """Pydantic model for the entire accounts tab data"""
    accounts: List[AccountTabEntry] = Field(description="List of account entries")
    
    @property
    def total_accounts(self) -> int:
        """Total number of accounts"""
        return len(self.accounts)
    
    def get_account_configs(self) -> List[AccountConfig]:
        """Get list of AccountConfig objects"""
        return [account.account_config for account in self.accounts]
    
    def get_ib_configs(self) -> List[InteractiveBrokersConfig]:
        """Get list of InteractiveBrokersConfig objects"""
        return [account.ib_config for account in self.accounts]


# New structured configuration models
class AccountsConfig(BaseTabData):
    """Configuration for accounts with indexed access by ID and alias"""
    accounts_by_id: Dict[str, AccountTabEntry] = Field(default_factory=dict, description="Accounts indexed by Account ID")
    accounts_by_alias: Dict[str, AccountTabEntry] = Field(default_factory=dict, description="Accounts indexed by Account Alias")
    validation_errors: List[AccountValidationError] = Field(default_factory=list, description="Validation errors for rejected accounts")
    
    def __init__(self, accounts: List[AccountTabEntry], validation_errors: List[AccountValidationError] = None, **kwargs):
        accounts_by_id = {}
        accounts_by_alias = {}
        
        for account in accounts:
            # Index by Account ID
            if account.account_config.AccountID:
                accounts_by_id[account.account_config.AccountID] = account
            
            # Index by Account Alias
            if account.account_config.AccountAlias:
                accounts_by_alias[account.account_config.AccountAlias] = account
        
        super().__init__(
            accounts_by_id=accounts_by_id,
            accounts_by_alias=accounts_by_alias,
            validation_errors=validation_errors or [],
            **kwargs
        )
    
    def get_account_by_id(self, account_id: str) -> Optional[AccountTabEntry]:
        """Get account by Account ID"""
        return self.accounts_by_id.get(account_id)
    
    def get_account_by_alias(self, alias: str) -> Optional[AccountTabEntry]:
        """Get account by Account Alias"""
        return self.accounts_by_alias.get(alias)
    
    def get_all_accounts(self) -> List[AccountTabEntry]:
        """Get all accounts as a list"""
        return list(self.accounts_by_id.values())
    
    @property
    def total_accounts(self) -> int:
        """Total number of accounts"""
        return len(self.accounts_by_id)
    
    @property
    def rejected_accounts(self) -> int:
        """Number of accounts rejected due to validation errors"""
        return len(self.validation_errors)
    
    def get_validation_summary(self) -> str:
        """Get a summary of validation results"""
        if not self.validation_errors:
            return f"All {self.total_accounts} accounts validated successfully."
        
        summary = f"Validation completed: {self.total_accounts} accounts accepted, {self.rejected_accounts} accounts rejected.\n"
        summary += "Rejected accounts:\n"
        
        for error in self.validation_errors:
            summary += f"  - Account {error.account_id} ({error.account_alias or 'No alias'}): {error.error_message}\n"
        
        return summary


class StrategiesConfig(BaseTabData):
    """Configuration for strategies tab"""
    strategies: List[StrategyConfig] = Field(default_factory=list, description="List of strategy configurations")
    
    def __init__(self, strategies: List[StrategyConfig] = None, **kwargs):
        super().__init__(strategies=strategies or [], **kwargs)


class IgnoredPositionsConfig(BaseTabData):
    """Configuration for ignored positions tab"""
    ignored_positions: List[IgnoredPositionConfig] = Field(default_factory=list, description="List of ignored position configurations")
    
    def __init__(self, ignored_positions: List[IgnoredPositionConfig] = None, **kwargs):
        super().__init__(ignored_positions=ignored_positions or [], **kwargs)


class FundsConfig(BaseTabData):
    """Configuration for funds tab"""
    funds: List[FundsConfig] = Field(default_factory=list, description="List of fund configurations")
    
    def __init__(self, funds: List[FundsConfig] = None, **kwargs):
        super().__init__(funds=funds or [], **kwargs)


class ExcelConfigV2(BaseModel):
    """Main configuration class for Excel V2 with dependency injection support"""
    file_path: str = Field(description="Path to the Excel configuration file")
    accounts: AccountsConfig = Field(description="Accounts configuration")
    strategies: Optional[StrategiesConfig] = Field(default=None, description="Strategies configuration")
    ignored_positions: Optional[IgnoredPositionsConfig] = Field(default=None, description="Ignored positions configuration")
    funds: Optional[FundsConfig] = Field(default=None, description="Funds configuration")
    custom_tabs: Dict[str, BaseTabData] = Field(default_factory=dict, description="Custom tabs added through dependency injection")
    
    def get_account_by_id(self, account_id: str) -> Optional[AccountTabEntry]:
        """Get account by Account ID"""
        return self.accounts.get_account_by_id(account_id)
    
    def get_account_by_alias(self, alias: str) -> Optional[AccountTabEntry]:
        """Get account by Account Alias"""
        return self.accounts.get_account_by_alias(alias)
    
    def add_custom_tab(self, tab_name: str, tab_data: BaseTabData) -> None:
        """Add a custom tab through dependency injection"""
        self.custom_tabs[tab_name] = tab_data
    
    def get_custom_tab(self, tab_name: str) -> Optional[BaseTabData]:
        """Get a custom tab by name"""
        return self.custom_tabs.get(tab_name)
    
    @property
    def total_accounts(self) -> int:
        """Total number of accounts"""
        return self.accounts.total_accounts


class TabParser(ABC):
    """Abstract base class for tab parsers"""
    
    @abstractmethod
    def parse_tab(self, excel_file_path: str, tab_name: str) -> BaseTabData:
        """Parse a specific tab from the Excel file"""
        pass


class AccountsTabParser(TabParser):
    """Parser for the accounts tab with validation"""
    
    def parse_tab(self, excel_file_path: str, tab_name: str) -> AccountsConfig:
        """Parse the accounts tab and return AccountsConfig with validation"""
        parser = SheetV2Parser()
        return parser.parse_accounts_tab(excel_file_path)


class ConfigParserFactory:
    """Factory for creating configuration parsers with dependency injection"""
    
    def __init__(self):
        self.tab_parsers: Dict[str, Type[TabParser]] = {
            RequiredTabs.ACCOUNTS.value: AccountsTabParser,
            # Add more parsers as they are implemented
        }
    
    def register_tab_parser(self, tab_name: str, parser_class: Type[TabParser]) -> None:
        """Register a custom tab parser"""
        self.tab_parsers[tab_name] = parser_class
    
    def create_config(self, excel_file_path: str, required_tabs: List[str] = None) -> ExcelConfigV2:
        """Create a complete configuration from Excel file"""
        if required_tabs is None:
            required_tabs = [tab.value for tab in RequiredTabs]
        
        # Validate tabs first
        parser = SheetV2Parser()
        validation_result = parser.validate_excel_tabs(excel_file_path)
        
        if not validation_result.is_valid:
            raise ValueError(f"Excel file validation failed: {validation_result.missing_tabs}")
        
        # Parse accounts (required)
        accounts_parser = self.tab_parsers.get(RequiredTabs.ACCOUNTS.value)
        if not accounts_parser:
            raise ValueError(f"No parser registered for {RequiredTabs.ACCOUNTS.value}")
        
        accounts_config = accounts_parser().parse_tab(excel_file_path, RequiredTabs.ACCOUNTS.value)
        
        # Initialize config with accounts
        config = ExcelConfigV2(
            file_path=excel_file_path,
            accounts=accounts_config
        )
        
        # Parse other tabs if parsers are available
        for tab_name in required_tabs:
            if tab_name == RequiredTabs.ACCOUNTS.value:
                continue  # Already parsed
            
            parser_class = self.tab_parsers.get(tab_name)
            if parser_class:
                try:
                    tab_data = parser_class().parse_tab(excel_file_path, tab_name)
                    # Set the appropriate attribute based on tab name
                    if tab_name == RequiredTabs.STRATEGIES.value:
                        config.strategies = tab_data
                    elif tab_name == RequiredTabs.IGNORED_POSITIONS.value:
                        config.ignored_positions = tab_data
                    elif tab_name == RequiredTabs.FUNDS.value:
                        config.funds = tab_data
                    else:
                        # Custom tab
                        config.add_custom_tab(tab_name, tab_data)
                except Exception as e:
                    print(f"Warning: Failed to parse tab '{tab_name}': {e}")
        
        return config


class SheetV2Parser:
    """
    Parser for Excel configuration files V2 with tab validation and account parsing.
    Uses existing config types from config.types.config.
    """
    
    def __init__(self):
        self.required_tabs = [tab.value for tab in RequiredTabs]
    
    def validate_excel_tabs(self, excel_file_path: str) -> ExcelValidationResult:
        """
        Validate that all required tabs exist in the Excel file.
        
        Args:
            excel_file_path: Path to the Excel file
            
        Returns:
            ExcelValidationResult with validation status
        """
        try:
            # Read all sheet names from the Excel file
            excel_file = pd.ExcelFile(excel_file_path)
            available_sheets = excel_file.sheet_names
            
            validation_results = []
            
            for tab_enum in RequiredTabs:
                tab_name = tab_enum.value
                exists = tab_name in available_sheets
                
                validation_result = TabValidationResult(
                    tab_name=tab_name,
                    exists=exists,
                    error_message=None if exists else f"Tab '{tab_name}' not found in Excel file"
                )
                validation_results.append(validation_result)
            
            return ExcelValidationResult(
                file_path=excel_file_path,
                required_tabs=[tab for tab in RequiredTabs],
                validation_results=validation_results
            )
            
        except Exception as e:
            # If we can't even read the Excel file, all tabs are missing
            validation_results = [
                TabValidationResult(
                    tab_name=tab.value,
                    exists=False,
                    error_message=f"Cannot read Excel file: {str(e)}"
                )
                for tab in RequiredTabs
            ]
            
            return ExcelValidationResult(
                file_path=excel_file_path,
                required_tabs=[tab for tab in RequiredTabs],
                validation_results=validation_results
            )
    
    def parse_accounts_tab(self, excel_file_path: str) -> AccountsConfig:
        """
        Parse the accounts tab with validation and error reporting.
        
        Returns:
            AccountsConfig with valid accounts and validation errors
        """
        try:
            # Read the accounts tab, always treat the first row as data
            df = pd.read_excel(excel_file_path, sheet_name=RequiredTabs.ACCOUNTS.value, header=None)
            logger.debug("First 10 rows of accounts tab:")
            logger.debug(f"\n{df.head(10)}")
            logger.debug(f"First row: {df.iloc[0].tolist()}")

            # Parse the multi-column layout with validation
            valid_accounts, validation_errors = self._parse_multi_column_accounts(df)

            # Create accounts config
            accounts_config = AccountsConfig(accounts=valid_accounts, validation_errors=validation_errors)
            
            # Pretty print validation results
            pretty_print_validation_results(accounts_config)

            return accounts_config

        except Exception as e:
            logger.error(f"Error parsing accounts tab: {str(e)}")
            raise ValueError(f"Error parsing accounts tab: {str(e)}")
    
    def _parse_multi_column_accounts(self, df: pd.DataFrame) -> tuple[List[AccountTabEntry], List[AccountValidationError]]:
        """
        Parse the multi-column accounts layout with validation and error reporting.
        
        Returns:
            Tuple of (valid_accounts, validation_errors)
        """
        valid_accounts = []
        validation_errors = []

        # Forward fill the first column to handle merged/blank cells
        df_ffill = df.copy()
        df_ffill.iloc[:, 0] = df_ffill.iloc[:, 0].ffill()

        # Get the first row (Account ID row) to determine how many accounts we have
        account_id_row = df_ffill.iloc[0]  # First row contains Account IDs

        # Find all non-null account IDs (skip the first column which is the field name)
        account_columns = []
        for i, value in enumerate(account_id_row[1:], start=1):  # Start from index 1 to skip field name column
            if pd.notna(value) and str(value).strip():
                account_columns.append(i)

        # Parse each account column
        for col_idx in account_columns:
            field_values = {}
            for row_idx, row in df_ffill.iterrows():
                field_name = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
                value = row.iloc[col_idx] if col_idx < len(row) else None
                
                # Debug logging for email field specifically
                if field_name == 'Email Address for Reporting':
                    logger.debug(f"Row {row_idx}, Col {col_idx}: field_name='{field_name}', raw_value={value}, type={type(value)}, notna={pd.notna(value)}")
                
                # Only set the field value if it's not already set (take first non-empty value)
                if field_name and field_name not in field_values:
                    if pd.notna(value) and str(value).strip():
                        field_values[field_name] = str(value).strip()
                    else:
                        field_values[field_name] = ""
            
            # Debug logging for field parsing
            logger.debug(f"Parsed fields for column {col_idx}: {field_values}")
            logger.debug(f"Email field value: '{field_values.get('Email Address for Reporting', 'NOT_FOUND')}'")
            
            # Skip accounts without ID
            if 'Account ID' not in field_values or not field_values['Account ID']:
                continue
            
            # Validate and create account entry
            validation_result = AccountTabEntry.create_from_excel_data(field_values)
            
            if validation_result.is_valid and validation_result.account_entry:
                valid_accounts.append(validation_result.account_entry)
            else:
                validation_errors.extend(validation_result.errors)
        
        return valid_accounts, validation_errors

    def parse_excel_file(self, excel_file_path: str) -> Dict[str, Any]:
        """
        Complete Excel file parsing with validation and account parsing.
        
        Args:
            excel_file_path: Path to the Excel file
            
        Returns:
            Dictionary containing validation results and parsed data
        """
        # First validate the tabs
        validation_result = self.validate_excel_tabs(excel_file_path)
        
        result = {
            'validation': validation_result.model_dump(),
            'accounts_data': None,
            'status': 'success' if validation_result.is_valid else 'validation_failed'
        }
        
        # If validation passes, parse the accounts tab
        if validation_result.is_valid:
            try:
                accounts_data = self.parse_accounts_tab(excel_file_path)
                # Convert to dict and add the computed total_accounts
                accounts_dict = accounts_data.model_dump()
                accounts_dict['total_accounts'] = accounts_data.total_accounts
                result['accounts_data'] = accounts_dict
            except Exception as e:
                result['status'] = 'parsing_failed'
                result['error'] = str(e)
        
        return result


# Convenience functions for easy usage
def validate_excel_tabs(excel_file_path: str) -> ExcelValidationResult:
    """
    Convenience function to validate Excel tabs.
    
    Args:
        excel_file_path: Path to the Excel file
        
    Returns:
        ExcelValidationResult with validation status
    """
    parser = SheetV2Parser()
    return parser.validate_excel_tabs(excel_file_path)


def parse_accounts_from_excel(excel_file_path: str) -> AccountsConfig:
    """
    Convenience function to parse accounts from Excel with validation.
    
    Args:
        excel_file_path: Path to the Excel file
        
    Returns:
        AccountsConfig containing all account entries with validation errors
    """
    parser = SheetV2Parser()
    return parser.parse_accounts_tab(excel_file_path)


def parse_excel_config(excel_file_path: str) -> Dict[str, Any]:
    """
    Complete Excel configuration parsing.
    
    Args:
        excel_file_path: Path to the Excel file
        
    Returns:
        Dictionary containing validation results and parsed data
    """
    parser = SheetV2Parser()
    return parser.parse_excel_file(excel_file_path)


def create_structured_config(excel_file_path: str) -> ExcelConfigV2:
    """
    Create a structured configuration object with indexed account access.
    
    Args:
        excel_file_path: Path to the Excel file
        
    Returns:
        ExcelConfigV2 object with indexed account access
    """
    factory = ConfigParserFactory()
    return factory.create_config(excel_file_path)


def create_structured_config_with_validation(excel_file_path: str) -> ExcelConfigV2:
    """
    Create a structured configuration object with validation and error reporting.
    
    Args:
        excel_file_path: Path to the Excel file
        
    Returns:
        ExcelConfigV2 object with indexed account access and validation errors
    """
    factory = ConfigParserFactory()
    config = factory.create_config(excel_file_path)
    
    # Pretty print validation results
    pretty_print_validation_results(config.accounts)
    
    return config


def pretty_print_validation_results(accounts_config: 'AccountsConfig') -> None:
    """
    Pretty print validation results and account data using Rich.
    
    Args:
        accounts_config: The accounts configuration with validation results
    """
    # Create main panel
    if accounts_config.validation_errors:
        # Show validation errors
        error_table = Table(title="❌ Validation Errors", show_header=True, header_style="bold red")
        error_table.add_column("Account ID", style="cyan", no_wrap=True)
        error_table.add_column("Alias", style="cyan")
        error_table.add_column("Field", style="yellow")
        error_table.add_column("Value", style="red", no_wrap=True)
        error_table.add_column("Error Message", style="red")
        error_table.add_column("Suggested Value", style="green")
        
        for error in accounts_config.validation_errors:
            error_table.add_row(
                error.account_id,
                error.account_alias or "No alias",
                error.field_name,
                error.value,
                error.error_message,
                error.suggested_value or "N/A"
            )
        
        console.print(error_table)
        console.print()
    
    # Show valid accounts
    if accounts_config.total_accounts > 0:
        account_table = Table(title="✅ Valid Accounts", show_header=True, header_style="bold green")
        account_table.add_column("Account ID", style="cyan", no_wrap=True)
        account_table.add_column("Alias", style="cyan")
        account_table.add_column("Type", style="blue")
        account_table.add_column("Platform", style="magenta")
        account_table.add_column("Port", style="yellow")
        account_table.add_column("Email", style="green")
        
        for account in accounts_config.get_all_accounts():
            logger.debug(f"Account {account.account_config.AccountID} email: {account.email_address} (type: {type(account.email_address)})")
            account_table.add_row(
                account.account_config.AccountID,
                account.account_config.AccountAlias,
                account.account_type,
                account.ib_config.platform.value,
                str(account.ib_config.port),
                str(account.email_address) if account.email_address else "None"
            )
        
        console.print(account_table)
        console.print()
    
    # Show summary
    summary_text = f"""
    📊 Validation Summary:
    • Valid accounts: {accounts_config.total_accounts}
    • Rejected accounts: {accounts_config.rejected_accounts}
    • Total processed: {accounts_config.total_accounts + accounts_config.rejected_accounts}
    """
    
    if accounts_config.validation_errors:
        panel = Panel(summary_text, title="Validation Complete", border_style="red")
    else:
        panel = Panel(summary_text, title="Validation Complete", border_style="green")
    
    console.print(panel)


def pretty_print_account_data(account: 'AccountTabEntry') -> None:
    """
    Pretty print a single account's data.
    
    Args:
        account: The account entry to display
    """
    table = Table(title=f"Account: {account.account_config.AccountID}", show_header=True, header_style="bold cyan")
    table.add_column("Field", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    
    table.add_row("Account ID", account.account_config.AccountID)
    table.add_row("Alias", account.account_config.AccountAlias)
    table.add_row("Type", account.account_type)
    table.add_row("Parent Account", account.account_config.ParentAccountID or "None")
    table.add_row("Platform", account.ib_config.platform.value)
    table.add_row("Port", str(account.ib_config.port))
    table.add_row("Client ID", str(account.ib_config.client_id) if account.ib_config.client_id else "None")
    table.add_row("Email", account.email_address or "None")
    
    console.print(table)
    console.print()


if __name__ == "__main__":
    # Test parsing of config file
    test_file = os.path.join(project_root, "tests", "test_parser","test_files", "config_v2.xlsx")
    if os.path.exists(test_file):
        logger.info(f"Testing config file parsing with: {test_file}")
        
        # Test validation
        validation_result = validate_excel_tabs(test_file)
        logger.info(f"Excel file validation: {'✅ PASSED' if validation_result.is_valid else '❌ FAILED'}")
        
        # Test accounts parsing with pretty output
        logger.info("Parsing accounts from Excel file...")
        accounts_data = parse_accounts_from_excel(test_file)
        
        # Test new structured configuration
        logger.info("Creating structured configuration...")
        structured_config = create_structured_config(test_file)
        
        # Test account access by ID and alias
        logger.info("Testing account access methods...")
        for account in structured_config.accounts.get_all_accounts():
            account_id = account.account_config.AccountID
            account_alias = account.account_config.AccountAlias
            
            # Test access by ID
            account_by_id = structured_config.get_account_by_id(account_id)
            logger.debug(f"Account by ID '{account_id}': {account_by_id.account_config.AccountAlias if account_by_id else 'Not found'}")
            
            # Test access by alias
            account_by_alias = structured_config.get_account_by_alias(account_alias)
            logger.debug(f"Account by alias '{account_alias}': {account_by_alias.account_config.AccountID if account_by_alias else 'Not found'}")
        
        logger.info("✅ All tests completed successfully!")
        
    else:
        logger.error(f"Test file not found at: {test_file}")
        logger.info("Please create a test config file at this location to run tests")
