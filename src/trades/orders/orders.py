from datetime import datetime
from globals.log_setup import LOG
from ibapi.order import Order
from ibapi.order_state import OrderState
from ibapi.order_condition import OrderCondition, Create
from ibapi.tag_value import TagValue

from trading_objects.raw_orders import RawOrder
from zoneinfo import ZoneInfo


class OrderRef:

    # the orderRef is a string that is used to uniquely identifies each order placed; it is attached to the ib order
    # orderRef has the format "{model_id}_{strategy_id}_{trade_id}_{order_type}" where
    # order_type is 'ENTRY', 'EXIT1', 'EXIT2' etc.

    def __init__(self, strategy_model_string, trade_id, order_type):
        # received an orderRef string from Quant Alpha order CSV
        # strategy_model_string is the reference for the order generated out of RealTest or AmiBroker.
        #  It is in the format {strategy}_{model} where a strategy may have multiple sub-models
        #  'strategy' is used for portfolio allocation
        #  'model' is used as a unique identifier for a trade (though this is superseded immediately by trade_id
        #  when an order is placed).
        #  sometimes 'Model ID' is used as shorthand to refer to the complete Strategy_Model

        if strategy_model_string.count('_') != 1:
            raise ValueError("Strategy ID must be in format: {strategy}_{model}")
        self.qa_strategy_id: str = strategy_model_string.split('_')[0].upper()
        self.qa_model_id: str = strategy_model_string.split('_')[1].upper()
        self.trade_id: int = trade_id
        self.order_type: str = order_type

    @property
    def ref(self):
        return f'{self.qa_strategy_id}_{self.qa_model_id}_{self.trade_id}_{self.order_type}'

    @property
    def strategy_model(self):
        return f'{self.qa_strategy_id}_{self.qa_model_id}'

    @property
    def is_entry(self):
        return 'ENTRY' in self.order_type.upper()

    @property
    def is_exit(self):
        return not self.is_entry


def decodeOrderRef(order_ref_string):
    values = order_ref_string.split('_')
    try:
        # QA OMS format
        strategy_model_string = values[0] + "_" + values[1]  # model id and strategy id
        trade_id = int(values[2])
        order_type = values[3]
        order_ref = OrderRef(strategy_model_string, trade_id, order_type)
    except IndexError:
        order_ref = OrderRef('_', 0, '')
    return order_ref


class OrderStatus:
    # a custom class to gather the various orderStatus callback variables into a single object.

    # In typically cryptic fashion, IB returns an orderState object via the openOrder/completedOrder callback, but
    # ALSO returns 11 variables related to the status of the order via the orderStatus callback.  Both callbacks have a
    # status field. Sometimes one will be returned, sometimes the other, and sometimes neither in which case executions
    # must be used to determine status. See trade.calculate_status function for how these various status callbacks
    # are handled to calculate trade status.

    # This custom object is created to hold the disparate 11 variables returned by the orderStatus callback. orderId,
    # permId, parentId and clientId are not recorded here to reduce memory use, as these are available in the parent
    # object that OrderStatus will be attached to.

    def __init__(self):
        self.status = None
        self.filled = None
        self.remaining = None
        self.avgFillPrice = None
        self.lastFillPrice = None
        self.whyHeld = None
        self.mktCapPrice = None


