from datetime import datetime, timedelta
from decimal import Decimal
from src.config.globals.addresses import ADDR
import src.trades.orders as orders
import src.utils.utilities as util
from src.config.globals.log_setup import LOG
from ibapi.execution import Execution
import os
import pickle
import shutil
import sys
import threading
import time as sleeper
from tkinter.filedialog import askopenfilename
from zoneinfo import ZoneInfo

# where are records saved?  how to access next trade id?
# exit definitions - write at creation, or write whole system object, or live reference system object?


class ReportItem:
    # provides formatted data and other information for use in gui's/reports
    def __init__(self, column_header, actual_value, value_as_string='', value_as_formatted_string='',
                 excel_width=12, gui_width=40, align='right', use_tooltip=False):
        self.column_header = column_header
        self.actual_value = actual_value
        self.string_value = value_as_string if value_as_string else (
            str(actual_value) if not type(actual_value) == str else actual_value)
        self.formatted_string_value = value_as_formatted_string if value_as_formatted_string else (
            str(actual_value) if not type(actual_value) == str else actual_value)
        self.excel_width = excel_width
        self.gui_width = gui_width
        self.align = align
        self.use_tooltip = use_tooltip


class TradeRecord:

    def __init__(self, ticker, trade_id, strategy, market,
                 direction, ib_contract_object, entry_order_size, entry_order_price,
                 account_id=None, account_alias=None, scheduled_entry_order_date=None,
                 norgate_asset_id=None):

        # trade data
        self.trade_id = trade_id
        self.ticker = ticker
        self.norgate_assetid = norgate_asset_id
        self.contract = ib_contract_object
        self.strategy = strategy
        self.account_id = account_id  # IB account_id that the order was originally placed through
        self.account_alias = account_alias
        self.direction = direction
        self.market = market
        self.cancel_reason = []
        self.scheduled_entry_order_date = scheduled_entry_order_date  # date which entry order SHOULD BE or WAS placed
        self.created_datetime = datetime.now(market.zone_info)
        self.last_updated = datetime.now(market.zone_info)

        # exposure
        # Exposure is calculated and recorded AT THE TIME OF PLACEMENT OF THE ENTRY ORDER, and never changes.
        # It is calculated as (value of order when placed)/(nlv of account when placed)
        self.exposure = 0

        # setup & order data
        self.setup_rank = None
        self.order_size = entry_order_size  # duplicates (for simplicity) entry order object qty
        self.order_price = entry_order_price  # price at which stock was ordered. Contrast self.avg_entry_price

        # Execution Data
        self.entry_order_record = None
        self.exit_order_records = list()  # List of exit order records
        self.executions = []  # list of Execution objects
        self.commissions = []  # list of CommissionReport objects
        self.errors = []  # IB errors

        # current data
        self.current_price = None
        self.status = 'DRAFT'

        # object settings
        self.unsaved_changes = True
        self.event_status_change = threading.Event()

        self.archived = False

    def __getstate__(self):
        # exclude threading.Event object, so that pickling can be done
        return {k: v for k, v in vars(self).items() if k not in ['event_status_change', 'ib_tick_req_id',
                                                                 'current_price']}

    def __setstate__(self, state):
        # when loading from pickle, the threading.Event object must be added back
        for k, v in state.items():
            vars(self)[k] = v
        if 'exposure' not in vars(self):
            self.exposure = 0
        if 'scheduled_entry_order_date' not in vars(self):
            self.scheduled_entry_order_date = None
        self.event_status_change = threading.Event()
        self.current_price = None

    @property
    def entry_order_ref(self):
        if self.entry_order_record is not None:
            return self.entry_order_record.order.orderRef
        else:
            return None

    @property
    def exit_order_refs(self):
        return [o_r.order.orderRef for o_r in self.exit_order_records]

    @property
    def active(self):
        # DRAFT, PLACED, REJECTED, OPEN, CANCELLED, COMPLETE
        self.calculate_status()
        return self.status in ['DRAFT', 'PLACED', 'OPEN']

    @property
    def complete(self):
        return self.status == 'COMPLETE'

    @property
    def timezone(self):
        # the UTC timezone code for the market in which the trade occurred
        if self.market:
            tz = util.case(self.market, ['US', 'AU'], ['US/Eastern', 'Australia/NSW'], None)
        else:
            tz = None
        return tz

    @property
    def unrealised_pnl(self):
        # unrealised PNL excludes brokerage, as brokerage is included in net_pnl calcs, and including it here can
        # cause double counting.
        if self.avg_entry_price and self.current_price and self.current_position:
            if self.direction == 'LONG':
                u_pnl = round((self.current_price - self.avg_entry_price) * self.current_position, 2)
            else:
                u_pnl = round((self.avg_entry_price - self.current_price) * -self.current_position, 2)
        else:
            u_pnl = 0
        return u_pnl

    @property
    def current_position(self):
        # current size
        entry_side = 'BOT' if self.direction == 'LONG' else 'SLD'
        if self.executions:
            current_position = sum([e.shares for e in self.executions if e.side == entry_side]) - sum(
                [e.shares for e in self.executions if e.side != entry_side])
            if self.direction == 'SHORT':
                current_position = -current_position
        else:
            current_position = 0
        return current_position

    @property
    def achieved_entry_size(self):
        # short positions return a negative achieved_entry_size
        entry_side = 'BOT' if self.direction == 'LONG' else 'SLD'
        entries = [e for e in self.executions if e.side == entry_side]
        if entries:
            achieved_entry_size = max(e.cumQty for e in entries)
            if self.direction == 'SHORT':
                achieved_entry_size = -achieved_entry_size
            assert abs(achieved_entry_size) == sum(e.shares for e in entries)
        else:
            achieved_entry_size = 0

        return achieved_entry_size

    @property
    def achieved_exit_size(self):
        # long positions return a negative achieved_exit_size
        exit_side = 'SLD' if self.direction == 'LONG' else 'BOT'
        exits = [e for e in self.executions if e.side == exit_side]
        if exits:
            achieved_exit_size = max(e.cumQty for e in exits)
            if self.direction == 'LONG':
                achieved_exit_size = -achieved_exit_size
            assert abs(achieved_exit_size) == sum(e.shares for e in exits)
        else:
            achieved_exit_size = 0

        return achieved_exit_size

    @property
    def avg_entry_price(self):
        entry_side = 'BOT' if self.direction == 'LONG' else 'SLD'
        entries = [e for e in self.executions if e.side == entry_side]
        if entries:
            avg_entry_price = sum(e.shares * Decimal(e.price) for e in entries) / sum(e.shares for e in entries)
        else:
            avg_entry_price = None
        return avg_entry_price

    @property
    def avg_exit_price(self):
        exit_side = 'SLD' if self.direction == 'LONG' else 'BOT'
        exits = [e for e in self.executions if e.side == exit_side]
        if exits:
            avg_exit_price = sum(e.shares * Decimal(e.price) for e in exits) / sum(e.shares for e in exits)
        else:
            avg_exit_price = None
        return avg_exit_price

    @property
    def entry_datetime(self):
        entry_side = 'BOT' if self.direction == 'LONG' else 'SLD'
        entries = [e for e in self.executions if e.side == entry_side]
        if entries:
            entry_datetime = datetime.strptime(entries[0].time[:17], '%Y%m%d %H:%M:%S').replace(
                tzinfo=ZoneInfo(entries[0].time.rsplit(' ')[-1])).astimezone(self.market.zone_info)
        else:
            entry_datetime = None
        return entry_datetime

    @property
    def exit_datetime(self):
        exit_side = 'SLD' if self.direction == 'LONG' else 'BOT'
        exits = [e for e in self.executions if e.side == exit_side]
        if exits:
            exit_datetime = datetime.strptime(exits[-1].time[:17], '%Y%m%d %H:%M:%S').replace(
                tzinfo=ZoneInfo(exits[-1].time.rsplit(' ')[-1])).astimezone(self.market.zone_info)
        else:
            exit_datetime = None
        return exit_datetime

    @property
    def order_value(self):
        return self.order_price * self.order_size

    @property
    def entry_value(self):
        if self.avg_entry_price and self.achieved_entry_size != 0:
            entry_value = Decimal(abs(self.avg_entry_price * self.achieved_entry_size))
        else:
            entry_value = 0
        return entry_value

    @property
    def brokerage(self):
        brokerage = 0
        b_entry = self.brokerage_entry
        b_exit = self.brokerage_exit
        if b_entry:
            brokerage += b_entry
        if b_exit:
            brokerage += b_exit
        return brokerage

    @property
    def brokerage_entry(self):
        entry_side = 'BOT' if self.direction == 'LONG' else 'SLD'
        if len(self.commissions) > 0:
            unique = []
            for c in self.commissions:
                if c.execId not in [u.execId for u in unique]:
                    unique.append(c)
            entry_execs = [e.execId for e in self.executions if e.side == entry_side]
            entry_commissions = [c for c in self.commissions if c.execId in entry_execs]
            brokerage = sum(c.commission for c in entry_commissions)
            if brokerage != 0:
                return Decimal(str(brokerage))
        return None

    @property
    def brokerage_exit(self):
        exit_side = 'SLD' if self.direction == 'LONG' else 'BOT'
        if len(self.commissions) > 0:
            unique = []
            for c in self.commissions:
                if c.execId not in [u.execId for u in unique]:
                    unique.append(c)
            exit_execs = [e.execId for e in self.executions if e.side == exit_side]
            exit_commissions = [c for c in self.commissions if c.execId in exit_execs]
            brokerage = sum(c.commission for c in exit_commissions)
            if brokerage != 0:
                return Decimal(str(brokerage))
        return None

    @property
    def exit_type(self):
        exit_side = 'SLD' if self.direction == 'LONG' else 'BOT'
        exits = [e for e in self.executions if e.side == exit_side]
        if exits:
            exit_type = orders.decodeOrderRef(exits[0].orderRef).order_type
        else:
            exit_type = None
        return exit_type

    @property
    def raw_pnl(self):
        _raw_pnl = 0
        if self.executions:
            if self.avg_exit_price is not None and self.avg_entry_price is not None:
                if self.direction.upper() == 'LONG':
                    _raw_pnl = round((self.avg_exit_price - self.avg_entry_price) *
                                     (self.achieved_entry_size - self.current_position), 2)
                else:
                    _raw_pnl = round((self.avg_entry_price - self.avg_exit_price) *
                                     -(self.achieved_entry_size - self.current_position), 2)

        return _raw_pnl

    @property
    def net_pnl(self):
        _net_pnl = 0
        if self.executions:
            if self.avg_exit_price is not None:
                _net_pnl = self.raw_pnl - self.brokerage
        return _net_pnl

    @property
    def error_codes(self):
        return [e.code for e in self.errors]

    def next_exit_id(self, broker):
        # OrderRefs for exit orders are numbered sequentially as '{strategy}_{tradeID}_EXIT-{n}' where is sequential
        all_order_refs = [o.order.orderRef for o in self.exit_order_records]
        for api_callback_object in [broker.api.raw_open_orders, broker.api.raw_completed_orders]:
            if self.account_id in api_callback_object.keys():
                all_order_refs.extend([k for k in api_callback_object[self.account_id].keys()])
        trade_order_refs = [o.order.orderRef for o in self.exit_order_records] + \
                           [o for o in all_order_refs if orders.decodeOrderRef(o).trade_id == self.trade_id]
        exit_order_refs = [o for o in trade_order_refs if 'EXIT-' in o]
        try:
            exit_id = max([int(r.split('-')[1]) for r in [o.rsplit('_')[-1] for o in exit_order_refs]]) + 1
        except ValueError:
            exit_id = 1
        return exit_id

    def add_execution(self, execution: Execution):
        if execution.execId not in [e.execId for e in self.executions]:
            # avoid duplication from repeat callbacks
            corrected = [e for e in self.executions if e.execId.rsplit('.', 1)[0] == execution.execId.rsplit('.', 1)[0]]
            if corrected:
                # the execution callback is a correction to a previously issued execution
                self.executions = [e for e in self.executions if e != corrected]
            self.executions.append(execution)

            # ensure no duplication of execution objects
            unique = []
            for e in self.executions:
                if e.execId not in [n.execId for n in unique]:
                    unique.append(e)
            self.executions = unique
            self.executions.sort(key=lambda x: x.time, reverse=False)

            self.last_updated = datetime.now(self.market.zone_info)
            self.unsaved_changes = True

    def add_commission_report(self, commission_report):
        if commission_report.execId not in [c.execId for c in self.commissions]:
            self.commissions.append(commission_report)

        # ensure no duplication of commission objects
        unique = []
        for c in self.commissions:
            if c.execId not in [n.execId for n in unique]:
                unique.append(c)
        self.commissions = unique

        self.last_updated = datetime.now(self.market.zone_info)
        self.unsaved_changes = True

    def populate_orderid_records(self):
        # keeps track of orderIds for entry/exit orders, as IB deletes them once the order completes
        for o_r in [self.entry_order_record] + self.exit_order_records:
            if o_r.order.orderId:
                o_r.orderId = o_r.order.orderId

    def calculate_status(self):
        # called by ibapi after order callbacks
        self.populate_orderid_records()

        if self.entry_order_record.orderState:
            entry_status = self.entry_order_record.orderState.status
            if self.entry_order_record.orderStatus and self.entry_order_record.orderStatus.status == 'Cancelled':
                # entry orders that expire (e.g. short orders where no shares are available to short) do not get
                # an orderState callback, they only get the orderStatus callback.
                entry_status = 'Cancelled'
            ib_status_options = ['PendingCancel', 'Inactive', 'PendingSubmit', 'PendingCancel',
                                 'PreSubmitted', 'Submitted', 'ApiCanceled', 'Cancelled', 'Filled']
            if entry_status in ib_status_options:
                if entry_status in ['Inactive']:
                    self.set_status('CANCELLED')

                elif entry_status == 'PendingSubmit':
                    # IB def:  "Order transmitted but not accepted"
                    self.set_status('PLACED')

                elif entry_status in ['PendingCancel', 'ApiCanceled']:
                    # IB def:  "Order cancellation request sent but not confirmed"
                    # IB def: "Order cancellation requested by API client but not confirmed"
                    self.set_status('CANCELLED')

                elif entry_status == 'PreSubmitted':
                    # IB def:  "Simulated order accepted but not submitted" - i.e. paper account
                    # Also saw PreSubmitted for a short order with error:  "404 Order held while securities are located"
                    # in live account, presubmitted is status for orders with conditions (I think!)
                    self.set_status('PLACED')

                elif entry_status == 'Submitted':
                    # IB def: "Order accepted by IB"
                    self.set_status('PLACED')

                elif entry_status in ['Canceled', 'Cancelled']:
                    # IB def: "Order cancelled"
                    if self.status != 'CANCELLED':
                        self.cancel_reason.append(f'IB entry status = {entry_status}, '
                                                  f'IB completedStatus = '
                                                  f'{self.entry_order_record.orderState.completedStatus}')
                        self.set_status('CANCELLED')

                elif entry_status == 'Filled':
                    # IB def:  "Order completely filled"
                    if self.current_position == 0:
                        self.set_status('COMPLETE')
                    else:
                        self.set_status('OPEN')

                elif entry_status == 'Inactive':
                    # IB def: "Order received but not active because of rejection or cancellation"
                    self.set_status('CANCELLED')

                else:
                    raise ValueError('Could not positively identify trade status from orderState object')

        else:
            self.set_status('DRAFT')

        # NOTE FROM https://interactivebrokers.github.io/tws-api/order_submission.html
        # There are not guaranteed to be orderStatus callbacks for every change in order status. For example with market
        # orders when the order is accepted and executes immediately, there commonly will not be any corresponding
        # orderStatus callbacks. For that reason it is recommended to monitor the IBApi.EWrapper.execDetails function
        # in addition to IBApi.EWrapper.orderStatus.

        # So status, as determined by OrderState is overridden here now by executions data

        if self.achieved_entry_size != 0 and self.status not in ['OPEN', 'COMPLETE']:
            if self.current_position == 0:
                self.set_status('COMPLETE')
            else:
                self.set_status('OPEN')

        assert self.status in ['DRAFT', 'NOT PLACED', 'PLACED', 'REJECTED', 'OPEN', 'CANCELLED', 'COMPLETE']

    def set_status(self, new_status):
        assert new_status in ['DRAFT', 'NOT PLACED', 'PLACED', 'REJECTED', 'OPEN', 'CANCELLED', 'COMPLETE']
        if new_status != self.status:
            LOG.debug(f'TRADE {self.trade_id} - status changed from {self.status} to {new_status}')
            self.status = new_status
            self.unsaved_changes = True
            self.event_status_change.set()

    def place_bracket_orders(self, broker):
        order = self.entry_order_record.order
        LOG.debug(f'{broker.api.account_id} - TRADE {self.trade_id} - Placing entry order for {order.totalQuantity} x '
                  f'{self.ticker} @ {self.contract.exchange} with exit '
                  f'{", ".join([e.order.orderType for e in self.exit_order_records])} attached exit order'
                  + f'{"s" if len(self.exit_order_records) > 1 else ""}')
        assert self.account_id == broker.api.account_id or self.account_id in broker.api.connected_accounts
        self.event_status_change.clear()
        broker.place_bracket_orders(contract=self.contract,
                                    entry_order=self.entry_order_record.order,
                                    child_exit_orders=[e.order for e in self.exit_order_records])

    def place_entry_order(self, broker):
        order = self.entry_order_record.order
        LOG.debug(f'{broker.api.account_id} - TRADE {self.trade_id} - Placing entry order for {order.totalQuantity} x '
                  f'{self.ticker} @ {self.contract.exchange}')
        assert self.account_id == broker.api.account_id or self.account_id in broker.api.connected_accounts
        self.event_status_change.clear()
        broker.place_order(self.contract, self.entry_order_record.order)

    def place_exit_order(self, exit_order_record, broker):

        eor = exit_order_record

        # validation
        assert self.account_id == broker.api.account_id or self.account_id in broker.api.connected_accounts
        if eor.order.orderType == 'MOC' and self.active_exit_orders(broker):
            msg = 'MOC orders cannot be used in ocaGroups yet.  Code must be updated before MOC orders can be used.'
            raise ValueError(msg)

        # write parent orderId (if parent order still live) to exit record
        if self.entry_order_record.is_active_at_broker(broker, self.account_id) and \
                not self.entry_order_record.orderStatus.filled:
            # do not write if parent order is partially filled - returns error 201
            eor.order.parentId = self.entry_order_record.order.orderId
        else:
            # if original parent order id has expired, it cannot be used in the new child order
            eor.order.parentId = ''

        # determine and write ocaGroup
        oca_group = set([e.order.ocaGroup for e in self.exit_order_records if e.order.ocaGroup != ''])
        assert len(oca_group) <= 1
        if not oca_group or list(oca_group)[0] == '':
            eor.order.ocaGroup = f'{self.ticker}_{self.trade_id}_EXITS'
        else:
            eor.order.ocaGroup = list(oca_group)[0]

        eor.order.ocaType = 2

        # append to trade
        self.exit_order_records.append(eor)

        # place order
        LOG.debug(f'{broker.api.account_id} - TRADE {self.trade_id} - Placing exit order for {eor.order.totalQuantity} '
                  f'x {self.ticker} @ {self.contract.exchange}')
        self.event_status_change.clear()
        order_id = broker.place_order(self.contract, eor.order)

        return order_id

    def active_exit_orders(self, broker):
        return [e for e in self.exit_order_records if e.is_active_at_broker(broker)]

    def report_parameter(self, parameter):
        # this simplifies migrating trade data into Excel or gui reports.
        # for each parameter of the trade, these values are returned in a list:
        #   0. Column Header
        #   1. Value as an int or float (for numeric values) or None (for string values)
        #   2. Formatted value as a string (2 dp etc.)
        #   2. Exact value as a string (for use in texthints in gui)
        #   3. Excel column width default
        #   4. GUI column width default

        if parameter == 'account_alias':
            if 'account_alias' in vars(self):
                return ReportItem('Account', self.account_alias)
            else:
                return ReportItem('Account', self.account_id)  # account alias was added later, not all trades have it
        elif parameter == 'strategy.qa_strategy_model':
            return ReportItem('Strategy', self.strategy.qa_strategy_model)
        elif parameter == 'ticker':
            return ReportItem('Symbol', self.ticker)
        elif parameter == 'entry_datetime':
            return ReportItem('Entry Time', self.entry_datetime,
                              value_as_string=datetime.strftime(
                                  self.entry_datetime, '%Y-%m-%d %H:%M:%S') if self.entry_datetime else '',
                              value_as_formatted_string=datetime.strftime(self.entry_datetime,
                                                                          '%Y-%m-%d %H:%M:%S') if
                              self.entry_datetime else '',
                              excel_width=16,
                              gui_width=60)
        elif parameter == 'order_price':
            return ReportItem('Order Price', self.order_price,
                              value_as_formatted_string=str(round(self.order_price, 2)),
                              use_tooltip=True)
        elif parameter == 'avg_entry_price':
            return ReportItem('Entry Price', self.avg_entry_price,
                              value_as_formatted_string=str(
                                  round(self.avg_entry_price, 2)) if self.avg_entry_price else '',
                              use_tooltip=True)
        elif parameter == 'order_size':
            return ReportItem('Order Size', self.order_size,
                              use_tooltip=True)
        elif parameter == 'achieved_entry_size':
            return ReportItem('Entry Size', self.achieved_entry_size,
                              use_tooltip=True)
        elif parameter == 'entry_value':
            return ReportItem('Entry Value', self.entry_value,
                              value_as_formatted_string=str(round(self.entry_value, 2)) if self.entry_value else '',
                              use_tooltip=False)
        elif parameter == 'current_price':
            return ReportItem('Current Price', self.current_price, value_as_formatted_string=str(
                round(self.current_price, 2)) if self.current_price else '', use_tooltip=True)
        elif parameter == 'exit_datetime':
            return ReportItem('Exit Time', self.exit_datetime,
                              value_as_string=datetime.strftime(self.exit_datetime,
                                                                '%Y-%m-%d %H:%M:%S') if self.exit_datetime else '',
                              value_as_formatted_string=datetime.strftime(self.exit_datetime,
                                                                          '%Y-%m-%d %H:%M:%S') if
                              self.exit_datetime else '',
                              excel_width=16,
                              gui_width=60)
        elif parameter == 'avg_exit_price':
            return ReportItem('Exit Price', self.avg_exit_price,
                              value_as_formatted_string=str(round(self.avg_exit_price,
                                                                  2)) if self.avg_exit_price else '',
                              use_tooltip=True)
        elif parameter == 'exit_type':
            return ReportItem('Exit Type', self.exit_type)
        elif parameter in 'net_pnl':
            return ReportItem('Net PnL', self.net_pnl,
                              value_as_formatted_string=str(round(self.net_pnl, 2)),
                              use_tooltip=True)
        elif parameter == 'brokerage':
            return ReportItem('Brokerage', self.brokerage,
                              value_as_formatted_string=str(round(self.brokerage, 2)),
                              use_tooltip=True)
        elif parameter == 'status':
            return ReportItem('Status', self.status)
        elif parameter == 'account_id':
            return ReportItem('Account', self.account_id)
        elif parameter == 'unrealised_pnl':
            return ReportItem('Unrealised PnL', actual_value=self.unrealised_pnl,
                              value_as_formatted_string=str(round(self.unrealised_pnl, 2)),
                              use_tooltip=True)
        elif parameter == 'trade_id':
            return ReportItem('Trade Id', actual_value=self.trade_id,
                              value_as_formatted_string=str(self.trade_id),
                              use_tooltip=False)
        else:
            raise ValueError(f'Unknown parameter {parameter} for trade object')

    def process_ib_error(self, order_record, error, broker_api):
        # triggered by broker api when an error is received

        is_entry = order_record == self.entry_order_record

        # all errors are saved to the trade, and logged at debug level
        self.errors.append(error)
        LOG.debug(f'ORDER {error.id} ERROR - Error {error.code}: {error.string}')

        # custom handling of individual error codes
        if error.code == 399:
            # 399 = your order will not be placed at the exchange until YYYY-MM-DD 04:00:00 US/Eastern
            pass
        elif error.code == 404:
            # 404 = Order held while securities are located.
            pass
        elif error.code == 2161:
            # 2161 = In accordance with our regulatory obligations as a broker, we will initially cap
            #        (or limit) the price of your Limit Order to #.## or a more aggressive price still
            #        within your specified limit price.
            cap_price = error.string.split(' or a more aggressive price')[0].rsplit(' ', 1)[1]
            original_order = error.string.split('  In accordance', 1)[0]
            LOG.debug(f'Order {error.id} [{original_order}] has been capped by Interactive Brokers at {cap_price}')
        elif error.code in [135, 136, 137, 161, 202]:
            # 136	This order cannot be cancelled.	An attempt was made to cancel an order than cannot be
            # cancelled, for instance because ...
            # 137	VWAP orders can only be cancelled up to three minutes before the start time.
            # 161	Cancel attempted when order is not in a cancellable state. Order permId =	An attempt
            # was made to cancel an order not active at the time.
            # 202	Order cancelled - Reason:	An active order on the IB server was cancelled. See
            # Order Placement Considerations for additional information/considerations for these errors.

            # These errors will cause endless loop of cancelling if cancel on error is used.
            pass
        elif error.code == 10311:
            # "This order will be directly routed to AMEX. Direct routed orders may result in higher trade fees.
            # Restriction is specified in Precautionary Settings of Global Configuration/API."
            pass

        else:
            if is_entry:

                # ERROR FROM AN ENTRY ORDER

                if error.code in [201, 202]:
                    # 1. entry order error -
                    # 202 = confirmation of cancelling  (An active order on the IB server was cancelled.)
                    # 201 - An attempted order was rejected by the IB servers.
                    self.set_status('CANCELLED')
                elif error.code in [10147, 10148]:
                    # OrderId {id} that needs to be cancelled cannot be cancelled, state: Cancelled.
                    # Errors 10147 and 10148 will cause endless loop of cancelling if cancel on error is used.
                    pass
                else:
                    # 1. entry order error - cancel whole trade
                    LOG.debug(f'TRADE {self.trade_id} cancelled due to error {error.code} on order {error.id}: '
                              f'{error.string}')
                    broker_api.cancelOrder(error.id)
                    self.set_status('CANCELLED')

                    if error.code == 343:
                        LOG.info(f'Invalid formatted date: {self.entry_order_record.order.goodTillDate}')

            else:

                # ERROR FROM AN EXIT ORDER

                if self.status == 'CANCELLED' and error.code in [10147, 10148]:
                    # parent entry order has been previously cancelled, which has automatically cancelled the child
                    # orders.  Cancelling of child orders then returns errors 10147, 10148 - "OrderId {id} that needs to
                    # be cancelled cannot be cancelled, state: Cancelled."
                    pass

                elif not self.executions:
                    # 2. exit order error + entry not filled - cancel whole trade
                    broker_api.cancelOrder(self.entry_order_record.order.orderId)
                    for e in self.exit_order_records:
                        broker_api.cancelOrder(e.order.orderId)
                    self.set_status('CANCELLED')
                    LOG.debug(f'TRADE {self.trade_id} cancelled due to error {error.code} on exit order {error.id}: '
                              f'{error.string}')

                else:
                    # 3. exit order error + entry filled
                    LOG.debug(f'TRADE {self.trade_id} - error received on exit order {error.id} but entry order '
                              f'already filled. Trade not cancelled, exit not placed.  Error: {error.code} - '
                              f'{error.string}')

                    if error.code == 343:
                        LOG.info(f'Invalid formatted date: {self.entry_order_record.order.goodTillDate}')

    def prune(self):
        # This is called to delete selected elements of the trade data object.  This should only be called on
        # trades that are completed and are being archived.

        if self.status != 'COMPLETE':
            return

        self.cancel_reason = []
        for e in self.exit_order_records:
            e.orderState_history = []
        self.entry_order_record.orderState_history = []
        self.exit_order_records = [e for e in self.exit_order_records
                                   if e.orderState
                                   and e.orderState.status not in ['Cancelled', 'PendingCancel']]
        self.errors = []
        self.market.session_list = []
        if 'norgate_assetid' in vars(self).keys():
            del self.norgate_assetid


