"""Extract structured chart annotations from AI analysis reports using a quick LLM call."""
import json
import logging

_logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Sen bir finansal analist asistanısın. Sana verilen analiz raporundan
sayısal fiyat seviyelerini çıkar ve YALNIZCA aşağıdaki JSON formatında yanıtla, başka hiçbir şey yazma:

{
  "support_levels": [sayı, sayı],
  "resistance_levels": [sayı, sayı],
  "target_price": sayı_veya_null,
  "stop_loss": sayı_veya_null,
  "key_levels": [
    {"price": sayı, "label": "kısa_açıklama", "type": "ma|indicator|other"}
  ]
}

Kurallar:
- En fazla 2-3 destek ve direnç seviyesi çıkar
- Fiyatlar yuvarlanmış olabilir — tam sayıya yakın değerleri temiz göster
- Belirsiz veya olmayan değerler için null kullan
- key_levels: hareketli ortalama, Bollinger bandı gibi teknik seviyeleri listele (maks 4 adet)
- Yalnızca raporda açıkça geçen sayısal değerleri kullan, tahmin etme"""


async def extract_chart_annotations(
    market_report: str,
    final_decision: str,
    quick_llm,
) -> dict:
    """Parse price levels from AI reports. Returns empty dict on any failure."""
    if not market_report and not final_decision:
        return {}

    # Truncate to avoid token overflow
    text = f"PIYASA RAPORU:\n{market_report[:2000]}\n\nSON KARAR:\n{final_decision[:1000]}"

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await _call_llm_async(quick_llm, text)
        raw = response.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        return _validate_annotations(data)

    except Exception as exc:
        _logger.debug("Annotation extraction failed (non-fatal): %s", exc)
        return {}


async def _call_llm_async(llm, text: str) -> str:
    """Call LLM in a thread pool to avoid blocking the event loop."""
    import asyncio
    from langchain_core.messages import HumanMessage, SystemMessage

    def _sync_call():
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=text),
        ]
        result = llm.invoke(messages)
        return result.content if hasattr(result, "content") else str(result)

    return await asyncio.to_thread(_sync_call)


def _validate_annotations(data: dict) -> dict:
    """Sanitize extracted annotation data — drop non-numeric values."""
    def _floats(lst) -> list[float]:
        if not isinstance(lst, list):
            return []
        return [round(float(x), 2) for x in lst if isinstance(x, (int, float)) and x > 0]

    def _float_or_none(val):
        try:
            v = float(val)
            return round(v, 2) if v > 0 else None
        except (TypeError, ValueError):
            return None

    key_levels = []
    for kl in data.get("key_levels") or []:
        if isinstance(kl, dict) and isinstance(kl.get("price"), (int, float)):
            key_levels.append({
                "price": round(float(kl["price"]), 2),
                "label": str(kl.get("label", ""))[:40],
                "type": str(kl.get("type", "other")),
            })

    return {
        "support_levels": _floats(data.get("support_levels")),
        "resistance_levels": _floats(data.get("resistance_levels")),
        "target_price": _float_or_none(data.get("target_price")),
        "stop_loss": _float_or_none(data.get("stop_loss")),
        "key_levels": key_levels[:4],
    }
