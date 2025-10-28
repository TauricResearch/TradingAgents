<!-- Inclusion Mode: Always -->
# 技術スタック: TradingAgents

## 1. アーキテクチャ
TradingAgentsフレームワークは、**LangGraph**を使用したステートフルなグラフアーキテクチャ上に構築された**マルチエージェントシステム**です。これにより、異なるエージェントを簡単に追加、削除、または再設定できる柔軟でモジュール式のワークフローが可能になります。情報と制御の流れはグラフによって管理され、エージェントノード間で状態が渡されます。

## 2. バックエンドとコアロジック
- **言語**: Python (バージョン 3.10)
- **コアフレームワーク**: エージェントの作成とオーケストレーションのための`langchain`および`langgraph`。
- **LLMプロバイダー**: このフレームワークは複数のLLMプロバイダーと連携できるように設計されています。主な統合先は以下の通りです：
    - OpenAI (`langchain-openai`)
    - Anthropic (`langchain-anthropic`)
    - Google Gemini (`langchain-google-genai`)
- **CLI**: コマンドラインインターフェースは、対話的な使用と整形された出力のために`typer`と`rich`を使用して構築されています。
- **データハンドリング**: データ操作には`pandas`が使用されます。
- **ベクトルストア**: エージェントの記憶・リフレクション機構には`chromadb`が使用されます。

## 3. データソースとAPI
このフレームワークは、いくつかの金融データAPIと統合されています。各カテゴリのデータソースは設定可能です。
- **主要なデータAPI**:
    - **Alpha Vantage**: ファンダメンタルデータ、ニュース、テクニカル指標に使用されます。
    - **yfinance**: 主要な株価データ（OHLCV）およびテクニカル指標に使用されます。
- **その他のデータソース**:
    - `praw` (Reddit API)
    - `feedparser` (RSSフィード)

## 4. 開発環境
- **Pythonバージョン**: 3.10（`.python-version`で指定）。
- **依存関係**: `pip`を介して管理され、パッケージは`requirements.txt`および`pyproject.toml`にリストされています。
- **仮想環境**: 仮想環境（例：`conda`や`venv`）の使用が推奨されます。

## 5. 一般的なコマンド
- **依存関係のインストール**:
  ```bash
  pip install -r requirements.txt
  ```
- **CLIアプリケーションの実行**:
  ```bash
  python -m cli.main
  ```
- **パッケージ例の実行**:
  ```bash
  python main.py
  ```

## 6. 環境変数
アプリケーションは、通常プロジェクトルートの`.env`ファイルで設定されるAPIキーを必要とします。
- `OPENAI_API_KEY`: OpenAIサービス（または互換エンドポイント）用のAPIキー。
- `ALPHA_VANTAGE_API_KEY`: Alpha Vantageデータサービス用のAPIキー。