class TradeRegister:
    _instances = {}
    _instance_lock = threading.Lock()

    def __new__(cls, account_id):
        with cls._instance_lock:
            if account_id not in cls._instances.keys():
                instance = super(TradeRegister, cls).__new__(cls)
                cls._instances[account_id] = instance
                return instance
            else:
                return cls._instances[account_id]

    def __init__(self, account_id):
        if hasattr(self, 'initialised'):
            return

        self.initialised = True
        self.account_id = account_id
        self.trades = []
        self.register_lock = threading.Lock()
        self.load_trade_list()
        self._last_backup = None
        self._trade_id_counter = 0
        self.enable_autosave = True
        self.manage_trade_register_backup_versions()
        self.autosave_thread = threading.Thread(target=self.autosave, name=f'{self.account_id} Trade Register Autosave')
        self.autosave_thread.start()

    def autosave(self, seconds=5):
        while self.enable_autosave:
            count = 0
            while count < seconds and self.enable_autosave:
                sleeper.sleep(0.1)
                count += 0.1
            changed = [t for t in self.trades if t.unsaved_changes is True]
            if changed:
                self.save_trade_list()
                for t in self.trades:
                    t.unsaved_changes = False

    def append_trade(self, trade):
        # must be done in a thread safe way
        self.register_lock.acquire(blocking=True)
        self.trades.append(trade)
        self.register_lock.release()

    def remove_trade(self, trade):
        self.register_lock.acquire(blocking=True)
        try:
            self.trades.remove(trade)
        except ValueError:
            pass
        self.register_lock.release()

    def load_trade_list(self):
        self.register_lock.acquire()
        self.trades = self._load_file()
        if self.register_lock.locked():
            self.register_lock.release()
        LOG.debug(f'{self.account_id} trading Trade register loaded')

    def _load_file(self):
        LOG.debug(f'Loading {self.account_id} Trade Register {self.file_path}')
        success, n, trades, corrupted = False, 0, [], False
        while not success and not corrupted:
            n += 1
            try:
                if os.path.isfile(self.file_path):
                    with open(self.file_path, "rb") as trades_file:
                        trades = pickle.load(trades_file)
                else:
                    with open(self.file_path, "wb") as f:
                        pickle.dump(self.trades, f)
                success = True
            except (FileExistsError, FileNotFoundError, PermissionError, BlockingIOError, IOError, InterruptedError,
                    ImportError, OSError, EOFError, WindowsError, RuntimeError, SystemError, TimeoutError) as e:
                success = False
                if 'Ran out of input' in e.args[0]:
                    corrupted = True
                else:
                    if n == 10:
                        LOG.critical(f'Could not access trade register for account {self.account_id}:  Error: {e}.'
                                     f'Trading is halted until this is addressed')
                        raise e
                    if n > 5:
                        sleeper.sleep(n)
                        LOG.warning(f"Error accessing {self.account_id} trade register file: {e}.  "
                                    f"Trying again, attempt {n}")
        if corrupted:
            if self.register_lock.locked():
                self.register_lock.release()
            self.restore_most_recent_backup()
            LOG.warning(f'{self.account_id} Trade Register did not finish saving last time and is corrupted.  A '
                        f'backup version has been restored.')

        return trades

    @property
    def file_path(self):
        return os.path.join(ADDR.folder_trade_registers, f'{self.account_id} Trade Register')

    def get_file_size_mb(self):
        if os.path.isfile(self.file_path):
            return os.path.getsize(self.file_path)/1024/1024
        else:
            return 0

    @property
    def backup_due(self):
        if not self._last_backup or (self._last_backup and self._last_backup < datetime.now() - timedelta(hours=2)):
            return True
        else:
            return False

    @property
    def max_order_id(self):
        # returns the highest orderId recorded in any trade in the register
        order_ids = [x for x in
                     [t.entry_order_record.order.orderId for t in self.trades if
                      t.entry_order_record and t.entry_order_record.order and t.entry_order_record.order.orderId] +
                     [a for b in [[e.order.orderId for e in t.exit_order_records if e.order and e.order.orderId]
                                  for t in self.trades] for a in b if a]]
        if order_ids:
            return max(order_ids)
        else:
            return 0

    def open_trades(self, strategy_id_list=None):
        if strategy_id_list:
            ot = [t for t in self.trades if t.active and t.strategy.qa_id in strategy_id_list]
        else:
            ot = [t for t in self.trades if t.active]
        return ot

    def next_trade_id(self, broker):

        # ensures unique trade id is called, accounts for trade ids not saved to register,
        # and (cancelled) trade ids at broker

        self.register_lock.acquire(blocking=True)

        broker_max, trades_max = 0, 0
        if broker:
            broker_max = broker.max_trade_id_at_broker  # cancelled trades can cause issues.
        if self.trades:
            trades_max = max([t.trade_id for t in self.trades])

        # self._trade_id_counter keeps track of trade_ids that are not yet saved back to the register
        self._trade_id_counter = max(trades_max, broker_max, self._trade_id_counter) + 1
        self.register_lock.release()

        return self._trade_id_counter

    def save_trade_list(self):

        # TODO: this thread safety can be improved
        self.register_lock.acquire(blocking=True)

        start = datetime.now()

        LOG.debug(f'{self.account_id} Saving Trade Register')

        assert isinstance(self.trades, list)
        trade_ids = [t.trade_id for t in self.trades]
        if len(trade_ids) != len(set(trade_ids)):
            raise ValueError(f'{self.account_id} Trade Register has duplicate trade ids')

        if self.backup_due and os.path.isfile(self.file_path):
            backup_file_path = os.path.join(ADDR.folder_trade_register_backups, f'{self.account_id} Trade Register '
                                            f'{datetime.strftime(datetime.now(), "%Y%m%d %H%M%S")}')
            shutil.copy(self.file_path, backup_file_path)
            self._last_backup = datetime.now()
            bu = ' with backup'
        else:
            bu = ''

        with open(self.file_path, "wb") as f:
            # note that threading objects, including locks, are not pickle-able
            pickle.dump(self.trades, f)

        end_time = datetime.now()
        duration_s = (end_time - start).total_seconds()

        LOG.debug(f'{self.account_id} Trade Register saved{bu} in {duration_s} seconds')
        self.register_lock.release()

    def restore_most_recent_backup(self):

        self.register_lock.acquire(blocking=True)
        backup_folder = ADDR.folder_trade_register_backups

        # move corrupted file into corrupted folder
        backup_file_path = os.path.join(backup_folder, f'CORRUPTED - {self.account_id} Trade Register '
                                        f'{datetime.strftime(datetime.now(), "%Y%m%d %H%M%S")}')
        shutil.copy(self.file_path, backup_file_path)
        self._last_backup = datetime.now()

        # load most recent backup into trades register
        backup_files = [f for f in os.listdir(backup_folder) if self.account_id in f and 'CORRUPTED' not in f]
        if backup_files:
            backup_files.sort(key=lambda x: x[-15])
            with open(os.path.join(backup_folder, backup_files[-1]), "rb") as trades_file:
                self.trades = pickle.load(trades_file)
        else:
            self.trades = None

        self.register_lock.release()

        # save backup file as current file
        self.save_trade_list()

    def manage_trade_register_backup_versions(self):
        # manage previous backups - retains:
        # • all backups for 7 days
        # • final daily backup for 1 month
        # • deletes all backups older than a month
        backup_folder = ADDR.folder_trade_register_backups

        delete_date = (datetime.now() - timedelta(days=31)).date()
        for file_name in os.listdir(backup_folder):
            file_date = str(file_name[-15:])
            if datetime.strptime(file_date, '%Y%m%d %H%M%S').date() < delete_date:
                os.remove(os.path.join(backup_folder, file_name))
                LOG.debug(f'{self.account_id} trade register backup {file_date} deleted')

        trim_date = (datetime.now() - timedelta(days=3)).date()
        dates_saved = set([datetime.strptime(f[-15:], '%Y%m%d %H%M%S').date() for f in
                           os.listdir(backup_folder) if
                           datetime.strptime(f[-15:], '%Y%m%d %H%M%S').date() < trim_date])
        for d in dates_saved:
            all_times = [datetime.strptime(f[-15:], '%Y%m%d %H%M%S') for f in os.listdir(backup_folder) if
                         datetime.strptime(f[-15:], '%Y%m%d %H%M%S').date() == d]
            if len(all_times) > 1:
                last_file = [f for f in os.listdir(backup_folder) if
                             datetime.strptime(f[-15:], '%Y%m%d %H%M%S') == max(all_times)][0]
                delete_files = [f for f in os.listdir(backup_folder) if
                                datetime.strptime(f[-15:], '%Y%m%d %H%M%S').date() == d and f != last_file]
                for f in delete_files:
                    os.remove(os.path.join(backup_folder, f))
                    LOG.debug(f'{self.account_id} trade register backup {f[-15:]} deleted')


# manual review of trades
if __name__ == '__main__':
    trade_register_file = askopenfilename(title='SELECT THE TRADE REGISTER').replace('/', '\\')
    with open(trade_register_file, 'rb') as f:
        trades = pickle.load(f)
    print(f'\n\n{len(trades)} trades loaded from file\n\n')
    while True:
        input('Register loaded')
