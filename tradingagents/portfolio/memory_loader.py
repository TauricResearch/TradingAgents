from pathlib import Path
from tradingagents.portfolio.lesson_store import LessonStore
from tradingagents.agents.utils.memory import FinancialSituationMemory

def load_into_memory(lesson_store: LessonStore,
                     memory: FinancialSituationMemory) -> int:
    """Populate memory with ONLY negative-sentiment lessons. Returns count loaded."""
    lessons = lesson_store.load_all()
    pairs = [
        (l.get("situation", ""), l.get("screening_advice", l.get("advice", "")))
        for l in lessons
        if l.get("sentiment") == "negative"
    ]
    if pairs:
        memory.add_situations(pairs)
    return len(pairs)

def build_selection_memory(path: Path | None = None) -> FinancialSituationMemory:
    """Convenience: LessonStore + FinancialSituationMemory + load. Used by CLI."""
    store = LessonStore(path)
    memory = FinancialSituationMemory("selection_memory")
    load_into_memory(store, memory)
    return memory
