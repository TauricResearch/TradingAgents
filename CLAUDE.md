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
  - `config.py` - 環境変数ベースの設定管理
- `cli/` - リッチなCLIインターフェース
- `agents/` - サブエージェント定義（各種ドメイン特化エージェント）
- `docs/` - 実装チケットとドキュメント

### 主要な設定ファイル
- `.env` - 環境変数設定（APIキー、LLM設定など）
- `tradingagents/config.py` - 設定のロードと管理
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

### 実装チケット管理
`docs/`ディレクトリに番号付き実装チケット（例：001_TAFlowStrategy_Implementation.md）があり、各機能の実装タスクを管理しています。

### コード品質チェック
```bash
# 型チェックの実行（mypyを使用）
mypy tradingagents/ cli/

# 特定ファイルの型チェック
mypy path/to/file.py
```

Claude Codeでのpost-toolフックにより、Pythonファイル編集時に自動的にmypy型チェックが実行されます。

### CI/CDパイプライン

#### GitHub Actions ワークフロー
- **PR Pipeline** (`.github/workflows/pr.yml`): プルリクエスト時の自動テストと品質チェック
- **Main Pipeline** (`.github/workflows/main.yml`): メインブランチへのプッシュ時の完全テストスイート
- **Release Pipeline** (`.github/workflows/release.yml`): タグプッシュ時の自動リリースプロセス

#### テストフレームワーク
```bash
# ユニットテストの実行
pytest tests/unit/ -v

# カバレッジ付きテスト
pytest tests/ --cov=tradingagents --cov-report=html

# 並列実行
pytest tests/ -n auto

# 特定のマーカーでテスト
pytest -m "not slow"
```

#### コード品質ツール
- **Black**: コードフォーマッター
- **Ruff**: 高速リンター
- **mypy**: 静的型チェッカー
- **bandit**: セキュリティスキャナー
- **safety**: 依存関係脆弱性チェック

#### post-toolフック
`.claude_code/python_tools_check.sh`により、Pythonファイル編集時に自動的に以下が実行されます：
- Black (自動フォーマット)
- Ruff (リンティングと自動修正)
- mypy (型チェック)

## トラブルシューティング

### M1 Mac (ARM64) での問題
- `chromadb`のインストール時にビルドエラーが発生する場合：`pip install --upgrade --force-reinstall chromadb`
- numpy互換性の問題：`pip install numpy==1.26.2`を使用