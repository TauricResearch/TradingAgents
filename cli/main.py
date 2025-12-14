# 匯入必要的模組
from typing import Optional
import datetime
import typer
from pathlib import Path
from functools import wraps
from rich.console import Console
from dotenv import load_dotenv

# 從 .env 檔案載入環境變數（強制覆蓋系統環境變數）
load_dotenv(override=True)
from rich.panel import Panel
from rich.spinner import Spinner
from rich.live import Live
from rich.columns import Columns
from rich.markdown import Markdown
from rich.layout import Layout
from rich.text import Text
from rich.table import Table
from collections import deque
import time
from rich.tree import Tree
from rich import box
from rich.align import Align
from rich.rule import Rule

# 匯入專案內的模組
from tradingagents.graph.trading_graph import TradingAgentsXGraph
from tradingagents.default_config import DEFAULT_CONFIG
from cli.models import AnalystType
from cli.utils import *
from cli.utils import select_market

# 初始化 rich Console
console = Console()

# 建立 Typer 應用程式
app = typer.Typer(
    name="TradingAgentsX",
    help="TradingAgentsX CLI：多代理 LLM 金融交易框架",
    add_completion=True,  # 啟用 shell 自動補全
)


# 建立一個 deque 來儲存最近的訊息，並設定最大長度
class MessageBuffer:
    """
    用於儲存和管理應用程式訊息、工具呼叫和報告狀態的緩衝區。
    """
    def __init__(self, max_length=100):
        # 使用 deque 儲存帶有時間戳的訊息，以實現高效的 append 和 pop 操作
        self.messages = deque(maxlen=max_length)
        self.tool_calls = deque(maxlen=max_length)
        self.current_report = None  # 當前顯示的報告部分
        self.final_report = None  # 儲存完整的最終報告
        # 代理狀態字典，追蹤每個代理的進度
        self.agent_status = {
            # 分析師團隊
            "Market Analyst": "pending",
            "Social Analyst": "pending",
            "News Analyst": "pending",
            "Fundamentals Analyst": "pending",
            # 研究團隊
            "Bull Researcher": "pending",
            "Bear Researcher": "pending",
            "Research Manager": "pending",
            # 交易團隊
            "Trader": "pending",
            # 風險管理團隊
            "Risky Analyst": "pending",
            "Neutral Analyst": "pending",
            "Safe Analyst": "pending",
            # 投資組合管理團隊
            "Portfolio Manager": "pending",
        }
        self.current_agent = None  # 當前正在執行的代理
        # 報告區塊字典，儲存分析過程中的各個報告
        self.report_sections = {
            "market_report": None,
            "sentiment_report": None,
            "news_report": None,
            "fundamentals_report": None,
            "investment_plan": None,
            "trader_investment_plan": None,
            "final_trade_decision": None,
        }

    def add_message(self, message_type, content):
        """新增一條訊息到緩衝區。"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))

    def add_tool_call(self, tool_name, args):
        """新增一條工具呼叫記錄到緩衝區。"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))

    def update_agent_status(self, agent, status):
        """更新代理的狀態。"""
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name, content):
        """更新報告的特定區塊。"""
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()

    def _update_current_report(self):
        """更新當前用於顯示的報告。"""
        # 為了面板顯示，只顯示最近更新的部分
        latest_section = None
        latest_content = None

        # 找到最近更新的部分
        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content
               
        if latest_section and latest_content:
            # 格式化當前部分以供顯示
            section_titles = {
                "market_report": "市場分析",
                "sentiment_report": "社群情緒",
                "news_report": "新聞分析",
                "fundamentals_report": "基本面分析",
                "investment_plan": "研究團隊決策",
                "trader_investment_plan": "交易團隊計畫",
                "final_trade_decision": "投資組合管理決策",
            }
            self.current_report = (
                f"### {section_titles[latest_section]}\n{latest_content}"
            )

        # 更新完整的最終報告
        self._update_final_report()

    def _update_final_report(self):
        """更新完整的最終報告。"""
        report_parts = []

        # 分析師團隊報告
        if any(
            self.report_sections[section]
            for section in [
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
            ]
        ):
            report_parts.append("## 分析師團隊報告")
            if self.report_sections["market_report"]:
                report_parts.append(
                    f"### 市場分析\n{self.report_sections['market_report']}"
                )
            if self.report_sections["sentiment_report"]:
                report_parts.append(
                    f"### 社群情緒\n{self.report_sections['sentiment_report']}"
                )
            if self.report_sections["news_report"]:
                report_parts.append(
                    f"### 新聞分析\n{self.report_sections['news_report']}"
                )
            if self.report_sections["fundamentals_report"]:
                report_parts.append(
                    f"### 基本面分析\n{self.report_sections['fundamentals_report']}"
                )

        # 研究團隊報告
        if self.report_sections["investment_plan"]:
            report_parts.append("## 研究團隊決策")
            report_parts.append(f"{self.report_sections['investment_plan']}")

        # 交易團隊報告
        if self.report_sections["trader_investment_plan"]:
            report_parts.append("## 交易團隊計畫")
            report_parts.append(f"{self.report_sections['trader_investment_plan']}")

        # 投資組合管理決策
        if self.report_sections["final_trade_decision"]:
            report_parts.append("## 投資組合管理決策")
            report_parts.append(f"{self.report_sections['final_trade_decision']}")

        self.final_report = "\n\n".join(report_parts) if report_parts else None


