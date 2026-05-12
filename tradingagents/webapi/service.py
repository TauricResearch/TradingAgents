from __future__ import annotations

import copy
import json
import os
import logging
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote
from urllib.request import urlopen

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

from .schemas import AnalysisRequest, SettingsPayload

logger = logging.getLogger(__name__)

API_KEY_ENV_BY_PROVIDER: Dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
}

AGENT_DISPLAY_NAMES: Dict[str, str] = {
    "Market Analyst": "市场分析师",
    "Social Analyst": "社媒分析师",
    "News Analyst": "新闻分析师",
    "Fundamentals Analyst": "基本面分析师",
    "Bull Researcher": "多头研究员",
    "Bear Researcher": "空头研究员",
    "Research Manager": "研究经理",
    "Trader": "交易员",
    "Aggressive Analyst": "进取型风险分析师",
    "Neutral Analyst": "中性风险分析师",
    "Conservative Analyst": "保守型风险分析师",
    "Portfolio Manager": "组合经理",
}

COMMON_COMPANY_ALIASES: Dict[str, Dict[str, str]] = {
    "英伟达": {"ticker": "NVDA", "company_name": "英伟达", "market": "US"},
    "苹果": {"ticker": "AAPL", "company_name": "苹果", "market": "US"},
    "微软": {"ticker": "MSFT", "company_name": "微软", "market": "US"},
    "特斯拉": {"ticker": "TSLA", "company_name": "特斯拉", "market": "US"},
    "谷歌": {"ticker": "GOOGL", "company_name": "谷歌", "market": "US"},
    "亚马逊": {"ticker": "AMZN", "company_name": "亚马逊", "market": "US"},
    "Meta": {"ticker": "META", "company_name": "Meta", "market": "US"},
    "脸书": {"ticker": "META", "company_name": "Meta", "market": "US"},
    "腾讯": {"ticker": "0700.HK", "company_name": "腾讯控股", "market": "HK"},
    "阿里": {"ticker": "BABA", "company_name": "阿里巴巴", "market": "US"},
    "阿里巴巴": {"ticker": "BABA", "company_name": "阿里巴巴", "market": "US"},
}


def agent_display_name(agent: str) -> str:
    return AGENT_DISPLAY_NAMES.get(agent, agent)


def mock_step_delay() -> float:
    try:
        return max(0.0, float(os.environ.get("TRADINGAGENTS_MOCK_STEP_DELAY", "0.35")))
    except ValueError:
        return 0.35


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(6, len(value) - 7)}{value[-3:]}"


def build_effective_config(settings: SettingsPayload) -> Dict[str, Any]:
    config = copy.deepcopy(DEFAULT_CONFIG)
    updates = settings.model_dump()
    config.update(
        {
            "llm_provider": updates["llm_provider"],
            "deep_think_llm": updates["deep_think_llm"],
            "quick_think_llm": updates["quick_think_llm"],
            "backend_url": updates["backend_url"],
            "google_thinking_level": updates["google_thinking_level"],
            "openai_reasoning_effort": updates["openai_reasoning_effort"],
            "anthropic_effort": updates["anthropic_effort"],
            "output_language": updates["output_language"],
            "max_debate_rounds": updates["max_debate_rounds"],
            "max_risk_discuss_rounds": updates["max_risk_discuss_rounds"],
            "checkpoint_enabled": updates["checkpoint_enabled"],
            "data_vendors": updates["data_vendors"],
        }
    )
    return config


def list_model_catalog() -> Dict[str, Dict[str, List[Dict[str, str]]]]:
    return {
        provider: {
            mode: [{"label": label, "value": value} for label, value in options]
            for mode, options in modes.items()
        }
        for provider, modes in MODEL_OPTIONS.items()
    }


