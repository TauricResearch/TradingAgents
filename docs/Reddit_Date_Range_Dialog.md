# Reddit データ取得期間の対話形式ヒアリング設計

## 対話フロー例

### 1. 基本的な対話フロー
```python
def interactive_date_range_prompt():
    """
    ユーザーと対話してデータ取得期間を決定する
    """
    
    print("Reddit Historical Data Fetcher")
    print("="*40)
    
    # Step 1: 取得目的の確認
    print("\nWhat is the purpose of this data fetch?")
    print("1. Backtesting preparation")
    print("2. Historical analysis")
    print("3. Initial data setup")
    print("4. Gap filling (missing dates)")
    purpose = input("Select purpose (1-4): ")
    
    # Step 2: 期間の提案
    if purpose == "1":  # Backtesting
        print("\nFor backtesting, we recommend:")
        print("- Short-term: Last 3 months")
        print("- Medium-term: Last 6 months")
        print("- Long-term: Last 1 year")
        
    elif purpose == "2":  # Historical analysis
        print("\nFor historical analysis:")
        print("- Recent events: Last 1 month")
        print("- Quarterly analysis: Last 3 months")
        print("- Annual trends: Last 1 year")
        
    # Step 3: 期間選択
    print("\nHow would you like to specify the date range?")
    print("1. Use predefined period (1 week/1 month/3 months/6 months/1 year)")
    print("2. Specify exact dates")
    print("3. Relative dates (e.g., 'last 30 days')")
    
    choice = input("Select option (1-3): ")
    
    if choice == "1":
        return handle_predefined_period()
    elif choice == "2":
        return handle_exact_dates()
    else:
        return handle_relative_dates()
```

### 2. Reddit API制限を考慮した警告表示
```python
def validate_date_range(start_date, end_date):
    """
    選択された期間の妥当性を確認し、必要に応じて警告
    """
    
    days_diff = (end_date - start_date).days
    
    # 警告レベルの判定
    if days_diff > 365:
        print(f"\n⚠️  WARNING: Large date range ({days_diff} days)")
        print("This will result in:")
        print(f"- Approximately {days_diff * 5} API calls")
        print(f"- Estimated time: {days_diff * 0.5:.1f} minutes")
        print("- Reddit API may not return complete historical data beyond 1000 posts per subreddit")
        
        if not confirm("Do you want to continue with this large range?"):
            return False
            
    elif days_diff > 180:
        print(f"\n📊 Date range: {days_diff} days")
        print(f"- Estimated time: {days_diff * 0.5:.1f} minutes")
        print("- This is a reasonable range for comprehensive analysis")
        
    return True
```

### 3. 段階的な期間設定（推奨実装）
```python
def smart_date_range_selector():
    """
    ユーザーの経験レベルに応じた期間設定
    """
    
    print("\nLet's determine the best date range for your needs.")
    
    # Step 1: データ利用頻度の確認
    print("\nHow often will you run backtests?")
    print("1. Daily (active trading)")
    print("2. Weekly (regular monitoring)")
    print("3. Monthly (periodic review)")
    print("4. One-time analysis")
    
    frequency = input("Select frequency (1-4): ")
    
    # Step 2: 推奨期間の提示
    recommendations = {
        "1": {
            "initial": "1 month",
            "update": "daily",
            "reason": "Recent data is most relevant for active trading"
        },
        "2": {
            "initial": "3 months",
            "update": "weekly",
            "reason": "Balanced between data volume and relevance"
        },
        "3": {
            "initial": "6 months",
            "update": "monthly",
            "reason": "Good for trend analysis and strategy validation"
        },
        "4": {
            "initial": "1 year",
            "update": "as needed",
            "reason": "Comprehensive historical data for research"
        }
    }
    
    rec = recommendations[frequency]
    print(f"\n💡 Recommendation based on your usage:")
    print(f"- Initial fetch: {rec['initial']} of historical data")
    print(f"- Update schedule: {rec['update']}")
    print(f"- Reason: {rec['reason']}")
    
    # Step 3: カスタマイズオプション
    print("\nWould you like to:")
    print("1. Accept recommendation")
    print("2. Modify the period")
    print("3. See data availability preview")
    
    return handle_user_choice()
```

