"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
// Input styling handled inline
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { TICKER_PRESETS, ANALYST_TYPES, PROVIDERS } from "@/lib/types";
import {
  Play,
  Settings,
  BarChart3,
  Users,
  Brain,
  ArrowRight,
  Loader2,
  ChevronDown,
} from "lucide-react";

export default function NewAnalysisPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);

  // Form state
  const [ticker, setTicker] = useState("");
  const [analysisDate, setAnalysisDate] = useState(
    new Date().toISOString().split("T")[0]
  );
  const [provider, setProvider] = useState("openai");
  const [deepModel, setDeepModel] = useState("gpt-5.6");
  const [quickModel, setQuickModel] = useState("gpt-5.6-luna");
  const [debateRounds, setDebateRounds] = useState(1);
  const [riskRounds, setRiskRounds] = useState(1);
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>([
    "market",
    "sentiment",
    "news",
    "fundamentals",
  ]);
  const [checkpoint, setCheckpoint] = useState(false);

  const toggleAnalyst = (key: string) => {
    setSelectedAnalysts((prev) =>
      prev.includes(key) ? prev.filter((a) => a !== key) : [...prev, key]
    );
  };

  const handleSubmit = async () => {
    if (!ticker.trim()) return;
    setSubmitting(true);
    try {
      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker: ticker.trim().toUpperCase(),
          analysisDate,
          provider,
          deepModel,
          quickModel,
          debateRounds,
          riskRounds,
          analysts: selectedAnalysts,
          checkpoint,
        }),
      });
      const data = await res.json();
      if (data.session) {
        router.push(`/run/${data.session.id}`);
      }
    } catch (err) {
      console.error("Failed to start analysis:", err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">New Analysis</h1>
        <p className="text-muted-foreground mt-1">
          Configure and launch a multi-agent trading analysis
        </p>
      </div>

      {/* Ticker & Date */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-primary" />
            Target
          </CardTitle>
          <CardDescription>Select the ticker and analysis date</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-2 block">Ticker Symbol</label>
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="e.g. NVDA, AAPL, BTC-USD"
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            {/* Quick picks */}
            <div className="mt-3 space-y-2">
              {TICKER_PRESETS.map((group) => (
                <div key={group.group} className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground w-16 shrink-0">{group.group}</span>
                  <div className="flex flex-wrap gap-1">
                    {group.tickers.map((t) => (
                      <button
                        key={t}
                        onClick={() => setTicker(t)}
                        className={`rounded px-2 py-0.5 text-xs transition-colors ${
                          ticker === t
                            ? "bg-primary text-primary-foreground"
                            : "bg-secondary text-secondary-foreground hover:bg-secondary/80"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Analysis Date</label>
              <input
                type="date"
                value={analysisDate}
                onChange={(e) => setAnalysisDate(e.target.value)}
                max={new Date().toISOString().split("T")[0]}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Research Depth</label>
              <div className="flex gap-2">
                {["quick", "standard", "deep"].map((depth) => (
                  <button
                    key={depth}
                    className={`flex-1 rounded-md border px-3 py-2 text-sm capitalize transition-colors ${
                      depth === "standard"
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border text-muted-foreground hover:bg-accent"
                    }`}
                  >
                    {depth}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* LLM Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-primary" />
            LLM Configuration
          </CardTitle>
          <CardDescription>Choose the language model provider and models</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-2 block">Provider</label>
            <div className="grid grid-cols-3 gap-2">
              {PROVIDERS.map((p) => (
                <button
                  key={p.key}
                  onClick={() => {
                    setProvider(p.key);
                    if (p.models.length > 0) {
                      setDeepModel(p.models[0].id);
                      setQuickModel(p.models.length > 1 ? p.models[1].id : p.models[0].id);
                    }
                  }}
                  className={`rounded-md border px-3 py-2.5 text-sm text-left transition-colors ${
                    provider === p.key
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:bg-accent"
                  }`}
                >
                  <span className="font-medium">{p.label}</span>
                  {p.configured && (
                    <span className="ml-2 text-[10px] text-green-400">(configured)</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Deep Thinking Model</label>
              <select
                value={deepModel}
                onChange={(e) => setDeepModel(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {PROVIDERS.find((p) => p.key === provider)?.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                )) || <option value={deepModel}>{deepModel}</option>}
                <option value="__custom__">Custom model ID...</option>
              </select>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Quick Thinking Model</label>
              <select
                value={quickModel}
                onChange={(e) => setQuickModel(e.target.value)}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {PROVIDERS.find((p) => p.key === provider)?.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                )) || <option value={quickModel}>{quickModel}</option>}
                <option value="__custom__">Custom model ID...</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Analyst Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Analyst Team
          </CardTitle>
          <CardDescription>Select which analysts to include in the analysis</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3">
            {ANALYST_TYPES.map((analyst) => (
              <button
                key={analyst.key}
                onClick={() => toggleAnalyst(analyst.key)}
                className={`rounded-lg border p-4 text-left transition-colors ${
                  selectedAnalysts.includes(analyst.key)
                    ? "border-primary bg-primary/10"
                    : "border-border hover:bg-accent/50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm">{analyst.label}</span>
                  <div
                    className={`h-4 w-4 rounded border-2 flex items-center justify-center ${
                      selectedAnalysts.includes(analyst.key)
                        ? "border-primary bg-primary"
                        : "border-muted-foreground"
                    }`}
                  >
                    {selectedAnalysts.includes(analyst.key) && (
                      <svg className="h-3 w-3 text-primary-foreground" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" />
                      </svg>
                    )}
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{analyst.description}</p>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Debate & Risk Rounds */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-primary" />
            Agent Configuration
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Debate Rounds</label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max="3"
                  value={debateRounds}
                  onChange={(e) => setDebateRounds(parseInt(e.target.value))}
                  className="flex-1 accent-primary"
                />
                <Badge variant="secondary" className="w-8 justify-center">
                  {debateRounds}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Bull vs Bear researcher debate iterations
              </p>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Risk Rounds</label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min="0"
                  max="3"
                  value={riskRounds}
                  onChange={(e) => setRiskRounds(parseInt(e.target.value))}
                  className="flex-1 accent-primary"
                />
                <Badge variant="secondary" className="w-8 justify-center">
                  {riskRounds}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Risk management team discussion rounds
              </p>
            </div>
          </div>

          <Separator />

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Checkpoint Resume</p>
              <p className="text-xs text-muted-foreground">
                Save state after each step for crash recovery
              </p>
            </div>
            <button
              onClick={() => setCheckpoint(!checkpoint)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                checkpoint ? "bg-primary" : "bg-muted"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  checkpoint ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </CardContent>
      </Card>

      {/* Launch */}
      <div className="flex justify-end gap-3 pb-6">
        <Button variant="outline" onClick={() => router.push("/dashboard")}>
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={!ticker.trim() || submitting}
          className="gap-2 min-w-[160px]"
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Starting...
            </>
          ) : (
            <>
              <Play className="h-4 w-4" />
              Launch Analysis
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
