# Logging Quick Reference Guide

## Quick Start

```python
from tradingagents.utils.logging_config import (
    get_logger,
    get_api_logger,
    get_performance_logger,
    configure_logging,
)

# Initialize (done once at startup)
configure_logging(level="INFO", console=True)

# Get loggers
logger = get_logger("tradingagents.component", component="COMPONENT")
api_logger = get_api_logger()
perf_logger = get_performance_logger()
```

## Basic Logging

### Simple Messages
```python
logger.debug("Detailed debugging information")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
logger.critical("Critical error")
```

### With Context
```python
logger.info(
    "Operation completed",
    extra={
        "context": {
            "operation": "analysis",
            "duration_ms": 1234.5,
            "items_processed": 42
        }
    }
)
```

### With Exceptions
```python
try:
    # some operation
    pass
except Exception as e:
    logger.error(
        f"Operation failed: {e}",
        extra={"context": {"error_type": type(e).__name__}},
        exc_info=True  # Include stack trace
    )
```

## API Call Logging

```python
api_logger.log_call(
    provider="openai",
    model="gpt-4o-mini",
    endpoint="/v1/chat/completions",
    tokens=150,
    cost=0.0015,
    duration=1234.5,
    status="success"
)

# Get statistics
stats = api_logger.get_stats()
# Returns: {"total_calls": 3, "total_tokens": 650}
```

## Performance Logging

```python
import time

start = time.time()
# ... do work ...
duration_ms = (time.time() - start) * 1000

perf_logger.log_timing(
    "operation_name",
    duration_ms,
    context={"details": "value"}
)

# Get average timing
avg = perf_logger.get_average_timing("operation_name")

# Log summary
perf_logger.log_summary()
```

## Log Levels

| Level    | When to Use                                    | Example                          |
|----------|------------------------------------------------|----------------------------------|
| DEBUG    | Detailed diagnostic information                | Variable values, loop iterations |
| INFO     | Confirmation things are working as expected    | Session start, completion        |
| WARNING  | Something unexpected but handled               | Deprecated API, fallback used    |
| ERROR    | Serious problem that needs attention           | Failed operation, exception      |
| CRITICAL | System failure, app may crash                  | Fatal error, out of resources    |

## Log Files

| File                  | Contents                          | Level  |
|-----------------------|-----------------------------------|--------|
| tradingagents.log     | All logs                          | DEBUG+ |
| api_calls.log         | API tracking                      | INFO+  |
| memory.log            | Memory operations                 | INFO+  |
| agents.log            | Agent activities                  | INFO+  |
| errors.log            | Errors only                       | ERROR+ |
| performance.log       | Performance metrics               | INFO+  |

## Configuration

### Change Log Level
```python
from tradingagents.utils.logging_config import set_log_level

set_log_level("DEBUG")  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Configure at Startup
```python
configure_logging(
    level="INFO",           # Log level
    log_dir="logs",         # Directory for log files
    console=True           # Enable/disable console output
)
```

### Custom Component Logger
```python
# Creates logger: tradingagents.myapp
logger = get_logger("tradingagents.myapp", component="MYAPP")

# Logs appear as:
# 2025-01-15 10:30:00 | INFO | MYAPP | Message here
```

## Common Patterns

### Session Start/End
```python
logger.info("=" * 70)
logger.info("Session Started")
logger.info("=" * 70)

# ... work ...

logger.info("Session completed", extra={
    "context": {"duration_ms": duration, "results": count}
})
```

### Track State Changes
```python
logger.info(
    f"State changed: {old_state} -> {new_state}",
    extra={
        "context": {
            "old_state": old_state,
            "new_state": new_state,
            "reason": "user_action"
        }
    }
)
```

### Tool/Function Calls
```python
logger.info(
    f"Calling tool: {tool_name}",
    extra={
        "context": {
            "tool": tool_name,
            "args": args_dict,
            "timestamp": timestamp
        }
    }
)
```

### Report Generation
```python
logger.info(
    f"Report generated: {section_name}",
    extra={
        "context": {
            "section": section_name,
            "file": str(file_path),
            "content_length": len(content)
        }
    }
)
```

### Performance Timing
```python
import time

start = time.time()
result = expensive_operation()
duration = (time.time() - start) * 1000

