#!/usr/bin/env python
"""
Interactive Research CLI - Conversational interface for investment research.
Allows natural language queries about stocks, markets, and investment opportunities.
"""

import asyncio
import os
import sys
from datetime import datetime
from typing import Optional
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.ai_research_agent import (
    AIResearchAgent,
    ResearchQuery,
    ResearchMode,
    ScreeningCriteria
)
from connectors.perplexity_finance import PerplexityFinanceConnector
from core.cache import RedisCache
from core.database import DatabaseManager

# Load environment variables
load_dotenv()

# Initialize Rich console
console = Console()


class ResearchCLI:
    """Interactive CLI for AI-powered investment research"""

    def __init__(self):
        """Initialize the Research CLI"""
        self.console = console
        self.agent = None
        self.cache = None
        self.db = None
        self.history = []

    async def initialize(self):
        """Initialize connections and agents"""
        self.console.print("\n[bold cyan]🤖 Initializing AI Research System...[/bold cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            # Initialize components
            task = progress.add_task("Setting up connections...", total=4)

            # Redis cache
            try:
                self.cache = RedisCache(
                    host=os.getenv('REDIS_HOST', 'localhost'),
                    port=int(os.getenv('REDIS_PORT', 6379))
                )
                progress.update(task, advance=1, description="Redis connected")
            except Exception as e:
                self.console.print(f"[yellow]Warning: Redis not available ({e})[/yellow]")
                progress.update(task, advance=1)

            # Database
            try:
                self.db = DatabaseManager(os.getenv('DATABASE_URL'))
                await self.db.init_database()
                progress.update(task, advance=1, description="Database connected")
            except Exception as e:
                self.console.print(f"[yellow]Warning: Database not available ({e})[/yellow]")
                progress.update(task, advance=1)

            # Perplexity connector
            perplexity = PerplexityFinanceConnector(
                api_key=os.getenv('PERPLEXITY_API_KEY'),
                cache=self.cache
            )
            progress.update(task, advance=1, description="Perplexity connected")

            # AI Research Agent
            self.agent = AIResearchAgent(
                openai_api_key=os.getenv('OPENAI_API_KEY'),
                perplexity_connector=perplexity,
                db_manager=self.db,
                cache=self.cache
            )
            progress.update(task, advance=1, description="AI Agent ready")

        self.console.print("[bold green]✅ System initialized successfully![/bold green]\n")

    def display_welcome(self):
        """Display welcome message"""
        welcome_text = """
# 🎯 AI Investment Research Assistant

I can help you with:
- Finding undervalued stocks
- Analyzing specific companies
- Screening for investment opportunities
- Portfolio optimization suggestions
- Market sentiment analysis
- Sector and industry research
- Risk assessment
- And much more!

Just ask me any investment question in natural language.
        """

        panel = Panel(
            Markdown(welcome_text),
            title="Welcome",
            border_style="cyan"
        )
        self.console.print(panel)

    def display_examples(self):
        """Display example queries"""
        examples = """
### 📝 Example Questions:

**Stock Analysis:**
- "What's your analysis of NVDA stock?"
- "Is Apple undervalued at current prices?"
- "Compare Microsoft vs Google as investments"

**Screening & Discovery:**
- "Find me undervalued tech stocks with P/E under 20"
- "What are the best dividend stocks yielding over 4%?"
- "Show me high-growth stocks in healthcare"

**Portfolio & Strategy:**
- "I have $10,000 to invest, what should I buy?"
- "How can I diversify my tech-heavy portfolio?"
- "What sectors look attractive for 2024?"

**Market Analysis:**
- "What's the current market sentiment?"
- "Are we in a bull or bear market?"
- "What are the major risks facing the market?"

**Advanced Research:**
- "What stocks are Congress members buying?"
- "Find companies with strong insider buying"
- "What are Warren Buffett's recent purchases?"
        """

        self.console.print(Markdown(examples))

    async def process_query(self, question: str) -> None:
        """Process a research query"""

        # Add to history
        self.history.append({"timestamp": datetime.now(), "question": question})

        # Show processing indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Researching your question...", total=None)

            try:
                # Determine query depth based on question complexity
                depth = "deep" if any(word in question.lower() for word in
                                    ['analyze', 'research', 'comprehensive', 'detailed']) else "standard"

                # Create research query
                query = ResearchQuery(
                    question=question,
                    depth=depth,
                    include_portfolio=True
                )

                # Execute research
                mode = ResearchMode.COMPREHENSIVE if depth == "deep" else ResearchMode.STANDARD
                response = await self.agent.research(query, mode=mode)

                progress.update(task, description="Analysis complete")

            except Exception as e:
                self.console.print(f"\n[red]Error: {e}[/red]")
                return

        # Display response
        self.display_response(response)

    def display_response(self, response):
        """Display research response in formatted way"""

        # Main answer
        answer_panel = Panel(
            response.answer,
            title="📊 Analysis",
            border_style="green"
        )
        self.console.print("\n", answer_panel)

        # Confidence score
        confidence_color = "green" if response.confidence > 0.7 else "yellow" if response.confidence > 0.4 else "red"
        self.console.print(
            f"\n[{confidence_color}]Confidence: {response.confidence:.0%}[/{confidence_color}]"
        )

        # Recommendations if any
        if response.recommendations:
            self.console.print("\n[bold cyan]💡 Recommendations:[/bold cyan]")
            for rec in response.recommendations:
                self.console.print(f"  • {rec}")

        # Risks
        if response.risks:
            self.console.print("\n[bold yellow]⚠️  Key Risks:[/bold yellow]")
            for risk in response.risks:
                self.console.print(f"  • {risk}")

        # Data sources
        if response.sources:
            self.console.print(f"\n[dim]Sources: {', '.join(response.sources)}[/dim]")

        # Follow-up questions
        if response.follow_up_questions:
            self.console.print("\n[bold]🤔 Follow-up questions you might ask:[/bold]")
            for q in response.follow_up_questions:
                self.console.print(f"  • {q}")

    async def screen_stocks(self):
        """Interactive stock screening"""
        self.console.print("\n[bold cyan]📈 Stock Screener[/bold cyan]")

        # Get screening criteria
        query = Prompt.ask("Describe what stocks you're looking for")

        # Optional: Get specific criteria
        use_filters = Confirm.ask("Add specific filters?", default=False)

        criteria = None
        if use_filters:
            criteria = ScreeningCriteria()

            if Confirm.ask("Set market cap range?"):
                criteria.min_market_cap = float(Prompt.ask("Minimum market cap (in billions)", default="0"))
                criteria.max_market_cap = float(Prompt.ask("Maximum market cap (in billions)", default="10000"))

            if Confirm.ask("Set P/E ratio range?"):
                criteria.min_pe = float(Prompt.ask("Minimum P/E", default="0"))
                criteria.max_pe = float(Prompt.ask("Maximum P/E", default="50"))

            if Confirm.ask("Filter by sector?"):
                sectors = Prompt.ask("Sectors (comma-separated)")
                criteria.sectors = [s.strip() for s in sectors.split(',')]

        # Run screening
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Screening stocks...", total=None)

            try:
                results = await self.agent.screen_stocks(query, criteria)
                progress.update(task, description="Screening complete")
            except Exception as e:
                self.console.print(f"\n[red]Error: {e}[/red]")
                return

        # Display results
        if results:
            table = Table(title=f"Stock Screening Results: {query}")
            table.add_column("Ticker", style="cyan", no_wrap=True)
            table.add_column("Company", style="white")
            table.add_column("Price", justify="right", style="green")
            table.add_column("P/E", justify="right")
            table.add_column("Fair Value", justify="right")
            table.add_column("Upside %", justify="right", style="yellow")
            table.add_column("AI Signal", justify="center")
            table.add_column("Confidence", justify="right")

            for stock in results:
                signal_color = "green" if stock['ai_signal'] == "BUY" else "red" if stock['ai_signal'] == "SELL" else "yellow"
                table.add_row(
                    stock['ticker'],
                    stock['company'][:30],
                    f"${stock['current_price']:.2f}",
                    f"{stock['pe_ratio']:.1f}" if stock['pe_ratio'] else "N/A",
                    f"${stock['fair_value']:.2f}" if stock['fair_value'] else "N/A",
                    f"{stock['upside_potential']:.1f}%" if stock['upside_potential'] else "N/A",
                    f"[{signal_color}]{stock['ai_signal']}[/{signal_color}]",
                    f"{stock['ai_confidence']:.0%}"
                )

            self.console.print("\n", table)
        else:
            self.console.print("[yellow]No stocks found matching criteria[/yellow]")

    async def find_opportunities(self):
        """Find investment opportunities based on parameters"""
        self.console.print("\n[bold cyan]💰 Investment Opportunity Finder[/bold cyan]")

        # Get parameters
        amount = float(Prompt.ask("Investment amount ($)", default="10000"))
        risk = Prompt.ask(
            "Risk tolerance",
            choices=["low", "medium", "high"],
            default="medium"
        )
        horizon = Prompt.ask(
            "Time horizon",
            choices=["short", "medium", "long"],
            default="medium"
        )

        # Find opportunities
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console
        ) as progress:
            task = progress.add_task("Finding opportunities...", total=None)

            try:
                opportunities = await self.agent.find_opportunities(amount, risk, horizon)
                progress.update(task, description="Analysis complete")
            except Exception as e:
                self.console.print(f"\n[red]Error: {e}[/red]")
                return

        # Display opportunities
        panel = Panel(
            f"""
[bold]Investment Profile:[/bold]
• Amount: ${amount:,.0f}
• Risk: {risk}
• Horizon: {horizon}

[bold]Market Conditions:[/bold]
{opportunities['market_conditions'].get('key_factors', 'N/A')}
            """,
            title="📊 Investment Plan",
            border_style="cyan"
        )
        self.console.print("\n", panel)

        # Allocation strategy
        if opportunities['allocation_strategy']:
            self.console.print("\n[bold]📈 Recommended Allocation:[/bold]")
            for ticker, allocation in opportunities['allocation_strategy'].items():
                pct = (allocation / amount) * 100
                self.console.print(f"  • {ticker}: ${allocation:,.0f} ({pct:.0f}%)")

        # Expected returns
        if opportunities['expected_returns']:
            returns = opportunities['expected_returns']
            self.console.print("\n[bold]💵 Projected Returns:[/bold]")
            self.console.print(f"  • Expected: {returns['expected']:.1f}%")
            self.console.print(f"  • Best case: {returns['best_case']:.1f}%")
            self.console.print(f"  • Worst case: {returns['worst_case']:.1f}%")

        # Execution plan
        if opportunities['execution_plan']:
            self.console.print("\n[bold]📋 Execution Plan:[/bold]")
            for step in opportunities['execution_plan']:
                self.console.print(f"  {step}")

    def show_history(self):
        """Show query history"""
        if not self.history:
            self.console.print("[yellow]No queries in history[/yellow]")
            return

        table = Table(title="Query History")
        table.add_column("Time", style="cyan", no_wrap=True)
        table.add_column("Question", style="white")

        for entry in self.history[-10:]:  # Last 10 queries
            table.add_row(
                entry['timestamp'].strftime("%H:%M:%S"),
                entry['question'][:80] + "..." if len(entry['question']) > 80 else entry['question']
            )

        self.console.print("\n", table)

    async def run(self):
        """Main CLI loop"""
        await self.initialize()
        self.display_welcome()

        while True:
            try:
                # Display prompt
                self.console.print("\n" + "="*50)
                choice = Prompt.ask(
                    "\n[bold cyan]What would you like to do?[/bold cyan]",
                    choices=["ask", "screen", "opportunities", "examples", "history", "exit"],
                    default="ask"
                )

                if choice == "exit":
                    self.console.print("\n[bold cyan]Thank you for using AI Research Assistant! 📈[/bold cyan]")
                    break

                elif choice == "ask":
                    question = Prompt.ask("\n[bold]Your question[/bold]")
                    if question.strip():
                        await self.process_query(question)

                elif choice == "screen":
                    await self.screen_stocks()

                elif choice == "opportunities":
                    await self.find_opportunities()

                elif choice == "examples":
                    self.display_examples()

                elif choice == "history":
                    self.show_history()

            except KeyboardInterrupt:
                if Confirm.ask("\nExit?", default=True):
                    break
            except Exception as e:
                self.console.print(f"\n[red]Error: {e}[/red]")
                self.console.print("[yellow]Please try again[/yellow]")


async def main():
    """Main entry point"""
    # Check for required environment variables
    required_vars = ['OPENAI_API_KEY', 'PERPLEXITY_API_KEY']
    missing = [var for var in required_vars if not os.getenv(var)]

    if missing:
        console.print(f"[red]Missing required environment variables: {', '.join(missing)}[/red]")
        console.print("\n[yellow]Please set them in your .env file:[/yellow]")
        for var in missing:
            console.print(f"  {var}=your_api_key_here")
        sys.exit(1)

    # Run CLI
    cli = ResearchCLI()
    await cli.run()


if __name__ == "__main__":
    asyncio.run(main())