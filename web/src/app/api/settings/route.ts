import { NextRequest, NextResponse } from "next/server";
import { loadSettings, saveSettings } from "@/lib/store";

export async function GET() {
  const settings = loadSettings();
  return NextResponse.json({ settings });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    saveSettings(body);
    return NextResponse.json({ ok: true });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to save settings" },
      { status: 500 }
    );
  }
}
