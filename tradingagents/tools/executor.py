"""
Tool Executor - Simplified Tool Execution with Registry-Based Routing

This module replaces the complex route_to_vendor() function with a simpler,
registry-based approach. All routing decisions are driven by the tool registry.

Key improvements over old system:
- Single registry lookup instead of multiple dictionary lookups
- Supports both fallback and aggregate execution modes
- Parallel vendor execution for aggregate mode
- Better error messages and debugging
- No dual registry systems
"""

from typing import Any, Optional, List, Dict
import logging
import concurrent.futures
from tradingagents.tools.registry import TOOL_REGISTRY, get_vendor_config, get_tool_metadata

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when tool execution fails across all vendors."""
    pass


class VendorNotFoundError(Exception):
    """Raised when no vendor implementation is found for a tool."""
    pass


def _execute_fallback(tool_name: str, vendor_config: Dict, *args, **kwargs) -> Any:
    """Execute vendors sequentially with fallback (original behavior).

    Tries vendors in priority order and returns the first successful result.

    Args:
        tool_name: Name of the tool
        vendor_config: Vendor configuration from registry
        *args: Positional arguments for vendor function
        **kwargs: Keyword arguments for vendor function

    Returns:
        Result from first successful vendor

    Raises:
        ToolExecutionError: If all vendors fail
    """
    vendor_functions = vendor_config["vendors"]
    vendors_to_try = vendor_config["vendor_priority"]
    errors = []

    logger.debug(f"Executing tool '{tool_name}' in fallback mode with vendors: {vendors_to_try}")

    for vendor_name in vendors_to_try:
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
            continue

    # All vendors failed
    error_summary = f"Tool '{tool_name}' failed with all vendors:\n" + "\n".join(f"  - {err}" for err in errors)
    logger.error(error_summary)
    raise ToolExecutionError(error_summary)


def _execute_aggregate(tool_name: str, vendor_config: Dict, metadata: Dict, *args, **kwargs) -> str:
    """Execute multiple vendors in parallel and aggregate results.

    Executes all specified vendors simultaneously using ThreadPoolExecutor,
    collects successful results, and combines them with vendor labels.

    Args:
        tool_name: Name of the tool
        vendor_config: Vendor configuration from registry
        metadata: Tool metadata from registry
        *args: Positional arguments for vendor functions
        **kwargs: Keyword arguments for vendor functions

    Returns:
        Aggregated results from all successful vendors, formatted with labels

    Raises:
        ToolExecutionError: If all vendors fail
    """
    vendor_functions = vendor_config["vendors"]

    # Get list of vendors to aggregate (default to all in priority list)
    vendors_to_aggregate = metadata.get("aggregate_vendors") or vendor_config["vendor_priority"]

    logger.debug(f"Executing tool '{tool_name}' in aggregate mode with vendors: {vendors_to_aggregate}")

    results = []
    errors = []

    # Execute vendors in parallel using ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(vendors_to_aggregate)) as executor:
        # Submit all vendor calls
        future_to_vendor = {}
        for vendor_name in vendors_to_aggregate:
            vendor_func = vendor_functions.get(vendor_name)
            if vendor_func:
                future = executor.submit(vendor_func, *args, **kwargs)
                future_to_vendor[future] = vendor_name
            else:
                logger.warning(f"Vendor '{vendor_name}' not found in vendors dict for tool '{tool_name}'")

        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_vendor):
            vendor_name = future_to_vendor[future]
            try:
                result = future.result()
                results.append({
                    "vendor": vendor_name,
                    "data": result
                })
                logger.debug(f"Tool '{tool_name}': vendor '{vendor_name}' succeeded")
            except Exception as e:
                error_msg = f"Vendor '{vendor_name}' failed: {str(e)}"
                errors.append(error_msg)
                logger.warning(f"Tool '{tool_name}': {error_msg}")

    # Check if we got any results
    if not results:
        error_summary = f"Tool '{tool_name}' aggregate mode: all vendors failed:\n" + "\n".join(f"  - {err}" for err in errors)
        logger.error(error_summary)
        raise ToolExecutionError(error_summary)

    # Format aggregated results with clear vendor labels
    formatted_results = []
    for item in results:
        vendor_label = f"=== {item['vendor'].upper()} ==="
        formatted_results.append(f"{vendor_label}\n{item['data']}")

    # Log partial success if some vendors failed
    if errors:
        logger.info(f"Tool '{tool_name}': {len(results)} vendors succeeded, {len(errors)} failed")

    return "\n\n".join(formatted_results)


def execute_tool(tool_name: str, *args, **kwargs) -> Any:
    """Execute a tool using fallback or aggregate mode based on configuration.

    This is the main entry point for tool execution. It dispatches to either
    fallback mode (sequential with early return) or aggregate mode (parallel
    with result combination) based on the tool's execution_mode setting.

    Args:
        tool_name: Name of the tool to execute (e.g., "get_stock_data")
        *args: Positional arguments to pass to the tool
        **kwargs: Keyword arguments to pass to the tool

    Returns:
        Result from vendor function(s). String for aggregate mode (formatted
        with vendor labels), Any for fallback mode (raw vendor result).

    Raises:
        VendorNotFoundError: If tool or vendor implementation not found
        ToolExecutionError: If all vendors fail to execute the tool
    """
    # Get vendor configuration and metadata from registry
    vendor_config = get_vendor_config(tool_name)
    metadata = get_tool_metadata(tool_name)

    if not vendor_config["vendor_priority"]:
        raise VendorNotFoundError(
            f"Tool '{tool_name}' not found in registry or has no vendors configured"
        )

    if not metadata:
        raise VendorNotFoundError(f"Tool '{tool_name}' metadata not found in registry")

    # Check execution mode (defaults to fallback for backward compatibility)
    execution_mode = metadata.get("execution_mode", "fallback")

    # Dispatch to appropriate execution strategy
    if execution_mode == "aggregate":
        return _execute_aggregate(tool_name, vendor_config, metadata, *args, **kwargs)
    else:
        return _execute_fallback(tool_name, vendor_config, *args, **kwargs)


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
