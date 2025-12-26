#!/usr/bin/env python3
"""
MCP Server Detector - Identify MCP Server Type from Tool Calls

This module detects which MCP server is being invoked based on tool names and
parameters. This enables the security enforcer to apply the correct validation
rules for different MCP server types (filesystem, git, github, python, bash, web).

Detection Strategy:
1. Tool name analysis (e.g., "read_file" → filesystem)
2. Parameter structure (e.g., has "command" → bash)
3. Context clues (e.g., has "repo" → git)

Supported MCP Server Types:
- filesystem: File read/write operations
- git: Git repository operations
- github: GitHub API operations (issues, PRs, repos)
- python: Python REPL code execution
- bash: Shell command execution
- web: Web search and content fetching

Usage:
    from mcp_server_detector import detect_mcp_server, MCPServerType

    # Detect server type
    server_type = detect_mcp_server("read_file", {"path": "src/main.py"})
    # Returns: MCPServerType.FILESYSTEM

    server_type = detect_mcp_server("run_command", {"command": "git status"})
    # Returns: MCPServerType.BASH

Date: 2025-12-07
Issue: #95 (MCP Security Implementation)
Version: v3.37.0
"""

from enum import Enum
from typing import Dict, Any
from dataclasses import dataclass


class MCPServerType(Enum):
    """Enumeration of supported MCP server types."""
    FILESYSTEM = "filesystem"
    GIT = "git"
    GITHUB = "github"
    PYTHON = "python"
    BASH = "bash"
    WEB = "web"
    UNKNOWN = "unknown"


@dataclass
class DetectionResult:
    """Result of MCP server type detection.

    Attributes:
        server_type: Detected MCP server type
        confidence: Confidence level (0.0-1.0)
        reason: Human-readable explanation of detection
    """
    server_type: MCPServerType
    confidence: float
    reason: str


# Tool name patterns for each server type
FILESYSTEM_TOOLS = {
    "read_file",
    "write_file",
    "list_directory",
    "create_directory",
    "delete_file",
    "move_file",
    "copy_file",
    "get_file_info",
    "search_files",
}

GIT_TOOLS = {
    "git_status",
    "git_diff",
    "git_log",
    "git_commit",
    "git_push",
    "git_pull",
    "git_checkout",
    "git_branch",
    "git_merge",
    "git_reset",
    "git_show",
    "git_blame",
}

GITHUB_TOOLS = {
    "list_repos",
    "get_repo",
    "create_issue",
    "update_issue",
    "list_issues",
    "get_issue",
    "create_pr",
    "update_pr",
    "list_prs",
    "get_pr",
    "merge_pr",
    "create_comment",
    "list_workflow_runs",
    "get_workflow_run",
    "list_branches",
    "get_branch",
}

PYTHON_TOOLS = {
    "execute_code",
    "execute_python",
    "eval",
    "run_python",
    "get_globals",
    "reset_session",
    "get_locals",
}

BASH_TOOLS = {
    "run_command",
    "execute_command",
    "run_bash",
    "run_shell",
    "execute_shell",
    "get_cwd",
    "change_directory",
}

WEB_TOOLS = {
    "web_search",
    "search_web",
    "brave_search",
    "search",
    "fetch_url",
    "get_url",
    "http_get",
    "local_search",
    "news_search",
    "image_search",
}


