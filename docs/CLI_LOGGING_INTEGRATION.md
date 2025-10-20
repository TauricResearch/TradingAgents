# CLI Logging Integration Documentation

## Overview

The TradingAgents CLI has been enhanced with comprehensive logging capabilities using the centralized logging system. This provides structured logging, performance tracking, and better debugging capabilities.

## Key Features

### 1. Comprehensive Logging System Integration

The CLI now uses the centralized logging system from `tradingagents.utils.logging_config`, providing:

- **Structured Logging**: All log entries include context information
- **Multiple Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **File and Console Output**: Logs are written to both files and console
- **Log Rotation**: Automatic rotation prevents log files from growing too large
- **Component-Specific Loggers**: Different components have dedicated loggers

### 2. Log Files

The system generates multiple log files in the `logs/` directory:

```
logs/
├── tradingagents.log       # Main application log (all levels)
├── api_calls.log           # API call tracking with costs
├── memory.log              # Memory system operations
├── agents.log              # Agent-specific activities
├── errors.log              # Error-only log (ERROR and CRITICAL)
└── performance.log         # Performance metrics and timings
```

Additionally, each analysis creates session-specific logs:

```
results/{ticker}/{date}/
├── message_tool.log        # Legacy message and tool call log
└── reports/
    ├── market_report.md
    ├── sentiment_report.md
    └── ...
```

### 3. Logging Components

#### CLI Logger
Main logger for CLI operations:
```python
cli_logger = get_logger("tradingagents.cli", component="CLI")
```

Logs:
- User selections and configuration
- Analysis session start/end
- Graph initialization
- Results directory creation
- Report generation
- Errors and exceptions

#### MessageBuffer Logger
Buffer-specific logger for tracking agent messages:
```python
self.logger = get_logger("tradingagents.cli.buffer", component="BUFFER")
```

Logs:
- Message additions with types
- Tool call registrations
- Agent status changes
- Report section updates

#### API Logger
Tracks all API calls:
```python
api_logger = get_api_logger()
```

Logs:
- API provider and model
- Token usage and costs
- Request duration
- Success/failure status
- Error messages

#### Performance Logger
Tracks timing and performance metrics:
```python
perf_logger = get_performance_logger()
```

Logs:
- Operation durations
- Performance summaries
- Statistical analysis (min, max, avg)

## Usage Examples

### Starting an Analysis Session

When you run an analysis, the CLI logs:

```
2024-01-15 10:30:00 | INFO     | CLI             | Starting trading analysis session
2024-01-15 10:30:05 | INFO     | CLI             | User selections received
  Context: {
    "ticker": "AAPL",
    "date": "2024-01-15",
    "analysts": ["market", "social", "news"],
    "research_depth": 3,
    "llm_provider": "openai"
  }
2024-01-15 10:30:06 | INFO     | CLI             | Initializing TradingAgents graph
2024-01-15 10:30:07 | INFO     | CLI             | Results directory created: results/AAPL/2024-01-15
```

### Agent Status Updates

```
2024-01-15 10:30:10 | INFO     | BUFFER          | Agent status updated: Market Analyst -> in_progress
  Context: {
    "agent": "Market Analyst",
    "old_status": "pending",
    "new_status": "in_progress"
  }
```

### Tool Calls

```
2024-01-15 10:30:15 | INFO     | BUFFER          | Tool call registered: get_stock_data
  Context: {
    "tool": "get_stock_data",
    "args": {"ticker": "AAPL", "period": "1mo"},
    "timestamp": "10:30:15"
  }
```

### Report Section Generation

```
2024-01-15 10:35:20 | INFO     | CLI             | Report section generated: market_report
  Context: {
    "section": "market_report",
    "file": "results/AAPL/2024-01-15/reports/market_report.md",
    "content_length": 2543
  }
```

### Analysis Completion

```
2024-01-15 10:45:30 | INFO     | CLI             | Analysis completed successfully
  Context: {
    "ticker": "AAPL",
    "date": "2024-01-15",
    "duration_ms": 903421.5,
    "chunks_processed": 47
  }
2024-01-15 10:45:30 | INFO     | PERF            | total_analysis_session completed in 903421.50ms
  Context: {
    "operation": "total_analysis_session",
    "duration_ms": 903421.5
  }
```

### Error Handling

