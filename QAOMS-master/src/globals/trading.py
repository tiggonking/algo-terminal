class TradingGlobals:

    def __init__(self):
        self.ib_lot_size = 100
        self.valid_exchanges = ['NASDAQ', 'NYSE', 'AMEX', 'ARCA', 'IDEALPRO', 'SMART']
        self.valid_currencies = ['AUD', 'USD']
        self.valid_markets = ['US', 'AU']
        self.valid_ib_security_types = ['STK', 'CASH', 'OPT', 'FUT', 'IND', 'FOP',
                                        'BAG', 'WAR', 'BOND', 'CMDTY', 'NEWS', 'FUND', 'CFD']
        self.supported_order_types = ['LMT', 'MKT']
        self.supported_ib_algos = ['DARKICE']
        self.supported_special_orders = ['Gap-Conditional', 'Child-MOC']
        # STK - stock( or ETF), OPT - option, FUT - future, IND - index, FOP - futures option, CASH - forex pair,
        # BAG - combo, WAR - warrant, BOND - bond, CMDTY - commodity, NEWS - news, FUND - mutual fund


TGL = TradingGlobals()