perf_logger.log_timing(
    "expensive_operation",
    duration,
    context={"result_size": len(result)}
)
```

## CLI Integration Examples

### MessageBuffer Logging
```python
class MessageBuffer:
    def __init__(self):
        self.logger = get_logger("tradingagents.cli.buffer", component="BUFFER")
    
    def add_message(self, message_type, content):
        # ... add message ...
        self.logger.debug(
            f"Message added: {message_type}",
            extra={"context": {"type": message_type}}
        )
```

### Analysis Session
```python
def run_analysis():
    start_time = time.time()
    cli_logger.info("Starting trading analysis session")
    
    # ... analysis work ...
    
    total_duration = (time.time() - start_time) * 1000
    cli_logger.info(
        "Analysis completed",
        extra={"context": {"duration_ms": total_duration}}
    )
```

## Viewing Logs

### Tail Live Logs
```bash
tail -f logs/tradingagents.log
```

### View Errors Only
```bash
cat logs/errors.log
```

### Search Logs
```bash
# Find specific ticker
grep "AAPL" logs/tradingagents.log

# Find errors
grep "ERROR" logs/tradingagents.log

# Find performance issues (>10 seconds)
grep "duration_ms.*[1-9][0-9]\{4,\}" logs/performance.log
```

### Filter by Component
```bash
grep "| CLI |" logs/tradingagents.log
grep "| BUFFER |" logs/tradingagents.log
grep "| API |" logs/tradingagents.log
```

### Filter by Date/Time
```bash
grep "2025-01-15 10:" logs/tradingagents.log
```

## Troubleshooting

### No Logs Appearing
1. Check logging is initialized: `configure_logging(level="INFO")`
2. Check log level isn't too high: `set_log_level("INFO")`
3. Check log directory exists: `ls -la logs/`

### Log Files Too Large
- System uses automatic rotation (10MB default)
- Check backup count: look for `.log.1`, `.log.2`, etc.
- Increase rotation settings in `logging_config.py`

### Missing Context in Logs
```python
# Bad - no context
logger.info("Analysis done")

# Good - with context
logger.info(
    "Analysis done",
    extra={
        "context": {
            "ticker": "AAPL",
            "duration_ms": 1234.5
        }
    }
)
```

### Performance Impact
- File logging is asynchronous and minimal
- DEBUG level has most overhead
- Use INFO or WARNING in production
- Disable console logging if needed: `configure_logging(console=False)`

## Best Practices

✅ **DO**
- Use appropriate log levels
- Include context in extra parameter
- Log at key decision points
- Use structured context (dicts)
- Enable exc_info for exceptions
- Use consistent component names

❌ **DON'T**
- Log sensitive data (passwords, keys)
- Log in tight loops (use sampling)
- Use print() instead of logger
- Log without context
- Ignore log rotation limits
- Mix logging and print statements

## Example: Complete Integration

```python
from tradingagents.utils.logging_config import (
    get_logger,
    get_api_logger,
    get_performance_logger,
    configure_logging,
)
import time

# Initialize
configure_logging(level="INFO", console=True)
logger = get_logger("tradingagents.mymodule", component="MYMODULE")
api_logger = get_api_logger()
perf_logger = get_performance_logger()

def process_data(data):
    """Process data with comprehensive logging."""
    start = time.time()
    
    logger.info("Starting data processing", extra={
        "context": {"items": len(data)}
    })
    
    try:
        # Simulate API call
        api_start = time.time()
        result = call_api(data)
        api_duration = (time.time() - api_start) * 1000
        
        api_logger.log_call(
            provider="openai",
            model="gpt-4o-mini",
            endpoint="/v1/chat/completions",
            tokens=150,
            duration=api_duration,
            status="success"
        )
        
        # Process result
        processed = transform(result)
        
        # Log completion
        total_duration = (time.time() - start) * 1000
        perf_logger.log_timing("process_data", total_duration)
        
        logger.info("Processing completed", extra={
            "context": {
                "items_processed": len(processed),
                "duration_ms": total_duration
            }
        })
        
        return processed
        
    except Exception as e:
        logger.error(
            f"Processing failed: {e}",
            extra={"context": {"error_type": type(e).__name__}},
            exc_info=True
        )
        raise

# Log performance summary at end
perf_logger.log_summary()
```

## Summary

The comprehensive logging system provides:
- 🎯 Structured, contextual logs
- 📊 Performance tracking
- 💰 API cost monitoring  
- 🔍 Easy debugging
- 📁 Organized log files
- 🔄 Automatic rotation
- ⚡ Minimal overhead

For detailed documentation, see `docs/CLI_LOGGING_INTEGRATION.md`
