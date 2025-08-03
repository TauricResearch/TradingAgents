# チケット #012: Reddit Utils互換性レイヤー実装

## 概要
既存のreddit_utils.pyと新しいpraw実装の間の互換性レイヤーを実装

## 目的
- 既存システムへの影響を最小限に抑える
- 段階的な移行を可能にする
- 既存のインターフェースを維持
- オンライン/オフラインモードの切り替え

## 実装要件

### 1. 段階的実装アプローチ
```python
# USE_PRAW_APIフラグで新旧実装を切り替え
from tradingagents.config import USE_PRAW_API

if USE_PRAW_API:
    # 新しいpraw実装を使用
    from .reddit_praw_fetcher import fetch_data
else:
    # 既存のファイルベース実装を使用
    from .reddit_local_fetcher import fetch_data
```

### 2. 互換性インターフェース
```python
# tradingagents/dataflows/reddit_utils.py の改修

def fetch_top_from_category(
    category: str,
    date: str,
    max_limit: int,
    query: str = None,
    data_path: str = "reddit_data",
    use_cache: bool = True,
    online_mode: bool = False
):
    """
    既存インターフェースを維持しつつ、praw実装を使用
    
    Args:
        category: "global_news" or "company_news"
        date: 対象日付 (YYYY-MM-DD)
        max_limit: 最大取得件数
        query: 企業検索用クエリ（ティッカー）
        data_path: データディレクトリパス
        use_cache: キャッシュを優先使用するか
        online_mode: オンラインで新規取得するか
        
    Returns:
        既存と同じ形式の投稿リスト
    """
    
    if use_cache and not online_mode:
        # 既存のファイルベース実装を使用
        return _fetch_from_local_files(category, date, max_limit, query, data_path)
    else:
        # 新しいpraw実装を使用
        return _fetch_from_reddit_api(category, date, max_limit, query)
```

### 3. 設定に基づく切り替え
```python
class RedditDataSource:
    """
    設定に基づいてデータソースを切り替え
    """
    def __init__(self, config: dict):
        self.config = config
        self.online_mode = config.get("online_tools", False)
        
        if self.online_mode:
            # praw実装を初期化
            self.fetcher = RedditDataFetcher(
                RedditPrawClient(config),
                config
            )
        
        # キャッシュマネージャーは常に初期化
        self.cache_manager = RedditCacheManager(
            config.get("reddit_data_dir", "reddit_data")
        )
    
    def get_data(self, category: str, date: str, **kwargs):
        """
        統一インターフェースでデータ取得
        """
        # まずキャッシュを確認
        if self.cache_manager.check_data_exists(category, date):
            return self.cache_manager.load_posts(category, date)
        
        # オンラインモードの場合は新規取得
        if self.online_mode:
            posts = self.fetcher.fetch_data(category, date, **kwargs)
            self.cache_manager.save_posts(posts, category, date)
            return posts
        
        # オフラインモードでキャッシュなし
        return []
```

### 4. データ形式の変換
```python
def convert_praw_to_legacy_format(praw_posts: List[dict]) -> List[dict]:
    """
    praw形式のデータを既存形式に変換
    
    既存形式:
    {
        "title": str,
        "content": str,  # selftextから変換
        "url": str,
        "upvotes": int,  # upsから変換
        "posted_date": str  # created_utcから変換
    }
    """
    legacy_posts = []
    for post in praw_posts:
        legacy_post = {
            "title": post["title"],
            "content": post["selftext"],
            "url": post["url"],
            "upvotes": post["ups"],
            "posted_date": datetime.fromtimestamp(
                post["created_utc"]
            ).strftime("%Y-%m-%d")
        }
        legacy_posts.append(legacy_post)
    
    return legacy_posts
```

### 5. エラーハンドリング
```python
def safe_reddit_fetch(func):
    """
    Reddit API エラーを既存システムに影響させないデコレータ
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RedditAPIError as e:
            logger.warning(f"Reddit API error: {e}")
            # フォールバック: キャッシュデータを返す
            return _fallback_to_cache(*args, **kwargs)
        except Exception as e:
            logger.error(f"Unexpected error in Reddit fetch: {e}")
            return []  # 空リストで安全に失敗
    
    return wrapper
```

### 6. 移行支援機能
```python
class RedditDataMigrator:
    """
    既存データから新形式への移行支援
    """
    def migrate_existing_data(self, 
                            old_data_dir: str,
                            new_data_dir: str):
        """
        既存のJSONLファイルを新しいディレクトリ構造に移行
        """
        pass
    
    def validate_migration(self):
        """
        移行データの検証
        """
        pass
```

### 7. インターフェース統合
```python
# tradingagents/dataflows/interface.py の更新

def get_reddit_global_news(
    start_date: str,
    look_back_days: int,
    **kwargs
) -> str:
    """
    既存のインターフェースを維持
    内部でRedditDataSourceを使用
    """
    data_source = RedditDataSource(DEFAULT_CONFIG)
    
    posts = []
    for i in range(look_back_days):
        date = calculate_date(start_date, -i)
        daily_posts = data_source.get_data(
            "global_news", 
            date,
            **kwargs
        )
        posts.extend(daily_posts)
    
    # 既存と同じ形式で返す
    return format_posts_as_string(posts)
```

## 受け入れ条件
- [ ] 既存のインターフェースが変更なく動作
- [ ] USE_PRAW_APIフラグでの切り替え
- [ ] データ形式の正確な変換
- [ ] エラー時の適切なフォールバック
- [ ] パフォーマンスの劣化なし
- [ ] 既存テストがすべて通過
- [ ] 単体テストの実装（モック使用）

## 依存関係
- 既存のreddit_utils.py
- RedditDataFetcher（チケット#009）
- RedditCacheManager（チケット#010）
- interface.py

## タスク
- [ ] 単体テストの作成（TDD）
- [ ] USE_PRAW_APIフラグの追加
- [ ] RedditDataSourceクラスの実装
- [ ] fetch_top_from_category の改修
- [ ] データ形式変換機能
- [ ] エラーハンドリングデコレータ
- [ ] 設定ベースの切り替え機能
- [ ] interface.py の更新
- [ ] 移行支援ツール
- [ ] 互換性テスト
- [ ] パフォーマンステスト
- [ ] ドキュメント更新