class OrderRecord:

    def __init__(self, order):
        if not isinstance(order, Order):
            raise ValueError('An order object must be passed to OrderRecord')

        self.order = order

        self.orderState = None
        self.orderState_history = list()

        self.orderStatus = OrderStatus()

        self.orderId = None  # must be manually recorded as IB deletes it from the order object once completed

        self.created_datetime = datetime.now(ZoneInfo('US/Eastern'))
        self.last_updated = datetime.now()

    def status(self, broker, account_id):
        if self.is_completed_at_broker(broker, account_id) and not self.is_cancelled_at_broker(broker, account_id):
            return 'Filled'
        elif self.is_cancelled_at_broker(broker, account_id):
            return 'Cancelled'
        elif self.number_filled not in [0, None] and self.number_filled != self.order.totalQuantity:
            return f'Partial Fill'
        elif self.is_active_at_broker(broker, account_id):
            return 'Active'
        elif not self.is_found_at_broker(broker, account_id):
            return 'Could not be found at broker'
        else:
            return 'Status could not be determined'

    def update_orderState(self, order_state, market):
        assert isinstance(order_state, OrderState)
        if not self.order_state_is_identical(order_state):
            order_state.received = market.current_time
            self.orderState = order_state
            self.orderState_history.append(order_state)
            self.last_updated = market.current_time

    def order_state_is_identical(self, comparison_order_state):
        my_order_state = self.orderState
        if my_order_state:
            for v in vars(my_order_state):
                if v != 'received' and vars(my_order_state)[v] != vars(comparison_order_state)[v]:
                    return False
        else:
            return False

        return True

    def order_status_is_identical(self, comparison_order_record):
        my_order_status = self.orderStatus
        if my_order_status:
            comparison_order_status = comparison_order_record.orderStatus
            identical = True
            for v in vars(my_order_status):
                if v != 'datetime_received' and vars(my_order_status)[v] != vars(comparison_order_status)[v]:
                    identical = False
                    break
        else:
            identical = False

        return identical

    def is_active_at_broker(self, broker, account_id):
        try:
            # TODO: debug/validate with live data
            active = self.order.orderRef in [k for k in broker.api.raw_open_orders[account_id].keys()]
            return active
        except KeyError:
            return False

    def is_completed_at_broker(self, broker, account_id):
        # will not return true if only a partial fill

        try:
            completed = self.order.orderRef in [k for k in broker.api.raw_completed_orders[account_id].keys()]
            return completed
        except KeyError:
            return False

    @property
    def number_filled(self):
        return self.orderStatus.filled

    def is_cancelled_at_broker(self, broker, account_id):

        try:
            cancelled = self.is_completed_at_broker(broker, account_id) and \
                        broker.api.raw_completed_orders[account_id][self.order.orderRef][2].status == 'Cancelled'
            return cancelled
        except KeyError:
            return False

    def is_found_at_broker(self, broker, account_id):

        try:
            found = (self.order.orderRef in [broker.api.raw_open_orders[account_id].keys()]
                     or
                     self.order.orderRef in [broker.api.raw_completed_orders[account_id].keys()]
                     )
            return found
        except KeyError:
            return False


def gap_and_go_special_order(contract, raw_order: RawOrder, pos_size, order_price):

    entry_order = limit_order(action=raw_order.action, quantity=pos_size,
                              limit_price=order_price,
                              order_ref=raw_order.order_ref.ref,
                              ORTH=False, tif='GTD')

    entry_order.goodTillDate = raw_order.gtd_time
    entry_order.transmit = False

    from ibapi.order_condition import OrderCondition, Create

    # Gap and Go system has a lower limit on open price, in addition to upper limit
    # this price_condition will make the order active once a price above that lower
    # limit is traded on the market
    price_condition = Create(OrderCondition.Price)
    price_condition.conId = contract.conId
    price_condition.exchange = 'SMART'
    price_condition.isMore = True
    price_condition.triggerMethod = 2
    price_condition.price = raw_order.price_condition
    price_condition.isConjunctionConnection = True

    entry_order.conditions.append(price_condition)

    entry_order.conditionsIgnoreRth = False
    entry_order.conditionsCancelOrder = False

    # Add MOC exit order
    exit_order = Order()
    exit_order.parentId = None
    exit_order.action = 'SELL' if raw_order.action == 'BUY' else 'BUY'
    exit_order.orderType = 'MOC'
    exit_order.totalQuantity = pos_size
    exit_order.orderRef = OrderRef(raw_order.strategy_model_string, raw_order.order_ref.trade_id, 'EXIT-1').ref
    exit_order.transmit = True

    return entry_order, exit_order


