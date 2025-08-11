# TradingAgents バックテスト機能

## 概要

TradingAgentsのマルチエージェントシステムを使用した株式取引戦略のバックテスト機能です。過去の市場データに対して、実際のエージェントフロー（アナリスト→リサーチャー→トレーダー→リスク管理→ポートフォリオマネージャー）を実行し、パフォーマンスを評価します。

## インストール

```bash
# 依存関係のインストール
pip install -r requirements.txt
```

## 使用方法

### 1. バックテストの実行

```bash
python -m cli.main backtest run \
    --ticker AAPL \
    --start 2024-01-01 \
    --end 2024-03-31 \
    --fee 0.001 \
    --slippage 0.0005
```

#### パラメータ
- `--ticker`: 銘柄シンボル（必須）
- `--start`: 開始日 YYYY-MM-DD（必須）
- `--end`: 終了日 YYYY-MM-DD（必須）
- `--fee`: 取引手数料率（デフォルト: 0.1%）
- `--slippage`: スリッページ率（デフォルト: 0.05%）
- `--initial-capital`: 初期資金（デフォルト: $100,000）

### 2. 過去の結果一覧

```bash
# すべての結果を表示
python -m cli.main backtest list

# 特定の銘柄でフィルタ
python -m cli.main backtest list --ticker AAPL

# 表示数を制限
python -m cli.main backtest list --limit 10
```

### 3. 結果の詳細表示

```bash
# ID 5の結果を表示（HTMLレポートを開く）
python -m cli.main backtest show 5
```

### 4. 結果の比較

```bash
# ID 3とID 7の結果を比較
python -m cli.main backtest compare 3 7
```

## シミュレーション仕様

### ポジション管理
- 未保有で Buy → ロング新規
- 未保有で Sell → ショート新規
- ロング中に Sell → ロング決済＋ショート新規
- ショート中に Buy → ショート決済＋ロング新規
- Hold → 現在のポジションを維持

### 取引ルール
- 全資産を100%投入（レバレッジ1倍）
- 取引コスト = 取引金額 × fee_rate
- スリッページ:
  - 買い: 価格 × (1 + slippage_rate)
  - 売り: 価格 × (1 - slippage_rate)

## 評価指標

| 指標 | 説明 |
|------|------|
| Total Return | 累積リターン |
| Annual Return | 年率換算リターン |
| Sharpe Ratio | リスク調整後リターン |
| Max Drawdown | 最大ドローダウン |
| Win Rate | 勝率 |
| Profit Factor | 総利益 ÷ 総損失 |

## 出力

### 1. ターミナル出力
美しいテーブル形式で戦略とBuy & Holdの比較結果を表示

### 2. HTMLレポート
- インタラクティブなグラフ（Plotly）
- 資産推移曲線
- ドローダウンチャート
- リターン分布
- 取引履歴テーブル

レポートは `reports/` ディレクトリに保存されます。

### 3. データベース永続化
結果は `results.sqlite` に保存され、後から参照・比較が可能です。

## プログラム例

```python
from tradingagents.backtest.ta_flow_strategy import TAFlowStrategy
from tradingagents.backtest.engine import BacktestEngine
from tradingagents.default_config import DEFAULT_CONFIG

# 設定
config = DEFAULT_CONFIG.copy()
config["online_tools"] = False  # オフラインモード

# 戦略の初期化
strategy = TAFlowStrategy(config=config)

# バックテストエンジンの初期化
engine = BacktestEngine(initial_capital=100000)

# バックテスト実行
result = engine.run(
    ticker="NVDA",
    start_date="2024-01-01",
    end_date="2024-03-31",
    strategy=strategy,
    fee_rate=0.001,
    slippage_rate=0.0005
)

print(f"Total Return: {result.metrics.total_return:.2%}")
print(f"Sharpe Ratio: {result.metrics.sharpe_ratio:.2f}")
print(f"Max Drawdown: {result.metrics.max_drawdown:.2%}")
```

## 注意事項

1. **APIキー設定**: 環境変数に以下を設定してください
   ```bash
   export OPENAI_API_KEY=your_api_key
   export FINNHUB_API_KEY=your_api_key
   ```

2. **オフラインモード**: バックテストは自動的にオフラインモードで実行され、キャッシュされたデータのみを使用します

3. **データの先読み防止**: 各日の判断は、その日の終値データまでしか使用しません

4. **計算負荷**: LLMを使用するため、長期間のバックテストは時間がかかります

## トラブルシューティング

### エラー: "No price data available"
- インターネット接続を確認してください
- 銘柄シンボルが正しいか確認してください
- 指定期間に市場が開いていたか確認してください

### エラー: "Strategy error"
- APIキーが正しく設定されているか確認してください
- LLMのレート制限に達していないか確認してください

## 拡張予定

- 複数銘柄の同時シミュレーション
- ポートフォリオ最適化
- リアルタイム取引との統合
- より詳細なリスク分析