"""
Visualization tools for trading strategy evaluation.
Generates plots and reports for comparing TradingAgents with baseline strategies.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Dict
import warnings
import json

warnings.filterwarnings('ignore')

# Try to import seaborn for better styling (optional)
try:
    import seaborn as sns
    plt.style.use('seaborn-v0_8-darkgrid')
    sns.set_palette("husl")
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False
    # Use default matplotlib styling
    plt.rcParams['figure.facecolor'] = 'white'
    plt.rcParams['axes.facecolor'] = 'white'
    plt.rcParams['axes.grid'] = True


def plot_cumulative_returns(
    results: Dict[str, pd.DataFrame],
    ticker: str,
    output_path: str = None,
    figsize: tuple = (14, 8)
) -> plt.Figure:
    """
    Plot cumulative returns comparison for all strategies.
    
    Args:
        results: Dictionary mapping strategy name to portfolio DataFrame
        ticker: Stock ticker symbol
        output_path: Path to save the figure (optional)
        figsize: Figure size (width, height)
        
    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    for name, portfolio in results.items():
        if "cumulative_return" in portfolio.columns:
            cumulative = (portfolio["cumulative_return"] - 1) * 100  # Convert to percentage
            ax.plot(portfolio.index, cumulative, label=name, linewidth=2, alpha=0.8)
    
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('Cumulative Return (%)', fontsize=12, fontweight='bold')
    ax.set_title(f'{ticker} - Cumulative Returns Comparison', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
    
    # Format y-axis as percentage
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.1f}%'))
    
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved cumulative returns plot to: {output_path}")
    
    return fig


def plot_transaction_history(
    portfolio: pd.DataFrame,
    ticker: str,
    strategy_name: str = "TradingAgents",
    output_path: str = None,
    figsize: tuple = (14, 10)
) -> plt.Figure:
    """
    Plot transaction history with buy/sell signals overlaid on price chart.
    
    Args:
        portfolio: Portfolio DataFrame with 'signal' and 'close' columns
        ticker: Stock ticker symbol
        strategy_name: Name of the strategy
        output_path: Path to save the figure (optional)
        figsize: Figure size (width, height)
        
    Returns:
        matplotlib Figure object
    """
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, height_ratios=[2, 1])
    
    # Price chart with signals
    ax1.plot(portfolio.index, portfolio["close"], label='Close Price', 
             color='blue', linewidth=1.5, alpha=0.7)
    
    # Buy signals (signal == 1 and previous signal != 1)
    signals = portfolio["signal"].copy()
    buy_signals = (signals == 1) & (signals.shift(1) != 1)
    sell_signals = (signals == -1) & (signals.shift(1) != -1)
    
    # Plot buy/sell markers
    if buy_signals.any():
        ax1.scatter(portfolio.index[buy_signals], 
                   portfolio.loc[buy_signals, "close"],
                   marker='^', color='green', s=100, label='Buy', 
                   zorder=5, alpha=0.8)
    
    if sell_signals.any():
        ax1.scatter(portfolio.index[sell_signals], 
                   portfolio.loc[sell_signals, "close"],
                   marker='v', color='red', s=100, label='Sell', 
                   zorder=5, alpha=0.8)
    
    ax1.set_ylabel('Price ($)', fontsize=12, fontweight='bold')
    ax1.set_title(f'{ticker} - {strategy_name} Transaction History', 
                  fontsize=14, fontweight='bold')
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3)
    
    # Portfolio value
    ax2.plot(portfolio.index, portfolio["portfolio_value"], 
             label='Portfolio Value', color='purple', linewidth=2)
    ax2.fill_between(portfolio.index, portfolio["portfolio_value"], 
                      alpha=0.3, color='purple')
    ax2.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Portfolio Value ($)', fontsize=12, fontweight='bold')
    ax2.legend(loc='best', fontsize=10)
    ax2.grid(True, alpha=0.3)
    
    # Format y-axis as currency
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'${y:,.0f}'))
    
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved transaction history plot to: {output_path}")
    
    return fig


