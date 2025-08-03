# チケット #016: Reddit時間制御とデータ整合性実装

## 概要
未来日のデータ取得を防止し、市場時間を考慮したデータ取得時間制御の実装（初期実装は米国市場のみ）

## 目的
- バックテストでの未来情報リーク防止
- 市場開始前のデータのみを使用
- タイムゾーンの適切な処理（初期実装: 米国東部時間のみ）
- データの時間的整合性の保証

## 実装要件

### 1. 時間検証クラス（初期実装: 米国市場のみ）
```python
from datetime import datetime, time, timezone, timedelta
import pytz
import pandas_market_calendars as mcal

class TemporalDataValidator:
    def __init__(self):
        # 初期実装: 米国市場のみ
        self.market_timezone = pytz.timezone('America/New_York')
        self.market_open = time(9, 30)
        self.data_cutoff_time = time(9, 0)  # 30分前
        self.calendar = mcal.get_calendar('NYSE')
        
        # 将来の拡張用（コメントアウト）
        # self.market_configs = {
        #     'US': {...},
        #     'JP': {...},
        #     'EU': {...},
        #     'DE': {...}
        # }
        
    def validate_date_not_future(self, target_date: str) -> bool:
        """
        対象日が未来日でないことを確認
        
        Args:
            target_date: YYYY-MM-DD形式の日付
            
        Returns:
            有効な場合True、未来日の場合False
            
        Raises:
            ValueError: 未来日を指定した場合
        """
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
        today = datetime.now(self.market_timezone).date()
        
        if target > today:
            raise ValueError(
                f"Cannot fetch data for future date: {target_date}. "
                f"Today is {today} (EST)."
            )
        
        return True
    
    def is_market_open_day(self, date: str) -> bool:
        """
        指定日が米国市場の営業日かどうかをチェック
        
        Args:
            date: YYYY-MM-DD形式の日付
            
        Returns:
            営業日の場合True、休場日の場合False
        """
        # 指定日が営業日かチェック
        schedule = self.calendar.schedule(start_date=date, end_date=date)
        return len(schedule) > 0
    
    def get_next_market_day(self, date: str) -> str:
        """
        次の営業日を取得（週末・祝日をスキップ）
        """
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        
        # 次の営業日を探す
        for i in range(1, 10):  # 最大10日先まで検索
            next_date = date_obj + timedelta(days=i)
            next_date_str = next_date.strftime("%Y-%m-%d")
            if self.is_market_open_day(next_date_str):
                return next_date_str
        
        raise ValueError(f"No market open day found within 10 days after {date}")
    
    def get_data_cutoff_timestamp(self, target_date: str) -> int:
        """
        米国市場の開始30分前のタイムスタンプを取得
        
        Args:
            target_date: YYYY-MM-DD形式の日付
            
        Returns:
            Unix timestamp (UTC)
        """
        # 営業日チェック
        if not self.is_market_open_day(target_date):
            raise ValueError(
                f"{target_date} is not a market open day. "
                f"Next open day is {self.get_next_market_day(target_date)}"
            )
        
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        
        # タイムゾーンを考慮してカットオフ時刻を作成
        # pytzは自動的にDST（サマータイム）を処理
        cutoff_datetime = self.market_timezone.localize(
            datetime.combine(date_obj, self.data_cutoff_time)
        )
        
        # UTCに変換してUnixタイムスタンプを返す
        return int(cutoff_datetime.timestamp())
```

