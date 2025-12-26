---
name: observability
version: 1.0.0
type: knowledge
description: Structured logging, debugging techniques (pdb/ipdb), profiling (cProfile/line_profiler), stack traces, performance monitoring, and metrics. Use when adding logging, debugging issues, or optimizing performance.
keywords: logging, debug, profiling, performance, monitoring, metrics, pdb, cProfile, observability, tracing
auto_activate: true
allowed-tools: [Read, Grep, Glob, Bash]
---

# Observability Skill

Comprehensive guide to logging, debugging, profiling, and performance monitoring in Python applications.

## When This Skill Activates

- Adding logging to code
- Debugging production issues
- Profiling performance bottlenecks
- Monitoring application metrics
- Analyzing stack traces
- Performance optimization
- Keywords: "logging", "debug", "profiling", "performance", "monitoring"

---

## Core Concepts

### 1. Structured Logging

Structured logging with JSON format for machine-readable logs and rich context.

**Why Structured Logging?**
- Machine-parseable (easy to search, filter, aggregate)
- Context-rich (attach metadata to log entries)
- Consistent format across services

**Key Features**:
- JSON-formatted logs
- Log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Context logging with extra metadata
- Best practices for meaningful logs

**Example**:
```python
import logging
import json

logger = logging.getLogger(__name__)
logger.info("User action", extra={
    "user_id": 123,
    "action": "login",
    "ip": "192.168.1.1"
})
```

**See**: `docs/structured-logging.md` for Python logging setup and patterns

---

### 2. Debugging Techniques

Interactive debugging with pdb/ipdb and effective debugging strategies.

**Tools**:
- **Print debugging** - Quick and simple
- **pdb** - Python's built-in debugger
- **ipdb** - IPython-enhanced debugger
- **Post-mortem debugging** - Debug after crash

**pdb Commands**:
- `n` (next) - Execute current line
- `s` (step) - Step into function
- `c` (continue) - Continue execution
- `p variable` - Print variable value
- `l` - List source code
- `q` - Quit debugger

**Example**:
```python
import pdb; pdb.set_trace()  # Debugger starts here
```

**See**: `docs/debugging.md` for interactive debugging patterns

---

### 3. Profiling

CPU and memory profiling to identify performance bottlenecks.

**Tools**:
- **cProfile** - CPU profiling (built-in)
- **line_profiler** - Line-by-line CPU profiling
- **memory_profiler** - Memory usage analysis
- **py-spy** - Sampling profiler (no code changes)

**cProfile Example**:
```bash
python -m cProfile -s cumulative script.py
```

**Profile Decorator**:
```python
import cProfile
import pstats

def profile(func):
    def wrapper(*args, **kwargs):
        profiler = cProfile.Profile()
        profiler.enable()
        result = func(*args, **kwargs)
        profiler.disable()
        stats = pstats.Stats(profiler)
        stats.sort_stats('cumulative')
        stats.print_stats(10)  # Top 10 functions
        return result
    return wrapper

@profile
def slow_function():
    # Your code here
    pass
```

**See**: `docs/profiling.md` for comprehensive profiling techniques

---

### 4. Monitoring & Metrics

Performance monitoring, timing decorators, and simple metrics.

**Timing Patterns**:
- **Timing decorator** - Measure function execution time
- **Context manager timer** - Measure code block duration
- **Performance assertions** - Fail if too slow

**Simple Metrics**:
- **Counters** - Track event occurrences
- **Histograms** - Track value distributions

**Example**:
```python
import time
from functools import wraps

def timer(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        print(f"{func.__name__} took {duration:.2f}s")
        return result
    return wrapper

@timer
def process_data():
    # Your code here
    pass
```

**See**: `docs/monitoring-metrics.md` for stack traces, timers, and metrics

---

### 5. Best Practices & Anti-Patterns

Debugging strategies and logging anti-patterns to avoid.

**Debugging Best Practices**:
1. **Binary Search Debugging** - Narrow down the problem area
2. **Rubber Duck Debugging** - Explain the problem to someone (or something)
3. **Add Assertions** - Catch bugs early
4. **Simplify and Isolate** - Reproduce with minimal code

