from langchain_core.messages import HumanMessage, RemoveMessage
import re

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a prompt instruction for the configured output language.

    Returns empty string when English (default), so no extra tokens are used.
    Only applied to user-facing agents (analysts, portfolio manager).
    Internal debate agents stay in English for reasoning quality.
    """
    from tradingagents.dataflows.config import get_config
    lang = get_config().get("output_language", "English")
    if lang.strip().lower() == "english":
        return ""
    return f" Write your entire response in {lang}."


def get_output_language() -> str:
    from tradingagents.dataflows.config import get_config

    return get_config().get("output_language", "English")


def _is_chinese_output() -> bool:
    return get_output_language().strip().lower() in {"chinese", "中文", "zh", "zh-cn", "zh-hans"}


def truncate_for_prompt(
    text: str,
    limit_key: str = "report_context_char_limit",
    default_limit: int = 16000,
) -> str:
    """Trim long context text to keep prompts within a stable token budget."""
    if not text:
        return ""

    from tradingagents.dataflows.config import get_config

    cfg = get_config()
    limit = int(cfg.get(limit_key, default_limit) or default_limit)
    if limit <= 0 or len(text) <= limit:
        return text

    omitted = len(text) - limit
    return f"[Content trimmed, omitted {omitted} characters]\n{text[-limit:]}"


def get_snapshot_template() -> str:
    if _is_chinese_output():
        return """反馈快照:
- 当前观点:
- 发生了什么变化:
- 为什么变化:
- 关键反驳:
- 下一轮教训:"""

    return """FEEDBACK SNAPSHOT:
- Current thesis:
- What changed:
- Why it changed:
- Key rebuttal:
- Lesson for next round:"""


def get_snapshot_writing_instruction() -> str:
    if _is_chinese_output():
        return (
            "反馈快照中的每一项都必须填写具体内容，直接总结本轮新增观点、证据、反驳和下一轮要验证的点。"
            "禁止填写“未明确说明”“暂无”“同上”“无变化”这类占位语。"
        )
    return (
        "Every field in the feedback snapshot must contain concrete content grounded in this round's argument, "
        "including what changed, why it changed, the key rebuttal, and what to verify next round. "
        "Do not use placeholders like 'not specified', 'none', 'same as above', or 'no change'."
    )


def localize_label(english: str, chinese: str) -> str:
    return chinese if _is_chinese_output() else english


def localize_role_name(role: str) -> str:
    mapping = {
        "Bull Analyst": "多头分析师",
        "Bear Analyst": "空头分析师",
        "Aggressive Analyst": "激进分析师",
        "Conservative Analyst": "保守分析师",
        "Neutral Analyst": "中性分析师",
        "Portfolio Manager": "投资组合经理",
        "Research Manager": "研究经理",
        "Trader": "交易员",
        "Judge": "裁决者",
    }
    return mapping.get(role, role) if _is_chinese_output() else role


def normalize_chinese_role_terms(text: str) -> str:
    """Normalize user-facing Chinese role terms to a single preferred wording."""
    if not text:
        return ""

    replacements = {
        "熊派分析师": "空头分析师",
        "熊派投资者": "空头投资者",
        "熊观点": "空头观点",
        "熊派": "空头",
        "牛派分析师": "多头分析师",
        "牛派投资者": "多头投资者",
        "牛观点": "多头观点",
        "牛派": "多头",
    }
    normalized = text
    for src, dst in replacements.items():
        normalized = normalized.replace(src, dst)
    return normalized


def localize_rating_term(term: str) -> str:
    mapping = {
        "Buy": "买入",
        "Overweight": "增持",
        "Hold": "持有",
        "Underweight": "减持",
        "Sell": "卖出",
        "BUY": "买入",
        "HOLD": "持有",
        "SELL": "卖出",
    }
    return mapping.get(term, term) if _is_chinese_output() else term


def get_localized_rating_scale() -> str:
    if _is_chinese_output():
        return """**评级体系**（只能选择一个）:
- **买入**: 对开仓或加仓有很强信心
- **增持**: 前景偏积极，建议逐步提高仓位
- **持有**: 维持当前仓位，暂不动作
- **减持**: 降低敞口，分批止盈或收缩仓位
- **卖出**: 退出仓位或避免入场"""

    return """**Rating Scale** (use exactly one):
