/**
 * API route to expose public configuration
 * This allows environment variables to be loaded at runtime instead of build time
 */
import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    googleClientId: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "",
  });
}
