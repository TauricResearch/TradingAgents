"use client";
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { PROVIDERS } from "@/lib/types";
import { Settings, Save, RotateCcw, Loader2, Check } from "lucide-react";

interface SettingsData {
  defaultProvider: string;
  defaultDeepModel: string;
  defaultQuickModel: string;
  defaultDebateRounds: number;
  defaultRiskRounds: number;
  outputLanguage: string;
  checkpointEnabled: boolean;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<SettingsData>({
    defaultProvider: "openai",
    defaultDeepModel: "gpt-5.6",
    defaultQuickModel: "gpt-5.6-luna",
    defaultDebateRounds: 1,
    defaultRiskRounds: 1,
    outputLanguage: "English",
    checkpointEnabled: false,
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    fetch("/api/settings")
      .then((r) => r.json())
      .then((data) => {
        if (data.settings) setSettings(data.settings);
      })
      .catch(() => {});
  }, []);

  const saveSettings = async () => {
    setSaving(true);
    try {
      await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {}
    setSaving(false);
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">
          Default configuration for new analysis runs
        </p>
      </div>

      {/* LLM Defaults */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-primary" />
            Default LLM Configuration
          </CardTitle>
          <CardDescription>
            These defaults are applied to new analysis runs
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-2 block">Default Provider</label>
            <select
              value={settings.defaultProvider}
              onChange={(e) =>
                setSettings({ ...settings, defaultProvider: e.target.value })
              }
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {PROVIDERS.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Deep Thinking Model</label>
              <input
                type="text"
                value={settings.defaultDeepModel}
                onChange={(e) =>
                  setSettings({ ...settings, defaultDeepModel: e.target.value })
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Quick Thinking Model</label>
              <input
                type="text"
                value={settings.defaultQuickModel}
                onChange={(e) =>
                  setSettings({ ...settings, defaultQuickModel: e.target.value })
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Default Debate Rounds</label>
              <input
                type="number"
                min="0"
                max="3"
                value={settings.defaultDebateRounds}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    defaultDebateRounds: parseInt(e.target.value) || 1,
                  })
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Default Risk Rounds</label>
              <input
                type="number"
                min="0"
                max="3"
                value={settings.defaultRiskRounds}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    defaultRiskRounds: parseInt(e.target.value) || 1,
                  })
                }
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>

          <Separator />

          <div>
            <label className="text-sm font-medium mb-2 block">Output Language</label>
            <select
              value={settings.outputLanguage}
              onChange={(e) =>
                setSettings({ ...settings, outputLanguage: e.target.value })
              }
              className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {["English", "Chinese", "Japanese", "Korean", "Spanish", "French", "German", "Portuguese", "Russian"].map(
                (lang) => (
                  <option key={lang} value={lang}>
                    {lang}
                  </option>
                )
              )}
            </select>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Default Checkpoint Resume</p>
              <p className="text-xs text-muted-foreground">
                Enable crash recovery for all new runs
              </p>
            </div>
            <button
              onClick={() =>
                setSettings({
                  ...settings,
                  checkpointEnabled: !settings.checkpointEnabled,
                })
              }
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                settings.checkpointEnabled ? "bg-primary" : "bg-muted"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  settings.checkpointEnabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </CardContent>
      </Card>

      {/* API Keys Status */}
      <Card>
        <CardHeader>
          <CardTitle>API Key Status</CardTitle>
          <CardDescription>
            Set API keys in your .env file in the project root
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[
              { name: "OPENAI_API_KEY", provider: "OpenAI" },
              { name: "GOOGLE_API_KEY", provider: "Google" },
              { name: "ANTHROPIC_API_KEY", provider: "Anthropic" },
              { name: "DEEPSEEK_API_KEY", provider: "DeepSeek" },
              { name: "XAI_API_KEY", provider: "xAI" },
              { name: "OPENROUTER_API_KEY", provider: "OpenRouter" },
              { name: "ALPHA_VANTAGE_API_KEY", provider: "Alpha Vantage" },
              { name: "FRED_API_KEY", provider: "FRED" },
            ].map((key) => (
              <div
                key={key.name}
                className="flex items-center justify-between rounded-md border border-border px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-mono">{key.name}</span>
                  <span className="text-xs text-muted-foreground">({key.provider})</span>
                </div>
                <Badge variant="secondary" className="text-[10px]">
                  Configure in .env
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Save */}
      <div className="flex justify-end gap-3 pb-6">
        <Button
          variant="outline"
          onClick={() => window.location.reload()}
          className="gap-2"
        >
          <RotateCcw className="h-4 w-4" />
          Reset
        </Button>
        <Button onClick={saveSettings} disabled={saving} className="gap-2 min-w-[140px]">
          {saving ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : saved ? (
            <Check className="h-4 w-4 text-green-400" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          {saved ? "Saved!" : "Save Settings"}
        </Button>
      </div>
    </div>
  );
}
