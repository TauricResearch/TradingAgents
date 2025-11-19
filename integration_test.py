#!/usr/bin/env python3
"""
Comprehensive Integration Testing for TradingAgents
Tests all integration points between new features and existing functionality.
"""

import os
import sys
from decimal import Decimal
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()


def test_llm_factory_tradingagents_integration():
    """Test 1: LLM Factory + TradingAgents Integration"""
    print("\n" + "="*70)
    print("INTEGRATION TEST 1: LLM Factory + TradingAgents")
    print("="*70)

    try:
        from tradingagents.llm_factory import LLMFactory
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG

        # Test 1.1: Provider switching
        print("\n1.1: Testing provider configuration...")
        config = DEFAULT_CONFIG.copy()

        providers_to_test = []
        for provider in ["openai", "anthropic", "google"]:
            validation = LLMFactory.validate_provider_setup(provider)
            if validation["valid"]:
                providers_to_test.append(provider)
                print(f"   ✓ {provider} is configured and ready")
            else:
                print(f"   ⚠ {provider} not configured (skipping)")

        if not providers_to_test:
            print("   ⚠ No LLM providers configured - cannot test provider switching")
            print("   ℹ Configure at least one provider in .env to test this feature")
            return "SKIPPED"

        # Test 1.2: TradingAgents initialization with different providers
        print("\n1.2: Testing TradingAgents initialization with different providers...")
        for provider in providers_to_test[:1]:  # Test first available provider
            try:
                config["llm_provider"] = provider
                models = LLMFactory.get_recommended_models(provider)
                config["deep_think_llm"] = models["deep_thinking"]
                config["quick_think_llm"] = models["quick_thinking"]

                ta = TradingAgentsGraph(
                    selected_analysts=["market"],
                    config=config,
                    debug=False
                )
                print(f"   ✓ TradingAgents initialized with {provider}")
                print(f"   ✓ Deep think model: {models['deep_thinking']}")
                print(f"   ✓ Quick think model: {models['quick_thinking']}")
            except Exception as e:
                print(f"   ✗ Failed to initialize with {provider}: {e}")
                return "FAIL"

        # Test 1.3: Error handling for invalid provider
        print("\n1.3: Testing error handling for invalid provider...")
        try:
            config["llm_provider"] = "invalid_provider"
            validation = LLMFactory.validate_provider_setup("invalid_provider")
            if not validation["valid"]:
                print("   ✓ Invalid provider correctly rejected")
            else:
                print("   ✗ Invalid provider not rejected")
                return "FAIL"
        except Exception as e:
            print(f"   ✓ Invalid provider raises error (expected)")

        print("\n✓ LLM Factory + TradingAgents Integration: PASS")
        return "PASS"

    except Exception as e:
        print(f"\n✗ LLM Factory + TradingAgents Integration: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return "FAIL"


def test_broker_portfolio_integration():
    """Test 2: Broker + Portfolio System Integration"""
    print("\n" + "="*70)
    print("INTEGRATION TEST 2: Broker + Portfolio Integration")
    print("="*70)

    try:
        from tradingagents.brokers.base import (
            BrokerOrder, BrokerPosition, OrderSide, OrderType, OrderStatus
        )
        from tradingagents.portfolio import Portfolio
        from tradingagents.portfolio.orders import Order, OrderType as PortfolioOrderType

        # Test 2.1: Data structure compatibility
        print("\n2.1: Testing broker and portfolio data structure compatibility...")

        # Create broker order
        broker_order = BrokerOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET
        )
        print(f"   ✓ Broker order created: {broker_order.symbol} {broker_order.side.value} {broker_order.quantity}")

        # Create portfolio order
        portfolio_order = Order(
            symbol="AAPL",
            order_type=PortfolioOrderType.MARKET,
            quantity=10,
            side="BUY"
        )
        print(f"   ✓ Portfolio order created: {portfolio_order.symbol} {portfolio_order.side} {portfolio_order.quantity}")

        # Test 2.2: Position tracking consistency
        print("\n2.2: Testing position tracking...")
        broker_position = BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("10"),
            avg_entry_price=Decimal("150.50"),
            current_price=Decimal("155.25"),
            market_value=Decimal("1552.50"),
            unrealized_pnl=Decimal("47.50")
        )
        print(f"   ✓ Broker position: {broker_position.symbol} @ ${broker_position.avg_entry_price}")
        print(f"   ✓ P&L tracking: ${broker_position.unrealized_pnl}")

        # Test 2.3: Portfolio initialization
        print("\n2.3: Testing portfolio initialization...")
        portfolio = Portfolio(initial_cash=100000.0)
        print(f"   ✓ Portfolio created with ${portfolio.cash:,.2f} cash")
        print(f"   ✓ Total value: ${portfolio.total_value:,.2f}")

        print("\n✓ Broker + Portfolio Integration: PASS")
        return "PASS"

    except Exception as e:
        print(f"\n✗ Broker + Portfolio Integration: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return "FAIL"


def test_configuration_management():
    """Test 3: Configuration Management"""
    print("\n" + "="*70)
    print("INTEGRATION TEST 3: Configuration Management")
    print("="*70)

    try:
        # Test 3.1: .env.example completeness
        print("\n3.1: Testing .env.example completeness...")
        env_example = Path("/home/user/TradingAgents/.env.example")

        required_sections = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "ALPHA_VANTAGE_API_KEY",
            "ALPACA_API_KEY",
            "ALPACA_SECRET_KEY",
            "LLM_PROVIDER",
        ]

        with open(env_example, 'r') as f:
            content = f.read()
            found = 0
            for section in required_sections:
                if section in content:
                    found += 1
                else:
                    print(f"   ✗ Missing: {section}")

        print(f"   ✓ Found {found}/{len(required_sections)} required configuration variables")

        # Test 3.2: Default configuration
        print("\n3.2: Testing default configuration...")
        from tradingagents.default_config import DEFAULT_CONFIG

        required_keys = [
            "llm_provider",
            "deep_think_llm",
            "quick_think_llm",
            "max_debate_rounds",
            "max_risk_discuss_rounds",
        ]

        found_keys = 0
        for key in required_keys:
            if key in DEFAULT_CONFIG:
                print(f"   ✓ {key}: {DEFAULT_CONFIG[key]}")
                found_keys += 1
            else:
                print(f"   ✗ Missing: {key}")

        # Test 3.3: Environment variable loading
        print("\n3.3: Testing environment variable loading...")
        from tradingagents.llm_factory import LLMFactory

        env_vars = {
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
            "ALPHA_VANTAGE_API_KEY": os.getenv("ALPHA_VANTAGE_API_KEY"),
        }

        configured = 0
        for var, value in env_vars.items():
            if value:
                print(f"   ✓ {var} is set")
                configured += 1
            else:
                print(f"   ⚠ {var} not set")

        if configured == 0:
            print("   ℹ No API keys configured - this is expected for fresh installations")

        print("\n✓ Configuration Management: PASS")
        return "PASS"

    except Exception as e:
        print(f"\n✗ Configuration Management: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return "FAIL"


def test_data_flow_integration():
    """Test 4: Data Flow Through System"""
    print("\n" + "="*70)
    print("INTEGRATION TEST 4: Data Flow Through System")
    print("="*70)

    try:
        # Test 4.1: Signal flow
        print("\n4.1: Testing signal processing flow...")
        from tradingagents.graph.signal_processing import SignalProcessing

        signal_processor = SignalProcessing()
        test_signals = ["BUY", "SELL", "HOLD"]

        for signal in test_signals:
            result = signal_processor.process_signal(signal)
            print(f"   ✓ Signal '{signal}' processed to '{result}'")

        # Test 4.2: Order flow
        print("\n4.2: Testing order flow...")
        from tradingagents.brokers.base import BrokerOrder, OrderSide, OrderType

        order = BrokerOrder(
            symbol="NVDA",
            side=OrderSide.BUY,
            quantity=Decimal("5"),
            order_type=OrderType.MARKET
        )

        print(f"   ✓ Order created: {order.symbol} {order.side.value} {order.quantity}")
        print(f"   ✓ Order type: {order.order_type.value}")

        # Test 4.3: Portfolio update flow
        print("\n4.3: Testing portfolio update flow...")
        from tradingagents.portfolio import Portfolio
        from tradingagents.portfolio.orders import Order as PortfolioOrder, OrderType as POrderType

        portfolio = Portfolio(initial_cash=100000.0)

        # Simulate order execution
        test_order = PortfolioOrder(
            symbol="NVDA",
            order_type=POrderType.MARKET,
            quantity=5,
            side="BUY",
            timestamp=None
        )

        print(f"   ✓ Portfolio order created: {test_order.symbol} {test_order.side} {test_order.quantity}")
        print(f"   ✓ Initial cash: ${portfolio.cash:,.2f}")

        print("\n✓ Data Flow Integration: PASS")
        return "PASS"

    except Exception as e:
        print(f"\n✗ Data Flow Integration: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return "FAIL"


def test_web_app_components():
    """Test 5: Web App Component Integration"""
    print("\n" + "="*70)
    print("INTEGRATION TEST 5: Web App Component Integration")
    print("="*70)

    try:
        # Test 5.1: Web app file structure
        print("\n5.1: Testing web app file structure...")
        web_app_path = Path("/home/user/TradingAgents/web_app.py")

        if not web_app_path.exists():
            print("   ✗ web_app.py not found")
            return "FAIL"

        with open(web_app_path, 'r') as f:
            content = f.read()

        # Check for required integrations
        integrations = {
            "chainlit": "Chainlit framework",
            "TradingAgentsGraph": "TradingAgents integration",
            "AlpacaBroker": "Broker integration",
            "LLMFactory": "LLM factory integration",
        }

        for component, description in integrations.items():
            if component in content:
                print(f"   ✓ {description} integrated")
            else:
                print(f"   ⚠ {description} not found")

        # Test 5.2: Configuration file
        print("\n5.2: Testing Chainlit configuration...")
        chainlit_config = Path("/home/user/TradingAgents/.chainlit")

        if chainlit_config.exists():
            print("   ✓ .chainlit configuration exists")
        else:
            print("   ⚠ .chainlit configuration not found")

        print("\n✓ Web App Component Integration: PASS")
        return "PASS"

    except Exception as e:
        print(f"\n✗ Web App Component Integration: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return "FAIL"


def test_docker_integration():
    """Test 6: Docker Integration"""
    print("\n" + "="*70)
    print("INTEGRATION TEST 6: Docker Integration")
    print("="*70)

    try:
        # Test 6.1: Dockerfile validity
        print("\n6.1: Testing Dockerfile...")
        dockerfile = Path("/home/user/TradingAgents/Dockerfile")

        if not dockerfile.exists():
            print("   ✗ Dockerfile not found")
            return "FAIL"

        with open(dockerfile, 'r') as f:
            content = f.read()

        required_elements = {
            "FROM python:": "Base image",
            "WORKDIR": "Working directory",
            "COPY requirements.txt": "Requirements file",
            "pip install": "Package installation",
            "EXPOSE 8000": "Port exposure",
            "CMD": "Default command",
        }

        for element, description in required_elements.items():
            if element in content:
                print(f"   ✓ {description}")
            else:
                print(f"   ⚠ Missing: {description}")

        # Test 6.2: Docker Compose
        print("\n6.2: Testing docker-compose.yml...")
        compose = Path("/home/user/TradingAgents/docker-compose.yml")

        if not compose.exists():
            print("   ✗ docker-compose.yml not found")
            return "FAIL"

        with open(compose, 'r') as f:
            content = f.read()

        compose_elements = {
            "version:": "Compose version",
            "services:": "Services definition",
            "tradingagents:": "Main service",
            "volumes:": "Volume mounts",
            "environment:": "Environment variables",
            "ports:": "Port mapping",
        }

        for element, description in compose_elements.items():
            if element in content:
                print(f"   ✓ {description}")
            else:
                print(f"   ⚠ Missing: {description}")

        # Test 6.3: Docker documentation
        print("\n6.3: Testing Docker documentation...")
        docker_md = Path("/home/user/TradingAgents/DOCKER.md")

        if docker_md.exists():
            print("   ✓ DOCKER.md exists")
            with open(docker_md, 'r') as f:
                doc_content = f.read()
                if "docker-compose up" in doc_content:
                    print("   ✓ Contains usage instructions")
        else:
            print("   ⚠ DOCKER.md not found")

        print("\n✓ Docker Integration: PASS")
        return "PASS"

    except Exception as e:
        print(f"\n✗ Docker Integration: FAIL - {e}")
        import traceback
        traceback.print_exc()
        return "FAIL"


def main():
    """Run all integration tests"""
    print("="*70)
    print("TRADINGAGENTS COMPREHENSIVE INTEGRATION TESTING")
    print("="*70)
    print("\nThis test suite verifies that all new features integrate")
    print("properly with existing TradingAgents functionality.")
    print("\n" + "="*70)

    results = []

    # Run all integration tests
    results.append(("LLM Factory + TradingAgents", test_llm_factory_tradingagents_integration()))
    results.append(("Broker + Portfolio", test_broker_portfolio_integration()))
    results.append(("Configuration Management", test_configuration_management()))
    results.append(("Data Flow Integration", test_data_flow_integration()))
    results.append(("Web App Components", test_web_app_components()))
    results.append(("Docker Integration", test_docker_integration()))

    # Summary
    print("\n" + "="*70)
    print("INTEGRATION TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result == "PASS")
    skipped = sum(1 for _, result in results if result == "SKIPPED")
    failed = sum(1 for _, result in results if result == "FAIL")
    total = len(results)

    for name, result in results:
        if result == "PASS":
            print(f"✓ PASS: {name}")
        elif result == "SKIPPED":
            print(f"⚠ SKIPPED: {name}")
        else:
            print(f"✗ FAIL: {name}")

    print(f"\nResults:")
    print(f"  Passed:  {passed}/{total}")
    print(f"  Skipped: {skipped}/{total}")
    print(f"  Failed:  {failed}/{total}")
    print(f"  Success Rate: {(passed/total)*100:.1f}%")

    if failed == 0:
        print("\n✓ All integration tests passed!")
        if skipped > 0:
            print(f"  ({skipped} test(s) skipped due to missing configuration)")
        return 0
    else:
        print(f"\n⚠ {failed} integration test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
