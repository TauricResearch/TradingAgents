# チケット #011: Reddit CLIコマンド実装（typer使用）

## 概要
Reddit データ取得のためのCLIコマンドインターフェースのtyperを使用した実装

## 目的
- 対話形式での過去データ取得
- 日次更新コマンド
- データ状況の確認機能
- 既存CLIフレームワーク（typer）との統合

## 実装要件

### 1. コマンド構造
```
cli/
├── main.py          # 既存のtyperアプリ
└── commands/
    └── reddit.py    # Redditコマンド実装
```

### 2. typerコマンド統合
```python
# cli/main.py への統合
from cli.commands import reddit

# 既存のappにサブコマンドを追加
app.add_typer(reddit.app, name="reddit", help="Reddit data management")
```

### 3. Redditコマンド実装
```python
# cli/commands/reddit.py
import typer
from rich.console import Console
import questionary

app = typer.Typer()
console = Console()

@app.command()
def fetch_historical(
    interactive: bool = typer.Option(True, "--interactive/--no-interactive",
                                    help="Use interactive mode for configuration")
):
    """Fetch historical Reddit data"""
    if interactive:
        # 対話形式
        config = interactive_configuration()
    else:
        # オプション指定
        config = parse_command_options()
    
    fetcher = create_reddit_fetcher(config)
    fetcher.run()
```

### 4. 対話形式の実装（questionary使用）
```python
def interactive_configuration():
    """
    対話形式でデータ取得設定を行う
    既存のquestionaryを活用
    """
    console = Console()
    
    # カテゴリ選択
    category = questionary.select(
        "Which category?",
        choices=["global_news", "company_news", "both"]
    ).ask()
    
    # 期間選択（推奨期間の表示付き）
    date_range = interactive_date_range_selection()
    
    # ティッカー選択（プリセット対応）
    if category in ["company_news", "both"]:
        tickers = interactive_ticker_selection()
    
    # 確認と実行
    if confirm_execution(category, date_range, tickers):
        return build_config(category, date_range, tickers)
```

### 4. ティッカー選択インターフェース
```python
def interactive_ticker_selection():
    """
    デフォルトTickerリストから選択
    """
    choice = questionary.select(
        "Select ticker preset or enter custom:",
        choices=[
            "1. Popular Tech Stocks (15 tickers)",
            "2. S&P 500 Top 20",
            "3. Global Indices (22 ETFs)",  # 日経225追加済み
            "4. All Combined (50+ tickers)",
            "5. Quick Test (5 tickers)",
            "6. Custom (enter your own)"
        ]
    ).ask()
    
    if choice.startswith("6"):
        # カスタム入力
        custom = questionary.text(
            "Enter tickers (comma-separated):"
        ).ask()
        return parse_custom_tickers(custom)
    else:
        # プリセット使用
        return get_preset_tickers(choice)
```

### 5. 日次更新コマンド
```python
@app.command()
def update(
    date: str = typer.Option('yesterday', help='Date to fetch (YYYY-MM-DD or "yesterday")'),
    auto: bool = typer.Option(False, help='Run in automatic mode (no prompts)')
):
    """Update Reddit data for specific date"""
    
    if date == 'yesterday':
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        target_date = validate_date(date)
    
    if auto:
        # 設定ファイルから自動実行
        config = load_auto_config()
    else:
        # 確認プロンプト表示
        if not click.confirm(f"Fetch data for {target_date}?"):
            return
    
    execute_update(target_date, config)
```

### 6. ステータス確認コマンド
```python
@app.command()
def status(
    start: str = typer.Option(None, help='Start date (YYYY-MM-DD)'),
    end: str = typer.Option(None, help='End date (YYYY-MM-DD)'),
    category: str = typer.Option('all', help='Category to check')
):
    """Check Reddit data cache status"""
    
    cache_manager = RedditCacheManager(get_reddit_data_dir())
    
    # データ可用性の表示
    table = Table(title="Reddit Data Status")
    table.add_column("Date", style="cyan")
    table.add_column("Global News", style="green")
    table.add_column("Company News", style="yellow")
    table.add_column("Total Posts", style="magenta")
    
    # 統計情報の表示
    display_cache_statistics(cache_manager, start, end, category)
```

### 7. データ検証コマンド
```python
@app.command()
def verify(
    start: str = typer.Argument(..., help='Start date'),
    end: str = typer.Argument(..., help='End date'),
    fix: bool = typer.Option(False, help='Attempt to fix issues')
):
    """Verify data integrity and completeness"""
    
    validator = RedditDataValidator()
    issues = validator.check_period(start, end)
    
    if issues['missing_dates']:
        console.print("[yellow]Missing dates found:[/yellow]")
        for date in issues['missing_dates']:
            console.print(f"  - {date}")
    
    if fix and issues['missing_dates']:
        if click.confirm("Fetch missing data?"):
            fetch_missing_data(issues['missing_dates'])
```

### 8. プログレス表示
```python
def show_fetch_progress(total_requests: int):
    """
    取得進捗の表示
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Fetching Reddit data...", total=total_requests)
        yield progress, task
```

## 受け入れ条件
- [ ] 対話形式での直感的な操作
- [ ] デフォルトTickerリストの選択機能
- [ ] 日次更新の自動実行対応
- [ ] 進捗表示とエラーハンドリング
- [ ] データ状況の可視化
- [ ] typer CLIフレームワークとの統合
- [ ] 単体テストの実装（モック使用）
- [ ] USE_PRAW_APIフラグでの切り替え

## 依存関係
- typer（既存CLIフレームワーク）
- rich（TUI表示）
- questionary（対話形式入力）
- RedditDataFetcher（チケット#009）
- RedditCacheManager（チケット#010）

## タスク
- [ ] 単体テストの作成（TDD）
- [ ] reddit.pyコマンドモジュールの作成
- [ ] typerアプリへの統合
- [ ] fetch-historicalコマンド実装
- [ ] 対話形式インターフェース
- [ ] デフォルトTickerリスト選択機能
- [ ] updateコマンド実装
- [ ] statusコマンド実装
- [ ] verifyコマンド実装
- [ ] プログレス表示機能
- [ ] エラーハンドリング
- [ ] ヘルプメッセージの充実
- [ ] 段階的実装フラグのテスト
- [ ] 統合テスト