# 實例化訊息緩衝區
message_buffer = MessageBuffer()


def create_layout():
    """建立 CLI 的版面配置。"""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )
    layout["main"].split_column(
        Layout(name="upper", ratio=3), Layout(name="analysis", ratio=5)
    )
    layout["upper"].split_row(
        Layout(name="progress", ratio=2), Layout(name="messages", ratio=3)
    )
    return layout


def update_display(layout, spinner_text=None):
    """更新 rich 即時顯示的內容。"""
    # 包含歡迎訊息的頁首
    layout["header"].update(
        Panel(
            "[bold green]歡迎使用 TradingAgentsX CLI[/bold green]\n"
            "[dim]© [Tauric Research](https://github.com/TauricResearch)[/dim]",
            title="歡迎使用 TradingAgentsX",
            border_style="green",
            padding=(1, 2),
            expand=True,
        )
    )

    # 顯示代理狀態的進度面板
    progress_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        box=box.SIMPLE_HEAD,  # 使用帶有水平線的簡單頁首
        title=None,  # 移除多餘的進度標題
        padding=(0, 2),  # 新增水平內邊距
        expand=True,  # 使表格擴展以填滿可用空間
    )
    progress_table.add_column("團隊", style="cyan", justify="center", width=20)
    progress_table.add_column("代理", style="green", justify="center", width=20)
    progress_table.add_column("狀態", style="yellow", justify="center", width=20)

    # 按團隊對代理進行分組
    teams = {
        "分析師團隊": [
            "Market Analyst",
            "Social Analyst",
            "News Analyst",
            "Fundamentals Analyst",
        ],
        "研究團隊": ["Bull Researcher", "Bear Researcher", "Research Manager"],
        "交易團隊": ["Trader"],
        "風險管理": ["Risky Analyst", "Neutral Analyst", "Safe Analyst"],
        "投資組合管理": ["Portfolio Manager"],
    }

    for team, agents in teams.items():
        # 新增帶有團隊名稱的第一個代理
        first_agent = agents[0]
        status = message_buffer.agent_status[first_agent]
        if status == "in_progress":
            spinner = Spinner(
                "dots", text="[blue]進行中[/blue]", style="bold cyan"
            )
            status_cell = spinner
        else:
            status_color = {
                "pending": "yellow",
                "completed": "green",
                "error": "red",
            }.get(status, "white")
            status_cell = f"[{status_color}]{status}[/{status_color}]"
        progress_table.add_row(team, first_agent, status_cell)

        # 新增團隊中的其餘代理
        for agent in agents[1:]:
            status = message_buffer.agent_status[agent]
            if status == "in_progress":
                spinner = Spinner(
                    "dots", text="[blue]進行中[/blue]", style="bold cyan"
                )
                status_cell = spinner
            else:
                status_color = {
                    "pending": "yellow",
                    "completed": "green",
                    "error": "red",
                }.get(status, "white")
                status_cell = f"[{status_color}]{status}[/{status_color}]"
            progress_table.add_row("", agent, status_cell)

        # 在每個團隊後新增水平線
        progress_table.add_row("─" * 20, "─" * 20, "─" * 20, style="dim")

    layout["progress"].update(
        Panel(progress_table, title="進度", border_style="cyan", padding=(1, 2))
    )

    # 顯示最近訊息和工具呼叫的訊息面板
    messages_table = Table(
        show_header=True,
        header_style="bold magenta",
        show_footer=False,
        expand=True,  # 使表格擴展以填滿可用空間
        box=box.MINIMAL,  # 使用最小化的框線樣式以獲得更輕量的外觀
        show_lines=True,  # 保留水平線
        padding=(0, 1),  # 在列之間新增一些內邊距
    )
    messages_table.add_column("時間", style="cyan", width=8, justify="center")
    messages_table.add_column("類型", style="green", width=10, justify="center")
    messages_table.add_column(
        "內容", style="white", no_wrap=False, ratio=1
    )  # 使內容列擴展

    # 合併工具呼叫和訊息
    all_messages = []

    # 新增工具呼叫
    for timestamp, tool_name, args in message_buffer.tool_calls:
        # 如果工具呼叫參數過長，則截斷
        if isinstance(args, str) and len(args) > 100:
            args = args[:97] + "..."
        all_messages.append((timestamp, "工具", f"{tool_name}: {args}"))

    # 新增常規訊息
    for timestamp, msg_type, content in message_buffer.messages:
        # 如果內容不是字串，則轉換為字串
        content_str = content
        if isinstance(content, list):
            # 處理內容區塊列表（Anthropic 格式）
            text_parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get('type') == 'text':
                        text_parts.append(item.get('text', ''))
                    elif item.get('type') == 'tool_use':
                        text_parts.append(f"[工具: {item.get('name', 'unknown')}]")
                else:
                    text_parts.append(str(item))
            content_str = ' '.join(text_parts)
        elif not isinstance(content_str, str):
            content_str = str(content)
            
        # 如果訊息內容過長，則截斷
        if len(content_str) > 200:
            content_str = content_str[:197] + "..."
        all_messages.append((timestamp, msg_type, content_str))

    # 按時間戳排序
    all_messages.sort(key=lambda x: x[0])

    # 根據可用空間計算可以顯示多少條訊息
    # 從一個合理的數字開始，並根據內容長度進行調整
    max_messages = 12  # 從 8 增加到 12 以更好地填滿空間

    # 獲取將適合面板的最後 N 條訊息
    recent_messages = all_messages[-max_messages:]

    # 將訊息新增到表格中
    for timestamp, msg_type, content in recent_messages:
        # 格式化內容並自動換行
        wrapped_content = Text(content, overflow="fold")
        messages_table.add_row(timestamp, msg_type, wrapped_content)

    if spinner_text:
        messages_table.add_row("", "Spinner", spinner_text)

    # 如果訊息被截斷，則新增頁尾以指示
    if len(all_messages) > max_messages:
        messages_table.footer = (
            f"[dim]顯示最近 {max_messages} 條訊息，共 {len(all_messages)} 條[/dim]"
        )

    layout["messages"].update(
        Panel(
            messages_table,
            title="訊息與工具",
            border_style="blue",
            padding=(1, 2),
        )
    )

    # 顯示當前報告的分析面板
    if message_buffer.current_report:
        layout["analysis"].update(
            Panel(
                Markdown(message_buffer.current_report),
                title="當前報告",
                border_style="green",
                padding=(1, 2),
            )
        )
    else:
        layout["analysis"].update(
            Panel(
                "[italic]等待分析報告...[/italic]",
                title="當前報告",
                border_style="green",
                padding=(1, 2),
            )
        )

    # 包含統計資訊的頁尾
    tool_calls_count = len(message_buffer.tool_calls)
    llm_calls_count = sum(
        1 for _, msg_type, _ in message_buffer.messages if msg_type == "Reasoning"
    )
    reports_count = sum(
        1 for content in message_buffer.report_sections.values() if content is not None
    )

    stats_table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    stats_table.add_column("統計", justify="center")
    stats_table.add_row(
        f"工具呼叫: {tool_calls_count} | LLM 呼叫: {llm_calls_count} | 已生成報告: {reports_count}"
    )

    layout["footer"].update(Panel(stats_table, border_style="grey50"))


