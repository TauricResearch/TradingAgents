type Props = { content: string; speakerA: string; speakerB: string }

export default function DebateView({ content, speakerA, speakerB }: Props) {
  if (!content) {
    return <p className="text-[#8c909f] text-sm">Waiting for debate to complete…</p>
  }
  const turns = content.split(/\n{2,}/).filter(Boolean)
  return (
    <div className="space-y-3">
      {turns.map((turn, i) => {
        const isA = i % 2 === 0
        return (
          <div
            key={i}
            className={`rounded-lg p-4 ${isA ? 'bg-[#171f33]' : 'bg-[#131b2e]'}`}
          >
            <div
              className="text-[11px] font-semibold mb-2 uppercase tracking-wider"
              style={{
                color: isA ? '#adc6ff' : '#c2c6d6',
                fontFamily: 'var(--font-manrope)',
              }}
            >
              {isA ? speakerA : speakerB}
            </div>
            <p className="text-sm text-[#c2c6d6] leading-relaxed">{turn}</p>
          </div>
        )
      })}
    </div>
  )
}
