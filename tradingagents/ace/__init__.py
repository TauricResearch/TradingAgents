"""
Agentic Context Engineering (ACE) implementation for TradingAgents.

Uses the official Kayba ACE framework (pip install ace-framework).
Based on the ACE paper (arXiv:2510.04618) - enables agents to improve through
in-context learning instead of fine-tuning.

Core pattern:
1. INJECT: Add learned strategies to agent prompts
2. EXECUTE: Agent performs task using accumulated knowledge
3. LEARN: Reflector analyzes results, SkillManager updates skillbook
"""

from ace import (
    ACELiteLLM,
    Skillbook,
    Skill,
    Reflector,
    SkillManager,
    UpdateOperation,
    UpdateBatch,
)

from .kayba_ace import TradingACE, create_trading_ace

__all__ = [
    "ACELiteLLM",
    "Skillbook",
    "Skill",
    "Reflector",
    "SkillManager",
    "UpdateOperation",
    "UpdateBatch",
    "TradingACE",
    "create_trading_ace",
]