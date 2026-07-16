/** Minimal renderer for LLM prose: `**bold**` becomes <strong>, everything
 * else stays literal text (no markdown engine, no HTML injection surface).
 * Trader review: raw asterisks were rendering unformatted in the flagship
 * invalidation card — polish wounds trust faster than missing features. */
export function Emphasis({ text }: { text: string }) {
  const parts = text.split(/\*\*([^*]+)\*\*/g);
  if (parts.length === 1) return <>{text}</>;
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <strong key={i} className="font-semibold text-fg">
            {part}
          </strong>
        ) : (
          part
        ),
      )}
    </>
  );
}
