from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from src.config.globals.signals import SIGNALS
from src.config.globals.trading import TGL
import numpy as np
from src.trades.trades import TradeRecord


@dataclass
class RawOrder:
    # this object is created when an order is imported from a CSV orders file.

    ticker: str
    date_str: str
    exchange: str
    # max_positions: int        deprecated - replaced with max_exposure
    # max_daily_entries: int    deprecated - replaced with max_new_exposure
    max_exposure: float
    max_new_exposure: float
    action: str
    is_exit: bool
    pos_size_pct: float
    # pos_score: float          deprecated - replaced with order_rank
    order_rank: float
    currency: str
    order_type: str
    order_type_special: str | None     # e.g. 'Gap-Conditional'
    gtd_time: str                      # number of seconds after open
    price_condition: str               # e.g. '33.14'  i.e. price of condition.
    order_price: float
    prior_close: float
    tif: str
    strategy_model_string: str
    account_id: str
    ib_algo: str
    qa_strategy_id: str = None
    qa_model_id: str = None
    alerts: list = field(default_factory=list)

    associated_trade: TradeRecord | None = None

    # non IB error and IB error callbacks must both be recorded; the latter are recorded as both string and IB error
    # objects; the IB_error object is necessary for positive quantification of IB errors.
    errors: list = field(default_factory=list)  # a list of strings indicating why order rejected etc. includes list of
    # ib error strings, which are duplicated (as IB_Error objects) in the ib_errors variable.
    ib_errors: list = field(default_factory=list)  # a list of IB callbacks (IB_Error objects) for the order

    status: str = 'PENDING'  # status to be displayed on gui

    # successful order information
    final_instrument_type: str = ''

    def __setstate__(self, state):
        for k, v in state.items():
            vars(self)[k] = v
        if 'associated_trade' not in vars(self):
            self.associated_trade = None

    def __post_init__(self):
        order_type = 'EXIT' if self.is_exit else 'ENTRY'
        from orders import OrderRef
        self.order_ref = OrderRef(self.strategy_model_string, 0, order_type)
        self.qa_strategy_id = self.order_ref.qa_strategy_id.upper()
        self.qa_model_id = self.order_ref.qa_model_id.upper()
        self.action = self.action.upper()
        self.order_price = Decimal(str(self.order_price))  # type: ignore
        self.price_condition = Decimal(str(self.price_condition)) # type: ignore
        self.date = self.parse_date()
        self.ib_algo = self.ib_algo.upper() if not np.isnan(self.ib_algo) else ''
        if not self.order_type_special or (type(self.order_type_special) == float and
                                           np.isnan(self.order_type_special)):
            self.order_type_special = None
        if self.gtd_time:
            if isinstance(self.gtd_time, str):
                hour, minute, second = [int(x) for x in self.gtd_time.split(':')]
                self.gtd_time = datetime.strftime(
                    datetime(self.date.year, self.date.month, self.date.day).replace(hour=hour, minute=minute,
                                                                                     second=second),
                    '%Y%m%d %H:%M:%S ') + 'US/Eastern'
            else:
                self.gtd_time = ''
        if isinstance(self.account_id, float) and np.isnan(self.account_id):
            self.account_id = ''

        if (isinstance(self.tif, float) and np.isnan(self.tif)) or self.tif == '':
            self.tif = 'DAY'

    def parse_date(self):
        # several issues using dateutil.parser, so using this instead
        # this assumes a constant date format from RT of dd/mm/yyyy
        separator = None
        if '-' in self.date_str:
            year = self.date_str.split('-')[0]
            month = self.date_str.split('-')[1]
            day = self.date_str.split('-')[2]
        elif '/' in self.date_str:
            separator = '/'
            year = self.date_str.split(separator)[2]
            month = self.date_str.split(separator)[1]
            day = self.date_str.split(separator)[0]
        else:
            year = self.date_str[:4]
            month = self.date_str[4:6]
            day = self.date_str[-2:]

        if len(year) != 4 or int(month) > 12:
            raise ValueError("Unknown date format in order file.  Date must be in format YYYY-MM-DD")

        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError as e:
            raise e

    @property
    def qa_strategy_model(self):
        return f'{self.qa_strategy_id}_{self.qa_model_id}'

    def valid(self, valid_accounts, valid_strategies, market):
        invalids = []
        # EXCHANGE is not used by the OMS so is ignored here.
        # if self.exchange not in tgl.valid_exchanges:
        #    invalids.append(f'{self.account_id}-{self.strategy_model_string}: UNSUPPORTED EXCHANGE ("{self.exchange}")'
        #                    f' specified in '
        #                    f'{"EXIT" if self.is_exit else "ENTRY"} ORDER for {self.ticker}. Contact developer to add'
        #                    f' new exchanges.')
        if self.action not in ['BUY', 'SELL']:
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: INVALID ACTION [{self.action}] specified '
                            f'in CSV order file order for {self.ticker} @ {self.exchange} ')
        if self.pos_size_pct > 1 or self.pos_size_pct < 0:
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: INVALID POS_SIZE_PCT found for '
                            f'{self.summary_text}.  Value must be entered as a fraction between 0 and 1.')
        qa_strategy = [s for s in valid_strategies if s.qa_id == self.qa_strategy_id]
        if not qa_strategy:
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: INVALID STRATEGY '
                            f'("{self.qa_strategy_id}") specified for '
                            f'{"EXIT" if self.is_exit else "ENTRY"} ORDER for {self.ticker}')
            return False, invalids
        qa_strategy = qa_strategy[0]
        if not self.valid_for_strategy(qa_strategy):
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: INVALID ACTION ("{self.action}") '
                            f'specified for {"EXIT" if self.is_exit else "ENTRY"} '
                            f'ORDER for {self.ticker} and {qa_strategy.direction} strategy {qa_strategy.qa_id}')
        if self.account_id and self.account_id not in [a.id for a in valid_accounts]:
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: INVALID ACCOUNT ID ("{self.account_id}") '
                            f'specified for '
                            f'{"EXIT" if self.is_exit else "ENTRY"} ORDER for {self.ticker}')
        if not ((self.date == market.current_time.date() and market.current_time < market.current_time.replace(
                hour=16, minute=0)) or (self.date == market.next_session.trading_date)):
            invalid_date = datetime.strftime(self.date, '%Y-%m-%d')  # type: ignore
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: NON CURRENT ORDER DATE ({invalid_date}) '
                            f'specified for {"EXIT" if self.is_exit else "ENTRY"} ORDER for {self.ticker}')
        if self.order_type not in TGL.supported_order_types:
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: UNSUPPORTED ORDER TYPE '
                            f'("{self.order_type}") specified for {"EXIT" if self.is_exit else "ENTRY"} ORDER for '
                            f'{self.ticker}.  Contact developer to add this order type.')
        account = [a for a in valid_accounts if a.id == self.account_id][0]
        if (self.qa_strategy_id not in account.strategy_allocations.keys() or
                not account.strategy_allocations[self.qa_strategy_id] > 0):
            invalids.append(f'{account.alias} HAS NO ALLOCATION TO STRATEGY {self.qa_strategy_id}')
        if self.order_type not in TGL.supported_order_types:
            # Currently the code only handles 'LMT' and 'MKT' exit orders. This will be updated as
            # more order types are required.
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: Unsupported order type '
                            f'"{self.order_type}". Contact developer to add order type.')
        if self.currency != 'USD':
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: Only USD orders can be processed. '
                            f'Invalid currency: {self.currency}')
        if self.tif not in ['DAY', 'GTC', 'OPG', 'GTD', 'IOC', 'FOK']:
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: Invalid TIF value of {self.tif}.  Valid '
                            f'values are DAY, GTC, OPG, GTD, IOC or FOK')
        if self.ib_algo and self.ib_algo not in TGL.supported_ib_algos:
            invalids.append(f'{self.account_id}-{self.strategy_model_string}: Unsupported IB Algo: {self.ib_algo}. '
                            f'Supported IB Algos are: {", ".join([a for a in TGL.supported_ib_algos])}')
        return not invalids, invalids

    def valid_for_strategy(self, strategy):
        valid = False
        if strategy.direction == 'LONG':
            valid = (self.is_exit and self.action == 'SELL') or (self.is_entry and self.action == 'BUY')
        elif strategy.direction == 'SHORT':
            valid = (self.is_exit and self.action == 'BUY') or (self.is_entry and self.action == 'SELL')
        return valid

    @property
    def is_entry(self):
        return not self.is_exit

    @property
    def direction(self):
        if self.is_entry:
            return 'LONG' if self.action == 'BUY' else 'SHORT'
        if self.is_exit:
            return 'LONG' if self.action == 'SELL' else 'SHORT'

    @property
    def summary_text(self, version=2):
        if version == 1:
            return f'{self.ticker}'
        elif version == 2:
            return f"{'EXIT' if self.is_exit else 'ENTRY'} ORDER - {self.qa_strategy_id}_{self.qa_model_id}, " \
                   f"{self.action} {self.ticker}@{self.exchange} on {datetime.strftime(self.date, '%Y%m%d')} in " \
                   f"{self.account_id}"

    def set_status(self, status, account_log, log_text=''):

        # set status
        assert status.upper() in ['PENDING', 'PROCESSING', 'PLACED', 'REJECTED', 'INVALID']
        self.status = status.upper()

        # obtain logging object - account_log may be either a log object, or a string representing
        # a log level ('ERROR' or 'WARNING')
        if type(account_log) == str:
            log_type = account_log.upper()
        else:
            log_type = account_log.__str__().upper()
            account_log(log_text)

        # add errors to raw order object for later summarising in email report
        if 'WARN' in log_type or 'ERROR' in log_type or 'CRITICAL' in log_type:
            # WARN - add to summary order report email, but does not get individual email
            # ERROR/CRITICAL - individual email sent for each error
            self.errors.append(log_text)
        else:
            self.alerts.append(log_text)
        SIGNALS.raw_order_update.emit()
