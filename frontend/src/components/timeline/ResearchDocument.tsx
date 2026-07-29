import { useMemo, useState, type ReactNode } from "react";
import { extractResponse } from "../../domain/responseExtractor";
import {
  buildResearchDocument,
  type ResearchEntry,
} from "../../domain/researchDocument";
import { stageColorClass } from "../../domain/roles";
import { useArtifact } from "../../hooks/useArtifact";
import type { ReducerState } from "../../state/model";
import { FinalReport } from "../shared/FinalReport";
import { SafeMarkdown } from "../shared/SafeMarkdown";

interface ResearchDocumentProps {
  state: ReducerState;
  run_id: string | null;
  onTurnSelected: (turn_id: string) => void;
}

function entryStatus(entry: ResearchEntry): string {
  switch (entry.status) {
    case "committed":
      return "已纳入研究结论";
    case "candidate":
    case "output_ready":
      return "候选输出，尚未提交";
    case "waiting":
      return "等待此阶段开始";
    case "started":
    case "resumed":
      return "正在分析";
    case "interrupted":
      return "本轮未完成";
    case "failed":
      return "该阶段失败";
    case "cancelled":
      return "已取消";
    default:
      return entry.status;
  }
}

function extractBusinessText(actor_id: string, content: string): string | null {
  try {
    const parsed: unknown = JSON.parse(content);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    return extractResponse(actor_id, parsed as Record<string, unknown>).text;
  } catch {
    return null;
  }
}

function excerpt(content: string): string {
  const compact = content.replace(/\s+/g, " ").trim();
  return compact.length > 320 ? `${compact.slice(0, 320)}…` : compact;
}

function ResearchEntryCard({
  entry,
  run_id,
  onTurnSelected,
}: {
  entry: ResearchEntry;
  run_id: string | null;
  onTurnSelected: (turn_id: string) => void;
}): JSX.Element {
  const isCommitted = entry.status === "committed";
  // Candidate artifacts may be replaced or abandoned.  Do not fetch or expose
  // them in the reading surface before a graph checkpoint has applied them.
  const { content, loading, error } = useArtifact(
    run_id,
    isCommitted ? entry.artifact_id : null,
  );
  const [expanded, setExpanded] = useState(false);
  const body = useMemo(() => {
    if (content === null) return null;
    return entry.artifact_kind === "report"
      ? content
      : extractBusinessText(entry.actor_id, content);
  }, [content, entry.actor_id, entry.artifact_kind]);
  const colorClass = stageColorClass(entry.actor_id);

  return (
    <article className={["research-entry", colorClass].filter(Boolean).join(" ")}>
      <button
        type="button"
        className="research-entry-head"
        onClick={() => entry.turn_id && onTurnSelected(entry.turn_id)}
      >
        <span className="research-entry-role">{entry.label}</span>
        <span className={isCommitted ? "research-status committed" : "research-status"}>
          {entryStatus(entry)}
        </span>
      </button>
      {entry.turn_index !== null && entry.turn_index > 1 && (
        <span className="round-label">第 {entry.turn_index} 轮</span>
      )}
      {entry.status === "waiting" ? (
        <p className="placeholder">该角色尚未开始。</p>
      ) : !isCommitted ? (
        <p className="placeholder">{entryStatus(entry)}。</p>
      ) : loading ? (
        <p className="placeholder">正在加载已提交的研究内容…</p>
      ) : error !== null ? (
        <p className="entry-error">内容读取失败：{error}</p>
      ) : body ? (
        <>
          <p className="research-excerpt">{excerpt(body)}</p>
          <button
            type="button"
            className="research-expand"
            aria-expanded={expanded}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "收起完整内容" : "展开完整内容"}
          </button>
          {expanded && <SafeMarkdown content={body} className="research-markdown" />}
        </>
      ) : (
        <p className="placeholder">已提交，但没有可显示的文本内容。</p>
      )}
    </article>
  );
}

function Phase({
  number,
  title,
  children,
}: {
  number: number;
  title: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <section className="research-phase">
      <div className="research-phase-head">
        <span>0{number}</span>
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

/** Research-reading projection: one stable document for live, history, and resume. */
export function ResearchDocument({
  state,
  run_id,
  onTurnSelected,
}: ResearchDocumentProps): JSX.Element {
  const document = buildResearchDocument(state);
  return (
    <div className="research-document">
      <Phase number={1} title="独立分析">
        <div className="research-grid analysts-grid">
          {document.analysts.map((entry) => (
            <ResearchEntryCard
              key={entry.actor_id}
              entry={entry}
              run_id={run_id}
              onTurnSelected={onTurnSelected}
            />
          ))}
        </div>
      </Phase>

      <Phase number={2} title="证据校验">
        <ResearchEntryCard
          entry={document.evidence}
          run_id={run_id}
          onTurnSelected={onTurnSelected}
        />
      </Phase>

      <Phase number={3} title="多空辩论">
        {document.debate_rounds.length === 0 ? (
          <p className="placeholder">等待多空研究阶段开始。</p>
        ) : (
          document.debate_rounds.map((round) => (
            <div key={round.round} className="debate-round">
              <div className="round-heading">第 {round.round} 轮</div>
              <div className="research-grid two-up">
                <ResearchEntryCard entry={round.bull} run_id={run_id} onTurnSelected={onTurnSelected} />
                <ResearchEntryCard entry={round.bear} run_id={run_id} onTurnSelected={onTurnSelected} />
              </div>
            </div>
          ))
        )}
      </Phase>

      <Phase number={4} title="研究经理裁决">
        <ResearchEntryCard
          entry={document.research_verdict}
          run_id={run_id}
          onTurnSelected={onTurnSelected}
        />
      </Phase>

      <Phase number={5} title="交易计划">
        <ResearchEntryCard
          entry={document.trading_plan}
          run_id={run_id}
          onTurnSelected={onTurnSelected}
        />
      </Phase>

      <Phase number={6} title="风险讨论">
        {document.risk_rounds.length === 0 ? (
          <p className="placeholder">等待风险讨论阶段开始。</p>
        ) : (
          document.risk_rounds.map((round) => (
            <div key={round.round} className="debate-round">
              <div className="round-heading">第 {round.round} 轮</div>
              <div className="research-grid risk-grid">
                <ResearchEntryCard entry={round.aggressive} run_id={run_id} onTurnSelected={onTurnSelected} />
                <ResearchEntryCard entry={round.conservative} run_id={run_id} onTurnSelected={onTurnSelected} />
                <ResearchEntryCard entry={round.neutral} run_id={run_id} onTurnSelected={onTurnSelected} />
              </div>
            </div>
          ))
        )}
      </Phase>

      <Phase number={7} title="组合经理裁决">
        <ResearchEntryCard
          entry={document.portfolio_verdict}
          run_id={run_id}
          onTurnSelected={onTurnSelected}
        />
      </Phase>

      <FinalReport state={state} run_id={run_id} />
    </div>
  );
}