```
2024-01-15 10:30:45 | ERROR    | CLI             | Analysis failed with error: Connection timeout
  Context: {
    "error_type": "TimeoutError"
  }
  Traceback (most recent call last):
    ...
```

## Configuration

### Log Level

Configure the logging level when starting the CLI:

```python
# In cli/main.py
configure_logging(level="INFO", console=True)
```

Available levels:
- `DEBUG`: Detailed information for debugging
- `INFO`: General information about progress (default)
- `WARNING`: Warning messages
- `ERROR`: Error messages
- `CRITICAL`: Critical errors

### Console Output

To disable console logging:

```python
configure_logging(level="INFO", console=False)
```

### Custom Log Directory

```python
configure_logging(level="INFO", log_dir="custom/log/path")
```

## Benefits

### 1. Better Debugging
- Structured context makes it easy to trace issues
- Timestamps and component labels help identify problem areas
- Full stack traces for exceptions

### 2. Performance Monitoring
- Track operation durations
- Identify bottlenecks
- Statistical summaries of performance metrics

### 3. Audit Trail
- Complete record of all operations
- Tool call history
- Agent status transitions
- API usage tracking

### 4. Cost Tracking
- Monitor API calls and token usage
- Track costs per analysis session
- Identify expensive operations

### 5. Compliance
- Structured logs suitable for compliance requirements
- Log rotation prevents disk space issues
- Separate error logs for quick issue identification

## Best Practices

1. **Use Appropriate Log Levels**
   - DEBUG: Detailed diagnostic information
   - INFO: Confirmation of expected behavior
   - WARNING: Something unexpected but handled
   - ERROR: Serious problem that needs attention
   - CRITICAL: System failure

2. **Include Context**
   ```python
   cli_logger.info(
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

3. **Log at Key Points**
   - Session start/end
   - Configuration changes
   - State transitions
   - API calls
   - Errors and exceptions

4. **Review Logs Regularly**
   - Check `errors.log` for issues
   - Monitor `performance.log` for bottlenecks
   - Review `api_calls.log` for cost optimization

## Troubleshooting

### Issue: No logs appearing

**Solution**: Check that logging is properly initialized:
```python
from tradingagents.utils.logging_config import configure_logging
configure_logging(level="INFO", console=True)
```

### Issue: Log files too large

**Solution**: The system uses automatic log rotation. Adjust settings in `logging_config.py`:
```python
maxBytes=10 * 1024 * 1024  # 10 MB
backupCount=5  # Keep 5 backup files
```

### Issue: Can't find specific logs

**Solution**: Use grep or log analysis tools:
```bash
# Find all ERROR logs
grep "ERROR" logs/tradingagents.log

# Find logs for specific ticker
grep "AAPL" logs/tradingagents.log

# Find performance issues
grep "duration_ms" logs/performance.log
```

## Migration Notes

### Legacy Logging

The CLI still maintains backward compatibility with the legacy `message_tool.log` file for each analysis session. This file contains:
- Agent messages
- Tool calls
- Timestamps

However, the new comprehensive logging system provides much more detailed information and should be preferred for debugging and monitoring.

### Gradual Migration

Other components of TradingAgents can gradually adopt the comprehensive logging system by:

1. Importing the logging utilities:
   ```python
   from tradingagents.utils.logging_config import get_logger
   ```

2. Getting a logger instance:
   ```python
   logger = get_logger("tradingagents.component_name", component="COMPONENT")
   ```

3. Replacing print statements with logger calls:
   ```python
   # Before
   print(f"Processing {item}")
   
   # After
   logger.info(f"Processing item", extra={"context": {"item": item}})
   ```

## Future Enhancements

- [ ] Add log aggregation support (e.g., ELK stack)
- [ ] Implement real-time log streaming
- [ ] Add log analysis dashboard
- [ ] Integrate with monitoring systems (Prometheus, Grafana)
- [ ] Add log filtering and search UI
- [ ] Implement log compression for archived logs
- [ ] Add distributed tracing for multi-agent workflows

## Summary

The CLI now uses a comprehensive logging system that provides:
- ✅ Structured, contextual logging
- ✅ Multiple log files for different purposes
- ✅ Performance tracking and metrics
- ✅ API call and cost monitoring
- ✅ Automatic log rotation
- ✅ Better debugging capabilities
- ✅ Audit trail for compliance

This makes the TradingAgents system more maintainable, debuggable, and production-ready.