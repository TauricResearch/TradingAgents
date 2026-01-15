from typing import Dict, Any
import json
import os
from langchain_openai import ChatOpenAI
from tradingagents.utils.logger import app_logger as logger
from tradingagents.dataflows.config import get_config
from tradingagents.agents.utils.agent_utils import write_json_atomic

class Reflector:
    """Handles reflection on decisions and updating memory."""

    def __init__(self, quick_thinking_llm: ChatOpenAI):
        """Initialize the reflector with an LLM."""
        self.quick_thinking_llm = quick_thinking_llm
        self.reflection_system_prompt = self._get_reflection_prompt()
        self.config_path = get_config().get("runtime_config_relative_path", "data_cache/runtime_config.json")

    def _get_reflection_prompt(self) -> str:
        """Get the system prompt for reflection (Legacy)."""
        return """... (Legacy Prompt) ..."""

    def _get_batch_reflection_prompt(self) -> str:
        """System prompt for analyzing the ENTIRE session in one pass."""
        return """
You are an expert Strategy Auditor. Review the entire trading session log below.
1. Analyze the logic of the Bull, Bear, and Judges.
2. Identify the PRIMARY FAILURE point (if any) or the STRONGEST INSIGHT.
3. CRITICAL: Output parameter updates if the system was too slow/fast.

FORMAT:
- Summary of Session: ...
- Critique of Bull/Bear: ...
- Critique of Risk Management: ...
- PARAMETER OPTIMIZATION (JSON):
  ```json
  {
    "UPDATE_PARAMETERS": {
      "rsi_period": 7,
      "risk_multiplier_cap": 1.2
    }
  }
  ```
If no parameters need changing, omit the JSON. """

    def _extract_current_situation(self, current_state: Dict[str, Any]) -> str:
        """
        Extract the current market situation from the state.
        CRITICAL FIX: Now includes Regime Context so the Reflector knows WHY rules were applied.
        """
        # Standard Reports
        curr_market_report = current_state.get("market_report", "No Market Report")
        curr_sentiment_report = current_state.get("sentiment_report", "No Sentiment Report")
        curr_news_report = current_state.get("news_report", "No News Report")
        curr_fundamentals_report = current_state.get("fundamentals_report", "No Fundamental Report")

        # 🛑 CRITICAL CONTEXT: The Regime Data
        market_regime = current_state.get("market_regime", "UNKNOWN")
        broad_regime = current_state.get("broad_market_regime", "UNKNOWN")
        volatility = current_state.get("volatility_score", "N/A")

        # Format the Situation String
        situation_str = (
            f"=== MARKET REGIME CONTEXT ===\n"
            f"Target Asset Regime: {market_regime}\n"
            f"Broad Market (SPY) Regime: {broad_regime}\n"
            f"Volatility Score: {volatility}\n\n"
            f"=== ANALYST REPORTS ===\n"
            f"TECHNICAL: {curr_market_report}\n\n"
            f"SENTIMENT: {curr_sentiment_report}\n\n"
            f"NEWS: {curr_news_report}\n\n"
            f"FUNDAMENTALS: {curr_fundamentals_report}"
        )

        return situation_str

    def _parse_parameter_updates(self, text: str) -> Dict[str, Any]:
        """Extracts JSON parameter updates from the LLM response."""
        try:
            if "```json" in text:
                # Extract content between code blocks
                parts = text.split("```json")
                if len(parts) > 1:
                    json_str = parts[1].split("```")[0].strip()
                    try:
                        data = json.loads(json_str)
                        if "UPDATE_PARAMETERS" in data:
                            logger.info(f"⚠️ REFLECTION UPDATE: Tuning System Parameters: {data['UPDATE_PARAMETERS']}")
                            return data["UPDATE_PARAMETERS"]
                    except json.JSONDecodeError:
                        logger.debug("DEBUG: Failed to decode JSON in reflection.")
        except Exception as e:
            logger.warning(f"DEBUG: Failed to parse parameter updates: {e}")
        return {}

    def _apply_parameter_updates(self, updates: Dict[str, Any], current_state: Dict[str, Any] = None):
        """Persist parameter updates to a runtime config file."""
        if not updates:
            return
            
        # 1. Save to Global Cache (Active State)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        current_config = {}
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    current_config = json.load(f)
            except Exception as e:
                logger.warning(f"WARNING: Failed to read existing config {self.config_path}: {e}")
                current_config = {}
        
        for key, value in updates.items():
            current_config[key] = value
            
        try:
            write_json_atomic(self.config_path, current_config)
            logger.info(f"✅ SYSTEM UPDATED: Saved new parameters to {self.config_path}")
        except Exception as e:
            logger.error(f"ERROR: Failed to write config to {self.config_path}: {e}")

        # 2. Archive to Ticker/Date Result Folder (Audit Trail)
        if current_state:
            try:
                ticker = current_state.get("company_of_interest", "UNKNOWN_TICKER")
                date = current_state.get("trade_date", "UNKNOWN_DATE")
                
                # Get results dir from environment/config or default
                results_base = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
                # Construct path: results/TICKER/DATE/runtime_config.json
                archive_path = os.path.join(results_base, ticker, date, "runtime_config.json")
                
                # Atomic Write for Archive too
                write_json_atomic(archive_path, current_config)
                    
                logger.info(f"💾 ARCHIVED: Tuning config saved to {archive_path}")
                
            except Exception as e:
                logger.warning(f"Failed to archive config to results folder: {e}")

    def _reflect_on_component(
        self, component_type: str, report: str, situation: str, returns_losses, current_state: Dict[str, Any] = None
    ) -> str:
        """Generate reflection for a component."""
        messages = [
            ("system", self.reflection_system_prompt),
            (
                "human",
                f"Returns: {returns_losses}\n\nAnalysis/Decision: {report}\n\nObjective Market Reports for Reference: {situation}",
            ),
        ]

        result = self.quick_thinking_llm.invoke(messages).content
        
        # 🛑 NEW LOGIC: Extract and Apply
        try:
            updates = self._parse_parameter_updates(result)
            self._apply_parameter_updates(updates, current_state)
        except Exception as e:
            logger.error(f"ERROR: Reflection loop failed to apply updates: {e}")
            
        return result
    
    def reflect_on_full_session(self, current_state, returns_losses, memories: Dict[str, Any]):
        """
        OPTIMIZED REFLECTION: 1 Call to rule them all.
        """
        situation = self._extract_current_situation(current_state)
        
        # Aggregate the entire debate history
        session_log = (
            f"=== RETURNS: {returns_losses} ===\n\n"
            f"--- INVESTMENT DEBATE ---\n"
            f"{current_state['investment_debate_state']['history']}\n\n"
            f"--- TRADER PLAN ---\n"
            f"{current_state['trader_investment_plan']}\n\n"
            f"--- RISK DEBATE ---\n"
            f"{current_state['risk_debate_state']['history']}\n"
        )
    
        messages = [
            ("system", self._get_batch_reflection_prompt()),
            ("human", f"MARKET CONTEXT:\n{situation}\n\nSESSION LOG:\n{session_log}")
        ]
    
        # 1 Call instead of 5
        result = self.quick_thinking_llm.invoke(messages).content
        
        # Extract & Apply Params
        updates = self._parse_parameter_updates(result)
        self._apply_parameter_updates(updates, current_state)
        
        # Optional: Save result to all memories (or just a central log)
        # For simplicity, we just log it to the Trader memory for now
        if 'trader' in memories:
            memories['trader'].add_situations([(situation, result)])
        
        logger.info("✅ BATCH REFLECTION COMPLETE")


    def reflect_bull_researcher(self, current_state, returns_losses, bull_memory):
        """Reflect on bull researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bull_debate_history = current_state["investment_debate_state"]["bull_history"]

        result = self._reflect_on_component(
            "BULL", bull_debate_history, situation, returns_losses, current_state
        )
        bull_memory.add_situations([(situation, result)])

    def reflect_bear_researcher(self, current_state, returns_losses, bear_memory):
        """Reflect on bear researcher's analysis and update memory."""
        situation = self._extract_current_situation(current_state)
        bear_debate_history = current_state["investment_debate_state"]["bear_history"]

        result = self._reflect_on_component(
            "BEAR", bear_debate_history, situation, returns_losses, current_state
        )
        bear_memory.add_situations([(situation, result)])

    def reflect_trader(self, current_state, returns_losses, trader_memory):
        """Reflect on trader's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        trader_decision = current_state["trader_investment_plan"]

        result = self._reflect_on_component(
            "TRADER", trader_decision, situation, returns_losses, current_state
        )
        trader_memory.add_situations([(situation, result)])

    def reflect_invest_judge(self, current_state, returns_losses, invest_judge_memory):
        """Reflect on investment judge's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["investment_debate_state"]["judge_decision"]

        result = self._reflect_on_component(
            "INVEST JUDGE", judge_decision, situation, returns_losses, current_state
        )
        invest_judge_memory.add_situations([(situation, result)])

    def reflect_risk_manager(self, current_state, returns_losses, risk_manager_memory):
        """Reflect on risk manager's decision and update memory."""
        situation = self._extract_current_situation(current_state)
        judge_decision = current_state["risk_debate_state"]["judge_decision"]

        result = self._reflect_on_component(
            "RISK JUDGE", judge_decision, situation, returns_losses, current_state
        )
        risk_manager_memory.add_situations([(situation, result)])
