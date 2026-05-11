import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        from tradingagents.backtesting.cli import main as backtest_main
        backtest_main()
    else:
        print("Usage: python -m tradingagents backtest [options]")
        print("       python -m tradingagents.backtesting [options]")
        sys.exit(1)


main()
