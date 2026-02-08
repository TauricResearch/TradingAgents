import {
  TrendingUp, TrendingDown, Users, Newspaper, FileText,
  Scale, Target, Zap, Shield, ShieldCheck,
  Clock, Loader2, CheckCircle, AlertCircle, ChevronDown, ChevronUp, GitBranch
} from 'lucide-react';
import { useState } from 'react';
import type { FlowchartNodeData, PipelineStepStatus } from '../../types/pipeline';
import { STEP_INPUT_SOURCES } from '../../types/pipeline';

interface FlowchartNodeProps {
  node: FlowchartNodeData;
  isSelected: boolean;
  onClick: () => void;
}

const ICON_MAP: Record<string, React.ElementType> = {
  TrendingUp, TrendingDown, Users, Newspaper, FileText,
  Scale, Target, Zap, Shield, ShieldCheck,
};

const STATUS_CONFIG: Record<PipelineStepStatus, {
  bg: string; border: string; text: string; badge: string; badgeText: string;
  StatusIcon: React.ElementType; statusLabel: string;
}> = {
  pending: {
    bg: 'bg-slate-50 dark:bg-slate-800/60',
    border: 'border-slate-200 dark:border-slate-700',
    text: 'text-slate-400 dark:text-slate-500',
    badge: 'bg-slate-100 dark:bg-slate-700',
    badgeText: 'text-slate-500 dark:text-slate-400',
    StatusIcon: Clock,
    statusLabel: 'Pending',
  },
  running: {
    bg: 'bg-blue-50/80 dark:bg-blue-900/20',
    border: 'border-blue-300 dark:border-blue-600',
    text: 'text-blue-600 dark:text-blue-400',
    badge: 'bg-blue-100 dark:bg-blue-900/40',
    badgeText: 'text-blue-600 dark:text-blue-400',
    StatusIcon: Loader2,
    statusLabel: 'Running',
  },
  completed: {
    bg: 'bg-green-50/60 dark:bg-green-900/15',
    border: 'border-green-300 dark:border-green-700',
    text: 'text-green-600 dark:text-green-400',
    badge: 'bg-green-100 dark:bg-green-900/30',
    badgeText: 'text-green-600 dark:text-green-400',
    StatusIcon: CheckCircle,
    statusLabel: 'Completed',
  },
  error: {
    bg: 'bg-red-50/60 dark:bg-red-900/15',
    border: 'border-red-300 dark:border-red-700',
    text: 'text-red-600 dark:text-red-400',
    badge: 'bg-red-100 dark:bg-red-900/30',
    badgeText: 'text-red-600 dark:text-red-400',
    StatusIcon: AlertCircle,
    statusLabel: 'Error',
  },
};

