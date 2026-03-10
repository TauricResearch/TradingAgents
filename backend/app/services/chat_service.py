"""
Chat service for answering questions about analysis reports
Uses the user's LLM API key to call an OpenAI-compatible endpoint.
"""
import logging
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_ZH = """你是 TradingAgentsX 的首席金融分析助手，擁有華爾街頂級分析師的專業素養。你的任務是基於提供的多位專業分析師（如基本面、技術面、新聞情緒等）的報告，精準、專業地回答使用者的問題。

回答指南與規則：
1. 【嚴守上下文】所有數據與觀點必須基於提供的報告內容，絕不可隨意編造或引入外部未經證實的資訊。若報告中未提及，請誠實告知「報告中未涵蓋此細節」。
2. 【極致簡潔】回答必須非常簡潔扼要，專注於核心結論，不要產生冗長且無意義的論述。
3. 【結構化與排版】使用清晰的 Markdown 格式排版。善用列點、粗體標示關鍵數據，讓使用者能快速抓到重點。
4. 【開門見山】直接切入要點回答問題，不需要以「根據提供的報告...」這類多餘的廢話開頭。保持自信且客觀專業的語氣。
5. 【明確引用】在提及特定預測或論點時，盡可能指出是哪一位分析師或哪一份報告提到的（例如：「技術面報告指出...」）。
6. 【語言要求】全程使用流暢、具備金融專業術語的繁體中文回答。

以下是本次對話的基準報告內容：
=========================================
【標的】: {ticker}
【分析日期】: {analysis_date}

{reports_text}
========================================="""

SYSTEM_PROMPT_EN = """You are the Lead Financial Analysis Assistant for TradingAgentsX, possessing the expertise of a top-tier Wall Street analyst. Your task is to accurately and professionally answer user questions based on the provided reports from various specialized analysts (e.g., Fundamentals, Technicals, Sentiment, etc.).

Guidelines and Rules:
1. [Strict Adherence to Context] All data and opinions must be grounded strictly in the provided reports. Do not fabricate data or bring in unverified external information. If the reports do not contain the answer, honestly state, "The provided reports do not cover this detail."
2. [Extreme Conciseness] Keep your answers extremely concise and to the point. Focus on core conclusions and avoid lengthy, unnecessary elaborations.
3. [Structure and Readability] Use clear Markdown formatting. Utilize bullet points and bold text for key metrics so the user can quickly grasp key insights.
4. [Get to the Point] Start your answer directly and confidently without filler introductions like "Based on the provided reports...".
5. [Explicit Citations] When mentioning specific forecasts or arguments, clarify which analyst or report it originated from (e.g., "The Technical Analyst noted...").
6. [Language Constraint] Ensure all responses are in highly professional, fluent English with appropriate financial terminology.

Below are the baseline reports for this conversation:
=========================================
[Ticker]: {ticker}
[Analysis Date]: {analysis_date}

{reports_text}
========================================="""


