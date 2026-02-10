"""Backtest service for calculating real prediction accuracy."""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
import database as db


def get_trading_day_price(ticker: yf.Ticker, target_date: datetime,
                          direction: str = 'forward', max_days: int = 7) -> tuple[Optional[float], Optional[datetime]]:
    """
    Get the closing price for a trading day near the target date.

    Args:
        ticker: yfinance Ticker object
        target_date: The date we want price for
        direction: 'forward' to look for next trading day, 'backward' for previous
        max_days: Maximum days to search

    Returns:
        Tuple of (closing_price, actual_date) or (None, None) if not found
    """
    for i in range(max_days):
        if direction == 'forward':
            check_date = target_date + timedelta(days=i)
        else:
            check_date = target_date - timedelta(days=i)

        start = check_date
        end = check_date + timedelta(days=1)

        hist = ticker.history(start=start.strftime('%Y-%m-%d'),
                             end=end.strftime('%Y-%m-%d'))
        if not hist.empty:
            return hist['Close'].iloc[0], check_date

    return None, None


def calculate_backtest_for_recommendation(date: str, symbol: str, decision: str,
                                           hold_days: int = None) -> Optional[dict]:
    """
    Calculate backtest results for a single recommendation.

    Args:
        date: Prediction date (YYYY-MM-DD)
        symbol: Stock symbol (NSE format like RELIANCE.NS)
        decision: BUY, SELL, or HOLD
        hold_days: Recommended holding period in days (for BUY/HOLD)

    Returns:
        Dict with backtest results or None if calculation failed
    """
    try:
        # Convert date
        pred_date = datetime.strptime(date, '%Y-%m-%d')

        # For Indian stocks, append .NS suffix if not present
        yf_symbol = symbol if '.' in symbol else f"{symbol}.NS"

        ticker = yf.Ticker(yf_symbol)

        # Get price at prediction date (or next trading day)
        price_at_pred, actual_pred_date = get_trading_day_price(ticker, pred_date, 'forward')
        if price_at_pred is None:
            return None

        # Get prices for 1 day, 1 week, 1 month later
        date_1d = pred_date + timedelta(days=1)
        date_1w = pred_date + timedelta(weeks=1)
        date_1m = pred_date + timedelta(days=30)

        price_1d, actual_1d_date = get_trading_day_price(ticker, date_1d, 'forward')
        price_1w, actual_1w_date = get_trading_day_price(ticker, date_1w, 'forward')
        price_1m, actual_1m_date = get_trading_day_price(ticker, date_1m, 'forward')

        # Detect same-day resolution: if pred and 1d resolved to the same trading day,
        # the 0% return is meaningless — treat as no data
        if price_1d and actual_pred_date and actual_1d_date and actual_pred_date == actual_1d_date:
            price_1d = None

        # Calculate returns (only when we have a genuinely different trading day)
        return_1d = ((price_1d - price_at_pred) / price_at_pred * 100) if price_1d else None
        return_1w = ((price_1w - price_at_pred) / price_at_pred * 100) if price_1w else None
        return_1m = ((price_1m - price_at_pred) / price_at_pred * 100) if price_1m else None

        # Calculate return at hold_days horizon if specified
        return_at_hold = None
        if hold_days and hold_days > 0:
            date_hold = pred_date + timedelta(days=hold_days)
            price_at_hold, actual_hold_date = get_trading_day_price(ticker, date_hold, 'forward')
            # Only count if we found a different day than the prediction date
            if price_at_hold and actual_hold_date and actual_hold_date != actual_pred_date:
                return_at_hold = round(((price_at_hold - price_at_pred) / price_at_pred * 100), 2)

        # Skip if we have no usable return data at all
        if return_1d is None and return_1w is None and return_at_hold is None:
            return None

        # Determine if prediction was correct
        # Use hold_days return when available, fall back to 1-day return
        prediction_correct = None
        check_return = return_at_hold if return_at_hold is not None else return_1d
        if check_return is not None:
            if decision == 'BUY' or decision == 'HOLD':
                prediction_correct = check_return > 0
            elif decision == 'SELL':
                prediction_correct = check_return < 0

        # Sanitize the decision value before storing
        clean_decision = decision.strip().upper()
        if clean_decision not in ('BUY', 'SELL', 'HOLD'):
            clean_decision = 'HOLD'

        return {
            'date': date,
            'symbol': symbol,
            'decision': clean_decision,
            'price_at_prediction': round(price_at_pred, 2),
            'price_1d_later': round(price_1d, 2) if price_1d else None,
            'price_1w_later': round(price_1w, 2) if price_1w else None,
            'price_1m_later': round(price_1m, 2) if price_1m else None,
            'return_1d': round(return_1d, 2) if return_1d is not None else None,
            'return_1w': round(return_1w, 2) if return_1w is not None else None,
            'return_1m': round(return_1m, 2) if return_1m is not None else None,
            'return_at_hold': return_at_hold,
            'hold_days': hold_days,
            'prediction_correct': prediction_correct
        }

    except Exception as e:
        print(f"Error calculating backtest for {symbol} on {date}: {e}")
        return None


