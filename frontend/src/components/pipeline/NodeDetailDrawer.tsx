import { useState } from 'react';
import { X, Clock, Timer, CheckCircle, AlertCircle, FileText, MessageSquare, ChevronDown, ChevronRight, Terminal, Bot, User, Wrench } from 'lucide-react';
import type { FlowchartNodeData, FullPipelineData, StepDetails } from '../../types/pipeline';

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

function getFallbackContent(node: FlowchartNodeData, data: FullPipelineData | null): string {
  if (node.agentReport?.report_content) return node.agentReport.report_content;
  if (node.debateContent) return node.debateContent;
  if (node.output_summary) return node.output_summary;
  if (!data) return '';

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

export function NodeDetailDrawer({ node, pipelineData, onClose }: NodeDetailDrawerProps) {
  const details: StepDetails | undefined = node.step_details;
  const fallbackContent = getFallbackContent(node, pipelineData);

  // Determine if we have structured data or just fallback
  const hasStructuredData = details && (details.system_prompt || details.user_prompt || details.response);

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

      {/* Content sections */}
      <div className="p-3 space-y-2">
        {hasStructuredData ? (
          <>
            {/* System Prompt */}
            {details.system_prompt && (
              <Section
                title="System Prompt"
                icon={Bot}
                iconColor="text-violet-500"
                badge={`${details.system_prompt.length} chars`}
              >
                <CodeBlock content={details.system_prompt} maxHeight="max-h-48" />
              </Section>
            )}

            {/* User Prompt / Input */}
            {details.user_prompt && (
              <Section
                title="User Prompt / Input"
                icon={User}
                iconColor="text-blue-500"
                badge={`${details.user_prompt.length} chars`}
              >
                <CodeBlock content={details.user_prompt} maxHeight="max-h-48" />
              </Section>
            )}

            {/* Tool Calls */}
            {details.tool_calls && details.tool_calls.length > 0 && (
              <Section
                title="Tool Calls"
                icon={Wrench}
                iconColor="text-amber-500"
                badge={`${details.tool_calls.length} calls`}
              >
                <div className="p-3 space-y-3">
                  {details.tool_calls.map((tc, i) => (
                    <div key={i} className="space-y-1">
                      <div className="flex items-start gap-2 text-xs">
                        <span className="font-mono font-semibold text-amber-600 dark:text-amber-400 whitespace-nowrap">
                          {tc.name}()
                        </span>
                        {tc.args && (
                          <span className="font-mono text-gray-500 dark:text-gray-400 truncate">
                            {tc.args}
                          </span>
                        )}
                      </div>
                      {tc.result_preview && (
                        <div className="ml-4 p-2 bg-slate-900 dark:bg-black/40 rounded text-[11px] font-mono text-green-300 dark:text-green-400 max-h-32 overflow-auto whitespace-pre-wrap">
                          {tc.result_preview}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* LLM Response */}
            {details.response && (
              <Section
                title="LLM Response"
                icon={MessageSquare}
                iconColor="text-green-500"
                defaultOpen={true}
                badge={`${details.response.length} chars`}
              >
                <CodeBlock content={details.response} maxHeight="max-h-80" />
              </Section>
            )}
          </>
        ) : fallbackContent ? (
          /* Fallback: show the old-style content */
          <>
            <Section
              title={node.agentType ? 'Agent Report' : node.debateRole === 'judge' ? 'Decision' : node.debateType ? 'Debate Argument' : 'Output'}
              icon={node.agentType ? FileText : node.debateType ? MessageSquare : FileText}
              iconColor="text-gray-500"
              defaultOpen={true}
              badge={`${fallbackContent.length} chars`}
            >
              <CodeBlock content={fallbackContent} maxHeight="max-h-80" />
            </Section>
          </>
        ) : node.status === 'pending' ? (
          <div className="text-center py-6 text-gray-400 dark:text-gray-500">
            <Clock className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">This step hasn't run yet</p>
            <p className="text-xs mt-1">Run an analysis to see results here</p>
          </div>
        ) : node.status === 'running' ? (
          <div className="text-center py-6 text-blue-500 dark:text-blue-400">
            <div className="w-8 h-8 mx-auto mb-2 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
            <p className="text-sm">Processing...</p>
          </div>
        ) : (
          <div className="text-center py-6 text-gray-400 dark:text-gray-500">
            <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">No output data available</p>
          </div>
        )}
      </div>
    </div>
  );
}
