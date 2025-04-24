from broker import BrokerApp
import pytest


class mock_broker(BrokerApp):

    def __init__(self, account_id='DU2477234', account_alias='Test', port='127.0.0.1', client_id=100):
        super().__init__(account_id, account_alias, port, client_id)

