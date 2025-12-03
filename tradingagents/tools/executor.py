"""
Tool Executor - Simplified Tool Execution with Registry-Based Routing

This module replaces the complex route_to_vendor() function with a simpler,
registry-based approach. All routing decisions are driven by the tool registry.

Key improvements over old system:
- Single registry lookup instead of multiple dictionary lookups
- Clear fallback logic per tool (optional, not mandatory)
- Better error messages and debugging
- No dual registry systems
"""

from typing import Any, Optional, List
import logging
from tradingagents.tools.registry import TOOL_REGISTRY, get_vendor_config

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when tool execution fails across all vendors."""
    pass


class VendorNotFoundError(Exception):
    """Raised when no vendor implementation is found for a tool."""
    pass


def execute_tool(tool_name: str, *args, **kwargs) -> Any:
    """Execute a tool using the registry-based routing system.

    This is the simplified replacement for route_to_vendor().

    Args:
        tool_name: Name of the tool to execute (e.g., "get_stock_data")
        *args: Positional arguments to pass to the tool
        **kwargs: Keyword arguments to pass to the tool

    Returns:
        Result from the vendor function

    Raises:
        VendorNotFoundError: If tool or vendor implementation not found
        ToolExecutionError: If all vendors fail to execute the tool
    """

    # Step 1: Get vendor configuration from registry
    vendor_config = get_vendor_config(tool_name)

    if not vendor_config["vendor_priority"]:
        raise VendorNotFoundError(
            f"Tool '{tool_name}' not found in registry or has no vendors configured"
        )

    # Step 2: Get vendor functions and priority list
    vendor_functions = vendor_config["vendors"]
    vendors_to_try = vendor_config["vendor_priority"]

    logger.debug(f"Executing tool '{tool_name}' with vendors: {vendors_to_try}")

    # Step 3: Try each vendor in priority order
    errors = []

    for vendor_name in vendors_to_try:
        # Get the vendor function directly from registry
        vendor_func = vendor_functions.get(vendor_name)

        if not vendor_func:
            logger.warning(f"Vendor '{vendor_name}' not found in registry for tool '{tool_name}'")
            continue

        try:
            result = vendor_func(*args, **kwargs)
            logger.debug(f"Tool '{tool_name}' succeeded with vendor '{vendor_name}'")
            return result

        except Exception as e:
            error_msg = f"Vendor '{vendor_name}' failed: {str(e)}"
            logger.warning(f"Tool '{tool_name}': {error_msg}")
            errors.append(error_msg)

            # Continue to next vendor (fallback)
            continue

    # Step 4: All vendors failed
    error_summary = f"Tool '{tool_name}' failed with all vendors:\n" + "\n".join(f"  - {err}" for err in errors)
    logger.error(error_summary)
    raise ToolExecutionError(error_summary)


def get_tool_info(tool_name: str) -> Optional[dict]:
    """Get information about a tool from the registry.

    Useful for debugging and introspection.

    Args:
        tool_name: Name of the tool

    Returns:
        Tool metadata dict, or None if not found
    """
    return TOOL_REGISTRY.get(tool_name)


def list_available_vendors(tool_name: str) -> List[str]:
    """List all available vendors for a tool.

    Args:
        tool_name: Name of the tool

    Returns:
        List of vendor names in priority order
    """
    vendor_config = get_vendor_config(tool_name)
    return vendor_config.get("vendor_priority", [])


# ============================================================================
# LEGACY COMPATIBILITY LAYER
# ============================================================================

def route_to_vendor(method: str, *args, **kwargs) -> Any:
    """Legacy compatibility function.

    This provides backward compatibility with the old route_to_vendor() calls.
    Internally, it just delegates to execute_tool().

    DEPRECATED: Use execute_tool() directly in new code.

    Args:
        method: Tool name (legacy parameter name)
        *args: Positional arguments
        **kwargs: Keyword arguments

    Returns:
        Result from tool execution
    """
    logger.warning(
        f"route_to_vendor() is deprecated. Use execute_tool('{method}', ...) instead."
    )
    return execute_tool(method, *args, **kwargs)


# ============================================================================
# TESTING & DEBUGGING
# ============================================================================

if __name__ == "__main__":
    # Enable debug logging
    logging.basicConfig(level=logging.DEBUG)

    print("=" * 70)
    print("TOOL EXECUTOR - TESTING")
    print("=" * 70)

    # Test 1: List available vendors for each tool
    print("\nAvailable vendors per tool:")
    from tradingagents.tools.registry import get_all_tools

    for tool_name in get_all_tools():
        vendors = list_available_vendors(tool_name)
        print(f"  {tool_name}:")
        print(f"    Primary: {vendors[0] if vendors else 'None'}")
        if len(vendors) > 1:
            print(f"    Fallbacks: {', '.join(vendors[1:])}")

    # Test 2: Show tool info
    print("\nTool info examples:")
    for tool_name in ["get_stock_data", "get_news", "get_fundamentals"]:
        info = get_tool_info(tool_name)
        if info:
            print(f"\n  {tool_name}:")
            print(f"    Category: {info['category']}")
            print(f"    Agents: {', '.join(info['agents']) if info['agents'] else 'None'}")
            print(f"    Description: {info['description']}")

    # Test 3: Validate registry
    print("\nValidating registry:")
    from tradingagents.tools.registry import validate_registry

    issues = validate_registry()
    if issues:
        print("  ⚠️  Registry validation issues found:")
        for issue in issues[:10]:  # Show first 10
            print(f"    - {issue}")
        if len(issues) > 10:
            print(f"    ... and {len(issues) - 10} more")
    else:
        print("  ✅ Registry is valid!")

    print("\n" + "=" * 70)
