# チケット #004: 評価指標計算実装

## 概要
バックテスト結果の評価指標を計算するモジュールの実装。標準的な金融指標を網羅的に計算

## 目的
- 戦略パフォーマンスの定量的評価
- Buy & Holdとの比較可能な指標提供
- 業界標準の指標による結果の信頼性確保

## 実装要件

### 1. 評価指標クラス

```python
@dataclass
class PerformanceMetrics:
    # リターン関連
    total_return: float  # 累積リターン
    annual_return: float  # 年率リターン
    
    # リスク関連
    sharpe_ratio: float  # シャープレシオ
    max_drawdown: float  # 最大ドローダウン
    max_drawdown_duration: int  # 最大DD期間（日数）
    
    # 取引統計
    win_rate: float  # 勝率
    profit_factor: float  # プロフィットファクター
    total_trades: int  # 総取引回数
    winning_trades: int  # 勝ち取引数
    losing_trades: int  # 負け取引数
    
    # その他
    final_capital: float  # 最終資産
    trading_days: int  # 取引日数

class MetricsCalculator:
    def calculate(self, 
                 equity_curve: List[float],
                 trades: List[Trade],
                 initial_capital: float,
                 start_date: str,
                 end_date: str) -> PerformanceMetrics:
        """
        評価指標を計算
        """
        pass
```

### 2. 指標計算の詳細

#### 累積リターン
```
累積リターン = (最終資産 / 初期資産 - 1) × 100%
```

#### 年率リターン
```
年率リターン = ((1 + 累積リターン) ^ (365 / 日数) - 1) × 100%
```

#### シャープレシオ
```
日次リターン = (今日の資産 / 昨日の資産) - 1
シャープレシオ = (日次平均リターン / 日次標準偏差) × √252
※無リスク金利 = 0と仮定
```

#### 最大ドローダウン
```python
def calculate_max_drawdown(equity_curve: List[float]) -> tuple[float, int]:
    """
    Returns:
        (max_drawdown_pct, max_duration_days)
    """
    peak = equity_curve[0]
    max_dd = 0
    max_duration = 0
    current_duration = 0
    
    for value in equity_curve:
        if value > peak:
            peak = value
            current_duration = 0
        else:
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)
            current_duration += 1
            max_duration = max(max_duration, current_duration)
    
    return max_dd * 100, max_duration
```

#### 勝率とプロフィットファクター
```
勝率 = 利益取引数 / 総取引数 × 100%
プロフィットファクター = 総利益 / 総損失
```

### 3. Buy & Hold との比較

```python
class ComparativeMetrics:
    def compare(self,
               strategy_metrics: PerformanceMetrics,
               buy_hold_metrics: PerformanceMetrics) -> dict:
        """
        戦略とBuy & Holdを比較
        
        Returns:
            {
                'excess_return': float,  # 超過リターン
                'relative_sharpe': float,  # シャープレシオの差
                'relative_drawdown': float,  # DD改善率
            }
        """
        pass
```

## 受け入れ条件
- [ ] 全指標の正確な計算
- [ ] エッジケース（取引なし、損失のみ等）の処理
- [ ] Buy & Hold指標の同時計算
- [ ] 比較指標の提供
- [ ] 計算精度のテスト（小数点以下の扱い）
- [ ] パフォーマンス（大量データでの計算速度）

## 依存関係
- numpy（統計計算）
- pandas（時系列処理）
- BacktestEngineの出力形式

## タスク
- [ ] PerformanceMetricsデータクラスの定義
- [ ] MetricsCalculatorクラスの基本実装
- [ ] 各指標の計算メソッド実装
- [ ] Buy & Hold計算機能
- [ ] 比較指標計算機能
- [ ] エラーハンドリング（ゼロ除算等）
- [ ] 単体テストの作成
- [ ] ドキュメント作成