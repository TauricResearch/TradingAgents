# TradingAgents 技術仕様書

## プロジェクト概要

TradingAgentsは、実世界の投資会社の組織構造を模倣したマルチエージェントLLMベースの金融取引フレームワークです。専門化されたAIエージェントが協調して市場分析と取引判断を行います。

## システムアーキテクチャ

### 1. コア構成

```
TradingAgents/
├── tradingagents/          # コアパッケージ
│   ├── agents/            # マルチエージェントシステム
│   ├── dataflows/         # データ処理・API統合
│   ├── graph/             # グラフベースオーケストレーション
│   └── default_config.py  # デフォルト設定
├── cli/                   # コマンドラインインターフェース
└── main.py               # エントリーポイント
```

### 2. エージェントシステム詳細

#### 2.1 エージェント階層

**Phase I: アナリストチーム**
- **Market Analyst**: テクニカル分析（SMA、EMA、MACD、RSI、ボリンジャーバンド等）
- **Social Media Analyst**: Reddit、ソーシャルメディアのセンチメント分析
- **News Analyst**: グローバルニュース、マクロ経済指標の分析
- **Fundamentals Analyst**: 財務諸表、インサイダー取引、企業業績分析

**Phase II: リサーチチーム**
- **Bull Researcher**: 楽観的視点での投資機会評価
- **Bear Researcher**: 悲観的視点でのリスク評価
- **Research Manager**: ディベートの調整と最終判断

**Phase III: トレーディングチーム**
- **Trader**: 全分析を統合し、取引戦略を策定

**Phase IV: リスク管理チーム**
- **Aggressive Debator**: 積極的リスク姿勢
- **Conservative Debator**: 保守的リスク姿勢
- **Neutral Debator**: 中立的リスク評価
- **Risk Manager**: リスク評価の統合と最終判断

**Phase V: ポートフォリオ管理**
- **Portfolio Manager**: 最終取引承認/拒否

#### 2.2 エージェント間通信

```python
# 状態管理クラス
class AgentState(MessagesState):
    company_of_interest: str
    trade_date: str
    market_report: str
    sentiment_report: str
    news_report: str
    fundamentals_report: str
    investment_plan: str
    trader_investment_plan: str
    final_trade_decision: str

class InvestDebateState:
    bull_history: str
    bear_history: str
    judge_decision: str
    count: int

class RiskDebateState:
    risky_history: str
    safe_history: str
    neutral_history: str
    judge_decision: str
    count: int
```

### 3. データフロー・API統合

#### 3.1 外部データソース

**金融データプロバイダー**
- **Yahoo Finance** (yfinance): 株価、出来高、財務データ
- **FinnHub**: ニュース、インサイダー取引、センチメント
- **StockStats**: テクニカル指標計算

**ソーシャル・ニュースデータ**
- **Reddit API** (praw): r/wallstreetbets等のセンチメント
- **Google News**: 最新ニュース記事
- **OpenAI API**: リアルタイムニュース要約

#### 3.2 データキャッシング

```python
# オンライン/オフラインモード切替
config["online_tools"] = True  # リアルタイムデータ
config["online_tools"] = False # キャッシュデータ使用
```

### 4. LLM統合システム

#### 4.1 対応LLMプロバイダー

```python
# プロバイダー設定
config["llm_provider"] = "openai"      # OpenAI GPT
config["llm_provider"] = "anthropic"   # Claude
config["llm_provider"] = "google"      # Gemini
config["llm_provider"] = "ollama"      # ローカルLLM
config["llm_provider"] = "openrouter"  # OpenRouter
```

#### 4.2 デュアルLLM戦略

```python
# 深い思考モデル（複雑な分析・判断）
config["deep_think_llm"] = "o1-preview"  # または gpt-4o

# 速い思考モデル（迅速な応答）
config["quick_think_llm"] = "gpt-4o-mini"
```

### 5. メモリ・学習システム

#### 5.1 FinancialSituationMemory

```python
class FinancialSituationMemory:
    def __init__(self, name, config):
        # ChromaDBベクトルデータベース使用
        # OpenAI/Nomic埋め込みモデル
        
    def add_situations(self, situations_and_advice):
        # 過去の取引状況と結果を保存
        
    def get_memories(self, current_situation, n_matches=1):
        # 類似状況から学習を取得
```