const NODE_COLORS: Record<string, { iconBg: string; iconText: string }> = {
  blue:    { iconBg: 'bg-blue-100 dark:bg-blue-900/40',    iconText: 'text-blue-600 dark:text-blue-400' },
  pink:    { iconBg: 'bg-pink-100 dark:bg-pink-900/40',    iconText: 'text-pink-600 dark:text-pink-400' },
  purple:  { iconBg: 'bg-purple-100 dark:bg-purple-900/40',  iconText: 'text-purple-600 dark:text-purple-400' },
  emerald: { iconBg: 'bg-emerald-100 dark:bg-emerald-900/40', iconText: 'text-emerald-600 dark:text-emerald-400' },
  green:   { iconBg: 'bg-green-100 dark:bg-green-900/40',   iconText: 'text-green-600 dark:text-green-400' },
  red:     { iconBg: 'bg-red-100 dark:bg-red-900/40',     iconText: 'text-red-600 dark:text-red-400' },
  violet:  { iconBg: 'bg-violet-100 dark:bg-violet-900/40',  iconText: 'text-violet-600 dark:text-violet-400' },
  amber:   { iconBg: 'bg-amber-100 dark:bg-amber-900/40',   iconText: 'text-amber-600 dark:text-amber-400' },
  orange:  { iconBg: 'bg-orange-100 dark:bg-orange-900/40',  iconText: 'text-orange-600 dark:text-orange-400' },
  sky:     { iconBg: 'bg-sky-100 dark:bg-sky-900/40',     iconText: 'text-sky-600 dark:text-sky-400' },
  slate:   { iconBg: 'bg-slate-200 dark:bg-slate-700',     iconText: 'text-slate-600 dark:text-slate-400' },
  indigo:  { iconBg: 'bg-indigo-100 dark:bg-indigo-900/40',  iconText: 'text-indigo-600 dark:text-indigo-400' },
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const secs = ms / 1000;
  if (secs < 60) return `${secs.toFixed(1)}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = Math.floor(secs % 60);
  return `${mins}m ${remSecs}s`;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const day = d.getDate().toString().padStart(2, '0');
  const month = (d.getMonth() + 1).toString().padStart(2, '0');
  const year = d.getFullYear();
  const time = d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  return `${day}/${month}/${year} ${time}`;
}

export function FlowchartNode({ node, isSelected, onClick }: FlowchartNodeProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const status = STATUS_CONFIG[node.status];
  const colors = NODE_COLORS[node.color] || NODE_COLORS.blue;
  const Icon = ICON_MAP[node.icon] || Target;

  const hasPreview = !!(node.output_summary || node.agentReport?.report_content || node.debateContent);
  const previewText = node.output_summary || node.agentReport?.report_content || node.debateContent || '';
  const inputCount = (STEP_INPUT_SOURCES[node.id] || []).length;

  return (
    <div className="w-full">
      <div
        role="button"
        tabIndex={0}
        onClick={onClick}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
        className={`
          w-full flex items-center gap-2 sm:gap-3 p-2.5 sm:p-3 rounded-xl border-2 transition-all text-left cursor-pointer
          ${status.bg} ${status.border}
          ${isSelected ? 'ring-2 ring-nifty-500 ring-offset-1 dark:ring-offset-slate-900 shadow-lg' : 'hover:shadow-md'}
          ${node.status === 'running' ? 'animate-pulse' : ''}
        `}
      >
        {/* Icon */}
        <div className={`p-1.5 sm:p-2 rounded-lg flex-shrink-0 ${colors.iconBg}`}>
          <Icon className={`w-4 h-4 sm:w-5 sm:h-5 ${colors.iconText}`} />
        </div>

        {/* Name & Step # */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-medium text-xs sm:text-sm text-gray-800 dark:text-gray-200 truncate">
              {node.label}
            </span>
            <span className="text-[9px] sm:text-[10px] text-gray-400 dark:text-gray-500 flex-shrink-0">
              #{node.number}
            </span>
          </div>
          {/* Timestamp */}
          {node.completed_at && (
            <div className="text-[9px] sm:text-[10px] text-gray-400 dark:text-gray-500 mt-0.5">
              {formatTimestamp(node.completed_at)}
            </div>
          )}
          {node.status === 'running' && node.started_at && (
            <div className="text-[9px] sm:text-[10px] text-blue-500 dark:text-blue-400 mt-0.5">
              Started {formatTimestamp(node.started_at)}
            </div>
          )}
        </div>

        {/* Status + Duration */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {inputCount > 0 && node.status === 'completed' && (
            <span className="hidden sm:inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 dark:bg-blue-900/20 text-blue-500 dark:text-blue-400 border border-blue-200 dark:border-blue-800/50">
              <GitBranch className="w-2.5 h-2.5" />
              {inputCount}
            </span>
          )}
          {node.duration_ms != null && node.status === 'completed' && (
            <span className="text-[10px] sm:text-xs font-mono font-semibold text-gray-500 dark:text-gray-400">
              {formatDuration(node.duration_ms)}
            </span>
          )}
          <div className={`flex items-center gap-1 px-1.5 sm:px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${status.badge} ${status.badgeText}`}>
            <status.StatusIcon className={`w-3 h-3 ${node.status === 'running' ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{status.statusLabel}</span>
          </div>
        </div>

        {/* Expand toggle */}
        {hasPreview && node.status === 'completed' && (
          <button
            onClick={(e) => { e.stopPropagation(); setIsExpanded(!isExpanded); }}
            className="p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex-shrink-0"
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        )}
      </div>

      {/* Inline preview */}
      {isExpanded && hasPreview && (
        <div className="mt-1 mx-2 p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-xs text-gray-600 dark:text-gray-400 font-mono leading-relaxed max-h-32 overflow-y-auto">
          {previewText.slice(0, 500)}{previewText.length > 500 ? '...' : ''}
        </div>
      )}
    </div>
  );
}
