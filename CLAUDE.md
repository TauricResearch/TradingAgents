# CLAUDE.md

このファイルはClaude Code (claude.ai/code) がTradingAgentsリポジトリで作業する際のガイダンスとベストプラクティスを提供します。

## 1. プロジェクトの目的と非目標

### 目的
- **マルチエージェント金融分析**: 実世界の投資会社の組織構造を模倣したLLMベースの取引分析システム
- **包括的市場分析**: テクニカル分析、ファンダメンタルズ分析、センチメント分析、ニュース分析の統合
- **協調的意思決定**: 複数のエージェントによるディベートと段階的な意思決定プロセス
- **学習機能**: 過去の取引から学習し、将来の判断を改善

### 非目標
- **実際の取引実行**: 本システムは分析と推奨のみを提供し、実際の取引は行わない
- **投資助言**: 金融投資アドバイスではなく、研究目的のフレームワーク
- **リアルタイム取引**: 高頻度取引やリアルタイムアービトラージは対象外
- **規制対応**: 金融規制への準拠は使用者の責任

## 2. コーディング規約

### 命名規則
```python
# クラス名: PascalCase
class TradingAgentsGraph:
class FinancialSituationMemory:

# 関数名: snake_case  
def create_market_analyst():
def get_finnhub_news():

# 定数: UPPER_SNAKE_CASE
DEFAULT_CONFIG = {...}
MAX_DEBATE_ROUNDS = 3

# プライベート属性: 先頭にアンダースコア
self._config = config
def _create_tool_nodes():
```

### 型付け
```python
# 必須: 関数シグネチャに型ヒント使用
from typing import Dict, Any, List, Optional, Annotated

def propagate(self, company_name: str, trade_date: str) -> Tuple[Dict, str]:
    pass

# Annotated使用例 (tradingagents/agents/utils/agent_utils.py)
@tool
def get_finnhub_news(
    ticker: Annotated[str, "Search query of a company, e.g. 'AAPL, TSM, etc."],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
) -> str:
```

### 制御フロー
```python
# 条件分岐の明確化 (tradingagents/graph/conditional_logic.py)
def should_continue_debate(self, state: AgentState) -> str:
    if state["investment_debate_state"]["count"] >= 2 * self.max_debate_rounds:
        return "Research Manager"
    if state["investment_debate_state"]["current_response"].startswith("Bull"):
        return "Bear Researcher"
    return "Bull Researcher"
```

### コメント・ドキュメント
```python
# クラス・関数にはdocstring必須
def create_market_analyst(llm, toolkit):
    """
    市場アナリストノードを作成
    
    Args:
        llm: 使用するLLMインスタンス
        toolkit: データアクセス用ツールキット
    
    Returns:
        market_analyst_node: 設定済みのノード関数
    """
```

## 3. LLM/プロンプト設計

### モデル選択戦略
```python
# 深い思考モデル: 複雑な判断・ディベート調整
# Research Manager, Risk Managerで使用
self.deep_thinking_llm = ChatOpenAI(model=config["deep_think_llm"])  # o1-preview, gpt-4o

# 速い思考モデル: 迅速な分析・データ処理
# 各アナリスト、リサーチャーで使用
self.quick_thinking_llm = ChatOpenAI(model=config["quick_think_llm"])  # gpt-4o-mini
```

### プロンプトテンプレート設計
```python
# 構造化プロンプト例 (tradingagents/agents/analysts/market_analyst.py)
system_message = """You are a trading assistant tasked with analyzing financial markets. 
Your role is to select the **most relevant indicators** for a given market condition...

Moving Averages:
- close_50_sma: 50 SMA: A medium-term trend indicator...
- close_200_sma: 200 SMA: A long-term trend benchmark...

[具体的な指標と使用方法を列挙]

Make sure to append a Markdown table at the end of the report..."""

# MessagesPlaceholderで動的コンテンツ挿入
prompt = ChatPromptTemplate.from_messages([
    ("system", system_message),
    MessagesPlaceholder(variable_name="messages"),
])
```