def get_user_selections():
    """在開始分析顯示之前獲取所有使用者選擇。"""
    # 顯示 ASCII 藝術歡迎訊息
    with open("./cli/static/welcome.txt", "r") as f:
        welcome_ascii = f.read()

    # 建立歡迎框內容
    welcome_content = f"{welcome_ascii}\n"
    welcome_content += "[bold green]TradingAgentsX：多代理 LLM 金融交易框架 - CLI[/bold green]\n\n"
    welcome_content += "[bold]工作流程步驟：[/bold]\n"
    welcome_content += "I. 分析師團隊 → II. 研究團隊 → III. 交易員 → IV. 風險管理 → V. 投資組合管理\n\n"
    welcome_content += (
        "[dim]由 [Tauric Research](https://github.com/TauricResearch) 開發[/dim]"
    )

    # 建立並置中歡迎框
    welcome_box = Panel(
        welcome_content,
        border_style="green",
        padding=(1, 2),
        title="歡迎使用 TradingAgentsX",
        subtitle="多代理 LLM 金融交易框架",
    )
    console.print(Align.center(welcome_box))
    console.print()  # 在歡迎框後新增一個空行

    # 為每個步驟建立一個帶框的問卷
    def create_question_box(title, prompt, default=None):
        box_content = f"[bold]{title}[/bold]\n"
        box_content += f"[dim]{prompt}[/dim]"
        if default:
            box_content += f"\n[dim]預設值: {default}[/dim]"
        return Panel(box_content, border_style="blue", padding=(1, 2))

    # 步驟 1：選擇市場
    console.print(
        create_question_box(
            "步驟 1：選擇市場", "選擇要分析的股票市場"
        )
    )
    selected_market, default_ticker = select_market()

    # 步驟 2：股票代碼
    console.print(
        create_question_box(
            "步驟 2：股票代碼", "輸入要分析的股票代碼", default_ticker
        )
    )
    selected_ticker = get_ticker(default_ticker)

    # 步驟 3：分析日期
    default_date = datetime.datetime.now().strftime("%Y-%m-%d")
    console.print(
        create_question_box(
            "步驟 3：分析日期",
            "輸入分析日期 (YYYY-MM-DD)",
            default_date,
        )
    )
    analysis_date = get_analysis_date()

    # 步驟 4：選擇分析師
    console.print(
        create_question_box(
            "步驟 4：分析師團隊", "為分析選擇您的 LLM 分析師代理"
        )
    )
    selected_analysts = select_analysts()
    console.print(
        f"[green]已選分析師：[/green] {', '.join(analyst.value for analyst in selected_analysts)}"
    )

    # 步驟 5：研究深度
    console.print(
        create_question_box(
            "步驟 5：研究深度", "選擇您的研究深度等級"
        )
    )
    selected_research_depth = select_research_depth()

    # 步驟 6：LLM 供應商
    console.print(
        create_question_box(
            "步驟 6：LLM 供應商", "選擇要對話的服務"
        )
    )
    selected_llm_provider, backend_url = select_llm_provider()
    
    # 步驟 7：思維代理
    console.print(
        create_question_box(
            "步驟 7：思維代理", "為分析選擇您的思維代理"
        )
    )
    selected_shallow_thinker = select_shallow_thinking_agent(selected_llm_provider)
    selected_deep_thinker = select_deep_thinking_agent(selected_llm_provider)

    # 步驟 8：嵌入模型供應商
    console.print(
        create_question_box(
            "步驟 8：嵌入模型供應商", "選擇嵌入模型服務（用於記憶體系統）"
        )
    )
    embedding_provider, embedding_url = select_embedding_provider()
    
    # 步驟 9：API Keys
    console.print(
        create_question_box(
            "步驟 9：API Keys", "輸入 API Keys（可留空使用 .env 中的設定）"
        )
    )
    
    import os
    
    # 定義供應商對應的環境變數名稱
    PROVIDER_API_KEY_MAP = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GEMINI_API_KEY",
        "grok": "XAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "自訂供應商": "OPENAI_API_KEY",  # 自訂供應商預設使用 OpenAI 格式
    }
    
    # 根據選擇的供應商獲取對應的 API Key 環境變數名稱
    def get_provider_api_key(provider_name: str) -> str:
        """根據供應商名稱從 .env 讀取對應的 API Key"""
        provider_lower = provider_name.lower()
        env_var_name = PROVIDER_API_KEY_MAP.get(provider_lower, "OPENAI_API_KEY")
        return os.getenv(env_var_name)
    
    # 從選擇的快速思維模型名稱推斷供應商
    def infer_provider_from_model(model_name: str) -> str:
        """根據模型名稱推斷供應商"""
        model_lower = model_name.lower()
        if "gpt" in model_lower or model_lower.startswith("o4"):
            return "openai"
        elif "claude" in model_lower:
            return "anthropic"
        elif "gemini" in model_lower:
            return "google"
        elif "grok" in model_lower:
            return "grok"
        elif "deepseek" in model_lower:
            return "deepseek"
        elif "qwen" in model_lower:
            return "qwen"
        return "openai"  # 預設
    
    # 根據模型推斷供應商並獲取對應的 API Key
    quick_think_provider = infer_provider_from_model(selected_shallow_thinker)
    deep_think_provider = infer_provider_from_model(selected_deep_thinker)
    
    default_quick_think_key = get_provider_api_key(quick_think_provider)
    default_deep_think_key = get_provider_api_key(deep_think_provider)
    default_embedding_key = get_provider_api_key(embedding_provider)
    
    # 快速思維模型 API Key
    quick_think_api_key = get_api_key("快速思維模型", default_quick_think_key)
    
    # 深度思維模型 API Key
    deep_think_api_key = get_api_key("深度思維模型", default_deep_think_key)
    
    # 嵌入模型 API Key
    embedding_api_key = get_api_key("嵌入模型", default_embedding_key)
    
    # Alpha Vantage API Key（必填）
    alpha_vantage_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not alpha_vantage_key:
        console.print("\n[yellow]未在 .env 中找到 ALPHA_VANTAGE_API_KEY[/yellow]")
        alpha_vantage_key = get_api_key("Alpha Vantage", None)
    else:
        console.print(f"\n[green]✓ 使用 .env 中的 ALPHA_VANTAGE_API_KEY[/green]") 

    return {
        "ticker": selected_ticker,
        "analysis_date": analysis_date,
        "analysts": selected_analysts,
        "research_depth": selected_research_depth,
        "llm_provider": selected_llm_provider.lower(),
        "backend_url": backend_url,
        "shallow_thinker": selected_shallow_thinker,
        "deep_thinker": selected_deep_thinker,
        "market_type": selected_market,
        "embedding_provider": embedding_provider,
        "embedding_url": embedding_url,
        "quick_think_api_key": quick_think_api_key,
        "deep_think_api_key": deep_think_api_key,
        "embedding_api_key": embedding_api_key,
        "alpha_vantage_api_key": alpha_vantage_key,
    }


