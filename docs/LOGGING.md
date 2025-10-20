# Comprehensive Logging System Documentation

**TradingAgents Logging System v1.0**

---

## Overview

TradingAgents now includes a comprehensive, production-ready logging system that provides:

- **Structured Logging**: Context-rich log messages with metadata
- **Multiple Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **File and Console Output**: Separate handlers for different purposes
- **Log Rotation**: Automatic file rotation to prevent disk space issues
- **Component-Specific Loggers**: Dedicated loggers for different parts of the system
- **Performance Tracking**: Built-in performance metrics and timing
- **API Call Tracking**: Monitor API usage, costs, and errors
- **Easy Configuration**: Simple setup with sensible defaults

---

## Quick Start

### Basic Usage

```python
from tradingagents.utils import get_logger

# Get a logger for your component
logger = get_logger("tradingagents.my_component", component="MY_COMP")

# Log messages at different levels
logger.debug("Detailed debugging information")
logger.info("General information about execution")
logger.warning("Warning about potential issues")
logger.error("Error occurred but execution continues")
logger.critical("Critical error, system may be unstable")
```

### With Context

```python
logger.info(
    "Processing trade decision",
    extra={
        "context": {
            "ticker": "AAPL",
            "decision": "BUY",
            "confidence": 0.85,
            "timestamp": "2025-01-15T10:30:00Z"
        }
    }
)
```

---

## Configuration

### Using Default Configuration

The logging system initializes automatically with defaults:

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

# Logging is automatically configured
graph = TradingAgentsGraph(["market", "news"])
```

### Custom Configuration

Configure logging settings in your config dictionary:

```python
config = {
    # ... other config ...
    
    # Logging settings
    "log_level": "DEBUG",           # More verbose logging
    "log_dir": "custom_logs",       # Custom log directory
    "log_to_console": True,         # Enable console output
    "log_to_file": True,            # Enable file output
}

graph = TradingAgentsGraph(["market"], config=config)
```

### Programmatic Configuration

```python
from tradingagents.utils import configure_logging, set_log_level

# Configure at application startup
configure_logging(
    level="INFO",              # Log level
    log_dir="my_logs",         # Custom directory
    console=True               # Console output
)

# Change log level at runtime
set_log_level("DEBUG")
```

---

## Log Levels

### DEBUG
**Use for**: Detailed diagnostic information

```python
logger.debug("Entering function with params: ticker=AAPL, date=2025-01-15")
logger.debug(f"Intermediate calculation: value={intermediate_result}")
```

**Output**: Only to log files (not console by default)

### INFO
**Use for**: General informational messages

```python
logger.info("Memory enabled with provider: openai")
logger.info("Propagation complete for AAPL")
```

**Output**: Console and log files

### WARNING
**Use for**: Potential issues that don't prevent execution

```python
logger.warning("Failed to get embedding for situation, skipping")
logger.warning("API rate limit approaching")
```

**Output**: Console and log files

### ERROR
**Use for**: Errors that prevent specific operations

```python
logger.error("Failed to initialize ChromaDB collection: Connection timeout")
logger.error(f"API call failed: {error_message}")
```

**Output**: Console, main log file, and errors.log

### CRITICAL
**Use for**: Severe errors that may crash the system

```python
logger.critical("Unable to initialize any LLM provider")
logger.critical("Database corruption detected")
```

**Output**: All handlers, highlighted in console

---

## Log Files

The logging system creates separate log files in the `logs/` directory:

### Main Logs

| File | Purpose | Rotation | Levels |
|------|---------|----------|--------|
| `tradingagents.log` | All application logs | 10 MB, 5 backups | DEBUG+ |
| `errors.log` | Errors only | 5 MB, 3 backups | ERROR+ |
| `api_calls.log` | API call tracking | 10 MB, 3 backups | INFO+ |
| `memory.log` | Memory operations | 10 MB, 3 backups | DEBUG+ |
| `agents.log` | Agent execution | 10 MB, 3 backups | INFO+ |
| `performance.log` | Performance metrics | 10 MB, 3 backups | INFO+ |

### Log Rotation

Files automatically rotate when they reach the size limit:

```
tradingagents.log       # Current
tradingagents.log.1     # Previous
tradingagents.log.2     # Older
...
tradingagents.log.5     # Oldest (then deleted)
```

---

## Specialized Loggers

### API Call Logger

Track all API calls with detailed metrics:

```python
from tradingagents.utils import get_api_logger

