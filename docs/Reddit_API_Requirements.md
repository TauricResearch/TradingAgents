# Reddit API (praw) 実装要件定義書

## 1. 概要
既存のローカルファイルベースのRedditデータ取得を、Reddit API (praw)を使用したリアルタイム取得に変更し、過去データの収集とキャッシュ機能を実装する。

## 2. 機能要件

### 2.1 データ取得範囲

#### Global News カテゴリ
以下のsubredditから金融・経済関連のグローバルニュースを取得：
- r/worldnews - 世界ニュース
- r/news - 一般ニュース
- r/economics - 経済ニュース  
- r/finance - 金融ニュース
- r/business - ビジネスニュース

#### Company News カテゴリ
以下のsubredditから企業・株式関連情報を取得：
- r/stocks - 株式投資全般
- r/StockMarket - 株式市場動向
- r/wallstreetbets - トレーダーコミュニティ
- r/investing - 投資戦略
- r/SecurityAnalysis - 企業分析

### 2.2 企業関連投稿の検索戦略（推奨）

**ハイブリッドアプローチ**を採用：
1. **直接検索**: Reddit検索APIで企業名/ティッカーを検索（API効率的）
2. **ストリーム監視**: 新着投稿をリアルタイムで取得し、企業名/ティッカーでフィルタリング
3. **人気投稿スキャン**: 各subredditのtop/hot投稿を定期取得してフィルタリング

```python
# 検索例
def search_company_posts(ticker: str, company_name: str):
    # 1. Reddit検索API
    search_queries = [
        f'"{ticker}"',
        f'"{company_name}"',
        f'${ticker}',  # Cashtag
    ]
    
    # 2. タイトルと本文でのマッチング
    # 3. 重複排除（post ID使用）
```

### 2.3 データ収集粒度（API制限を考慮した推奨設定）

**Reddit API制限**：
- 認証済みアプリ: 100リクエスト/分（QPM）
- 1リクエストで最大100アイテム取得可能
- 10分間の平均でレート制限を計算（バースト対応）

**最適化されたデータ収集設定**：
- Global News: 
  - 各subredditから上位50-100件/日（1リクエストで取得可能）
  - 5 subreddits × 1リクエスト = 5リクエスト/日
- Company News:
  - 各企業につき上位50件/日（1リクエストで取得）
  - 人気10銘柄の場合: 10リクエスト/日
  - 追加銘柄: バッチ処理で効率化

**バッチ処理戦略**：
- 1分あたり最大80リクエストに制限（バッファ20%）
- 大量銘柄の場合は時間分散:
  - 50銘柄 = 約1分で完了
  - 500銘柄 = 約7分で完了（レート制限考慮）
- ソート基準: Hot → Top (24h) → New の優先順位

### 2.4 重複排除
- Reddit post IDを使用してグローバルに重複を排除
- 同一投稿が複数subredditに投稿された場合、最初に取得したものを保持

## 3. CLI インターフェース

### 3.1 過去データ取得（対話形式）
```bash
python -m cli.main reddit fetch-historical

# 対話形式のプロンプト
> Which category? (global_news/company_news/both): both
> Start date (YYYY-MM-DD): 2024-01-01
> End date (YYYY-MM-DD) [default: today]: 2024-03-31
> For company news, select tickers:
  1. Popular Tech Stocks (15 tickers)
  2. S&P 500 Top 20
  3. Global Indices (20 ETFs)
  4. All Combined (50+ tickers)
  5. Quick Test (5 tickers)
  6. Custom (enter your own)
> Select option (1-6): 1
> Confirm fetch? This may take several minutes. (y/n): y
```

### 3.2 日次更新
```bash
# 昨日のデータを取得
python -m cli.main reddit update --date yesterday

# 特定日のデータを取得
python -m cli.main reddit update --date 2024-03-15

# 自動実行用（エラー時はログ記録）
python -m cli.main reddit update --auto
```

### 3.3 データ検証
```bash
# キャッシュ状況確認
python -m cli.main reddit status

# 特定期間のデータ完全性チェック
python -m cli.main reddit verify --start 2024-01-01 --end 2024-03-31
```

## 4. キャッシュ設計

### 4.1 ディレクトリ構造
```
/Users/y_sato/Library/Mobile Documents/com~apple~CloudDocs/curosur/API疎通確認ずみ/APIテスト完了済み/TradingAgents/Datasource/
└── reddit_data/
    ├── global_news/
    │   ├── r_worldnews_2024-01-01.jsonl
    │   ├── r_economics_2024-01-01.jsonl
    │   └── ...
    ├── company_news/
    │   ├── AAPL_2024-01-01.jsonl
    │   ├── MSFT_2024-01-01.jsonl
    │   └── ...
    └── metadata/
        ├── fetch_history.json  # 取得履歴
        ├── post_ids.db        # 重複チェック用
        └── ticker_presets.json # デフォルトTickerリスト
```

