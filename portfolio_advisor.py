import datetime
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


@dataclass
class PortfolioPosition:
    ticker: str
    shares: float
    avg_price: float

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_price


def get_float_input(prompt: str, min_val: float = 0) -> float:
    while True:
        try:
            value = float(input(prompt))
            if value < min_val:
                print(f"Value must be at least {min_val}. Please try again.")
                continue
            return value
        except ValueError:
            print("Invalid number. Please try again.")


def get_ticker_input() -> str:
    while True:
        ticker = input("Enter ticker symbol to analyze: ").strip().upper()
        if ticker:
            return ticker
        print("Ticker cannot be empty. Please try again.")


def get_date_input() -> str:
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    user_input = input(f"Enter analysis date (YYYY-MM-DD) [default: {default_date}]: ").strip()
    if not user_input:
        return default_date
    try:
        datetime.datetime.strptime(user_input, "%Y-%m-%d")
        return user_input
    except ValueError:
        print(f"Invalid date format. Using default: {default_date}")
        return default_date


def parse_decision(decision_text: str) -> dict:
    result = {
        "rating": None,
        "price_target": None,
        "time_horizon": None,
        "summary": "",
    }

    for line in decision_text.split("\n"):
        line = line.strip()
        if line.startswith("**Rating**:"):
            result["rating"] = line.replace("**Rating**:", "").strip()
        elif line.startswith("**Price Target**:"):
            try:
                raw_val = line.replace("**Price Target**:", "").strip().replace("$", "").replace(",", "")
                result["price_target"] = float(raw_val)
            except ValueError:
                pass
        elif line.startswith("**Time Horizon**:"):
            result["time_horizon"] = line.replace("**Time Horizon**:", "").strip()
        elif line.startswith("**Executive Summary**:"):
            result["summary"] = line.replace("**Executive Summary**:", "").strip()

    return result


def calculate_recommendation(decision: dict, position: PortfolioPosition, portfolio_value: float) -> str:
    rating = decision.get("rating", "Hold")
    price_target = decision.get("price_target")
    time_horizon = decision.get("time_horizon", "unknown timeframe")
    summary = decision.get("summary", "")

    current_value = position.cost_basis
    allocation_pct = (current_value / portfolio_value * 100) if portfolio_value > 0 else 0

    lines = []
    lines.append("=" * 70)
    lines.append("PORTFOLIO ANALYSIS & RECOMMENDATION")
    lines.append("=" * 70)
    lines.append(f"")
    lines.append(f"Portfolio Value: ${portfolio_value:,.2f}")
    lines.append(f"Position: {position.shares:.0f} shares of {position.ticker} @ ${position.avg_price:.2f} avg")
    lines.append(f"Current Position Value: ${current_value:,.2f} ({allocation_pct:.1f}% of portfolio)")
    lines.append(f"")
    lines.append(f"Agent Consensus Rating: {rating}")
    if price_target:
        lines.append(f"Price Target: ${price_target:.2f}")
    if time_horizon:
        lines.append(f"Time Horizon: {time_horizon}")
    if summary:
        lines.append(f"Summary: {summary}")
    lines.append(f"")

    rating_lower = rating.lower() if rating else "hold"

    if rating_lower == "buy" or rating_lower == "overweight":
        lines.append("--- RECOMMENDED ACTION ---")
        if allocation_pct < 20:
            suggested_shares = int((portfolio_value * 0.10) / position.avg_price)
            lines.append(f"INCREASE position: Buy approximately {suggested_shares} more shares")
            lines.append(f"Target allocation: ~{allocation_pct + 10:.1f}% of portfolio")
            if price_target:
                lines.append(f"Buy below ${price_target:.2f} for optimal entry")
        elif allocation_pct < 40:
            suggested_shares = int((portfolio_value * 0.05) / position.avg_price)
            lines.append(f"MODERATELY INCREASE: Add approximately {suggested_shares} shares")
            if price_target:
                lines.append(f"Accumulate on dips below ${price_target:.2f}")
        else:
            lines.append(f"HOLD current position but maintain bullish outlook")
            lines.append(f"Consider trimming only if position exceeds 50% of portfolio")
        lines[-1] += f". Time horizon: {time_horizon}."

    elif rating_lower == "sell" or rating_lower == "underweight":
        lines.append("--- RECOMMENDED ACTION ---")
        if allocation_pct > 10:
            sell_pct = 50 if rating_lower == "sell" else 25
            shares_to_sell = int(position.shares * sell_pct / 100)
            lines.append(f"REDUCE position: Sell approximately {shares_to_sell} shares ({sell_pct}%)")
            if price_target:
                lines.append(f"Place sell orders near ${price_target:.2f}")
        elif position.shares > 0:
            sell_pct = 100 if rating_lower == "sell" else 50
            shares_to_sell = int(position.shares * sell_pct / 100)
            lines.append(f"EXIT or REDUCE: Sell {shares_to_sell} shares")
            if price_target:
                lines.append(f"Target exit price: ${price_target:.2f}")
        else:
            lines.append(f"AVOID entry at current levels")

    else:
        lines.append("--- RECOMMENDED ACTION ---")
        lines.append(f"HOLD: Maintain current position of {position.shares:.0f} shares")
        lines.append(f"Do not add or reduce at this time")
        if price_target:
            if price_target > position.avg_price:
                lines.append(f"Consider taking partial profits above ${price_target:.2f}")
            elif price_target < position.avg_price:
                lines.append(f"Set a stop-loss at ${price_target:.2f} to limit downside")
        lines.append(f"Re-evaluate in {time_horizon}")

    lines.append("")
    lines.append("--- RISK MANAGEMENT ---")
    if position.shares > 0:
        stop_loss_price = position.avg_price * 0.92
        lines.append(f"Stop-loss suggestion: ${stop_loss_price:.2f} (8% below your average cost)")
        max_loss = position.shares * (position.avg_price - stop_loss_price)
        lines.append(f"Maximum potential loss at stop: ${max_loss:,.2f} ({max_loss / portfolio_value * 100:.1f}% of portfolio)")
    lines.append("")
    lines.append("=" * 70)
    lines.append("DISCLAIMER: This is AI-generated analysis, not financial advice.")
    lines.append("Always consult a licensed financial advisor before making investment decisions.")
    lines.append("=" * 70)

    return "\n".join(lines)


def main():
    print("=" * 60)
    print("  TradingAgents - Portfolio Advisor")
    print("=" * 60)
    print()
    print("This tool analyzes a stock and gives personalized recommendations")
    print("based on your portfolio position.")
    print()

    portfolio_value = get_float_input("What is your total portfolio value in USD? $", min_val=1)
    ticker = get_ticker_input()
    shares = get_float_input(f"How many shares of {ticker} do you currently hold? ", min_val=0)
    avg_price = get_float_input(f"What is your average cost per share for {ticker}? $", min_val=0.01)
    trade_date = get_date_input()

    position = PortfolioPosition(ticker=ticker, shares=shares, avg_price=avg_price)

    print()
    print(f"Running multi-agent analysis for {ticker}...")
    print(f"This may take a few minutes as agents research and debate.")
    print()

    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "openai"
    config["deep_think_llm"] = "gpt-4o"
    config["quick_think_llm"] = "gpt-4o-mini"

    ta = TradingAgentsGraph(debug=False, config=config)
    _, decision = ta.propagate(ticker, trade_date)

    print()
    print()
    parsed = parse_decision(decision)
    recommendation = calculate_recommendation(parsed, position, portfolio_value)
    print(recommendation)


if __name__ == "__main__":
    main()
