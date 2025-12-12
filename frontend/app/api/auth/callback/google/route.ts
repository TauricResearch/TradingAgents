/**
 * Next.js API Route for Google OAuth callback redirect
 * Redirects to the auth callback page with the code
 */
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get("code");
  const error = searchParams.get("error");

  // Handle OAuth errors
  if (error) {
    return NextResponse.redirect(
      new URL(`/auth/callback?error=${encodeURIComponent(error)}`, request.url)
    );
  }

  // Redirect to callback page with code
  if (code) {
    return NextResponse.redirect(
      new URL(`/auth/callback?code=${encodeURIComponent(code)}`, request.url)
    );
  }

  // No code or error
  return NextResponse.redirect(
    new URL("/auth/callback?error=no_code", request.url)
  );
}
