# チケット #003: シミュレーションエンジン実装

## 概要
バックテストのコアとなるシミュレーションエンジンの実装。日次での売買シミュレーションとポジション管理を行う

## 目的
- 期間中の営業日ループでの取引シミュレーション
- ポジション管理（ロング/ショート/フラット）
- 取引コストとスリッページの考慮
- 正確な損益計算

## 実装要件

### 1. クラス設計

```python
class BacktestEngine:
    def __init__(self, initial_capital: float = 100000.0):
        """
        Args:
            initial_capital: 初期資金（デフォルト: $100,000）
        """
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.position = None  # 'long', 'short', None
        self.trades = []  # 取引履歴
        self.equity_curve = []  # 資産推移
        
    def run(self, 
            ticker: str,
            start_date: str,
            end_date: str,
            strategy: TAFlowStrategy,
            fee_rate: float = 0.001,
            slippage_rate: float = 0.0005) -> BacktestResult:
        """
        バックテストを実行
        
        Args:
            ticker: 銘柄シンボル
            start_date: 開始日
            end_date: 終了日
            strategy: 戦略オブジェクト
            fee_rate: 取引手数料率
            slippage_rate: スリッページ率
            
        Returns:
            BacktestResult: 結果オブジェクト
        """
        pass
```

### 2. シミュレーションロジック

#### 日次ループ処理
1. 営業日リストの取得（pandas_market_calendars使用）
2. 各営業日について：
   - 当日終値後にstrategy.decide(ticker, date)を実行
   - シグナルを取得（Buy/Sell/Hold）
   - 翌営業日始値で約定処理

#### ポジション管理ルール
```
現在ポジション | シグナル | アクション
-------------|---------|------------
None         | Buy     | ロング新規
None         | Sell    | ショート新規
Long         | Sell    | ロング決済→ショート新規
Short        | Buy     | ショート決済→ロング新規
Long         | Buy     | 保有継続
Short        | Sell    | 保有継続
Any          | Hold    | 保有継続
```

#### 約定処理
- 買い約定価格 = 始値 × (1 + slippage_rate)
- 売り約定価格 = 始値 × (1 - slippage_rate)
- 取引コスト = 約定金額 × fee_rate
- 全資産を100%投入（レバレッジ1倍）

### 3. データ管理

#### 価格データの取得
- YahooFinance APIを使用
- 必要なデータ：OHLCV
- キャッシュ機構の実装

#### 取引履歴の記録
```python
@dataclass
class Trade:
    date: str
    action: str  # 'buy', 'sell'
    price: float
    shares: float
    fee: float
    slippage: float
    capital_after: float
```

## 受け入れ条件
- [ ] 営業日ベースでの正確なループ処理
- [ ] ポジション遷移の正確な実装
- [ ] スリッページと手数料の正しい計算
- [ ] 取引履歴の完全な記録
- [ ] エッジケース（データ欠損等）の処理
- [ ] Buy & Hold戦略の同時計算

## 依存関係
- pandas
- pandas_market_calendars
- yfinance
- TAFlowStrategy

## タスク
- [ ] BacktestEngineクラスの基本実装
- [ ] 営業日カレンダーの統合
- [ ] 価格データ取得機能
- [ ] ポジション管理ロジック
- [ ] 約定処理と手数料計算
- [ ] 取引履歴の記録機能
- [ ] Buy & Hold比較実装
- [ ] エラーハンドリング
- [ ] ユニットテスト作成