def detect_mcp_server(tool: str, parameters: Dict[str, Any]) -> DetectionResult:
    """Detect MCP server type from tool name and parameters.

    Detection uses multiple strategies:
    1. Exact tool name match (highest confidence)
    2. Tool name pattern matching
    3. Parameter structure analysis

    Args:
        tool: Tool name (e.g., "read_file", "run_command")
        parameters: Tool parameters dictionary

    Returns:
        DetectionResult with server type, confidence, and reason

    Examples:
        >>> detect_mcp_server("read_file", {"path": "src/main.py"})
        DetectionResult(server_type=MCPServerType.FILESYSTEM, confidence=1.0,
                       reason="Exact match: tool 'read_file' in filesystem tools")

        >>> detect_mcp_server("execute_code", {"code": "print('hello')"})
        DetectionResult(server_type=MCPServerType.PYTHON, confidence=1.0,
                       reason="Exact match: tool 'execute_code' in python tools")
    """
    tool_lower = tool.lower()

    # Strategy 1: Exact tool name match (confidence: 1.0)
    if tool_lower in FILESYSTEM_TOOLS:
        return DetectionResult(
            server_type=MCPServerType.FILESYSTEM,
            confidence=1.0,
            reason=f"Exact match: tool '{tool}' in filesystem tools"
        )

    if tool_lower in GIT_TOOLS:
        return DetectionResult(
            server_type=MCPServerType.GIT,
            confidence=1.0,
            reason=f"Exact match: tool '{tool}' in git tools"
        )

    if tool_lower in GITHUB_TOOLS:
        return DetectionResult(
            server_type=MCPServerType.GITHUB,
            confidence=1.0,
            reason=f"Exact match: tool '{tool}' in github tools"
        )

    if tool_lower in PYTHON_TOOLS:
        return DetectionResult(
            server_type=MCPServerType.PYTHON,
            confidence=1.0,
            reason=f"Exact match: tool '{tool}' in python tools"
        )

    if tool_lower in BASH_TOOLS:
        return DetectionResult(
            server_type=MCPServerType.BASH,
            confidence=1.0,
            reason=f"Exact match: tool '{tool}' in bash tools"
        )

    if tool_lower in WEB_TOOLS:
        return DetectionResult(
            server_type=MCPServerType.WEB,
            confidence=1.0,
            reason=f"Exact match: tool '{tool}' in web tools"
        )

    # Strategy 2: Tool name pattern matching (confidence: 0.8)
    if "file" in tool_lower or "directory" in tool_lower or "path" in tool_lower:
        return DetectionResult(
            server_type=MCPServerType.FILESYSTEM,
            confidence=0.8,
            reason=f"Pattern match: tool '{tool}' contains filesystem keywords"
        )

    if "git" in tool_lower:
        return DetectionResult(
            server_type=MCPServerType.GIT,
            confidence=0.8,
            reason=f"Pattern match: tool '{tool}' contains 'git'"
        )

    if "github" in tool_lower or "repo" in tool_lower or "issue" in tool_lower or "pr" in tool_lower:
        return DetectionResult(
            server_type=MCPServerType.GITHUB,
            confidence=0.8,
            reason=f"Pattern match: tool '{tool}' contains GitHub keywords"
        )

    if "python" in tool_lower or "code" in tool_lower:
        return DetectionResult(
            server_type=MCPServerType.PYTHON,
            confidence=0.8,
            reason=f"Pattern match: tool '{tool}' contains Python keywords"
        )

    if "command" in tool_lower or "bash" in tool_lower or "shell" in tool_lower:
        return DetectionResult(
            server_type=MCPServerType.BASH,
            confidence=0.8,
            reason=f"Pattern match: tool '{tool}' contains shell keywords"
        )

    if "search" in tool_lower or "fetch" in tool_lower or "url" in tool_lower or "web" in tool_lower:
        return DetectionResult(
            server_type=MCPServerType.WEB,
            confidence=0.8,
            reason=f"Pattern match: tool '{tool}' contains web keywords"
        )

    # Strategy 3: Parameter structure analysis (confidence: 0.6)
    if "path" in parameters or "file_path" in parameters or "directory" in parameters:
        return DetectionResult(
            server_type=MCPServerType.FILESYSTEM,
            confidence=0.6,
            reason=f"Parameter match: parameters contain filesystem paths"
        )

    if "command" in parameters:
        return DetectionResult(
            server_type=MCPServerType.BASH,
            confidence=0.6,
            reason=f"Parameter match: parameters contain 'command'"
        )

    if "code" in parameters:
        return DetectionResult(
            server_type=MCPServerType.PYTHON,
            confidence=0.6,
            reason=f"Parameter match: parameters contain 'code'"
        )

    if "url" in parameters or "query" in parameters:
        return DetectionResult(
            server_type=MCPServerType.WEB,
            confidence=0.6,
            reason=f"Parameter match: parameters contain web-related keys"
        )

    if "repository" in parameters or "repo" in parameters or "branch" in parameters:
        return DetectionResult(
            server_type=MCPServerType.GIT,
            confidence=0.6,
            reason=f"Parameter match: parameters contain git-related keys"
        )

    if "owner" in parameters and "repo" in parameters:
        return DetectionResult(
            server_type=MCPServerType.GITHUB,
            confidence=0.6,
            reason=f"Parameter match: parameters contain GitHub repo identifiers"
        )

    # Unknown tool
    return DetectionResult(
        server_type=MCPServerType.UNKNOWN,
        confidence=0.0,
        reason=f"No match found for tool '{tool}'"
    )


def get_server_type_from_string(server_type_str: str) -> MCPServerType:
    """Convert string to MCPServerType enum.

    Args:
        server_type_str: Server type as string (e.g., "filesystem")

    Returns:
        MCPServerType enum value

    Raises:
        ValueError: If server type string is invalid
    """
    try:
        return MCPServerType(server_type_str.lower())
    except ValueError:
        raise ValueError(
            f"Invalid MCP server type: '{server_type_str}'. "
            f"Valid types: {[t.value for t in MCPServerType]}"
        )


def is_high_confidence(result: DetectionResult, threshold: float = 0.8) -> bool:
    """Check if detection result has high confidence.

    Args:
        result: Detection result to check
        threshold: Minimum confidence threshold (default: 0.8)

    Returns:
        True if confidence >= threshold
    """
    return result.confidence >= threshold


# Example usage
if __name__ == "__main__":
    # Test filesystem detection
    result = detect_mcp_server("read_file", {"path": "src/main.py"})
    print(f"Filesystem: {result}")

    # Test bash detection
    result = detect_mcp_server("run_command", {"command": "git status"})
    print(f"Bash: {result}")

    # Test python detection
    result = detect_mcp_server("execute_code", {"code": "print('hello')"})
    print(f"Python: {result}")

    # Test web detection
    result = detect_mcp_server("web_search", {"query": "MCP servers"})
    print(f"Web: {result}")

    # Test github detection
    result = detect_mcp_server("create_issue", {"owner": "user", "repo": "project", "title": "Bug"})
    print(f"GitHub: {result}")

    # Test unknown
    result = detect_mcp_server("unknown_tool", {})
    print(f"Unknown: {result}")
