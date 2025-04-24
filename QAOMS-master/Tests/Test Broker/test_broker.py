import pytest
from Test_Kit.Mocks.mock_broker import mock_broker


def test_request_nlv_in_unavailable_currency(api_account_values_dict):
    broker = mock_broker()
    broker.api.account_values = api_account_values_dict
    del broker.api.account_values[broker.api.account_id]['USD']
    with pytest.raises(ValueError) as e_info:
        broker.nlv(broker.api.account_id, 'USD')
    assert 'Before the OMS can trade in USD in account' in e_info.value.args[0]


