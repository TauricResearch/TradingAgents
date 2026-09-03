"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { formatDate, formatDuration, statusColor, agentIcon } from "@/lib/utils";
import {
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  Trash2,
  Plus,
  TrendingUp,
  Activity,
} from "lucide-react";
import type { AnalysisSession } from "@/lib/types";

export default function DashboardPage() {
  const [sessions, setSessions] = useState<AnalysisSession[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchSessions = useCallback(async () => {
    try {
      const res = await fetch("/api/sessions");
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch (err) {
      console.error("Failed to fetch sessions:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
    const interval = setInterval(fetchSessions, 5000);
    return () => clearInterval(interval);
  }, [fetchSessions]);

  const deleteSession = async (id: string) => {
    await fetch(`/api/sessions/${id}`, { method: "DELETE" });
    setSessions((prev) => prev.filter((s) => s.id !== id));
  };

  const stats = {
    total: sessions.length,
    running: sessions.filter((s) => s.status === "running").length,
    completed: sessions.filter((s) => s.status === "completed").length,
    failed: sessions.filter((s) => s.status === "failed").length,
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground mt-1">
            Monitor your TradingAgents analysis sessions
          </p>
        </div>
        <Link href="/new">
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            New Analysis
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-md bg-primary/10 p-2">
                <TrendingUp className="h-4 w-4 text-primary" />
              </div>
              <div>
                <p className="text-2xl font-bold">{stats.total}</p>
                <p className="text-xs text-muted-foreground">Total Runs</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-md bg-blue-500/10 p-2">
                <Activity className="h-4 w-4 text-blue-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-400">{stats.running}</p>
                <p className="text-xs text-muted-foreground">Running</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-md bg-green-500/10 p-2">
                <CheckCircle2 className="h-4 w-4 text-green-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-green-400">{stats.completed}</p>
                <p className="text-xs text-muted-foreground">Completed</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="rounded-md bg-red-500/10 p-2">
                <XCircle className="h-4 w-4 text-red-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-red-400">{stats.failed}</p>
                <p className="text-xs text-muted-foreground">Failed</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Sessions list */}
      <Card>
        <CardHeader>
          <CardTitle>Analysis Sessions</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <TrendingUp className="h-12 w-12 text-muted-foreground/30 mb-4" />
              <p className="text-muted-foreground mb-4">No analysis sessions yet</p>
              <Link href="/new">
                <Button variant="outline" className="gap-2">
                  <Play className="h-4 w-4" />
                  Start your first analysis
                </Button>
              </Link>
            </div>
          ) : (
            <div className="space-y-2">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className="flex items-center justify-between rounded-lg border border-border p-4 transition-colors hover:bg-accent/50"
                >
                  <div className="flex items-center gap-4">
                    <div className="text-2xl">{agentIcon(session.ticker)}</div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{session.ticker}</span>
                        <Badge className={statusColor(session.status)}>
                          {session.status === "running" && (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          )}
                          {session.status}
                        </Badge>
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {session.analysisDate}
                        </span>
                        <span>•</span>
                        <span>{session.llmProvider}</span>
                        <span>•</span>
                        <span>{formatDate(session.createdAt)}</span>
                        {session.completedAt && (
                          <>
                            <span>•</span>
                            <span>{formatDuration(session.startedAt!, session.completedAt)}</span>
                          </>
                        )}
                      </div>
                      {session.decision && (
                        <p className="mt-1 text-sm text-primary font-medium">
                          Decision: {session.decision}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {session.status === "running" ? (
                      <Link href={`/run/${session.id}`}>
                        <Button variant="outline" size="sm" className="gap-1">
                          <Activity className="h-3 w-3" />
                          View Live
                        </Button>
                      </Link>
                    ) : (
                      <>
                        <Link href={`/run/${session.id}`}>
                          <Button variant="ghost" size="sm">Logs</Button>
                        </Link>
                        {session.reports && session.reports.files.length > 0 && (
                          <Link href={`/reports/${session.id}`}>
                            <Button variant="ghost" size="sm">Reports</Button>
                          </Link>
                        )}
                      </>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-muted-foreground hover:text-destructive"
                      onClick={() => deleteSession(session.id)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