### 4. データ可用性のプレビュー
```python
def preview_data_availability(start_date, end_date, tickers=None):
    """
    指定期間のデータ可用性をプレビュー表示
    """
    
    print("\n📈 Data Availability Preview")
    print("="*50)
    
    # Reddit API制限の説明
    print("\nReddit API Limitations:")
    print("- Posts older than 6 months may be incomplete")
    print("- Maximum 1000 posts per subreddit search")
    print("- Rate limit: 60 requests per minute")
    
    # 期間別の推定データ量
    days = (end_date - start_date).days
    print(f"\nEstimated data volume for {days} days:")
    print(f"- Global news: ~{days * 100} posts from 5 subreddits")
    
    if tickers:
        print(f"- Company news for {len(tickers)} tickers:")
        for ticker in tickers[:5]:  # 最初の5つを表示
            print(f"  - {ticker}: ~{days * 20} posts")
        if len(tickers) > 5:
            print(f"  - ... and {len(tickers)-5} more tickers")
    
    # 取得時間の見積もり
    total_requests = estimate_api_requests(days, tickers)
    estimated_time = (total_requests / 60) * 1.2  # 20%のバッファ
    
    print(f"\n⏱️  Estimated fetch time: {estimated_time:.1f} minutes")
    print(f"📊 Total API requests: ~{total_requests}")
    
    return True
```

### 5. 実装例：CLI統合
```python
# cli/commands/reddit.py

@click.command()
@click.option('--interactive/--no-interactive', default=True, 
              help='Use interactive mode for date selection')
def fetch_historical(interactive):
    """Fetch historical Reddit data with smart date selection"""
    
    if interactive:
        # 対話形式で期間を決定
        date_range = smart_date_range_selector()
        
        # プレビュー表示
        if preview_data_availability(date_range.start, date_range.end):
            if click.confirm("Proceed with data fetch?"):
                fetch_reddit_data(date_range)
    else:
        # 非対話形式（自動実行用）
        fetch_reddit_data(get_default_date_range())
```

## 使用例

### 初回セットアップ時
```
$ python -m cli.main reddit fetch-historical

Reddit Historical Data Fetcher
========================================

What is the purpose of this data fetch?
1. Backtesting preparation
2. Historical analysis  
3. Initial data setup
4. Gap filling (missing dates)
Select purpose (1-4): 3

For initial setup, we recommend starting with recent data.
How much historical data do you need?

1. Last 1 month (recommended for testing)
2. Last 3 months (good for short-term analysis)
3. Last 6 months (balanced approach)
4. Last 1 year (comprehensive but time-consuming)
5. Custom range

Select option (1-5): 2

📊 You selected: Last 3 months (2024-01-01 to 2024-03-31)

Which tickers would you like to track? 
1. Top 10 most discussed (TSLA, AAPL, GME, AMC, NVDA, ...)
2. S&P 500 leaders
3. Custom list
4. All available (not recommended)

Select option (1-4): 1

📈 Data Availability Preview
==================================================
Period: 2024-01-01 to 2024-03-31 (90 days)
Tickers: TSLA, AAPL, GME, AMC, NVDA, MSFT, AMZN, META, GOOGL, SPY

Estimated data volume:
- Global news: ~9,000 posts from 5 subreddits
- Company news: ~18,000 posts for 10 tickers

⏱️  Estimated fetch time: 15.0 minutes
📊 Total API requests: ~750

Proceed with data fetch? [y/N]: y
```

この設計により、ユーザーは自分のニーズに合った期間を選択でき、同時にAPI制限やデータ量についても理解した上で実行できます。