- **Buy**: Strong conviction to enter or add to position
- **Overweight**: Favorable outlook, gradually increase exposure
- **Hold**: Maintain current position, no action needed
- **Underweight**: Reduce exposure, take partial profits
- **Sell**: Exit position or avoid entry"""


def get_localized_final_proposal_instruction() -> str:
    if _is_chinese_output():
        return (
            "End with a firm decision and present the user-facing conclusion as "
            "'最终交易建议: **买入/持有/卖出**'. For machine compatibility, you may optionally append a separate final line "
            "using the internal token 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' only when needed."
        )
    return (
        "End with a firm decision and always conclude your response with "
        "'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**' to confirm your recommendation."
    )


def get_collaboration_stop_instruction() -> str:
    if _is_chinese_output():
        return (
            " If you or another assistant has already reached a final deliverable, prefer the user-facing line "
            "'最终交易建议: **买入/持有/卖出**'. Only when a machine-readable stop signal is necessary, append an extra final line "
            "with the internal token 'FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**'."
        )
    return (
        " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
        " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
    )


SNAPSHOT_MARKERS = ("FEEDBACK SNAPSHOT:", "反馈快照:")
SNAPSHOT_TEMPLATE = get_snapshot_template()


def _condense_excerpt(text: str, limit: int = 120) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _get_rating_patterns() -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("买入", ("最终交易建议: **买入**", "评级: 买入", "建议买入", "维持买入", "转为买入", "买入")),
        ("增持", ("最终交易建议: **增持**", "评级: 增持", "建议增持", "维持增持", "转为增持", "增持")),
        ("持有", ("最终交易建议: **持有**", "评级: 持有", "建议持有", "维持持有", "转为持有", "持有")),
        ("减持", ("最终交易建议: **减持**", "评级: 减持", "建议减持", "维持减持", "转为减持", "减持")),
        ("卖出", ("最终交易建议: **卖出**", "评级: 卖出", "建议卖出", "维持卖出", "转为卖出", "卖出")),
    ]


def _detect_chinese_rating(text: str) -> str:
    content = normalize_chinese_role_terms(text or "")
    if not content.strip():
        return "持有"

    for rating, patterns in _get_rating_patterns():
        for pattern in patterns:
            if pattern in content:
                return rating

    heuristic_patterns = [
        ("卖出", ("清仓", "退出", "避免入场", "止损离场", "果断卖出")),
        ("减持", ("降低仓位", "分批止盈", "降低敞口", "部分卖出", "先减仓")),
        ("增持", ("加仓", "提高仓位", "逢低布局", "继续增持", "扩大仓位")),
        ("买入", ("买入机会", "积极布局", "值得买入", "坚定看多", "继续买入")),
        ("持有", ("继续观察", "暂不动作", "维持仓位", "等待确认", "持仓观望")),
    ]
    for rating, patterns in heuristic_patterns:
        if any(pattern in content for pattern in patterns):
            return rating

    return "持有"


def _detect_english_rating(text: str) -> str:
    content = (text or "").lower()
    if not content.strip():
        return "HOLD"

    explicit_patterns = [
        ("SELL", ("final transaction proposal: **sell**", "rating: sell", "recommend sell")),
        ("UNDERWEIGHT", ("final transaction proposal: **underweight**", "rating: underweight", "recommend underweight")),
        ("HOLD", ("final transaction proposal: **hold**", "rating: hold", "recommend hold")),
        ("OVERWEIGHT", ("final transaction proposal: **overweight**", "rating: overweight", "recommend overweight")),
        ("BUY", ("final transaction proposal: **buy**", "rating: buy", "recommend buy")),
    ]
    for rating, patterns in explicit_patterns:
        if any(pattern in content for pattern in patterns):
            return rating

    heuristic_patterns = [
        ("SELL", ("exit position", "avoid entry", "sell the stock", "close the position")),
        ("UNDERWEIGHT", ("reduce exposure", "trim the position", "take partial profits")),
        ("OVERWEIGHT", ("add to position", "increase exposure", "build the position")),
        ("BUY", ("buy the stock", "enter the position", "strong upside")),
        ("HOLD", ("maintain the position", "wait for confirmation", "stay on hold")),
    ]
    for rating, patterns in heuristic_patterns:
        if any(pattern in content for pattern in patterns):
            return rating

    return "HOLD"


def _extract_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[。！？!?\.])\s+|\n+", compact)
    return [part.strip() for part in parts if part.strip()]


def _contains_placeholder_snapshot(snapshot: str) -> bool:
    placeholders = (
        "未明确说明",
        "暂无",
        "同上",
        "无变化",
        "Not explicitly stated",
        "None yet",
        "same as above",
        "no change",
    )
    return any(token in snapshot for token in placeholders)


def _snapshot_field_labels() -> list[str]:
    if _is_chinese_output():
        return ["当前观点", "发生了什么变化", "为什么变化", "关键反驳", "下一轮教训"]
    return [
        "Current thesis",
        "What changed",
        "Why it changed",
        "Key rebuttal",
        "Lesson for next round",
    ]


def _snapshot_field_aliases() -> dict[str, tuple[str, ...]]:
    return {
        "current_thesis": ("当前观点", "Current thesis"),
        "what_changed": ("发生了什么变化", "What changed"),
        "why_changed": ("为什么变化", "Why it changed"),
        "key_rebuttal": ("关键反驳", "Key rebuttal"),
        "lesson_next_round": ("下一轮教训", "Lesson for next round"),
    }


def _parse_snapshot_fields(snapshot: str) -> dict[str, str]:
    fields = {key: "" for key in _snapshot_field_aliases()}
    if not snapshot:
        return fields

    for line in snapshot.splitlines():
        stripped = line.strip()
        matched = False
        for field_key, aliases in _snapshot_field_aliases().items():
            for label in aliases:
                prefix = f"- {label}:"
                if stripped.startswith(prefix):
                    fields[field_key] = stripped[len(prefix):].strip()
                    matched = True
                    break
            if matched:
                break
    return fields


def _snapshot_has_missing_fields(snapshot: str) -> bool:
    fields = _parse_snapshot_fields(snapshot)
    for value in fields.values():
        normalized = value.strip()
        if not normalized:
            return True
        if normalized in {"。", ".", "...", "……", "-", "--"}:
            return True
    return False


def _merge_snapshot_with_inferred(snapshot: str, inferred_snapshot: str) -> str:
    explicit = _parse_snapshot_fields(snapshot)
    inferred = _parse_snapshot_fields(inferred_snapshot)

    lines = [SNAPSHOT_MARKERS[1] if _is_chinese_output() else SNAPSHOT_MARKERS[0]]
    display_labels = _snapshot_field_labels()
    for field_key, label in zip(_snapshot_field_aliases().keys(), display_labels):
        value = explicit.get(field_key, "").strip()
        if not value or value in {"。", ".", "...", "……", "-", "--"}:
            value = inferred.get(field_key, "").strip()
        lines.append(f"- {label}: {value}")
    return "\n".join(lines)


def is_feedback_snapshot_inferred(text: str) -> bool:
    """Return True when the displayed snapshot will be inferred from the body."""
    if not text or not text.strip():
        return True

    for marker in SNAPSHOT_MARKERS:
        idx = text.rfind(marker)
        if idx != -1:
            snapshot = text[idx:].strip()
            return _contains_placeholder_snapshot(snapshot) or _snapshot_has_missing_fields(snapshot)
    return True


def _infer_feedback_snapshot_from_body(text: str) -> str:
    body = normalize_chinese_role_terms(strip_feedback_snapshot(text))
    sentences = _extract_sentences(body)
    first = _condense_excerpt(sentences[0], 120) if sentences else _condense_excerpt(body, 120)
    second = _condense_excerpt(sentences[1], 120) if len(sentences) > 1 else first
    third = _condense_excerpt(sentences[2], 120) if len(sentences) > 2 else second

    if _is_chinese_output():
        rating = _detect_chinese_rating(text)
        current = rating
        changed = (
            second if len(sentences) > 1 else f"本轮围绕“{rating}”补充了更明确的交易依据、风险边界和执行条件。"
        )
        why = (
            third if len(sentences) > 2 else f"变化来自本轮新增的数据证据、市场信号和对手论点带来的判断修正。"
        )
        rebuttal_source = next(
            (s for s in sentences if any(word in s for word in ("但", "然而", "不过", "反驳", "忽略", "高估"))),
            second or f"本轮核心反驳集中在对手忽略了影响“{rating}”判断的关键数据或风险约束。",
        )
        lesson_source = next(
            (s for s in sentences if any(word in s for word in ("需要", "继续", "监控", "跟踪", "等待", "验证", "警惕"))),
            f"下一轮需要继续验证支持“{rating}”结论的关键数据、风险触发条件和执行时点。",
        )
        return (
            "反馈快照:\n"
            f"- 当前观点: {current}\n"
            f"- 发生了什么变化: {changed}\n"
            f"- 为什么变化: {why}\n"
            f"- 关键反驳: {rebuttal_source}\n"
            f"- 下一轮教训: {lesson_source}"
        )

    rating = _detect_english_rating(text)
    current = rating
    changed = second if len(sentences) > 1 else f"This round added clearer trading evidence, risk boundaries, and execution conditions behind the {rating} call."
    why = third if len(sentences) > 2 else "The update came from new evidence, market signals, and adjustments prompted by the opponent's latest claims."
    rebuttal_source = next(
        (s for s in sentences if any(word in s.lower() for word in ("but", "however", "rebut", "weakness", "risk", "miss"))),
        second or f"The key rebuttal is that the opposing case missed the main evidence or risk controls behind the {rating} stance.",
    )
    lesson_source = next(
        (s for s in sentences if any(word in s.lower() for word in ("monitor", "watch", "verify", "track", "wait", "risk"))),
        f"Next round should verify the core data assumptions, risk triggers, and timing conditions behind the {rating} stance.",
    )
    return (
        "FEEDBACK SNAPSHOT:\n"
        f"- Current thesis: {current}\n"
        f"- What changed: {changed}\n"
        f"- Why it changed: {why}\n"
        f"- Key rebuttal: {rebuttal_source}\n"
        f"- Lesson for next round: {lesson_source}"
    )


def extract_feedback_snapshot(text: str) -> str:
    """Extract the structured feedback snapshot block from an agent response."""
    if not text:
        if _is_chinese_output():
            return "反馈快照:\n- 当前观点: 暂无。\n- 发生了什么变化: 暂无。\n- 为什么变化: 暂无。\n- 关键反驳: 暂无。\n- 下一轮教训: 暂无。"
        return "FEEDBACK SNAPSHOT:\n- Current thesis: None yet.\n- What changed: None yet.\n- Why it changed: None yet.\n- Key rebuttal: None yet.\n- Lesson for next round: None yet."

    for marker in SNAPSHOT_MARKERS:
        idx = text.rfind(marker)
        if idx != -1:
            snapshot = text[idx:].strip()
            if _contains_placeholder_snapshot(snapshot):
                return _infer_feedback_snapshot_from_body(text)
            normalized_snapshot = normalize_chinese_role_terms(snapshot)
            if _snapshot_has_missing_fields(normalized_snapshot):
                inferred_snapshot = _infer_feedback_snapshot_from_body(text)
                return _merge_snapshot_with_inferred(normalized_snapshot, inferred_snapshot)
            return normalized_snapshot

    return _infer_feedback_snapshot_from_body(text)


def strip_feedback_snapshot(text: str) -> str:
    """Remove the feedback snapshot block from the visible argument body."""
    if not text:
        return ""
    best_idx = -1
    for marker in SNAPSHOT_MARKERS:
        idx = text.rfind(marker)
        if idx > best_idx:
            best_idx = idx
    if best_idx == -1:
        return text.strip()
    return text[:best_idx].strip()


def build_debate_brief(snapshots: dict[str, str], latest_speaker: str = "") -> str:
    """Build a compact cross-agent brief from the latest structured snapshots."""
    sections = []
    if latest_speaker:
        if _is_chinese_output():
            sections.append(f"最新更新来自: {localize_role_name(latest_speaker)}")
        else:
            sections.append(f"Latest update came from: {latest_speaker}")

    for speaker, snapshot in snapshots.items():
        if snapshot:
            if _is_chinese_output():
                sections.append(f"{localize_role_name(speaker)} 最新快照:\n{snapshot}")
            else:
                sections.append(f"{speaker} latest snapshot:\n{snapshot}")

    return "\n\n".join(sections).strip()


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
