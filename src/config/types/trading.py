from enum import Enum
from pydantic import BaseModel, ValidationError, BeforeValidator
from pydantic_core import ErrorDetails
from typing import List, Dict, Any, Annotated

# Start with enums that we know are available in the API.
class Exchange(Enum):
    """
    These are the exchange inputs that can be provided to the interactive brokers API.
    This is not a complete list by any means and its dependent on the market as well.
    The amount of exchanges i pretty fast, just the United States has 150 supported exchanges.
    See https://www.interactivebrokers.com/en/trading/products-exchanges.php#/
    """
    NASDAQ = 'NASDAQ'
    NYSE = 'NYSE'
    AMEX = 'AMEX'
    ARCA = 'ARCA'
    IDEALPRO = 'IDEALPRO' # A special exchange provided by IBKR for traders wanting to move larger quantities.
    SMART = 'SMART' # A special exchange type provided by IBKR that will route the order to the exchange with the best price.

class Currency(Enum):
    """
    Supported currencies in the Interactive Brokers API.
    Major currencies are listed first, followed by other supported currencies.
    """
    # Major currencies
    USD = 'USD'  # US Dollar
    EUR = 'EUR'  # Euro
    GBP = 'GBP'  # British Pound
    JPY = 'JPY'  # Japanese Yen
    AUD = 'AUD'  # Australian Dollar
    CAD = 'CAD'  # Canadian Dollar
    CHF = 'CHF'  # Swiss Franc

    # Other supported currencies
    AED = 'AED'  # UAE Dirham
    CNH = 'CNH'  # Chinese Yuan (Offshore)
    CZK = 'CZK'  # Czech Koruna
    DKK = 'DKK'  # Danish Krone
    HKD = 'HKD'  # Hong Kong Dollar
    HUF = 'HUF'  # Hungarian Forint
    ILS = 'ILS'  # Israeli Shekel
    KRW = 'KRW'  # South Korean Won
    MXN = 'MXN'  # Mexican Peso
    MYR = 'MYR'  # Malaysian Ringgit
    NOK = 'NOK'  # Norwegian Krone
    NZD = 'NZD'  # New Zealand Dollar
    PLN = 'PLN'  # Polish Złoty
    SAR = 'SAR'  # Saudi Riyal
    SEK = 'SEK'  # Swedish Krona
    SGD = 'SGD'  # Singapore Dollar
    TRY = 'TRY'  # Turkish Lira
    TWD = 'TWD'  # Taiwan Dollar
    ZAR = 'ZAR'  # South African Rand

class Market(Enum):
    US = 'US'
    AU = 'AU'

class SecurityType(Enum):
    """ 
    can be found in the docks https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-ref/#commreport-pub-func
    Security type is a slight misnomer as some of these are not security based (e.g CFD).
    """
    STK = 'STK'  # stock or ETF
    CASH = 'CASH'  # forex pair
    OPT = 'OPT'  # option
    FUT = 'FUT'  # future
    IND = 'IND'  # index
    FOP = 'FOP'  # futures option
    BAG = 'BAG'  # combo
    WAR = 'WAR'  # warrant
    BOND = 'BOND'  # bond
    CMDTY = 'CMDTY'  # commodity
    NEWS = 'NEWS'  # news
    FUND = 'FUND'  # mutual fund
    CFD = 'CFD'  # contract for difference

class OrderType(Enum):
    LMT = 'LMT'  # limit order
    MKT = 'MKT'  # market order

class IBAlgo(Enum):
    """
    See https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-ref/#order-ref
    See https://www.interactivebrokers.com/en/trading/ordertypes.php
    """
    DARKICE = 'DARKICE'  # Dark Ice algorithm
    ICEBERG = 'ICEBERG'  # Iceberg algorithm
    ARRIVALPX = 'ARRIVALPX'  # Arrival Price algorithm
    PCTVOL = 'PCTVOL'  # Percentage of Volume algorithm
    TWAP = 'TWAP'  # Time Weighted Average Price algorithm
    VWAP = 'VWAP'  # Volume Weighted Average Price algorithm

class SpecialOrder(Enum):
    GAP_CONDITIONAL = 'Gap-Conditional'
    CHILD_MOC = 'Child-MOC' 

# Custom error messages for incorrect values.
# We can use this to more easily provide a consistent user error message experience.
TRADING_ERROR_MESSAGES = {
    'unsupported_exchange': 'Exchange {exchange} is not supported yet. Supported exchanges are: {supported_exchanges}',
    'unsupported_currency': 'Currency {currency} is not supported yet. Supported currencies are: {supported_currencies}',
    'unsupported_market': 'Market {market} is not supported yet. Supported markets are: {supported_markets}',
    'unsupported_security_type': 'Security type {security_type} is not supported yet. Supported types are: {supported_types}',
    'unsupported_order_type': 'Order type {order_type} is not supported yet. Supported types are: {supported_types}',
    'unsupported_algo': 'Algorithm {algo} is not supported yet. Supported algorithms are: {supported_algos}',
    'unsupported_special_order': 'Special order {special_order} is not supported yet. Supported orders are: {supported_orders}',
    'invalid_combination': 'Invalid combination: {details}',
}

