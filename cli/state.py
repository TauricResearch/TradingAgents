import datetime
from collections import deque
from typing import Optional, Dict, Any, Deque

from cli.models import AgentStatus


class MessageBuffer:
    def __init__(self, max_length: int = 100) -> None:
        self.messages: Deque = deque(maxlen=max_length)
        self.tool_calls: Deque = deque(maxlen=max_length)
        self.current_report = None
        self.final_report = None
        self.agent_status: Dict[str, AgentStatus] = {
            "Market Analyst": AgentStatus.PENDING,
            "Social Analyst": AgentStatus.PENDING,
            "News Analyst": AgentStatus.PENDING,
            "Fundamentals Analyst": AgentStatus.PENDING,
            "Bull Researcher": AgentStatus.PENDING,
            "Bear Researcher": AgentStatus.PENDING,
            "Research Manager": AgentStatus.PENDING,
            "Trader": AgentStatus.PENDING,
            "Risky Analyst": AgentStatus.PENDING,
            "Neutral Analyst": AgentStatus.PENDING,
            "Safe Analyst": AgentStatus.PENDING,
            "Portfolio Manager": AgentStatus.PENDING,
        }
        self.current_agent = None
        self.report_sections = {
            "market_report": None,
            "sentiment_report": None,
            "news_report": None,
            "fundamentals_report": None,
            "investment_plan": None,
            "trader_investment_plan": None,
            "final_trade_decision": None,
        }

    def add_message(self, message_type: str, content: str) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.messages.append((timestamp, message_type, content))

    def add_tool_call(self, tool_name: str, args: Dict[str, Any]) -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.tool_calls.append((timestamp, tool_name, args))

    def update_agent_status(self, agent: str, status: AgentStatus) -> None:
        if agent in self.agent_status:
            self.agent_status[agent] = status
            self.current_agent = agent

    def update_report_section(self, section_name: str, content: str) -> None:
        if section_name in self.report_sections:
            self.report_sections[section_name] = content
            self._update_current_report()

    def _update_current_report(self) -> None:
        latest_section = None
        latest_content = None

        for section, content in self.report_sections.items():
            if content is not None:
                latest_section = section
                latest_content = content

        if latest_section and latest_content:
            section_titles = {
                "market_report": "Market Analysis",
                "sentiment_report": "Social Sentiment",
                "news_report": "News Analysis",
                "fundamentals_report": "Fundamentals Analysis",
                "investment_plan": "Research Team Decision",
                "trader_investment_plan": "Trading Team Plan",
                "final_trade_decision": "Portfolio Management Decision",
            }
            self.current_report = (
                f"### {section_titles[latest_section]}\n{latest_content}"
            )

        self._update_final_report()

    def _update_final_report(self) -> None:
        report_parts = []

        if any(
            self.report_sections[section]
            for section in [
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
            ]
        ):
            report_parts.append("## Analyst Team Reports")
            if self.report_sections["market_report"]:
                report_parts.append(
                    f"### Market Analysis\n{self.report_sections['market_report']}"
                )
            if self.report_sections["sentiment_report"]:
                report_parts.append(
                    f"### Social Sentiment\n{self.report_sections['sentiment_report']}"
                )
            if self.report_sections["news_report"]:
                report_parts.append(
                    f"### News Analysis\n{self.report_sections['news_report']}"
                )
            if self.report_sections["fundamentals_report"]:
                report_parts.append(
                    f"### Fundamentals Analysis\n{self.report_sections['fundamentals_report']}"
                )

        if self.report_sections["investment_plan"]:
            report_parts.append("## Research Team Decision")
            report_parts.append(f"{self.report_sections['investment_plan']}")

        if self.report_sections["trader_investment_plan"]:
            report_parts.append("## Trading Team Plan")
            report_parts.append(f"{self.report_sections['trader_investment_plan']}")

        if self.report_sections["final_trade_decision"]:
            report_parts.append("## Portfolio Management Decision")
            report_parts.append(f"{self.report_sections['final_trade_decision']}")

        self.final_report = "\n\n".join(report_parts) if report_parts else None

    def reset(self) -> None:
        for agent in self.agent_status:
            self.agent_status[agent] = AgentStatus.PENDING
        for section in self.report_sections:
            self.report_sections[section] = None
        self.current_report = None
        self.final_report = None
        self.messages.clear()
        self.tool_calls.clear()


message_buffer = MessageBuffer()
