#!/usr/bin/env python3
"""
Test script for AccountV2 class demonstrating Pydantic v2 validation and enum usage.
"""

from account_v2 import AccountV2, IBAccountType, IBPlatform, IBAlgo, ValidPorts


def test_valid_account():
    """Test creating a valid account"""
    print("Testing valid account creation...")
    
    account = AccountV2(
        id=12345,
        alias="Test Account",
        ib_type=IBAccountType.TRADING,
        ib_algo=IBAlgo.DARKICE,
        ib_platform=IBPlatform.TWS,
        ib_port=7497,  # TWS Paper
        ib_client_id=1,
        strategy_allocations={"STRATEGY_1": 0.5, "STRATEGY_2": 0.3},
        strategy_security_types={"STRATEGY_1": ["STK", "CASH"], "STRATEGY_2": ["STK"]}
    )
    
    print(f"✅ Valid account created: {account}")
    print(f"   Account type: {account.ib_type.value}")
    print(f"   Platform: {account.ib_platform.value}")
    print(f"   Port: {account.ib_port}")
    print(f"   Strategies: {list(account.strategy_allocations.keys())}")
    return account


def test_fund_advisory_account():
    """Test creating a fund advisory account (must have client_id = 0)"""
    print("\nTesting fund advisory account...")
    
    try:
        account = AccountV2(
            id=67890,
            alias="Fund Advisory Account",
            ib_type=IBAccountType.FUND_ADVISORY,
            ib_algo=IBAlgo.EMPTY,
            ib_platform=IBPlatform.TWS,
            ib_port=7496,  # TWS Live
            ib_client_id=0,  # Must be 0 for fund advisory
            strategy_allocations={"STRATEGY_1": 1.0},
            strategy_security_types={"STRATEGY_1": ["STK"]}
        )
        print(f"✅ Fund advisory account created: {account}")
    except ValueError as e:
        print(f"❌ Fund advisory account validation failed: {e}")


def test_managed_account():
    """Test creating a managed account (must have parent account)"""
    print("\nTesting managed account...")
    
    try:
        account = AccountV2(
            id=11111,
            alias="Managed Account",
            ib_type=IBAccountType.MANAGED,
            ib_algo=IBAlgo.EMPTY,
            ib_platform=IBPlatform.IBG,
            ib_port=4001,  # IB Gateway Live
            ib_client_id=2,
            parent_account="PARENT_ACCOUNT_123",  # Required for managed accounts
            strategy_allocations={"STRATEGY_1": 0.8},
            strategy_security_types={"STRATEGY_1": ["STK"]}
        )
        print(f"✅ Managed account created: {account}")
    except ValueError as e:
        print(f"❌ Managed account validation failed: {e}")


def test_invalid_port():
    """Test invalid port validation"""
    print("\nTesting invalid port validation...")
    
    try:
        account = AccountV2(
            id=22222,
            alias="Invalid Port Account",
            ib_type=IBAccountType.TRADING,
            ib_algo=IBAlgo.EMPTY,
            ib_platform=IBPlatform.TWS,
            ib_port=9999,  # Invalid port
            ib_client_id=1,
            strategy_allocations={"STRATEGY_1": 0.5},
            strategy_security_types={"STRATEGY_1": ["STK"]}
        )
        print(f"❌ Should have failed: {account}")
    except ValueError as e:
        print(f"✅ Port validation caught error: {e}")


def test_invalid_allocation():
    """Test invalid strategy allocation validation"""
    print("\nTesting invalid allocation validation...")
    
    try:
        account = AccountV2(
            id=33333,
            alias="Invalid Allocation Account",
            ib_type=IBAccountType.TRADING,
            ib_algo=IBAlgo.EMPTY,
            ib_platform=IBPlatform.TWS,
            ib_port=7497,
            ib_client_id=1,
            strategy_allocations={"STRATEGY_1": 1.5},  # Invalid: > 1.0
            strategy_security_types={"STRATEGY_1": ["STK"]}
        )
        print(f"❌ Should have failed: {account}")
    except ValueError as e:
        print(f"✅ Allocation validation caught error: {e}")


def test_enum_values():
    """Test enum values and their string representations"""
    print("\nTesting enum values...")
    
    print(f"IB Account Types: {[t.value for t in IBAccountType]}")
    print(f"IB Platforms: {[p.value for p in IBPlatform]}")
    print(f"IB Algorithms: {[a.value for a in IBAlgo]}")
    print(f"Valid Ports: {[p.value for p in ValidPorts]}")
    
    # Test enum comparison
    account_type = IBAccountType.TRADING
    print(f"Account type comparison: {account_type == IBAccountType.TRADING}")
    print(f"Account type value: {account_type.value}")


def test_serialization():
    """Test JSON serialization/deserialization"""
    print("\nTesting serialization...")
    
    account = AccountV2(
        id=44444,
        alias="Serialization Test",
        ib_type=IBAccountType.TRADING,
        ib_algo=IBAlgo.EMPTY,
        ib_platform=IBPlatform.TWS,
        ib_port=7497,
        ib_client_id=1,
        strategy_allocations={"STRATEGY_1": 0.7},
        strategy_security_types={"STRATEGY_1": ["STK"]}
    )
    
    # Convert to dict
    account_dict = account.model_dump()
    print(f"✅ Account serialized to dict: {account_dict}")
    
    # Convert back to AccountV2
    reconstructed_account = AccountV2.model_validate(account_dict)
    print(f"✅ Account reconstructed: {reconstructed_account}")
    
    # Test JSON
    account_json = account.model_dump_json()
    print(f"✅ Account JSON: {account_json}")


if __name__ == "__main__":
    print("🧪 Testing AccountV2 Class\n")
    print("=" * 50)
    
    # Run all tests
    test_valid_account()
    test_fund_advisory_account()
    test_managed_account()
    test_invalid_port()
    test_invalid_allocation()
    test_enum_values()
    test_serialization()
    
    print("\n" + "=" * 50)
    print("✅ All tests completed!") 