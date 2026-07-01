// web/frontend/src/lib/agentTools.ts
import { base } from "./api";

// Debug flag - set to true to see detailed tool execution logs
const DEBUG_TOOLS = false;

function debugLog(...args: unknown[]) {
  if (DEBUG_TOOLS) {
    console.log("[agentTools]", ...args);
  }
}

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
  debug?: {
    toolName: string;
    originalName: string;
    params: Record<string, unknown>;
    sanitizedParams: Record<string, unknown>;
    path: string;
    recentToolContext: Record<string, unknown>;
  };
}

let cachedTools: ToolDefinition[] | null = null;

// Maps renamed tool name -> original backend name
// Set by AgentChatBubble before agent runs, used by executeTool to resolve renamed names
let renamedToolMap: Record<string, string> = {};

export function setRenamedToolMap(map: Record<string, string>) {
  debugLog("setRenamedToolMap:", map);
  renamedToolMap = map;
}

// Track recent successful tool parameter values (e.g. ticker symbols used)
// This helps when the LLM passes placeholder values like {TICKER} instead of real values
const recentToolContext: Record<string, unknown> = {};

// Store the current user message for inferring missing parameters
let currentUserMessage = "";

// Store full conversation history for context extraction
let conversationHistory: Array<{ role: string; content: string }> = [];

export function setCurrentUserMessage(msg: string) {
  currentUserMessage = msg;
}

export function clearCurrentUserMessage() {
  currentUserMessage = "";
}

export function setConversationHistory(history: Array<{ role: string; content: string }>) {
  conversationHistory = history;
}

export function clearConversationHistory() {
  conversationHistory = [];
}

export function prepopulateToolContext(params: Record<string, unknown>) {
  for (const [key, value] of Object.entries(params)) {
    if (typeof value === "string" && value.length > 0 && value.length < 20) {
      recentToolContext[key] = value;
    }
  }
}

const PLACEHOLDER_PATTERNS = /^(ticker|symbol|name|id|param|value|parameter|placeholder)$/i;

function isPlaceholderValue(value: string): boolean {
  return PLACEHOLDER_PATTERNS.test(value);
}

const TICKER_CONTEXT_WORDS = /\b(buy|sell|long|short|entry|exit|price|stock|etf|fund|trade|trading|market|call|put|option|shares?|position|hold|stop|take profit|tp|sl)\b/i;

const COMMON_WORDS = new Set([
  "ETF", "ETF.", "FUND", "STOCK", "PROMO", "THE", "THIS", "THAT", "WHAT", "WHEN", "WHERE",
  "WHO", "WHY", "HOW", "ALL", "ANY", "SOME", "THEM", "THEN", "THERE", "HERE", "WERE", "WAS",
  "ARE", "IS", "HAS", "HAD", "CAN", "COULD", "WOULD", "SHOULD", "WILL", "JUST", "LIKE",
  "GET", "GOT", "MAKE", "MAD", "SAY", "SAID", "NEW", "NOW", "OLD", "WAY", "DAY", "YEAR",
  "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "HKD", "NZD", "API", "CEO", "CFO",
  "COO", "CTO", "IPO", "M&A", "P&L", "ROI", "ROE", "EPS", "GDP", "CPI", "PPI", "FED", "SEC",
  "FINRA", "NYSE", "NASDAQ", "AMEX", "TSX", "LSE", "SGX", "HKEX",
]);

function extractTickersFromMessage(message: string): string[] {
  const found = new Set<string>();
  const hasTradingContext = TICKER_CONTEXT_WORDS.test(message);

  const patterns = [
    /\$([A-Z]{1,5})\b/g,                              // $SPY format (any length)
    /\b([A-Z]{2,5})\b/g,                              // 2-5 uppercase letters
  ];

  for (const pattern of patterns) {
    const matches = message.match(pattern);
    if (matches) {
      for (const match of matches) {
        const ticker = match.startsWith("$") ? match.slice(1) : match;
        if (ticker.length <= 2 && !match.startsWith("$")) continue;
        if (COMMON_WORDS.has(ticker.toUpperCase())) continue;
        found.add(ticker.toUpperCase());
      }
    }
  }

  if (!hasTradingContext && found.size > 0) {
    const likelyTickers = Array.from(found).filter(t => t.length >= 3 || message.includes(`$${t}`));
    if (likelyTickers.length > 0) return likelyTickers;
  }

  return Array.from(found);
}

function extractLastTickerFromConversation(): string | null {
  // Scan messages in reverse (newest first) to find the most recently mentioned ticker
  for (let i = conversationHistory.length - 1; i >= 0; i--) {
    const content = conversationHistory[i].content || "";
    const tickers = extractTickersFromMessage(content);
    if (tickers.length > 0) {
      return tickers[0];
    }
  }
  return null;
}

function isTickerTool(name: string): boolean {
  const lower = name.toLowerCase();
  return lower.includes("ticker") || lower.includes("stock") || lower.includes("price") ||
         lower.includes("history") || lower.includes("indicator") || lower.includes("runs") ||
         lower.includes("fundamental") || lower.includes("news") || lower.includes("sentiment") ||
         lower.includes("market");
}

