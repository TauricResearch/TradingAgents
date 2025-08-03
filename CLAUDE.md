# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Todo管理ルール

### チケット内のタスク管理
- 各実装チケット（docs/XXX_*.md）内のタスクは`- [ ]`で未完了、`- [x]`で完了を表す
- タスクが完了したら、該当ファイルを編集して`- [ ]`を`- [x]`に変更する
- 例：
  ```markdown
  ## タスク
  - [x] 完了したタスク
  - [ ] 未完了のタスク
  ```

## プロジェクト概要

TradingAgentsは、実際の投資会社の構造を模倣したマルチエージェントLLMトレーディングフレームワークです。LangGraphを使用して構築され、ファンダメンタル分析、センチメント分析、テクニカル分析などを行う専門的なエージェントが協調して市場分析と取引判断を行います。

## 重要なコマンド

### インストールと環境セットアップ
```bash
# 仮想環境の作成（Python 3.10以上が必要）
conda create -n tradingagents python=3.13
conda activate tradingagents

# 依存関係のインストール
pip install -r requirements.txt

# 必要なAPIキーの設定
export FINNHUB_API_KEY=$YOUR_FINNHUB_API_KEY
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
```

### CLIの実行
```bash
python -m cli.main
```

### パッケージとしての使用
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2024-05-10")
```

## アーキテクチャと主要コンポーネント

### ディレクトリ構造
- `tradingagents/` - メインパッケージ
  - `agents/` - すべてのエージェント実装
    - `analysts/` - 4種類のアナリストエージェント（Market, Social, News, Fundamentals）
    - `researchers/` - Bull/Bearリサーチャー（議論によるバランス評価）
    - `trader/` - 取引判断を行うトレーダーエージェント
    - `managers/` - リサーチマネージャーとリスクマネージャー
    - `risk_mgmt/` - リスク評価のディベーターエージェント
  - `dataflows/` - データ取得とキャッシュ管理
  - `graph/` - LangGraphベースのワークフロー実装
- `cli/` - リッチなCLIインターフェース

### 主要な設定ファイル
- `tradingagents/default_config.py` - デフォルト設定
  - LLMプロバイダー設定（OpenAI、Anthropic、Google）
  - モデル選択（deep_think_llm、quick_think_llm）
  - 議論ラウンド数の設定
  - オンライン/オフラインツールの切り替え

### エージェントフロー
1. **アナリストチーム** - 市場、ソーシャル、ニュース、ファンダメンタル分析を並行実行
2. **リサーチチーム** - Bull/Bearリサーチャーによる議論と評価
3. **トレーダー** - 総合的な取引判断
4. **リスク管理** - ポートフォリオリスクの評価と調整
5. **ポートフォリオマネージャー** - 最終承認/拒否

### データソース
- FinnHub API（金融データ）
- Reddit API（ソーシャルセンチメント）
- Google News（ニュース分析）
- Yahoo Finance（価格データ）
- StockStats（テクニカル指標）

## 開発時の注意点

### API使用量
フレームワークは大量のAPIコールを行うため、テスト時は以下を推奨：
- `gpt-4o-mini`や`o4-mini`を使用してコストを削減
- `config["max_debate_rounds"]`を1に設定して議論ラウンドを制限
- `config["online_tools"]`をFalseにしてキャッシュデータを使用

### メモリ管理
各エージェントは独自のメモリ（`FinancialSituationMemory`）を持ち、`results_dir`に保存されます。

### 現在の制限
- 正式なテストフレームワークが未設定
- リンターやコード品質ツールが未設定
- CI/CDパイプラインが未実装

## トラブルシューティング

### M1 Mac (ARM64) での問題
- `chromadb`のインストール時にビルドエラーが発生する場合：`pip install --upgrade --force-reinstall chromadb`
- numpy互換性の問題：`pip install numpy==1.26.2`を使用