def plot_metrics_comparison(
    comparison_df: pd.DataFrame,
    ticker: str,
    output_path: str = None,
    figsize: tuple = (16, 10)
) -> plt.Figure:
    """
    Create bar charts comparing key metrics across strategies.
    
    Args:
        comparison_df: DataFrame with strategies as rows and metrics as columns
        ticker: Stock ticker symbol
        output_path: Path to save the figure (optional)
        figsize: Figure size (width, height)
        
    Returns:
        matplotlib Figure object
    """
    # Select key metrics (matching paper's Table 1)
    metrics_to_plot = [
        "Cumulative Return (%)",
        "Annualized Return (%)",
        "Sharpe Ratio",
        "Maximum Drawdown (%)"
    ]
    
    # Filter to available metrics
    available_metrics = [m for m in metrics_to_plot if m in comparison_df.columns]
    
    if not available_metrics:
        raise ValueError("No matching metrics found in comparison DataFrame")
    
    n_metrics = len(available_metrics)
    fig, axes = plt.subplots(2, 2, figsize=figsize)
    axes = axes.flatten()
    
    for idx, metric in enumerate(available_metrics):
        ax = axes[idx]
        data = comparison_df[metric].sort_values(ascending=False)
        
        # Color code: TradingAgents in different color
        colors = ['#FF6B6B' if name == 'TradingAgents' else '#4ECDC4' 
                  for name in data.index]
        
        bars = ax.barh(range(len(data)), data.values, color=colors, alpha=0.8)
        ax.set_yticks(range(len(data)))
        ax.set_yticklabels(data.index, fontsize=10)
        ax.set_xlabel(metric, fontsize=11, fontweight='bold')
        ax.set_title(metric, fontsize=12, fontweight='bold')
        ax.grid(True, alpha=0.3, axis='x')
        
        # Add value labels on bars
        for i, (bar, value) in enumerate(zip(bars, data.values)):
            if "Ratio" in metric:
                label = f'{value:.2f}'
            else:
                label = f'{value:.1f}%'
            ax.text(value, bar.get_y() + bar.get_height()/2, 
                   f'  {label}', va='center', fontsize=9)
    
    # Hide unused subplots
    for idx in range(n_metrics, 4):
        axes[idx].axis('off')
    
    fig.suptitle(f'{ticker} - Performance Metrics Comparison', 
                 fontsize=16, fontweight='bold', y=0.995)
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved metrics comparison plot to: {output_path}")
    
    return fig


def plot_drawdown(
    results: Dict[str, pd.DataFrame],
    ticker: str,
    output_path: str = None,
    figsize: tuple = (14, 8)
) -> plt.Figure:
    """
    Plot drawdown analysis for all strategies.
    
    Args:
        results: Dictionary mapping strategy name to portfolio DataFrame
        ticker: Stock ticker symbol
        output_path: Path to save the figure (optional)
        figsize: Figure size (width, height)
        
    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    for name, portfolio in results.items():
        if "portfolio_value" in portfolio.columns:
            values = portfolio["portfolio_value"]
            running_max = values.cummax()
            drawdown = (values - running_max) / running_max * 100
            ax.plot(portfolio.index, drawdown, label=name, linewidth=2, alpha=0.7)
    
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('Drawdown (%)', fontsize=12, fontweight='bold')
    ax.set_title(f'{ticker} - Drawdown Analysis', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
    
    # Fill drawdown areas
    for name, portfolio in results.items():
        if "portfolio_value" in portfolio.columns:
            values = portfolio["portfolio_value"]
            running_max = values.cummax()
            drawdown = (values - running_max) / running_max * 100
            ax.fill_between(portfolio.index, drawdown, 0, alpha=0.1)
    
    # Format y-axis as percentage
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.1f}%'))
    
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved drawdown plot to: {output_path}")
    
    return fig


def plot_returns_distribution(
    results: Dict[str, pd.DataFrame],
    ticker: str,
    output_path: str = None,
    figsize: tuple = (14, 8)
) -> plt.Figure:
    """
    Plot distribution of daily returns for all strategies.
    
    Args:
        results: Dictionary mapping strategy name to portfolio DataFrame
        ticker: Stock ticker symbol
        output_path: Path to save the figure (optional)
        figsize: Figure size (width, height)
        
    Returns:
        matplotlib Figure object
    """
    fig, ax = plt.subplots(figsize=figsize)
    
    for name, portfolio in results.items():
        if "strategy_return" in portfolio.columns:
            returns = portfolio["strategy_return"].dropna() * 100  # Convert to percentage
            ax.hist(returns, bins=50, alpha=0.5, label=name, density=True)
    
    ax.set_xlabel('Daily Return (%)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Density', fontsize=12, fontweight='bold')
    ax.set_title(f'{ticker} - Returns Distribution', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.axvline(x=0, color='black', linestyle='--', linewidth=1, alpha=0.5)
    
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved returns distribution plot to: {output_path}")
    
    return fig


def create_summary_report(
    ticker: str,
    results: Dict[str, pd.DataFrame],
    comparison_df: pd.DataFrame,
    output_dir: str
) -> None:
    """
    Generate comprehensive visual summary report.
    Creates all standard plots and saves them to output directory.
    
    Args:
        ticker: Stock ticker symbol
        results: Dictionary mapping strategy name to portfolio DataFrame
        comparison_df: DataFrame with performance metrics comparison
        output_dir: Directory to save output files
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("\nGenerating visualizations...")
    
    # 1. Cumulative Returns
    try:
        plot_cumulative_returns(
            results, 
            ticker,
            output_path=str(output_path / f"{ticker}_cumulative_returns.png")
        )
    except Exception as e:
        print(f"✗ Failed to generate cumulative returns plot: {e}")
    
    # 2. Metrics Comparison
    try:
        plot_metrics_comparison(
            comparison_df, 
            ticker,
            output_path=str(output_path / f"{ticker}_metrics_comparison.png")
        )
    except Exception as e:
        print(f"✗ Failed to generate metrics comparison plot: {e}")
    
    # 3. Drawdown Analysis
    try:
        plot_drawdown(
            results, 
            ticker,
            output_path=str(output_path / f"{ticker}_drawdown.png")
        )
    except Exception as e:
        print(f"✗ Failed to generate drawdown plot: {e}")
    
    # 4. Transaction History (if TradingAgents results available)
    if "TradingAgents" in results:
        try:
            plot_transaction_history(
                results["TradingAgents"],
                ticker,
                strategy_name="TradingAgents",
                output_path=str(output_path / f"{ticker}_TradingAgents_transactions.png")
            )
        except Exception as e:
            print(f"✗ Failed to generate transaction history plot: {e}")
    
    # 5. Returns Distribution
    try:
        plot_returns_distribution(
            results, 
            ticker,
            output_path=str(output_path / f"{ticker}_returns_distribution.png")
        )
    except Exception as e:
        print(f"✗ Failed to generate returns distribution plot: {e}")
    
    print(f"\n✓ All visualizations saved to: {output_dir}")


