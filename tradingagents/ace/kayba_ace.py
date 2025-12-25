"""
Kayba ACE Integration for TradingAgents.

Uses the official ace-framework from Kayba (pip install ace-framework)
for self-improving trading agents.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ace import (
    OnlineACE,
    Agent,
    Reflector,
    SkillManager,
    LiteLLMClient,
    Sample,
    TaskEnvironment,
    EnvironmentResult,
    Skillbook,
    Skill,
    AgentOutput
)


class TradingEnvironment(TaskEnvironment):
    """
    Environment for evaluating the quality and consistency of trading analysis.
    
    Instead of just looking at price, it evaluates the logical flow between
    market data, sentiment, news, and the final decision.
    """
    
    def evaluate(self, sample: Sample, agent_output) -> EnvironmentResult:
        """
        Evaluate the analytical rigor of the trading decision.
        """
        # We provide a high-level goal for the reflector
        feedback = (
            "Evaluate the logical consistency of this analysis. "
            "Check if the final decision is truly supported by the market report, "
            "sentiment analysis, and news. Identify any contradictions or missed "
            "signals that could lead to a sub-optimal trade, regardless of the price outcome."
        )
        
        return EnvironmentResult(
            feedback=feedback,
            ground_truth="A logically sound, consistent, and well-supported investment thesis."
        )


class TradingACE:
    """
    Self-improving trading agent using Kayba's ACE framework.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        skillbook_path: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        """
        Initialize TradingACE.
        """
        self.model = model
        self.skillbook_path = skillbook_path
        
        # Initialize LLM client
        self.client = LiteLLMClient(model=model, api_base=api_base)
        
        # Create ACE components
        self.agent = Agent(self.client)
        self.reflector = Reflector(self.client)
        self.skill_manager = SkillManager(self.client)
        
        # Load or create skillbook
        if skillbook_path and Path(skillbook_path).exists():
            self.skillbook = Skillbook.load_from_file(skillbook_path)
        else:
            self.skillbook = Skillbook()
            
        # Create OnlineACE adapter
        self.ace = OnlineACE(
            skillbook=self.skillbook,
            agent=self.agent,
            reflector=self.reflector,
            skill_manager=self.skill_manager
        )
        
        self.environment = TradingEnvironment()

    def learn_from_analysis(self, reports: Dict[str, str], decision: str):
        """
        Learn from a trading analysis by reflecting on the consistency of all reports.
        """
        ticker = reports.get("ticker", "Unknown")
        date = reports.get("date", "Unknown")
        
        print(f"ACE: Learning from analytical consistency for {ticker} on {date}")
        
        # Combine all reports into a single context for the reflector
        full_context = "\n\n".join([
            f"MARKET REPORT:\n{reports.get('market', 'N/A')}",
            f"SENTIMENT REPORT:\n{reports.get('sentiment', 'N/A')}",
            f"NEWS REPORT:\n{reports.get('news', 'N/A')}",
            f"FUNDAMENTALS REPORT:\n{reports.get('fundamentals', 'N/A')}",
            f"INVESTMENT PLAN:\n{reports.get('plan', 'N/A')}"
        ])

        sample = Sample(
            question=(
                f"Analyze the following multi-agent trading reports for {ticker} and "
                "determine if the final decision is logically consistent with all data points."
            ),
            context=full_context,
            ground_truth="A perfectly consistent and well-reasoned investment thesis."
        )
        
        # Create a proper AgentOutput instance representing the whole analysis
        actual_output = AgentOutput(
            reasoning=f"Full analysis process for {ticker}.",
            final_answer=decision,
            raw={"decision": decision}
        )
        
        try:
            # 1. Evaluate the analytical rigor
            eval_result = self.environment.evaluate(sample, actual_output)
            print(f"ACE: Evaluation focus: {eval_result.feedback}")
            
            # 2. Reflect on the consistency and quality
            print("ACE: Reflecting on analytical quality...")
            reflector_output = self.reflector.reflect(
                question=sample.question,
                agent_output=actual_output,
                skillbook=self.skillbook,
                ground_truth=eval_result.ground_truth,
                feedback=eval_result.feedback
            )
            
            print(f"ACE: Reflection generated (reasoning length: {len(reflector_output.reasoning)})")
            
            # 3. Update the skillbook with the new reflection
            print("ACE: Updating skillbook...")
            sm_output = self.skill_manager.update_skills(
                skillbook=self.skillbook,
                reflection=reflector_output,
                question_context=sample.context,
                progress=eval_result.feedback
            )
            
            if sm_output.update:
                print("ACE: Applying update to skillbook...")
                self.skillbook.apply_update(sm_output.update)
            
            # Force save
            self.save_skillbook()
            print(f"ACE: Skillbook saved to {self.skillbook_path}")
            
        except Exception as e:
            print(f"Error in ACE learning: {e}")
            import traceback
            traceback.print_exc()

    def learn_from_trade(self, context: str, decision: str, result: str, market_data: str):
        """
        Compatibility method for TradingAgentsGraph.
        """
        reports = {
            "market": market_data,
            "ticker": context.split(" on ")[0],
            "date": context.split(" on ")[1] if " on " in context else "Unknown"
        }
        self.learn_from_analysis(reports, decision)

    def get_skills_context(self) -> str:
        """Get formatted skills for injection into prompts."""
        if not self.skillbook.skills():
            return ""
        return self.skillbook.as_prompt()

    def save_skillbook(self, path: Optional[str] = None) -> str:
        """Save the skillbook to file."""
        save_path = path or self.skillbook_path or "ace_skillbook.json"
        self.skillbook.save_to_file(save_path)
        return save_path

    def get_stats(self) -> Dict[str, Any]:
        """Get ACE statistics."""
        try:
            skills = self.skillbook.skills()
            count = len(skills)
        except:
            try:
                count = self.skillbook.stats().get('skills', 0)
            except:
                count = 0
                
        return {
            "skills_count": count,
            "model": self.model
        }


def create_trading_ace(
    config: Dict[str, Any],
    skillbook_path: Optional[str] = None,
) -> TradingACE:
    """
    Factory function to create TradingACE.
    """
    model = config.get("quick_think_llm", "gpt-4o-mini")
    api_base = config.get("backend_url")
    
    return TradingACE(
        model=model,
        skillbook_path=skillbook_path,
        api_base=api_base
    )