import { NextRequest, NextResponse } from "next/server";
import { listSessions, saveSession, loadSettings, generateId } from "@/lib/store";
import { startAnalysis } from "@/lib/process-runner";

export async function GET() {
  const sessions = listSessions();
  return NextResponse.json({ sessions });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const {
      ticker,
      analysisDate,
      provider,
      deepModel,
      quickModel,
      debateRounds,
      riskRounds,
      analysts,
      checkpoint,
    } = body;

    if (!ticker || !analysisDate) {
      return NextResponse.json(
        { error: "ticker and analysisDate are required" },
        { status: 400 }
      );
    }

    const settings = loadSettings();

    const session = startAnalysis(ticker, analysisDate, {
      provider: provider || settings.defaultProvider,
      deepModel: deepModel || settings.defaultDeepModel,
      quickModel: quickModel || settings.defaultQuickModel,
      debateRounds: debateRounds ?? settings.defaultDebateRounds,
      riskRounds: riskRounds ?? settings.defaultRiskRounds,
      analysts: analysts || ["market", "sentiment", "news", "fundamentals"],
      checkpoint: checkpoint ?? settings.checkpointEnabled,
    });

    return NextResponse.json({ session }, { status: 201 });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to create session" },
      { status: 500 }
    );
  }
}
