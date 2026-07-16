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
import { DecisionPipeline3D } from "@/components/DecisionPipeline3D";
import { DirectionBadge } from "@/components/DirectionBadge";
import { EmptyState } from "@/components/EmptyState";
import { EvidencePanel } from "@/components/EvidencePanel";
import { GateWaterfall } from "@/components/GateWaterfall";
import { PipelineProgressChip } from "@/components/RunPipelineDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SkeletonCard } from "@/components/ui/skeleton";
import { MIN_ANALOG_SIMILARITY } from "@/lib/thresholds";
import {
  useAgents,
  useOverview,
  useRecommendation,
  useRunEvidence,
  useRunRecommendation,
  useRuns,
  useRunTimeline,
} from "@/lib/api/queries";
import { fmtDateCompact } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useLiveStages } from "@/stores/pipelineLive";
import { usePipelineProgress, useUiStore } from "@/stores/ui";

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
      <div className="mb-2.5 flex gap-1 text-[11px]">
        {(["all", "traded", "rejected"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "rounded-full border px-3 py-[3px] lowercase",
              filter === f
                ? "border-accent bg-accent font-bold text-on-solid"
                : "border-border-strong font-semibold text-fg-subtle hover:text-fg",
            )}
            aria-pressed={filter === f}
          >
            {f}
          </button>
        ))}
      </div>
      <ol className="min-h-0 grow space-y-1.5 overflow-y-auto pr-1" data-testid="run-rail">
        {items.length === 0 && (
          <EmptyState kind="empty" title="No runs match" className="py-4" />
        )}
        {items.map((run) => (
          <li key={run.run_id}>
            <button
              onClick={() => onSelect(run.run_id)}
              className={cn(
                "w-full rounded-[14px] border px-3 py-2 text-left text-[11.5px] text-fg",
                "transition-[transform,box-shadow] duration-200",
                "hover:-translate-y-px hover:shadow-[var(--shadow-card)]",
                selected === run.run_id
                  ? "border-accent bg-accent-muted"
                  : "border-border bg-transparent",
              )}
            >
              <div className="flex items-center justify-between gap-1">
                <DirectionBadge
                  value={run.action ?? "rejected"}
                  className="font-extrabold"
                />
                <span className="whitespace-nowrap text-[10.5px] text-fg-subtle">
                  {fmtDateCompact(run.started_at)}
                </span>
              </div>
              <div className="mt-[3px] flex items-center gap-[5px]">
                <span className="font-mono font-semibold">{run.symbol}</span>
                {run.timeframe && (
                  <span className="inline-flex items-center rounded-[6px] bg-surface-2 px-1.5 font-mono text-[9.5px] text-fg-muted">
                    {run.timeframe}
                  </span>
                )}
                {!run.action && (
                  <span className="inline-flex items-center rounded-[6px] bg-bear-muted px-1.5 font-mono text-[9.5px] text-bear">
                    @ {run.rejected_at}
                  </span>
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
  const pipelineProgress = usePipelineProgress();
  const liveStages = useLiveStages();
  const runs = useRuns();
  const overview = useOverview();
  const recommendation = useRecommendation();
  const agents = useAgents();

  const latestId = runs.data?.[runs.data.length - 1]?.run_id ?? null;
  const selected = params.runId ?? latestId;
  const isLatest = selected != null && selected === latestId;

  const timeline = useRunTimeline(selected, isLatest);
  const evidence = useRunEvidence(selected, isLatest);
  // historical runs serve their persisted ticket (G8); latest keeps the
  // live recommendation hook (follow-latest behavior unchanged)
  const historicalTicket = useRunRecommendation(isLatest ? null : selected);

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
  const shownRec = isLatest ? recommendation.data : historicalTicket.data;
  const selectedRun = runs.data?.find((r) => r.run_id === selected);
  const runNo = (runs.data?.findIndex((r) => r.run_id === selected) ?? -1) + 1;
  const runLabel = selectedRun
    ? `${isLatest ? "last run" : "run"} · ${selectedRun.symbol}${
        selectedRun.timeframe ? ` ${selectedRun.timeframe}` : ""
      } · #${runNo}`
    : "—";

  return (
    <div className="grid gap-4 lg:grid-cols-[250px_minmax(0,1fr)_310px]">
      <Card className="lg:col-span-full">
        <CardHeader>
          <CardTitle>Decision pipeline</CardTitle>
        </CardHeader>
        <CardContent>
          <DecisionPipeline3D
            timeline={timeline.data}
            evidence={evidence.data}
            rec={shownRec}
            live={pipelineProgress}
            liveStages={liveStages}
            runLabel={runLabel}
          />
        </CardContent>
      </Card>

      <Card className="lg:h-[calc(100vh-8rem)] lg:overflow-hidden">
        <CardHeader>
          <CardTitle>Runs</CardTitle>
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
                <span className="font-medium normal-case tracking-normal text-fg-subtle">(latest — following)</span>
              ) : (
                <span className="font-medium normal-case tracking-normal text-fg-subtle">(pinned)</span>
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
            ) : historicalTicket.isPending ? (
              <SkeletonCard lines={5} />
            ) : historicalTicket.data ? (
              <DecisionCard rec={historicalTicket.data} />
            ) : (
              <p className="text-sm text-fg-muted">
                This run predates ticket persistence — the debate transcript
                and evidence below are its complete record.
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
            <CardTitle>Similar past setups</CardTitle>
          </CardHeader>
          <CardContent>
            {(() => {
              const shown = isLatest ? recommendation.data : historicalTicket.data;
              const all = shown?.historical_analogs ?? [];
              // weak matches are noise, not analogs (review P0.6): only
              // credible similarity renders; the best reject is disclosed
              const analogs = all.filter(
                (a) => (a.similarity ?? 0) >= MIN_ANALOG_SIMILARITY,
              );
              if (analogs.length === 0)
                return (
                  <p className="text-xs text-fg-subtle">
                    {all.length > 0
                      ? `no sufficiently similar past setups (best match ${Math.round(
                          Math.max(...all.map((a) => a.similarity ?? 0)) * 100,
                        )}%, shown from ${Math.round(MIN_ANALOG_SIMILARITY * 100)}%)`
                      : "No closed analogs yet — this panel fills as similar setups resolve and their outcomes are recorded."}
                  </p>
                );
              return (
                <ul className="space-y-2 text-xs" data-testid="analogs-panel">
                  {analogs.map((analog, i) => (
                    <li key={i} className="rounded-[10px] bg-surface-2 px-2.5 py-2">
                      <p>{analog.description}</p>
                      <p className="mt-1 text-fg-muted">
                        outcome: {analog.outcome}
                        {analog.similarity != null && (
                          <span className="text-fg-subtle">
                            {" "}· similarity {(analog.similarity * 100).toFixed(0)}%
                          </span>
                        )}
                      </p>
                    </li>
                  ))}
                </ul>
              );
            })()}
          </CardContent>
        </Card>
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
            <p className="mt-2 text-[11px] text-fg-subtle">
              Hollow points = insufficient sample. This chart is the product's
              honesty metric.
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
