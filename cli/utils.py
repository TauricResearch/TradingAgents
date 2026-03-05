# 匯入 questionary 套件，用於建立互動式命令列提示
import questionary
# 匯入類型提示，用於更清晰地定義函式簽名
from typing import List, Optional, Tuple, Dict
# 匯入 rich.console 用於美化輸出
from rich.console import Console

# 從 cli.models 模組匯入 AnalystType 列舉
from cli.models import AnalystType

# 初始化 console
console = Console()

# 定義分析師的順序和對應的類型
ANALYST_ORDER = [
    ("市場分析師", AnalystType.MARKET),
    ("社群媒體分析師", AnalystType.SOCIAL),
    ("新聞分析師", AnalystType.NEWS),
    ("基本面分析師", AnalystType.FUNDAMENTALS),
]


def get_ticker() -> str:
    """
    提示使用者輸入股票代碼。

    返回:
        str: 使用者輸入的股票代碼，已轉換為大寫並去除頭尾空格。
    """
    ticker = questionary.text(
        "請輸入要分析的股票代碼：",
        # 驗證輸入是否為空
        validate=lambda x: len(x.strip()) > 0 or "請輸入有效的股票代碼。",
        # 設定提示的樣式
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    # 如果使用者沒有輸入，則退出程式
    if not ticker:
        console.print("\n[red]未提供股票代碼。正在結束程式...[/red]")
        exit(1)

    # 返回處理過的股票代碼
    return ticker.strip().upper()


def get_analysis_date() -> str:
    """
    提示使用者輸入 YYYY-MM-DD 格式的日期。

    返回:
        str: 使用者輸入的日期字串。
    """
    import re
    from datetime import datetime

    def validate_date(date_str: str) -> bool:
        """驗證日期字串是否為 YYYY-MM-DD 格式"""
        # 使用正規表示式檢查格式
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return False
        try:
            # 嘗試將字串解析為日期物件
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    date = questionary.text(
        "請輸入分析日期 (YYYY-MM-DD)：",
        # 驗證日期格式是否正確
        validate=lambda x: validate_date(x.strip())
        or "請輸入有效的 YYYY-MM-DD 格式日期。",
        # 設定提示的樣式
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()

    # 如果使用者沒有輸入，則退出程式
    if not date:
        console.print("\n[red]未提供日期。正在結束程式...[/red]")
        exit(1)

    # 返回處理過的日期字串
    return date.strip()


def select_analysts() -> List[AnalystType]:
    """
    使用互動式核取方塊選擇分析師。

    返回:
        List[AnalystType]: 使用者選擇的分析師類型列表。
    """
    choices = questionary.checkbox(
        "選擇您的 [分析師團隊]：",
        # 設定可選項
        choices=[
            questionary.Choice(display, value=value) for display, value in ANALYST_ORDER
        ],
        # 提供操作說明
        instruction="\n- 按下空白鍵選擇/取消選擇分析師\n- 按下 'a' 鍵選擇/取消選擇所有\n- 完成後按下 Enter 鍵",
        # 驗證至少選擇一位分析師
        validate=lambda x: len(x) > 0 or "您必須至少選擇一位分析師。",
        # 設定提示的樣式
        style=questionary.Style(
            [
                ("checkbox-selected", "fg:green"),
                ("selected", "fg:green noinherit"),
                ("highlighted", "noinherit"),
                ("pointer", "noinherit"),
            ]
        ),
    ).ask()

    # 如果使用者沒有選擇，則退出程式
    if not choices:
        console.print("\n[red]未選擇任何分析師。正在結束程式...[/red]")
        exit(1)

    # 返回選擇的分析師列表
    return choices


def select_market() -> tuple[str, str]:
    """
    使用互動式選單選擇市場類型。

    返回:
        tuple[str, str]: 包含市場類型代碼和預設股票代碼的元組。
            市場類型: "us" (美股) 或 "tw" (台股)
            預設股票: "SPY" (美股) 或 "2330" (台股)
    """
    # 定義市場選項
    MARKET_OPTIONS = [
        ("🇺🇸 美股 (US Stocks)", ("us", "SPY")),
        ("🇹🇼 台股 (Taiwan Stocks)", ("tw", "2330")),
    ]

    choice = questionary.select(
        "選擇您要分析的市場：",
        # 設定可選項
        choices=[
            questionary.Choice(display, value=value) for display, value in MARKET_OPTIONS
        ],
        # 提供操作說明
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        # 設定提示的樣式
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()

    # 如果使用者沒有選擇，則退出程式
    if choice is None:
        console.print("\n[red]未選擇市場。正在結束程式...[/red]")
        exit(1)

    market_type, default_ticker = choice
    console.print(f"[green]已選擇：{'美股' if market_type == 'us' else '台股'}[/green]")
    
    # 返回市場類型和預設股票代碼
    return market_type, default_ticker


def select_research_depth() -> int:
    """
    使用互動式選單選擇研究深度。

    返回:
        int: 代表研究深度的整數。
    """

    # 定義研究深度的選項及其對應值
    DEPTH_OPTIONS = [
        ("淺層 - 快速研究，較少的辯論和策略討論", 1),
        ("中等 - 中等程度，適度的辯論和策略討論", 3),
        ("深層 - 全面研究，深入的辯論和策略討論", 5),
    ]

    choice = questionary.select(
        "選擇您的 [研究深度]：",
        # 設定可選項
        choices=[
            questionary.Choice(display, value=value) for display, value in DEPTH_OPTIONS
        ],
        # 提供操作說明
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        # 設定提示的樣式
        style=questionary.Style(
            [
                ("selected", "fg:yellow noinherit"),
                ("highlighted", "fg:yellow noinherit"),
                ("pointer", "fg:yellow noinherit"),
            ]
        ),
    ).ask()

    # 如果使用者沒有選擇，則退出程式
    if choice is None:
        console.print("\n[red]未選擇研究深度。正在結束程式...[/red]")
        exit(1)

    # 返回選擇的研究深度
    return choice


def select_shallow_thinking_agent(provider=None) -> str:
    """
    使用互動式選單選擇淺層思維的 LLM 引擎。

    參數:
        provider (str, optional): LLM 供應商的名稱（已廢棄，不再使用）。

    返回:
        str: 選擇的 LLM 模型的名稱。
    """
    
    # 定義不同供應商的淺層思維 LLM 引擎選項
    SHALLOW_AGENT_OPTIONS = {
        "OpenAI": [
            ("GPT-5.1", "gpt-5.1"),
            ("GPT-5-mini","gpt-5-mini"),
            ("GPT-5-nano","gpt-5-nano"),
            ("GPT-4.1-mini", "gpt-4.1-mini"),
            ("GPT-4.1-nano", "gpt-4.1-nano"),
            ("o4-mini", "o4-mini"),
        ],
        "Anthropic": [
            ("Claude Sonnet 4.5", "claude-sonnet-4-5-20250929"),
            ("Claude Haiku 4.5", "claude-haiku-4-5-20251001"),
            ("Claude Sonnet 4", "claude-sonnet-4-20250514"),
            ("Claude 3 Haiku", "claude-3-haiku-20240307"),
        ],
        "Google": [
            ("Gemini 2.5 Pro", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash", "gemini-2.5-flash"),
            ("Gemini 2.5 Flash Lite", "gemini-2.5-flash-lite"),
            ("Gemini 2.0 Flash", "gemini-2.0-flash"),
            ("Gemini 2.0 Flash-Lite", "gemini-2.0-flash-lite"),
        ],
        "Grok":[
            ("Grok 4.1 Fast Reasoning","grok-4-1-fast-reasoning"),
            ("Grok 4.1 Fast Non Reasoning","grok-4-1-fast-non-reasoning"),
            ("Grok 4 Fast Reasoning","grok-4-fast-reasoning"),
            ("Grok 4 Fast Non Reasoning","grok-4-fast-non-reasoning"),
            ("Grok 4","grok-4-0709"),
            ("Grok 3","grok-3"),
            ("Grok 3 Mini","grok-3-mini"),
        ],
        "DeepSeek": [
            ("DeepSeek Reasoner","deepseek-reasoner"),
            ("DeepSeek Chat","deepseek-chat"),
        ],
        "Qwen":[
            ("Qwen 3 Max", "qwen3-max"),
            ("Qwen Plus", "qwen-plus"),
            ("Qwen Flash", "qwen-flash"),
        ]
    }
    
    # 第一步：選擇供應商
    provider_choice = questionary.select(
        "選擇 [快速思維] 模型供應商：",
        choices=[
            questionary.Choice(provider_name, value=provider_name)
            for provider_name in SHALLOW_AGENT_OPTIONS.keys()
        ],
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()
    
    if provider_choice is None:
        console.print("\n[red]未選擇供應商。正在結束程式...[/red]")
        exit(1)
    
    # 第二步：根據選擇的供應商顯示模型列表
    model_choice = questionary.select(
        f"選擇 [{provider_choice}] 的快速思維模型：",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in SHALLOW_AGENT_OPTIONS[provider_choice]
        ],
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if model_choice is None:
        console.print(
            "\n[red]未選擇快速思維 LLM 引擎。正在結束程式...[/red]"
        )
        exit(1)
    
    # 如果選擇自訂，提示輸入模型名稱
    if model_choice == "custom":
        model_name = questionary.text(
            "請輸入快速思維 LLM 模型名稱：",
            validate=lambda x: len(x.strip()) > 0 or "請輸入有效的模型名稱。",
            style=questionary.Style(
                [
                    ("text", "fg:green"),
                    ("highlighted", "noinherit"),
                ]
            ),
        ).ask()
        
        if not model_name:
            console.print(
                "\n[red]未提供模型名稱。正在結束程式...[/red]"
            )
            exit(1)
        
        return model_name.strip()

    # 返回選擇的 LLM 模型
    return model_choice


def select_deep_thinking_agent(provider=None) -> str:
    """
    使用互動式選單選擇深層思維的 LLM 引擎。

    參數:
        provider (str, optional): LLM 供應商的名稱（已廢棄，不再使用）。

    返回:
        str: 選擇的 LLM 模型的名稱。
    """

    # 定義不同供應商的深層思維 LLM 引擎選項
    DEEP_AGENT_OPTIONS = {
        "OpenAI": [
            ("GPT-5.1", "gpt-5.1"),
            ("GPT-5-mini","gpt-5-mini"),
            ("GPT-5-nano","gpt-5-nano"),
            ("GPT-4.1-mini", "gpt-4.1-mini"),
            ("GPT-4.1-nano", "gpt-4.1-nano"),
            ("o4-mini", "o4-mini"),
        ],
        "Anthropic": [
            ("Claude Sonnet 4.5", "claude-sonnet-4-5-20250929"),
            ("Claude Haiku 4.5", "claude-haiku-4-5-20251001"),
            ("Claude Sonnet 4", "claude-sonnet-4-20250514"),
            ("Claude 3 Haiku", "claude-3-haiku-20240307"),
        ],
        "Google": [
            ("Gemini 2.5 Pro", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash", "gemini-2.5-flash"),
            ("Gemini 2.5 Flash Lite", "gemini-2.5-flash-lite"),
            ("Gemini 2.0 Flash", "gemini-2.0-flash"),
            ("Gemini 2.0 Flash-Lite", "gemini-2.0-flash-lite"),
        ],
        "Grok":[
            ("Grok 4.1 Fast Reasoning","grok-4-1-fast-reasoning"),
            ("Grok 4.1 Fast Non Reasoning","grok-4-1-fast-non-reasoning"),
            ("Grok 4 Fast Reasoning","grok-4-fast-reasoning"),
            ("Grok 4 Fast Non Reasoning","grok-4-fast-non-reasoning"),
            ("Grok 4","grok-4-0709"),
            ("Grok 3","grok-3"),
            ("Grok 3 Mini","grok-3-mini"),
        ],
        "DeepSeek":[
            ("DeepSeek Reasoner","deepseek-reasoner"),
            ("DeepSeek Chat","deepseek-chat"),
        ],
        "Qwen":[
            ("Qwen 3 Max", "qwen3-max"),
            ("Qwen Plus", "qwen-plus"),
            ("Qwen Flash", "qwen-flash"),
        ]
    }
    
    # 第一步：選擇供應商
    provider_choice = questionary.select(
        "選擇 [深度思維] 模型供應商：",
        choices=[
            questionary.Choice(provider_name, value=provider_name)
            for provider_name in DEEP_AGENT_OPTIONS.keys()
        ],
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()
    
    if provider_choice is None:
        console.print("\n[red]未選擇供應商。正在結束程式...[/red]")
        exit(1)
    
    # 第二步：根據選擇的供應商顯示模型列表
    model_choice = questionary.select(
        f"選擇 [{provider_choice}] 的深度思維模型：",
        choices=[
            questionary.Choice(display, value=value)
            for display, value in DEEP_AGENT_OPTIONS[provider_choice]
        ],
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()

    if model_choice is None:
        console.print("\n[red]未選擇深度思維 LLM 引擎。正在結束程式...[/red]")
        exit(1)
    
    # 如果選擇自訂，提示輸入模型名稱
    if model_choice == "custom":
        model_name = questionary.text(
            "請輸入深度思維 LLM 模型名稱：",
            validate=lambda x: len(x.strip()) > 0 or "請輸入有效的模型名稱。",
            style=questionary.Style(
                [
                    ("text", "fg:green"),
                    ("highlighted", "noinherit"),
                ]
            ),
        ).ask()
        
        if not model_name:
            console.print(
                "\n[red]未提供模型名稱。正在結束程式...[/red]"
            )
            exit(1)
        
        return model_name.strip()

    # 返回選擇的 LLM 模型
    return model_choice

def select_llm_provider() -> tuple[str, str]:
    """
    使用互動式選單選擇 LLM 供應商。

    返回:
        tuple[str, str]: 包含供應商顯示名稱和 API 基礎 URL 的元組。
    """
    # 定義 LLM 供應商及其 API 基礎 URL
    BASE_URLS = [
        ("OpenAI", "https://api.openai.com/v1"),
        ("Anthropic", "https://api.anthropic.com/v1"),
        ("Google", "https://generativelanguage.googleapis.com/v1beta/openai"),
        ("Grok", "https://api.x.ai/v1"),
        ("DeepSeek", "https://api.deepseek.com/v1"),
        ("Qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
        ("自訂 URL", "custom")  # 新增自訂 URL 選項
    ]
    
    choice = questionary.select(
        "選擇您的 LLM 供應商：",
        # 設定可選項
        choices=[
            questionary.Choice(display, value=(display, value))
            for display, value in BASE_URLS
        ],
        # 提供操作說明
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        # 設定提示的樣式
        style=questionary.Style(
            [
                ("selected", "fg:magenta noinherit"),
                ("highlighted", "fg:magenta noinherit"),
                ("pointer", "fg:magenta noinherit"),
            ]
        ),
    ).ask()
    
    # 如果使用者沒有選擇，則退出程式
    if choice is None:
        console.print("\n[red]未選擇 LLM 後端。正在結束程式...[/red]")
        exit(1)
    
    # 解構選擇的元組
    display_name, url = choice
    
    # 如果使用者選擇自訂 URL，提示輸入
    if url == "custom":
        custom_url = questionary.text(
            "請輸入自訂的 Base URL：",
            # 驗證 URL 格式
            validate=lambda x: (x.strip().startswith("http://") or x.strip().startswith("https://")) 
                or "請輸入有效的 URL（必須以 http:// 或 https:// 開頭）",
            # 設定提示的樣式
            style=questionary.Style(
                [
                    ("text", "fg:green"),
                    ("highlighted", "noinherit"),
                ]
            ),
        ).ask()
        
        # 如果使用者沒有輸入，則退出程式
        if not custom_url:
            console.print("\n[red]未提供 Base URL。正在結束程式...[/red]")
            exit(1)
        
        url = custom_url.strip()
        display_name = "自訂供應商"
    
    # 印出使用者的選擇
    print(f"您選擇了：{display_name}\tURL: {url}")
    
    # 返回供應商名稱和 URL
    return display_name, url


def select_embedding_provider() -> tuple[str, str]:
    """
    使用互動式選單選擇嵌入模型供應商。

    返回:
        tuple[str, str]: 包含供應商名稱和 API 基礎 URL 的元組。
                        對於本地模型，URL 為 "local"。
    """
    # 定義嵌入模型供應商（本地 HuggingFace、OpenAI 和自訂）
    EMBEDDING_PROVIDERS = [
        ("🖥️  本地模型 (HuggingFace) - 免費", "local"),
        ("☁️  OpenAI - 收費", "https://api.openai.com/v1"),
        ("🔧 自訂 URL", "custom")
    ]
    
    choice = questionary.select(
        "選擇您的嵌入模型供應商：",
        # 設定可選項
        choices=[
            questionary.Choice(display, value=(display, value))
            for display, value in EMBEDDING_PROVIDERS
        ],
        # 提供操作說明
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        # 設定提示的樣式
        style=questionary.Style(
            [
                ("selected", "fg:cyan noinherit"),
                ("highlighted", "fg:cyan noinherit"),
                ("pointer", "fg:cyan noinherit"),
            ]
        ),
    ).ask()
    
    # 如果使用者沒有選擇，則退出程式
    if choice is None:
        console.print("\n[red]未選擇嵌入模型供應商。正在結束程式...[/red]")
        exit(1)
    
    # 解構選擇的元組
    display_name, url = choice
    
    # 如果選擇自訂 URL，提示使用者輸入
    if url == "custom":
        custom_url = questionary.text(
            "請輸入自訂的 Base URL：",
            validate=lambda x: (x.startswith("http://") or x.startswith("https://")) or "URL 必須以 http:// 或 https:// 開頭",
            style=questionary.Style(
                [
                    ("text", "fg:green"),
                    ("highlighted", "noinherit"),
                ]
            ),
        ).ask()
        
        # 如果使用者沒有輸入，則退出程式
        if not custom_url:
            console.print("\n[red]未提供 Base URL。正在結束程式...[/red]")
            exit(1)
        
        url = custom_url.strip()
        display_name = "自訂供應商"
    
    # 印出使用者的選擇
    if url == "local":
        print(f"您選擇了：{display_name}（本地執行，無需 API Key）")
    else:
        print(f"您選擇了嵌入模型：{display_name}\tURL: {url}")
    
    # 返回供應商名稱和 URL
    return display_name, url


def select_embedding_model(provider: str) -> str:
    """
    根據供應商選擇具體的嵌入模型。

    參數:
        provider (str): 嵌入模型供應商名稱

    返回:
        str: 選擇的嵌入模型名稱
    """
    # 本地 HuggingFace 模型選項
    LOCAL_EMBEDDING_MODELS = [
        ("all-MiniLM-L6-v2 (推薦) - 90MB, 輕量快速", "all-MiniLM-L6-v2"),
        ("all-mpnet-base-v2 - 420MB, 更高質量", "all-mpnet-base-v2"),
    ]
    
    # OpenAI 嵌入模型選項
    OPENAI_EMBEDDING_MODELS = [
        ("text-embedding-3-small (推薦) - 高性價比", "text-embedding-3-small"),
        ("text-embedding-3-large - 最高質量", "text-embedding-3-large"),
    ]
    
    # 根據供應商判斷使用哪個模型列表
    if "本地" in provider or "local" in provider.lower():
        model_options = LOCAL_EMBEDDING_MODELS
        prompt_text = "選擇本地嵌入模型："
        description = "\n[dim]💡 本地模型首次使用會自動下載，之後無需網路連接[/dim]"
    else:
        model_options = OPENAI_EMBEDDING_MODELS
        prompt_text = "選擇 OpenAI 嵌入模型："
        description = "\n[dim]💡 OpenAI 模型需要 API Key 和網路連接[/dim]"
    
    console.print(description)
    
    choice = questionary.select(
        prompt_text,
        choices=[
            questionary.Choice(display, value=value)
            for display, value in model_options
        ],
        instruction="\n- 使用方向鍵導覽\n- 按下 Enter 鍵選擇",
        style=questionary.Style(
            [
                ("selected", "fg:green noinherit"),
                ("highlighted", "fg:green noinherit"),
                ("pointer", "fg:green noinherit"),
            ]
        ),
    ).ask()
    
    if choice is None:
        console.print("\n[red]未選擇嵌入模型。正在結束程式...[/red]")
        exit(1)
    
    console.print(f"[green]✓ 已選擇：{choice}[/green]")
    return choice


def get_api_key(model_type: str, default_key: Optional[str] = None) -> str:
    """
    提示使用者輸入 API Key，如果留空則使用預設值。

    參數:
        model_type (str): 模型類型（例如：「快速思維」、「深度思維」、「嵌入模型」）
        default_key (Optional[str]): 從 .env 文件讀取的預設 API Key

    返回:
        str: 使用者輸入的 API Key 或預設值
    """
    import os
    from rich.console import Console
    
    console = Console()
    
    # 顯示提示訊息
    if default_key:
        hint = f"[dim]（留空使用 .env 中的 API Key: {default_key[:10]}...{default_key[-4:]}）[/dim]"
    else:
        hint = "[dim]（必填）[/dim]"
    
    console.print(f"\n[cyan]{model_type} API Key {hint}[/cyan]")
    
    api_key = questionary.password(
        f"請輸入 {model_type} 的 API Key：",
        style=questionary.Style(
            [
                ("text", "fg:green"),
                ("highlighted", "noinherit"),
            ]
        ),
    ).ask()
    
    # 如果使用者沒有輸入，使用預設值
    if not api_key or api_key.strip() == "":
        if default_key:
            console.print(f"[green]✓ 使用 .env 中的 API Key[/green]")
            return default_key
        else:
            console.print(f"\n[red]未提供 {model_type} API Key。正在結束程式...[/red]")
            exit(1)
    
    console.print(f"[green]✓ API Key 已設定[/green]")
    return api_key.strip()