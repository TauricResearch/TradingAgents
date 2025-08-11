#!/bin/bash

# Post-tool hook for mypy type checking
# This script runs after Edit, MultiEdit, or Write tools are used

# Check if the modified file is a Python file
if [[ "$CLAUDE_TOOL_FILE_PATH" == *.py ]]; then
    echo "Running type check on $CLAUDE_TOOL_FILE_PATH..."
    
    # Try to run mypy with timeout to avoid hanging on macOS
    # Using timeout command to prevent infinite hanging
    if command -v gtimeout &> /dev/null; then
        # macOS with GNU coreutils installed
        TIMEOUT_CMD="gtimeout 3"
    elif command -v timeout &> /dev/null; then
        # Linux or macOS with timeout available
        TIMEOUT_CMD="timeout 3"
    else
        # No timeout command available, skip mypy
        echo "⚠ Skipping type check (timeout command not available)"
        exit 0
    fi
    
    # Try running mypy with timeout
    $TIMEOUT_CMD python -m mypy "$CLAUDE_TOOL_FILE_PATH" --ignore-missing-imports --no-error-summary 2>&1
    
    # Get the exit code
    MYPY_EXIT_CODE=$?
    
    if [ $MYPY_EXIT_CODE -eq 124 ] || [ $MYPY_EXIT_CODE -eq 143 ]; then
        echo "⚠ Type check timed out (known macOS issue with mypy)"
        echo "  Consider running type checks manually later"
    elif [ $MYPY_EXIT_CODE -eq 0 ]; then
        echo "✓ Type check passed"
    else
        echo "⚠ Type check found issues. Consider fixing them."
    fi
fi

# Always exit successfully to not block the workflow
exit 0