import { NextRequest, NextResponse } from "next/server";
import { cancelAnalysis } from "@/lib/process-runner";

export async function POST(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  const cancelled = cancelAnalysis(params.id);
  if (!cancelled) {
    return NextResponse.json(
      { error: "Session not found or not running" },
      { status: 404 }
    );
  }
  return NextResponse.json({ ok: true });
}
