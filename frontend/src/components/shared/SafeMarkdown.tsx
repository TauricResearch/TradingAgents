/**
 * G3 - Sanitized markdown renderer (minimal).
 *
 * Server-side redaction (RunMeta.redaction_manifest) already strips sensitive
 * content from artifacts; this component is a defense-in-depth layer ensuring
 * any residual HTML in artifact text is rendered as inert text, never
 * executed as live markup.
 *
 * react-markdown + remark-gfm + rehype-sanitize integration is DEFERRED to H2
 * packaging: those deps are NOT in frontend/package.json today and the task
 * explicitly forbids modifying package.json. For G3 we escape &, <, > to HTML
 * entities and render in a <pre> with whitespace preserved. Markdown syntax
 * (headings, bold, code) is NOT parsed - content is shown verbatim as
 * preformatted escaped text. This is acceptable because the content is already
 * redacted server-side.
 *
 * Safety: the escaped string is assigned via dangerouslySetInnerHTML ONLY
 * after &, <, > have been converted to entities, so no substring can ever be
 * interpreted as a live HTML tag by the browser.
 */

export interface SafeMarkdownProps {
  content: string;
}

function escapeHtml(input: string): string {
  return input
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

export function SafeMarkdown({ content }: SafeMarkdownProps): JSX.Element {
  const escaped = escapeHtml(content);
  return (
    <pre
      className="safe-markdown"
      style={{ whiteSpace: "pre-wrap" }}
      dangerouslySetInnerHTML={{ __html: escaped }}
    />
  );
}