def normalize_ticker_code(ticker: str) -> str:
    raw = ticker.strip().upper()
    for suffix in (".SS", ".SZ", ".SH", ".HK"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    return "".join(character for character in raw if character.isalnum())


def candidate_ticker_symbols(ticker: str) -> List[str]:
    symbol = normalize_ticker_code(ticker)
    if not symbol:
        return []
    if symbol.isdigit():
        candidates: List[str] = []
        if len(symbol) == 6:
            if symbol.startswith("6"):
                candidates.extend([f"{symbol}.SS", f"{symbol}.SZ"])
            elif symbol.startswith(("0", "3")):
                candidates.extend([f"{symbol}.SZ", f"{symbol}.SS"])
        if 4 <= len(symbol) <= 5:
            candidates.append(f"{symbol.zfill(4)}.HK")
        candidates.append(symbol)
        return list(dict.fromkeys(candidates))
    return [symbol]


def contains_cjk(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def market_ticker_from_tencent_code(code: str, raw_symbol: str) -> str:
    lower = code.lower()
    if lower.startswith("sh"):
        return f"{raw_symbol}.SS"
    if lower.startswith("sz"):
        return f"{raw_symbol}.SZ"
    if lower.startswith("hk"):
        return f"{raw_symbol.zfill(4)}.HK"
    if lower.startswith("us"):
        return raw_symbol.upper()
    return raw_symbol.upper()


def canonical_to_runtime_ticker(canonical_code: str) -> str:
    if canonical_code.endswith(".SH"):
        return canonical_code[:-3] + ".SS"
    return canonical_code


@lru_cache(maxsize=1)
def load_stock_index() -> List[Dict[str, Any]]:
    path = Path(__file__).resolve().parents[2] / "web" / "public" / "stocks.index.json"
    if not path.exists():
        return []
    try:
        raw_items = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.info("Could not load stock index from %s", path, exc_info=True)
        return []
    items: List[Dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, list) or len(item) < 9:
            continue
        aliases = item[5] if isinstance(item[5], list) else []
        items.append(
            {
                "canonical": str(item[0]),
                "display": str(item[1]),
                "name": str(item[2]),
                "pinyin": str(item[3] or ""),
                "pinyin_abbr": str(item[4] or ""),
                "aliases": [str(alias) for alias in aliases],
                "market": str(item[6]),
                "active": bool(item[8]),
                "popularity": int(item[9] or 0) if len(item) > 9 else 0,
            }
        )
    return items


def stock_index_score(query: str, item: Dict[str, Any]) -> int:
    q = query.strip().lower()
    if not q:
        return 0
    fields = {
        "canonical": item["canonical"].lower(),
        "display": item["display"].lower(),
        "name": item["name"].lower(),
        "pinyin": item["pinyin"].lower(),
        "pinyin_abbr": item["pinyin_abbr"].lower(),
    }
    aliases = [alias.lower() for alias in item.get("aliases", [])]
    if q in (fields["canonical"], fields["display"], fields["name"]):
        return 100
    if q == fields["pinyin_abbr"] or q in aliases:
        return 96
    if fields["display"].startswith(q):
        return 90
    if fields["name"].startswith(q):
        return 88
    if fields["pinyin_abbr"].startswith(q):
        return 86
    if fields["pinyin"].startswith(q):
        return 84
    if any(alias.startswith(q) for alias in aliases):
        return 82
    if q in fields["display"]:
        return 70
    if q in fields["name"]:
        return 68
    if q in fields["pinyin"]:
        return 66
    if any(q in alias for alias in aliases):
        return 64
    return 0


def search_stock_index(query: str, limit: int = 8) -> List[Dict[str, Optional[str]]]:
    scored = []
    for item in load_stock_index():
        if not item.get("active"):
            continue
        score = stock_index_score(query, item)
        if score <= 0:
            continue
        scored.append((score, int(item.get("popularity") or 0), item))
    scored.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    suggestions: List[Dict[str, Optional[str]]] = []
    for _, _, item in scored[:limit]:
        suggestions.append(
            {
                "ticker": canonical_to_runtime_ticker(item["canonical"]),
                "code": item["display"],
                "company_name": item["name"],
                "market": item["market"],
            }
        )
    return suggestions


def resolve_chinese_company_profile(ticker: str) -> Optional[Dict[str, Optional[str]]]:
    symbol = normalize_ticker_code(ticker)
    if not symbol:
        return None
    indexed = search_stock_index(symbol, limit=1)
    if indexed:
        return indexed[0]
    try:
        url = f"https://smartbox.gtimg.cn/s3/?q={quote(symbol)}"
        with urlopen(url, timeout=3) as response:
            text = response.read().decode("gbk", errors="ignore")
        _, _, payload = text.partition('"')
        payload, _, _ = payload.partition('"')
        for item in payload.split("^"):
            parts = item.split("~")
            if len(parts) < 3:
                continue
            code, name, raw_symbol = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if not name or not contains_cjk(name):
                continue
            return {
                "ticker": market_ticker_from_tencent_code(code, raw_symbol or symbol),
                "company_name": name,
                "market": code[:2].upper() if code else None,
            }
    except Exception:
        logger.info("Could not resolve Chinese company profile for %s", symbol, exc_info=True)
    return None


def search_company_profiles(query: str, limit: int = 8) -> List[Dict[str, Optional[str]]]:
    cleaned = query.strip()
    if not cleaned:
        return []
    alias_hits = [
        {
            "ticker": value["ticker"],
            "code": normalize_ticker_code(value["ticker"]),
            "company_name": value["company_name"],
            "market": value["market"],
        }
        for alias, value in COMMON_COMPANY_ALIASES.items()
        if cleaned.lower() in alias.lower() or alias.lower() in cleaned.lower()
    ]
    indexed = search_stock_index(cleaned, limit=limit)
    merged: List[Dict[str, Optional[str]]] = []
    seen: set[str] = set()
    for item in alias_hits + indexed:
        ticker = item.get("ticker") or ""
        if ticker in seen:
            continue
        seen.add(ticker)
        merged.append(item)
        if len(merged) >= limit:
            return merged
    if merged:
        return merged
    try:
        url = f"https://smartbox.gtimg.cn/s3/?q={quote(cleaned)}"
        with urlopen(url, timeout=3) as response:
            text = response.read().decode("gbk", errors="ignore")
        _, _, payload = text.partition('"')
        payload, _, _ = payload.partition('"')
        suggestions: List[Dict[str, Optional[str]]] = []
        seen: set[str] = set()
        for item in payload.split("^"):
            parts = item.split("~")
            if len(parts) < 3:
                continue
            code, name, raw_symbol = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if not code or not name or not raw_symbol:
                continue
            ticker = market_ticker_from_tencent_code(code, raw_symbol)
            if ticker in seen:
                continue
            seen.add(ticker)
            suggestions.append(
                {
                    "ticker": ticker,
                    "code": normalize_ticker_code(raw_symbol),
                    "company_name": name,
                    "market": code[:2].upper() if code else None,
                }
            )
            if len(suggestions) >= limit:
                break
        return suggestions
    except Exception:
        logger.info("Could not search company profiles for %s", cleaned, exc_info=True)
        return []


def resolve_company_profile(ticker: str) -> Dict[str, Optional[str]]:
    candidates = candidate_ticker_symbols(ticker)
    if not candidates:
        return {"ticker": None, "company_name": None, "market": None}
    chinese_profile = resolve_chinese_company_profile(ticker)
    if chinese_profile and chinese_profile.get("company_name"):
        return chinese_profile
    try:
        import yfinance as yf
    except Exception:
        logger.info("Could not import yfinance for company profile lookup", exc_info=True)
        return {"ticker": candidates[0], "company_name": None, "market": None}

    for symbol in candidates:
        try:
            ticker_obj = yf.Ticker(symbol)
            if hasattr(ticker_obj, "get_info"):
                info = ticker_obj.get_info()
            else:
                info = ticker_obj.info
            if not isinstance(info, dict):
                continue
            name = None
            for key in ("longName", "shortName", "displayName"):
                value = info.get(key)
                if isinstance(value, str) and value.strip() and value.strip().upper() != symbol:
                    name = value.strip()
                    break
            if name:
                market = info.get("exchange") or info.get("market") or info.get("fullExchangeName")
                return {
                    "ticker": symbol,
                    "company_name": name,
                    "market": str(market).strip() if market else None,
                }
        except Exception:
            logger.info("Could not resolve company profile for %s", symbol, exc_info=True)
    return {"ticker": candidates[0], "company_name": None, "market": None}


def resolve_company_name(ticker: str) -> Optional[str]:
    return resolve_company_profile(ticker)["company_name"]


def resolve_ticker_symbol(ticker: str) -> Optional[str]:
    profile = resolve_company_profile(ticker)
    resolved = profile.get("ticker")
    if resolved:
        return resolved
    candidates = candidate_ticker_symbols(ticker)
    if candidates:
        return candidates[0]
    return None


def get_masked_api_keys() -> Dict[str, str]:
    return {
        provider: mask_secret(os.environ.get(env_name, ""))
        for provider, env_name in API_KEY_ENV_BY_PROVIDER.items()
    }


def set_api_key(provider: str, value: str) -> Dict[str, str]:
    provider_key = provider.strip().lower()
    env_name = API_KEY_ENV_BY_PROVIDER.get(provider_key)
    if not env_name:
        raise KeyError(provider_key)
    os.environ[env_name] = value.strip()
    return {"provider": provider_key, "masked": mask_secret(os.environ[env_name])}


def summarize_run_event(
    *,
    run_id: str,
    event_type: str,
    agent: Optional[str] = None,
    status: Optional[str] = None,
    content: Optional[str] = None,
    section: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": f"evt_{uuid.uuid4().hex}",
        "runId": run_id,
        "type": event_type,
        "agent": agent,
        "status": status,
        "section": section,
        "content": content,
        "payload": payload or {},
        "createdAt": now_iso(),
    }


def extract_content_string(content: Any) -> Optional[str]:
    if content is None:
        return None
    if isinstance(content, str):
        cleaned = content.strip()
        return cleaned or None
    if isinstance(content, dict):
        text = content.get("text")
        return extract_content_string(text)
    if isinstance(content, list):
        parts = [extract_content_string(item) for item in content]
        cleaned = " ".join(part for part in parts if part)
        return cleaned or None
    cleaned = str(content).strip()
    return cleaned or None


def chunk_to_run_events(run_id: str, chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    for message in chunk.get("messages", []) or []:
        content = extract_content_string(getattr(message, "content", None))
        message_id = getattr(message, "id", None)
        if content:
            events.append(
                summarize_run_event(
                    run_id=run_id,
                    event_type="message",
                    content=content,
                    payload={"messageType": message.__class__.__name__, "messageId": message_id},
                )
            )
        for tool_call in getattr(message, "tool_calls", []) or []:
            if isinstance(tool_call, dict):
                name = tool_call.get("name", "tool")
                args = tool_call.get("args", {})
            else:
                name = getattr(tool_call, "name", "tool")
                args = getattr(tool_call, "args", {})
            events.append(
                summarize_run_event(
                    run_id=run_id,
                    event_type="tool_call",
                    content=name,
                    payload={"args": args},
                )
            )

    direct_reports = {
        "market_report": "Market Analyst",
        "sentiment_report": "Social Analyst",
        "news_report": "News Analyst",
        "fundamentals_report": "Fundamentals Analyst",
        "trader_investment_plan": "Trader",
    }
    for section, agent in direct_reports.items():
        content = extract_content_string(chunk.get(section))
        if content:
            events.append(
                summarize_run_event(
                    run_id=run_id,
                    event_type="report",
                    agent=agent,
                    status="completed",
                    section=section,
                    content=content,
                )
            )

    debate_state = chunk.get("investment_debate_state") or {}
    investment_reports = [
        ("bull_history", "bull_researcher", "Bull Researcher"),
        ("bear_history", "bear_researcher", "Bear Researcher"),
        ("judge_decision", "research_manager", "Research Manager"),
    ]
    for key, section, agent in investment_reports:
        content = extract_content_string(debate_state.get(key))
        if content:
            events.append(
                summarize_run_event(
                    run_id=run_id,
                    event_type="report",
                    agent=agent,
                    status="completed",
                    section=section,
                    content=f"### {agent_display_name(agent)}\n{content}",
                )
            )

    risk_state = chunk.get("risk_debate_state") or {}
    risk_reports = [
        ("aggressive_history", "aggressive_analyst", "Aggressive Analyst"),
        ("neutral_history", "neutral_analyst", "Neutral Analyst"),
        ("conservative_history", "conservative_analyst", "Conservative Analyst"),
        ("judge_decision", "portfolio_manager", "Portfolio Manager"),
    ]
    for key, section, agent in risk_reports:
        content = extract_content_string(risk_state.get(key))
        if content:
            events.append(
                summarize_run_event(
                    run_id=run_id,
                    event_type="report",
                    agent=agent,
                    status="completed",
                    section=section,
                    content=f"### {agent_display_name(agent)}\n{content}",
                )
            )

    final_decision = extract_content_string(chunk.get("final_trade_decision"))
    if final_decision:
        events.append(
            summarize_run_event(
                run_id=run_id,
                event_type="decision",
                agent="Portfolio Manager",
                status="completed",
                content=final_decision,
                payload={"action": final_decision},
            )
        )

    return events


def event_fingerprint(event: Dict[str, Any]) -> str:
    event_type = event.get("type", "")
    payload = event.get("payload") or {}
    if event_type == "message" and payload.get("messageId"):
        return f"message:{payload['messageId']}"
    if event_type == "tool_call":
        return f"tool_call:{event.get('content')}:{payload.get('args')}"
    if event_type in {"report", "decision"}:
        return f"{event_type}:{event.get('section')}:{event.get('agent')}:{event.get('content')}"
    return f"{event_type}:{event.get('status')}:{event.get('content')}"


def create_run_summary(request: AnalysisRequest) -> Dict[str, Any]:
    timestamp = now_iso()
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    return {
        "id": run_id,
        "ticker": request.ticker,
        "company_name": request.company_name,
        "analysis_date": request.analysis_date,
        "status": "queued",
        "created_at": timestamp,
        "updated_at": timestamp,
        "decision": None,
        "title": f"{request.ticker} 研究 - {request.analysis_date}",
    }


def iter_mock_research_events(run_id: str, request: AnalysisRequest) -> Iterable[Dict[str, Any]]:
    delay = mock_step_delay()
    analyst_labels = {
        "market": "Market Analyst",
        "social": "Social Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }
    yield summarize_run_event(
        run_id=run_id,
        event_type="run_status",
        status="running",
        content=f"已开始研究 {request.ticker}",
    )
    for key in request.analysts:
        agent = analyst_labels[key]
        yield summarize_run_event(run_id=run_id, event_type="agent_status", agent=agent, status="running")
        time.sleep(delay)
        yield summarize_run_event(
            run_id=run_id,
            event_type="report",
            agent=agent,
            status="completed",
            section=f"{key}_report",
            content=(
                f"### {agent_display_name(agent)}\n"
                f"{request.ticker} 在演示流中呈现相对均衡的结构。"
                "配置模型密钥并关闭演示流后，可运行完整的 TradingAgents 图流程。"
            ),
        )

    for round_index in range(1, request.research_depth + 1):
        debate = [
            (
                "Bull Researcher",
                "bull_researcher",
                f"第 {round_index} 轮多头观点：关注趋势延续、需求韧性和资金面改善，并寻找能够支撑估值继续扩张的催化因素。",
            ),
            (
                "Bear Researcher",
                "bear_researcher",
                f"第 {round_index} 轮空头观点：重新审视估值压力、事件风险和宏观敏感性，要求多头证明安全边际足够充分。",
            ),
            (
                "Research Manager",
                "research_manager",
                f"第 {round_index} 轮研究经理总结：多空证据仍需交叉验证，当前更适合保留弹性仓位并等待更明确的确认信号。",
            ),
        ]
        for agent, section, content in debate:
            yield summarize_run_event(run_id=run_id, event_type="agent_status", agent=agent, status="running")
            time.sleep(delay)
            yield summarize_run_event(
                run_id=run_id,
                event_type="report",
                agent=agent,
                status="completed",
                section=f"{section}_round_{round_index}",
                content=f"### {agent_display_name(agent)} · 第 {round_index} 轮\n{content}",
            )

    yield summarize_run_event(run_id=run_id, event_type="agent_status", agent="Trader", status="running")
    time.sleep(delay)
    yield summarize_run_event(
        run_id=run_id,
        event_type="report",
        agent="Trader",
        status="completed",
        section="trader_plan",
        content="### 交易员\n建议计划：等待确认信号，控制仓位，并在入场前定义失效条件。",
    )

    for round_index in range(1, request.research_depth + 1):
        risk_debate = [
            (
                "Aggressive Analyst",
                "aggressive_analyst",
                f"第 {round_index} 轮进取型风控：若价格突破关键阻力，可接受小幅提高风险预算，但必须配合止损。",
            ),
            (
                "Neutral Analyst",
                "neutral_analyst",
                f"第 {round_index} 轮中性风控：建议等待成交量和基本面催化同步确认，再扩大暴露。",
            ),
            (
                "Conservative Analyst",
                "conservative_analyst",
                f"第 {round_index} 轮保守型风控：在不确定性没有下降前，应限制仓位并优先保护本金。",
            ),
            (
                "Portfolio Manager",
                "portfolio_manager",
                f"第 {round_index} 轮组合经理裁决：维持持有 / 观察，风险预算保持有限，等待更高置信度信号。",
            ),
        ]
        for agent, section, content in risk_debate:
            yield summarize_run_event(run_id=run_id, event_type="agent_status", agent=agent, status="running")
            time.sleep(delay)
            yield summarize_run_event(
                run_id=run_id,
                event_type="report",
                agent=agent,
                status="completed",
                section=f"{section}_round_{round_index}",
                content=f"### {agent_display_name(agent)} · 第 {round_index} 轮\n{content}",
            )

    yield summarize_run_event(
        run_id=run_id,
        event_type="decision",
        agent="Portfolio Manager",
        status="completed",
        content="持有 / 观察",
        payload={"action": "持有", "confidence": 0.62, "risk": "中等"},
    )
    yield summarize_run_event(run_id=run_id, event_type="run_status", status="completed")


def iter_live_research_events(
    run_id: str,
    request: AnalysisRequest,
    settings: SettingsPayload,
) -> Iterable[Dict[str, Any]]:
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.graph.checkpointer import thread_id

    config = build_effective_config(settings)
    config["max_debate_rounds"] = request.research_depth
    config["max_risk_discuss_rounds"] = request.research_depth
    config["output_language"] = request.output_language
    config["checkpoint_enabled"] = request.checkpoint_enabled

    yield summarize_run_event(
        run_id=run_id,
        event_type="run_status",
        status="running",
        content=f"已启动 {request.ticker} 的 TradingAgents 实时图流程",
    )

    graph = TradingAgentsGraph(
        selected_analysts=request.analysts,
        config=config,
        debug=False,
    )
    init_agent_state = graph.propagator.create_initial_state(
        request.ticker,
        request.analysis_date,
        past_context=graph.memory_log.get_past_context(request.ticker),
    )
    args = graph.propagator.get_graph_args()
    if request.checkpoint_enabled:
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread_id(
            request.ticker,
            request.analysis_date,
        )

    final_state: Optional[Dict[str, Any]] = None
    emitted_events: set[str] = set()
    for chunk in graph.graph.stream(init_agent_state, **args):
        final_state = chunk
        for event in chunk_to_run_events(run_id, chunk):
            fingerprint = event_fingerprint(event)
            if fingerprint in emitted_events:
                continue
            emitted_events.add(fingerprint)
            yield event

    if final_state and final_state.get("final_trade_decision"):
        decision = graph.process_signal(final_state["final_trade_decision"])
        yield summarize_run_event(
            run_id=run_id,
            event_type="decision",
            agent="Portfolio Manager",
            status="completed",
            content=str(decision),
            payload={"action": str(decision)},
        )

    yield summarize_run_event(run_id=run_id, event_type="run_status", status="completed")


def iter_research_events(
    run_id: str,
    request: AnalysisRequest,
    settings: SettingsPayload,
) -> Iterable[Dict[str, Any]]:
    if request.use_mock_stream:
        yield from iter_mock_research_events(run_id, request)
        return

    try:
        yield from iter_live_research_events(run_id, request, settings)
    except Exception as exc:
        logger.exception("TradingAgents live run failed for %s", request.ticker)
        yield summarize_run_event(
            run_id=run_id,
            event_type="run_status",
            status="failed",
            content=f"{exc.__class__.__name__}: {exc}",
            payload={"error": str(exc)},
        )