### 出力検証
```python
# 最終判断の明確なマーカー
"FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**"

# ツール呼び出しチェック
if len(result.tool_calls) == 0:
    report = result.content
```

## 4. シークレット/設定管理

### 環境変数管理
```bash
# 必須環境変数 (.env.example作成推奨)
export FINNHUB_API_KEY=$YOUR_FINNHUB_API_KEY
export OPENAI_API_KEY=$YOUR_OPENAI_API_KEY
export GOOGLE_API_KEY=$YOUR_GOOGLE_API_KEY  # Google使用時
export ANTHROPIC_API_KEY=$YOUR_ANTHROPIC_API_KEY  # Anthropic使用時
```

### 設定ファイル構造
```python
# tradingagents/default_config.py
DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(...),  # 動的パス解決
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),  # 環境変数オーバーライド可能
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "max_debate_rounds": 1,
    "online_tools": True,  # オンライン/オフライン切替
}
```

### APIキー漏洩防止
```python
# ログ出力時の秘匿化
def log_api_call(endpoint: str, params: Dict):
    # APIキーを含まないパラメータのみログ出力
    safe_params = {k: v for k, v in params.items() if "key" not in k.lower()}
    logger.info(f"API Call: {endpoint}, params: {safe_params}")
```

## 5. データフローとキャッシュ

### 外部API利用方針
```python
# オンライン/オフライン切替 (tradingagents/agents/analysts/market_analyst.py)
if toolkit.config["online_tools"]:
    tools = [
        toolkit.get_YFin_data_online,
        toolkit.get_stockstats_indicators_report_online,
    ]
else:
    tools = [
        toolkit.get_YFin_data,  # キャッシュデータ使用
        toolkit.get_stockstats_indicators_report,
    ]
```

### レート制限対策
```python
# API呼び出し間隔制御
import time
from functools import wraps

def rate_limit(calls_per_second=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            time.sleep(1 / calls_per_second)
            return func(*args, **kwargs)
        return wrapper
    return decorator
```

### キャッシュ戦略
```python
# データキャッシュディレクトリ構造
# tradingagents/dataflows/data_cache/
#   ├── [ticker]/
#   │   ├── news_data/
#   │   ├── price_data/
#   │   └── fundamentals/

# キャッシュファイル命名
cache_file = f"{ticker}_{date}_{data_type}.json"
```

## 6. エージェント/グラフ設計

### 状態管理パターン
```python
# 階層的状態設計 (tradingagents/agents/utils/agent_states.py)
class AgentState(MessagesState):
    # 基本情報
    company_of_interest: str
    trade_date: str
    
    # 分析レポート
    market_report: str
    sentiment_report: str
    news_report: str
    fundamentals_report: str
    
    # ディベート状態
    investment_debate_state: InvestDebateState
    risk_debate_state: RiskDebateState
    
    # 最終決定
    final_trade_decision: str
```

### メモリシステム
```python
# ChromaDBベクトルデータベース使用 (tradingagents/agents/utils/memory.py)
class FinancialSituationMemory:
    def add_situations(self, situations_and_advice):
        # 埋め込みベクトル生成
        embeddings.append(self.get_embedding(situation))
        # ChromaDBに保存
        self.situation_collection.add(...)
    
    def get_memories(self, current_situation, n_matches=1):
        # 類似検索
        query_embedding = self.get_embedding(current_situation)
        results = self.situation_collection.query(...)
```

### 条件分岐ロジック
```python
# 明示的な条件分岐 (tradingagents/graph/conditional_logic.py)
def should_continue_market(self, state: AgentState):
    messages = state["messages"]
    last_message = messages[-1]
    if last_message.tool_calls:
        return "tools_market"  # ツール実行へ
    return "Msg Clear Market"  # 次のノードへ
```

