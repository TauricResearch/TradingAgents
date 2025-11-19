import { AnalysisRequest, AnalysisStatus, AnalysisResults, HistoricalAnalysisSummary, ConfigPreset } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function startAnalysis(request: AnalysisRequest): Promise<{ analysis_id: string }> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(`Failed to start analysis: ${response.statusText}`);
  }

  return response.json();
}

export async function getAnalysisStatus(analysisId: string): Promise<AnalysisStatus> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/${analysisId}/status`);

  if (!response.ok) {
    throw new Error(`Failed to get analysis status: ${response.statusText}`);
  }

  return response.json();
}

export async function getAnalysisResults(analysisId: string): Promise<AnalysisResults> {
  const response = await fetch(`${API_BASE_URL}/api/analysis/${analysisId}/results`);

  if (!response.ok) {
    throw new Error(`Failed to get analysis results: ${response.statusText}`);
  }

  return response.json();
}

export async function listHistoricalAnalyses(): Promise<HistoricalAnalysisSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/history`);

  if (!response.ok) {
    throw new Error(`Failed to list historical analyses: ${response.statusText}`);
  }

  return response.json();
}

export async function getHistoricalAnalysis(
  ticker: string,
  date: string
): Promise<Record<string, any>> {
  const response = await fetch(`${API_BASE_URL}/api/history/${ticker}/${date}`);

  if (!response.ok) {
    throw new Error(`Failed to get historical analysis: ${response.statusText}`);
  }

  return response.json();
}

export async function listConfigPresets(): Promise<ConfigPreset[]> {
  const response = await fetch(`${API_BASE_URL}/api/config/presets`);

  if (!response.ok) {
    throw new Error(`Failed to list config presets: ${response.statusText}`);
  }

  return response.json();
}

export async function saveConfigPreset(preset: ConfigPreset): Promise<ConfigPreset> {
  const response = await fetch(`${API_BASE_URL}/api/config/save`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(preset),
  });

  if (!response.ok) {
    throw new Error(`Failed to save config preset: ${response.statusText}`);
  }

  return response.json();
}

export async function deleteConfigPreset(name: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/config/presets/${name}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(`Failed to delete config preset: ${response.statusText}`);
  }
}