api_logger = get_api_logger()

# Log successful API call
api_logger.log_call(
    provider="openai",
    model="gpt-4",
    endpoint="/v1/chat/completions",
    tokens=150,
    cost=0.003,
    duration=250.5,
    status="success"
)

# Log failed API call
api_logger.log_call(
    provider="openrouter",
    model="llama-3",
    endpoint="/v1/chat/completions",
    status="error",
    error="Connection timeout"
)

# Get statistics
stats = api_logger.get_stats()
print(f"Total calls: {stats['total_calls']}")
print(f"Total tokens: {stats['total_tokens']}")
```

**Output Format**:
```
2025-01-15 10:30:15 | INFO     | API             | API call to openai/gpt-4 - success
  Context: {
    "call_number": 42,
    "provider": "openai",
    "model": "gpt-4",
    "endpoint": "/v1/chat/completions",
    "tokens": 150,
    "cost": 0.003,
    "duration_ms": 250.5,
    "status": "success"
  }
```

### Performance Logger

Track operation timings and generate performance reports:

```python
from tradingagents.utils import get_performance_logger
import time

perf_logger = get_performance_logger()

# Log operation timing
start = time.time()
# ... do something ...
duration = (time.time() - start) * 1000

perf_logger.log_timing(
    "analyst_execution",
    duration,
    context={"analyst": "market", "ticker": "AAPL"}
)

# Get average timing
avg = perf_logger.get_average_timing("analyst_execution")
print(f"Average time: {avg:.2f}ms")

# Log performance summary
perf_logger.log_summary()
```

**Summary Output**:
```
2025-01-15 10:35:00 | INFO     | PERF            | Performance Summary
  Context: {
    "analyst_execution": {
      "count": 10,
      "avg_ms": 1234.5,
      "min_ms": 987.3,
      "max_ms": 2100.8
    },
    "embedding_generation": {
      "count": 25,
      "avg_ms": 45.2,
      "min_ms": 32.1,
      "max_ms": 78.9
    }
  }
```

---

## Log Format

### Console Output

```
2025-01-15 10:30:15 | INFO     | MEMORY          | Added 5 situations to 'bull_memory'
2025-01-15 10:30:16 | WARNING  | MEMORY          | Failed to get embedding for situation 3, skipping
2025-01-15 10:30:17 | ERROR    | API             | API call failed: Connection timeout
```

Format: `{timestamp} | {level} | {component} | {message}`

### File Output

```
2025-01-15T10:30:15.123456 | INFO     | tradingagents.memory | MEMORY | Added 5 situations to 'bull_memory'
  Context: {
    "collection": "bull_memory",
    "count": 5,
    "total_in_collection": 15,
    "duration_ms": 123.45
  }
```

Format: `{timestamp} | {level} | {logger_name} | {component} | {message}`

---

## Examples

### Memory Operations

```python
from tradingagents.agents.utils.memory import FinancialSituationMemory

config = {
    "embedding_provider": "openai",
    "enable_memory": True,
}

memory = FinancialSituationMemory("test_memory", config)

# Logs:
# INFO | MEMORY | Initialized embedding client for 'test_memory'
# INFO | MEMORY | Initialized ChromaDB collection 'test_memory'

# Add situations
memory.add_situations([
    ("High volatility", "Reduce positions"),
    ("Strong uptrend", "Scale in")
])

# Logs:
# DEBUG | MEMORY | Generated embedding for text (15 chars)
# DEBUG | MEMORY | Generated embedding for text (14 chars)
# INFO  | MEMORY | Added 2 situations to 'test_memory'
# INFO  | API    | API call to openai/text-embedding-3-small - success

# Query memories
results = memory.get_memories("Market showing volatility", n_matches=1)

# Logs:
# DEBUG | MEMORY | Generated embedding for text (27 chars)
# INFO  | MEMORY | Retrieved 1 memories from 'test_memory'
# INFO  | PERF   | get_memories completed in 45.23ms
```

### Trading Graph Execution

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

graph = TradingAgentsGraph(["market", "news"])

# Logs:
# INFO | GRAPH | Initializing TradingAgentsGraph
# INFO | GRAPH | Initializing chat LLMs with provider: openai
# INFO | GRAPH | Memory enabled with provider: openai
# INFO | MEMORY | Initialized embedding client for 'bull_memory'
# INFO | MEMORY | Initialized embedding client for 'bear_memory'
# ...
# INFO | GRAPH | TradingAgentsGraph initialization complete

# Run analysis
final_state, decision = graph.propagate("AAPL", "2025-01-15")

# Logs:
# INFO  | GRAPH | Starting propagation for AAPL on 2025-01-15
# DEBUG | GRAPH | Starting graph execution
# DEBUG | GRAPH | Running in standard mode
# INFO  | GRAPH | Propagation complete for AAPL
# INFO  | PERF  | propagation completed in 5432.1ms
```