/**
 * Fetch tool definitions from backend (cached after first call)
 */
export async function fetchTools(): Promise<ToolDefinition[]> {
  if (cachedTools) {
    debugLog("fetchTools: returning cached tools:", cachedTools.length);
    return cachedTools;
  }
  
  debugLog("fetchTools: fetching from API...");
  const response = await fetch(`${base}/api/chat/tools`);
  if (!response.ok) {
    throw new Error(`Failed to fetch tools: ${response.statusText}`);
  }
  
  const data = await response.json();
  cachedTools = data.tools;
  debugLog("fetchTools: fetched tools:", cachedTools.length);
  debugLog("fetchTools: tool names:", cachedTools.map(t => t.name));
  return cachedTools;
}

function cleanToolName(name: string): string {
  return name.replace(/__+/g, "_").replace(/^get_/, "").replace(/_+$/, "");
}

function findToolByName(name: string, tools: ToolDefinition[]): ToolDefinition | undefined {
  debugLog(`findToolByName: looking for "${name}"`);
  
let tool = tools.find(t => t.name === name);
  if (tool) {
    debugLog(`findToolByName: found exact match "${name}"`);
    return tool;
  }

  // Fallback 1: check renamed tool map (set by AgentChatBubble before agent runs)
  const originalName = renamedToolMap[name];
  if (originalName) {
    debugLog(`findToolByName: checking renamedToolMap["${name}"] = "${originalName}"`);
    tool = tools.find(t => t.name === originalName);
    if (tool) {
      debugLog(`findToolByName: found via renamedToolMap "${originalName}"`);
      return tool;
    }
  }

  // Fallback 2: try cleaned name if exact match not found
  const cleanedName = cleanToolName(name);
  debugLog(`findToolByName: trying cleaned name "${cleanedName}"`);
  tool = tools.find(t => cleanToolName(t.name) === cleanedName);
  if (tool) {
    debugLog(`findToolByName: found via cleaned name`);
    return tool;
  }

  debugLog(`findToolByName: NOT FOUND "${name}"`);
  debugLog(`findToolByName: available tools:`, tools.map(t => t.name));
  return undefined;
}

/**
 * Execute a tool via the proxy endpoint
 */
