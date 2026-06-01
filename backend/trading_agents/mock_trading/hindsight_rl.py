"""Hindsight RL dataset preparation and export."""

import csv
import json
from typing import Dict, List, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class HindsightRLDatasetBuilder:
    """Build datasets for Hindsight RL training."""
    
    def __init__(self, db, portfolio_id: int, reward_calculator=None):
        """Initialize dataset builder.
        
        Args:
            db: TradingDatabase instance
            portfolio_id: Portfolio ID
            reward_calculator: RewardCalculator instance (optional)
        """
        self.db = db
        self.portfolio_id = portfolio_id
        self.reward_calc = reward_calculator
        self.decisions = []
        self.outcomes = []
    
    def load_decisions_with_outcomes(self) -> List[Dict]:
        """Load all decisions with their realized outcomes.
        
        Returns:
            List of decision + outcome dictionaries
        """
        decisions = self.db.execute_query("""
            SELECT 
                d.id, d.ticker, d.decision, d.confidence_score,
                d.reasoning, d.timestamp,
                d.analysis_start_time, d.analysis_end_time,
                d.executed, d.execution_price, d.realized_pl,
                d.reward_score, d.reward_type,
                t.quantity_filled, t.transaction_type, t.total_value,
                t.slippage_pct, t.fees
            FROM ai_decisions d
            LEFT JOIN transactions t ON d.id = t.ai_decision_id
            WHERE d.portfolio_id = ?
            ORDER BY d.timestamp
        """, (self.portfolio_id,))
        
        self.decisions = decisions
        logger.info(f"Loaded {len(decisions)} decisions with outcomes")
        return decisions
    
    def calculate_decision_metrics(self, decision: Dict) -> Dict:
        """Calculate metrics for a single decision.
        
        Args:
            decision: Decision dictionary
            
        Returns:
            Metrics dictionary
        """
        metrics = {
            "decision_id": decision["id"],
            "ticker": decision["ticker"],
            "decision_type": decision["decision"],  # BUY/SELL/HOLD
            "confidence": decision["confidence_score"],
            
            # Execution metrics
            "executed": decision["executed"],
            "execution_price": decision["execution_price"],
            "slippage_pct": decision.get("slippage_pct", 0),
            "fees": decision.get("fees", 0),
            
            # Outcome metrics
            "realized_pl": decision["realized_pl"],
            "realized_pl_pct": None,
            
            # Analysis metrics
            "analysis_duration_sec": None,
        }
        
        # Calculate analysis duration
        if decision["analysis_start_time"] and decision["analysis_end_time"]:
            from datetime import datetime
            start = datetime.fromisoformat(decision["analysis_start_time"])
            end = datetime.fromisoformat(decision["analysis_end_time"])
            metrics["analysis_duration_sec"] = (end - start).total_seconds()
        
        # Calculate return %
        if decision["execution_price"] and decision["realized_pl"]:
            total_value = decision["quantity_filled"] * decision["execution_price"]
            if total_value > 0:
                metrics["realized_pl_pct"] = (decision["realized_pl"] / total_value) * 100
        
        return metrics
    
    def build_training_dataset(self) -> List[Dict]:
        """Build complete training dataset for Hindsight RL.
        
        Returns:
            List of training samples
        """
        self.load_decisions_with_outcomes()
        
        training_data = []
        
        for decision in self.decisions:
            # Skip if no execution
            if not decision["executed"]:
                continue
            
            metrics = self.calculate_decision_metrics(decision)
            
            # Prepare training sample
            sample = {
                "decision_id": metrics["decision_id"],
                "ticker": metrics["ticker"],
                
                # Input features (what the model sees)
                "ai_reasoning": decision["reasoning"],  # Analysis text
                "decision_type": metrics["decision_type"],
                "confidence_score": metrics["confidence"],
                "analysis_duration_sec": metrics["analysis_duration_sec"],
                
                # Output label (reward signal)
                "reward": decision["reward_score"],  # Pre-calculated reward
                "reward_type": decision["reward_type"],
                
                # Outcome details (for analysis)
                "realized_pl": metrics["realized_pl"],
                "realized_pl_pct": metrics["realized_pl_pct"],
                "execution_price": metrics["execution_price"],
                "slippage_pct": metrics["slippage_pct"],
                
                # Metadata
                "decision_timestamp": decision["timestamp"],
            }
            
            training_data.append(sample)
        
        logger.info(f"Built training dataset with {len(training_data)} samples")
        return training_data
    
    def export_training_dataset_csv(self, output_path: str):
        """Export training dataset as CSV.
        
        Args:
            output_path: Path to CSV file
        """
        training_data = self.build_training_dataset()
        
        if not training_data:
            logger.warning("No training data to export")
            return
        
        fieldnames = [
            "decision_id", "ticker", "decision_type", "confidence_score",
            "analysis_duration_sec", "ai_reasoning",
            "reward", "reward_type", "realized_pl", "realized_pl_pct",
            "execution_price", "slippage_pct", "decision_timestamp"
        ]
        
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(training_data)
        
        logger.info(f"Exported {len(training_data)} training samples to {output_path}")
    
    def export_training_dataset_json(self, output_path: str):
        """Export training dataset as JSON.
        
        Args:
            output_path: Path to JSON file
        """
        training_data = self.build_training_dataset()
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(training_data, f, indent=2, default=str)
        
        logger.info(f"Exported {len(training_data)} training samples to {output_path}")
    
    def export_training_dataset_jsonl(self, output_path: str):
        """Export training dataset as JSONL (one JSON per line).
        
        Args:
            output_path: Path to JSONL file
        """
        training_data = self.build_training_dataset()
        
        with open(output_path, "w", encoding="utf-8") as f:
            for sample in training_data:
                f.write(json.dumps(sample, default=str) + "\n")
        
        logger.info(f"Exported {len(training_data)} training samples to {output_path}")
    
    def get_dataset_statistics(self) -> Dict:
        """Get statistics about the training dataset.
        
        Returns:
            Statistics dictionary
        """
        training_data = self.build_training_dataset()
        
        if not training_data:
            return {"total_samples": 0}
        
        rewards = [s["reward"] for s in training_data if s["reward"] is not None]
        returns_pct = [s["realized_pl_pct"] for s in training_data if s["realized_pl_pct"] is not None]
        
        stats = {
            "total_samples": len(training_data),
            "executed_samples": sum(1 for d in self.decisions if d["executed"]),
            
            # Decision distribution
            "buy_decisions": sum(1 for s in training_data if s["decision_type"] == "BUY"),
            "sell_decisions": sum(1 for s in training_data if s["decision_type"] == "SELL"),
            "hold_decisions": sum(1 for s in training_data if s["decision_type"] == "HOLD"),
            
            # Confidence stats
            "avg_confidence": sum(s["confidence_score"] for s in training_data) / len(training_data),
            "min_confidence": min(s["confidence_score"] for s in training_data),
            "max_confidence": max(s["confidence_score"] for s in training_data),
            
            # Reward stats
            "reward_mean": sum(rewards) / len(rewards) if rewards else None,
            "reward_min": min(rewards) if rewards else None,
            "reward_max": max(rewards) if rewards else None,
            
            # Return stats
            "return_mean_pct": sum(returns_pct) / len(returns_pct) if returns_pct else None,
            "return_min_pct": min(returns_pct) if returns_pct else None,
            "return_max_pct": max(returns_pct) if returns_pct else None,
            
            # Analysis latency
            "avg_analysis_duration_sec": sum(
                s["analysis_duration_sec"] for s in training_data 
                if s["analysis_duration_sec"]
            ) / sum(1 for s in training_data if s["analysis_duration_sec"]),
            
            # Slippage
            "avg_slippage_pct": sum(s["slippage_pct"] for s in training_data) / len(training_data),
        }
        
        return stats
    
    def print_statistics(self):
        """Print dataset statistics to console."""
        stats = self.get_dataset_statistics()
        
        print("\n" + "="*60)
        print("HINDSIGHT RL DATASET STATISTICS")
        print("="*60)
        
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"{key:40s}: {value:10.4f}")
            else:
                print(f"{key:40s}: {value}")
        
        print("="*60 + "\n")
    
    def filter_by_confidence(self, min_confidence: float = 0.5) -> List[Dict]:
        """Get only high-confidence decisions.
        
        Args:
            min_confidence: Minimum confidence threshold
            
        Returns:
            Filtered training data
        """
        training_data = self.build_training_dataset()
        return [s for s in training_data if s["confidence_score"] >= min_confidence]
    
    def filter_by_reward_type(self, reward_type: str) -> List[Dict]:
        """Get decisions with specific reward type.
        
        Args:
            reward_type: Reward type string
            
        Returns:
            Filtered training data
        """
        training_data = self.build_training_dataset()
        return [s for s in training_data if s["reward_type"] == reward_type]
    
    def get_best_decisions(self, top_n: int = 10) -> List[Dict]:
        """Get best-performing decisions.
        
        Args:
            top_n: Number of top decisions
            
        Returns:
            Top decisions sorted by reward
        """
        training_data = self.build_training_dataset()
        return sorted(training_data, key=lambda x: x["reward"] or 0, reverse=True)[:top_n]
    
    def get_worst_decisions(self, top_n: int = 10) -> List[Dict]:
        """Get worst-performing decisions.
        
        Args:
            top_n: Number of worst decisions
            
        Returns:
            Worst decisions sorted by reward
        """
        training_data = self.build_training_dataset()
        return sorted(training_data, key=lambda x: x["reward"] or 0)[:top_n]
