# チケット #013: Reddit自動更新機能実装

## 概要
Redditデータの定期的な自動更新機能とスケジューラー設定の実装

## 目的
- 日次での自動データ更新
- エラー時の通知とリトライ
- 実行ログの管理
- cron/スケジューラーとの統合

## 実装要件

### 1. 段階的実装アプローチ
```python
# USE_PRAW_APIフラグによる実装切り替え
from tradingagents.config import USE_PRAW_API

if USE_PRAW_API:
    # 新しいpraw実装での自動更新
    from .reddit_praw_updater import RedditDailyUpdater
else:
    # 既存のファイルベース更新（何もしない）
    class RedditDailyUpdater:
        def run_daily_update(self, date):
            print("Offline mode - no updates needed")
```

### 2. 自動更新スクリプト
```python
# scripts/reddit_daily_update.py

class RedditDailyUpdater:
    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: 設定ファイルパス
        """
        self.config = self.load_config(config_path)
        self.logger = self.setup_logging()
        
    def run_daily_update(self, date: str = None):
        """
        日次更新のメイン処理
        
        Args:
            date: 対象日付（デフォルト: 昨日）
        """
        if not date:
            date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        self.logger.info(f"Starting daily update for {date}")
        
        try:
            # データ取得
            results = self.fetch_all_data(date)
            
            # 結果の検証
            self.validate_results(results)
            
            # 成功通知
            self.notify_success(date, results)
            
        except Exception as e:
            self.handle_error(date, e)
```

### 3. 設定ファイル
```yaml
# config/reddit_auto_update.yaml

daily_update:
  # 取得対象
  categories:
    - global_news
    - company_news
  
  # 対象ティッカー
  tickers:
    preset: "sp500"  # または具体的なリスト
    # custom: ["AAPL", "MSFT", "NVDA"]
  
  # 実行時間設定
  schedule:
    time: "02:00"  # 午前2時実行
    timezone: "America/New_York"
  
  # リトライ設定
  retry:
    max_attempts: 3
    delay_seconds: 300  # 5分間隔
  
  # 通知設定
  notifications:
    on_error: true
    on_success: false
    methods:
      - log_file
      # - email
      # - slack

# ログ設定
logging:
  level: INFO
  file: logs/reddit_update.log
  max_size: 10MB
  backup_count: 7
```

### 4. エラーハンドリングとリトライ
```python
def fetch_with_retry(self, fetch_func, *args, **kwargs):
    """
    リトライ機能付きデータ取得
    """
    max_attempts = self.config['retry']['max_attempts']
    delay = self.config['retry']['delay_seconds']
    
    for attempt in range(max_attempts):
        try:
            return fetch_func(*args, **kwargs)
        except RedditAPIError as e:
            if attempt < max_attempts - 1:
                self.logger.warning(
                    f"Attempt {attempt + 1} failed: {e}. "
                    f"Retrying in {delay} seconds..."
                )
                time.sleep(delay)
            else:
                raise
```

### 5. 実行ログ管理
```python
class UpdateLogger:
    """
    更新実行のログ管理
    """
    def log_execution(self,
                     date: str,
                     status: str,
                     details: dict):
        """
        実行結果をログに記録
        
        ログ形式:
        {
            "timestamp": "2024-03-15T02:05:30Z",
            "date": "2024-03-14",
            "status": "success",
            "categories": {
                "global_news": {
                    "posts_fetched": 250,
                    "new_posts": 230
                },
                "company_news": {
                    "tickers_processed": 50,
                    "total_posts": 1250
                }
            },
            "duration_seconds": 180,
            "errors": []
        }
        """
        pass
```

### 6. Cron設定
```bash
# crontab設定例

# 毎日午前2時に実行（米国東部時間）
0 2 * * * cd /path/to/TradingAgents && /usr/bin/python3 -m scripts.reddit_daily_update >> logs/cron.log 2>&1

# 週次でデータ検証（毎週月曜日午前9時）
0 9 * * 1 cd /path/to/TradingAgents && /usr/bin/python3 -m cli.main reddit verify --days 7 >> logs/verify.log 2>&1

# 月次でストレージクリーンアップ（毎月1日午前3時）
0 3 1 * * cd /path/to/TradingAgents && /usr/bin/python3 -m scripts.reddit_cleanup --days 90 >> logs/cleanup.log 2>&1
```

### 7. systemdサービス（Alternative）
```ini
# /etc/systemd/system/reddit-updater.service

[Unit]
Description=Reddit Data Daily Updater
After=network.target

[Service]
Type=oneshot
User=tradingagents
WorkingDirectory=/path/to/TradingAgents
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 -m scripts.reddit_daily_update

[Install]
WantedBy=multi-user.target
```

### 8. 監視とアラート
```python
class UpdateMonitor:
    """
    更新の監視とアラート
    """
    def check_last_update(self):
        """
        最後の更新をチェック
        24時間以上更新がない場合はアラート
        """
        pass
    
    def send_alert(self, message: str, level: str = "error"):
        """
        設定に基づいてアラートを送信
        """
        if self.config['notifications']['methods']:
            for method in self.config['notifications']['methods']:
                if method == "log_file":
                    self.logger.error(message)
                # elif method == "email":
                #     self.send_email_alert(message)
                # elif method == "slack":
                #     self.send_slack_alert(message)
```

### 9. データ整合性チェック
```python
def validate_daily_data(self, date: str) -> dict:
    """
    日次データの整合性チェック
    
    Returns:
        {
            "valid": bool,
            "issues": [...],
            "statistics": {...}
        }
    """
    validator = RedditDataValidator()
    
    # チェック項目
    checks = {
        "minimum_posts": self.check_minimum_posts(date),
        "duplicate_ratio": self.check_duplicate_ratio(date),
        "data_freshness": self.check_data_freshness(date),
        "file_integrity": self.check_file_integrity(date)
    }
    
    return validator.run_checks(checks)
```

## 受け入れ条件
- [ ] 日次自動更新の安定動作
- [ ] エラー時の適切なリトライ
- [ ] 実行ログの記録と管理
- [ ] Cron/systemdでの実行対応
- [ ] データ整合性の自動チェック
- [ ] 設定ファイルでの柔軟な制御
- [ ] USE_PRAW_APIフラグでの切り替え
- [ ] 単体テストの実装（モック使用）

## 依存関係
- RedditDataFetcher（チケット#009）
- RedditCacheManager（チケット#010）
- CLI実装（チケット#011）
- システムのcron/systemd

## タスク
- [ ] 単体テストの作成（TDD）
- [ ] USE_PRAW_APIフラグの統合
- [ ] RedditDailyUpdaterクラスの実装
- [ ] 設定ファイル形式の定義
- [ ] リトライ機能の実装
- [ ] ログ管理機能
- [ ] Cron設定スクリプト
- [ ] systemdサービス定義
- [ ] 監視・アラート機能
- [ ] データ整合性チェック
- [ ] エラー通知機能
- [ ] 運用ドキュメント作成