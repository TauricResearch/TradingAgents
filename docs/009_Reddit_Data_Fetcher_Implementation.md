# チケット #009: Redditデータ取得ロジック実装

## 概要
RedditPrawClientを使用して、実際のデータ取得とフィルタリングを行うビジネスロジックの段階的実装

## 目的
- Global NewsとCompany Newsの効率的な取得
- 企業関連投稿の検索とフィルタリング
- 重複排除とデータ整形
- 日付指定での取得機能
- 既存システムとの互換性維持

## 実装要件

### 1. 段階的実装アプローチ
```python
# 既存システムとの並行動作をサポート
from tradingagents.config import USE_PRAW_API

if USE_PRAW_API:
    # 新しいpraw実装を使用
    fetcher = RedditDataFetcher(client, config)
else:
    # 既存のファイルベースの実装を使用
    return fetch_from_local_files()
```

### 2. クラス設計
```python
class RedditDataFetcher:
    def __init__(self, client: RedditPrawClient, config: dict):
        """
        Args:
            client: RedditPrawClientインスタンス
            config: 取得設定（subredditリスト、取得件数等）
        """
        self.client = client
        self.config = config
        self.seen_post_ids = set()  # 重複排除用
        
    def fetch_global_news(self, 
                         date: str,
                         limit_per_subreddit: int = 100) -> List[dict]:
        """
        指定日のグローバルニュースを取得
        
        Args:
            date: 対象日付 (YYYY-MM-DD)
            limit_per_subreddit: 各subredditからの取得件数
            
        Returns:
            ニュース投稿のリスト
        """
        pass
    
    def fetch_company_news(self,
                          ticker: str,
                          company_name: str,
                          date: str,
                          limit: int = 50) -> List[dict]:
        """
        特定企業のニュースを取得
        
        Args:
            ticker: ティッカーシンボル
            company_name: 企業名
            date: 対象日付
            limit: 取得件数
            
        Returns:
            企業関連投稿のリスト
        """
        pass
```

### 2. 企業投稿の検索戦略
```python
def build_search_queries(ticker: str, company_name: str) -> List[str]:
    """
    効果的な検索クエリを生成
    
    Returns:
        検索クエリのリスト
        例: ["AAPL", "Apple", "$AAPL", "Apple Inc"]
    """
    queries = [
        f'"{ticker}"',
        f'"{company_name}"',
        f'${ticker}',  # Cashtag
    ]
    
    # 企業名のバリエーション対応
    if " OR " in company_name:
        for variant in company_name.split(" OR "):
            queries.append(f'"{variant.strip()}"')
    
    return queries
```

### 3. データフィルタリング
```python
def filter_posts_by_date(posts: List[dict], target_date: str) -> List[dict]:
    """
    指定日付の投稿のみをフィルタリング
    
    Args:
        posts: 投稿リスト
        target_date: 対象日付 (YYYY-MM-DD)
        
    Returns:
        フィルタリング後の投稿リスト
    """
    pass

def filter_company_relevant_posts(posts: List[dict], 
                                 ticker: str,
                                 company_name: str) -> List[dict]:
    """
    企業に関連する投稿のみをフィルタリング
    
    タイトルまたは本文に企業名/ティッカーが含まれるもの
    """
    pass
```

### 4. データ整形
```python
def format_post_data(post: praw.models.Submission) -> dict:
    """
    prawの投稿オブジェクトを統一形式に変換
    
    Returns:
        {
            "id": str,
            "title": str,
            "selftext": str,
            "url": str,
            "ups": int,
            "created_utc": int,
            "subreddit": str,
            "author": str,
            "num_comments": int,
            "ticker": str  # 企業投稿の場合
        }
    """
    pass
```

### 5. バッチ処理
```python
def fetch_historical_data(self,
                         start_date: str,
                         end_date: str,
                         tickers: List[str] = None,
                         categories: List[str] = ["global_news", "company_news"]):
    """
    過去データの一括取得
    
    Args:
        start_date: 開始日
        end_date: 終了日
        tickers: 対象ティッカーリスト
        categories: 取得カテゴリ
        
    Yields:
        (date, category, data) のタプル
    """
    pass
```

## 受け入れ条件
- [ ] 指定日付のデータのみを正確に取得
- [ ] 企業関連投稿の適切なフィルタリング
- [ ] 重複投稿の排除（Reddit post ID使用）
- [ ] データ形式が既存システムと互換
- [ ] エラー時の適切な処理
- [ ] 効率的なAPI使用（最小限のリクエスト）
- [ ] 単体テストの実装（モック使用）
- [ ] USE_PRAW_APIフラグでの切り替え動作

## 依存関係
- RedditPrawClient（チケット#008）
- 既存のreddit_utils.py
- デフォルトTickerリスト設定

## タスク
- [ ] 単体テストの作成（TDD）
- [ ] RedditDataFetcherクラスの基本実装
- [ ] Global News取得機能
- [ ] Company News取得機能
- [ ] 検索クエリ生成ロジック
- [ ] 日付フィルタリング機能
- [ ] 企業関連性フィルタリング
- [ ] データ整形機能
- [ ] 重複排除機能
- [ ] バッチ処理機能
- [ ] 段階的実装フラグのテスト
- [ ] 統合テスト作成