def calculate_and_save_backtest(date: str, symbol: str, decision: str,
                                hold_days: int = None) -> Optional[dict]:
    """Calculate backtest and save to database."""
    result = calculate_backtest_for_recommendation(date, symbol, decision, hold_days)

    if result:
        db.save_backtest_result(
            date=result['date'],
            symbol=result['symbol'],
            decision=result['decision'],
            price_at_prediction=result['price_at_prediction'],
            price_1d_later=result['price_1d_later'],
            price_1w_later=result['price_1w_later'],
            price_1m_later=result['price_1m_later'],
            return_1d=result['return_1d'],
            return_1w=result['return_1w'],
            return_1m=result['return_1m'],
            prediction_correct=result['prediction_correct'],
            hold_days=result.get('hold_days'),
            return_at_hold=result.get('return_at_hold'),
        )

    return result


def backtest_all_recommendations_for_date(date: str) -> dict:
    """
    Calculate backtest for all recommendations on a given date.

    Returns summary statistics.
    """
    rec = db.get_recommendation_by_date(date)
    if not rec or 'analysis' not in rec:
        return {'error': 'No recommendations found for date', 'date': date}

    analysis = rec['analysis']  # Dict keyed by symbol
    results = []
    errors = []

    for symbol, stock_data in analysis.items():
        decision = stock_data['decision']
        hold_days = stock_data.get('hold_days')

        # Check if we already have a backtest result
        existing = db.get_backtest_result(date, symbol)
        if existing:
            results.append(existing)
            continue

        # Calculate new backtest
        result = calculate_and_save_backtest(date, symbol, decision, hold_days)
        if result:
            results.append(result)
        else:
            errors.append(symbol)

    # Calculate summary
    correct = sum(1 for r in results if r.get('prediction_correct'))
    total_with_result = sum(1 for r in results if r.get('prediction_correct') is not None)

    return {
        'date': date,
        'total_stocks': len(analysis),
        'calculated': len(results),
        'errors': errors,
        'correct_predictions': correct,
        'total_with_result': total_with_result,
        'accuracy': round(correct / total_with_result * 100, 1) if total_with_result > 0 else 0
    }


def get_backtest_data_for_frontend(date: str, symbol: str) -> dict:
    """
    Get backtest data formatted for frontend display.
    Includes price history for charts.
    """
    result = db.get_backtest_result(date, symbol)

    if not result:
        # Try to calculate it
        rec = db.get_recommendation_by_date(date)
        if rec and 'analysis' in rec:
            stock_data = rec['analysis'].get(symbol)
            if stock_data:
                result = calculate_and_save_backtest(date, symbol, stock_data['decision'], stock_data.get('hold_days'))

    if not result:
        return {'available': False, 'reason': 'Could not calculate backtest'}

    # Get price history for chart
    try:
        pred_date = datetime.strptime(date, '%Y-%m-%d')
        yf_symbol = symbol if '.' in symbol else f"{symbol}.NS"
        ticker = yf.Ticker(yf_symbol)

        # Get 30 days of history starting from prediction date
        end_date = pred_date + timedelta(days=35)
        hist = ticker.history(start=pred_date.strftime('%Y-%m-%d'),
                             end=end_date.strftime('%Y-%m-%d'))

        price_history = [
            {'date': idx.strftime('%Y-%m-%d'), 'price': round(row['Close'], 2)}
            for idx, row in hist.iterrows()
        ][:30]  # Limit to 30 data points

    except Exception:
        price_history = []

    return {
        'available': True,
        'prediction_correct': result['prediction_correct'],
        'actual_return_1d': result['return_1d'],
        'actual_return_1w': result['return_1w'],
        'actual_return_1m': result['return_1m'],
        'return_at_hold': result.get('return_at_hold'),
        'hold_days': result.get('hold_days'),
        'price_at_prediction': result['price_at_prediction'],
        'current_price': result.get('price_1m_later') or result.get('price_1w_later'),
        'price_history': price_history
    }
