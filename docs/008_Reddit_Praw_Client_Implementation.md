# チケット #008: Reddit prawクライアント実装

## 概要
Reddit API (praw) を使用してデータを取得するクライアントラッパーの段階的実装

## 目的
- Reddit APIへの認証と接続管理
- レート制限の適切な処理
- エラーハンドリングとリトライ機構
- 既存システムとの互換性維持
- オプショナル機能としての実装（既存システムと並行動作）

## 実装要件

### 1. 段階的実装アプローチ
```python
# tradingagents/config.py に追加
USE_PRAW_API = os.getenv("USE_PRAW_API", "false").lower() == "true"
```

### 2. クラス設計
```python
class RedditPrawClient:
    def __init__(self, config: dict):
        """
        Args:
            config: Reddit API設定
                - client_id: Reddit App ID
                - client_secret: Reddit App Secret
                - user_agent: User Agent文字列
                - rate_limit_pause: レート制限時の待機秒数
        """
        pass
    
    def authenticate(self) -> bool:
        """
        Reddit APIへの認証
        
        Returns:
            成功時True、失敗時False
        """
        pass
    
    def get_subreddit_posts(self, 
                          subreddit: str,
                          sort: str = "hot",
                          limit: int = 100,
                          time_filter: str = "day") -> List[dict]:
        """
        特定のsubredditから投稿を取得
        
        Args:
            subreddit: subreddit名
            sort: ソート方法 (hot/top/new)
            limit: 取得件数 (最大100)
            time_filter: 期間フィルタ (day/week/month/year/all)
            
        Returns:
            投稿データのリスト
        """
        pass
    
    def search_posts(self,
                    query: str,
                    subreddit: str = None,
                    limit: int = 100,
                    sort: str = "relevance") -> List[dict]:
        """
        キーワード検索で投稿を取得
        
        Args:
            query: 検索クエリ
            subreddit: 特定のsubredditに限定（オプション）
            limit: 取得件数
            sort: ソート方法
            
        Returns:
            検索結果の投稿リスト
        """
        pass
```

### 2. レート制限管理
```python
class RateLimiter:
    def __init__(self, requests_per_minute: int = 80):
        """
        Args:
            requests_per_minute: 1分あたりの最大リクエスト数
        """
        self.request_times = deque(maxlen=requests_per_minute)
        self.requests_per_minute = requests_per_minute
        
    def wait_if_needed(self):
        """必要に応じて待機"""
        pass
```

### 3. エラーハンドリング
- 認証エラー: `RedditAuthenticationError`を発生
- レート制限エラー: 自動リトライ with exponential backoff
- ネットワークエラー: 最大3回リトライ
- 不正なsubreddit: `SubredditNotFoundError`を発生

### 4. 設定管理
```python
REDDIT_CLIENT_CONFIG = {
    "user_agent": "TradingAgents/1.0 (by /u/your_username)",
    "rate_limit_pause": 1.0,
    "max_retries": 3,
    "timeout": 30,
    "requests_per_minute": 80  # 安全マージン20%
}
```

## 受け入れ条件
- [ ] prawライブラリを使用した認証が成功する
- [ ] 投稿データの取得が正しく動作する
- [ ] レート制限に違反しない
- [ ] エラー時の適切な例外処理
- [ ] 取得データが既存のJSONL形式と互換性がある
- [ ] 既存システムとの並行動作確認
- [ ] 単体テストの実装（モック使用）
- [ ] 環境変数での機能切り替えが動作

## 依存関係
- praw (Python Reddit API Wrapper)
- python-dotenv（環境変数管理）
- 既存のreddit_utils.pyとの連携

## タスク
- [ ] 単体テストの作成（TDD）
- [ ] RedditPrawClientクラスの基本実装
- [ ] 認証機能の実装
- [ ] subreddit投稿取得機能
- [ ] 検索機能の実装
- [ ] レート制限管理の実装
- [ ] エラーハンドリング実装
- [ ] 環境変数による機能切り替え
- [ ] 設定ファイルの作成
- [ ] 統合テスト作成
- [ ] ドキュメント作成