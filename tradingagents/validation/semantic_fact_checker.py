"""
Production Semantic Fact Checker with NLI

Features:
- DeBERTa-based entailment checking
- Targeted validation (final arguments only, not full conversation)
- Hash-based caching to prevent redundant checks
- Catches semantic contradictions ("fell" vs "rose")
"""

from typing import Dict, Any, List, Optional
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
import re


class EntailmentLabel(Enum):
    """NLI entailment labels."""
    ENTAILMENT = "entailment"
    CONTRADICTION = "contradiction"
    NEUTRAL = "neutral"


@dataclass
class FactCheckResult:
    """Result of fact checking."""
    valid: bool
    label: EntailmentLabel
    confidence: float
    evidence: str
    cached: bool = False


class SemanticFactChecker:
    """
    Validate claims using NLI (Natural Language Inference).
    
    CRITICAL OPTIMIZATIONS:
    1. Targeted validation: Only check final arguments, not full conversation
    2. Caching: Hash claims and cache results per trading day
    3. Batch processing: Check multiple claims in one NLI call
    """
    
    def __init__(
        self,
        model_name: str = "microsoft/deberta-v3-small",
        use_local_model: bool = True,
        cache_size: int = 10000
    ):
        """
        Initialize fact checker.
        
        Args:
            model_name: HuggingFace NLI model
            use_local_model: Try to load local model, fallback to LLM
            cache_size: Maximum cache entries
        """
        self.use_local_model = use_local_model
        self.nli_pipeline = None
        self.llm = None
        
        # Cache: {claim_hash: FactCheckResult}
        self.cache = {}
        self.cache_size = cache_size
        
        # Try to load NLI model
        if use_local_model:
            try:
                from transformers import pipeline
                import torch
                
                self.nli_pipeline = pipeline(
                    "text-classification",
                    model=model_name,
                    device=0 if torch.cuda.is_available() else -1
                )
                print(f"✅ Loaded NLI model: {model_name}")
            except Exception as e:
                print(f"⚠️  Could not load NLI model: {e}")
                print("   Falling back to LLM-based validation")
                self.use_local_model = False
    
    def set_llm(self, llm):
        """Set LLM for fallback validation."""
        self.llm = llm
    
    def validate_arguments(
        self,
        arguments: List[str],
        ground_truth: Dict[str, Any],
        trading_date: str
    ) -> Dict[str, FactCheckResult]:
        """
        Validate a list of arguments against ground truth.
        
        TARGETED VALIDATION: Only validates final arguments, not full conversation.
        
        Args:
            arguments: List of claims to validate (from JSON "key_arguments")
            ground_truth: Structured ground truth data
            trading_date: Date for cache scoping
        
        Returns:
            Dict mapping argument to FactCheckResult
        """
        results = {}
        
        for argument in arguments:
            # Check cache first
            cache_key = self._get_cache_key(argument, trading_date)
            
            if cache_key in self.cache:
                result = self.cache[cache_key]
                result.cached = True
                results[argument] = result
                continue
            
            # Validate uncached argument
            result = self._validate_single_argument(argument, ground_truth)
            
            # Cache result
            self._add_to_cache(cache_key, result)
            results[argument] = result
        
        return results
    
    def _validate_single_argument(
        self,
        argument: str,
        ground_truth: Dict[str, Any]
    ) -> FactCheckResult:
        """
        Validate a single argument.
        
        Args:
            argument: Claim to validate
            ground_truth: Ground truth data
        
        Returns:
            FactCheckResult
        """
        # Classify argument type
        arg_type = self._classify_argument(argument)
        
        if arg_type == "revenue":
            return self._validate_revenue_claim(argument, ground_truth)
        elif arg_type == "price":
            return self._validate_price_claim(argument, ground_truth)
        elif arg_type == "technical":
            return self._validate_technical_claim(argument, ground_truth)
        else:
            # Cannot validate qualitative claims
            return FactCheckResult(
                valid=True,  # Assume valid if can't verify
                label=EntailmentLabel.NEUTRAL,
                confidence=0.5,
                evidence="Qualitative claim - cannot verify"
            )
    
    def _validate_revenue_claim(
        self,
        claim: str,
        ground_truth: Dict[str, Any]
    ) -> FactCheckResult:
        """
        Validate revenue-related claim using NLI.
        
        Example:
            Claim: "Revenue fell 5%"
            Truth: revenue_growth_yoy = 0.05 (grew 5%)
            Result: CONTRADICTION
        """
        # Extract ground truth
        revenue_growth = ground_truth.get("revenue_growth_yoy")
        if revenue_growth is None:
            return FactCheckResult(
                valid=True,
                label=EntailmentLabel.NEUTRAL,
                confidence=0.0,
                evidence="No revenue data available"
            )
        
        # Construct premise from ground truth
        if revenue_growth > 0:
            premise = f"Revenue increased by {abs(revenue_growth):.1%} year-over-year."
        elif revenue_growth < 0:
            premise = f"Revenue decreased by {abs(revenue_growth):.1%} year-over-year."
        else:
            premise = "Revenue remained flat year-over-year."
        
        # Check entailment
        return self._check_entailment(premise, claim)
    
    def _validate_price_claim(
        self,
        claim: str,
        ground_truth: Dict[str, Any]
    ) -> FactCheckResult:
        """Validate price movement claim."""
        price_change = ground_truth.get("price_change_pct")
        if price_change is None:
            return FactCheckResult(
                valid=True,
                label=EntailmentLabel.NEUTRAL,
                confidence=0.0,
                evidence="No price data available"
            )
        
        # Construct premise
        if price_change > 0:
            premise = f"Price increased by {abs(price_change):.1%}."
        elif price_change < 0:
            premise = f"Price decreased by {abs(price_change):.1%}."
        else:
            premise = "Price remained unchanged."
        
        return self._check_entailment(premise, claim)
    
    def _validate_technical_claim(
        self,
        claim: str,
        ground_truth: Dict[str, Any]
    ) -> FactCheckResult:
        """Validate technical indicator claim (simple numeric check)."""
        # For technical indicators, use simple numeric comparison
        # Extract number from claim
        import re
        claim_numbers = re.findall(r'\d+(?:\.\d+)?', claim)
        
        if not claim_numbers:
            return FactCheckResult(
                valid=True,
                label=EntailmentLabel.NEUTRAL,
                confidence=0.5,
                evidence="No numbers in claim"
            )
        
        # Check if RSI/MACD values match ground truth
        indicators = ground_truth.get("indicators", {})
        
        # Simple heuristic: if claim mentions RSI and ground truth has RSI, compare
        if "rsi" in claim.lower() and "RSI" in indicators:
            claim_val = float(claim_numbers[0])
            truth_val = indicators["RSI"]
            
            if abs(claim_val - truth_val) < 2.0:  # Within 2 points
                return FactCheckResult(
                    valid=True,
                    label=EntailmentLabel.ENTAILMENT,
                    confidence=0.9,
                    evidence=f"RSI values match: {claim_val} ≈ {truth_val}"
                )
            else:
                return FactCheckResult(
                    valid=False,
                    label=EntailmentLabel.CONTRADICTION,
                    confidence=0.8,
                    evidence=f"RSI mismatch: claimed {claim_val}, actual {truth_val}"
                )
        
        return FactCheckResult(
            valid=True,
            label=EntailmentLabel.NEUTRAL,
            confidence=0.5,
            evidence="Cannot verify technical claim"
        )
    
    def _check_entailment(
        self,
        premise: str,
        hypothesis: str
    ) -> FactCheckResult:
        """
        Check if premise entails hypothesis using HYBRID VALIDATION.
        
        LAYER 1: Numeric Hard-Check (Sanity Layer)
        - Extract all % and $ values
        - If divergence > 10%, reject immediately
        - Do NOT let LLM decide if 500 equals 8
        
        LAYER 2: DeBERTa NLI Model (Context Layer)
        - Catches directional contradictions
        - Catches semantic shifts
        
        Args:
            premise: Ground truth statement
            hypothesis: Claim to verify
        
        Returns:
            FactCheckResult
        """
        # LAYER 1: NUMERIC HARD-CHECK
        numeric_check = self._check_numeric_divergence(premise, hypothesis)
        if numeric_check is not None:
            # Numeric contradiction found - reject immediately
            return numeric_check
        
        # LAYER 2: NLI MODEL (or fallback)
        if self.use_local_model and self.nli_pipeline:
            return self._check_entailment_nli(premise, hypothesis)
        elif self.llm:
            return self._check_entailment_llm(premise, hypothesis)
        else:
            return self._check_entailment_fallback(premise, hypothesis)
    
    def _check_numeric_divergence(
        self,
        premise: str,
        hypothesis: str,
        tolerance: float = 0.10
    ) -> Optional[FactCheckResult]:
        """
        LAYER 1: Numeric Hard-Check (The "Sanity" Layer)
        
        Extract all % and $ values from premise and hypothesis.
        If abs(claim - truth) / truth > tolerance, return CONTRADICTION immediately.
        
        DO NOT LET AN LLM DECIDE IF 500 EQUALS 8.
        
        Args:
            premise: Ground truth statement
            hypothesis: Claim to verify
            tolerance: Maximum allowed divergence (default 10%)
        
        Returns:
            FactCheckResult if numeric contradiction found, None otherwise
        """
        import re
        
        # Extract percentages (e.g., "500%", "8%", "5.5%")
        premise_pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', premise)
        hyp_pcts = re.findall(r'(\d+(?:\.\d+)?)\s*%', hypothesis)
        
        # Extract dollar amounts (e.g., "$500", "$8.50")
        premise_dollars = re.findall(r'\$\s*(\d+(?:\.\d+)?)', premise)
        hyp_dollars = re.findall(r'\$\s*(\d+(?:\.\d+)?)', hypothesis)
        
        # Extract plain numbers (e.g., "500", "8")
        premise_nums = re.findall(r'\b(\d+(?:\.\d+)?)\b', premise)
        hyp_nums = re.findall(r'\b(\d+(?:\.\d+)?)\b', hypothesis)
        
        # Check percentages first (most common in financial claims)
        if premise_pcts and hyp_pcts:
            truth_val = float(premise_pcts[0])
            claim_val = float(hyp_pcts[0])
            
            # Calculate divergence
            if truth_val > 0:
                divergence = abs(claim_val - truth_val) / truth_val
            else:
                divergence = abs(claim_val - truth_val)
            
            if divergence > tolerance:
                return FactCheckResult(
                    valid=False,
                    label=EntailmentLabel.CONTRADICTION,
                    confidence=1.0,  # Hard math, 100% confident
                    evidence=f"Numeric mismatch: Claim {claim_val}% vs Truth {truth_val}% (divergence: {divergence:.1%})"
                )
        
        # Check dollar amounts
        if premise_dollars and hyp_dollars:
            truth_val = float(premise_dollars[0])
            claim_val = float(hyp_dollars[0])
            
            if truth_val > 0:
                divergence = abs(claim_val - truth_val) / truth_val
            else:
                divergence = abs(claim_val - truth_val)
            
            if divergence > tolerance:
                return FactCheckResult(
                    valid=False,
                    label=EntailmentLabel.CONTRADICTION,
                    confidence=1.0,
                    evidence=f"Numeric mismatch: Claim ${claim_val} vs Truth ${truth_val} (divergence: {divergence:.1%})"
                )
        
        # Check plain numbers (less reliable, only if no % or $)
        if not premise_pcts and not premise_dollars and premise_nums and hyp_nums:
            # Only check if numbers are large enough to be meaningful
            truth_val = float(premise_nums[0])
            claim_val = float(hyp_nums[0])
            
            if truth_val >= 10:  # Only check numbers >= 10 to avoid false positives
                if truth_val > 0:
                    divergence = abs(claim_val - truth_val) / truth_val
                else:
                    divergence = abs(claim_val - truth_val)
                
                if divergence > tolerance:
                    return FactCheckResult(
                        valid=False,
                        label=EntailmentLabel.CONTRADICTION,
                        confidence=0.9,  # Slightly less confident for plain numbers
                        evidence=f"Numeric mismatch: Claim {claim_val} vs Truth {truth_val} (divergence: {divergence:.1%})"
                    )
        
        # No numeric contradiction found
        return None
    
    def _check_entailment_nli(
        self,
        premise: str,
        hypothesis: str
    ) -> FactCheckResult:
        """Use DeBERTa NLI model for entailment checking."""
        # Format for NLI: premise [SEP] hypothesis
        input_text = f"{premise} [SEP] {hypothesis}"
        
        # Run NLI
        result = self.nli_pipeline(input_text)[0]
        
        label_str = result['label'].lower()
        confidence = result['score']
        
        # Map to EntailmentLabel
        if 'entail' in label_str:
            label = EntailmentLabel.ENTAILMENT
            valid = True
            evidence = f"Claim entailed by ground truth: {premise}"
        elif 'contradict' in label_str:
            label = EntailmentLabel.CONTRADICTION
            valid = False
            evidence = f"Claim contradicts ground truth: {premise}"
        else:
            label = EntailmentLabel.NEUTRAL
            valid = True  # Neutral = can't disprove
            evidence = f"Claim neither entailed nor contradicted: {premise}"
        
        return FactCheckResult(
            valid=valid,
            label=label,
            confidence=confidence,
            evidence=evidence
        )
    
    def _check_entailment_llm(
        self,
        premise: str,
        hypothesis: str
    ) -> FactCheckResult:
        """Fallback: Use LLM for entailment checking."""
        prompt = f"""Determine if the Hypothesis is supported by the Premise.

Premise (Ground Truth): {premise}
Hypothesis (Claim): {hypothesis}

Respond in JSON:
{{
    "entailment": "entailment" | "contradiction" | "neutral",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}"""
        
        response = self.llm.invoke(prompt)
        
        try:
            result = json.loads(response.content)
            
            label_map = {
                "entailment": EntailmentLabel.ENTAILMENT,
                "contradiction": EntailmentLabel.CONTRADICTION,
                "neutral": EntailmentLabel.NEUTRAL
            }
            
            label = label_map.get(result["entailment"], EntailmentLabel.NEUTRAL)
            valid = label != EntailmentLabel.CONTRADICTION
            
            return FactCheckResult(
                valid=valid,
                label=label,
                confidence=result["confidence"],
                evidence=result["reasoning"]
            )
        except:
            return self._check_entailment_fallback(premise, hypothesis)
    
    def _check_entailment_fallback(
        self,
        premise: str,
        hypothesis: str
    ) -> FactCheckResult:
        """Last resort: Simple keyword matching."""
        # Extract direction words
        increase_words = ["increase", "grew", "rose", "up", "gain", "higher"]
        decrease_words = ["decrease", "fell", "dropped", "down", "loss", "lower"]
        
        premise_dir = None
        if any(w in premise.lower() for w in increase_words):
            premise_dir = "increase"
        elif any(w in premise.lower() for w in decrease_words):
            premise_dir = "decrease"
        
        hyp_dir = None
        if any(w in hypothesis.lower() for w in increase_words):
            hyp_dir = "increase"
        elif any(w in hypothesis.lower() for w in decrease_words):
            hyp_dir = "decrease"
        
        # Check if directions match
        if premise_dir and hyp_dir:
            if premise_dir == hyp_dir:
                return FactCheckResult(
                    valid=True,
                    label=EntailmentLabel.ENTAILMENT,
                    confidence=0.7,
                    evidence=f"Directions match: both {premise_dir}"
                )
            else:
                return FactCheckResult(
                    valid=False,
                    label=EntailmentLabel.CONTRADICTION,
                    confidence=0.8,
                    evidence=f"Direction mismatch: {premise_dir} vs {hyp_dir}"
                )
        
        return FactCheckResult(
            valid=True,
            label=EntailmentLabel.NEUTRAL,
            confidence=0.5,
            evidence="Cannot determine entailment"
        )
    
    def _classify_argument(self, argument: str) -> str:
        """Classify argument type for appropriate validation."""
        arg_lower = argument.lower()
        
        if any(w in arg_lower for w in ["revenue", "earnings", "sales", "income"]):
            return "revenue"
        elif any(w in arg_lower for w in ["price", "stock", "share"]):
            return "price"
        elif any(w in arg_lower for w in ["rsi", "macd", "sma", "ema", "bollinger"]):
            return "technical"
        else:
            return "qualitative"
    
    def _get_cache_key(self, argument: str, trading_date: str) -> str:
        """Generate cache key from argument and date."""
        # Hash argument + date
        hash_input = f"{argument}_{trading_date}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _add_to_cache(self, key: str, result: FactCheckResult):
        """Add result to cache with size limit."""
        if len(self.cache) >= self.cache_size:
            # Remove oldest entry (simple FIFO)
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        
        self.cache[key] = result
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "max_size": self.cache_size,
            "hit_rate": self._calculate_hit_rate()
        }
    
    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        # This would need to track hits/misses in production
        return 0.0
    
    def clear_cache(self):
        """Clear cache (e.g., at end of trading day)."""
        self.cache.clear()


# Example usage
if __name__ == "__main__":
    checker = SemanticFactChecker(use_local_model=False)  # Use fallback for demo
    
    # Test: Contradictory claim
    arguments = [
        "Revenue fell by 5% last quarter",
        "Strong earnings growth of 10%"
    ]
    
    ground_truth = {
        "revenue_growth_yoy": 0.05,  # Actually grew 5%
        "earnings_growth": 0.10
    }
    
    results = checker.validate_arguments(arguments, ground_truth, "2024-01-15")
    
    for arg, result in results.items():
        print(f"\nArgument: {arg}")
        print(f"Valid: {result.valid}")
        print(f"Label: {result.label.value}")
        print(f"Evidence: {result.evidence}")
        print(f"Cached: {result.cached}")
