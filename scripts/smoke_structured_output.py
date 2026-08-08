def main() -> int:
    # ... (parser and client setup remains the same) ...

    failures = 0
    investment_plan = "Mock RM Plan: Buy NVDA due to data-center strength."
    trader_plan = "Mock Trader Plan: Market buy 100 shares."
    final_decision = "**Rating**: BUY\n**Executive Summary**: Growth path clear.\n**Investment Thesis**: Bull case holds."

    # 1) Research Manager
    print("\nRunning Research Manager...")
    try:
        rm = create_research_manager(deep_llm)
        rm_result = rm(_make_rm_state())
        investment_plan = rm_result["investment_plan"]
        _print_section("[1] Research Manager — investment_plan", investment_plan)
    except Exception as e:
        print(f"❌ Research Manager execution failed: {e}")
        failures += 1

    # 2) Trader
    print("\nRunning Trader...")
    try:
        trader = create_trader(quick_llm)
        trader_result = trader(_make_trader_state(investment_plan))
        trader_plan = trader_result["trader_investment_plan"]
        _print_section("[2] Trader — trader_investment_plan", trader_plan)
    except Exception as e:
        print(f"❌ Trader execution failed: {e}")
        failures += 1

    # 3) Portfolio Manager
    print("\nRunning Portfolio Manager...")
    try:
        pm = create_portfolio_manager(deep_llm)
        pm_result = pm(_make_pm_state(investment_plan, trader_plan))
        final_decision = pm_result["final_trade_decision"]
        _print_section("[3] Portfolio Manager — final_trade_decision", final_decision)
    except Exception as e:
        print(f"❌ Portfolio Manager execution failed: {e}")
        failures += 1

    # 4) SignalProcessor
    print("\nRunning SignalProcessor...")
    try:
        sp = SignalProcessor()
        rating = sp.process_signal(final_decision)
        _print_section("[4] SignalProcessor → rating", str(rating))
    except Exception as e:
        print(f"❌ SignalProcessor failed: {e}")
        failures += 1

    # 5) Structure checks
    print("\n" + "=" * 70 + "\nStructure checks\n" + "=" * 70)
    checks = [
        ("Research Manager", investment_plan, ["**Recommendation**:"]),
        ("Trader", trader_plan, ["**Action**:", "FINAL TRANSACTION PROPOSAL:"]),
        ("Portfolio Manager", final_decision, ["**Rating**:", "**Executive Summary**:", "**Investment Thesis**:"]),
    ]

    for name, text, required in checks:
        for marker in required:
            ok = marker in text
            print(f" {'PASS' if ok else 'FAIL'} {name}: contains {marker!r}")
            if not ok:
                failures += 1

    print()
    if failures:
        print(f"Smoke FAILED: {failures} issue(s) detected.")
        return 1
        
    print("Smoke PASSED: structured output → rendered markdown chain works for", args.provider)
    return 0
