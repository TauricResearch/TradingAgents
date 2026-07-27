/**
 * Sanitized markdown renderer with two typographic modes.
 *
 * - "prose": parses markdown via react-markdown + remark-gfm, sanitized
 *   through rehype-sanitize defaultSchema. For LLM-authored reports.
 * - "data": byte-faithful preformatted monospace, no markdown parsing.
 *   For machine payloads (JSON, prompts, raw vendor values).
 *
 * Safety: sanitization happens in the HAST pipeline, not via pre-escaping
 * the source string, so markdown stays parseable while embedded markup
 * stays inert. Anchor hrefs are restricted to http/https in the component
 * override without widening the sanitize schema.
 */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

export interface SafeMarkdownProps {
  content: string;
  mode?: "prose" | "data";
}

function Anchor(props: React.AnchorHTMLAttributes<HTMLAnchorElement>): JSX.Element {
  const { href, children, ...rest } = props;
  if (!href || !/^https?:\/\//i.test(href)) {
    return <>{children}</>;
  }
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      {...rest}
    >
      {children}
    </a>
  );
}

export function SafeMarkdown({ content, mode = "prose" }: SafeMarkdownProps): JSX.Element {
  if (mode === "data") {
    return <pre className="datablock">{content}</pre>;
  }

  return (
    <div className="prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, defaultSchema]]}
        components={{
          a: Anchor,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
