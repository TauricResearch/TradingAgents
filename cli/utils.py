import questionary
from typing import List, Optional, Tuple, Dict
from rich.console import Console

from cli.models import AnalystType

console = Console()

ANALYST_ORDER = [
    ("Market Analyst", AnalystType.MARKET),
    ("Social Media Analyst", AnalystType.SOCIAL),
    ("News Analyst", AnalystType.NEWS),
    ("Fundamentals Analyst", AnalystType.FUNDAMENTALS),
]


def get_ticker() -> str:
    """Prompt the user to enter a ticker symbol."""
    ticker = questionary.text(
        "📈 请输入要分析的股票代码:",
        validate=lambda x: len(x.strip()) > 0 or "请输入有效的股票代码。",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not ticker:
        console.print("\n[red]❌ 未提供股票代码，退出...[/red]")
        exit(1)

    return ticker.strip().upper()


def get_analysis_date() -> str:
    """Prompt the user to enter a date in YYYY-MM-DD format."""
    import re
    from datetime import datetime

    def validate_date(date_str: str) -> bool:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return False
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    date = questionary.text(
        "📅 请输入分析日期 (YYYY-MM-DD):",
        validate=lambda x: validate_date(x.strip())
        or "请输入有效的日期格式 (YYYY-MM-DD)。",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    if not date:
        console.print("\n[red]❌ 未提供分析日期，退出...[/red]")
        exit(1)

    return date.strip()


def select_analysts() -> List[AnalystType]:
    """Select analysts using an interactive checkbox."""
    choices = questionary.checkbox(
        "👥 选择分析师团队:",
        choices=[
            questionary.Choice(display, value=value) for display, value in ANALYST_ORDER
        ],
        instruction="\n- 按空格键选择/取消选择分析师\n- 按'a'键全选/取消全选\n- 按Enter确认",
        validate=lambda x: len(x) > 0 or "必须至少选择一个分析师。",
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:green"),
                ("selected", "fg:green noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    if not choices:
        console.print("\n[red]❌ 未选择任何分析师，退出...[/red]")
        exit(1)

    return choices


def select_research_depth() -> int:
    """Select research depth using an interactive selection."""

    # Define research depth options with their corresponding values
    DEPTH_OPTIONS = [
        ("🔍 浅层 - 快速研究，少量辩论和策略讨论", 1),
        ("⚖️ 中等 - 平衡研究，适度辩论和策略讨论", 3),
        ("🔬 深度 - 全面研究，深入辩论和策略讨论", 5),
    ]

    choice = questionary.select(
        "📊 选择研究深度:",
        choices=[
            questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS
        ],
        instruction="\n- 使用方向键导航\n- 按Enter选择\n- 深度越高，分析越全面但耗时越长",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]❌ 未选择研究深度，退出...[/red]")
        exit(1)

    return choice


def select_shallow_thinking_agent(provider) -> str:
    """Select shallow thinking llm engine using an interactive selection."""

    # Define shallow thinking llm engine options with their corresponding model names
    SHALLOW_AGENT_OPTIONS = {
        # 国内免费大模型
        "qwen": [
            ("Qwen-Turbo - 快速响应，适合简单任务", "qwen-turbo"),
            ("Qwen-Plus - 平衡性能和速度", "qwen-plus"),
            ("Qwen-Max - 最强性能，适合复杂任务", "qwen-max"),
        ],
        "ernie": [
            ("ERNIE-3.5-8K - 快速响应版本", "ernie-3.5-8k"),
            ("ERNIE-4.0-8K - 最新版本，性能更强", "ernie-4.0-8k"),
            ("ERNIE-4.0-128K - 长文本处理版本", "ernie-4.0-128k"),
        ],
        "glm": [
            ("GLM-4 - 智谱AI最新模型", "glm-4"),
            ("GLM-4-Flash - 快速响应版本", "glm-4-flash"),
            ("GLM-4V - 多模态版本", "glm-4v"),
        ],
        "kimi": [
            ("Moonshot-v1-8K - 标准版本", "moonshot-v1-8k"),
            ("Moonshot-v1-32K - 长文本版本", "moonshot-v1-32k"),
            ("Moonshot-v1-128K - 超长文本版本", "moonshot-v1-128k"),
        ],
        # 国外模型
        "openai": [
            ("GPT-4o-mini - Fast and efficient for quick tasks", "gpt-4o-mini"),
            ("GPT-4.1-nano - Ultra-lightweight model for basic operations", "gpt-4.1-nano"),
            ("GPT-4.1-mini - Compact model with good performance", "gpt-4.1-mini"),
            ("GPT-4o - Standard model with solid capabilities", "gpt-4o"),
        ],
        "anthropic": [
            ("Claude Haiku 3.5 - Fast inference and standard capabilities", "claude-3-5-haiku-latest"),
            ("Claude Sonnet 3.5 - Highly capable standard model", "claude-3-5-sonnet-latest"),
            ("Claude Sonnet 3.7 - Exceptional hybrid reasoning and agentic capabilities", "claude-3-7-sonnet-latest"),
            ("Claude Sonnet 4 - High performance and excellent reasoning", "claude-sonnet-4-0"),
        ],
        "google": [
            ("Gemini 2.0 Flash-Lite - Cost efficiency and low latency", "gemini-2.0-flash-lite"),
            ("Gemini 2.0 Flash - Next generation features, speed, and thinking", "gemini-2.0-flash"),
            ("Gemini 2.5 Flash - Adaptive thinking, cost efficiency", "gemini-2.5-flash-preview-05-20"),
        ],
        "openrouter": [
            ("Meta: Llama 4 Scout", "meta-llama/llama-4-scout:free"),
            ("Meta: Llama 3.3 8B Instruct - A lightweight and ultra-fast variant of Llama 3.3 70B", "meta-llama/llama-3.3-8b-instruct:free"),
            ("google/gemini-2.0-flash-exp:free - Gemini Flash 2.0 offers a significantly faster time to first token", "google/gemini-2.0-flash-exp:free"),
        ],
        "ollama": [
            ("llama3.1 local", "llama3.1"),
            ("llama3.2 local", "llama3.2"),
        ]
    }

    choice = questionary.select(
        "🚀 选择快速思考模型:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in SHALLOW_AGENT_OPTIONS[provider.lower()]
        ],
        instruction="\n- 使用方向键导航\n- 按Enter选择\n- 快速模型用于简单任务",
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print(
            "\n[red]❌ 未选择快速思考模型，退出...[/red]"
        )
        exit(1)

    return choice


def select_deep_thinking_agent(provider) -> str:
    """Select deep thinking llm engine using an interactive selection."""

    # Define deep thinking llm engine options with their corresponding model names
    DEEP_AGENT_OPTIONS = {
        # 国内免费大模型
        "qwen": [
            ("Qwen-Plus - 平衡性能，适合复杂分析", "qwen-plus"),
            ("Qwen-Max - 最强性能，适合深度思考", "qwen-max"),
            ("Qwen-Turbo - 快速版本，适合一般任务", "qwen-turbo"),
        ],
        "ernie": [
            ("ERNIE-4.0-8K - 最新版本，性能最强", "ernie-4.0-8k"),
            ("ERNIE-4.0-128K - 长文本处理版本", "ernie-4.0-128k"),
            ("ERNIE-3.5-8K - 稳定版本", "ernie-3.5-8k"),
        ],
        "glm": [
            ("GLM-4 - 智谱AI最新模型，性能最强", "glm-4"),
            ("GLM-4-Flash - 快速响应版本", "glm-4-flash"),
            ("GLM-4V - 多模态版本", "glm-4v"),
        ],
        "kimi": [
            ("Moonshot-v1-32K - 长文本版本，适合深度分析", "moonshot-v1-32k"),
            ("Moonshot-v1-128K - 超长文本版本", "moonshot-v1-128k"),
            ("Moonshot-v1-8K - 标准版本", "moonshot-v1-8k"),
        ],
        # 国外模型
        "openai": [
            ("GPT-4.1-nano - Ultra-lightweight model for basic operations", "gpt-4.1-nano"),
            ("GPT-4.1-mini - Compact model with good performance", "gpt-4.1-mini"),
            ("GPT-4o - Standard model with solid capabilities", "gpt-4o"),
            ("o4-mini - Specialized reasoning model (compact)", "o4-mini"),
            ("o3-mini - Advanced reasoning model (lightweight)", "o3-mini"),
            ("o3 - Full advanced reasoning model", "o3"),
            ("o1 - Premier reasoning and problem-solving model", "o1"),
        ],
        "anthropic": [
            ("Claude Haiku 3.5 - Fast inference and standard capabilities", "claude-3-5-haiku-latest"),
            ("Claude Sonnet 3.5 - Highly capable standard model", "claude-3-5-sonnet-latest"),
            ("Claude Sonnet 3.7 - Exceptional hybrid reasoning and agentic capabilities", "claude-3-7-sonnet-latest"),
            ("Claude Sonnet 4 - High performance and excellent reasoning", "claude-sonnet-4-0"),
            ("Claude Opus 4 - Most powerful Anthropic model", "	claude-opus-4-0"),
        ],
        "google": [
            ("Gemini 2.0 Flash-Lite - Cost efficiency and low latency", "gemini-2.0-flash-lite"),
            ("Gemini 2.0 Flash - Next generation features, speed, and thinking", "gemini-2.0-flash"),
            ("Gemini 2.5 Flash - Adaptive thinking, cost efficiency", "gemini-2.5-flash-preview-05-20"),
            ("Gemini 2.5 Pro", "gemini-2.5-pro-preview-06-05"),
        ],
        "openrouter": [
            ("DeepSeek V3 - a 685B-parameter, mixture-of-experts model", "deepseek/deepseek-chat-v3-0324:free"),
            ("Deepseek - latest iteration of the flagship chat model family from the DeepSeek team.", "deepseek/deepseek-chat-v3-0324:free"),
        ],
        "ollama": [
            ("llama3.1 local", "llama3.1"),
            ("qwen3", "qwen3"),
        ]
    }
    
    choice = questionary.select(
        "🧠 选择深度思考模型:",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in DEEP_AGENT_OPTIONS[provider.lower()]
        ],
        instruction="\n- 使用方向键导航\n- 按Enter选择\n- 深度模型用于复杂分析",
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    if choice is None:
        console.print("\n[red]❌ 未选择深度思考模型，退出...[/red]")
        exit(1)

    return choice

def select_llm_provider() -> tuple[str, str]:
    """Select the LLM provider using interactive selection."""
    # Define LLM provider options with their corresponding endpoints
    BASE_URLS = [
        # 国内免费大模型（推荐）
        ("🇨🇳 通义千问 (Qwen) - 金融领域表现优秀", "qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        ("🇨🇳 文心一言 (ERNIE) - 免费额度最高", "ernie", "https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat"),
        ("🇨🇳 智谱AI (GLM) - 清华大学出品", "glm", "https://open.bigmodel.cn/api/paas/v4"),
        ("🇨🇳 月之暗面Kimi - 长文本处理强", "kimi", "https://api.moonshot.cn/v1"),
        # 国外模型
        ("🌍 OpenAI - GPT系列", "openai", "https://api.openai.com/v1"),
        ("🌍 Anthropic - Claude系列", "anthropic", "https://api.anthropic.com/"),
        ("🌍 Google - Gemini系列", "google", "https://generativelanguage.googleapis.com/v1"),
        ("🌍 OpenRouter - 多模型聚合", "openrouter", "https://openrouter.ai/api/v1"),
        ("🌍 Ollama - 本地部署", "ollama", "http://localhost:11434/v1"),
    ]
    
    choice = questionary.select(
        "🤖 选择AI模型提供商:",
        choices=[
            questionary.Choice(display, value=(provider, url))
            for display, provider, url in BASE_URLS
        ],
        instruction="\n- 使用方向键导航\n- 按Enter选择\n- 国内模型推荐用于金融分析",
        style=questionary.Style(
            [
                ("selected", "fg:green noinherit"),
                ("highlighted", "fg:green noinherit"),
                ("pointer", "fg:green noinherit"),
            ]
        ),
    ).ask()
    
    if choice is None:
        console.print("\n[red]❌ 未选择AI模型提供商，退出...[/red]")
        exit(1)
    
    provider, url = choice
    print(f"✅ 已选择: {provider}\tURL: {url}")
    
    return provider, url
