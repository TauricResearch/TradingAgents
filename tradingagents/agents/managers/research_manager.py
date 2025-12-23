# -*- coding: utf-8 -*-
import time
import json
import logging
import random
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from anthropic._exceptions import OverloadedError
from tradingagents.agents.utils.output_filter import fix_common_llm_errors, validate_and_warn
from tradingagents.agents.utils.prompts import get_research_manager_prompt

logger = logging.getLogger(__name__)


def create_research_manager(llm, memory, language: str = "zh-TW"):
    """
    建立一個研究管理員（裁判）節點。

    Args:
        llm: 用於生成決策和計畫的語言模型。
        memory: 儲存過去情況和反思的記憶體物件。
        language: 報告語言 ('en' 或 'zh-TW')

    Returns:
        function: 一個代表研究管理員節點的函式。
    """

    def research_manager_node(state) -> dict:
        """研究管理員節點的執行函式。"""
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        
        market_research_report = state["market_report"]
        sentiment_report = state["sentiment_report"]
        news_report = state["news_report"]
        fundamentals_report = state["fundamentals_report"]

        curr_situation = f"{market_research_report}\n\n{sentiment_report}\n\n{news_report}\n\n{fundamentals_report}"
        
        past_memories = memory.get_memories(curr_situation, n_matches=2)
        past_memory_str = ""
        for i, rec in enumerate(past_memories, 1):
            recommendation = rec["recommendation"]
            past_memory_str += recommendation + "\n\n"

        # Get language-specific prompt
        base_prompt = get_research_manager_prompt(language)
        
        if language == "en":
            prompt = f"""{base_prompt}

【Available Information】
- Past Reflections: "{past_memory_str}"
- Debate History: {history}

Please provide your investment decision report."""
        else:
            prompt = f"""{base_prompt}

【可用資訊】
- 過去反思："{past_memory_str}"
- 辯論歷史：{history}

請提供您的投資決策報告。"""
        
        @retry(
            retry=retry_if_exception_type(OverloadedError),
            wait=wait_exponential(multiplier=1, min=2, max=60),
            stop=stop_after_attempt(5),
            before_sleep=before_sleep_log(logger, logging.WARNING)
        )
        def invoke_llm_with_retry(llm_instance, prompt_text):
            jitter = random.uniform(0, 0.5)
            if jitter > 0:
                time.sleep(jitter)
            logger.info("正在調用 Research Manager LLM...")
            return llm_instance.invoke(prompt_text)
        
        response = invoke_llm_with_retry(llm, prompt)
        
        response.content = fix_common_llm_errors(response.content)
        validate_and_warn(response.content, "Research_Manager")

        new_investment_debate_state = {
            "judge_decision": response.content,
            "history": investment_debate_state.get("history", ""),
            "bear_history": investment_debate_state.get("bear_history", ""),
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": response.content,
            "count": investment_debate_state["count"],
        }

        return {
            "investment_debate_state": new_investment_debate_state,
            "investment_plan": response.content,
        }

    return research_manager_node