### Error Handling

```python
# Failed API call
try:
    response = client.embeddings.create(...)
except Exception as e:
    logger.error(
        f"Failed to get embedding: {e}",
        extra={
            "context": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "error": str(e)
            }
        }
    )
    
# Logs:
# ERROR | MEMORY | Failed to get embedding: 401 Unauthorized
#   Context: {
#     "provider": "openai",
#     "model": "text-embedding-3-small",
#     "error": "401 Unauthorized"
#   }
# ERROR | API | API call to openai/text-embedding-3-small - error
#   Context: {
#     "provider": "openai",
#     "model": "text-embedding-3-small",
#     "endpoint": "embeddings.create",
#     "status": "error",
#     "error": "401 Unauthorized"
#   }
```

---

## Best Practices

### 1. Use Appropriate Log Levels

```python
# ✅ Good
logger.debug(f"Processing item {i} of {total}")  # Detailed info
logger.info("Analysis complete")                 # Important milestone
logger.warning("API rate limit at 80%")          # Potential issue
logger.error("Failed to connect to database")    # Actual error

# ❌ Bad
logger.info(f"i={i}, j={j}, k={k}")             # Too detailed for INFO
logger.error("Successfully completed task")      # Wrong level
```

### 2. Include Context

```python
# ✅ Good - Rich context
logger.info(
    "Trade decision made",
    extra={
        "context": {
            "ticker": "AAPL",
            "decision": "BUY",
            "confidence": 0.85,
            "price": 150.50
        }
    }
)

# ❌ Bad - No context
logger.info("Trade decision made")
```

### 3. Log Performance Metrics

```python
# ✅ Good - Track timing
start_time = time.time()
result = expensive_operation()
duration = (time.time() - start_time) * 1000

perf_logger.log_timing(
    "expensive_operation",
    duration,
    context={"items_processed": len(result)}
)

# ❌ Bad - No performance tracking
result = expensive_operation()
```

### 4. Log API Calls

```python
# ✅ Good - Track all API interactions
try:
    start_time = time.time()
    response = api_client.call(...)
    duration = (time.time() - start_time) * 1000
    
    api_logger.log_call(
        provider="openai",
        model="gpt-4",
        endpoint="/v1/chat",
        tokens=response.usage.total_tokens,
        duration=duration,
        status="success"
    )
except Exception as e:
    api_logger.log_call(
        provider="openai",
        model="gpt-4",
        endpoint="/v1/chat",
        status="error",
        error=str(e)
    )

# ❌ Bad - No API tracking
response = api_client.call(...)
```

### 5. Use Component Names

```python
# ✅ Good - Component identification
logger = get_logger("tradingagents.analyst.market", component="MARKET_ANALYST")

# ❌ Bad - Generic logger
logger = get_logger("tradingagents")
```

---

## Troubleshooting

### Logs Not Appearing

**Problem**: No logs in console or files

**Solution**:
1. Check log level: `set_log_level("DEBUG")`
2. Verify log directory exists and is writable
3. Check if logging was configured: `configure_logging(level="INFO")`

### Too Many Log Files

**Problem**: Log directory growing too large

**Solution**:
1. Reduce backup count in logging_config.py
2. Increase rotation size to rotate less frequently
3. Set up log cleanup cron job

### Performance Impact

**Problem**: Logging slowing down application

**Solution**:
1. Increase log level to WARNING or ERROR
2. Disable console logging: `configure_logging(console=False)`
3. Use async logging (future enhancement)

### Missing Context

**Problem**: Log messages don't show context dict

**Solution**:
1. Ensure you're using `extra={"context": {...}}`
2. Check that StructuredFormatter is being used
3. Verify logger is from TradingAgents system

---

## Advanced Usage

### Custom Logger Configuration

