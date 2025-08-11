#!/bin/bash

# Post-tool hook for Python tools (Black, Ruff, mypy)
# This script runs after Edit, MultiEdit, or Write tools are used

# Check if the modified file is a Python file
if [[ "$CLAUDE_TOOL_FILE_PATH" == *.py ]]; then
    echo "🔧 Running Python tools on $CLAUDE_TOOL_FILE_PATH..."
    echo ""
    
    # 1. Run Black formatter
    echo "▶ Running Black formatter..."
    if command -v black &> /dev/null; then
        black "$CLAUDE_TOOL_FILE_PATH" --quiet 2>&1
        if [ $? -eq 0 ]; then
            echo "  ✓ Black formatting completed"
        else
            echo "  ⚠ Black formatting failed"
        fi
    else
        echo "  ⚠ Black not installed"
    fi
    echo ""
    
    # 2. Run Ruff linter and formatter
    echo "▶ Running Ruff linter and formatter..."
    if command -v ruff &> /dev/null; then
        # Run Ruff format (similar to Black but faster)
        ruff format "$CLAUDE_TOOL_FILE_PATH" --quiet 2>&1
        FORMAT_EXIT_CODE=$?
        
        # Run Ruff check (linting) with auto-fix
        ruff check "$CLAUDE_TOOL_FILE_PATH" --fix --quiet 2>&1
        LINT_EXIT_CODE=$?
        
        if [ $FORMAT_EXIT_CODE -eq 0 ] && [ $LINT_EXIT_CODE -eq 0 ]; then
            echo "  ✓ Ruff check and format completed"
        else
            # Show detailed Ruff output if there are issues
            echo "  ⚠ Ruff found issues:"
            ruff check "$CLAUDE_TOOL_FILE_PATH" 2>&1 | sed 's/^/    /'
        fi
    else
        echo "  ⚠ Ruff not installed"
    fi
    echo ""
    
    # 3. Run mypy type checker
    echo "▶ Running mypy type checker..."
    if command -v mypy &> /dev/null; then
        # Try to run mypy with timeout to avoid hanging on macOS
        if command -v gtimeout &> /dev/null; then
            # macOS with GNU coreutils installed
            TIMEOUT_CMD="gtimeout 3"
        elif command -v timeout &> /dev/null; then
            # Linux or macOS with timeout available
            TIMEOUT_CMD="timeout 3"
        else
            # No timeout command available, run without timeout
            TIMEOUT_CMD=""
        fi
        
        if [ -n "$TIMEOUT_CMD" ]; then
            # Run with timeout
            $TIMEOUT_CMD python -m mypy "$CLAUDE_TOOL_FILE_PATH" --ignore-missing-imports --no-error-summary 2>&1
            MYPY_EXIT_CODE=$?
            
            if [ $MYPY_EXIT_CODE -eq 124 ] || [ $MYPY_EXIT_CODE -eq 143 ]; then
                echo "  ⚠ Type check timed out (known macOS issue)"
            elif [ $MYPY_EXIT_CODE -eq 0 ]; then
                echo "  ✓ Type check passed"
            else
                # Show mypy output if there are type errors
                echo "  ⚠ Type check found issues:"
                python -m mypy "$CLAUDE_TOOL_FILE_PATH" --ignore-missing-imports 2>&1 | sed 's/^/    /'
            fi
        else
            # Run without timeout
            python -m mypy "$CLAUDE_TOOL_FILE_PATH" --ignore-missing-imports --no-error-summary 2>&1
            if [ $? -eq 0 ]; then
                echo "  ✓ Type check passed"
            else
                echo "  ⚠ Type check found issues"
            fi
        fi
    else
        echo "  ⚠ mypy not installed"
    fi
    
    echo ""
    echo "🏁 Python tools check completed"
fi

# Always exit successfully to not block the workflow
exit 0