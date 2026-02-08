import { useState, useMemo } from 'react';
import { X, Clock, Timer, CheckCircle, AlertCircle, FileText, MessageSquare, ChevronDown, ChevronRight, Terminal, Bot, User, GitBranch, ArrowRight, Info, Wrench } from 'lucide-react';
import type { FlowchartNodeData, FullPipelineData, StepDetails } from '../../types/pipeline';
import { STEP_INPUT_SOURCES, FLOWCHART_STEPS, mapPipelineToFlowchart } from '../../types/pipeline';

interface NodeDetailDrawerProps {
  node: FlowchartNodeData;
  pipelineData: FullPipelineData | null;
  onClose: () => void;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const day = d.getDate().toString().padStart(2, '0');
  const month = (d.getMonth() + 1).toString().padStart(2, '0');
  const year = d.getFullYear();
  const time = d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  return `${day}/${month}/${year} ${time}`;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const secs = ms / 1000;
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = Math.floor(secs % 60);
  return `${mins}m ${remSecs}s`;
}

/**
 * Extract the ACTUAL meaningful output for a step.
 * Prefers agent_reports and debate content over raw step_details.response,
 * since the latter may contain "TOOL_CALL:" noise or be empty for debate steps.
 */
function getStepOutput(node: FlowchartNodeData, data: FullPipelineData | null): string {
  // 1. Agent report content (for analyst steps)
  if (node.agentReport?.report_content) return node.agentReport.report_content;
  // 2. Debate content (for debate participants)
  if (node.debateContent) return node.debateContent;
  // 3. Output summary from pipeline step
  if (node.output_summary) return node.output_summary;
  // 4. Try debate tables directly
  if (data) {
    if (node.debateType === 'investment' && data.debates?.investment) {
      const d = data.debates.investment;
      if (node.debateRole === 'bull') return d.bull_arguments || '';
      if (node.debateRole === 'bear') return d.bear_arguments || '';
      if (node.debateRole === 'judge') return d.judge_decision || '';
    }
    if (node.debateType === 'risk' && data.debates?.risk) {
      const d = data.debates.risk;
      if (node.debateRole === 'risky') return d.risky_arguments || '';
      if (node.debateRole === 'safe') return d.safe_arguments || '';
      if (node.debateRole === 'neutral') return d.neutral_arguments || '';
      if (node.debateRole === 'judge') return d.judge_decision || '';
    }
  }
  return '';
}

