"""Portfolio analysis graph coordinator."""
import concurrent.futures
from typing import Dict, List, Any, Tuple
import yfinance as yf
from datetime import datetime

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.portfolio.models import Portfolio, Position, PortfolioAnalysisResult
from tradingagents.portfolio.metrics import calculate_portfolio_metrics
from tradingagents.default_config import DEFAULT_CONFIG


class PortfolioAnalysisGraph:
    """Coordinates portfolio-level analysis across multiple stocks."""

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        debug=False,
        config: Dict[str, Any] = None,
    ):
        """
        Initialize portfolio analysis graph.

        Args:
            selected_analysts: List of analyst types to use
            debug: Whether to enable debug mode
            config: Configuration dictionary
        """
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.selected_analysts = selected_analysts

        # We'll create individual trading graphs per stock as needed
        self.trading_graphs: Dict[str, TradingAgentsGraph] = {}

    def _get_current_prices(self, tickers: List[str], analysis_date: str) -> Dict[str, float]:
        """
        Fetch current prices for tickers.

        Args:
            tickers: List of ticker symbols
            analysis_date: Analysis date (YYYY-MM-DD)

        Returns:
            Dictionary mapping tickers to prices
        """
        prices = {}
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                # Get the historical data up to analysis date
                hist = stock.history(period="5d", end=analysis_date)
                if not hist.empty:
                    prices[ticker] = float(hist['Close'].iloc[-1])
                else:
                    print(f"Warning: No price data for {ticker}")
                    prices[ticker] = None
            except Exception as e:
                print(f"Error fetching price for {ticker}: {e}")
                prices[ticker] = None

        return prices

    def _analyze_single_stock(
        self,
        ticker: str,
        analysis_date: str
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Analyze a single stock using the trading agents framework.

        Args:
            ticker: Stock ticker symbol
            analysis_date: Analysis date

        Returns:
            Tuple of (ticker, analysis_result)
        """
        try:
            print(f"\nAnalyzing {ticker}...")

            # Create a trading graph for this stock
            ta = TradingAgentsGraph(
                selected_analysts=self.selected_analysts,
                debug=self.debug,
                config=self.config.copy()
            )

            # Run the analysis
            final_state, decision = ta.propagate(ticker, analysis_date)

            return (ticker, {
                'final_state': final_state,
                'decision': decision,
                'success': True
            })

        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
            return (ticker, {
                'error': str(e),
                'success': False
            })

    def analyze_portfolio(
        self,
        portfolio: Portfolio,
        max_workers: int = 3
    ) -> PortfolioAnalysisResult:
        """
        Analyze the entire portfolio.

        Args:
            portfolio: Portfolio object with positions
            max_workers: Maximum number of parallel workers for stock analysis

        Returns:
            PortfolioAnalysisResult with complete analysis
        """
        print(f"\n{'='*60}")
        print(f"Starting Portfolio Analysis: {portfolio.name}")
        print(f"Analysis Date: {portfolio.analysis_date}")
        print(f"Positions: {', '.join(portfolio.tickers)}")
        print(f"{'='*60}\n")

        # Step 1: Fetch current prices and update portfolio
        print("Fetching current prices...")
        current_prices = self._get_current_prices(
            portfolio.tickers,
            portfolio.analysis_date
        )

        for ticker, price in current_prices.items():
            if price is not None:
                portfolio.positions[ticker].current_price = price

        # Display portfolio summary
        print(f"\nPortfolio Summary:")
        print(f"  Total Cost Basis: ${portfolio.total_cost_basis:,.2f}")
        if portfolio.total_market_value:
            print(f"  Total Market Value: ${portfolio.total_market_value:,.2f}")
            print(f"  Unrealized P/L: ${portfolio.total_unrealized_gain_loss:,.2f} "
                  f"({portfolio.total_unrealized_gain_loss_pct:+.2f}%)")
        print()

        # Step 2: Calculate portfolio metrics
        print("Calculating portfolio metrics...")
        portfolio_metrics = calculate_portfolio_metrics(portfolio)

        # Step 3: Analyze individual stocks in parallel
        print(f"\nAnalyzing {len(portfolio.tickers)} stocks in parallel...")
        individual_analyses = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all analysis tasks
            future_to_ticker = {
                executor.submit(
                    self._analyze_single_stock,
                    ticker,
                    portfolio.analysis_date
                ): ticker
                for ticker in portfolio.tickers
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker, result = future.result()
                individual_analyses[ticker] = result
                if result.get('success'):
                    print(f"✓ Completed analysis for {ticker}")
                else:
                    print(f"✗ Failed analysis for {ticker}: {result.get('error')}")

        # Step 4: Generate portfolio-level recommendations
        print("\nGenerating portfolio-level insights...")
        portfolio_recommendation = self._generate_portfolio_recommendation(
            portfolio,
            portfolio_metrics,
            individual_analyses
        )

        # Step 5: Generate rebalancing suggestions
        rebalancing_suggestions = self._generate_rebalancing_suggestions(
            portfolio,
            portfolio_metrics,
            individual_analyses
        )

        # Step 6: Generate risk assessment
        risk_assessment = self._generate_risk_assessment(
            portfolio,
            portfolio_metrics,
            individual_analyses
        )

        print(f"\n{'='*60}")
        print("Portfolio Analysis Complete!")
        print(f"{'='*60}\n")

        return PortfolioAnalysisResult(
            portfolio=portfolio,
            individual_analyses=individual_analyses,
            portfolio_metrics=portfolio_metrics,
            portfolio_recommendation=portfolio_recommendation,
            rebalancing_suggestions=rebalancing_suggestions,
            risk_assessment=risk_assessment
        )

    def _generate_portfolio_recommendation(
        self,
        portfolio: Portfolio,
        metrics: Dict,
        analyses: Dict[str, Dict]
    ) -> str:
        """Generate overall portfolio recommendation."""
        lines = []
        lines.append("# Portfolio Overview")
        lines.append("")

        # Summarize individual recommendations
        buy_count = 0
        sell_count = 0
        hold_count = 0

        for ticker, analysis in analyses.items():
            if not analysis.get('success'):
                continue

            decision = analysis.get('decision', '').upper()
            weight = portfolio.get_position_weights()[ticker]

            if 'BUY' in decision:
                buy_count += 1
            elif 'SELL' in decision:
                sell_count += 1
            else:
                hold_count += 1

        lines.append(f"**Individual Stock Recommendations:**")
        lines.append(f"- Buy signals: {buy_count}")
        lines.append(f"- Hold signals: {hold_count}")
        lines.append(f"- Sell signals: {sell_count}")
        lines.append("")

        # Portfolio metrics summary
        if 'diversification_score' in metrics:
            div_score = metrics['diversification_score']
            lines.append(f"**Diversification Score:** {div_score:.2f}/1.00")
            if div_score < 0.5:
                lines.append("⚠️ Portfolio shows high correlation - consider diversifying")
            lines.append("")

        if 'portfolio_beta' in metrics:
            beta = metrics['portfolio_beta']
            lines.append(f"**Portfolio Beta:** {beta:.2f}")
            if beta > 1.2:
                lines.append("  - Portfolio is more volatile than market")
            elif beta < 0.8:
                lines.append("  - Portfolio is less volatile than market")
            lines.append("")

        if 'sharpe_ratio' in metrics:
            sharpe = metrics['sharpe_ratio']
            lines.append(f"**Sharpe Ratio:** {sharpe:.2f}")
            if sharpe > 1:
                lines.append("  - Good risk-adjusted returns")
            elif sharpe < 0:
                lines.append("  - Negative risk-adjusted returns")
            lines.append("")

        # Sector concentration
        if 'sector_weights' in metrics:
            lines.append("**Sector Allocation:**")
            for sector, weight in sorted(
                metrics['sector_weights'].items(),
                key=lambda x: x[1],
                reverse=True
            ):
                lines.append(f"- {sector}: {weight:.1f}%")
            lines.append("")

            # Check for over-concentration
            max_sector_weight = max(metrics['sector_weights'].values())
            if max_sector_weight > 50:
                lines.append(f"⚠️ High concentration in {max(metrics['sector_weights'], key=metrics['sector_weights'].get)} "
                           f"({max_sector_weight:.1f}%) - consider diversifying")
                lines.append("")

        return "\n".join(lines)

    def _generate_rebalancing_suggestions(
        self,
        portfolio: Portfolio,
        metrics: Dict,
        analyses: Dict[str, Dict]
    ) -> List[Dict]:
        """Generate rebalancing suggestions."""
        suggestions = []
        weights = portfolio.get_position_weights()

        # Check for over-concentration
        for ticker, weight in weights.items():
            if weight > 30:
                suggestions.append({
                    'type': 'REDUCE',
                    'ticker': ticker,
                    'current_weight': weight,
                    'reason': f'Position represents {weight:.1f}% of portfolio - consider reducing for better diversification'
                })

            if weight < 5 and len(portfolio.tickers) > 5:
                suggestions.append({
                    'type': 'EVALUATE',
                    'ticker': ticker,
                    'current_weight': weight,
                    'reason': f'Small position ({weight:.1f}%) - consider consolidating or increasing'
                })

        # Check individual stock recommendations
        for ticker, analysis in analyses.items():
            if not analysis.get('success'):
                continue

            decision = analysis.get('decision', '').upper()
            if 'SELL' in decision:
                suggestions.append({
                    'type': 'CONSIDER_SELL',
                    'ticker': ticker,
                    'current_weight': weights[ticker],
                    'reason': 'Individual analysis suggests SELL'
                })

        return suggestions

    def _generate_risk_assessment(
        self,
        portfolio: Portfolio,
        metrics: Dict,
        analyses: Dict[str, Dict]
    ) -> str:
        """Generate risk assessment for portfolio."""
        lines = []
        lines.append("# Portfolio Risk Assessment")
        lines.append("")

        # Volatility
        if 'portfolio_volatility' in metrics:
            vol = metrics['portfolio_volatility'] * 100
            lines.append(f"**Portfolio Volatility:** {vol:.1f}% (annualized)")
            if vol > 25:
                lines.append("  - High volatility portfolio")
            elif vol < 15:
                lines.append("  - Low volatility portfolio")
            lines.append("")

        # Correlation risk
        if 'diversification_score' in metrics:
            div_score = metrics['diversification_score']
            if div_score < 0.5:
                lines.append("**Correlation Risk:** HIGH")
                lines.append("  - Positions are highly correlated")
                lines.append("  - Portfolio may not benefit from diversification during market stress")
            else:
                lines.append("**Correlation Risk:** LOW")
                lines.append("  - Good diversification across positions")
            lines.append("")

        # Concentration risk
        weights = portfolio.get_position_weights()
        max_weight = max(weights.values())
        if max_weight > 30:
            max_ticker = max(weights, key=weights.get)
            lines.append("**Concentration Risk:** HIGH")
            lines.append(f"  - {max_ticker} represents {max_weight:.1f}% of portfolio")
            lines.append("  - Consider reducing position size")
        else:
            lines.append("**Concentration Risk:** LOW")
            lines.append("  - Well-balanced position sizing")
        lines.append("")

        # Sector concentration risk
        if 'sector_weights' in metrics:
            max_sector_weight = max(metrics['sector_weights'].values())
            if max_sector_weight > 50:
                max_sector = max(metrics['sector_weights'], key=metrics['sector_weights'].get)
                lines.append("**Sector Concentration Risk:** HIGH")
                lines.append(f"  - {max_sector} sector represents {max_sector_weight:.1f}%")
                lines.append("  - Consider adding exposure to other sectors")
            else:
                lines.append("**Sector Concentration Risk:** MODERATE")
            lines.append("")

        return "\n".join(lines)