# Here we define the trading values that are actually supported by the OMS.
# One thing to note here is that this does not account for invalid combinations of values.
SUPPORTED_EXCHANGES = [Exchange.NYSE, Exchange.NASDAQ, Exchange.ARCA, Exchange.SMART]
SUPPORTED_CURRENCIES = [Currency.USD, Currency.AUD]
SUPPORTED_MARKETS = [Market.US, Market.AU]
SUPPORTED_SECURITY_TYPES = [SecurityType.STK, SecurityType.CFD]
SUPPORTED_ORDER_TYPES = [OrderType.LMT, OrderType.MKT]
SUPPORTED_ALGOS = [IBAlgo.DARKICE, IBAlgo.ICEBERG]
SUPPORTED_SPECIAL_ORDERS = []

# Here we define the validator functions that we use to construct an annotated type
# For each of the supported values. Using an annotated type allows us to re-use the 
# type in several classes and keep a consistent experience in for example error messages
# Across the whole project.
def validate_exchange(exchange: Exchange) -> Exchange:
    if exchange not in SUPPORTED_EXCHANGES:
        raise ValueError(TRADING_ERROR_MESSAGES['unsupported_exchange'].format(
            exchange=exchange.value,
            supported_exchanges=', '.join(e.value for e in SUPPORTED_EXCHANGES)
        ))
    return exchange

def validate_currency(currency: Currency) -> Currency:
    if currency not in SUPPORTED_CURRENCIES:
        raise ValueError(TRADING_ERROR_MESSAGES['unsupported_currency'].format(
            currency=currency.value,
            supported_currencies=', '.join(c.value for c in SUPPORTED_CURRENCIES)
        ))
    return currency

def validate_market(market: Market) -> Market:
    if market not in SUPPORTED_MARKETS:
        raise ValueError(TRADING_ERROR_MESSAGES['unsupported_market'].format(
            market=market.value,
            supported_markets=', '.join(m.value for m in SUPPORTED_MARKETS)
        ))
    return market

def validate_security_type(security_type: SecurityType) -> SecurityType:
    if security_type not in SUPPORTED_SECURITY_TYPES:
        raise ValueError(TRADING_ERROR_MESSAGES['unsupported_security_type'].format(
            security_type=security_type.value,
            supported_types=', '.join(st.value for st in SUPPORTED_SECURITY_TYPES)
        ))
    return security_type

def validate_order_type(order_type: OrderType) -> OrderType:
    if order_type not in SUPPORTED_ORDER_TYPES:
        raise ValueError(TRADING_ERROR_MESSAGES['unsupported_order_type'].format(
            order_type=order_type.value,
            supported_types=', '.join(ot.value for ot in SUPPORTED_ORDER_TYPES)
        ))
    return order_type

def validate_algo(algo: IBAlgo) -> IBAlgo:
    if algo not in SUPPORTED_ALGOS:
        raise ValueError(TRADING_ERROR_MESSAGES['unsupported_algo'].format(
            algo=algo.value,
            supported_algos=', '.join(a.value for a in SUPPORTED_ALGOS)
        ))
    return algo

def validate_special_order(special_order: SpecialOrder) -> SpecialOrder:
    if special_order not in SUPPORTED_SPECIAL_ORDERS:
        raise ValueError(TRADING_ERROR_MESSAGES['unsupported_special_order'].format(
            special_order=special_order.value,
            supported_orders=', '.join(so.value for so in SUPPORTED_SPECIAL_ORDERS)
        ))
    return special_order

# These are the annotated types that we actually use in downstream code.
# This can be used by classes that we use in trading related context to validate inputs.
# these types should be used as the type annotation. Can be used in classes and functions.
SupportedExchange = Annotated[Exchange, BeforeValidator(validate_exchange)]
SupportedCurrency = Annotated[Currency, BeforeValidator(validate_currency)]
SupportedMarket = Annotated[Market, BeforeValidator(validate_market)]
SupportedSecurityType = Annotated[SecurityType, BeforeValidator(validate_security_type)]
SupportedOrderType = Annotated[OrderType, BeforeValidator(validate_order_type)]
SupportedAlgo = Annotated[IBAlgo, BeforeValidator(validate_algo)]
SupportedSpecialOrder = Annotated[SpecialOrder, BeforeValidator(validate_special_order)]

if __name__ == "__main__":
    # Example usage
    class OrderRequest(BaseModel):
        exchange: SupportedExchange
        currency: SupportedCurrency
        market: SupportedMarket
        security_type: SupportedSecurityType
        order_type: SupportedOrderType
        algo: SupportedAlgo | None = None
        special_order: SupportedSpecialOrder | None = None
    try:
        # This should raise a validation error
        order = OrderRequest(
            exchange=Exchange.AMEX,  # Not supported
            currency=Currency.EUR,
            market=Market.AU,
            security_type=SecurityType.STK,
            order_type=OrderType.LMT
        )
    except ValidationError as e:
        print("Validation Error:")
        for error in e.errors():
            print(f"Field: {error['loc']}")
            print(f"Error: {error['msg']}")
            print("---")