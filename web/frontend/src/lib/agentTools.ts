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
    if (typeof value === "string" && value.startsWith("{") && value.endsWith("}")) {
      sanitizedParams[key] = value.slice(1, -1);
    } else {
      sanitizedParams[key] = value;
    }
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
