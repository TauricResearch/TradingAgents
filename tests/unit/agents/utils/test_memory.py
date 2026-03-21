import pytest
from tradingagents.agents.utils.memory import FinancialSituationMemory

@pytest.fixture
def memory_instance():
    """Fixture to provide a FinancialSituationMemory instance."""
    return FinancialSituationMemory(name="test_memory")

@pytest.mark.parametrize(
    "input_text, expected_tokens",
    [
        # Simple cases
        ("hello world", ["hello", "world"]),
        ("SINGLE", ["single"]),
        ("Mixed Case String", ["mixed", "case", "string"]),

        # Numbers
        ("123 456", ["123", "456"]),
        ("year 2024", ["year", "2024"]),

        # Punctuation
        ("hello, world!", ["hello", "world"]),
        ("end. start", ["end", "start"]),
        ("questions?", ["questions"]),
        ("multiple... dots", ["multiple", "dots"]),

        # Edge cases with quotes, apostrophes, and hyphens (based on current implementation)
        ("don't", ["don", "t"]),
        ("it's", ["it", "s"]),
        ("a-b", ["a", "b"]),
        ("long-term", ["long", "term"]),
        ('"quote"', ["quote"]),

        # Underscores (word boundary \b and \w behavior)
        ("_leading", ["_leading"]),
        ("trailing_", ["trailing_"]),
        ("in_between", ["in_between"]),

        # Symbols
        ("100% growth", ["100", "growth"]),
        ("price $50", ["price", "50"]),
        ("a & b", ["a", "b"]),
        ("tech @ sector", ["tech", "sector"]),

        # Empty and whitespace
        ("", []),
        ("   ", []),
        ("\t\n", []),
        ("  spaces  around  ", ["spaces", "around"]),

        # Complex sentence
        (
            "High inflation (CPI at 8.5%) affects the $SPY heavily!",
            ["high", "inflation", "cpi", "at", "8", "5", "affects", "the", "spy", "heavily"]
        ),
    ]
)
def test_tokenize(memory_instance, input_text, expected_tokens):
    """Test the _tokenize method handles various strings correctly."""
    tokens = memory_instance._tokenize(input_text)
    assert tokens == expected_tokens