export async function executeTool(
  name: string,
  params: Record<string, unknown>
): Promise<ToolResult> {
  debugLog("========================================");
  debugLog(`executeTool START: "${name}"`);
  debugLog(`executeTool: raw params =`, JSON.stringify(params));
  debugLog(`executeTool: recentToolContext =`, JSON.stringify(recentToolContext));
  
  const tools = await fetchTools();
  const tool = findToolByName(name, tools);
  
  if (!tool) {
    const error = `Tool not found: ${name}`;
    debugLog(`executeTool ERROR: ${error}`);
    return { success: false, error };
  }

  debugLog(`executeTool: matched to backend tool "${tool.name}"`);
  debugLog(`executeTool: tool.path = "${tool.path}"`);
  debugLog(`executeTool: tool.parameters =`, JSON.stringify(tool.parameters));

  // Sanitize path params: replace {param} placeholders with actual values
  // and remove any literal curly brace values the LLM might have passed
  const sanitizedParams: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(params)) {
    let cleanValue = value;
    debugLog(`executeTool: param "${key}" = ${JSON.stringify(value)}`);
    
    if (typeof cleanValue === "string" && cleanValue.startsWith("{") && cleanValue.endsWith("}")) {
      cleanValue = cleanValue.slice(1, -1);
      debugLog(`executeTool: stripped braces -> "${cleanValue}"`);
    }
    // If value is still a placeholder like "ticker" or "TICKER", try to infer from context.
    // Only do this if we have a real value from a previous successful call.
    if (typeof cleanValue === "string" && isPlaceholderValue(cleanValue)) {
      debugLog(`executeTool: "${cleanValue}" is placeholder, checking recentToolContext...`);
      const contextValue = recentToolContext[key];
      if (contextValue !== undefined) {
        debugLog(`executeTool: using contextValue["${key}"] = "${contextValue}"`);
        cleanValue = contextValue as string;
      } else {
        debugLog(`executeTool: no context value for "${key}"`);
        const hintTicker = extractLastTickerFromConversation();
        const error = hintTicker
          ? `Missing required parameter '${key}'. Use a real ticker symbol like '${hintTicker}' (found in your conversation). Do not use '{${key}}' or '${key}' as placeholder.`
          : `Missing required parameter '${key}'. You must specify a real ticker symbol (e.g. SPY, AAPL, QQQ). Do not use '{${key}}' or '${key}' as placeholder.`;
        debugLog(`executeTool ERROR: ${error}`);
        return {
          success: false,
          error,
          debug: {
            toolName: name,
            originalName: tool.name,
            params,
            sanitizedParams,
            path: tool.path,
            recentToolContext: { ...recentToolContext },
          },
        };
      }
    }
    sanitizedParams[key] = cleanValue;
  }
  
  debugLog(`executeTool: sanitizedParams =`, JSON.stringify(sanitizedParams));
  
  // Substitute path parameters: /api/tickers/{ticker}/history → /api/tickers/SPY/history
  let path = tool.path;
  const pathParams = tool.path.match(/\{(\w+)\}/g) || [];
  debugLog(`executeTool: pathParams in path =`, pathParams);
  
  // First, try to fill path params from recentToolContext as fallback
  for (const placeholder of pathParams) {
    const paramName = placeholder.slice(1, -1);
    debugLog(`executeTool: checking path param "${paramName}" in recentToolContext...`);
    if (sanitizedParams[paramName] === undefined || sanitizedParams[paramName] === null) {
      const contextValue = recentToolContext[paramName];
      if (contextValue !== undefined) {
        debugLog(`executeTool: filling "${paramName}" from context = "${contextValue}"`);
        sanitizedParams[paramName] = contextValue;
      } else {
        debugLog(`executeTool: no context value for path param "${paramName}"`);
        // If still undefined, try to extract from conversation history for ticker/symbol params.
        // Only fill for ticker-related tools (avoid forcing tickers for general questions).
        if ((paramName === "ticker" || paramName === "symbol") && isTickerTool(name)) {
          const lastTicker = extractLastTickerFromConversation();
          if (lastTicker) {
            sanitizedParams[paramName] = lastTicker;
            debugLog(`executeTool: extracted "${paramName}" from recent conversation: "${lastTicker}"`);
          } else if (currentUserMessage) {
            const extractedTickers = extractTickersFromMessage(currentUserMessage);
            if (extractedTickers.length > 0) {
              sanitizedParams[paramName] = extractedTickers[0];
              debugLog(`executeTool: extracted "${paramName}" from user message: "${extractedTickers[0]}"`);
            }
          }
        }
      }
    }
  }
  
  debugLog(`executeTool: after context fallback, sanitizedParams =`, JSON.stringify(sanitizedParams));
  
  for (const placeholder of pathParams) {
    const paramName = placeholder.slice(1, -1);
    const value = sanitizedParams[paramName];
    debugLog(`executeTool: substituting "${placeholder}" -> "${value}"`);
    if (value !== undefined && value !== null) {
      // Store path param in context BEFORE deletion (so failed calls can still use it on next turn)
      if (typeof value === "string" && value.length > 0 && value.length < 20) {
        debugLog(`executeTool: storing path param context["${paramName}"] = "${value}"`);
        recentToolContext[paramName] = value;
      }
      path = path.replace(placeholder, String(value));
      delete sanitizedParams[paramName];
    }
  }
  
  debugLog(`executeTool: final path = "${path}"`);

  // Validate all path parameters were resolved
  const unresolvedParams = path.match(/\{(\w+)\}/g) || [];
  if (unresolvedParams.length > 0) {
    const names = unresolvedParams.map(p => p.slice(1, -1)).join(", ");
    const hintTicker = extractLastTickerFromConversation();
    const error = hintTicker
      ? `Missing required tool parameters: ${names}. You must specify a real value for each (e.g. ${names.includes("ticker") ? `ticker="${hintTicker}"` : "value"}). This should be a real ticker symbol from your conversation, not a placeholder.`
      : `Missing required tool parameters: ${names}. You must specify a real value for each (e.g. ${names.includes("ticker") ? 'ticker="SPY"' : "value"}). Use a real ticker symbol, not a placeholder.`;
    debugLog(`executeTool ERROR: ${error}`);
    return {
      success: false,
      error,
      debug: {
        toolName: name,
        originalName: tool.name,
        params,
        sanitizedParams,
        path,
        recentToolContext: { ...recentToolContext },
      },
    };
  }
  
  debugLog(`executeTool: sending proxy request...`);
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
    
    debugLog(`executeTool: proxy response status = ${response.status}`);
    
    if (!response.ok) {
      const error = `Request failed: ${response.statusText}`;
      debugLog(`executeTool ERROR: ${error}`);
      return { success: false, error };
    }
    
    const data = await response.json();
    debugLog(`executeTool: proxy response data =`, JSON.stringify(data).slice(0, 200) + "...");
    
    // Store successful parameter values in context for other tool calls
    for (const [key, value] of Object.entries(sanitizedParams)) {
      if (typeof value === "string" && value.length > 0 && value.length < 20) {
        debugLog(`executeTool: storing success context["${key}"] = "${value}"`);
        recentToolContext[key] = value;
      }
    }
    
    debugLog(`executeTool SUCCESS: "${name}"`);
    debugLog("========================================");
    return { success: true, data };
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : "Unknown error";
    debugLog(`executeTool EXCEPTION: ${errorMsg}`);
    return {
      success: false,
      error: errorMsg,
      debug: {
        toolName: name,
        originalName: tool.name,
        params,
        sanitizedParams,
        path,
        recentToolContext: { ...recentToolContext },
      },
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
