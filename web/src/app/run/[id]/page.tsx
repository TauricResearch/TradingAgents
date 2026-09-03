"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { formatDate, formatDuration, statusColor, logLevelColor, agentIcon } from "@/lib/utils";
import {
  ArrowLeft,
  Loader2,
  XCircle,
  FileText,
  Clock,
  Cpu,
  Zap,
  AlertTriangle,
  CheckCircle2,
  Bot,
  Wrench,
  MessageSquare,
  RefreshCw,
} from "lucide-react";
import type { AnalysisSession, LogEntry, AgentEvent } from "@/lib/types";

export default function RunPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [session, setSession] = useState<AnalysisSession | null>(null);
  const [activeTab, setActiveTab] = useState<"logs" | "agents" | "decision">("logs");
  const [logFilter, setLogFilter] = useState<string>("all");
  const logsEndRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  const fetchSession = useCallback(async () => {
    try {
      const res = await fetch(`/api/sessions/${id}`);
      if (res.ok) {
        const data = await res.json();
        setSession(data.session);
      }
    } catch {}
  }, [id]);

  useEffect(() => {
    fetchSession();
    const interval = setInterval(fetchSession, 2000);
    return () => clearInterval(interval);
  }, [fetchSession]);

  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [session?.logs, autoScroll]);

  const cancelRun = async () => {
    await fetch(`/api/sessions/${id}/cancel`, { method: "POST" });
    fetchSession();
  };

  if (!session) {
    return (
      <div className="flex items-center justify-center py-24">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const filteredLogs =
    logFilter === "all"
      ? session.logs
      : session.logs.filter((l) => l.level === logFilter);

  const isRunning = session.status === "running";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-4">
          <Link href="/dashboard">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight">{session.ticker}</h1>
              <Badge className={statusColor(session.status)}>
                {isRunning && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
                {session.status}
              </Badge>
            </div>
            <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {session.analysisDate}
              </span>
              <span>•</span>
              <span className="flex items-center gap-1">
                <Cpu className="h-3.5 w-3.5" />
                {session.llmProvider}
              </span>
              <span>•</span>
              <span>{formatDate(session.createdAt)}</span>
              {session.completedAt && (
                <>
                  <span>•</span>
                  <span>{formatDuration(session.startedAt!, session.completedAt)}</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRunning && (
            <Button variant="destructive" size="sm" onClick={cancelRun} className="gap-1">
              <XCircle className="h-3.5 w-3.5" />
              Cancel
            </Button>
          )}
          {session.reports && session.reports.files.length > 0 && (
            <Link href={`/reports/${session.id}`}>
              <Button variant="outline" size="sm" className="gap-1">
                <FileText className="h-3.5 w-3.5" />
                View Reports
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* Decision banner (if available) */}
      {session.decision && (
        <Card className="border-primary/30 bg-primary/5">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="h-5 w-5 text-primary shrink-0" />
              <div>
                <p className="text-sm font-medium text-primary">Final Decision</p>
                <p className="text-lg font-bold mt-0.5">{session.decision}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Error display */}
      {session.error && (
        <Card className="border-destructive/30 bg-destructive/5">
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <AlertTriangle className="h-5 w-5 text-destructive shrink-0" />
              <div>
                <p className="text-sm font-medium text-destructive">Error</p>
                <p className="text-sm mt-0.5 text-muted-foreground">{session.error}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tab navigation */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {(["logs", "agents", "decision"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab === "logs" && "📋 "}
            {tab === "agents" && "🤖 "}
            {tab === "decision" && "🎯 "}
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Logs tab */}
      {activeTab === "logs" && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Agent Logs</CardTitle>
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  {["all", "info", "agent", "tool", "decision", "warn", "error"].map((f) => (
                    <button
                      key={f}
                      onClick={() => setLogFilter(f)}
                      className={`rounded px-2 py-1 text-xs capitalize transition-colors ${
                        logFilter === f
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-accent"
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setAutoScroll(!autoScroll)}
                  className={autoScroll ? "text-primary" : ""}
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="log-output max-h-[600px] overflow-y-auto rounded-lg bg-black/30 p-4 font-mono text-sm">
              {filteredLogs.length === 0 ? (
                <p className="text-muted-foreground">
                  {isRunning ? "Waiting for logs..." : "No logs recorded"}
                </p>
              ) : (
                filteredLogs.map((log, i) => (
                  <div key={i} className="flex gap-3 py-0.5 hover:bg-white/5">
                    <span className="text-muted-foreground/50 shrink-0 w-[85px]">
                      {new Date(log.timestamp).toLocaleTimeString("en-US", {
                        hour12: false,
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </span>
                    <span
                      className={`shrink-0 w-14 text-right uppercase font-bold ${
                        logLevelColor(log.level)
                      }`}
                    >
                      {log.level}
                    </span>
                    <span className="text-muted-foreground/60 shrink-0 w-24 truncate">
                      [{log.source}]
                    </span>
                    <span className="flex-1 break-words">{log.message}</span>
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Agents tab */}
      {activeTab === "agents" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Agent Events Timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {session.agentEvents.length === 0 ? (
              <p className="text-center py-8 text-muted-foreground">
                {isRunning ? "Agent events will appear here as the analysis runs..." : "No agent events recorded"}
              </p>
            ) : (
              <div className="space-y-2">
                {session.agentEvents.map((event, i) => (
                  <div key={i} className="flex items-start gap-3 rounded-lg border border-border p-3">
                    <div className="text-xl">{agentIcon(event.agent)}</div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm">{event.agent}</span>
                        <Badge
                          variant={
                            event.type === "error"
                              ? "destructive"
                              : event.type === "complete"
                              ? "default"
                              : "secondary"
                          }
                          className="text-[10px]"
                        >
                          {event.type}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {new Date(event.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">{event.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Decision tab */}
      {activeTab === "decision" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Trading Decision</CardTitle>
          </CardHeader>
          <CardContent>
            {session.decision ? (
              <div className="space-y-4">
                <div className="rounded-lg bg-primary/5 border border-primary/20 p-6">
                  <p className="text-2xl font-bold text-primary">{session.decision}</p>
                </div>
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs text-muted-foreground">Ticker</p>
                    <p className="text-lg font-bold">{session.ticker}</p>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs text-muted-foreground">Date</p>
                    <p className="text-lg font-bold">{session.analysisDate}</p>
                  </div>
                  <div className="rounded-lg border border-border p-3">
                    <p className="text-xs text-muted-foreground">Provider</p>
                    <p className="text-lg font-bold capitalize">{session.llmProvider}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                {isRunning ? (
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="h-8 w-8 animate-spin" />
                    <p>Analysis in progress — decision will appear here when ready</p>
                  </div>
                ) : (
                  <p>No decision recorded</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