#### 5.2 メモリ種別

- **bull_memory**: 楽観的予測の履歴
- **bear_memory**: 悲観的予測の履歴
- **trader_memory**: 取引決定の履歴
- **invest_judge_memory**: 投資判断の履歴
- **risk_manager_memory**: リスク評価の履歴

### 6. グラフベース実行フロー

#### 6.1 LangGraphフレームワーク

```python
# グラフ構築
workflow = StateGraph(AgentState)

# ノード追加
workflow.add_node("Market Analyst", market_analyst_node)
workflow.add_node("tools_market", tool_node)

# 条件付きエッジ
workflow.add_conditional_edges(
    "Market Analyst",
    should_continue_market,
    ["tools_market", "Msg Clear Market"]
)
```

#### 6.2 実行フロー

1. **並列分析フェーズ**: 全アナリストが同時にデータ収集
2. **リサーチディベート**: Bull vs Bear、最大N回のディベート
3. **取引決定**: トレーダーが統合レポート作成
4. **リスク評価**: 3つの視点からリスク議論
5. **最終承認**: ポートフォリオマネージャーが決定

### 7. CLI技術仕様

#### 7.1 リアルタイムUI

**Richライブラリによる4パネル表示**
```python
Layout(
    Header: ウェルカムメッセージ
    Progress: エージェント状態テーブル
    Messages: メッセージログ（100件バッファ）
    Analysis: 現在のレポート表示
    Footer: 統計情報
)
```

#### 7.2 ユーザーインタラクション

1. **ティッカー選択**: 銘柄コード入力
2. **日付選択**: 分析日（YYYY-MM-DD）
3. **アナリスト選択**: チェックボックス
4. **研究深度**: Shallow(1) / Medium(3) / Deep(5)
5. **LLMプロバイダー**: 選択メニュー
6. **モデル選択**: 深い/速い思考モデル

### 8. 依存関係

#### 8.1 主要ライブラリ

**LLMフレームワーク**
- langchain-openai >=0.3.23
- langchain-anthropic >=0.3.15
- langchain-google-genai >=2.1.5
- langgraph >=0.4.8

**金融データ**
- yfinance >=0.2.63
- finnhub-python >=2.4.23
- stockstats >=0.6.5

**UI/CLI**
- typer (CLIフレームワーク)
- rich >=14.0.0 (ターミナルUI)
- questionary >=2.1.0 (対話型プロンプト)

**データ処理**
- pandas >=2.3.0
- chromadb >=1.0.12
- redis >=6.2.0

### 9. 設定システム

#### 9.1 デフォルト設定

```python
DEFAULT_CONFIG = {
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    "online_tools": True,
    "backend_url": "https://api.openai.com/v1"
}
```

#### 9.2 カスタマイズ例

```python
config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "google"
config["deep_think_llm"] = "gemini-2.0-flash"
config["max_debate_rounds"] = 3
config["online_tools"] = False  # オフラインモード
```

### 10. 実行要件

#### 10.1 システム要件

- **Python**: >=3.10
- **メモリ**: 推奨8GB以上
- **ストレージ**: データキャッシュ用1GB以上

#### 10.2 API要件

```bash
export FINNHUB_API_KEY=$YOUR_FINNHUB_API_KEY
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
```

### 11. セキュリティ考慮事項

- APIキーは環境変数で管理
- キャッシュデータはローカル保存
- ChromaDBによる埋め込みベクトルのローカル管理
- SSL/TLS通信の使用

### 12. パフォーマンス最適化

- **並列処理**: 複数アナリストの同時実行
- **キャッシング**: 頻繁にアクセスするデータの保存
- **メモリ管理**: dequeによる効率的なバッファリング
- **UI更新**: 4FPSの最適化されたリフレッシュレート

## まとめ

TradingAgentsは、高度に構造化されたマルチエージェントシステムで、実世界の投資会社の意思決定プロセスを忠実に再現しています。LangGraphによるオーケストレーション、複数のLLMプロバイダー対応、包括的な金融データ統合により、柔軟かつ強力な金融分析プラットフォームを実現しています。