### デバッグ方針
```python
# デバッグモード実装 (tradingagents/graph/trading_graph.py)
if self.debug:
    trace = []
    for chunk in self.graph.stream(init_agent_state, **args):
        chunk["messages"][-1].pretty_print()  # リアルタイム出力
        trace.append(chunk)
```

## 7. エラーハンドリングとロギング

### 構造化エラーハンドリング
```python
# API呼び出しエラー処理
try:
    result = get_data_in_range(ticker, before, curr_date, "news_data", DATA_DIR)
except Exception as e:
    logger.error(f"Failed to fetch news for {ticker}: {str(e)}")
    return ""  # 空文字列で継続（フェイルセーフ）
```

### ログレベル戦略
```python
import logging

# 環境別ログレベル
log_level = logging.DEBUG if debug else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### 例外分類
```python
class TradingAgentsException(Exception):
    """基底例外クラス"""
    pass

class DataFetchError(TradingAgentsException):
    """データ取得エラー"""
    pass

class LLMInvocationError(TradingAgentsException):
    """LLM呼び出しエラー"""
    pass
```

## 8. パフォーマンス最適化

### 並列化戦略
```python
# 複数アナリストの並列実行 (tradingagents/graph/setup.py)
# LangGraphが自動的に独立したノードを並列実行
workflow.add_edge(START, "Market Analyst")  # これらは
workflow.add_edge(START, "Social Analyst")  # 並列に
workflow.add_edge(START, "News Analyst")    # 実行される
workflow.add_edge(START, "Fundamentals Analyst")
```

### トークン管理
```python
# リフレクション時のトークン制限 (tradingagents/graph/reflection.py)
"Extract key insights from the summary into a concise sentence of no more than 1000 tokens."
```

### コスト最適化
```python
# メッセージ削除でコンテキスト削減 (tradingagents/agents/utils/agent_utils.py)
def create_msg_delete():
    def delete_messages(state):
        messages = state["messages"]
        removal_operations = [RemoveMessage(id=m.id) for m in messages]
        placeholder = HumanMessage(content="Continue")  # 最小限のプレースホルダー
        return {"messages": removal_operations + [placeholder]}
```

## 9. テスト戦略

### テスト構造（推奨）
```
tests/
├── unit/
│   ├── test_agents/
│   ├── test_dataflows/
│   └── test_graph/
├── integration/
│   ├── test_full_pipeline.py
│   └── test_api_integration.py
└── fixtures/
    └── sample_data.json
```

### モックデータ使用
```python
# オフラインモードでテスト
test_config = DEFAULT_CONFIG.copy()
test_config["online_tools"] = False  # キャッシュデータ使用

# モックLLM応答
@patch('langchain_openai.ChatOpenAI.invoke')
def test_market_analyst(mock_invoke):
    mock_invoke.return_value = AIMessage(content="FINAL TRANSACTION PROPOSAL: **HOLD**")
```

## 10. CLI UXガイドライン

### 入力検証
```python
# questionary による対話的入力 (cli/utils.py)
def get_ticker() -> str:
    ticker = questionary.text(
        "Enter the ticker symbol to analyze:",
        validate=lambda x: len(x.strip()) > 0 or "Please enter a valid ticker symbol.",
        style=questionary.Style([("text", "fg:green")])
    ).ask()
```

### リッチ表示
```python
# Rich Layout構造 (cli/main.py)
layout = Layout()
layout.split_column(
    Layout(name="header", size=3),
    Layout(name="body"),
    Layout(name="footer", size=3)
)
```

### フェイルセーフ
```python
# 終了処理
if not ticker:
    console.print("\n[red]No ticker symbol provided. Exiting...[/red]")
    exit(1)
```

## 11. セキュリティ/コンプライアンス

### APIキー保護
```python
# 環境変数から取得、ハードコード禁止
api_key = os.getenv("FINNHUB_API_KEY")
if not api_key:
    raise ValueError("FINNHUB_API_KEY not set")