### 2. 時間フィルタリング機能
```python
class TemporalDataFilter:
    def __init__(self, validator: TemporalDataValidator):
        self.validator = validator
        
    def filter_posts_by_cutoff(self, 
                              posts: List[dict], 
                              target_date: str) -> List[dict]:
        """
        米国市場開始30分前までの投稿のみをフィルタリング
        
        Args:
            posts: Reddit投稿のリスト
            target_date: 対象日付
            
        Returns:
            フィルタリング後の投稿リスト
        """
        try:
            cutoff_timestamp = self.validator.get_data_cutoff_timestamp(target_date)
        except ValueError as e:
            # 休場日の場合は空リストを返す
            logging.info(str(e))
            return []
        
        filtered_posts = []
        for post in posts:
            post_timestamp = post.get('created_utc', 0)
            
            # カットオフ時刻より前の投稿のみを含める
            if post_timestamp < cutoff_timestamp:
                filtered_posts.append(post)
            else:
                logging.debug(
                    f"Excluded post '{post.get('title')}' - "
                    f"posted after cutoff time"
                )
        
        logging.info(
            f"Filtered {len(posts) - len(filtered_posts)} posts "
            f"posted after {target_date} 09:00 EST"
        )
        
        return filtered_posts
```

### 3. 日付範囲の検証
```python
class DateRangeValidator:
    def validate_date_range(self, start_date: str, end_date: str) -> dict:
        """
        日付範囲の妥当性を検証
        
        Returns:
            {
                "valid": bool,
                "adjustments": {
                    "original_end": str,
                    "adjusted_end": str
                },
                "warnings": List[str]
            }
        """
        validator = TemporalDataValidator()
        warnings = []
        adjustments = {}
        
        # 終了日が今日以降の場合は昨日に調整
        today = datetime.now(validator.market_timezone).date()
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date()
        
        if end_date_obj >= today:
            yesterday = today - timedelta(days=1)
            adjustments["original_end"] = end_date
            adjustments["adjusted_end"] = yesterday.strftime("%Y-%m-%d")
            warnings.append(
                f"End date adjusted from {end_date} to {adjustments['adjusted_end']} "
                f"to prevent future data access"
            )
            end_date = adjustments["adjusted_end"]
        
        # 当日のデータ取得に関する警告
        if end_date_obj == today:
            current_time = datetime.now(validator.market_timezone).time()
            if current_time < validator.data_cutoff_time:
                warnings.append(
                    f"Today's data is not yet available. "
                    f"Data becomes available after 09:00 EST."
                )
        
        return {
            "valid": True,
            "adjustments": adjustments,
            "warnings": warnings
        }
```

### 4. 今後の拡張: マルチマーケット対応
```python
# 将来の実装予定: 複数市場のサポート
# 現在は米国市場のみをサポート
#
# class MultiMarketBatchProcessor:
#     """
#     複数市場のティッカーを効率的に処理
#     """
#     pass
```

### 5. Reddit API取得時の時間制御
```python
class TimeAwareRedditFetcher(RedditDataFetcher):
    def __init__(self, client, config):
        super().__init__(client, config)
        self.temporal_validator = TemporalDataValidator()
        self.temporal_filter = TemporalDataFilter(self.temporal_validator)
        
    def fetch_company_news(self, 
                          ticker: str,
                          company_name: str,
                          date: str,
                          limit: int = 50) -> List[dict]:
        """
        時間制御付きの企業ニュース取得（米国市場対応）
        """
        # 未来日チェック
        self.temporal_validator.validate_date_not_future(date)
        
        # 市場営業日チェック
        if not self.temporal_validator.is_market_open_day(date):
            logging.info(
                f"{date} is not a trading day. Skipping."
            )
            return []
        
        # 通常の取得処理
        posts = super().fetch_company_news(ticker, company_name, date, limit)
        
        # 時間フィルタリング
        filtered_posts = self.temporal_filter.filter_posts_by_cutoff(
            posts, date
        )
        
        return filtered_posts
```

### 5. バックテスト実行時の検証
```python
class BacktestTimeValidator:
    """
    バックテスト実行時の時間整合性チェック
    """
    def validate_backtest_date(self, test_date: str) -> dict:
        """
        バックテスト日付の妥当性検証
        
        Returns:
            {
                "can_run": bool,
                "reason": str,
                "next_available_time": datetime
            }
        """
        validator = TemporalDataValidator()
        now = datetime.now(validator.market_timezone)
        
        # 今日の日付でバックテストする場合
        if test_date == now.strftime("%Y-%m-%d"):
            if now.time() < validator.data_cutoff_time:
                next_available = datetime.combine(
                    now.date(),
                    validator.data_cutoff_time,
                    tzinfo=validator.market_timezone
                )
                return {
                    "can_run": False,
                    "reason": f"Today's data not yet available. Available after 09:00 EST.",
                    "next_available_time": next_available
                }
        
        return {
            "can_run": True,
            "reason": "Date is valid for backtesting",
            "next_available_time": None
        }
```

