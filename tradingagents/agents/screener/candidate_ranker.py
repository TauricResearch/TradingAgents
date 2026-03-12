"""LLM-based candidate ranking for swing trading.

After technical + fundamental screening narrows candidates to ~10-20 stocks,
this ranker uses an LLM to rank them by swing trade attractiveness.
"""

import json
import logging

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)


def create_candidate_ranker(llm: ChatOpenAI):
    """Create a candidate ranking function bound to an LLM.

    Args:
        llm: LLM instance for ranking evaluation

    Returns:
        Callable that ranks candidates
    """

    def rank_candidates(
        candidates: list[dict],
        portfolio_context: str = "",
        max_candidates: int = 5,
    ) -> list[dict]:
        """Rank and select top swing trading candidates using LLM.

        Args:
            candidates: Filtered candidates from screeners
            portfolio_context: Current portfolio summary
            max_candidates: Maximum candidates to return

        Returns:
            Ranked list of top candidates with LLM reasoning
        """
        if not candidates:
            return []

        if len(candidates) <= max_candidates:
            return candidates

        # Prepare candidate summaries for LLM
        candidate_summaries = []
        for i, c in enumerate(candidates):
            summary = (
                f"[{i + 1}] {c['ticker']} ({c['name']})\n"
                f"  시장: {c['market']}\n"
                f"  기술적 신호: {', '.join(c['signals'])}\n"
                f"  펀더멘탈: {c.get('fundamental_check', 'N/A')}\n"
            )

            # Add key indicators if available
            ind = c.get("indicators", {})
            if ind:
                price = ind.get("current_price", "N/A")
                rsi = ind.get("rsi", "N/A")
                vol_ratio = ind.get("volume_ratio", "N/A")
                if isinstance(rsi, float):
                    rsi = f"{rsi:.1f}"
                if isinstance(vol_ratio, float):
                    vol_ratio = f"{vol_ratio:.1f}x"
                summary += (
                    f"  현재가: {price} / RSI: {rsi} / 거래량 비율: {vol_ratio}\n"
                )

            candidate_summaries.append(summary)

        candidates_text = "\n".join(candidate_summaries)

        system_prompt = f"""너는 스윙 트레이딩 종목 선정 전문가다.
아래 스크리닝을 통과한 후보 종목들을 스윙 트레이딩 매력도 기준으로 상위 {max_candidates}개를 선정하라.

평가 기준:
1. 기술적 신호의 강도 및 복합성 (여러 신호가 겹칠수록 강함)
2. 스윙 트레이딩에 적합한 변동성과 유동성
3. 펀더멘탈 건전성 (안전장치)
4. 현재 포트폴리오와의 분산 효과

반드시 아래 JSON 형식만 출력하라. 다른 텍스트는 절대 출력하지 마라.
{{"selected": [번호1, 번호2, ...], "reasoning": "선정 이유 한 줄 요약"}}
"""

        messages = [
            ("system", system_prompt),
            ("human", f"포트폴리오 현황:\n{portfolio_context}\n\n후보 종목:\n{candidates_text}"),
        ]

        try:
            response = llm.invoke(messages).content
            parsed = json.loads(response)
            selected_indices = parsed.get("selected", [])
            reasoning = parsed.get("reasoning", "")

            ranked = []
            for idx in selected_indices:
                actual_idx = idx - 1  # 1-indexed in prompt
                if 0 <= actual_idx < len(candidates):
                    c = candidates[actual_idx]
                    c["ranking_reason"] = reasoning
                    ranked.append(c)

            if ranked:
                return ranked[:max_candidates]

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"LLM ranking parse error: {e}, returning top by signal count")

        # Fallback: return top by signal count
        return candidates[:max_candidates]

    return rank_candidates
