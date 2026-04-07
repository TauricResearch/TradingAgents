"""Main TradingAgentsGraph - the ADK equivalent of the LangGraph version.

Architecture mapping:
    LangGraph StateGraph        ->  ADK SequentialAgent (pipeline)
    Analyst nodes (sequential)  ->  ADK ParallelAgent (analysts run concurrently!)
    Bull/Bear debate loop       ->  ADK LoopAgent + SequentialAgent
    Risk debate loop            ->  ADK LoopAgent
    LangGraph state dict        ->  ADK shared session.state (via output_key)
    @tool decorators            ->  Plain Python functions (ADK FunctionTool)
    ToolNode + conditional      ->  ADK handles tool calls automatically

The main pipeline:
    ParallelAgent[Analysts] -> InvestmentDebate -> Trader -> RiskDebate -> PortfolioManager
"""

from typing import Optional

from google.adk.agents import SequentialAgent, ParallelAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.analysts import create_market_analyst, create_fundamentals_analyst, create_news_analyst
from agents.debate import create_investment_debate, create_risk_debate
from agents.trader import create_trader
from agents.portfolio_manager import create_portfolio_manager


class TradingAgentsGraph:
    """Main orchestrator for the trading agents framework, built on Google ADK.

    This mirrors the original TradingAgentsGraph API but uses ADK's
    SequentialAgent, ParallelAgent, and LoopAgent instead of LangGraph's
    StateGraph.
    """

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        deep_model: str = "gemini-2.5-pro",
        selected_analysts: Optional[list[str]] = None,
        max_debate_rounds: int = 1,
        max_risk_rounds: int = 1,
        debug: bool = False,
    ):
        """Initialize the trading agents graph.

        Args:
            model: Model for quick-thinking agents (analysts, researchers, trader)
            deep_model: Model for deep-thinking agents (research manager, portfolio manager)
            selected_analysts: Which analysts to include. Options: "market", "fundamentals", "news"
                             Defaults to all three.
            max_debate_rounds: Number of bull/bear debate rounds
            max_risk_rounds: Number of risk debate rounds
            debug: Whether to enable debug logging
        """
        self.model = model
        self.deep_model = deep_model
        self.selected_analysts = selected_analysts or ["market", "fundamentals", "news"]
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_rounds = max_risk_rounds
        self.debug = debug

        # Build the agent pipeline
        self.root_agent = self._build_pipeline()

        # ADK session management
        self.session_service = InMemorySessionService()
        self.runner = Runner(
            agent=self.root_agent,
            app_name="trading_agents_adk",
            session_service=self.session_service,
        )

    def _build_pipeline(self) -> SequentialAgent:
        """Build the full agent pipeline.

        Pipeline structure:
            1. ParallelAgent[Analysts]  - gather data concurrently
            2. InvestmentDebate         - bull/bear debate -> investment plan
            3. Trader                   - make trade decision
            4. RiskDebate               - aggressive/conservative/neutral debate
            5. PortfolioManager         - final decision
        """
        # --- Phase 1: Analyst Team (run concurrently) ---
        analyst_agents = []
        if "market" in self.selected_analysts:
            analyst_agents.append(create_market_analyst(self.model))
        if "fundamentals" in self.selected_analysts:
            analyst_agents.append(create_fundamentals_analyst(self.model))
        if "news" in self.selected_analysts:
            analyst_agents.append(create_news_analyst(self.model))

        if len(analyst_agents) == 0:
            raise ValueError("At least one analyst must be selected!")

        analyst_team = ParallelAgent(
            name="AnalystTeam",
            sub_agents=analyst_agents,
        )

        # --- Phase 2: Investment Debate ---
        investment_debate = create_investment_debate(
            model=self.model,
            deep_model=self.deep_model,
            max_rounds=self.max_debate_rounds,
        )

        # --- Phase 3: Trader ---
        trader = create_trader(self.model)

        # --- Phase 4: Risk Debate ---
        risk_debate = create_risk_debate(
            model=self.model,
            max_rounds=self.max_risk_rounds,
        )

        # --- Phase 5: Portfolio Manager ---
        portfolio_manager = create_portfolio_manager(self.deep_model)

        # --- Compose the full pipeline ---
        return SequentialAgent(
            name="TradingAgentsPipeline",
            sub_agents=[
                analyst_team,
                investment_debate,
                trader,
                risk_debate,
                portfolio_manager,
            ],
        )

    @staticmethod
    def _extract_event_text(event) -> str:
        """Extract the full text content from an ADK event.

        Returns the concatenated text from all text parts, or a description
        of non-text parts (function calls/responses).
        """
        try:
            if not hasattr(event, 'content') or not event.content:
                return ""
            parts = getattr(event.content, 'parts', None)
            if not parts:
                return ""

            texts = []
            for part in parts:
                text = getattr(part, 'text', None)
                if text:
                    texts.append(text)
                else:
                    fn_call = getattr(part, 'function_call', None)
                    if fn_call:
                        fn_name = getattr(fn_call, 'name', 'unknown')
                        fn_args = getattr(fn_call, 'args', {})
                        texts.append(f"[tool call: {fn_name}({fn_args})]")
                    fn_resp = getattr(part, 'function_response', None)
                    if fn_resp:
                        fn_name = getattr(fn_resp, 'name', 'unknown')
                        texts.append(f"[tool response: {fn_name}]")

            return "\n".join(texts)
        except Exception as e:
            return f"(error reading event: {e})"

    @staticmethod
    def _event_has_text(event) -> bool:
        """Check if an ADK event contains text content."""
        try:
            if not hasattr(event, 'content') or not event.content:
                return False
            parts = getattr(event.content, 'parts', None)
            if not parts:
                return False
            return any(getattr(part, 'text', None) for part in parts)
        except Exception:
            return False

    async def propagate(self, company: str, trade_date: str) -> dict:
        """Run the trading agents pipeline for a company on a specific date.

        This is the ADK equivalent of the original propagate() method.

        Args:
            company: Ticker symbol (e.g., "NVDA", "AAPL")
            trade_date: Date string in yyyy-mm-dd format

        Returns:
            A dict with the final state including all reports and the decision.
        """
        # Create a new session for this analysis
        session = await self.session_service.create_session(
            app_name="trading_agents_adk",
            user_id="trader",
            state={
                "company": company,
                "trade_date": trade_date,
                # These will be populated by agents via output_key
                "market_report": "",
                "fundamentals_report": "",
                "news_report": "",
                "debate_history": "",
                "bull_argument": "",
                "bear_argument": "",
                "investment_plan": "",
                "trader_decision": "",
                "risk_debate_history": "",
                "aggressive_argument": "",
                "conservative_argument": "",
                "neutral_argument": "",
                "final_decision": "",
            },
        )

        # Create the user message that kicks off the pipeline
        user_message = types.Content(
            role="user",
            parts=[types.Part(text=(
                f"Analyze {company} as of {trade_date} and provide a trading recommendation. "
                f"The ticker symbol is {company}."
            ))],
        )

        # Run the pipeline
        final_response = None
        last_author = None
        async for event in self.runner.run_async(
            user_id="trader",
            session_id=session.id,
            new_message=user_message,
        ):
            author = getattr(event, 'author', 'unknown')

            if self.debug:
                # Print a separator when a new agent starts speaking
                if author != last_author:
                    print(f"\n{'─'*60}")
                    print(f"  Agent: {author}")
                    print(f"{'─'*60}")
                    last_author = author

                event_text = self._extract_event_text(event)
                if event_text:
                    print(event_text)

            # Track the last event that has text content
            if self._event_has_text(event):
                final_response = event

        # Retrieve final state
        final_session = await self.session_service.get_session(
            app_name="trading_agents_adk",
            user_id="trader",
            session_id=session.id,
        )

        state = final_session.state if final_session else {}

        if self.debug:
            print(f"\n{'='*60}")
            print("  STATE KEYS POPULATED")
            print(f"{'='*60}")
            for key, val in state.items():
                status = f"{len(val)} chars" if isinstance(val, str) and val else "empty"
                print(f"  {key}: {status}")

        return {
            "state": state,
            "final_decision": state.get("final_decision", ""),
            "market_report": state.get("market_report", ""),
            "fundamentals_report": state.get("fundamentals_report", ""),
            "news_report": state.get("news_report", ""),
            "investment_plan": state.get("investment_plan", ""),
            "trader_decision": state.get("trader_decision", ""),
        }
