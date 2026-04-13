import glob
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from tradingagents.utils.logger import get_logger

logger = get_logger(__name__)


class DiscoveryAnalytics:
    """
    Handles performance tracking, statistics, and result saving for the Discovery Graph.
    """

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.recommendations_dir = self.data_dir / "recommendations"
        self.recommendations_dir.mkdir(parents=True, exist_ok=True)

    def _load_existing_database(self) -> Dict[str, Dict]:
        """Load existing performance database keyed by (ticker, discovery_date).

        Returns a dict mapping "TICKER|DATE" -> rec dict, preserving accumulated
        return data (return_1d, return_7d, etc.) across runs.
        """
        db_path = self.recommendations_dir / "performance_database.json"
        if not db_path.exists():
            return {}

        try:
            with open(db_path, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Error loading performance database: {e}")
            return {}

        existing = {}
        by_date = data.get("recommendations_by_date", {})
        for recs in by_date.values():
            if isinstance(recs, list):
                for rec in recs:
                    key = f"{rec.get('ticker')}|{rec.get('discovery_date')}"
                    existing[key] = rec
        return existing

    def _load_raw_recommendations(self) -> List[Dict]:
        """Load recommendations from raw date files."""
        all_recs = []
        pattern = str(self.recommendations_dir / "*.json")

        for filepath in glob.glob(pattern):
            if "performance_database" in filepath or "statistics" in filepath:
                continue
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                    recs = data.get("recommendations", [])
                    for rec in recs:
                        rec["discovery_date"] = data.get(
                            "date", os.path.basename(filepath).replace(".json", "")
                        )
                        all_recs.append(rec)
            except Exception as e:
                logger.warning(f"Error loading {filepath}: {e}")
        return all_recs

    def update_performance_tracking(self):
        """Update performance metrics for all recommendations.

        Loads accumulated data from performance_database.json first, merges in
        any new recs from raw date files, then updates prices for open positions.
        This preserves return_1d/return_7d/return_30d across runs.
        """
        logger.info("📊 Updating recommendation performance tracking...")

        if not self.recommendations_dir.exists():
            logger.info("No historical recommendations to track yet.")
            return

        # Step 1: Load existing database (preserves accumulated return data)
        existing = self._load_existing_database()
        logger.info(f"Loaded {len(existing)} existing records from performance database")

        # Step 2: Load raw recommendation files and merge new ones
        raw_recs = self._load_raw_recommendations()
        new_count = 0
        for rec in raw_recs:
            key = f"{rec.get('ticker')}|{rec.get('discovery_date')}"
            if key not in existing:
                existing[key] = rec
                new_count += 1

        if not existing:
            logger.info("No recommendations found to track.")
            return

        if new_count > 0:
            logger.info(f"Added {new_count} new recommendations")

        all_recs = list(existing.values())
        open_recs = [r for r in all_recs if r.get("status") != "closed"]
        logger.info(f"Tracking {len(open_recs)} open positions (out of {len(all_recs)} total)...")

        # Step 3: Update prices for open positions
        today = datetime.now().strftime("%Y-%m-%d")
        updated_count = 0

        for rec in all_recs:
            ticker = rec.get("ticker")
            discovery_date = rec.get("discovery_date")
            entry_price = rec.get("entry_price")

            if rec.get("status") == "closed" or not all([ticker, discovery_date, entry_price]):
                continue

            try:
                from tradingagents.dataflows.y_finance import get_stock_price

                current_price = get_stock_price(ticker, curr_date=today)

                if current_price is None:
                    continue

                rec_date = datetime.strptime(discovery_date, "%Y-%m-%d")
                days_held = (datetime.now() - rec_date).days
                return_pct = ((current_price - entry_price) / entry_price) * 100

                rec["current_price"] = current_price
                rec["return_pct"] = round(return_pct, 2)
                rec["days_held"] = days_held
                rec["last_updated"] = today

                # Capture milestone returns (only once, at the first eligible run)
                if days_held >= 1 and "return_1d" not in rec:
                    rec["return_1d"] = round(return_pct, 2)
                    rec["win_1d"] = return_pct > 0

                if days_held >= 7 and "return_7d" not in rec:
                    rec["return_7d"] = round(return_pct, 2)
                    rec["win_7d"] = return_pct > 0

                if days_held >= 30 and "return_30d" not in rec:
                    rec["return_30d"] = round(return_pct, 2)
                    rec["win_30d"] = return_pct > 0
                    rec["status"] = "closed"

                updated_count += 1

            except Exception:
                pass

        # Step 4: Always save — even if no price updates, the merge may have added new recs
        if updated_count > 0 or new_count > 0:
            logger.info(f"Updated {updated_count} positions, {new_count} new recs")
            self._save_performance_db(all_recs)
        else:
            logger.info("No updates needed")

    def _save_performance_db(self, all_recs: List[Dict]):
        """Save the aggregated performance database and recalculate stats."""
        # Save updated database
        by_date = {}
        for rec in all_recs:
            date = rec.get("discovery_date", "unknown")
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(rec)

        db_path = self.recommendations_dir / "performance_database.json"
        with open(db_path, "w") as f:
            json.dump(
                {
                    "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "total_recommendations": len(all_recs),
                    "recommendations_by_date": by_date,
                },
                f,
                indent=2,
            )

        # Calculate and save statistics
        stats = self.calculate_statistics(all_recs)
        stats_path = self.recommendations_dir / "statistics.json"
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=2)

        logger.info("💾 Updated performance database and statistics")

    @staticmethod
    def _normalize_strategy(name: str) -> str:
        """Normalize strategy names to snake_case canonical form.

        Merges duplicates like 'Momentum' / 'momentum', 'Insider Play' / 'insider_buying'.
        """
        import re

        if not name:
            return "unknown"

        # Lowercase and replace separators with underscore
        normalized = name.strip().lower()
        normalized = re.sub(r"[\s/]+", "_", normalized)
        # Collapse multiple underscores
        normalized = re.sub(r"_+", "_", normalized).strip("_")

        # Map known aliases to canonical names (scanner strategy values)
        aliases = {
            # Scanner name → strategy
            "insider_play": "insider_buying",
            "earnings_calendar": "earnings_play",
            "volume_accumulation": "early_accumulation",
            # LLM-guessed variants → canonical
            "momentum_hype": "momentum",
            "momentum_hype_short_squeeze": "short_squeeze",
            "earnings_momentum": "earnings_play",
            "earnings_growth": "earnings_play",
            "earnings_reversal": "earnings_play",
            "momentum_options": "options_flow",
            "oversold_reversal": "contrarian_value",
            "reddit_dd": "social_dd",
            "reddit_trending": "social_hype",
            "undiscovered_dd": "social_dd",
        }
        return aliases.get(normalized, normalized)

    def calculate_statistics(self, recommendations: list) -> dict:
        """Calculate aggregate statistics from historical performance."""
        stats = {
            "total_recommendations": len(recommendations),
            "by_strategy": {},
            "overall_1d": {"count": 0, "wins": 0, "avg_return": 0},
            "overall_7d": {"count": 0, "wins": 0, "avg_return": 0},
            "overall_30d": {"count": 0, "wins": 0, "avg_return": 0},
        }

        def _get_strategy_bucket(strategy_name):
            if strategy_name not in stats["by_strategy"]:
                stats["by_strategy"][strategy_name] = {
                    "count": 0,
                    "wins_1d": 0,
                    "losses_1d": 0,
                    "wins_7d": 0,
                    "losses_7d": 0,
                    "wins_30d": 0,
                    "losses_30d": 0,
                    "avg_return_1d": 0,
                    "avg_return_7d": 0,
                    "avg_return_30d": 0,
                }
            return stats["by_strategy"][strategy_name]

        # Calculate by strategy
        for rec in recommendations:
            strategy = self._normalize_strategy(rec.get("strategy_match", "unknown"))
            bucket = _get_strategy_bucket(strategy)
            bucket["count"] += 1

            # 1-day stats
            if "return_1d" in rec:
                stats["overall_1d"]["count"] += 1
                bucket["avg_return_1d"] += rec["return_1d"]
                if rec.get("win_1d"):
                    stats["overall_1d"]["wins"] += 1
                    bucket["wins_1d"] += 1
                else:
                    bucket["losses_1d"] += 1
                stats["overall_1d"]["avg_return"] += rec["return_1d"]

            # 7-day stats
            if "return_7d" in rec:
                stats["overall_7d"]["count"] += 1
                bucket["avg_return_7d"] += rec["return_7d"]
                if rec.get("win_7d"):
                    stats["overall_7d"]["wins"] += 1
                    bucket["wins_7d"] += 1
                else:
                    bucket["losses_7d"] += 1
                stats["overall_7d"]["avg_return"] += rec["return_7d"]

            # 30-day stats
            if "return_30d" in rec:
                stats["overall_30d"]["count"] += 1
                bucket["avg_return_30d"] += rec["return_30d"]
                if rec.get("win_30d"):
                    stats["overall_30d"]["wins"] += 1
                    bucket["wins_30d"] += 1
                else:
                    bucket["losses_30d"] += 1
                stats["overall_30d"]["avg_return"] += rec["return_30d"]

        # Calculate overall averages and win rates
        self._calculate_metric_averages(stats["overall_1d"])
        self._calculate_metric_averages(stats["overall_7d"])
        self._calculate_metric_averages(stats["overall_30d"])

        # Calculate per-strategy win rates and avg returns
        for strategy, data in stats["by_strategy"].items():
            total_1d = data["wins_1d"] + data["losses_1d"]
            total_7d = data["wins_7d"] + data["losses_7d"]
            total_30d = data["wins_30d"] + data["losses_30d"]

            if total_1d > 0:
                data["win_rate_1d"] = round((data["wins_1d"] / total_1d) * 100, 1)
                data["avg_return_1d"] = round(data["avg_return_1d"] / total_1d, 2)

            if total_7d > 0:
                data["win_rate_7d"] = round((data["wins_7d"] / total_7d) * 100, 1)
                data["avg_return_7d"] = round(data["avg_return_7d"] / total_7d, 2)

            if total_30d > 0:
                data["win_rate_30d"] = round((data["wins_30d"] / total_30d) * 100, 1)
                data["avg_return_30d"] = round(data["avg_return_30d"] / total_30d, 2)

        return stats

    def _calculate_metric_averages(self, metric_dict):
        if metric_dict["count"] > 0:
            metric_dict["win_rate"] = round((metric_dict["wins"] / metric_dict["count"]) * 100, 1)
            metric_dict["avg_return"] = round(metric_dict["avg_return"] / metric_dict["count"], 2)

    def load_historical_stats(self) -> dict:
        """Load historical performance statistics."""
        stats_file = self.recommendations_dir / "statistics.json"

        if not stats_file.exists():
            return {
                "available": False,
                "message": "No historical data yet - this will improve over time as we track performance",
            }

        try:
            with open(stats_file, "r") as f:
                stats = json.load(f)

            # Format insights
            insights = {
                "available": True,
                "total_tracked": stats.get("total_recommendations", 0),
                "overall_1d_win_rate": stats.get("overall_1d", {}).get("win_rate", 0),
                "overall_7d_win_rate": stats.get("overall_7d", {}).get("win_rate", 0),
                "overall_30d_win_rate": stats.get("overall_30d", {}).get("win_rate", 0),
                "by_strategy": stats.get("by_strategy", {}),
                "summary": self.format_stats_summary(stats),
            }

            return insights

        except Exception as e:
            logger.warning(f"Could not load historical stats: {e}")
            return {"available": False, "message": "Error loading historical data"}

    def format_stats_summary(self, stats: dict) -> str:
        """Format statistics into a concise summary."""
        lines = []

        overall_1d = stats.get("overall_1d", {})
        overall_7d = stats.get("overall_7d", {})
        overall_30d = stats.get("overall_30d", {})

        if overall_1d.get("count", 0) > 0:
            lines.append(
                f"Historical 1-day win rate: {overall_1d.get('win_rate', 0)}% ({overall_1d.get('count')} tracked)"
            )

        if overall_7d.get("count", 0) > 0:
            lines.append(
                f"Historical 7-day win rate: {overall_7d.get('win_rate', 0)}% ({overall_7d.get('count')} tracked)"
            )

        if overall_30d.get("count", 0) > 0:
            lines.append(
                f"Historical 30-day win rate: {overall_30d.get('win_rate', 0)}% ({overall_30d.get('count')} tracked)"
            )

        # Top and bottom performing strategies
        by_strategy = stats.get("by_strategy", {})
        if by_strategy:
            qualified = [
                (k, v)
                for k, v in by_strategy.items()
                if v.get("win_rate_7d") is not None
                and (v.get("wins_7d", 0) + v.get("losses_7d", 0)) >= 5
            ]
            sorted_strats = sorted(
                qualified, key=lambda x: x[1].get("win_rate_7d", 0), reverse=True
            )

            lines.append("\nBest performing strategies (7-day):")
            for strategy, data in sorted_strats[:3]:
                wr = data.get("win_rate_7d", 0)
                avg_ret = data.get("avg_return_7d", 0)
                count = data.get("wins_7d", 0) + data.get("losses_7d", 0)
                lines.append(
                    f"  - {strategy}: {wr}% win rate, avg {avg_ret:+.1f}% return ({count} samples)"
                )

            lines.append(
                "\nWORST performing strategies (7-day) — penalize these heavily in scoring:"
            )
            for strategy, data in sorted_strats[-3:]:
                wr = data.get("win_rate_7d", 0)
                avg_ret = data.get("avg_return_7d", 0)
                count = data.get("wins_7d", 0) + data.get("losses_7d", 0)
                lines.append(
                    f"  - {strategy}: {wr}% win rate, avg {avg_ret:+.1f}% return ({count} samples)"
                )

        return "\n".join(lines) if lines else "No historical data available yet"

    def save_recommendations(self, rankings: list, trade_date: str, llm_provider: str):
        """Save recommendations for tracking."""
        from tradingagents.dataflows.y_finance import get_stock_price

        # Get current prices for entry tracking
        enriched_rankings = []
        for rank in rankings:
            ticker = rank.get("ticker")

            # Get current price as entry price
            try:
                entry_price = get_stock_price(ticker, curr_date=trade_date)
            except Exception as e:
                logger.warning(f"Could not get entry price for {ticker}: {e}")
                entry_price = None

            enriched_rankings.append(
                {
                    "ticker": ticker,
                    "rank": rank.get("rank"),
                    "company_name": rank.get("company_name", ticker),
                    "description": rank.get("description", ""),
                    "strategy_match": rank.get("strategy_match"),
                    "pipeline": rank.get("strategy_match", rank.get("strategy", "unknown")),
                    "final_score": rank.get("final_score"),
                    "confidence": rank.get("confidence"),
                    "risk_level": rank.get("risk_level", "moderate"),
                    "reason": rank.get("reason"),
                    "entry_price": entry_price,
                    "discovery_date": trade_date,
                    "status": "open",  # open or closed
                }
            )

        # Save to dated file
        output_file = self.recommendations_dir / f"{trade_date}.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "date": trade_date,
                    "llm_provider": llm_provider,
                    "recommendations": enriched_rankings,
                },
                f,
                indent=2,
            )

        logger.info(
            f"   📊 Saved {len(enriched_rankings)} recommendations for tracking: {output_file}"
        )

    def save_discovery_results(self, state: dict, trade_date: str, config: Dict[str, Any]):
        """Save full discovery results and tool logs."""

        run_dir = config.get("discovery_run_dir")
        if run_dir:
            results_dir = Path(run_dir)
        else:
            run_timestamp = datetime.now().strftime("%H_%M_%S")
            results_dir = (
                Path(config.get("results_dir", "./results"))
                / "discovery"
                / trade_date
                / f"run_{run_timestamp}"
            )
            results_dir.mkdir(parents=True, exist_ok=True)

        # Save main results as markdown
        try:
            with open(results_dir / "discovery_results.md", "w") as f:
                f.write(f"# Discovery Analysis - {trade_date}\n\n")
                f.write(f"**LLM Provider**: {config.get('llm_provider', 'unknown').upper()}\n")
                f.write(
                    f"**Models**: Shallow={config.get('quick_think_llm', 'N/A')}, Deep={config.get('deep_think_llm', 'N/A')}\n\n"
                )
                f.write("## Top Investment Opportunities\n\n")

                final_ranking = state.get("final_ranking", "")
                if final_ranking:
                    self._write_ranking_md(f, final_ranking)
                else:
                    f.write("*No recommendations generated.*\n\n")

                # Format candidates analyzed section
                f.write("\n## All Candidates Analyzed\n\n")
                opportunities = state.get("opportunities", [])
                if opportunities:
                    f.write(f"Total candidates analyzed: {len(opportunities)}\n\n")
                    for opp in opportunities:
                        ticker = opp.get("ticker", "UNKNOWN")
                        strategy = opp.get("strategy", "N/A")
                        f.write(f"- **{ticker}** ({strategy})\n")

        except Exception as e:
            logger.error(f"Error saving results: {e}")

        # Save as JSON
        try:
            with open(results_dir / "discovery_result.json", "w") as f:
                json_state = {
                    "trade_date": trade_date,
                    "tickers": state.get("tickers", []),
                    "filtered_tickers": state.get("filtered_tickers", []),
                    "final_ranking": state.get("final_ranking", ""),
                    "status": state.get("status", ""),
                }
                json.dump(json_state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving JSON: {e}")

        # Save tool logs
        tool_logs = state.get("tool_logs", [])
        if tool_logs:
            tool_log_max_chars = (
                config.get("discovery", {}).get("tool_log_max_chars", 10_000) if config else 10_000
            )
            self._save_tool_logs(results_dir, tool_logs, trade_date, tool_log_max_chars)

        logger.info(f"   Results saved to: {results_dir}")

    def _write_ranking_md(self, f, final_ranking):
        try:
            # Handle both string and dict/list formats
            if isinstance(final_ranking, str):
                rankings = json.loads(final_ranking)
            else:
                rankings = final_ranking

            # Handle both direct list and dict with 'rankings' key
            if isinstance(rankings, dict):
                rankings = rankings.get("rankings", [])

            for rank in rankings:
                ticker = rank.get("ticker", "UNKNOWN")
                company_name = rank.get("company_name", ticker)
                current_price = rank.get("current_price")
                description = rank.get("description", "")
                strategy = rank.get("strategy_match", "N/A")
                final_score = rank.get("final_score", 0)
                confidence = rank.get("confidence", 0)
                risk_level = rank.get("risk_level", "")
                reason = rank.get("reason", "")
                rank_num = rank.get("rank", "?")

                # Format price
                price_str = f"${current_price:.2f}" if current_price else "N/A"

                # Write formatted recommendation
                f.write(f"### #{rank_num}: {ticker}\n\n")
                f.write(f"**Company:** {company_name}\n\n")
                f.write(f"**Current Price:** {price_str}\n\n")
                f.write(f"**Strategy:** {strategy}\n\n")
                risk_str = f" | **Risk:** {risk_level.title()}" if risk_level else ""
                f.write(f"**Score:** {final_score} | **Confidence:** {confidence}/10{risk_str}\n\n")

                if description:
                    f.write("**Description:**\n\n")
                    f.write(f"> {description}\n\n")

                f.write("**Investment Thesis:**\n\n")
                # Wrap long text nicely
                wrapped_reason = reason.replace(". ", ".\n\n")
                f.write(f"{wrapped_reason}\n\n")
                f.write("---\n\n")
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            f.write(f"⚠️ Error formatting rankings: {e}\n\n")
            f.write("```json\n")
            f.write(str(final_ranking))
            f.write("\n```\n\n")

    def _save_tool_logs(
        self, results_dir: Path, tool_logs: list, trade_date: str, md_max_chars: int
    ):
        try:
            with open(results_dir / "tool_execution_logs.json", "w") as f:
                json.dump(tool_logs, f, indent=2)

            with open(results_dir / "tool_execution_logs.md", "w") as f:
                f.write(f"# Tool Execution Logs - {trade_date}\n\n")
                for i, log in enumerate(tool_logs, 1):
                    step = log.get("step", "Unknown step")
                    log_type = log.get("type", "tool")
                    f.write(f"## {i}. {step}\n\n")
                    f.write(f"- **Type:** `{log_type}`\n")
                    f.write(f"- **Node:** {log.get('node', '')}\n")
                    f.write(f"- **Timestamp:** {log.get('timestamp', '')}\n")
                    if log.get("context"):
                        f.write(f"- **Context:** {log['context']}\n")
                    if log.get("error"):
                        f.write(f"- **Error:** {log['error']}\n")

                    if log_type == "llm":
                        f.write(f"- **Model:** `{log.get('model', 'unknown')}`\n")
                        f.write(f"- **Prompt Length:** {log.get('prompt_length', 0)} chars\n")
                        f.write(f"- **Output Length:** {log.get('output_length', 0)} chars\n\n")

                        prompt = log.get("prompt", "")
                        output = log.get("output", "")
                        if md_max_chars and len(prompt) > md_max_chars:
                            prompt = prompt[:md_max_chars] + "... [truncated]"
                        if md_max_chars and len(output) > md_max_chars:
                            output = output[:md_max_chars] + "... [truncated]"

                        f.write("### Prompt\n")
                        f.write(f"```\n{prompt}\n```\n\n")
                        f.write("### Output\n")
                        f.write(f"```\n{output}\n```\n\n")
                    else:
                        f.write(f"- **Tool:** `{log.get('tool', '')}`\n")
                        f.write(f"- **Parameters:** `{log.get('parameters', {})}`\n")
                        f.write(f"- **Output Length:** {log.get('output_length', 0)} chars\n\n")
                        output = log.get("output", "")
                        if md_max_chars and len(output) > md_max_chars:
                            output = output[:md_max_chars] + "... [truncated]"
                        f.write(f"### Output\n```\n{output}\n```\n\n")
                    f.write("---\n\n")
        except Exception as e:
            logger.error(f"Error saving tool logs: {e}")