def _flatten_reports(reports: Dict[str, Any], language: str = "zh-TW") -> str:
    """Flatten all reports into a single text block for context."""
    sections = []
    
    if language == "zh-TW":
        REPORT_LABELS = {
            "market_report": "市場分析師 (Market Analyst)",
            "sentiment_report": "社群情緒分析師 (Social Media Analyst)",
            "news_report": "新聞分析師 (News Analyst)",
            "fundamentals_report": "基本面分析師 (Fundamentals Analyst)",
            "trader_investment_plan": "交易員 (Trader)",
        }
        debate_keys = {
            "investment_debate_state": {
                "bull_history": "看漲研究員 (Bull Researcher)",
                "bear_history": "看跌研究員 (Bear Researcher)",
                "judge_decision": "研究經理 (Research Manager)",
            },
            "risk_debate_state": {
                "risky_history": "激進分析師 (Aggressive Analyst)",
                "safe_history": "保守分析師 (Conservative Analyst)",
                "neutral_history": "中立分析師 (Neutral Analyst)",
                "judge_decision": "風險經理 (Risk Manager)",
            },
        }
    else:
        REPORT_LABELS = {
            "market_report": "Market Analyst",
            "sentiment_report": "Social Media Analyst",
            "news_report": "News Analyst",
            "fundamentals_report": "Fundamentals Analyst",
            "trader_investment_plan": "Trader",
        }
        debate_keys = {
            "investment_debate_state": {
                "bull_history": "Bull Researcher",
                "bear_history": "Bear Researcher",
                "judge_decision": "Research Manager",
            },
            "risk_debate_state": {
                "risky_history": "Aggressive Analyst",
                "safe_history": "Conservative Analyst",
                "neutral_history": "Neutral Analyst",
                "judge_decision": "Risk Manager",
            },
        }
    
    for key, label in REPORT_LABELS.items():
        content = reports.get(key)
        if content and isinstance(content, str):
            sections.append(f"## {label}\n{content}")
    
    for state_key, sub_keys in debate_keys.items():
        state = reports.get(state_key)
        if isinstance(state, dict):
            for sub_key, label in sub_keys.items():
                content = state.get(sub_key)
                if content and isinstance(content, str):
                    sections.append(f"## {label}\n{content}")
    
    return "\n\n".join(sections) if sections else "(No reports available)"


async def chat_with_reports(
    message: str,
    reports: Dict[str, Any],
    ticker: str,
    analysis_date: str,
    history: Optional[List[Dict[str, str]]],
    model: str,
    api_key: str,
    base_url: str,
    language: str = "zh-TW",
) -> str:
    """
    Send a chat message about analysis reports to the LLM.
    
    Args:
        message: User's question
        reports: Full analysis reports dict
        ticker: Stock ticker
        analysis_date: Analysis date string
        history: Previous conversation messages [{role, content}]
        model: LLM model name
        api_key: User's API key
        base_url: LLM API base URL
        language: Response language
        
    Returns:
        Assistant's reply string
    """
    reports_text = _flatten_reports(reports, language=language)
    
    # Increase truncation limit significantly to support 12 full analyst reports natively
    MAX_REPORT_CHARS = 100000
    if len(reports_text) > MAX_REPORT_CHARS:
        reports_text = reports_text[:MAX_REPORT_CHARS] + "\n\n...(報告內容已截斷以符合模型限制)..."
        logger.info(f"Reports truncated from {len(reports_text)} to {MAX_REPORT_CHARS} chars")
    
    # Choose system prompt based on language
    if language == "en":
        system_prompt = SYSTEM_PROMPT_EN.format(
            ticker=ticker,
            analysis_date=analysis_date,
            reports_text=reports_text,
        )
    else:
        system_prompt = SYSTEM_PROMPT_ZH.format(
            ticker=ticker,
            analysis_date=analysis_date,
            reports_text=reports_text,
        )
    
    # Build messages list
    messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation history (limit to last 6 messages to control token usage)
    if history:
        recent_history = history[-6:]
        for msg in recent_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })
    
    # Add current user message
    messages.append({"role": "user", "content": message})
    
    logger.info(f"Chat request for {ticker}: model={model}, history_len={len(history) if history else 0}, system_prompt_len={len(system_prompt)}")
    
    try:
        # Call LLM via async OpenAI-compatible SDK
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=60.0,
        )
        
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=8192,
        )
        
        reply = response.choices[0].message.content or ""
        logger.info(f"Chat response for {ticker}: {len(reply)} chars")
        
        return reply
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"LLM call failed: {error_msg}", exc_info=True)
        
        # Provide user-friendly error messages
        if "maximum context length" in error_msg.lower() or "token" in error_msg.lower():
            raise Exception(f"報告內容過長，超出模型 token 限制。請嘗試縮短問題或清除對話歷史後重試。")
        elif "rate_limit" in error_msg.lower() or "429" in error_msg:
            raise Exception(f"API 速率限制，請稍後再試。")
        elif "401" in error_msg or "api_key" in error_msg.lower():
            raise Exception(f"API Key 無效或已過期，請檢查設定。")
        elif "timeout" in error_msg.lower():
            raise Exception(f"請求超時，請稍後再試。")
        else:
            raise
