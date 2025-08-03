# Reddit API レート制限の分析と最適なデータ収集戦略

## 調査結果サマリー

### Reddit API の現在のレート制限（2024年）

1. **認証済みOAuthクライアント**: 100 queries per minute (QPM)
2. **非認証クライアント**: 10 QPM（実質使用不可）
3. **バッチサイズ**: 1リクエストで最大100アイテム取得可能
4. **レート計算方法**: 10分間の平均で計算（バースト対応）
5. **制限単位**: OAuth Client ID ごと（ユーザーごとではない）

### 重要な制約

- **1000件制限**: 各検索・リストで最大1000件までしか取得できない
- **過去データ制限**: 6ヶ月以上前の投稿は取得が困難
- **料金**: 無料枠を超えると $0.24 per 1,000 API calls

## データ収集量の最適化案

### 現実的なデータ収集設定

#### 1. 少量運用（推奨：初期導入・テスト用）
```
対象銘柄: 10銘柄
Global News: 各subreddit 50件/日 × 5 = 250件
Company News: 各銘柄 50件/日 × 10 = 500件
日次取得時間: 約1分
月次バックフィル（30日）: 約5分
```

#### 2. 中規模運用（推奨：通常運用）
```
対象銘柄: 50銘柄
Global News: 各subreddit 100件/日 × 5 = 500件
Company News: 各銘柄 50件/日 × 50 = 2,500件
日次取得時間: 約2分
月次バックフィル（30日）: 約21分
```

#### 3. 大規模運用（S&P500等）
```
対象銘柄: 500銘柄
Global News: 各subreddit 100件/日 × 5 = 500件
Company News: 各銘柄 20件/日 × 500 = 10,000件
日次取得時間: 約7分
月次バックフィル（30日）: 約3.5時間
```

## レート制限を考慮した実装戦略

### 1. リクエスト間隔の設定
```python
# 安全な設定
SAFE_REQUEST_INTERVAL = 0.75  # 秒（80 requests/minute）

# アグレッシブな設定（モニタリング必須）
AGGRESSIVE_REQUEST_INTERVAL = 0.6  # 秒（100 requests/minute）

# 推奨：段階的アプローチ
if total_requests < 100:
    interval = 0.6  # 短時間なら高速
elif total_requests < 1000:
    interval = 0.75  # 中規模は安全に
else:
    interval = 1.0  # 大規模は慎重に
```

### 2. 効率的なデータ取得パターン

#### A. 日次更新（推奨）
```python
# 毎日深夜に前日分のデータを取得
# メリット: API負荷分散、安定運用
# デメリット: リアルタイム性なし
schedule.every().day.at("02:00").do(fetch_yesterday_data)
```

#### B. 複数回更新
```python
# 1日3回更新（市場開始前、昼、終了後）
# メリット: 準リアルタイム
# デメリット: API使用量3倍
schedule.every().day.at("08:00").do(fetch_recent_data)
schedule.every().day.at("13:00").do(fetch_recent_data)
schedule.every().day.at("17:00").do(fetch_recent_data)
```

#### C. 優先度ベース
```python
# 重要銘柄は頻繁に、その他は日次
HIGH_PRIORITY = ["AAPL", "MSFT", "NVDA", "TSLA"]
fetch_interval = {
    "high": 4,  # 4時間ごと
    "medium": 12,  # 12時間ごと
    "low": 24  # 24時間ごと
}
```

### 3. エラーハンドリングとレート制限対策

```python
class RedditRateLimiter:
    def __init__(self):
        self.request_times = deque(maxlen=100)
        self.minute_window = 60
        
    def wait_if_needed(self):
        now = time.time()
        # 直近100リクエストをチェック
        if len(self.request_times) == 100:
            oldest = self.request_times[0]
            if now - oldest < self.minute_window:
                sleep_time = self.minute_window - (now - oldest) + 1
                time.sleep(sleep_time)
        
        self.request_times.append(now)
```

## 推奨構成

### 初期導入時
1. **対象**: TOP 10銘柄 + Global News
2. **頻度**: 日次更新（深夜2時）
3. **データ量**: 各50-100件/日
4. **所要時間**: 約1-2分/日
5. **月間API使用量**: 約1,650 calls

### 本番運用時
1. **対象**: 50銘柄 + Global News
2. **頻度**: 
   - 重要10銘柄: 6時間ごと
   - その他40銘柄: 日次
3. **データ量**: 
   - 重要銘柄: 100件/回
   - その他: 50件/日
4. **所要時間**: 約10分/日（分散実行）
5. **月間API使用量**: 約15,000 calls

### スケーラビリティ考慮事項
- 500銘柄以上は複数のClient IDを使用検討
- 時間帯分散（米国市場時間外を活用）
- キャッシュ活用でAPI呼び出し削減
- 増分更新（新規投稿のみ取得）

## まとめ

Reddit APIのレート制限（100 QPM）を考慮すると、中規模運用（50銘柄程度）が最もバランスが良い。データ収集量は各投稿50-100件/日が現実的で、これにより：

- 十分な市場センチメント把握が可能
- API制限内で安定運用
- 日次更新が数分で完了
- 月次バックフィルも30分以内

大規模運用（500銘柄以上）の場合は、優先度設定や時間分散などの工夫が必要。