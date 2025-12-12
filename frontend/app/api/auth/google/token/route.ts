/**
 * Next.js API Route for Google OAuth callback
 * This proxies the token exchange to the backend
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { code, redirect_uri } = body;

    if (!code) {
      return NextResponse.json(
        { error: "Missing authorization code" },
        { status: 400 }
      );
    }

    // Forward to backend
    const backendResponse = await fetch(`${BACKEND_URL}/api/auth/google/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ code, redirect_uri }),
    });

    const data = await backendResponse.json();

    if (!backendResponse.ok) {
      return NextResponse.json(data, { status: backendResponse.status });
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error("Token exchange error:", error);
    return NextResponse.json(
      { error: "Token exchange failed", detail: error.message },
      { status: 500 }
    );
  }
}
