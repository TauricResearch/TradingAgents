import type { ReactNode } from "react";

interface SafeMarkdownProps {
  content: string;
  className?: string;
}

type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; lines: string[] }
  | { kind: "quote"; lines: string[] }
  | { kind: "unordered"; items: string[] }
  | { kind: "ordered"; items: string[] }
  | { kind: "code"; language: string; content: string }
  | { kind: "table"; headers: string[]; rows: string[][] }
  | { kind: "rule" };

const unordered = /^\s*[-*+]\s+(.+)$/;
const ordered = /^\s*\d+[.)]\s+(.+)$/;
const heading = /^(#{1,6})\s+(.+)$/;
const fence = /^```([^`]*)$/;
const quote = /^>\s?(.*)$/;
const tableSeparator = /^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$/;
const rule = /^\s*(?:---+|\*\*\*+|___+)\s*$/;

function isBlockStart(line: string, next?: string): boolean {
  return (
    fence.test(line) ||
    heading.test(line) ||
    quote.test(line) ||
    unordered.test(line) ||
    ordered.test(line) ||
    rule.test(line) ||
    (line.includes("|") && next !== undefined && tableSeparator.test(next))
  );
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function parseBlocks(content: string): Block[] {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fenceMatch = fence.exec(line);
    if (fenceMatch) {
      const language = fenceMatch[1].trim();
      index += 1;
      const codeLines: string[] = [];
      while (index < lines.length && !fence.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ kind: "code", language, content: codeLines.join("\n") });
      continue;
    }

    const headingMatch = heading.exec(line);
    if (headingMatch) {
      blocks.push({
        kind: "heading",
        level: headingMatch[1].length,
        text: headingMatch[2],
      });
      index += 1;
      continue;
    }

    if (rule.test(line)) {
      blocks.push({ kind: "rule" });
      index += 1;
      continue;
    }

    if (line.includes("|") && tableSeparator.test(lines[index + 1] ?? "")) {
      const headers = splitTableRow(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      blocks.push({ kind: "table", headers, rows });
      continue;
    }

    const quoteMatch = quote.exec(line);
    if (quoteMatch) {
      const quoteLines: string[] = [];
      while (index < lines.length) {
        const match = quote.exec(lines[index]);
        if (!match) break;
        quoteLines.push(match[1]);
        index += 1;
      }
      blocks.push({ kind: "quote", lines: quoteLines });
      continue;
    }

    const unorderedMatch = unordered.exec(line);
    const orderedMatch = ordered.exec(line);
    if (unorderedMatch || orderedMatch) {
      const matcher = unorderedMatch ? unordered : ordered;
      const items: string[] = [];
      while (index < lines.length) {
        const match = matcher.exec(lines[index]);
        if (!match) break;
        items.push(match[1]);
        index += 1;
      }
      blocks.push({ kind: unorderedMatch ? "unordered" : "ordered", items });
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !isBlockStart(lines[index], lines[index + 1])
    ) {
      paragraph.push(lines[index]);
      index += 1;
    }
    // A lone non-paragraph marker is still safe readable text.
    if (paragraph.length === 0) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push({ kind: "paragraph", lines: paragraph });
  }
  return blocks;
}

function safeHref(value: string): string | null {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.href
      : null;
  } catch {
    return null;
  }
}

function inline(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let remaining = text;
  let index = 0;
  const pushText = (value: string): void => {
    if (value) nodes.push(value);
  };

  while (remaining) {
    const match = /`([^`]+)`|\*\*([^*]+)\*\*|__([^_]+)__|\[([^\]]+)\]\(([^\s)]+)\)|\*([^*]+)\*|_([^_]+)_/.exec(
      remaining,
    );
    if (!match || match.index === undefined) {
      pushText(remaining);
      break;
    }
    pushText(remaining.slice(0, match.index));
    const key = `${keyPrefix}-${index}`;
    index += 1;
    if (match[1] !== undefined) {
      nodes.push(<code key={key}>{match[1]}</code>);
    } else if (match[2] !== undefined || match[3] !== undefined) {
      nodes.push(<strong key={key}>{match[2] ?? match[3]}</strong>);
    } else if (match[4] !== undefined && match[5] !== undefined) {
      const href = safeHref(match[5]);
      nodes.push(
        href ? (
          <a key={key} href={href} target="_blank" rel="noopener noreferrer">
            {match[4]}
          </a>
        ) : (
          <span key={key}>{match[0]}</span>
        ),
      );
    } else {
      nodes.push(<em key={key}>{match[6] ?? match[7]}</em>);
    }
    remaining = remaining.slice(match.index + match[0].length);
  }
  return nodes;
}

function multiline(lines: string[], keyPrefix: string): ReactNode[] {
  return lines.flatMap((line, index) =>
    index === 0
      ? inline(line, `${keyPrefix}-${index}`)
      : [<br key={`${keyPrefix}-break-${index}`} />, ...inline(line, `${keyPrefix}-${index}`)],
  );
}

/**
 * A deliberately small Markdown renderer. It never parses or injects raw
 * HTML; unsupported syntax remains escaped text. This makes reports readable
 * without expanding the browser trust boundary or adding a package dependency.
 */
export function SafeMarkdown({ content, className }: SafeMarkdownProps): JSX.Element {
  return (
    <div className={["markdown-document", className].filter(Boolean).join(" ")}>
      {parseBlocks(content).map((block, index) => {
        const key = `block-${index}`;
        switch (block.kind) {
          case "heading": {
            const Tag = `h${block.level}` as keyof JSX.IntrinsicElements;
            return <Tag key={key}>{inline(block.text, key)}</Tag>;
          }
          case "paragraph":
            return <p key={key}>{multiline(block.lines, key)}</p>;
          case "quote":
            return <blockquote key={key}>{multiline(block.lines, key)}</blockquote>;
          case "unordered":
            return (
              <ul key={key}>
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{inline(item, `${key}-${itemIndex}`)}</li>
                ))}
              </ul>
            );
          case "ordered":
            return (
              <ol key={key}>
                {block.items.map((item, itemIndex) => (
                  <li key={`${key}-${itemIndex}`}>{inline(item, `${key}-${itemIndex}`)}</li>
                ))}
              </ol>
            );
          case "code":
            return (
              <pre key={key}>
                <code data-language={block.language || undefined}>{block.content}</code>
              </pre>
            );
          case "table":
            return (
              <div key={key} className="markdown-table-wrap">
                <table>
                  <thead>
                    <tr>
                      {block.headers.map((cell, cellIndex) => (
                        <th key={`${key}-head-${cellIndex}`}>
                          {inline(cell, `${key}-head-${cellIndex}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, rowIndex) => (
                      <tr key={`${key}-row-${rowIndex}`}>
                        {block.headers.map((_, cellIndex) => (
                          <td key={`${key}-cell-${rowIndex}-${cellIndex}`}>
                            {inline(row[cellIndex] ?? "", `${key}-cell-${rowIndex}-${cellIndex}`)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "rule":
            return <hr key={key} />;
        }
      })}
    </div>
  );
}
