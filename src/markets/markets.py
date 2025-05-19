from dataclasses import dataclass
from datetime import datetime, date, timedelta
from ibapi.contract import Contract
import src.utils.utilities as util
from globals.trading import TGL
from zoneinfo import ZoneInfo


def get_market_from_exchange(exchange):
    if exchange.upper() in ['NYSE', 'NASDAQ', 'ARCA', 'AMEX']:
        return Market('US')
    elif exchange.upper() in ['ASX']:
        return Market('AU')
    else:
        return None


class Market:
    # identifies a trading market, and contains data about market hours
    def __init__(self, market_code):
        assert market_code in TGL.valid_markets
        self.code = market_code
        self.tz = util.case(market_code, ['US', 'AU'], ['US/Eastern', 'Australia/NSW'], 'Update with new market')
        self.zone_info = util.case(market_code, ['US', 'AU'], [ZoneInfo('America/New_York'),
                                                               ZoneInfo('Australia/Sydney')], 'Update with new market')
        self.currency = util.case(market_code, ['US', 'AU'], ['USD', 'AUD'], 'Update with new market')
        self.session_list = []  # list of Session Objects from self.get_market_sessions()
        self.sessions_last_updated = datetime(2000, 1, 1)

    def update_market_sessions(self, broker):
        assert self.code in TGL.valid_markets
        if self.code == 'US':

            cd_orth, cd_rth, n = None, None, 0

            # very hard to find a single contract/exchange where IB observes normal RTH/ORTH hours.  Instead, use
            # two contracts here for RTH and ORTH hour settings.
            while not cd_rth:
                n += 1
                c_rth = Contract()
                c_rth.symbol = 'NYID'
                c_rth.currency = 'USD'
                c_rth.exchange = 'NYSE'
                c_rth.secType = 'IND'

                cds = broker.get_contract_details(c_rth)
                if cds:
                    cd_rth = cds[0]

                if n > 20:
                    raise ConnectionError('Could not retrieve market session time data for contract NYID.')
            assert cd_rth.timeZoneId == self.tz

            n = 0
            while not cd_orth:
                n += 1
                c_orth = Contract()
                c_orth.symbol = 'SPY'
                c_orth.currency = 'USD'
                c_orth.exchange = 'SMART'
                c_orth.secType = 'STK'

                cds = broker.get_contract_details(c_orth)
                if cds:
                    cd_orth = cds[0]

                if n > 20:
                    raise ConnectionError('Could not retrieve market session time data for contract SPY.')
            assert cd_orth.timeZoneId == self.tz

            timezone = cd_orth.timeZoneId

            trading_hours = dict({h[:8]: h for h in cd_orth.tradingHours.split(';')})
            liquid_hours = dict({h[:8]: h for h in cd_rth.liquidHours.split(';')})

        elif self.code == 'AU':
            c = Contract()
            c.symbol = 'BHP'
            c.currency = 'AUD'
            c.exchange = 'ASX'
            c.secType = 'STK'
            cd = broker.get_contract_details(c)[0]
            assert cd.timeZoneId == self.tz
            trading_hours = dict({h[:8]: h for h in cd.tradingHours.split(';')})
            liquid_hours = dict({h[:8]: h for h in cd.liquidHours.split(';')})
            timezone = cd.timeZoneId
        else:
            raise ValueError('Invalid Market object passed to market.update_market_sessions')

        existing_session_dates = [s.trading_date for s in self.session_list]

        for k, v in liquid_hours.items():
            lh = v
            th = trading_hours[k]
            t_date = datetime.strptime(k, '%Y%m%d').date()
            if t_date not in existing_session_dates and v.split(':')[1] != 'CLOSED':
                session = Session(datetime.strptime(k, '%Y%m%d').date(),
                                  datetime.strptime(lh.split("-")[0], '%Y%m%d:%H%M').replace(tzinfo=ZoneInfo(timezone)),
                                  datetime.strptime(lh.split("-")[1][:13], '%Y%m%d:%H%M').replace(
                                      tzinfo=ZoneInfo(timezone)),
                                  datetime.strptime(th.split("-")[0], '%Y%m%d:%H%M').replace(
                                      tzinfo=ZoneInfo(timezone)),
                                  datetime.strptime(th.split("-")[1][:13], '%Y%m%d:%H%M').replace(
                                      tzinfo=ZoneInfo(timezone))
                                  )
                self.session_list.append(session)

        if self.code == 'AU':
            # can't get a reliable instrument from IB, so manual adjusting here
            for s in self.session_list:
                s.liquid_open = s.liquid_open.replace(hour=10, minute=0)
                s.liquid_close = s.liquid_close.replace(hour=16, minute=0)
                s.preopen = s.preopen.replace(hour=10, minute=0)
                s.aftermarket_close = s.aftermarket_close.replace(hour=10, minute=0)

        self.session_list.sort(key=lambda x: x.trading_date)

        self.sessions_last_updated = self.current_time

    @property
    def todays_session(self):
        cs = None
        if self.session_list:
            cs = [s for s in self.session_list if s.trading_date == self.current_time.date()]
            if cs:
                cs = cs[0]
            else:
                cs = None
        return cs

    @property
    def current_time(self):
        return datetime.now(self.zone_info)

    @property
    def next_session(self):
        ns = None
        if self.session_list:
            ns = [s for s in self.session_list if s.trading_date > self.current_time.date()]
            if ns:
                ns.sort(key=lambda s: s.trading_date)
                ns = ns[0]
        return ns

    @property
    def EOD_data_next_available(self):
        # what time is the next EOD data available

        nadt = datetime(2200, 1, 1)
        if self.todays_session:
            if self.current_time < self.todays_session.aftermarket_close + timedelta(hours=3):
                nadt = self.todays_session.aftermarket_close + timedelta(hours=3)
            else:
                nadt = self.current_time
        elif self.next_session:
            nadt = self.next_session.aftermarket_close + timedelta(hours=3)

        return nadt


@dataclass
class Session:
    # defines a market session
    trading_date: date
    liquid_open: datetime
    liquid_close: datetime
    preopen: datetime = None
    aftermarket_close: datetime = None


def default_session(market, market_datetime):
    market_datetime = market_datetime.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=market.zone_info)

    if market.code == 'US':
        session = Session(trading_date=market_datetime.date(),
                          liquid_open=market_datetime.replace(hour=9, minute=30),
                          liquid_close=market_datetime.replace(hour=16, minute=0),
                          preopen=market_datetime.replace(hour=4, minute=0),
                          aftermarket_close=market_datetime.replace(hour=20, minute=0)
                          )
    elif market.code == 'ASX':
        session = Session(trading_date=market_datetime.date(),
                          liquid_open=market_datetime.replace(hour=10),
                          liquid_close=market_datetime.replace(hour=16),
                          preopen=market_datetime.replace(hour=10),
                          aftermarket_close=market_datetime.replace(hour=16)
                          )
    else:
        session = None
    return session


US_MARKET = Market('US')