**Logging Anti-Patterns to Avoid**:
- Logging sensitive data (passwords, tokens)
- Logging in loops (use counters instead)
- No context in error logs
- Inconsistent log formats
- Too verbose logging (noise)

**See**: `docs/best-practices-antipatterns.md` for detailed strategies

---

## Quick Reference

| Tool | Use Case | Details |
|------|----------|---------|
| Structured Logging | Production logs | `docs/structured-logging.md` |
| pdb/ipdb | Interactive debugging | `docs/debugging.md` |
| cProfile | CPU profiling | `docs/profiling.md` |
| line_profiler | Line-by-line profiling | `docs/profiling.md` |
| memory_profiler | Memory analysis | `docs/profiling.md` |
| Timer decorator | Function timing | `docs/monitoring-metrics.md` |
| Context timer | Code block timing | `docs/monitoring-metrics.md` |

---

## Logging Cheat Sheet

```python
import logging

# Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Usage
logger.debug("Debug message")       # Detailed diagnostic
logger.info("Info message")         # General information
logger.warning("Warning message")   # Warning (recoverable)
logger.error("Error message")       # Error (handled)
logger.critical("Critical message") # Critical (unrecoverable)

# With context
logger.info("User action", extra={"user_id": 123, "action": "login"})
```

---

## Debugging Cheat Sheet

```python
# pdb
import pdb; pdb.set_trace()

# ipdb (enhanced)
import ipdb; ipdb.set_trace()

# Post-mortem (debug after crash)
import pdb, sys
try:
    # Your code
    pass
except Exception:
    pdb.post_mortem(sys.exc_info()[2])
```

---

## Profiling Cheat Sheet

```bash
# CPU profiling
python -m cProfile -s cumulative script.py

# Line profiling
kernprof -l -v script.py

# Memory profiling
python -m memory_profiler script.py

# Sampling profiler (no code changes)
py-spy top --pid 12345
```

---

## Progressive Disclosure

This skill uses progressive disclosure to prevent context bloat:

- **Index** (this file): High-level concepts and quick reference (<500 lines)
- **Detailed docs**: `docs/*.md` files with implementation details (loaded on-demand)

**Available Documentation**:
- `docs/structured-logging.md` - Logging setup, levels, JSON format, best practices
- `docs/debugging.md` - Print debugging, pdb/ipdb, post-mortem debugging
- `docs/profiling.md` - cProfile, line_profiler, memory_profiler, py-spy
- `docs/monitoring-metrics.md` - Stack traces, timing patterns, simple metrics
- `docs/best-practices-antipatterns.md` - Debugging strategies and logging anti-patterns

---

## Cross-References

**Related Skills**:
- **error-handling-patterns** - Error handling best practices
- **python-standards** - Python coding conventions
- **testing-guide** - Testing and debugging strategies
- **performance-optimization** - Performance tuning techniques

**Related Tools**:
- **Python logging** - Standard library logging module
- **pdb/ipdb** - Interactive debuggers
- **cProfile** - CPU profiling
- **memory_profiler** - Memory analysis
- **py-spy** - Sampling profiler

---

## Key Takeaways

1. **Use structured logging** - JSON format for machine-readable logs
2. **Log at appropriate levels** - DEBUG < INFO < WARNING < ERROR < CRITICAL
3. **Include context** - Add metadata to logs (user_id, request_id, etc.)
4. **Don't log sensitive data** - Passwords, tokens, PII
5. **Use pdb/ipdb for debugging** - Interactive debugging is powerful
6. **Profile before optimizing** - Measure to find real bottlenecks
7. **Use cProfile for CPU profiling** - Identify slow functions
8. **Use line_profiler for line-level profiling** - Fine-grained analysis
9. **Use memory_profiler for memory leaks** - Track memory usage
10. **Time critical sections** - Decorator or context manager
11. **Binary search debugging** - Narrow down problem area
12. **Simplify and isolate** - Reproduce with minimal code
