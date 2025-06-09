import os
import sys

# Add the project root directory to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.insert(0, project_root)

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
import pytz
from src.account.nav_monitor import NAVMonitor
from src.markets.markets import US_MARKET
from src.config.globals.config import OMS_CONFIG
from src.broker.broker import BrokerApp
from src.ib_api.interface.ib_api import IB_API
import time

@pytest.fixture(scope="module")
def ib_api():
    """Create a real connection to IB API"""
    api = IB_API(
        account_id="DUN049246",  # Paper trading account ID
        account_alias="MIT-ALPHA",
        port=7497,  # Paper trading port
        client_id=1
    )
    
    # Connect to TWS/IB Gateway
    api.open_port_connection()
    
    # Wait for connection to be established
    time.sleep(2)
    
    yield api
    
    # Cleanup
    api.disconnect()

@pytest.fixture(scope="module")
def broker_app(ib_api):
    """Create a broker app instance with real IB API"""
    broker = BrokerApp(
        account_id="DUN049246",
        account_alias="MIT_ALPHA",
        ib_type="INDIVIDUAL",
        ib_platform="TWS",
        ib_port=7497,
        ib_client_id=1
    )
    broker.api = ib_api
    return broker

@pytest.fixture(scope="module")
def nav_monitor(broker_app):
    """Create NAV monitor instance"""
    class MockOMS:
        def __init__(self):
            self.trading_accounts = [broker_app]
    
    monitor = NAVMonitor(MockOMS())
    yield monitor
    monitor.keep_alive = False

def test_api_connection(ib_api):
    """Test that we can connect to IB API"""
    assert ib_api.isConnected()
    assert "DUN049246" in ib_api.connected_accounts

def test_account_values(ib_api):
    """Test that we can retrieve account values"""
    # Request account updates
    ib_api.reqAccountUpdates(True, "DUN049246")
    time.sleep(2)  # Wait for data to arrive
    
    # Check we have account values
    assert "DUN049246" in ib_api.account_values
    assert "BASE" in ib_api.account_values["DUN049246"]
    
    # Check for NetLiquidation value
    base_values = ib_api.account_values["DUN049246"]["BASE"]
    assert "NetLiquidation" in base_values
    assert isinstance(base_values["NetLiquidation"], (Decimal, float, int))

def test_nav_retrieval(broker_app):
    """Test retrieving NAV through broker app"""
    nav = broker_app.nlv(account_id="DUN049246", currency="BASE", refresh=True)
    assert isinstance(nav, (Decimal, float))
    assert nav >= 0  # NAV should be non-negative

def test_nav_monitoring(nav_monitor):
    """Test the NAV monitoring functionality"""
    # Force a NAV update
    nav_monitor.monitor_navs()
    time.sleep(2)  # Wait for update to complete
    
    # Check that NAV was recorded
    account = nav_monitor.oms.trading_accounts[0]
    assert account.last_nav_write is not None
    
    # Test NAV calculation with funds change
    OMS_CONFIG.config = {
        "Funds": [
            ["DUN049246", datetime.now().date(), 50000],
            ["DUN049246", (datetime.now() - timedelta(days=30)).date(), 25000]
        ]
    }
    
    # Get current NAV
    broker = [b for b in BrokerApp._instances if "DUN049246" in b.api.connected_accounts][0]
    nav = broker.nlv(account_id="DUN049246", currency="BASE", refresh=True)
    
    # Export NAV to file
    result = nav_monitor.export_nav_to_file(account, nav)
    assert result is True

def test_nav_update_frequency(nav_monitor):
    """Test NAV update frequency"""
    initial_time = datetime.now(pytz.timezone('US/Eastern'))
    
    # Wait for next scheduled update
    time.sleep(60)  # Wait a minute
    nav_monitor.monitor_navs()
    
    account = nav_monitor.oms.trading_accounts[0]
    assert account.last_nav_write > initial_time