def get_ticker(default: str = "SPY"):
    """從使用者輸入中獲取股票代碼。
    
    參數:
        default (str): 預設的股票代碼（美股預設 SPY，台股預設 2330）
    """
    ticker = typer.prompt("", default=default)
    # 防呆：將股票代碼轉換為大寫
    ticker = ticker.strip().upper()
    return ticker


def get_analysis_date():
    """從使用者輸入中獲取分析日期。"""
    while True:
        date_str = typer.prompt(
            "", default=datetime.datetime.now().strftime("%Y-%m-%d")
        )
        try:
            # 驗證日期格式並確保不是未來日期
            analysis_date = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            if analysis_date.date() > datetime.datetime.now().date():
                console.print("[red]錯誤：分析日期不能是未來日期[/red]")
                continue
            return date_str
        except ValueError:
            console.print(
                "[red]錯誤：日期格式無效。請使用 YYYY-MM-DD[/red]"
            )


def display_complete_report(final_state):
    """顯示包含基於團隊的面板的完整分析報告。"""
    console.print("\n[bold green]完整分析報告[/bold green]\n")

    # I. 分析師團隊報告
    analyst_reports = []

    # 市場分析師報告
    if final_state.get("market_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["market_report"]),
                title="市場分析師",
                border_style="blue",
                padding=(1, 2),
            )
        )

    # 社群分析師報告
    if final_state.get("sentiment_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["sentiment_report"]),
                title="社群分析師",
                border_style="blue",
                padding=(1, 2),
            )
        )

    # 新聞分析師報告
    if final_state.get("news_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["news_report"]),
                title="新聞分析師",
                border_style="blue",
                padding=(1, 2),
            )
        )

    # 基本面分析師報告
    if final_state.get("fundamentals_report"):
        analyst_reports.append(
            Panel(
                Markdown(final_state["fundamentals_report"]),
                title="基本面分析師",
                border_style="blue",
                padding=(1, 2),
            )
        )

    if analyst_reports:
        console.print(
            Panel(
                Columns(analyst_reports, equal=True, expand=True),
                title="I. 分析師團隊報告",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    # II. 研究團隊報告
    if final_state.get("investment_debate_state"):
        research_reports = []
        debate_state = final_state["investment_debate_state"]

        # 看漲研究員分析
        if debate_state.get("bull_history"):
            research_reports.append(
                Panel(
                    Markdown(debate_state["bull_history"]),
                    title="看漲研究員",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # 看跌研究員分析
        if debate_state.get("bear_history"):
            research_reports.append(
                Panel(
                    Markdown(debate_state["bear_history"]),
                    title="看跌研究員",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # 研究經理決策
        if debate_state.get("judge_decision"):
            research_reports.append(
                Panel(
                    Markdown(debate_state["judge_decision"]),
                    title="研究經理",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        if research_reports:
            console.print(
                Panel(
                    Columns(research_reports, equal=True, expand=True),
                    title="II. 研究團隊決策",
                    border_style="magenta",
                    padding=(1, 2),
                )
            )

    # III. 交易團隊報告
    if final_state.get("trader_investment_plan"):
        console.print(
            Panel(
                Panel(
                    Markdown(final_state["trader_investment_plan"]),
                    title="交易員",
                    border_style="blue",
                    padding=(1, 2),
                ),
                title="III. 交易團隊計畫",
                border_style="yellow",
                padding=(1, 2),
            )
        )

    # IV. 風險管理團隊報告
    if final_state.get("risk_debate_state"):
        risk_reports = []
        risk_state = final_state["risk_debate_state"]

        # 激進（風險）分析師分析
        if risk_state.get("risky_history"):
            risk_reports.append(
                Panel(
                    Markdown(risk_state["risky_history"]),
                    title="激進分析師",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # 保守（安全）分析師分析
        if risk_state.get("safe_history"):
            risk_reports.append(
                Panel(
                    Markdown(risk_state["safe_history"]),
                    title="保守分析師",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        # 中立分析師分析
        if risk_state.get("neutral_history"):
            risk_reports.append(
                Panel(
                    Markdown(risk_state["neutral_history"]),
                    title="中立分析師",
                    border_style="blue",
                    padding=(1, 2),
                )
            )

        if risk_reports:
            console.print(
                Panel(
                    Columns(risk_reports, equal=True, expand=True),
                    title="IV. 風險管理團隊決策",
                    border_style="red",
                    padding=(1, 2),
                )
            )

        # V. 投資組合經理決策
        if risk_state.get("judge_decision"):
            console.print(
                Panel(
                    Panel(
                        Markdown(risk_state["judge_decision"]),
                        title="投資組合經理",
                        border_style="blue",
                        padding=(1, 2),
                    ),
                    title="V. 投資組合經理決策",
                    border_style="green",
                    padding=(1, 2),
                )
            )


def update_research_team_status(status):
    """更新所有研究團隊成員和交易員的狀態。"""
    research_team = ["Bull Researcher", "Bear Researcher", "Research Manager", "Trader"]
    for agent in research_team:
        message_buffer.update_agent_status(agent, status)

def extract_content_string(content):
    """從各種訊息格式中提取字串內容。"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # 處理 Anthropic 的列表格式
        text_parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    text_parts.append(item.get('text', ''))
                elif item.get('type') == 'tool_use':
                    text_parts.append(f"[工具: {item.get('name', 'unknown')}]")
            else:
                text_parts.append(str(item))
        return ' '.join(text_parts)
    else:
        return str(content)

def run_analysis():
    """執行完整的分析流程。"""
    # 首先獲取所有使用者選擇
    selections = get_user_selections()

    # 使用選擇的研究深度建立設定
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    
    # 添加 API Keys 到配置
    config["quick_think_api_key"] = selections["quick_think_api_key"]
    config["deep_think_api_key"] = selections["deep_think_api_key"]
    config["embedding_api_key"] = selections["embedding_api_key"]
    config["embedding_base_url"] = selections["embedding_url"]
    
    # 根據市場類型設定資料供應商
    market_type = selections.get("market_type", "us")
    if market_type == "tw":
        # 台股使用 FinMind API
        console.print("[cyan]📊 使用 FinMind API 獲取台股資料[/cyan]")
        config["data_vendors"] = {
            "core_stock_apis": "finmind",       # 使用 FinMind 獲取股價
            "technical_indicators": "finmind",  # 使用 FinMind 獲取技術指標
            "fundamental_data": "finmind",      # 使用 FinMind 獲取基本面資料
            "news_data": "finmind",             # 使用 FinMind 獲取新聞
        }
    else:
        # 美股使用 yfinance 和 Alpha Vantage
        console.print("[cyan]📊 使用 yfinance / Alpha Vantage 獲取美股資料[/cyan]")
        config["data_vendors"] = {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "alpha_vantage",
            "news_data": "openai",
        }
    
    # 設置環境變數（某些工具可能需要）
    import os
    os.environ["OPENAI_API_KEY"] = selections["quick_think_api_key"]
    os.environ["ALPHA_VANTAGE_API_KEY"] = selections["alpha_vantage_api_key"]
    
    # 如果是台股，還需要設置 FinMind API Key
    if market_type == "tw":
        finmind_key = os.getenv("FINMIND_API_KEY", "")
        if finmind_key:
            os.environ["FINMIND_API_KEY"] = finmind_key
            console.print("[green]✓ 已載入 FinMind API Key[/green]")
        else:
            console.print("[yellow]⚠ 未找到 FINMIND_API_KEY，部分功能可能受限[/yellow]")

    # 初始化圖
    graph = TradingAgentsXGraph(
        [analyst.value for analyst in selections["analysts"]], config=config, debug=True
    )

    # 建立結果目錄
    results_dir = Path(config["results_dir"]) / selections["ticker"] / selections["analysis_date"]
    results_dir.mkdir(parents=True, exist_ok=True)
    report_dir = results_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "message_tool.log"
    log_file.touch(exist_ok=True)

    # 裝飾器，用於儲存訊息
    def save_message_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, message_type, content = obj.messages[-1]
            content = content.replace("\n", " ")  # 將換行符替換為空格
            with open(log_file, "a") as f:
                f.write(f"{timestamp} [{message_type}] {content}\n")
        return wrapper
    
    # 裝飾器，用於儲存工具呼叫
    def save_tool_call_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(*args, **kwargs):
            func(*args, **kwargs)
            timestamp, tool_name, args = obj.tool_calls[-1]
            args_str = ", ".join(f"{k}={v}" for k, v in args.items())
            with open(log_file, "a") as f:
                f.write(f"{timestamp} [工具呼叫] {tool_name}({args_str})\n")
        return wrapper

    # 裝飾器，用於儲存報告區塊
    def save_report_section_decorator(obj, func_name):
        func = getattr(obj, func_name)
        @wraps(func)
        def wrapper(section_name, content):
            func(section_name, content)
            if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                content = obj.report_sections[section_name]
                if content:
                    file_name = f"{section_name}.md"
                    with open(report_dir / file_name, "w") as f:
                        f.write(content)
        return wrapper

    # 應用裝飾器
    message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
    message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
    message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

    # 現在開始顯示版面配置
    layout = create_layout()

    with Live(layout, refresh_per_second=4) as live:
        # 初始顯示
        update_display(layout)

        # 新增初始訊息
        message_buffer.add_message("系統", f"選擇的股票代碼: {selections['ticker']}")
        message_buffer.add_message(
            "系統", f"分析日期: {selections['analysis_date']}"
        )
        message_buffer.add_message(
            "系統",
            f"選擇的分析師: {', '.join(analyst.value for analyst in selections['analysts'])}",
        )
        update_display(layout)

        # 重設代理狀態
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "pending")

        # 重設報告區塊
        for section in message_buffer.report_sections:
            message_buffer.report_sections[section] = None
        message_buffer.current_report = None
        message_buffer.final_report = None

        # 將第一個分析師的代理狀態更新為進行中
        first_analyst = f"{selections['analysts'][0].value.capitalize()} Analyst"
        message_buffer.update_agent_status(first_analyst, "in_progress")
        update_display(layout)

        # 建立 spinner 文字
        spinner_text = (
            f"正在分析 {selections['ticker']} 於 {selections['analysis_date']}..."
        )
        update_display(layout, spinner_text)

        # 初始化狀態並獲取圖參數
        init_agent_state = graph.propagator.create_initial_state(
            selections["ticker"], selections["analysis_date"]
        )
        args = graph.propagator.get_graph_args()

        # 串流分析
        trace = []
        for chunk in graph.graph.stream(init_agent_state, **args):
            if len(chunk["messages"]) > 0:
                # 獲取區塊中的最後一條訊息
                last_message = chunk["messages"][-1]

                # 提取訊息內容和類型
                if hasattr(last_message, "content"):
                    content = extract_content_string(last_message.content)  # 使用輔助函式
                    msg_type = "推理"
                else:
                    content = str(last_message)
                    msg_type = "系統"

                # 將訊息新增到緩衝區
                message_buffer.add_message(msg_type, content)                

                # 如果是工具呼叫，則將其新增到工具呼叫中
                if hasattr(last_message, "tool_calls"):
                    for tool_call in last_message.tool_calls:
                        # 處理字典和物件兩種工具呼叫格式
                        if isinstance(tool_call, dict):
                            message_buffer.add_tool_call(
                                tool_call["name"], tool_call["args"]
                            )
                        else:
                            message_buffer.add_tool_call(tool_call.name, tool_call.args)

                # 根據區塊內容更新報告和代理狀態
                # 分析師團隊報告
                if "market_report" in chunk and chunk["market_report"]:
                    message_buffer.update_report_section(
                        "market_report", chunk["market_report"]
                    )
                    message_buffer.update_agent_status("Market Analyst", "completed")
                    # 將下一個分析師設定為進行中
                    if "social" in selections["analysts"]:
                        message_buffer.update_agent_status(
                            "Social Analyst", "in_progress"
                        )

                if "sentiment_report" in chunk and chunk["sentiment_report"]:
                    message_buffer.update_report_section(
                        "sentiment_report", chunk["sentiment_report"]
                    )
                    message_buffer.update_agent_status("Social Analyst", "completed")
                    # 將下一個分析師設定為進行中
                    if "news" in selections["analysts"]:
                        message_buffer.update_agent_status(
                            "News Analyst", "in_progress"
                        )

                if "news_report" in chunk and chunk["news_report"]:
                    message_buffer.update_report_section(
                        "news_report", chunk["news_report"]
                    )
                    message_buffer.update_agent_status("News Analyst", "completed")
                    # 將下一個分析師設定為進行中
                    if "fundamentals" in selections["analysts"]:
                        message_buffer.update_agent_status(
                            "Fundamentals Analyst", "in_progress"
                        )

                if "fundamentals_report" in chunk and chunk["fundamentals_report"]:
                    message_buffer.update_report_section(
                        "fundamentals_report", chunk["fundamentals_report"]
                    )
                    message_buffer.update_agent_status(
                        "Fundamentals Analyst", "completed"
                    )
                    # 將所有研究團隊成員設定為進行中
                    update_research_team_status("in_progress")

                # 研究團隊 - 處理投資辯論狀態
                if (
                    "investment_debate_state" in chunk
                    and chunk["investment_debate_state"]
                ):
                    debate_state = chunk["investment_debate_state"]

                    # 更新看漲研究員狀態和報告
                    if "bull_history" in debate_state and debate_state["bull_history"]:
                        # 保持所有研究團隊成員為進行中
                        update_research_team_status("in_progress")
                        # 提取最新的看漲回應
                        bull_responses = debate_state["bull_history"].split("\n")
                        latest_bull = bull_responses[-1] if bull_responses else ""
                        if latest_bull:
                            message_buffer.add_message("推理", latest_bull)
                            # 使用看漲研究員的最新分析更新研究報告
                            message_buffer.update_report_section(
                                "investment_plan",
                                f"### 看漲研究員分析\n{latest_bull}",
                            )

                    # 更新看跌研究員狀態和報告
                    if "bear_history" in debate_state and debate_state["bear_history"]:
                        # 保持所有研究團隊成員為進行中
                        update_research_team_status("in_progress")
                        # 提取最新的看跌回應
                        bear_responses = debate_state["bear_history"].split("\n")
                        latest_bear = bear_responses[-1] if bear_responses else ""
                        if latest_bear:
                            message_buffer.add_message("推理", latest_bear)
                            # 使用看跌研究員的最新分析更新研究報告
                            message_buffer.update_report_section(
                                "investment_plan",
                                f"{message_buffer.report_sections['investment_plan']}\n\n### 看跌研究員分析\n{latest_bear}",
                            )

                    # 更新研究經理狀態和最終決策
                    if (
                        "judge_decision" in debate_state
                        and debate_state["judge_decision"]
                    ):
                        # 在最終決策前保持所有研究團隊成員為進行中
                        update_research_team_status("in_progress")
                        message_buffer.add_message(
                            "推理",
                            f"研究經理: {debate_state['judge_decision']}",
                        )
                        # 使用最終決策更新研究報告
                        message_buffer.update_report_section(
                            "investment_plan",
                            f"{message_buffer.report_sections['investment_plan']}\n\n### 研究經理決策\n{debate_state['judge_decision']}",
                        )
                        # 將所有研究團隊成員標記為已完成
                        update_research_team_status("completed")
                        # 將第一個風險分析師設定為進行中
                        message_buffer.update_agent_status(
                            "Risky Analyst", "in_progress"
                        )

                # 交易團隊
                if (
                    "trader_investment_plan" in chunk
                    and chunk["trader_investment_plan"]
                ):
                    message_buffer.update_report_section(
                        "trader_investment_plan", chunk["trader_investment_plan"]
                    )
                    # 將第一個風險分析師設定為進行中
                    message_buffer.update_agent_status("Risky Analyst", "in_progress")

                # 風險管理團隊 - 處理風險辯論狀態
                if "risk_debate_state" in chunk and chunk["risk_debate_state"]:
                    risk_state = chunk["risk_debate_state"]

                    # 更新風險分析師狀態和報告
                    if (
                        "current_risky_response" in risk_state
                        and risk_state["current_risky_response"]
                    ):
                        message_buffer.update_agent_status(
                            "Risky Analyst", "in_progress"
                        )
                        message_buffer.add_message(
                            "推理",
                            f"風險分析師: {risk_state['current_risky_response']}",
                        )
                        # 僅使用風險分析師的最新分析更新風險報告
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### 風險分析師分析\n{risk_state['current_risky_response']}",
                        )

                    # 更新安全分析師狀態和報告
                    if (
                        "current_safe_response" in risk_state
                        and risk_state["current_safe_response"]
                    ):
                        message_buffer.update_agent_status(
                            "Safe Analyst", "in_progress"
                        )
                        message_buffer.add_message(
                            "推理",
                            f"安全分析師: {risk_state['current_safe_response']}",
                        )
                        # 僅使用安全分析師的最新分析更新風險報告
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### 安全分析師分析\n{risk_state['current_safe_response']}",
                        )

                    # 更新中立分析師狀態和報告
                    if (
                        "current_neutral_response" in risk_state
                        and risk_state["current_neutral_response"]
                    ):
                        message_buffer.update_agent_status(
                            "Neutral Analyst", "in_progress"
                        )
                        message_buffer.add_message(
                            "推理",
                            f"中立分析師: {risk_state['current_neutral_response']}",
                        )
                        # 僅使用中立分析師的最新分析更新風險報告
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### 中立分析師分析\n{risk_state['current_neutral_response']}",
                        )

                    # 更新投資組合經理狀態和最終決策
                    if "judge_decision" in risk_state and risk_state["judge_decision"]:
                        message_buffer.update_agent_status(
                            "Portfolio Manager", "in_progress"
                        )
                        message_buffer.add_message(
                            "推理",
                            f"投資組合經理: {risk_state['judge_decision']}",
                        )
                        # 僅使用最終決策更新風險報告
                        message_buffer.update_report_section(
                            "final_trade_decision",
                            f"### 投資組合經理決策\n{risk_state['judge_decision']}",
                        )
                        # 將風險分析師標記為已完成
                        message_buffer.update_agent_status("Risky Analyst", "completed")
                        message_buffer.update_agent_status("Safe Analyst", "completed")
                        message_buffer.update_agent_status(
                            "Neutral Analyst", "completed"
                        )
                        message_buffer.update_agent_status(
                            "Portfolio Manager", "completed"
                        )

                # 更新顯示
                update_display(layout)

            trace.append(chunk)

        # 獲取最終狀態和決策
        final_state = trace[-1]
        decision = graph.process_signal(final_state["final_trade_decision"])

        # 將所有代理狀態更新為已完成
        for agent in message_buffer.agent_status:
            message_buffer.update_agent_status(agent, "completed")

        message_buffer.add_message(
            "分析", f"已完成 {selections['analysis_date']} 的分析"
        )

        # 更新最終報告區塊
        for section in message_buffer.report_sections.keys():
            if section in final_state:
                message_buffer.update_report_section(section, final_state[section])

        # 顯示完整的最終報告
        display_complete_report(final_state)

        update_display(layout)


@app.command()
def analyze():
    """
    執行分析。
    """
    run_analysis()


if __name__ == "__main__":
    app()