# This provides all client/user facing functions. No direct API functions in this module.


from decimal import Decimal
from globals.log_setup import LOG
from globals.signals import SIGNALS
from src.ib_api.ib_api import IB_API
from ibapi.order_state import OrderState
from itertools import chain, combinations
import src.utils.utilities as util
from ibapi.contract import Contract
import orders as o

timer = util.CodeTimer()


class BrokerApp:
    _instances = []

    class ExceptionHandler:
        def __enter__(self):
            pass

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                SIGNALS.exception.emit((1, exc_type, True, exc_tb))

    def __init__(self, account_id, account_alias, port, client_id):

        BrokerApp._instances.append(self)
        self.api = IB_API(account_id, account_alias, port, client_id)

    def update_trade_register_from_api(self, refresh=True):

        # refresh issues new calls to the api
        if refresh:
            success, callback = self.api.request_and_confirm_updates()

            if not success:
                LOG.debug(f'Error connecting to broker for account {self.api.account_id} - no {callback} callback '
                          f'received')
                raise TimeoutError(f'{callback} callback not received from Account {self.api.account_id}')
            else:
                LOG.debug(f'{self.api.account_alias} order, execution & open position updates obtained\n')

        # write current share prices
        for account in self.api.connected_accounts:
            self.update_current_prices(account, refresh=False)  # prices only refreshed when called directly

            # update PLACED trades with lapsed/expired/cancelled entry orders
            # if an entry order has been cancelled (manually, or by expiry or any other means) for a PLACED trade
            #  and the client has not monitored that cancelling, then the order state will not be
            #  updated (cancelling is only sent once). The absence of an entry order at the broker
            # for a trade record with status == 'PLACED' is interpreted to mean the entry order has been cancelled.
            trade_register = self.api.retrieve_trade_register(account)
            if trade_register:
                for t in trade_register.trades:
                    t.calculate_status()
                    if t.status == 'PLACED' and \
                            t.entry_order_record.status(self, t.account_id) == 'Could not be found at broker':
                        order_state = OrderState()
                        order_state.status = 'Cancelled'
                        order_state.completedStatus = 'QA OMS: order not found at broker; assumed cancelled.'
                        t.entry_order_record.update_orderState(order_state, t.market)

        SIGNALS.trade_data_updated.emit()

    def nlv(self, account_id, currency='BASE', refresh=False):

        if refresh:
            self.api.get_account_values(account_id)

        # Net Liquidation value is only reported in the account values of the base currency (e.g. 'AUD' (not 'BASE))
        _nlv = None
        for k in self.api.account_values[account_id].keys():
            if 'NetLiquidation' in self.api.account_values[account_id][k].keys():
                _nlv = self.api.account_values[account_id][k]['NetLiquidation']
                if not (self.api.account_values[account_id][k]['ExchangeRate'] ==
                        self.api.account_values[account_id]['BASE']['ExchangeRate']):
                    raise ValueError(f'Error in NLV for account {self.api.account_alias}')

        # convert to required currency, if available
        if _nlv and currency != 'BASE':
            if currency in self.api.account_values[account_id].keys() and 'ExchangeRate' in \
                    self.api.account_values[account_id][currency].keys():
                _nlv = _nlv / self.api.account_values[account_id][currency]['ExchangeRate']
            else:
                raise ValueError(f'Before the OMS can trade in {currency} in account {account_id} there '
                                 f'must be a balance, trade or FX position in that currency in the account')

        return round(Decimal(str(_nlv)), 2)

    def current_time_from_broker(self, timeout=1):
        # IB returns the local machine time, not TWS or Market time (for some bizarre reason)
        current_time = None
        if self.api:
            self.api.reqCurrentTime()
            if self.api.event_market_time_received.wait(timeout):
                current_time = self.api.current_market_time
        return current_time

    def base_currency(self, account_id):
        currency = None
        for currency in self.api.account_values[account_id].keys():
            # Net Liquidation value is only reported in the account values of the base currency (e.g. 'AUD' (not 'BASE))
            if 'NetLiquidation' in self.api.account_values[account_id][currency].keys():
                if not (self.api.account_values[account_id][currency]['ExchangeRate'] ==
                        self.api.account_values[account_id]['BASE']['ExchangeRate']):
                    raise ValueError
                break
        return currency

    @property
    def trading_mode(self):
        return self.api.trading_mode

    @property
    def account_ids(self):
        return self.api.connected_accounts

    def connect_to_api_account(self):
        self.api.open_port_connection()

    def update_current_prices(self, account_id, refresh=True):

        # reqMktData will not reliably give us an on-demand price during market hours.   It will give us
        # EITHER the next tick during market hours (which may be some minutes/hours in the future and
        # therefore not reportable), OR the close price of the previous session IF we are outside market hours,
        # but we can't get that price during an open session.  Historical market data, on the other hand requires
        # market data subscription
        # TWS Portfolio callback provides a current price for open positions

        if refresh:
            self.api.get_account_values(account_id)

        trade_register = self.api.retrieve_trade_register(account_id)
        if trade_register and account_id in self.api.portfolio.keys():
            for t in [trade for trade in trade_register.trades if trade.active]:
                if t.contract.conId in self.api.portfolio[account_id].keys():
                    t.current_price = self.api.portfolio[account_id][t.contract.conId]['Market Price']

        SIGNALS.trade_data_updated.emit()

    def get_contract_from_ticker(self, ticker, currency, exchange='SMART', secType='STK'):

        c = Contract()
        c.symbol = ticker
        c.currency = currency
        c.exchange = exchange
        c.secType = secType

        contract_details = self.get_contract_details(c)

        LOG.debug(f'{len(contract_details)} contracts found for ticker {ticker} {currency} {exchange} '
                  f'{secType}')
        if len(contract_details) == 1:
            return contract_details[0].contract
        else:
            return None

    def get_contract_details(self, contract, wait=15):
        # ContractDetails is a larger IB object compared to the lighter Contract object
        rid = self.api.next_request_id
        contract_details = []
        self.api.reqContractDetails(rid, contract)
        if wait > 0:
            LOG.debug(f'{rid} Waiting for event_contract_details_end')
            if not self.api.event_contract_details[rid].wait(15):
                LOG.debug(f'No callback received from broker for contract details for '
                          f'{contract.symbol} at {contract.exchange}')
                return []
            if rid in self.api.raw_contract_details.keys():
                contract_details = self.api.raw_contract_details[rid]
            elif rid in self.api.error_log.keys():
                for e in self.api.error_log[rid]:
                    LOG.debug(f"Error retrieving contract details for {contract.symbol} at {contract.exchange }:"
                              f" {e.code}: {e.string}")
        return contract_details

    # ORDERS

    @property
    def max_trade_id_at_broker(self):
        i = 0
        self.api.verify_connection(ignore_market_data=True)
        for account in list(set(list(self.api.raw_open_orders.keys()) + list(self.api.raw_completed_orders.keys()))):
            # TODO: debug/validate formulas with live data
            if self.api.raw_open_orders and account in self.api.raw_open_orders.keys():
                i = max([i] + [o.decodeOrderRef(k).trade_id for k in self.api.raw_open_orders[account].keys()])
            if self.api.raw_completed_orders and account in self.api.raw_completed_orders.keys():
                i = max([i] + [o.decodeOrderRef(k).trade_id for k in self.api.raw_completed_orders[account].keys()])
        return i

    def place_bracket_orders(self, contract, entry_order, child_exit_orders):
        all_orders = [entry_order] + child_exit_orders

        # validate, and set transmit=False for all but last order
        for order in all_orders:
            order.transmit = False
            if not order.account:
                raise ValueError('Orders must specify the account in which the order is to be place')
        all_orders[-1].transmit = True

        # place entry (parent) order
        parent_order_id = self.api.next_order_id
        entry_order.orderId = parent_order_id
        entry_order.clientId = self.api.client_id
        LOG.debug(f'ORDER {parent_order_id} being placed in account {entry_order.account} '
                  f'client {entry_order.clientId}')
        self.api.placeOrder(parent_order_id, contract, entry_order)

        # place child orders
        for child_exit_order in child_exit_orders:
            child_order_id = self.api.next_order_id
            child_exit_order.orderId = child_order_id
            child_exit_order.parentId = parent_order_id
            self.api.placeOrder(child_order_id, contract, child_exit_order)

            if child_exit_order.transmit:
                self.api.event_order_placement_end[child_order_id].wait()

    def place_order(self, contract, order):
        if not order.account:
            raise ValueError('Orders must specify the account in which the order is to be place')
        order_id = self.api.next_order_id
        order.orderId = order_id
        order.clientId = self.api.client_id
        LOG.debug(f'ORDER {order_id} being placed in account {order.account} client {order.clientId}')

        self.api.placeOrder(order_id, contract, order)

        if order.transmit:
            self.api.event_order_placement_end[order_id].wait()

        return order_id

    def reconcile_trades_and_broker(self, account_id):

        excess_positions, excess_trades = [], []

        try:
            account_positions = self.api.raw_positions[account_id]
        except KeyError:
            account_positions = {}
        open_trades = self.api.retrieve_trade_register(account_id).open_trades()

        # find position without matching trades
        _excess_positions = [v for (conId, v) in account_positions.items() if
                             v['Account'] == account_id and
                             abs(v['Position']) > abs(sum([t.current_position for t
                                                           in open_trades
                                                           if t.contract.conId == conId]))]
        for v in _excess_positions:
            excess_qty = v['Position'] - sum([t.current_position for t in open_trades
                                              if t.contract.conId == v['Contract'].conId])
            excess_positions.append((v['Contract'], excess_qty))

        # find trades without matching position
        _excess_trades = [t for t in open_trades if
                          t.current_position != 0 and
                          (t.contract.conId not in account_positions.keys()
                           or
                           abs(sum([x.current_position for x in open_trades
                                    if x.contract.conId == t.contract.conId])) >
                           abs(sum([v['Position'] for k, v in account_positions.items()
                                    if v['Account'] == account_id and
                                    v['Contract'].conId == t.contract.conId])))]

        _excess_trade_conids = list(set([t.contract.conId for t in _excess_trades]))
        for c in _excess_trade_conids:
            combos_that_reconcile = []
            all_ticker_trades = [t for t in _excess_trades if t.contract.conId == c]
            all_ticker_trade_combinations = chain(*map(lambda x: combinations(all_ticker_trades, x),
                                                       range(0, len(all_ticker_trades) + 1)))
            for combo in all_ticker_trade_combinations:
                if c in account_positions.keys():
                    if sum([x.current_position for x in combo]) == account_positions[c]:
                        combos_that_reconcile.append(combo)

            if len(combos_that_reconcile) == 1:
                # there is exactly one (i.e. unambiguous) subset of trades for the ticker that match the broker
                # position; the remaining trades for that ticker are treated as having no matching broker position.
                excess_trades.extend([t for t in all_ticker_trades if t not in combos_that_reconcile[0]])
            else:
                excess_trades.extend(all_ticker_trades)

        return excess_positions, excess_trades

    def cancel_order(self, order_id):
        self.api.cancelOrder(order_id)

    def get_min_tick(self, price, market_rule_ids):
        if type(market_rule_ids) == str:
            # contractDetails object records marketRules as string of strings
            market_rule_ids = market_rule_ids.split(',')
            market_rule_ids = list(set([int(r) for r in market_rule_ids]))

        # market rules should be retrieved automatically when contract details are returned, but check here in case not
        for rule in market_rule_ids:
            if rule not in [mr.rule_id for mr in self.api.market_rules]:
                self.api.reqMarketRule(rule)

        # get applicable rules
        rules = [r for r in self.api.market_rules
                 if r.rule_id in market_rule_ids
                 and r.low_edge <= price]
        rules.sort(key=lambda x: x.low_edge, reverse=True)
        if rules:
            rule = rules[0]
            return rule.increment
        else:
            raise ValueError('Could not find minimum tick rules for contract')

    def conform_price_to_broker_min_tick(self, price, market_rule_ids):
        min_tick = self.get_min_tick(price, market_rule_ids)
        round_factor = Decimal(str((1/min_tick)))
        price_in_min_tick = Decimal(str(round(price * round_factor) / round_factor))
        return price_in_min_tick


if __name__ == '__main__':

    from src.trades.trades import TradeRegister
    import os
    from tkinter.filedialog import askdirectory
    import time as sleeper

    with open('ini.txt', 'r') as f:
        master_folder = f.read()
    if not os.path.isdir(master_folder):
        master_folder = askdirectory(title='SELECT THE FOLDER TO STORE OMS DATA:').replace('/', '\\')
        with open('ini.txt', 'w') as f:
            f.write(master_folder)

    test_account_id = 'DF1535102'
    broker = BrokerApp(account_id=test_account_id,
                       account_alias='Tester',
                       port=7550,
                       client_id=0)
    test_trade_register = TradeRegister(test_account_id)
    broker.api.trade_registers = [test_trade_register]
    broker.connect_to_api_account()

    con = Contract()
    con.symbol = 'TSLA'
    con.exchange = 'SMART'
    con.currency = 'USD'
    con.secType = 'STK'

    while True:
        sleeper.sleep(10)
    