# manages all IB/API functions.  All functions here should (normally) be internal and accessed only by
# the Broker manager
# Trades, however, observe this object directly.
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from src.config.globals.log_setup import LOG
from src.config.globals.email_manager import EMAIL_MANAGER
from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.execution import Execution, ExecutionFilter
from ibapi.commission_and_fees_report import CommissionAndFeesReport
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.wrapper import EWrapper, BarData
import itertools
import pytz
import time
from time import sleep
import threading
import src.utils.utilities as util
from zoneinfo import ZoneInfo


timer = util.CodeTimer()


class IB_Error:

    def __init__(self, error_id, code, string, advancedOrderRejectJson):
        # custom object containing error callback data, for ease of use in rest of code
        self.id: int = error_id
        self.code: int = code
        self.string: str = string
        self.advancedOrderRejectJson: str = advancedOrderRejectJson
        self.received: datetime = datetime.now()


@dataclass
class IB_market_rule:
    # custom object containing market rule (price increment data)
    rule_id: int
    low_edge: float
    increment: float


class IB_API(EWrapper, EClient):
    _instances = []

    def __init__(self, account_id, account_alias, port, client_id):
        EClient.__init__(self, self)
        EWrapper.__init__(self)

        IB_API._instances.append(self)

        self._order_id_counter = None
        self._request_id_counter = None

        self.trade_registers = []
        self.orphaned_executions = []
        self.orphaned_commissions = []

        # account and connection
        self.current_market_time = None
        self.account_id = account_id
        self.account_alias = account_alias
        self.reader_thread = None
        self.connection_thread = None
        self.port_number = port  # static record, as self.port can be cleared by IB
        self.port = port
        self.client_id = int(client_id) if client_id else 1  # Use default client ID of 1 if empty
        self.connection_error = False
        self.connected_accounts = []
        self.keep_alive = True

        # thread events
        self.event = threading.Event()
        self.event_account_update_end = {account_id: threading.Event()}  # key is account id of adviser/sub-accounts
        self.event_account_update_increment = threading.Event()
        self.event_contract_details = dict()
        self.event_error_received = threading.Event()
        self.event_execution = threading.Event()
        self.event_executions_end = threading.Event()
        self.event_open_order = threading.Event()
        self.event_open_orders_end = threading.Event()
        self.event_completed_orders_end = threading.Event()
        self.event_completed_order = threading.Event()
        self.event_positions_end = threading.Event()
        self.event_managed_accounts_received = threading.Event()
        self.event_market_time_received = threading.Event()
        # keys are order id's added at time of order placement
        self.event_order_placement_end = dict()
        self.event_bar_data = dict()
        self.event_bar_data_end = dict()
        self.event_market_rule = dict()
        self.event_nextValidId_callback = threading.Event()  # used to indicate a successful connection

        self.market_data_status = dict()  # dict of booleans, with farm as key
        self.hmds_status = dict()  # dict of booleans, with farm as key
        self.sec_def_status = dict()  # dict of booleans, with farm as key
        self.account_values = dict()
        self.AUD_account_values = dict()

        self.counters_lock = threading.Lock()
        self._updates_lock = threading.Lock()

        # callback dicts
        self.raw_contract_details = dict()
        self.raw_contract_details_by_conid = dict()
        self.raw_open_orders = dict()
        self.raw_completed_orders = dict()
        self.raw_positions = dict()
        self.raw_positions[account_id] = dict()
        self.portfolio = dict()  # overlaps with raw_positions, but also returns current market price
        self.hist_bar_data = dict()
        self.error_log = dict()
        self.market_rules = list()
        self.ib_market_data_type = int

        LOG.debug(f'IB_API instance for Account {self.account_id} initiated')

    # ORDER IDs and REQUEST IDs

    @property
    def is_financial_advisory_account(self):
        # don't request account updates from managed accounts, see
        # https://interactivebrokers.github.io/tws-api/account_updates.html#acct_update_cancel
        return 'F' in self.account_id

    @property
    def existing_order_refs(self):
        accounts = [a for a in self.connected_accounts if a in self.raw_open_orders.keys()]
        open_order_order_refs = [list(self.raw_open_orders[a].keys()) for a in accounts]
        accounts = [a for a in self.connected_accounts if a in self.raw_completed_orders.keys()]
        completed_order_order_refs = [list(self.raw_completed_orders[a].keys()) for a in accounts]
        return [x for x in  open_order_order_refs + completed_order_order_refs]

    @property
    def next_request_id(self):
        # used for id for data requests etc.
        self.counters_lock.acquire(blocking=True)
        if not self._request_id_counter:
            self._request_id_counter = 1
        else:
            self._request_id_counter += 1
        self.counters_lock.release()
        return self._request_id_counter

    @property
    def next_order_id(self):
        # used for id for orders
        with self.counters_lock:
            if not self._order_id_counter:
                # initial order id obtained from a call to IB API
                self.event.clear()
                self.reqIds(-1)
                self.event.wait()
                self._order_id_counter = max([self._order_id_counter] + [t.max_order_id + 1 for t in self.trade_registers])
                LOG.debug(f'Initial Broker Order Id = {self._order_id_counter}')
            else:
                self._order_id_counter = max([self._order_id_counter] +
                                             [t.max_order_id for t in self.trade_registers]) + 1

        return self._order_id_counter

    @property
    def trading_mode(self):
        return 'PAPER' if self.account_id[0].upper() == 'D' else 'LIVE'

    def retrieve_trade_register(self, account_id):
        r = [t for t in self.trade_registers if t.account_id == account_id]
        if r:
            return r[0]
        else:
            return None

    def nextValidId(self, request_ID):
        # this is the parent class callback function from reqIds(-1) returning the next valid request/order id
        # called once by next_order_id at launch of program to get first order id #
        self.event_nextValidId_callback.set()
        if not self._order_id_counter:
            self._order_id_counter = 0
        self._order_id_counter = max(self._order_id_counter, max([t.max_order_id for t in self.trade_registers]))
        self._order_id_counter = max(self._order_id_counter, 100000, request_ID) + 1
        self.event.set()
        super().nextValidId(request_ID)

    def managedAccounts(self, accountsList):
        self.event_nextValidId_callback.set()
        self.connected_accounts = accountsList.split(',')
        self.connected_accounts = [a.strip() for a in self.connected_accounts]
        for a in self.connected_accounts:
            if a and self.is_financial_advisory_account and 'F' not in a:
                LOG.debug(f'Managed account {a} found in account {self.account_id}')
        self.event_managed_accounts_received.set()
        super().managedAccounts(accountsList)

    def reqCurrentTime(self):
        self.event_market_time_received.clear()
        super().reqCurrentTime()

    def currentTime(self, time:int):
        self.event_nextValidId_callback.set()
        # strangely this returns local machine time, not TWS/Market time
        self.current_market_time = datetime.fromtimestamp(time)
        self.event_market_time_received.set()
        super().currentTime(time)

    # CONNECTION MANAGEMENT

    def open_port_connection(self):
        # exceptions are handled by the calling script, not here

        # connects broker self to TWS and sets it in a thread
        LOG.debug(f'Opening API connection to IB. (Port={self.port_number}, ClientId={self.client_id}, '
                          f'Trading Mode={self.trading_mode})')

        # initiate connection to broker
        self.connection_error = False  # this will be set to false by connection error 502
        self.event_nextValidId_callback.clear()
        try:
            LOG.debug(f'ib_api.connect() about to be called on port {self.port_number}, client {self.client_id}')
            self.connect("127.0.0.1", self.port_number, self.client_id)
            LOG.debug('ib_api.connect() call complete')
        except AttributeError:
            # this sometimes gets raised if TWS isn't open
            self.connection_error = True

        # start listener
        self.reader_thread = threading.Thread(target=api_reader, args=(self,), daemon=True,
                                              name=f'IB API Listener - {self.account_alias}')
        self.reader_thread.start()

        # NOTE: no requests can be sent via the API until connection is verified (in our case by
        # self.event_nextValidId_callback). Sending requests (even self.reqIds(-1)) will result in
        # the connection being closed by TWS

        # wait for valid connection, signified by receiving a nextValidId callback in the self.nextValidId and
        # self.managedAccounts callbacks, both of which are sent by TWS on initial connection
        if not self.event_nextValidId_callback.wait(5) or self.connection_error:
            self.connection_error = True
            LOG.debug('Connection Error: event_nextValidId_callback not rec. or self.connection_error')
            raise ConnectionError((1, f'Could not connect to IB account {self.account_id} via port {self.port_number}'))
        else:
            LOG.debug(f'Interactive Brokers API Connection established')
            self.connection_thread = threading.Thread(target=self.connection_manager, name=f'API Connection Manager - '
                                                                                           f'{self.account_id}')
            self.connection_thread.start()
        # why is this here?
        # while not self.isConnected():
        #   time.sleep(1)

        # Request all relevant current broker data
        self.reqCurrentTime()
        self.get_account_values(self.account_id)

        LOG.debug(f'IB account {self.account_id} - initial next order id = {self.next_order_id}')
        LOG.debug(f'IB account {self.account_id} - initial next request id = {self.next_request_id}')
        LOG.debug(f'{self.account_alias} API CONNECTION COMPLETE. TRADING MODE: {self.trading_mode}')

    def disconnect(self):
        LOG.debug('API Disconnecting')
        super().disconnect()
        LOG.debug('API Disconnected')

    def connection_manager(self):
        # runs in a connection manager thread

        connState_dict = {0: 'DISCONNECTED', 1: 'CONNECTING', 2: 'CONNECTED', 3: 'REDIRECT'}

        while self.keep_alive:
            if not self.isConnected() or not self.reader_thread.is_alive():
                msg = f'{self.account_alias} API connection has been lost. Attempting reconnection. '
                LOG.warning(msg)
                LOG.debug(msg + f'app.account_id:  {self.account_id} | app.isConnected():  {self.isConnected()} | '
                                f'connState = {self.connState} ({connState_dict[self.connState]}) | '
                                f'self.connection_thread.is_alive(): {self.reader_thread.is_alive()} | '
                                f'app.port = {self.port}')

                n, self.connection_error = 0, True
                start_time = datetime.now()
                alert_sent = False
                while self.connection_error and self.keep_alive:

                    if (datetime.now() - start_time).seconds > 900 and not alert_sent:
                        EMAIL_MANAGER.email_queue.append(['OMS Connection Alert',
                                                          'The OMS has not been able to connect to TWS for 15 minutes.'
                                                          ' The OMS will continue to attempt to connect, but manual '
                                                          'intervention to restart TWS may be required.', None])
                        alert_sent = True

                    self.connection_error = False
                    n += 1
                    LOG.debug(f'Reconnection attempt {n}')

                    # Full disconnect, and kill existing thread
                    self.disconnect()
                    self.reader_thread.join(5)

                    # Reconnect and restart listener thread  (must be done in order: connect -> reader -> wait)
                    self.port = self.port_number  # self.port can be cleared by IB after max rate of msgs received
                    self.event_nextValidId_callback.clear()
                    self.connect("127.0.0.1", self.port, self.client_id)
                    self.reader_thread = threading.Thread(target=api_reader, args=(self,), daemon=True,
                                                          name=f'IB API Listener - {self.account_alias}')
                    self.reader_thread.start()
                    if not self.event_nextValidId_callback.wait(5) or self.connection_error:
                        self.connection_error = True
                if self.keep_alive:
                    LOG.info(f'\r{datetime.strftime(datetime.now(), "%Y%m%d %H:%M:%S")} local: '
                             f'Reconnection attempt {n} successful: app.isConnected():  {self.isConnected()} | '
                             f'connState = {self.connState} ({connState_dict[self.connState]})| '
                             f'connection_thread.is_alive(): {self.reader_thread.is_alive()}\n')
            else:
                sleep(1)

    def verify_connection(self, ignore_market_data=False):

        while (not self.isConnected() or not self.reader_thread.is_alive()) and self.keep_alive:
            # wait for connection_manager thread to reestablish connection
            sleep(2)
        LOG.debug('Connection Verified')

        if not ignore_market_data and \
                not (all(self.market_data_status.values()) and
                     all(self.hmds_status.values()) and
                     all(self.sec_def_status.values())) and self.keep_alive:
            timer.start()
            if not all(self.market_data_status.values()) and self.keep_alive:
                LOG.info(f'Waiting for reconnection to market data')
                while not all(self.market_data_status.values()) and self.keep_alive:
                    time.sleep(1)
                if self.keep_alive:
                    LOG.info('Market data reconnected')
            if not all(self.hmds_status.values()) and self.keep_alive:
                LOG.info('Waiting for reconnection to HMDS')
                while not all(self.hmds_status.values()) and self.keep_alive:
                    time.sleep(1)
                if self.keep_alive:
                    LOG.info('HMDS reconnected')
            if not all(self.sec_def_status.values()) and self.keep_alive:
                LOG.info('Waiting for reconnection to Security Definition farm')
                while not all(self.sec_def_status.values()) and self.keep_alive:
                    time.sleep(1)
                if self.keep_alive:
                    LOG.info('Sec-Def farm reconnected')

    def request_and_confirm_updates(self):

        with self._updates_lock:

            for event in [self.event_open_orders_end, self.event_completed_orders_end,
                          self.event_positions_end, self.event_executions_end]:
                event.clear()

            oo_success = False
            co_success = False
            pos_success = False
            exec_success = False
            attempts = 0
            max_attempts = 100

            LOG.debug('Initiating requests for broker updates')

            while (not (oo_success and co_success and pos_success and exec_success) and
                   attempts < max_attempts and
                   self.keep_alive):
                attempts += 1

                self.verify_connection(ignore_market_data=True)

                if not oo_success:
                    self.reqAllOpenOrders()
                    if self.event_open_orders_end.is_set() or self.event_open_orders_end.wait(5):
                        LOG.debug(f'{self.account_id} OpenOrder End callback received')
                        oo_success = True

                if not co_success:
                    self.reqCompletedOrders(apiOnly=True)
                    if self.event_completed_orders_end.is_set() or self.event_completed_orders_end.wait(5):
                        LOG.debug(f'{self.account_id} CompletedOrder End callback received')
                        co_success = True

                if not pos_success:
                    self.reqPositions()
                    if self.event_positions_end.is_set() or self.event_positions_end.wait(5):
                        LOG.debug(f'{self.account_id} Broker Positions End received')
                        pos_success = True

                if not exec_success:
                    exec_filter = ExecutionFilter()
                    exec_filter.clientId = self.client_id
                    exec_filter.acct = self.account_id
                    self.reqExecutions(self.next_request_id, exec_filter)
                    if self.event_executions_end.is_set() or self.event_executions_end.wait(5):
                        LOG.debug(f'{self.account_id} executions End callback received')
                        exec_success = True

            if oo_success and co_success and pos_success and exec_success:
                return True, ''
            else:
                missing_callbacks = ['openOrder' if not oo_success else '',
                                     'completedOrder' if not co_success else '',
                                     'positions' if not pos_success else '',
                                     'execDetails' if not exec_success else '']
                missing_callbacks = ', '.join([m for m in missing_callbacks if m])
                return False, missing_callbacks

    # ACCOUNT UPDATES

    def get_account_values(self, account_id, attempts=30, event_wait_seconds=60):

        if account_id not in self.event_account_update_end.keys():
            self.event_account_update_end[account_id] = threading.Event()
        self.event_account_update_end[account_id].clear()
        if len(self.connected_accounts) == 1:
            LOG.debug(f'Requesting account update values for single account {account_id}.')
            self.reqAccountUpdates(True, self.account_id)

        else:
            # Account update subscriptions are not used because of adviser accounts, see:
            # https://groups.io/g/twsapi/topic/4043444#14008
            # https://interactivebrokers.github.io/tws-api/account_updates.html#acct_update_cancel

            try:
                idx = self.connected_accounts.index(account_id) + 1
            except ValueError:
                idx = '-'

            LOG.debug(f'Requesting account update values for {account_id}'
                      f' ({idx} of {len(self.connected_accounts)} total accounts).')

            updates_received, n = False, 0
            while not updates_received and self.keep_alive:

                n += 1

                if n > attempts:
                    raise ConnectionError(f'Could not get Account Updates for {account_id} after '
                                          f'{attempts * event_wait_seconds / 60} minutes')
                elif n > 1:
                    LOG.info(f'Requesting account update values for {account_id}, attempt {n}.')

                    if n > 2:
                        # After three attempts, disconnect from API, to force a new connection.
                        # The self.connection_manager thread will trigger a reconnection.
                        # The self.verify_connection function called below will wait for the connection manager to
                        # reestablish a valid connection before account updates are called again.
                        self.disconnect()
                        self.reader_thread.join(5)

                self.verify_connection(ignore_market_data=True)
                self.reqAccountUpdates(True, account_id)

                waited = 0
                while not updates_received and waited <= event_wait_seconds and self.keep_alive:
                    if self.event_account_update_end[account_id].is_set():
                        updates_received = True
                        if n > 1:
                            LOG.info(f'{account_id} Account updates received.')

                    else:
                        sleep(0.1)
                        waited += 0.1

                self.reqAccountUpdates(False, account_id)  # turn off the subscription, ready for new request.

    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        # request format: https://interactivebrokers.github.io/tws-api/account_updates.html

        # Re: account updates from adviser accounts, see:
        # https://groups.io/g/twsapi/topic/4043444#14008
        # https://interactivebrokers.github.io/tws-api/account_updates.html#acct_update_cancel

        super().updateAccountValue(key, val, currency, accountName)  # logs the request

        LOG.debug(f'{accountName} - updateAccountValue | {key.ljust(20)} | {val.ljust(20)} | {currency}')

        # some values are returned as strings - convert them to decimal
        if val.replace('.', '', 1).replace('-', '', 1).isnumeric():
            val = Decimal(val)

        if accountName not in self.account_values.keys():
            self.account_values[accountName] = dict()

        if currency not in self.account_values[accountName].keys():
            self.account_values[accountName][currency] = dict()

        if currency == '':
            for c in self.account_values[accountName].keys():
                self.account_values[accountName][c][key] = val
        else:
            self.account_values[accountName][currency][key] = val

        self.event_account_update_increment.set()

    def updatePortfolio(self, contract: Contract, position:Decimal,
                        marketPrice: float, marketValue: float,
                        averageCost: float, unrealizedPNL: float,
                        realizedPNL: float, accountName: str):
        if accountName not in self.portfolio.keys():
            self.portfolio[accountName] = {}
        self.portfolio[accountName][contract.conId] = {'Contract': contract, 'Position': Decimal(position),
                                                       'Market Price': Decimal(marketPrice),
                                                       'Market Value': Decimal(marketValue),
                                                       'Average Cost': Decimal(averageCost),
                                                       'Unrealised PnL': Decimal(unrealizedPNL),
                                                       'Realised PnL': Decimal(realizedPNL), 'Account ID': accountName}
        super().updatePortfolio(contract, position, marketPrice, marketValue, averageCost,
                                unrealizedPNL, realizedPNL, accountName)

    def accountDownloadEnd(self, accountName: str):
        if accountName in self.event_account_update_end.keys():

            self.event_account_update_end[accountName].set()
            LOG.debug(f'{accountName} - event_account_update_end set')
        else:
            raise ValueError(f'Update for unknown account {accountName}')

    # CONTRACTS

    def reqContractDetails(self, reqId, contract):
        LOG.debug(f'REQUEST {reqId} SENT: reqContractDetails - {contract.symbol} on {contract.exchange}')
        if reqId not in self.event_contract_details.keys():
            self.event_contract_details[reqId] = threading.Event()
        self.error_log[reqId] = []
        super().reqContractDetails(reqId, contract)

    def contractDetails(self, reqId, contractDetails):
        if reqId not in self.raw_contract_details.keys():
            self.raw_contract_details[reqId] = [contractDetails]
            self.raw_contract_details_by_conid[contractDetails.contract.conId] = [contractDetails]
        else:
            self.raw_contract_details[reqId].append(contractDetails)
            self.raw_contract_details_by_conid[contractDetails.contract.conId].append(contractDetails)
        for r in list(set(contractDetails.marketRuleIds.split(','))):
            if int(r) not in [mr.rule_id for mr in self.market_rules]:
                self.reqMarketRule(int(r))
        LOG.debug(f'REQUEST {reqId} RECEIVED: contractDetails - {contractDetails.contract.symbol} '
                  f'{contractDetails.contract.exchange}')

    def contractDetailsEnd(self, reqId: int):
        LOG.debug(f'REQUEST {reqId} END: contractDetailsEnd')
        self.event_contract_details[reqId].set()

    def reqMarketRule(self, marketRuleId: int):
        if marketRuleId in self.event_market_rule.keys():
            self.event_market_rule[marketRuleId].clear()
        else:
            self.event_market_rule[marketRuleId] = threading.Event()
        super().reqMarketRule(marketRuleId)
        LOG.debug(f'REQUEST MARKET RULE {marketRuleId} SENT: reqMarketRule')

    def marketRule(self, marketRuleId: int, priceIncrements):
        # market rules are price increments per contracts
        LOG.debug(f'MARKET RULE {marketRuleId} RECEIVED: {priceIncrements}')
        if marketRuleId not in [mr.rule_id for mr in self.market_rules]:
            for pi in priceIncrements:
                mr = IB_market_rule(marketRuleId, pi.lowEdge, pi.increment)
                self.market_rules.append(mr)
        self.event_market_rule[marketRuleId].set()
        super().marketRule(marketRuleId, priceIncrements)

    # POSITIONS

    def reqPositions(self):
        LOG.debug(f'REQUEST reqPositions SENT')
        self.event_positions_end.clear()
        self.verify_connection(ignore_market_data=True)
        super().reqPositions()

    def position(self, account: str, contract: Contract, position: float, avgCost: float):
        LOG.debug(f'BROKER ACCOUNT {account} POSITION RECEIVED: {position} x {contract.symbol} @ '
                  f'{contract.exchange}, avg entry {avgCost}')
        if account not in self.raw_positions.keys():
            self.raw_positions[account] = dict()
        self.raw_positions[account][contract.conId] = {'Account': account, 'Contract': contract, 'Position': position,
                                                       'AvgCost': avgCost}

    def positionEnd(self):
        self.event_positions_end.set()

    # ORDERS

    def placeOrder(self, orderId, contract, order):
        LOG.debug(f'ORDER {orderId} PLACED AT ACCOUNT {self.account_id}: {order.totalQuantity} x {contract.symbol}')
        self.event_order_placement_end[orderId] = threading.Event()

        if order.orderRef in self.existing_order_refs:
            raise ValueError('OrderRefs must be unique')
        super().placeOrder(orderId, contract, order)

    def cancelOrder(self, orderId, manualCancelOrderTime=''):
        # since TWS API 10.19 manualCancelOrderTime has been added as a required field.  It is bypassed by this code.
        # cf https://groups.io/g/twsapi/topic/90297869#49821
        super().cancelOrder(orderId, manualCancelOrderTime)

    # ORDER CALLBACKS
    # This code works on an observable model.  Trades are as listed in self.trade_register.trades
    # and are updated each time new order data is received from the broker

    def openOrder(self, orderId, contract, order, orderState):
        # order ref is used universally, as it is the only unique identifier that persists through all stages of
        # an order's life.
        LOG.debug(f'ORDER {orderId} RECEIVED: openOrder - orderRef={order.orderRef} '
                  f'permId={order.permId} order.orderId={order.orderId}; '
                  f'orderState: Status={orderState.status} completedStatus={orderState.completedStatus} '
                  f'completedTime={orderState.completedTime} warningText={orderState.warningText}')

        if order.account not in self.raw_open_orders.keys():
            self.raw_open_orders[order.account] = {}
        self.raw_open_orders[order.account][order.orderRef] = [orderId, contract, order, orderState]

        t, o_r = self.find_trade_by_orderRef(order)
        if o_r:
            o_r.order = order
            o_r.contract = contract
            o_r.update_orderState(orderState, t.market)
            t.calculate_status()
            t.last_updated = datetime.now(pytz.timezone(t.market.tz))
        else:
            if order.orderRef:
                LOG.info(f'{order.account} - Unable to identify trade for openOrder callback received from IB '
                                 f'(orderRef {order.orderRef})')

        if orderId in self.event_order_placement_end.keys():
            self.event_order_placement_end[orderId].set()
        else:
            self.event_order_placement_end[orderId] = threading.Event()

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId,
                    parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        LOG.debug(f'ORDER {orderId} RECEIVED: orderStatus - permId={permId} status={status} filled={filled} '
                  f'remaining={remaining} avgFillPrice={avgFillPrice} LastFillPrice={lastFillPrice} '
                  f'clientId={clientId} WhyHeld={whyHeld} MktCapPrice={mktCapPrice}')

        t, o_r = self.find_trade_by_id(orderId, permId)
        if t:
            o_r.orderStatus.status = status
            o_r.orderStatus.filled = filled
            o_r.orderStatus.remaining = remaining
            o_r.orderStatus.avgFillPrice = avgFillPrice
            o_r.orderStatus.lastFillPrice = lastFillPrice
            o_r.orderStatus.whyHeld = whyHeld
            o_r.orderStatus.mktCapPrice = mktCapPrice
            o_r.orderStatus.last_updated = datetime.now(pytz.timezone(t.market.tz))
            t.calculate_status()
            t.last_updated = datetime.now(pytz.timezone(t.market.tz))
        else:
            if orderId:
                LOG.info(f'Unable to identify trade for orderStatus callback orderId {orderId}')

        self.event_order_placement_end[orderId].set()
        
    def openOrderEnd(self):
        self.event_open_orders_end.set()

    def completedOrder(self, contract: Contract, order: Order, orderState: OrderState):
        # returns both (recently) cancelled and filled orders
        account_id = order.account
        LOG.debug(f'ORDER {order.orderRef}/{order.permId} RECEIVED: completedOrder callback '
                  f'orderState.status={orderState.status}')
        if account_id not in self.raw_completed_orders.keys():
            self.raw_completed_orders[account_id] = {}
        self.raw_completed_orders[account_id][order.orderRef] = [contract, order, orderState]
        if account_id in self.raw_open_orders.keys() and order.orderRef in self.raw_open_orders[account_id].keys():
            del self.raw_open_orders[account_id][order.orderRef]

        t, o_r = self.find_trade_by_orderRef(order)
        if o_r:
            o_r.update_orderState(orderState, t.market)
            o_r.order = order
            o_r.contract = contract
            t.calculate_status()
            t.last_updated = datetime.now(pytz.timezone(t.market.tz))
        else:
            LOG.debug(f'{order.account} - unable to identify trade for completedOrder callback received from '
                              f'IB (orderRef {order.orderRef})')

        if order.orderId in self.event_order_placement_end.keys():
            self.event_order_placement_end[order.orderId].set()
        elif order.orderId != 0:
            self.event_order_placement_end[order.orderId] = threading.Event()

    def completedOrdersEnd(self):
        self.event_completed_orders_end.set()

    # EXECUTION CALLBACKS

    def execDetails(self, reqId: int, contract: Contract, execution: Execution):

        LOG.debug(f'ORDER {execution.orderId} RECEIVED: execDetails - {execution.execId} {execution.orderId} '
                  f'{execution.orderRef} {execution.permId} '
                  f'{execution.exchange} {execution.time} {execution.clientId} {execution.shares} '
                  f'{execution.side} {execution.acctNumber} {execution.avgPrice} {execution.cumQty} '
                  f'{execution.price}')
        t, o_r = self.find_trade_by_orderRef(execution=execution)
        if t:
            t.add_execution(execution)
            t.calculate_status()
        else:
            self.orphaned_executions.append(execution)
        if execution.orderId in self.event_order_placement_end.keys():
            self.event_order_placement_end[execution.orderId].set()
        elif execution.orderId != 0:
            self.event_order_placement_end[execution.orderId] = threading.Event()

    def execDetailsEnd(self, reqId):
        for r in self.trade_registers:
            r.save_trade_list()
        LOG.debug(f'{self.account_id} - execDetailsEnd')
        self.event_executions_end.set()

    def CommissionAndFeesReport(self, CommissionAndFeesReport: CommissionAndFeesReport):
        t = []
        for r in self.trade_registers:
            t.extend([trd for trd in r.trades if CommissionAndFeesReport.execId in [e.execId for e in trd.executions]])
        if t:
            t[0].add_commission_report(CommissionAndFeesReport)
        else:
            self.orphaned_commissions.append(CommissionAndFeesReport)

    # TRADE IDENTIFIERS

    def find_trade_by_orderRef(self, order: Order = None, execution: Execution = None):
        if order:
            account_id, order_ref = order.account, order.orderRef
        elif execution:
            account_id, order_ref = execution.acctNumber, execution.orderRef
        else:
            return None, None

        trd, o_r = None, None
        trade_register = [t for t in self.trade_registers if t.account_id == account_id]
        if trade_register:
            trade_register = trade_register[0]
            for t in trade_register.trades:
                if order_ref == t.entry_order_ref:
                    trd, o_r = t, t.entry_order_record
                    break
                elif order_ref in t.exit_order_refs:
                    trd, o_r = t, [e for e in t.exit_order_records if e.order.orderRef == order_ref][0]
                    break
        return trd, o_r

    def find_trade_by_id(self, order_id=None, perm_id=None):
        # identifies TradeRecord object and OrderRecord object by either or both of orderId and permId
        # only used where orderRef is not available (i.e. orderStatus callback) - this one is a much more expensive
        # function, as all trades in all registers must be checked
        pid_trade, pid_o_r, oid_trade, oid_o_r = None, None, None, None
        all_trades = [t for trade_list in [tr.trades for tr in self.trade_registers] for t in trade_list]
        if all_trades:
            for t in all_trades:
                if perm_id and not pid_trade:
                    if t.entry_order_record.order.permId == perm_id:
                        pid_trade, pid_o_r = t, t.entry_order_record
                    elif perm_id in [e.order.permId for e in t.exit_order_records]:
                        pid_trade, pid_o_r = t, [e for e in t.exit_order_records if e.order.permId == perm_id][0]
                if order_id and not oid_trade:
                    if t.entry_order_record.order.orderId == order_id:
                        oid_trade, oid_o_r = t, t.entry_order_record
                    elif order_id in [e.order.orderId for e in t.exit_order_records]:
                        oid_trade, oid_o_r = t, [e for e in t.exit_order_records if e.order.orderId == order_id][0]

        if pid_trade and oid_trade:
            assert pid_trade == oid_trade, "Mismatching trades identified by orderId and permId"
            assert pid_o_r == oid_o_r, "Mismatching orders identified by orderId and permId"
        trade = pid_trade if pid_trade else oid_trade
        o_r = pid_o_r if pid_o_r else oid_o_r

        return trade, o_r

    # HISTORICAL DATA
    def reqHistoricalData(self, reqId, contract: Contract, endDateTime: str,
                          durationStr: str, barSizeSetting: str, whatToShow: str,
                          useRTH: int, formatDate: int, keepUpToDate: bool, chartOptions=None):
        if not chartOptions:
            chartOptions = []
        if reqId not in self.hist_bar_data.keys():
            self.hist_bar_data[reqId] = []
            self.event_bar_data[reqId] = threading.Event()
            self.event_bar_data_end[reqId] = threading.Event()
        LOG.debug(f'reqHistoricalData {reqId} submitted: {contract.symbol} on  {contract.exchange}, {durationStr} of '
                  f'{barSizeSetting} bars, subscribe = {keepUpToDate}')
        self.verify_connection()
        super().reqHistoricalData(reqId, contract, endDateTime, durationStr, barSizeSetting, whatToShow, useRTH,
                                  formatDate, keepUpToDate, chartOptions)

    def historicalData(self, reqId: int, bar: BarData):
        bar.date = self.convert_date_string_to_datetime(bar.date)
        self.hist_bar_data[reqId].append(bar)
        self.event_bar_data[reqId].set()

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        bar.date = self.convert_date_string_to_datetime(bar.date)
        self.hist_bar_data[reqId].append(bar)
        self.event_bar_data[reqId].set()

    def historicalDataEnd(self, reqId:int, start:str, end:str):
        self.event_bar_data_end[reqId].set()

    @staticmethod
    def convert_date_string_to_datetime(date_var):
        try:
            _bardate = datetime.strptime(date_var, '%Y%m%d')
        except ValueError:
            try:
                _bardate = datetime.strptime(date_var, '%Y%m%d %H:%M:%S')
            except ValueError:
                _bardate = datetime.strptime(date_var[:17], '%Y%m%d %H:%M:%S').replace(
                    tzinfo=ZoneInfo(date_var.rsplit(' ', 1)[1]))
        return _bardate

    # ERROR HANDLING

    def winError(self, text:str, lastError:int):
        LOG.info(f'{self.account_id} Windows Error: {text}')
        super().winError(text, lastError)

    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson='', *args):
        # Error Codes: https://interactivebrokers.github.io/tws-api/message_codes.html#system_codes

        # ALL error callbacks are logged at debug level
        # Some order errors are ignored (here), viz. 399, 404, 2161, otherwise, order errors are logged at error level
        # Other errors are handled on a case by case basis in the logic below

        error = IB_Error(reqId, errorCode, errorString, advancedOrderRejectJson)

        if reqId in self.error_log:
            self.error_log[reqId].append(error)
        else:
            self.error_log[reqId] = [error]

        # ORDER ERRORS
        if reqId >= 100000:

            t, o_r = self.find_trade_by_id(order_id=reqId)
            if t:
                # all processing and logging of the order errors is handled in the Trade object, not here
                t.process_ib_error(o_r, error, self)
            if errorCode not in [399, 404, 2161]:
                # the error likely indicates the terminus of the order placement process; likely there will be no
                # openOrder callback to indicate the terminus of the order placement process
                self.event_order_placement_end[reqId].set()

                # 399 = your order will not be placed at the exchange until YYYY-MM-DD 04:00:00 US/Eastern
                # 404 = Order held while securities are located.
                # 2161 = In accordance with our regulatory obligations as a broker, we will initially cap
                #        (or limit) the price of your Limit Order to 4.06 or a more aggressive price still
                #        within your specified limit price.

        # REQUEST/DATA ERRORS
        else:
            LOG.debug(f'Request {reqId} Error: {errorCode} - {errorString}')

        if errorCode in [2103, 2104, 2105, 2106, 2157, 2158, 2108]:
            try:
                farm = errorString.split(":")[1]
            except IndexError:
                farm = None
            if errorCode == 2103:  # Market data farm broken
                self.market_data_status[farm] = False
            elif errorCode == 2104:  # Market data farm OK
                self.market_data_status[farm] = True
            elif errorCode == 2108:  # Market data farm connection is inactive but should be available upon demand
                self.market_data_status[farm] = True
            elif errorCode == 2105:  # hmds data farm broken
                self.hmds_status[farm] = False
            elif errorCode == 2106:  # hmds data farm OK
                self.hmds_status[farm] = True
            elif errorCode == 2157:  # sec-def data farm broken
                self.sec_def_status[farm] = False
            elif errorCode == 2158:  # sec-def data farm OK
                self.sec_def_status[farm] = True
            elif errorCode in [2104, 2108]:
                # ignore these codes - the data farm just goes inactive when not used for a while, but is still ok.
                pass
        if errorCode == 162:
            # 162: 	Historical market data Service error message.
            pass
        elif errorCode == 200:
            # 200:  No security definition has been found for the request. OR The contract description specified for
            # <Symbol> is ambiguous
            pass

        # data connections:

        elif errorCode == 502:
            # Couldn't connect to TWS. Confirm that "Enable ActiveX and Socket EClients" is enabled and connection port
            # is the same as "Socket Port" on the TWS "Edit->Global Configuration...->API->Settings" menu. Live Trading
            # ports: TWS: 7496; IB Gateway: 4001. Simulated Trading ports for new installations of version 954.1 or
            # newer:  TWS: 7497; IB Gateway: 4002
            self.port = self.port_number
            self.connection_error = True
        elif errorCode == 504:
            # 504 - not connected. "You are trying to perform a request without properly connecting and/or after
            # connection to TWS has been broken probably due to an unhandled exception within your client application."
            self.connection_error = True
        elif errorCode == 322:
            # exceeded request limits
            pass

        if reqId in self.event_bar_data_end.keys():
            self.event_bar_data_end[reqId].set()
        elif reqId in self.event_contract_details.keys():
            self.event_contract_details[reqId].set()



def api_reader(app):
    app.run()

