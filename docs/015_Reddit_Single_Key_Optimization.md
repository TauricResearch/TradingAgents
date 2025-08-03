# チケット #015: Reddit単一APIキー最適化実装

## 概要
単一のReddit APIキーで最大限のパフォーマンスを実現する最適化実装（基本機能実装後に検討）

## 目的
- API呼び出し回数の最小化
- 待機時間の有効活用
- データ処理の並列化
- レート制限内での最速処理

## 注意
この最適化は基本機能が安定動作した後に実装を検討する

## 実装要件

### 1. バッチ取得の最適化
```python
class OptimizedRedditFetcher:
    def fetch_multiple_subreddits(self, 
                                 subreddits: List[str],
                                 limit: int = 100) -> Dict[str, List[dict]]:
        """
        複数subredditを1回のAPI呼び出しで取得
        
        Args:
            subreddits: subredditのリスト
            limit: 取得件数（最大100）
            
        Example:
            # 5つのsubredditから各20件ずつ取得したい場合
            # 通常: 5回のAPI呼び出し
            # 最適化: 1回のAPI呼び出し
            combined = "+".join(subreddits)
            posts = reddit.subreddit(combined).hot(limit=100)
        """
        pass
```

### 2. 非同期処理の活用
```python
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

class AsyncRedditProcessor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    async def process_batch(self, tickers: List[str], date: str):
        """
        API呼び出しと並列処理可能なタスクを効率的に実行
        """
        tasks = []
        
        # API呼び出し（レート制限あり）
        for ticker in tickers:
            api_data = await self.fetch_with_rate_limit(ticker, date)
            
            # データ処理は並列実行
            tasks.extend([
                self.executor.submit(self.sentiment_analysis, api_data),
                self.executor.submit(self.save_to_cache, api_data),
                self.executor.submit(self.extract_metrics, api_data)
            ])
        
        # 並列処理の完了を待つ
        await asyncio.gather(*tasks)
```

### 3. インテリジェントキャッシング
```python
class SmartCache:
    def __init__(self):
        self.memory_cache = {}  # 頻繁にアクセスされるデータ
        self.disk_cache = RedditCacheManager()
        self.access_patterns = {}  # アクセスパターンの追跡
        
    def get_with_prediction(self, ticker: str, date: str):
        """
        アクセスパターンを学習して先読みキャッシング
        """
        # よく一緒にアクセスされる銘柄を予測
        related_tickers = self.predict_related_tickers(ticker)
        
        # バックグラウンドでプリフェッチ
        self.prefetch_async(related_tickers, date)
```

### 4. API呼び出しの最適化戦略
```python
class APICallOptimizer:
    def __init__(self):
        self.call_queue = PriorityQueue()
        self.rate_limiter = RateLimiter(calls_per_minute=80)
        
    def optimize_call_order(self, requests: List[APIRequest]) -> List[APIRequest]:
        """
        API呼び出しの順序を最適化
        
        優先順位:
        1. 複数銘柄を含むバッチリクエスト
        2. 人気銘柄
        3. キャッシュミスのデータ
        4. その他
        """
        # バッチ可能なリクエストをグループ化
        batched = self.group_batchable_requests(requests)
        
        # 優先度順にソート
        return self.sort_by_priority(batched)
```

### 5. 処理パイプライン
```python
class ProcessingPipeline:
    """
    データ取得から保存までのパイプライン処理
    """
    def __init__(self):
        self.stages = [
            self.fetch_stage,      # API呼び出し（直列）
            self.filter_stage,     # フィルタリング（並列可）
            self.transform_stage,  # データ変換（並列可）
            self.analyze_stage,    # 分析処理（並列可）
            self.save_stage       # 保存（並列可）
        ]
        
    async def run_pipeline(self, input_data):
        """
        パイプライン実行
        """
        data = input_data
        
        for stage in self.stages:
            if stage.can_parallelize:
                # 並列実行
                data = await self.run_parallel(stage, data)
            else:
                # 直列実行（API呼び出しなど）
                data = await stage(data)
                
        return data
```

### 6. レート制限の賢い管理
```python
class SmartRateLimiter:
    def __init__(self, calls_per_minute: int = 80):
        self.calls_per_minute = calls_per_minute
        self.call_history = deque(maxlen=calls_per_minute)
        
    def adaptive_wait(self):
        """
        現在のレート使用状況に応じて待機時間を調整
        """
        usage_rate = self.get_current_usage_rate()
        
        if usage_rate > 0.9:  # 90%以上使用
            # 安全のため長めに待機
            wait_time = 1.0
        elif usage_rate > 0.7:  # 70-90%使用
            # 標準的な待機
            wait_time = 0.75
        else:  # 70%未満
            # 積極的に使用
            wait_time = 0.6
            
        return wait_time
```

## 受け入れ条件
- [ ] 基本機能が安定動作していること
- [ ] 単一APIキーで現在より30%以上の高速化
- [ ] レート制限違反ゼロ
- [ ] API呼び出し数の最小化を実証
- [ ] 並列処理による効率化の測定
- [ ] エラー時の適切なフォールバック

## 依存関係
- asyncio（非同期処理）
- aiohttp（非同期HTTP）
- concurrent.futures（並列処理）
- 既存のReddit実装モジュール

## タスク（基本機能実装後）
- [ ] 基本機能の安定性確認
- [ ] OptimizedRedditFetcherクラスの実装
- [ ] 非同期処理フレームワークの構築
- [ ] バッチ取得ロジックの実装
- [ ] インテリジェントキャッシングシステム
- [ ] API呼び出し最適化アルゴリズム
- [ ] 処理パイプラインの実装
- [ ] 適応的レート制限管理
- [ ] パフォーマンステスト
- [ ] 最適化効果の測定ツール
- [ ] ドキュメント作成