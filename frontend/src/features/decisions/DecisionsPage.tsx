/** AI Decision Center: run rail (filterable, security-badged), verdict
 * header, gate waterfall, debate timeline, consensus, evidence with
 * provenance, persistent counterargument column, calibration, agent
 * leaderboard. Rejections are first-class citizens. */
import { Play, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { AgentLeaderboard } from "@/components/AgentLeaderboard";
import { CalibrationChart } from "@/components/CalibrationChart";
import { ConsensusBar } from "@/components/ConsensusBar";
import { DebateTimeline } from "@/components/DebateTimeline";
import { DecisionCard } from "@/components/DecisionCard";
import { DirectionBadge } from "@/components/DirectionBadge";
import { EmptyState } from "@/components/EmptyState";
import { EvidencePanel } from "@/components/EvidencePanel";
import { GateWaterfall } from "@/components/GateWaterfall";
import { PipelineProgressChip } from "@/components/RunPipelineDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import {
  useAgents,
  useOverview,
  useRecommendation,
  useRunEvidence,
  useRuns,
  useRunTimeline,
} from "@/lib/api/queries";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";

type Filter = "all" | "traded" | "rejected";

function RunRail({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const runs = useRuns();
  const [filter, setFilter] = useState<Filter>("all");
  const items = useMemo(() => {
    const list = [...(runs.data ?? [])].reverse();
    if (filter === "traded") return list.filter((r) => r.action && r.action !== "HOLD");
    if (filter === "rejected") return list.filter((r) => r.rejected_at);
    return list;
  }, [runs.data, filter]);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex gap-1 text-xs">
        {(["all", "traded", "rejected"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-full border px-2.5 py-0.5 font-semibold capitalize",
              filter === f
                ? "border-accent bg-accent text-on-solid"
                : "border-border text-fg-subtle hover:text-fg",
            )}
            aria-pressed={filter === f}
          >
            {f}
          </button>
        ))}
      </div>
      <ol className="min-h-0 grow space-y-1 overflow-y-auto pr-1" data-testid="run-rail">
        {items.length === 0 && (
          <EmptyState kind="empty" title="No runs match" className="py-4" />
        )}
        {items.map((run) => (
          <li key={run.run_id}>
            <button
              onClick={() => onSelect(run.run_id)}
              className={cn(
                "w-full rounded-[14px] border px-2.5 py-1.5 text-left text-xs",
                selected === run.run_id
                  ? "border-accent bg-accent-muted"
                  : "border-border bg-surface-2/60 hover:border-border-strong",
              )}
            >
              <div className="flex items-center justify-between">
                <DirectionBadge value={run.action ?? "rejected"} showWord={false} />
                <span className="text-fg-subtle">{fmtDateTime(run.started_at)}</span>
              </div>
              <div className="mt-0.5 flex items-center gap-1">
                <span className="font-mono">{run.symbol}</span>
                {run.timeframe && (
                  <Badge className="px-1.5 font-mono text-[10px]">
                    {run.timeframe}
                  </Badge>
                )}
                {run.action ? (
                  <span>{run.action}</span>
                ) : (
                  <Badge variant="neutral" className="px-1.5 text-[10px]">
                    rejected @ {run.rejected_at}
                  </Badge>
                )}
              </div>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}

export default function DecisionsPage() {
  const params = useParams<{ runId?: string }>();
  const navigate = useNavigate();
  const setRunDialogOpen = useUiStore((s) => s.setRunDialogOpen);
  const runs = useRuns();
  const overview = useOverview();
  const recommendation = useRecommendation();
  const agents = useAgents();

  const latestId = runs.data?.[runs.data.length - 1]?.run_id ?? null;
  const selected = params.runId ?? latestId;
  const isLatest = selected != null && selected === latestId;

  const timeline = useRunTimeline(selected, isLatest);
  const evidence = useRunEvidence(selected, isLatest);

  const missingFeeds = isLatest ? (overview.data?.missing_feeds ?? []) : [];
  const quarantinedRun =
    timeline.data == null
      ? false
      : missingFeeds.some((f) => f.startsWith("news:quarantined"));

  if (runs.isPending) return <SkeletonCard lines={8} />;
  if ((runs.data ?? []).length === 0) {
    return (
      <div className="space-y-3">
        <EmptyState
          kind="waiting"
          title="No runs yet"
          detail="Trigger a pipeline run now, or wait for the hourly loop's next decision."
        />
        <div className="flex justify-center">
          <Button onClick={() => setRunDialogOpen(true)} data-testid="run-pipeline-cta">
            <Play size={13} /> Run pipeline now
          </Button>
        </div>
      </div>
    );
  }

  const judgeEntry = timeline.data?.entries.find((e) => e.speaker === "judge");
  const votes = recommendation.data?.vote_breakdown?.votes ?? [];

  return (
    <div className="grid gap-4 lg:grid-cols-[240px_1fr_300px]">
      <Card className="lg:h-[calc(100vh-8rem)] lg:overflow-hidden">
        <CardHeader>
          <CardTitle>Runs</CardTitle>
          <Button
            size="sm"
            variant="outline"
            onClick={() => setRunDialogOpen(true)}
            data-testid="run-pipeline-open"
          >
            <Play size={12} /> Run
          </Button>
        </CardHeader>
        <CardContent className="h-full">
          <RunRail
            selected={selected}
            onSelect={(id) => navigate(`/decisions/${id}`)}
          />
        </CardContent>
      </Card>

      <div className="min-w-0 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>
              Verdict{" "}
              {isLatest ? (
                <span className="text-fg-subtle">(latest — following)</span>
              ) : (
                <span className="text-fg-subtle">(pinned)</span>
              )}
            </CardTitle>
            {quarantinedRun && (
              <Badge variant="bear">
                <ShieldAlert size={12} /> injection quarantined
              </Badge>
            )}
            <PipelineProgressChip />
          </CardHeader>
          <CardContent>
            {isLatest ? (
              recommendation.isPending ? (
                <SkeletonCard lines={5} />
              ) : (
                <DecisionCard rec={recommendation.data} />
              )
            ) : (
              <p className="text-sm text-fg-muted">
                Historical run — full recommendation payloads are kept for the
                latest run; the debate transcript and evidence below are this
                run's complete record.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Gate waterfall</CardTitle>
          </CardHeader>
          <CardContent>
            {timeline.data ? (
              <GateWaterfall
                nodeSequence={timeline.data.node_sequence}
                rejection={timeline.data.rejection}
              />
            ) : (
              <SkeletonCard lines={2} />
            )}
          </CardContent>
        </Card>

        {votes.length > 0 && isLatest && (
          <Card>
            <CardHeader>
              <CardTitle>Consensus</CardTitle>
            </CardHeader>
            <CardContent>
              <ConsensusBar
                votes={votes}
                judgeAction={recommendation.data?.action ?? judgeEntry?.stance}
              />
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Debate timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {timeline.isPending ? (
              <SkeletonCard lines={6} />
            ) : timeline.data ? (
              <DebateTimeline timeline={timeline.data} />
            ) : (
              <EmptyState kind="error" title="Timeline unavailable" />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Evidence</CardTitle>
          </CardHeader>
          <CardContent>
            {evidence.isPending ? (
              <SkeletonCard lines={6} />
            ) : evidence.data ? (
              <EvidencePanel panels={evidence.data} missingFeeds={missingFeeds} />
            ) : (
              <EmptyState kind="error" title="Evidence unavailable" />
            )}
          </CardContent>
        </Card>
      </div>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>Calibration</CardTitle>
          </CardHeader>
          <CardContent>
            {agents.data ? (
              <CalibrationChart perf={agents.data} />
            ) : (
              <SkeletonCard lines={4} />
            )}
            <p className="mt-2 text-xs text-fg-subtle">
              Does stated confidence match realized accuracy? Hollow points =
              insufficient sample. This chart is the product's honesty metric.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Agent leaderboard</CardTitle>
          </CardHeader>
          <CardContent>
            {agents.data ? (
              <AgentLeaderboard perf={agents.data} />
            ) : (
              <SkeletonCard lines={6} />
            )}
          </CardContent>
        </Card>
        <p className="text-xs text-fg-subtle">
          Every claim cites machine-readable data refs.{" "}
          <Link to="/legacy" className="text-accent hover:underline" reloadDocument>
            Legacy view
          </Link>
        </p>
      </div>
    </div>
  );
}
