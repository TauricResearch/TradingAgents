/**
 * Catch-all API proxy route.
 *
 * Proxies every /api/* request that does NOT have a more-specific route handler
 * (e.g. /api/chat, /api/auth/*, /api/config) to the FastAPI backend.
 *
 * Unlike next.config.ts rewrites(), this resolves the backend URL **per-request**
 * so it works correctly on Railway and other platforms where the backend URL
 * is only available at runtime via environment variables.
 */
import { NextRequest, NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/backend-url";

const TIMEOUT_MS = 300_000; // 5 minutes – analysis tasks can be long-running

async function proxyRequest(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const backendUrl = getBackendUrl();
  const target = `${backendUrl}/api/${path.join("/")}`;

  // Preserve query string
  const url = new URL(req.url);
  const qs = url.search; // includes leading "?"
  const fullTarget = `${target}${qs}`;

  try {
    // Forward relevant headers
    const headers: Record<string, string> = {
      "Content-Type": req.headers.get("content-type") || "application/json",
    };

    const auth = req.headers.get("authorization");
    if (auth) {
      headers["Authorization"] = auth;
    }

    // Read body for methods that have one
    let body: string | undefined;
    if (req.method !== "GET" && req.method !== "HEAD") {
      body = await req.text();
    }

    const response = await fetch(fullTarget, {
      method: req.method,
      headers,
      body,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });

    const data = await response.text();

    if (!response.ok) {
      console.error(`[API Proxy] ${req.method} ${target} → ${response.status}`);
      try {
        return NextResponse.json(JSON.parse(data), { status: response.status });
      } catch {
        return NextResponse.json(
          { detail: `Backend error: ${response.status}` },
          { status: response.status },
        );
      }
    }

    // Try to return JSON; fall back to plain text
    try {
      return NextResponse.json(JSON.parse(data));
    } catch {
      return new NextResponse(data, {
        status: 200,
        headers: { "Content-Type": response.headers.get("content-type") || "text/plain" },
      });
    }
  } catch (error: any) {
    console.error(`[API Proxy] ${req.method} ${fullTarget} failed:`, error?.message || error);
    return NextResponse.json(
      { detail: `Failed to connect to backend: ${error?.message || "Unknown error"}` },
      { status: 502 },
    );
  }
}

export const GET    = proxyRequest;
export const POST   = proxyRequest;
export const PUT    = proxyRequest;
export const PATCH  = proxyRequest;
export const DELETE = proxyRequest;