```python
from tradingagents.utils.logging_config import TradingAgentsLogger

# Get logger instance
logger_system = TradingAgentsLogger()

# Add custom file handler
logger_system.add_file_handler(
    logger_name="tradingagents.custom",
    filename="custom_component.log",
    level=logging.INFO
)

# Get logger
logger = logger_system.get_logger(
    "tradingagents.custom",
    component="CUSTOM"
)
```

### Filtering Logs

View only specific components:

```bash
# Only memory logs
grep "MEMORY" logs/tradingagents.log

# Only errors
cat logs/errors.log

# API calls for specific provider
grep "openai" logs/api_calls.log
```

### Log Analysis

```bash
# Count error types
grep "ERROR" logs/tradingagents.log | cut -d'|' -f4 | sort | uniq -c

# API call statistics
grep "API call to" logs/api_calls.log | wc -l

# Performance summary
grep "Performance Summary" logs/performance.log -A 20
```

---

## Testing

### Test Logging System

```bash
# Run logging system tests
python -m tradingagents.utils.logging_config

# Output:
# Testing TradingAgents Logging System
# ======================================================================
# 2025-01-15 10:30:00 | INFO     | TEST | This is an info message
# 2025-01-15 10:30:00 | WARNING  | TEST | This is a warning message
# 2025-01-15 10:30:00 | ERROR    | TEST | This is an error message
# ...
# Logging test complete. Check the 'logs' directory for output files.
```

### Verify Log Files

```bash
# Check log directory
ls -lh logs/

# Output:
# -rw-r--r-- tradingagents.log
# -rw-r--r-- api_calls.log
# -rw-r--r-- errors.log
# -rw-r--r-- performance.log
```

---

## Configuration Reference

### Config Parameters

```python
DEFAULT_CONFIG = {
    # Logging settings
    "log_level": "INFO",           # DEBUG, INFO, WARNING, ERROR, CRITICAL
    "log_dir": "logs",             # Directory for log files
    "log_to_console": True,        # Enable console output
    "log_to_file": True,           # Enable file output
}
```

### Environment Variables

```bash
# Override log level
export TRADINGAGENTS_LOG_LEVEL=DEBUG

# Override log directory
export TRADINGAGENTS_LOG_DIR=/var/log/tradingagents
```

---

## API Reference

### get_logger()

```python
def get_logger(name: str = "tradingagents", component: Optional[str] = None) -> logging.Logger
```

Get a configured logger instance.

**Parameters**:
- `name`: Logger name (default: "tradingagents")
- `component`: Component name for context (optional)

**Returns**: Configured logger instance

### get_api_logger()

```python
def get_api_logger() -> APICallLogger
```

Get the API call tracking logger.

**Returns**: APICallLogger instance

### get_performance_logger()

```python
def get_performance_logger() -> PerformanceLogger
```

Get the performance tracking logger.

**Returns**: PerformanceLogger instance

### configure_logging()

```python
def configure_logging(
    level: str = "INFO",
    log_dir: Optional[str] = None,
    console: bool = True
)
```

Configure the logging system.

**Parameters**:
- `level`: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `log_dir`: Directory for log files
- `console`: Whether to log to console

### set_log_level()

```python
def set_log_level(level: str)
```

Set the global log level.

**Parameters**:
- `level`: Log level string

---

## Migration from Print Statements

### Before

```python
print(f"Memory enabled with provider: {provider}")
print(f"Added {count} situations")
print(f"ERROR: Failed to connect: {error}")
```

### After

```python
logger.info(
    f"Memory enabled with provider: {provider}",
    extra={"context": {"provider": provider}}
)

logger.info(
    f"Added {count} situations",
    extra={"context": {"count": count}}
)

logger.error(
    f"Failed to connect: {error}",
    extra={"context": {"error": str(error)}}
)
```

---

## Future Enhancements

Planned improvements:

- [ ] Async logging for better performance
- [ ] Cloud logging integration (CloudWatch, Stackdriver)
- [ ] Real-time log streaming dashboard
- [ ] Log aggregation and analytics
- [ ] Structured JSON logging option
- [ ] Log compression for archived files
- [ ] Email alerts for critical errors
- [ ] Slack/Discord notifications

---

## Support

For questions or issues with the logging system:

1. Check this documentation
2. Review log files in `logs/` directory
3. Test with `python -m tradingagents.utils.logging_config`
4. Open GitHub issue with log samples

---

**Version**: 1.0  
**Last Updated**: 2025-01-15  
**Status**: Production Ready ✅