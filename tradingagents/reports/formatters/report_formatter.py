"""
Report Formatter for TradingAgents Analysis

This module formats and structures analysis results for PDF generation,
matching the exact terminal output structure.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json


class ReportFormatter:
    """Formats trading analysis results into structured sections for PDF generation."""
    
    def __init__(self):
        self.sections = {}
        
    def format_complete_report(self, analysis_data: Dict[str, Any], ticker: str, date: str) -> str:
        """
        Format complete analysis report into structured HTML matching the terminal output.
        
        Args:
            analysis_data: Complete analysis results including final_state
            ticker: Stock ticker symbol
            date: Analysis date
            
        Returns:
            Formatted HTML content matching terminal structure
        """
        html_sections = []
        
        # Cover page
        html_sections.append(self._create_cover_page(ticker, date))
        
        # Get final_state for structured data
        final_state = analysis_data.get('final_state', {})
        
        # Complete Analysis Report Header
        html_sections.append('<h1 style="color: #00aa00; font-weight: bold; text-align: center; margin: 30px 0;">Complete Analysis Report</h1>')
        
        # I. Analyst Team Reports
        analyst_section = self._format_analyst_team_reports(final_state)
        if analyst_section:
            html_sections.append(analyst_section)
        
        # II. Research Team Decision  
        research_section = self._format_research_team_decision(final_state)
        if research_section:
            html_sections.append(research_section)
        
        # III. Trading Team Plan
        trading_section = self._format_trading_team_plan(final_state)
        if trading_section:
            html_sections.append(trading_section)
        
        # IV. Risk Management Team Decision
        risk_section = self._format_risk_management_team_decision(final_state)
        if risk_section:
            html_sections.append(risk_section)
        
        # V. Portfolio Manager Decision
        portfolio_section = self._format_portfolio_manager_decision(final_state)
        if portfolio_section:
            html_sections.append(portfolio_section)
        
        return '\n'.join(html_sections)
    
    def _create_cover_page(self, ticker: str, date: str) -> str:
        """Create report cover page."""
        return f"""
        <div class="cover-page" style="page-break-after: always; text-align: center; margin-top: 100px;">
            <h1 style="font-size: 36px; color: #2c3e50; margin-bottom: 20px;">TradingAgents Analysis Report</h1>
            <h2 style="font-size: 28px; color: #3498db; margin-bottom: 40px;">{ticker}</h2>
            <p style="font-size: 18px; color: #7f8c8d; margin-bottom: 20px;">Analysis Date: {date}</p>
            <p style="font-size: 16px; color: #7f8c8d;">Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <div style="margin-top: 80px; padding: 20px; border: 2px solid #3498db; border-radius: 10px; background-color: #f8f9fa;">
                <h3 style="color: #2c3e50; margin-bottom: 15px;">Multi-Agents LLM Financial Trading Framework</h3>
                <p style="color: #7f8c8d; font-size: 14px;">
                    Workflow: Analyst Team → Research Team → Trader → Risk Management → Portfolio Management
                </p>
            </div>
        </div>
        """
    
    def _format_analyst_team_reports(self, final_state: Dict[str, Any]) -> str:
        """Format I. Analyst Team Reports section."""
        analysts = []
        
        # Market Analyst Report
        if final_state.get("market_report"):
            analysts.append(self._create_analyst_panel("Market Analyst", final_state["market_report"]))
        
        # Social Analyst Report  
        if final_state.get("sentiment_report"):
            analysts.append(self._create_analyst_panel("Social Analyst", final_state["sentiment_report"]))
        
        # News Analyst Report
        if final_state.get("news_report"):
            analysts.append(self._create_analyst_panel("News Analyst", final_state["news_report"]))
        
        # Fundamentals Analyst Report
        if final_state.get("fundamentals_report"):
            analysts.append(self._create_analyst_panel("Fundamentals Analyst", final_state["fundamentals_report"]))
        
        if not analysts:
            return ""
        
        return f"""
        <div class="section" style="margin: 30px 0; page-break-inside: avoid;">
            <h2 style="color: #00bcd4; border-bottom: 3px solid #00bcd4; padding-bottom: 10px; margin-bottom: 20px;">
                I. Analyst Team Reports
            </h2>
            <div class="analyst-reports" style="display: flex; flex-wrap: wrap; gap: 20px;">
                {''.join(analysts)}
            </div>
        </div>
        """
    
    def _format_research_team_decision(self, final_state: Dict[str, Any]) -> str:
        """Format II. Research Team Decision section."""
        if not final_state.get("investment_debate_state"):
            return ""
        
        debate_state = final_state["investment_debate_state"]
        researchers = []
        
        # Bull Researcher Analysis
        if debate_state.get("bull_history"):
            researchers.append(self._create_analyst_panel("Bull Researcher", debate_state["bull_history"]))
        
        # Bear Researcher Analysis
        if debate_state.get("bear_history"):
            researchers.append(self._create_analyst_panel("Bear Researcher", debate_state["bear_history"]))
        
        # Research Manager Decision
        if debate_state.get("judge_decision"):
            researchers.append(self._create_analyst_panel("Research Manager", debate_state["judge_decision"]))
        
        if not researchers:
            return ""
        
        return f"""
        <div class="section" style="margin: 30px 0; page-break-inside: avoid;">
            <h2 style="color: #e91e63; border-bottom: 3px solid #e91e63; padding-bottom: 10px; margin-bottom: 20px;">
                II. Research Team Decision
            </h2>
            <div class="research-reports" style="display: flex; flex-wrap: wrap; gap: 20px;">
                {''.join(researchers)}
            </div>
        </div>
        """
    
    def _format_trading_team_plan(self, final_state: Dict[str, Any]) -> str:
        """Format III. Trading Team Plan section."""
        if not final_state.get("trader_investment_plan"):
            return ""
        
        return f"""
        <div class="section" style="margin: 30px 0; page-break-inside: avoid;">
            <h2 style="color: #ff9800; border-bottom: 3px solid #ff9800; padding-bottom: 10px; margin-bottom: 20px;">
                III. Trading Team Plan
            </h2>
            <div class="trading-plan">
                {self._create_analyst_panel("Trader", final_state["trader_investment_plan"])}
            </div>
        </div>
        """
    
    def _format_risk_management_team_decision(self, final_state: Dict[str, Any]) -> str:
        """Format IV. Risk Management Team Decision section."""
        if not final_state.get("risk_debate_state"):
            return ""
        
        risk_state = final_state["risk_debate_state"]
        risk_analysts = []
        
        # Aggressive (Risky) Analyst Analysis
        if risk_state.get("risky_history"):
            risk_analysts.append(self._create_analyst_panel("Aggressive Analyst", risk_state["risky_history"]))
        
        # Conservative (Safe) Analyst Analysis
        if risk_state.get("safe_history"):
            risk_analysts.append(self._create_analyst_panel("Conservative Analyst", risk_state["safe_history"]))
        
        # Neutral Analyst Analysis
        if risk_state.get("neutral_history"):
            risk_analysts.append(self._create_analyst_panel("Neutral Analyst", risk_state["neutral_history"]))
        
        if not risk_analysts:
            return ""
        
        return f"""
        <div class="section" style="margin: 30px 0; page-break-inside: avoid;">
            <h2 style="color: #f44336; border-bottom: 3px solid #f44336; padding-bottom: 10px; margin-bottom: 20px;">
                IV. Risk Management Team Decision
            </h2>
            <div class="risk-reports" style="display: flex; flex-wrap: wrap; gap: 20px;">
                {''.join(risk_analysts)}
            </div>
        </div>
        """
    
    def _format_portfolio_manager_decision(self, final_state: Dict[str, Any]) -> str:
        """Format V. Portfolio Manager Decision section."""
        if not final_state.get("risk_debate_state") or not final_state["risk_debate_state"].get("judge_decision"):
            return ""
        
        decision = final_state["risk_debate_state"]["judge_decision"]
        
        return f"""
        <div class="section" style="margin: 30px 0; page-break-inside: avoid;">
            <h2 style="color: #4caf50; border-bottom: 3px solid #4caf50; padding-bottom: 10px; margin-bottom: 20px;">
                V. Portfolio Manager Decision
            </h2>
            <div class="portfolio-decision">
                {self._create_analyst_panel("Portfolio Manager", decision)}
            </div>
        </div>
        """
    
    def _create_analyst_panel(self, title: str, content: str) -> str:
        """Create a styled panel for an analyst's report."""
        # Convert markdown-style content to HTML if needed
        formatted_content = self._format_markdown_content(content)
        
        return f"""
        <div class="analyst-panel" style="
            flex: 1; 
            min-width: 300px; 
            border: 2px solid #3498db; 
            border-radius: 8px; 
            padding: 20px; 
            margin: 10px;
            background-color: #f8f9fa;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        ">
            <h3 style="color: #3498db; margin-top: 0; margin-bottom: 15px; border-bottom: 1px solid #3498db; padding-bottom: 8px;">
                {title}
            </h3>
            <div class="content" style="line-height: 1.6; color: #2c3e50;">
                {formatted_content}
            </div>
        </div>
        """
    
    def _format_markdown_content(self, content: str) -> str:
        """Convert basic markdown formatting to HTML."""
        if not content:
            return ""
        
        # Replace markdown headers
        content = content.replace('### ', '<h4>').replace('\n### ', '</h4>\n<h4>')
        content = content.replace('## ', '<h3>').replace('\n## ', '</h3>\n<h3>')
        content = content.replace('# ', '<h2>').replace('\n# ', '</h2>\n<h2>')
        
        # Replace bold text
        import re
        content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', content)
        
        # Replace bullet points
        content = re.sub(r'\n\s*•\s+', '\n<li>', content)
        content = re.sub(r'\n\s*\*\s+', '\n<li>', content)
        content = re.sub(r'\n\s*-\s+', '\n<li>', content)
        
        # Wrap consecutive list items in <ul> tags
        content = re.sub(r'(<li>.*?)(?=\n(?!<li>))', r'<ul>\1</ul>', content, flags=re.DOTALL)
        
        # Replace line breaks with <br> for better formatting
        content = content.replace('\n\n', '<br><br>')
        content = content.replace('\n', '<br>')
        
        # Clean up any unclosed headers
        if '<h' in content and not content.endswith(('</h2>', '</h3>', '</h4>')):
            content += '</h4>'
        
        return content
    
    def _combine_sections(self, sections: List[str]) -> str:
        """Combine all sections into final HTML."""
        return '\n'.join(sections)