### 4.2 JSONL形式（既存互換）
```json
{
  "id": "1a2b3c4",
  "title": "Apple announces new product",
  "selftext": "Content here...",
  "url": "https://reddit.com/...",
  "ups": 1234,
  "created_utc": 1704067200,
  "subreddit": "r/stocks",
  "author": "username",
  "num_comments": 56,
  "ticker": "AAPL"  // 企業投稿の場合
}
```

## 5. 実装アーキテクチャ

### 5.1 モジュール構成
```python
tradingagents/dataflows/
├── reddit_praw_client.py    # prawクライアントラッパー
├── reddit_fetcher.py         # データ取得ロジック
├── reddit_cache_manager.py   # キャッシュ管理
└── reddit_utils.py           # 既存互換性レイヤー
```

### 5.2 エラーハンドリング
- API接続エラー: 上位層に例外を伝播
- Rate limit エラー: 自動リトライ with exponential backoff
- 認証エラー: 即座に例外を発生させる

### 5.3 設定管理
```python
# tradingagents/config.py に追加
REDDIT_CONFIG = {
    "user_agent": "TradingAgents/1.0",
    "rate_limit_pause": 1.0,  # 秒
    "max_retries": 3,
    "data_base_dir": "/Users/y_sato/Library/Mobile Documents/com~apple~CloudDocs/curosur/API疎通確認ずみ/APIテスト完了済み/TradingAgents/Datasource",
    "cache_dir": "reddit_data",
    "global_news_subreddits": [
        "worldnews", "news", "economics", "finance", "business"
    ],
    "company_news_subreddits": [
        "stocks", "StockMarket", "wallstreetbets", "investing", "SecurityAnalysis"
    ],
    "daily_post_limits": {
        "global_news": 100,
        "company_news": 50
    },
    "default_ticker_presets": {
        "tech": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AMZN", "TSLA", "AMD", "INTC", "NFLX", "AVGO", "ORCL", "ADBE", "CRM", "QCOM"],
        "sp500": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK.B", "LLY", "AVGO", "JPM", "TSLA", "V", "UNH", "XOM", "MA", "JNJ", "WMT", "PG", "HD"],
        "indices": ["SPY", "QQQ", "DIA", "IWM", "EWJ", "DXJ", "EWG", "EWQ", "EWU", "FEZ", "EEM", "FXI", "INDA", "EWZ", "XLK", "XLF", "XLE", "XLV"],
        "quick": ["AAPL", "MSFT", "NVDA", "TSLA", "SPY"]
    }
}
```

## 6. 自動実行設定

### 6.1 Cron設定例
```bash
# 毎日午前6時に前日データを取得
0 6 * * * cd /path/to/TradingAgents && python -m cli.main reddit update --auto >> logs/reddit_update.log 2>&1

# 毎週月曜日に先週のデータ完全性をチェック
0 9 * * 1 cd /path/to/TradingAgents && python -m cli.main reddit verify --days 7 >> logs/reddit_verify.log 2>&1
```

### 6.2 エラー通知
- ログファイルにエラー記録
- 重要なエラー（認証失敗等）はメール/Slack通知（オプション）

## 7. 移行計画

### Phase 1: 基盤実装
1. praw クライアントラッパー実装
2. 基本的なデータ取得機能
3. キャッシュ管理機能

### Phase 2: CLI実装  
1. 対話形式の過去データ取得
2. 日次更新コマンド
3. ステータス確認機能

### Phase 3: 自動化
1. エラーハンドリング強化
2. 自動実行対応
3. 既存システムとの統合テスト

## 8. 性能要件

### API制限に基づく現実的な性能目標
- **レート制限**: 100 requests/minute（認証済み）
- **バッチサイズ**: 100 items/request
- **安全マージン**: 80 requests/minute で運用

### データ取得時間の見積もり
**1日分のデータ**:
- Global News: 5 subreddits = 5リクエスト
- Company News (50銘柄): 50リクエスト  
- 合計: 55リクエスト = **約1分で完了**

**1ヶ月分（30日）の過去データ**:
- 各日付ごとに処理が必要
- Global News: 5 × 30 = 150リクエスト
- Company News (50銘柄): 50 × 30 = 1,500リクエスト
- 合計: 1,650リクエスト = **約21分で完了**

**1年分（365日）の過去データ**:
- Global News: 5 × 365 = 1,825リクエスト  
- Company News (50銘柄): 50 × 365 = 18,250リクエスト
- 合計: 20,075リクエスト = **約4.2時間で完了**

### 最適化のポイント
- 並列処理は避ける（レート制限違反のリスク）
- 2秒間隔でリクエストを送信（30 requests/minute）で安定運用
- エラー時の再試行は exponential backoff を使用

## 9. セキュリティ
- Reddit認証情報は環境変数で管理
- キャッシュデータへのアクセス制限
- ログに認証情報を含めない