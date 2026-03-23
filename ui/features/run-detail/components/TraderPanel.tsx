type Props = { content: string }

export default function TraderPanel({ content }: Props) {
  if (!content) {
    return <p className="text-[#8c909f] text-sm">Waiting for trader analysis…</p>
  }
  return (
    <div className="rounded-lg bg-[#171f33] p-6">
      <h3
        className="text-sm font-semibold text-[#adc6ff] mb-4"
        style={{ fontFamily: 'var(--font-manrope)' }}
      >
        Investment Plan
      </h3>
      <p className="text-sm text-[#c2c6d6] whitespace-pre-wrap leading-relaxed">{content}</p>
    </div>
  )
}
