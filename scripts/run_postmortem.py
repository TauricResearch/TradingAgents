import argparse

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.experiments.postmortem import PostMortemRunner, StrategyRuleStore
from tradingagents.experiments.semantic_memory import SemanticMemory
from tradingagents.llm_clients import create_llm_client


def main():
    parser = argparse.ArgumentParser(description="Generate strategy rules from resolved trades.")
    parser.parse_args()
    config = DEFAULT_CONFIG.copy()
    llm = create_llm_client(
        provider=config["llm_provider"],
        model=config["quick_think_llm"],
        base_url=config.get("backend_url"),
    ).get_llm()
    rules = PostMortemRunner(
        llm,
        SemanticMemory(config["semantic_memory_path"]),
        StrategyRuleStore(config["strategy_rules_path"]),
    ).run()
    print("\n".join(rules))


if __name__ == "__main__":
    main()
