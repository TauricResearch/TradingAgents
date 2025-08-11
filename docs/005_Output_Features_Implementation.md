# チケット #005: 出力機能実装

## 概要
バックテスト結果の可視化とレポート生成機能の実装。ターミナル出力とHTMLレポートの2形式で結果を提供

## 目的
- 結果の即座の確認（ターミナル）
- 詳細な分析用レポート（HTML）
- インタラクティブなグラフによる視覚的理解

## 実装要件

### 1. ターミナル出力

#### サマリーテーブル
```python
class TerminalReporter:
    def display_summary(self, 
                       metrics: PerformanceMetrics,
                       buy_hold_metrics: PerformanceMetrics):
        """
        Richライブラリを使用した美しいテーブル表示
        """
        # 例:
        # ┌─────────────────────┬────────────┬────────────┐
        # │ Metric              │ Strategy   │ Buy & Hold │
        # ├─────────────────────┼────────────┼────────────┤
        # │ Total Return        │ +45.2%     │ +32.1%     │
        # │ Annual Return       │ +38.5%     │ +27.8%     │
        # │ Sharpe Ratio        │ 1.45       │ 1.12       │
        # │ Max Drawdown        │ -12.3%     │ -18.5%     │
        # │ Win Rate            │ 58.2%      │ N/A        │
        # │ Total Trades        │ 42         │ 1          │
        # └─────────────────────┴────────────┴────────────┘
```

#### プログレスバー
```python
def show_progress(self, current: int, total: int, message: str):
    """
    シミュレーション実行中の進捗表示
    """
    # Rich.progress を使用
```

### 2. HTMLレポート生成

#### レポート構造
```html
<!DOCTYPE html>
<html>
<head>
    <title>Backtest Report - {ticker} ({start} to {end})</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        /* レスポンシブデザイン */
    </style>
</head>
<body>
    <h1>バックテスト結果レポート</h1>
    
    <!-- 1. サマリーセクション -->
    <section id="summary">
        <!-- 実行パラメータ -->
        <!-- 主要指標の比較 -->
    </section>
    
    <!-- 2. グラフセクション -->
    <section id="charts">
        <!-- Equity Curve -->
        <!-- Drawdown Chart -->
        <!-- Returns Distribution -->
    </section>
    
    <!-- 3. 取引履歴 -->
    <section id="trades">
        <!-- ページネーション付きテーブル -->
    </section>
</body>
</html>
```

#### Plotlyグラフ実装

```python
class ChartGenerator:
    def create_equity_curve(self,
                           dates: List[str],
                           strategy_equity: List[float],
                           buyhold_equity: List[float]) -> str:
        """
        戦略とBuy&Holdの資産推移グラフ
        """
        pass
    
    def create_drawdown_chart(self,
                             dates: List[str],
                             drawdown_pct: List[float]) -> str:
        """
        ドローダウン推移グラフ
        """
        pass
    
    def create_returns_histogram(self,
                                daily_returns: List[float]) -> str:
        """
        日次リターンの分布
        """
        pass
```

### 3. レポート保存と管理

```python
class ReportManager:
    def __init__(self, reports_dir: str = "reports/"):
        self.reports_dir = reports_dir
    
    def save_report(self, 
                   html_content: str,
                   ticker: str,
                   start_date: str,
                   end_date: str) -> str:
        """
        レポートを保存し、ファイルパスを返す
        
        ファイル名形式: 
        {ticker}_{start}_{end}_{timestamp}.html
        """
        pass
    
    def open_in_browser(self, report_path: str):
        """
        デフォルトブラウザでレポートを開く
        """
        pass
```

## 受け入れ条件
- [ ] ターミナルでの見やすいサマリー表示
- [ ] インタラクティブなHTMLレポート
- [ ] 全グラフの正しい描画
- [ ] レスポンシブデザイン（モバイル対応）
- [ ] 取引履歴の完全な表示
- [ ] レポートの自動保存と管理
- [ ] ブラウザでの自動オープン機能

## 依存関係
- rich（ターミナルUI）
- plotly（グラフ描画）
- jinja2（HTMLテンプレート）
- webbrowser（ブラウザ制御）

## タスク
- [ ] TerminalReporterクラスの実装
- [ ] HTMLテンプレートの作成
- [ ] ChartGeneratorクラスの実装
- [ ] Equity Curveグラフ実装
- [ ] Drawdownグラフ実装
- [ ] リターン分布グラフ実装
- [ ] 取引履歴テーブル実装
- [ ] ReportManagerクラスの実装
- [ ] CSSスタイリング
- [ ] 統合テスト