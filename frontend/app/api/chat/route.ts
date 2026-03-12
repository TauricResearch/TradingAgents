import { NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/backend-url";

export async function POST(req: Request) {
  try {
    const backendUrl = getBackendUrl();

    // Read the complete body from the request
    const bodyText = await req.text();
    
    console.log(`[API Route] Proxying /api/chat to ${backendUrl}/api/chat (${bodyText.length} bytes)`);

    // Use native fetch to proxy the request to the backend.
    // This bypasses the Next.js next.config.ts rewrites http-proxy,
    // which has known bugs with large POST bodies and timeouts in standalone mode.
    const response = await fetch(`${backendUrl}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: bodyText,
      // @ts-ignore - Node.js fetch specific option to disable timeout
      signal: AbortSignal.timeout ? AbortSignal.timeout(180_000) : undefined, // 3 minutes timeout
    });

    const data = await response.text();

    if (!response.ok) {
      console.error(`[API Route] Backend returned ${response.status}:`, data);
      try {
        const json = JSON.parse(data);
        return NextResponse.json(json, { status: response.status });
      } catch (e) {
        return NextResponse.json(
          { detail: `Backend error: ${response.status}` },
          { status: response.status }
        );
      }
    }

    return NextResponse.json(JSON.parse(data));
  } catch (error: any) {
    console.error("[API Route] Proxy error:", error);
    return NextResponse.json(
      { detail: `Failed to connect to backend: ${error.message}` },
      { status: 500 }
    );
  }
}