### 6. CLI統合
```python
# cli/commands/reddit.py への追加

@reddit.command()
@click.option('--force', is_flag=True, help='Force fetch without time validation')
def fetch_historical(force):
    """Fetch historical Reddit data with temporal validation"""
    
    if not force:
        # 日付範囲の検証
        validator = DateRangeValidator()
        validation_result = validator.validate_date_range(start_date, end_date)
        
        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                console.print(f"[yellow]Warning: {warning}[/yellow]")
        
        if validation_result["adjustments"]:
            console.print(
                f"[cyan]Date range adjusted: "
                f"{validation_result['adjustments']['original_end']} → "
                f"{validation_result['adjustments']['adjusted_end']}[/cyan]"
            )
            
            if not click.confirm("Continue with adjusted dates?"):
                return
```

### 7. 設定オプション
```python
# config/reddit_temporal_config.yaml

temporal_settings:
  # タイムゾーン設定
  market_timezone: "America/New_York"
  
  # 市場時間
  market_open: "09:30"
  market_close: "16:00"
  
  # データ取得カットオフ（市場開始何分前か）
  data_cutoff_minutes_before_open: 30
  
  # 検証設定
  validation:
    prevent_future_data: true
    enforce_cutoff_time: true
    allow_override: false  # --forceオプションの許可
    
  # 警告設定
  warnings:
    show_timezone_info: true
    show_next_available_time: true
```

### 8. ログとモニタリング
```python
class TemporalAuditLogger:
    """
    時間制御に関する監査ログ
    """
    def log_temporal_filtering(self,
                              date: str,
                              total_posts: int,
                              filtered_posts: int,
                              cutoff_time: str):
        """
        時間フィルタリングの結果を記録
        """
        audit_entry = {
            "timestamp": datetime.now().isoformat(),
            "target_date": date,
            "cutoff_time_est": cutoff_time,
            "total_posts_fetched": total_posts,
            "posts_after_cutoff": total_posts - filtered_posts,
            "posts_included": filtered_posts,
            "filter_ratio": (total_posts - filtered_posts) / total_posts if total_posts > 0 else 0
        }
        
        self.write_audit_log(audit_entry)
```

## 受け入れ条件
- [ ] 未来日のデータ取得が確実に防止される
- [ ] 米国市場の開始30分前（09:00 EST/EDT）でデータが切られる
- [ ] 週末・祝日が自動的にスキップされる
- [ ] サマータイムが自動的に処理される
- [ ] タイムゾーンが正しく処理される
- [ ] バックテストでの時間的整合性が保証される
- [ ] 適切な警告とログが出力される
- [ ] 既存システムとの互換性維持
- [ ] 単体テストの実装（モック使用）

## 依存関係
- pytz（タイムゾーン処理、DST対応）
- pandas_market_calendars（米国市場の営業日カレンダー）
- 既存のRedditDataFetcher
- CLI実装

## タスク
- [ ] 単体テストの作成（TDD）
- [ ] TemporalDataValidatorクラスの実装（米国市場のみ）
- [ ] TemporalDataFilterクラスの実装
- [ ] DateRangeValidatorの実装
- [ ] TimeAwareRedditFetcherの実装
- [ ] 米国市場カレンダーの統合（NYSE）
- [ ] バックテスト時間検証機能
- [ ] CLI統合（警告表示）
- [ ] 設定ファイルの追加
- [ ] 監査ログ機能
- [ ] タイムゾーン・DST処理のテスト
- [ ] 米国市場の休場日テスト
- [ ] 統合テスト
- [ ] ドキュメント更新