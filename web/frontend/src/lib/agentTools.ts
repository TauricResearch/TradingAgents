// web/frontend/src/lib/agentTools.ts
import { base } from "./api";

export interface ToolParameter {
  type: string;
  description?: string;
}

export interface ToolDefinition {
  name: string;
  description: string;
  method: string;
  path: string;
  parameters: Record<string, ToolParameter>;
}

export interface ToolResult {
  success: boolean;
  data?: unknown;
  error?: string;
}

let cachedTools: ToolDefinition[] | null = null;

// Track recent successful tool parameter values (e.g. ticker symbols used)
// This helps when the LLM passes placeholder values like {TICKER} instead of real values
const recentToolContext: Record<string, unknown> = {};

const PLACEHOLDER_PATTERNS = /^(ticker|symbol|name|id|param|value|parameter|placeholder)$/i;

/**
 * Check if a string value looks like a template placeholder rather than a real value
 */
function isPlaceholderValue(value: string): boolean {
  return PLACEHOLDER_PATTERNS.test(value);
}

/**
 * Fetch tool definitions from backend (cached after first call)
 */
export async function fetchTools(): Promise<ToolDefinition[]> {
  if (cachedTools) return cachedTools;
  
  const response = await fetch(`${base}/api/chat/tools`);
  if (!response.ok) {
    throw new Error(`Failed to fetch tools: ${response.statusText}`);
  }
  
  const data = await response.json();
  cachedTools = data.tools;
  return cachedTools;
}

/**
 * Execute a tool via the proxy endpoint
 */
export async function executeTool(
  name: string,
  params: Record<string, unknown>
): Promise<ToolResult> {
  const tools = await fetchTools();
  const tool = tools.find(t => t.name === name);
  
  if (!tool) {
    return { success: false, error: `Tool not found: ${name}` };
  }

  // Sanitize path params: replace {param} placeholders with actual values
  // and remove any literal curly brace values the LLM might have passed
  const sanitizedParams: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    let cleanValue = value;
    if (typeof cleanValue === "string" && cleanValue.startsWith("{") && cleanValue.endsWith("}")) {
      cleanValue = cleanValue.slice(1, -1);
    }
    // If value is still a placeholder like "ticker" or "TICKER", try to infer from context
    if (typeof cleanValue === "string" && isPlaceholderValue(cleanValue)) {
      const contextValue = recentToolContext[key];
      if (contextValue !== undefined) {
        cleanValue = contextValue;
      }
    }
    sanitizedParams[key] = cleanValue;
  }
  
  // Substitute path parameters: /api/tickers/{ticker}/history → /api/tickers/SPY/history
  let path = tool.path;
  const pathParams = tool.path.match(/\{(\w+)\}/g) || [];
  for (const placeholder of pathParams) {
    const paramName = placeholder.slice(1, -1);
    const value = sanitizedParams[paramName];
    if (value !== undefined && value !== null) {
      path = path.replace(placeholder, String(value));
      delete sanitizedParams[paramName];
    }
  }
  
  try {
    const response = await fetch(`${base}/api/chat/proxy`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        method: tool.method,
        path,
        params: tool.method === "GET" ? sanitizedParams : undefined,
        body: tool.method !== "GET" ? sanitizedParams : undefined,
      }),
    });
    
    if (!response.ok) {
      return { success: false, error: `Request failed: ${response.statusText}` };
    }
    
    const data = await response.json();
    
    // Store successful parameter values in context for other tool calls
    for (const [key, value] of Object.entries(sanitizedParams)) {
      if (typeof value === "string" && value.length > 0 && value.length < 20) {
        recentToolContext[key] = value;
      }
    }
    
    return { success: true, data };
  } catch (error) {
    return { 
      success: false, 
      error: error instanceof Error ? error.message : "Unknown error" 
    };
  }
}

/**
 * Clear cached tools (for testing or after API changes)
 */
export function clearToolCache(): void {
  cachedTools = null;
}

/**
 * Clear the tool context (resets remembered parameter values)
 */
export function clearToolContext(): void {
  Object.keys(recentToolContext).forEach(key => delete recentToolContext[key]);
}