def plot_cumulative_returns_from_results(
    results_dir: str,
    ticker: str,
    output_path: str = None,
    figsize: tuple = (12, 7)
) -> plt.Figure:
    """
    Plot cumulative returns comparison from saved JSON results.
    
    Args:
        results_dir: Directory containing strategy result folders
        ticker: Stock ticker symbol
        output_path: Path to save the figure (optional)
        figsize: Figure size (width, height)
        
    Returns:
        matplotlib Figure object
    """
    results_path = Path(results_dir)
    
    # Define strategies to load
    strategies = {
        'BuyAndHold': 'BuyAndHoldStrategy',
        'MACD': 'MACDStrategy',
        'KDJ&RSI': 'KDJRSIStrategy',
        'ZMR': 'ZMRStrategy',
        'SMA': 'SMAStrategy',
        'TradingAgents': 'TradingAgents',
        'TradingAgents_DAPT': 'TradingAgents (DAPT+SFT)'
    }
    
    fig, ax = plt.subplots(figsize=figsize)
    
    # Load and plot each strategy
    for folder_name, display_name in strategies.items():
        strategy_dir = results_path / folder_name
        if not strategy_dir.exists():
            continue
            
        # Find actions JSON file
        action_files = list(strategy_dir.glob("actions_*.json"))
        if not action_files:
            continue
        
        try:
            # Load data
            with open(action_files[0], 'r') as f:
                data = json.load(f)
            
            # Extract date and cumulative_return
            dates = pd.to_datetime([action['date'] for action in data['actions']])
            cumulative_returns = [action['cumulative_return'] for action in data['actions']]
            
            # Plot with enhanced styling for TradingAgents variants
            if 'TradingAgents' in display_name:
                linewidth = 2.5
                alpha = 0.95
            else:
                linewidth = 1.5
                alpha = 0.8
            
            ax.plot(dates, cumulative_returns, label=display_name, 
                   linewidth=linewidth, alpha=alpha)
            
        except Exception as e:
            print(f"Warning: Failed to load {display_name}: {e}")
    
    ax.set_xlabel('Date', fontsize=12)
    ax.set_ylabel('Cumulative Return', fontsize=12)
    ax.set_title(f'Strategy Comparison - Cumulative Returns for {ticker}', 
                 fontsize=14, fontweight='bold')
    ax.legend(title='Strategies', loc='best', fontsize=10, framealpha=0.9)
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.axhline(y=1.0, color='black', linestyle='--', linewidth=1, alpha=0.5)
    
    plt.tight_layout()
    
    if output_path:
        fig.savefig(output_path, dpi=300, bbox_inches='tight')
        print(f"✓ Saved cumulative returns comparison to: {output_path}")
    
    return fig


if __name__ == "__main__":
    # Example usage / testing
    print("Visualization module loaded successfully!")
    print("\nAvailable functions:")
    print("  - plot_cumulative_returns")
    print("  - plot_cumulative_returns_from_results")
    print("  - plot_transaction_history")
    print("  - plot_metrics_comparison")
    print("  - plot_drawdown")
    print("  - plot_returns_distribution")
    print("  - create_summary_report")