```

### 依存関係管理
```bash
# 定期的な依存関係更新
pip install --upgrade -r requirements.txt
pip audit  # 脆弱性チェック
```

### データプライバシー
```python
# PII（個人識別情報）の除外
def sanitize_output(text: str) -> str:
    # メールアドレス、電話番号等を除去
    import re
    text = re.sub(r'\S+@\S+', '[EMAIL]', text)
    text = re.sub(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '[PHONE]', text)
    return text
```

## 12. 依存/ビルド/実行方法

### 必須ツール
```bash
# Python 3.10以上必須
python --version  # >= 3.10

# 仮想環境作成
conda create -n tradingagents python=3.13
conda activate tradingagents
```

### インストール手順
```bash
# 依存関係インストール
pip install -r requirements.txt

# 開発用インストール
pip install -e .
```

### 実行コマンド
```bash
# CLI実行
python -m cli.main

# プログラム実行
python main.py

# カスタム設定での実行
FINNHUB_API_KEY=xxx OPENAI_API_KEY=yyy python main.py
```

### よくある落とし穴
```python
# 1. ハードコードされたパス
# NG: "/Users/yluo/Documents/Code/ScAI/FR1-data"
# OK: os.getenv("DATA_DIR", "./data")

# 2. APIキー不足
# 必ずFINNHUB_API_KEYとLLMプロバイダーのAPIキーを設定

# 3. オンライン/オフライン混在
# config["online_tools"]を統一的に設定
```

## 13. コントリビュート規約

### ブランチ戦略
```bash
# 機能開発
git checkout -b feature/agent-improvement

# バグ修正
git checkout -b fix/api-error-handling

# ドキュメント
git checkout -b docs/update-readme
```

### コミットメッセージ
```bash
# 形式: <type>: <description>
feat: Add portfolio optimization agent
fix: Handle FinnHub API timeout
docs: Update installation guide
refactor: Simplify debate logic
test: Add unit tests for market analyst
```

### PR要件
- [ ] コードがPEP 8準拠
- [ ] 型ヒント追加
- [ ] docstring記載
- [ ] テスト追加/更新
- [ ] CLAUDE.md更新（必要に応じて）

## 14. 変更の安全運用

### 実験フラグ
```python
# 新機能の段階的ロールアウト
DEFAULT_CONFIG = {
    "experimental_features": {
        "advanced_memory": False,  # デフォルトOFF
        "parallel_analysis": True,  # 段階的有効化
    }
}

if config.get("experimental_features", {}).get("advanced_memory"):
    # 新機能のコード
```

### ロールバック戦略
```python
# 設定による動作切替
if config.get("fallback_mode"):
    # 安定版の処理
    return legacy_analysis()
else:
    # 新バージョンの処理
    return advanced_analysis()
```

### 監視ポイント
```python
# 重要メトリクスのログ出力
logger.info(f"Analysis completed: ticker={ticker}, duration={duration}s, tokens={token_count}")
logger.info(f"Debate rounds: {state['investment_debate_state']['count']}")
logger.info(f"Final decision: {state['final_trade_decision']}")
```

## 15. LangGraphベストプラクティス (2024-2025)

### コアフレームワーク原則

LangGraphは制御可能なエージェントを構築するために設計されており、複雑なタスクを確実に処理し、エージェントが軌道から外れることを防ぐモデレーションと品質ループを簡単に追加できます。

#### グラフベース設計
```python
# すべての相互作用を循環グラフとしてモデル化
from langgraph.graph import StateGraph, START, END

workflow = StateGraph(AgentState)
# 複数のループとif文を持つ高度なワークフロー実装
```

#### 低レベルの柔軟性
```python
# 完全にカスタマイズ可能なエージェント作成
# 単一、マルチエージェント、階層的な制御フロー
# すべて一つのフレームワークで実現
```

### 状態管理パターン

#### 共有状態vs プライベート状態
```python
# 共有状態パターン
class SharedAgentState(TypedDict):
    messages: List[BaseMessage]
    shared_context: str
    
