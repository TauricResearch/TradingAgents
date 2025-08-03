# チケット #010: Redditキャッシュ管理機能実装

## 概要
取得したRedditデータのキャッシュ管理とJSONLファイルへの保存機能の段階的実装

## 目的
- 取得データの永続化（JSONL形式）
- 既存データとの互換性維持
- 効率的なデータ読み込み
- 取得履歴の管理
- 既存システムとの互換性確保

## 実装要件

### 1. 段階的実装アプローチ
```python
# 既存のファイル構造と互換性を保つ
from tradingagents.config import USE_PRAW_API

if USE_PRAW_API:
    # 新しいキャッシュマネージャーを使用
    cache_manager = RedditCacheManager(base_dir)
else:
    # 既存のファイルシステムを直接使用
    pass
```

### 2. クラス設計
```python
class RedditCacheManager:
    def __init__(self, base_dir: str):
        """
        Args:
            base_dir: データ保存のベースディレクトリ
                /Users/y_sato/.../Datasource/reddit_data/
        """
        self.base_dir = Path(base_dir)
        self.ensure_directory_structure()
        
    def ensure_directory_structure(self):
        """
        必要なディレクトリ構造を作成
        
        reddit_data/
        ├── global_news/
        ├── company_news/
        └── metadata/
        """
        pass
```

### 2. データ保存機能
```python
def save_posts(self,
              posts: List[dict],
              category: str,
              date: str,
              identifier: str = None) -> str:
    """
    投稿データをJSONL形式で保存
    
    Args:
        posts: 投稿データのリスト
        category: "global_news" or "company_news"
        date: 日付 (YYYY-MM-DD)
        identifier: subreddit名またはティッカー
        
    Returns:
        保存したファイルパス
        
    Example:
        global_news/r_worldnews_2024-01-01.jsonl
        company_news/AAPL_2024-01-01.jsonl
    """
    pass

def append_posts(self, 
                posts: List[dict],
                file_path: str):
    """
    既存ファイルに投稿を追加（重複チェック付き）
    """
    pass
```

### 3. データ読み込み機能
```python
def load_posts(self,
              category: str,
              date: str,
              identifier: str = None) -> List[dict]:
    """
    キャッシュから投稿データを読み込み
    
    Returns:
        投稿データのリスト、存在しない場合は空リスト
    """
    pass

def check_data_exists(self,
                     category: str,
                     date: str,
                     identifier: str = None) -> bool:
    """
    指定データがキャッシュに存在するか確認
    """
    pass
```

### 4. メタデータ管理
```python
def update_fetch_history(self,
                        category: str,
                        date: str,
                        identifiers: List[str],
                        fetch_timestamp: str,
                        post_count: int):
    """
    取得履歴を記録
    
    metadata/fetch_history.json に保存
    {
        "global_news": {
            "2024-01-01": {
                "timestamp": "2024-01-02T10:30:00Z",
                "subreddits": ["worldnews", "news", ...],
                "post_count": 250
            }
        },
        "company_news": {
            "AAPL": {
                "2024-01-01": {
                    "timestamp": "2024-01-02T10:35:00Z",
                    "post_count": 50
                }
            }
        }
    }
    """
    pass

def get_missing_dates(self,
                     start_date: str,
                     end_date: str,
                     category: str,
                     identifier: str = None) -> List[str]:
    """
    指定期間で未取得の日付リストを返す
    """
    pass
```

### 5. 重複管理
```python
class PostIDTracker:
    """
    Reddit post IDを使用した重複管理
    
    metadata/post_ids.db (SQLite) で管理
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
        
    def is_duplicate(self, post_id: str) -> bool:
        """投稿が既に保存されているか確認"""
        pass
        
    def add_post_id(self, post_id: str, date: str, category: str):
        """投稿IDを記録"""
        pass
```

### 6. データ検証
```python
def validate_cache_integrity(self,
                           start_date: str,
                           end_date: str) -> dict:
    """
    キャッシュデータの完全性を検証
    
    Returns:
        {
            "missing_dates": [...],
            "corrupted_files": [...],
            "statistics": {
                "total_posts": int,
                "by_category": {...}
            }
        }
    """
    pass
```

## 受け入れ条件
- [ ] JSONL形式でのデータ保存
- [ ] 既存ファイル形式との完全な互換性
- [ ] 効率的な重複チェック
- [ ] データ取得履歴の管理
- [ ] 欠損データの検出機能
- [ ] データ検証機能
- [ ] 単体テストの実装（モック使用）
- [ ] USE_PRAW_APIフラグでの切り替え

## 依存関係
- Pathlib（ファイル操作）
- JSON/JSONL処理
- SQLite（重複管理用）

## タスク
- [ ] 単体テストの作成（TDD）
- [ ] RedditCacheManagerクラスの基本実装
- [ ] ディレクトリ構造の自動作成
- [ ] JSONL保存機能
- [ ] JSONL読み込み機能
- [ ] 取得履歴管理機能
- [ ] PostIDTrackerクラス実装
- [ ] データ検証機能
- [ ] 欠損日付検出機能
- [ ] 段階的実装フラグのテスト
- [ ] 既存データとの互換性テスト
- [ ] 統合テスト作成