def moc_exit_order(parent_raw_entry_order, pos_size):
    exit_order = Order()
    exit_order.parentId = None
    exit_order.action = 'SELL' if parent_raw_entry_order.action == 'BUY' else 'BUY'
    exit_order.orderType = 'MOC'
    exit_order.totalQuantity = pos_size
    exit_order.orderRef = OrderRef(parent_raw_entry_order.strategy_model_string,
                                   parent_raw_entry_order.order_ref.trade_id, 'EXIT-1').ref
    exit_order.transmit = True

    return exit_order


def add_algo_dark_ice(baseOrder, displaySize: int, startTime='09:30:00 US/Eastern', endTime='16:00:00 US/Eastern',
                      allowPastEndTime=False):
    baseOrder.algoStrategy = "DarkIce"
    baseOrder.algoParams = []
    baseOrder.algoParams.append(TagValue("displaySize", str(displaySize)))
    baseOrder.algoParams.append(TagValue("startTime", startTime))
    baseOrder.algoParams.append(TagValue("endTime", endTime))
    baseOrder.algoParams.append(TagValue("allowPastEndTime", str(int(allowPastEndTime))))

    return baseOrder


def market_order(action, quantity, order_ref, tif='DAY'):
    assert tif in ['DAY', 'GTC', 'OPG', 'GTD', 'IOC', 'FOK']
    o = Order()
    o.orderId = None
    o.action = action
    o.orderType = 'MKT'
    o.totalQuantity = quantity
    o.outsideRth = False
    o.orderRef = order_ref
    o.tif = tif

    return o


def limit_order(action, quantity, limit_price, order_ref, ORTH=True, tif='DAY'):
    assert action in ['BUY', 'SELL']
    assert tif in ['DAY', 'GTC', 'OPG', 'GTD', 'IOC', 'FOK']
    assert ORTH in [True, False]

    quantity = int(quantity)
    o = Order()
    o.orderId = None
    o.action = action
    o.orderType = "LMT"
    o.totalQuantity = quantity
    o.lmtPrice = limit_price
    o.outsideRth = ORTH
    o.orderRef = order_ref
    o.tif = tif

    return o


def add_margin_condition(order, min_pct=None, max_pct=None, conjunction='AND'):
    assert isinstance(order, Order)
    assert min_pct is None or max_pct is None, 'Cannot set both max and min margin conditions in one instruction'
    assert conjunction in ['AND', 'OR'], "Order condition conjunction must be 'AND' or 'OR'"

    margin_condition = Create(OrderCondition.Margin)
    # isMore = True : margin percent is the minimum acceptable margin
    # isMore = False: margin percent is the maximum acceptable margin
    if min_pct is not None:
        margin_condition.percent = min_pct
        margin_condition.isMore = True
    elif max_pct is not None:
        margin_condition.percent = max_pct
        margin_condition.isMore = False
    else:
        LOG.error('No margin percent was passed to add_margin_condition.')
        raise ValueError('No margin percent was passed to add_margin_condition.')

    margin_condition.isConjunctionConnection = conjunction
    order.conditions.append(margin_condition)

    return order


def add_time_condition(order, start_datetime=None, end_datetime=None, conjunction='AND', orth=True):
    assert isinstance(order, Order)
    assert conjunction in ['AND', 'OR'], "Order conditioning conjunction must be 'AND' or 'OR'"
    # datetimes must be timezone aware

    # isMore = True : time is the earliest acceptable time
    # isMore = False: time is the latest acceptable time

    if start_datetime is not None:
        time_condition = Create(OrderCondition.Time)
        time_condition.time = datetime.strftime(start_datetime, '%Y%m%d %H:%M:%S ') + start_datetime.tzinfo.zone
        time_condition.isMore = True
        time_condition.isConjunctionConnection = conjunction
        order.conditions.append(time_condition)
    if end_datetime is not None:
        time_condition = Create(OrderCondition.Time)
        time_condition.time = datetime.strftime(end_datetime, '%Y%m%d %H:%M:%S ') + end_datetime.tzinfo.zone
        time_condition.isMore = False
        time_condition.isConjunctionConnection = conjunction
        order.conditions.append(time_condition)

    order.conditionsIgnoreRth = orth
    return order
