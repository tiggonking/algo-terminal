import os
import pytest
from unittest.mock import MagicMock


def test_invalid_file(filewatcher):
    with pytest.raises(FileNotFoundError):
        filewatcher.validate_and_load_order_file('invalid_file_path.xxx')


def test_conflicting_max_pos(filewatcher):
    test_orders_df = filewatcher.load_file(os.getcwd() + '\\Test_Kit\\Test Data\\orders_file.csv')
    test_orders_df.iloc[0, test_orders_df.columns.get_loc('MaxPos')] = 5
    test_orders_df.iloc[2, test_orders_df.columns.get_loc('MaxPos')] = 8
    filewatcher.load_file = MagicMock(return_value=test_orders_df)
    os.path.isfile = MagicMock(return_value=True)
    with pytest.raises(ValueError) as e_info:
        filewatcher.validate_and_load_order_file('xxxx.csv')
    assert 'Conflicting or missing max positions settings for strategy' in e_info.value.args[0]


def test_conflicting_max_daily_entries(filewatcher):
    test_orders_df = filewatcher.load_file(os.getcwd() + '\\Test_Kit\\Test Data\\orders_file.csv')
    test_orders_df.iloc[0, test_orders_df.columns.get_loc('MaxDaily')] = 5
    test_orders_df.iloc[2, test_orders_df.columns.get_loc('MaxDaily')] = 8
    filewatcher.load_file = MagicMock(return_value=test_orders_df)
    os.path.isfile = MagicMock(return_value=True)
    with pytest.raises(ValueError) as e_info:
        filewatcher.validate_and_load_order_file('xxxx.csv')
    assert 'Conflicting or missing max daily entries settings' in e_info.value.args[0]


def test_missing_columns(filewatcher):
    test_orders_df = filewatcher.load_file(os.getcwd() + '\\Test_Kit\\Test Data\\orders_file.csv')
    for c in filewatcher.required_columns:
        df = test_orders_df.drop(columns=[c])
        filewatcher.load_file = MagicMock(return_value=df)
        os.path.isfile = MagicMock(return_value=True)
        with pytest.raises(ValueError) as e_info:
            filewatcher.validate_and_load_order_file('xxxx.csv')
        assert 'Missing column(s)' in e_info.value.args[0]


def test_invalid_file_type(filewatcher):
    os.path.isfile = MagicMock(return_value=True)
    with pytest.raises(TypeError) as e_info:
        filewatcher.validate_and_load_order_file('xxxx.xls')
    assert e_info.value.args[0] == 'only CSV files can be processed'


def test_file_not_loaded(filewatcher):
    os.path.isfile = MagicMock(return_value=True)
    filewatcher.load_file = MagicMock(return_value=None)
    with pytest.raises(ImportError) as e_info:
        filewatcher.validate_and_load_order_file('xxxx.csv')
    assert 'could not load order file' in e_info.value.args[0]