# プライベート状態パターン（サブグラフ用）
class SearchAgentState(TypedDict):
    queries: List[str]
    documents: List[Document]
    # 親グラフとは独立した状態スキーマ
```

#### 階層的メモリ管理
```python
# 三層構造のメモリシステム
class MemoryHierarchy:
    short_term: ConversationalMemory  # 短期会話メモリ
    long_term: HistoricalStorage      # 長期履歴ストレージ
    external: RAGDataSource           # 外部データソース（RAG）
```

### チェックポイントと永続化

#### チェックポインター実装
```python
from langgraph.checkpoint import MemorySaver, PostgresSaver

# インメモリチェックポインター（開発用）
checkpointer = MemorySaver()

# PostgreSQLチェックポインター（本番用）
checkpointer = PostgresSaver(connection_string="postgresql://...")

# グラフコンパイル時に指定
graph = workflow.compile(checkpointer=checkpointer)
```

#### スレッド管理
```python
# スレッドIDを使用した状態の永続化
config = {"configurable": {"thread_id": "user_123_session_456"}}
result = graph.invoke(input_data, config=config)

# 後から同じスレッドを再開
resumed_result = graph.invoke(new_input, config=config)
```

### Human-in-the-Loop パターン (2024最新)

#### interrupt関数の使用
```python
from langgraph.prebuilt import interrupt

def review_decision_node(state):
    decision = analyze_data(state)
    
    # 人間のレビューが必要な場合は中断
    if decision.requires_human_review:
        human_input = interrupt(
            "Please review this decision: " + decision.summary
        )
        decision = update_decision(decision, human_input)
    
    return {"decision": decision}
```

#### レビューと承認パターン
```python
# ツール呼び出しのレビュー
def review_tool_calls(state):
    tool_calls = state["pending_tool_calls"]
    
    # 危険な操作は人間の承認を要求
    if any(is_dangerous(call) for call in tool_calls):
        approval = interrupt(f"Approve these operations? {tool_calls}")
        if not approval:
            return {"tool_calls": [], "status": "rejected"}
    
    return {"tool_calls": tool_calls, "status": "approved"}
```

#### 状態編集パターン
```python
# グラフ状態の人間による編集
def allow_state_editing(state):
    # 現在の状態を表示
    display_state = format_for_human(state)
    
    # 人間による編集を許可
    edited_state = interrupt(
        f"Current state: {display_state}\nEdit if needed:"
    )
    
    # 編集された状態で続行
    return merge_states(state, edited_state)
```

### マルチエージェントオーケストレーション

#### スーパーバイザーアーキテクチャ
```python
# ハンドオフツールを使用したスーパーバイザー実装
def create_supervisor_graph():
    workflow = StateGraph(SupervisorState)
    
    # スーパーバイザーノード
    workflow.add_node("supervisor", supervisor_agent)
    
    # ワーカーエージェント
    workflow.add_node("analyst", analyst_agent)
    workflow.add_node("researcher", researcher_agent)
    
    # 動的ルーティング
    workflow.add_conditional_edges(
        "supervisor",
        route_to_worker,
        ["analyst", "researcher", END]
    )
    
    return workflow.compile()
```

#### コラボレーションパターン
```python
# 共有スクラッチパッドでの協調
class CollaborativeState(TypedDict):
    shared_messages: List[Message]  # 全エージェントが見える
    individual_contexts: Dict[str, Any]  # エージェント固有
```

#### 階層的チーム構造
```python
# サブグラフとしてのチーム実装
def create_hierarchical_teams():
    # 各チームは独立したLangGraphオブジェクト
    research_team = create_research_team_graph()
    analysis_team = create_analysis_team_graph()
    
    # メインワークフロー
    main_workflow = StateGraph(MainState)
    main_workflow.add_node("research", research_team)
    main_workflow.add_node("analysis", analysis_team)
    
    return main_workflow.compile()
