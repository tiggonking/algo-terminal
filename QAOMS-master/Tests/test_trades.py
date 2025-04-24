from Test_Kit.Mocks.mock_broker import mock_broker


def test_next_exit_id_from_no_exits(fixture_tsla_trade):
    fixture_tsla_trade.exit_order_records = []
    broker = mock_broker()
    assert fixture_tsla_trade.next_exit_id(broker) == 1

# TODO: next_exit_id from properly formatted exit order records
# TODO: next_exit_id from improperly formatted exit order records