/** Collapsible section component */
function Section({ title, icon: Icon, iconColor, defaultOpen, children, badge }: {
  title: string;
  icon: React.ElementType;
  iconColor: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
  badge?: string;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <div className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 bg-slate-50 dark:bg-slate-900/50 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors text-left"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />}
        <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${iconColor}`} />
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 flex-1">{title}</span>
        {badge && (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-gray-500 dark:text-gray-400">
            {badge}
          </span>
        )}
      </button>
      {open && (
        <div className="border-t border-slate-200 dark:border-slate-700">
          {children}
        </div>
      )}
    </div>
  );
}

/** Code block with monospace text */
function CodeBlock({ content, maxHeight = 'max-h-64' }: { content: string; maxHeight?: string }) {
  return (
    <div className={`${maxHeight} overflow-y-auto p-3 bg-slate-900 dark:bg-black/40`}>
      <pre className="text-xs text-green-300 dark:text-green-400 font-mono whitespace-pre-wrap leading-relaxed">
        {content}
      </pre>
    </div>
  );
}

/** Tool call with optional result */
interface ToolCallEntry {
  name: string;
  args: string;
  result_preview?: string;
}

/** Get tool calls: prefer stored step_details.tool_calls, fall back to text parsing */
function getToolCalls(details: StepDetails | undefined, rawResponse: string): ToolCallEntry[] {
  // Prefer stored tool_calls with actual results from the backend
  if (details?.tool_calls && details.tool_calls.length > 0) {
    return details.tool_calls.map(tc => ({
      name: tc.name,
      args: tc.args || '',
      result_preview: tc.result_preview,
    }));
  }
  // Fallback: parse TOOL_CALL: patterns from response text (legacy data)
  const regex = /TOOL_CALL:\s*(\w+)\(([^)]*)\)/g;
  const calls: ToolCallEntry[] = [];
  let match;
  while ((match = regex.exec(rawResponse)) !== null) {
    calls.push({ name: match[1], args: match[2] });
  }
  return calls;
}

/** Strip TOOL_CALL lines from response to get only the prose */
function stripToolCalls(text: string): string {
  return text.replace(/TOOL_CALL:\s*\w+\([^)]*\)\s*/g, '').trim();
}

/** Collapsible result preview for a single tool call */
function ToolResultPreview({ result }: { result: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = result.length > 200;
  const display = expanded ? result : result.slice(0, 200);

  return (
    <div className="mt-1.5">
      <div className="text-[10px] font-semibold text-green-600 dark:text-green-400 mb-0.5 flex items-center gap-1">
        <CheckCircle className="w-2.5 h-2.5" />
        Result:
      </div>
      <div className="max-h-40 overflow-y-auto rounded bg-slate-900 dark:bg-black/40 px-2 py-1.5">
        <pre className="text-[10px] text-green-300 dark:text-green-400 font-mono whitespace-pre-wrap leading-relaxed break-all">
          {display}{isLong && !expanded ? '...' : ''}
        </pre>
      </div>
      {isLong && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-[10px] text-blue-500 hover:text-blue-400 mt-0.5"
        >
          {expanded ? 'Show less' : `Show all (${result.length} chars)`}
        </button>
      )}
    </div>
  );
}

/** Tool calls panel showing invocations and their results */
function ToolCallsPanel({ calls }: { calls: ToolCallEntry[] }) {
  if (calls.length === 0) return null;

  return (
    <div className="divide-y divide-slate-200 dark:divide-slate-700">
      {calls.map((call, i) => {
        // Distinguish: undefined/null = no data stored, empty string = tool returned nothing, error = starts with [
        const resultStored = call.result_preview !== undefined && call.result_preview !== null;
        const isError = resultStored && call.result_preview!.startsWith('[');
        const hasData = resultStored && call.result_preview!.length > 0 && !isError;
        const isEmpty = resultStored && call.result_preview!.length === 0;
        return (
          <div key={i} className="px-3 py-2 flex items-start gap-2">
            <div className={`flex-shrink-0 mt-0.5 w-5 h-5 rounded flex items-center justify-center ${
              hasData
                ? 'bg-green-100 dark:bg-green-900/30'
                : isError
                  ? 'bg-red-100 dark:bg-red-900/30'
                  : resultStored
                    ? 'bg-slate-100 dark:bg-slate-800'
                    : 'bg-amber-100 dark:bg-amber-900/30'
            }`}>
              <Wrench className={`w-3 h-3 ${
                hasData ? 'text-green-600 dark:text-green-400'
                  : isError ? 'text-red-600 dark:text-red-400'
                  : resultStored ? 'text-slate-500 dark:text-slate-400'
                  : 'text-amber-600 dark:text-amber-400'
              }`} />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 font-mono">{call.name}</span>
                <span className="text-[10px] text-gray-400">(#{i + 1})</span>
                {resultStored && (
                  <span className={`text-[9px] px-1 py-0.5 rounded font-medium ${
                    hasData
                      ? 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                      : isError
                        ? 'bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                  }`}>
                    {hasData ? 'executed' : isError ? 'error' : 'empty result'}
                  </span>
                )}
              </div>
              <div className="mt-0.5 text-[11px] font-mono text-gray-500 dark:text-gray-400 break-all">
                ({call.args})
              </div>
              {hasData && (
                <ToolResultPreview result={call.result_preview!} />
              )}
              {isError && (
                <div className="mt-1 text-[10px] text-red-600 dark:text-red-400">
                  {call.result_preview}
                </div>
              )}
              {isEmpty && (
                <div className="mt-1 text-[10px] text-slate-500 dark:text-slate-400 italic">
                  Tool executed but returned no data
                </div>
              )}
              {!resultStored && (
                <div className="mt-1 text-[10px] text-amber-600 dark:text-amber-400 italic">
                  No result data available (legacy run)
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** Context received panel showing data lineage */
function ContextReceivedPanel({ node, pipelineData }: { node: FlowchartNodeData; pipelineData: FullPipelineData | null }) {
  const inputSources = STEP_INPUT_SOURCES[node.id] || [];
  const allNodes = useMemo(() => mapPipelineToFlowchart(pipelineData), [pipelineData]);

  if (inputSources.length === 0) {
    return (
      <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-slate-50 dark:bg-slate-900/40 border border-slate-200 dark:border-slate-700">
        <Info className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
        <span className="text-xs text-slate-500 dark:text-slate-400">
          Independent step — no forwarded context from previous steps
        </span>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-blue-200 dark:border-blue-800/60 bg-blue-50/50 dark:bg-blue-900/10 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-900/20 border-b border-blue-200 dark:border-blue-800/60">
        <GitBranch className="w-3.5 h-3.5 text-blue-500 flex-shrink-0" />
        <span className="text-xs font-semibold text-blue-700 dark:text-blue-300">
          Context Received from {inputSources.length} Previous Steps
        </span>
      </div>
      <div className="px-3 py-2.5 flex flex-wrap gap-1.5">
        {inputSources.map(sourceId => {
          const stepDef = FLOWCHART_STEPS.find(s => s.id === sourceId);
          const sourceNode = allNodes.find(n => n.id === sourceId);
          const isCompleted = sourceNode?.status === 'completed';
          const label = stepDef?.label || sourceId;

          return (
            <span
              key={sourceId}
              className={`inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border ${
                isCompleted
                  ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800/60'
                  : 'bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border-slate-200 dark:border-slate-700'
              }`}
            >
              {isCompleted ? (
                <CheckCircle className="w-3 h-3 text-green-500 flex-shrink-0" />
              ) : (
                <Clock className="w-3 h-3 text-slate-400 flex-shrink-0" />
              )}
              {label}
              <ArrowRight className="w-2.5 h-2.5 opacity-40" />
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** Empty state for steps with no data */
function EmptyState({ status }: { status: string }) {
  if (status === 'pending') {
    return (
      <div className="text-center py-6 text-gray-400 dark:text-gray-500">
        <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p className="text-sm">This step hasn't run yet</p>
        <p className="text-xs mt-1">Run an analysis to see results here</p>
      </div>
    );
  }
  if (status === 'running') {
    return (
      <div className="text-center py-6 text-blue-500 dark:text-blue-400">
        <div className="w-8 h-8 mx-auto mb-2 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm">Processing...</p>
      </div>
    );
  }
  return (
    <div className="text-center py-6 text-gray-400 dark:text-gray-500">
      <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
      <p className="text-sm">No output data available</p>
    </div>
  );
}

export function NodeDetailDrawer({ node, pipelineData, onClose }: NodeDetailDrawerProps) {
  const details: StepDetails | undefined = node.step_details;
  const inputSources = STEP_INPUT_SOURCES[node.id] || [];
  const hasForwardedContext = inputSources.length > 0;

  // Step Output: the ACTUAL meaningful output (agent report / debate content first, then raw response)
  // Always strip TOOL_CALL lines from step output since they're noise in the output view
  const rawStepOutput = getStepOutput(node, pipelineData) || details?.response || '';
  const stepOutput = stripToolCalls(rawStepOutput);
  // Raw LLM Response: the raw text from step_details (may contain TOOL_CALL noise)
  const rawResponse = details?.response || '';
  // Get tool calls: prefers stored results from backend, falls back to text parsing
  const parsedToolCalls = useMemo(() => getToolCalls(details, rawResponse), [details, rawResponse]);
  // Clean response = raw response minus TOOL_CALL lines (for display without noise)
  const cleanRawResponse = useMemo(() => parsedToolCalls.length > 0 ? stripToolCalls(rawResponse) : rawResponse, [rawResponse, parsedToolCalls]);
  // Only show raw response section if it differs from step output (avoid duplication)
  const showRawResponse = rawResponse && rawResponse !== stepOutput;

  const hasAnyContent = stepOutput || details?.user_prompt || details?.system_prompt;

  return (
    <div className="mt-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg overflow-hidden animate-in slide-in-from-top-2">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-slate-50 dark:bg-slate-900/50 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-gray-500" />
          <span className="font-semibold text-sm text-gray-800 dark:text-gray-200">
            {node.label}
          </span>
          <span className="text-[10px] text-gray-400">#{node.number}</span>
          {node.status === 'completed' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400 font-medium">
              completed
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-slate-200 dark:hover:bg-slate-700 rounded transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Timing info bar */}
      <div className="flex flex-wrap items-center gap-3 sm:gap-5 px-4 py-2 bg-slate-50/50 dark:bg-slate-900/30 border-b border-slate-100 dark:border-slate-800 text-xs">
        {node.started_at && (
          <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
            <Clock className="w-3 h-3" />
            <span>Started: {formatTimestamp(node.started_at)}</span>
          </div>
        )}
        {node.completed_at && (
          <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
            <CheckCircle className="w-3 h-3 text-green-500" />
            <span>Completed: {formatTimestamp(node.completed_at)}</span>
          </div>
        )}
        {node.duration_ms != null && (
          <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
            <Timer className="w-3 h-3" />
            <span className="font-mono font-semibold">{formatDuration(node.duration_ms)}</span>
          </div>
        )}
        {node.status === 'error' && (
          <div className="flex items-center gap-1.5 text-red-500">
            <AlertCircle className="w-3 h-3" />
            <span>Failed</span>
          </div>
        )}
      </div>

      {/* Content sections — unified flow, no branching */}
      <div className="p-3 space-y-2">
        {/* 1. Context Received — always first */}
        <ContextReceivedPanel node={node} pipelineData={pipelineData} />

        {hasAnyContent ? (
          <>
            {/* 2. System Instructions — role definition (default OPEN) */}
            {details?.system_prompt && (
              <Section
                title="System Instructions"
                icon={Bot}
                iconColor="text-violet-500"
                defaultOpen={true}
                badge={`${details.system_prompt.length} chars`}
              >
                <CodeBlock content={details.system_prompt} maxHeight="max-h-48" />
              </Section>
            )}

            {/* 3. Input Prompt — forwarded context or initial prompt */}
            {details?.user_prompt && (
              <Section
                title="Input Prompt"
                icon={User}
                iconColor="text-blue-500"
                badge={`${details.user_prompt.length} chars`}
              >
                <CodeBlock content={details.user_prompt} maxHeight="max-h-48" />
              </Section>
            )}

            {/* 4. Tool Calls — parsed from raw response (analyst steps) */}
            {parsedToolCalls.length > 0 && (
              <Section
                title="Tool Calls"
                icon={Wrench}
                iconColor="text-amber-500"
                badge={`${parsedToolCalls.length} calls`}
              >
                <ToolCallsPanel calls={parsedToolCalls} />
              </Section>
            )}

            {/* 5. Raw LLM Response — only when different from Step Output */}
            {showRawResponse && (
              <Section
                title="Raw LLM Response"
                icon={MessageSquare}
                iconColor="text-gray-500"
                badge={`${rawResponse.length} chars`}
              >
                <CodeBlock content={cleanRawResponse || rawResponse} maxHeight="max-h-48" />
              </Section>
            )}

            {/* 6. Step Output — the actual meaningful output */}
            {stepOutput && (
              <Section
                title="Step Output"
                icon={CheckCircle}
                iconColor="text-green-500"
                badge={`${stepOutput.length} chars`}
              >
                <CodeBlock content={stepOutput} maxHeight="max-h-80" />
              </Section>
            )}
          </>
        ) : (
          <EmptyState status={node.status} />
        )}
      </div>
    </div>
  );
}
