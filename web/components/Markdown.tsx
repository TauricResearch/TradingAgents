"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Wraps react-markdown with GFM (tables, strikethrough) and a tight
// prose style. We don't escape `$` — react-markdown doesn't try to
// render math by default, so the Streamlit gotcha doesn't apply here.

export function Markdown({ children }: { children: string | null | undefined }) {
  if (!children) return <span className="text-muted text-sm">_(no content)_</span>;
  return (
    <div className="prose-tight">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
      <style jsx>{`
        .prose-tight :global(h1) { font-size: 1.25rem; font-weight: 700; margin: 1rem 0 0.5rem; }
        .prose-tight :global(h2) { font-size: 1.125rem; font-weight: 700; margin: 0.875rem 0 0.5rem; }
        .prose-tight :global(h3) { font-size: 1rem; font-weight: 600; margin: 0.75rem 0 0.375rem; }
        .prose-tight :global(p)  { margin: 0.5rem 0; line-height: 1.55; }
        .prose-tight :global(ul), .prose-tight :global(ol) { margin: 0.5rem 0 0.5rem 1.25rem; }
        .prose-tight :global(li) { margin: 0.125rem 0; }
        .prose-tight :global(code) { background: rgba(127,127,127,0.18); padding: 0 0.25rem; border-radius: 3px; font-size: 0.875em; }
        .prose-tight :global(pre) { background: rgba(127,127,127,0.12); padding: 0.75rem; border-radius: 6px; overflow-x: auto; font-size: 0.85em; }
        .prose-tight :global(blockquote) { border-left: 3px solid var(--accent); padding-left: 0.75rem; color: var(--muted); margin: 0.5rem 0; }
        .prose-tight :global(table) { border-collapse: collapse; }
        .prose-tight :global(th), .prose-tight :global(td) { border: 1px solid var(--border); padding: 0.25rem 0.5rem; }
        .prose-tight :global(strong) { font-weight: 600; }
      `}</style>
    </div>
  );
}
