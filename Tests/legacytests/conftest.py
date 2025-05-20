# conftest.py contains fixtures that can be used across all tests
# conftest.py documentation:
# https://docs.pytest.org/en/6.2.x/fixture.html#conftest-py-sharing-fixtures-across-multiple-files

from decimal import Decimal
from ibapi.contract import Contract, ContractDetails
from ibapi.execution import Execution
# from ibapi.commission_report import CommissionReport
from markets import Market
import pytest
from trades import TradeRecord
from order_file_handler import FileWatcher


@pytest.fixture(scope='module')
def fixture_tsla_contract():

    # data is as retrieved 6/3/2023

    c = Contract()
    c.symbol = 'TSLA'
    c.exchange = 'SMART'
    c.primaryExchange = 'NASDAQ'
    c.currency = 'USD'
    c.secType = 'STK',

    c.comboLegs = None,
    c.comboLegsDescrip = '',
    c.conId = 0,
    c.deltaNeutralContract = None,
    c.description = '',
    c.includeExpired = False,
    c.issuerId = '',
    c.lastTradeDateOrContractMonth = '',
    c.localSymbol = '',
    c.multiplier = '',
    c.right = '',
    c.secId = '',
    c.secIdType = '',
    c.strike = 0.0,
    c.tradingClass = ''

    return c


@pytest.fixture(scope='module')
def fixture_tsla_contract_details(fixture_tsla_contract):

    # data is as retrieved 6/3/2023

    cd = ContractDetails()
    cd.aggGroup = 1,
    cd.bondType = '',
    cd.callable = False,
    cd.category = 'Auto Manufacturers',
    cd.contract = fixture_tsla_contract,
    cd.contractMonth = '',
    cd.convertible = False,
    cd.coupon = 0,
    cd.couponType = '',
    cd.cusip = '',
    cd.descAppend = '',
    cd.evMultiplier = 0,
    cd.evRule = '',
    cd.industry = 'Consumer, Cyclical',
    cd.issueDate = '',
    cd.lastTradeTime = '',
    cd.liquidHours = '20230306:0930-20230306:1600;20230307:0930-20230307:1600;20230308:0930-20230308:1600;20230309:' \
                     '0930-20230309:1600;20230310:0930-20230310:1600',
    cd.longName = 'TESLA INC',
    cd.marketName = 'NMS',
    cd.marketRuleIds = '26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26,26',
    cd.maturity = '',
    cd.minSize = Decimal('0.0001'),
    cd.minTick = 0.01,
    cd.nextOptionDate = '',
    cd.nextOptionPartial = False,
    cd.nextOptionType = '',
    cd.notes = '',
    cd.orderTypes = 'ACTIVETIM,AD,ADJUST,ALERT,ALGO,ALLOC,AON,AVGCOST,BASKET,BENCHPX,CASHQTY,COND,CONDORDER,' \
                    'DARKONLY,DARKPOLL,DAY,DEACT,DEACTDIS,DEACTEOD,DIS,DUR,GAT,GTC,GTD,GTT,HID,IBKRATS,ICE,IMB,IOC,' \
                    'LIT,LMT,LOC,MIDPX,MIT,MKT,MOC,MTL,NGCOMB,NODARK,NONALGO,OCA,OPG,OPGREROUT,PEGBENCH,PEGMID,' \
                    'POSTATS,POSTONLY,PREOPGRTH,PRICECHK,REL,REL2MID,RELPCTOFS,RPI,RTH,SCALE,SCALEODD,SCALERST,' \
                    'SIZECHK,SMARTSTG,SNAPMID,SNAPMKT,SNAPREL,STP,STPLMT,SWEEP,TRAIL,TRAILLIT,TRAILLMT,TRAILMIT,WHATIF',
    cd.priceMagnifier = 1,
    cd.putable = False,
    cd.ratings = '',
    cd.realExpirationDate = '',
    cd.secIdList = ['1778538377184: ISIN = US88160R1014;'],
    cd.sizeIncrement = Decimal('0.0001'),
    cd.stockType = 'COMMON',
    cd.subcategory = 'Auto-Cars/Light Trucks',
    cd.suggestedSizeIncrement = Decimal('100'),
    cd.timeZoneId = 'US/Eastern',
    cd.tradingHours = '20230306:0400-20230306:2000;20230307:0400-20230307:2000;20230308:0400-20230308:2000;20230309:' \
                      '0400-20230309:2000;20230310:0400-20230310:2000',
    cd.underConId = 0,
    cd.underSecType = '',
    cd.underSymbol = '',
    cd.validExchanges = 'SMART,AMEX,NYSE,CBOE,PHLX,ISE,CHX,ARCA,ISLAND,DRCTEDGE,BEX,BATS,EDGEA,CSFBALGO,JEFFALGO,' \
                        'BYX,IEX,EDGX,FOXRIVER,PEARL,NYSENAT,LTSE,MEMX,PSX'

    return cd


@pytest.fixture(scope='module')
def fixture_tsla_trade(fixture_tsla_contract_details):
    trade = TradeRecord(ticker='TSLA',
                        trade_id=1,
                        strategy='LMMR.Lev_1',
                        market=Market('US'),
                        direction='LONG',
                        ib_contract_object=fixture_tsla_contract_details,
                        entry_order_size=100,
                        entry_order_price=300,
                        account_id='DU2477234',
                        norgate_asset_id=None)
    return trade


@pytest.fixture
def fixture_execution():
    e = Execution()

    e.acctNumber = 'DU2477234',
    e.avgPrice = 17.33,
    e.clientId = 17,
    e.cumQty = Decimal('200'),
    e.evMultiplier = 0.0,
    e.evRule = '',
    e.exchange = 'ISLAND',
    e.execId = '00025b45.64058cf8.01.01',
    e.lastLiquidity = 1,
    e.liquidation = 0,
    e.modelCode = '',
    e.orderId = 100861,
    e.orderRef = 'SMMR.Lev_2_681_ENTRY',
    e.permId = 2121949802,
    e.price = 17.33,
    e.shares = Decimal('200'),
    e.side = 'BOT',
    e.time = '20230306 09:30:01 US/Eastern'

    return e


@pytest.fixture
def fixture_commissionReport():
    c = CommissionReport()
    c.commission = 1.0,
    c.currency = 'USD',
    c.execId = '00025b45.64058cf8.01.01',
    c.realizedPNL = 1.7976931348623157e+308,
    c.yieldRedemptionDate = 0,
    c.yield_ = 1.7976931348623157e+308

    return c


@pytest.fixture
def filewatcher():
    from deprecated_globals import ADDR
    fw = FileWatcher(ADDR)
    fw.testing_mode = False
    return fw