```

### パフォーマンス最適化

#### ストリーミングサポート
```python
# トークンごとのストリーミング
async for chunk in graph.astream(input_data, config):
    if chunk.get("messages"):
        print(chunk["messages"][-1].content)
    
    # 中間ステップのストリーミング
    if chunk.get("intermediate_steps"):
        display_reasoning(chunk["intermediate_steps"])
```

#### インテリジェントキャッシング
```python
# LangGraph Platformの自動キャッシング
config = {
    "caching": {
        "enable": True,
        "ttl": 3600,  # 1時間
        "max_size": "1GB"
    }
}
```

#### 並列実行
```python
# 独立したノードの自動並列化
workflow.add_edge(START, ["agent1", "agent2", "agent3"])
# LangGraphが自動的に並列実行
```

### エラーハンドリングと再試行

#### 自動再試行
```python
from langgraph.prebuilt import RetryPolicy

retry_policy = RetryPolicy(
    max_attempts=3,
    backoff_factor=2,
    exceptions=(APIError, TimeoutError)
)

graph = workflow.compile(retry_policy=retry_policy)
```

#### フォールトトレランス
```python
# チェックポイントによる障害復旧
try:
    result = graph.invoke(input_data, config)
except Exception as e:
    # チェックポイントから自動復旧
    last_checkpoint = checkpointer.get_latest(thread_id)
    result = graph.invoke(None, config, from_checkpoint=last_checkpoint)
```

### 本番環境デプロイメント

#### LangGraph Platform設定
```python
# 水平スケーリング設定
deployment_config = {
    "scaling": {
        "min_replicas": 2,
        "max_replicas": 10,
        "target_cpu_utilization": 70
    },
    "task_queue": {
        "max_concurrent": 100,
        "timeout": 300
    }
}
```

#### 監視とロギング
```python
# 構造化ログの実装
import structlog

logger = structlog.get_logger()

def monitored_node(state):
    logger.info("node_execution_start", 
                node_name="analyst",
                thread_id=state.get("thread_id"))
    
    result = process(state)
    
    logger.info("node_execution_complete",
                node_name="analyst",
                duration=elapsed_time,
                token_count=count_tokens(result))
    
    return result
```

### 2025年の推奨事項

#### 長コンテキストRAG
```python
# 25,000トークン以上の処理
config = {
    "context_window": 32000,
    "chunking_strategy": "semantic",
    "overlap": 200
}
```

#### Agentic RAGパターン
```python
# モジュラーでインテリジェントなエージェントワークフロー
class AgenticRAG:
    def __init__(self):
        self.retrieval_agent = RetrievalAgent()
        self.reasoning_agent = ReasoningAgent()
        self.generation_agent = GenerationAgent()
    
    def process(self, query):
        # 各エージェントが専門的な役割を担当
        docs = self.retrieval_agent.retrieve(query)
        reasoning = self.reasoning_agent.analyze(docs)
        response = self.generation_agent.generate(reasoning)
        return response
```

## クイックリファレンス

### 主要ファイル
- `tradingagents/graph/trading_graph.py` - メインオーケストレーター
- `tradingagents/agents/` - 各エージェント実装
- `tradingagents/dataflows/interface.py` - データAPI統合
- `cli/main.py` - CLIエントリーポイント

### 重要な設定
```python
config["max_debate_rounds"] = 3  # ディベート回数
config["online_tools"] = True    # リアルタイムデータ使用
config["llm_provider"] = "openai"  # LLMプロバイダー
```

### デバッグTips
```python
# デバッグモード有効化
ta = TradingAgentsGraph(debug=True, config=config)

# 状態ログ確認
self._log_state(trade_date, final_state)  # logs/に保存
```