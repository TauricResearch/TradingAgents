import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const plugins = [remarkGfm]

/** Report text from the agents: Markdown with GFM tables. */
export function Markdown({ text, className = '' }: { text: string; className?: string }) {
  const body = text.trim()
  if (!body) return <div className="text-muted">（无内容）</div>
  return (
    <div className={`md ${className}`}>
      <ReactMarkdown remarkPlugins={plugins}>{body}</ReactMarkdown>
    </div>
  )
}
