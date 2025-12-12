/**
 * Next.js API Route for Google OAuth callback redirect
 * Redirects to the auth callback page with the code
 */
import { NextRequest, NextResponse } from "next/server";

// Get the proper base URL from request headers (handles Railway proxy)
function getBaseUrl(request: NextRequest): string {
  // Try to get the forwarded host first (used by proxies like Railway)
  const forwardedHost = request.headers.get("x-forwarded-host");
  const forwardedProto = request.headers.get("x-forwarded-proto") || "https";
  
  if (forwardedHost) {
    return `${forwardedProto}://${forwardedHost}`;
  }
  
  // Fall back to host header
  const host = request.headers.get("host");
  if (host && !host.startsWith("0.0.0.0") && !host.startsWith("localhost")) {
    return `https://${host}`;
  }
  
  // Last resort: use environment variable
  return process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");
  const error = searchParams.get("error");
  
  const baseUrl = getBaseUrl(request);

  // Handle OAuth errors
  if (error) {
    return NextResponse.redirect(
      new URL(`/auth/callback?error=${encodeURIComponent(error)}`, baseUrl)
    );
  }

  // Redirect to callback page with code
  if (code) {
    return NextResponse.redirect(
      new URL(`/auth/callback?code=${encodeURIComponent(code)}`, baseUrl)
    );
  }

  // No code or error
  return NextResponse.redirect(
    new URL("/auth/callback?error=no_code", baseUrl)
  );
}
