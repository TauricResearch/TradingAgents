import RunConfigForm from '@/features/new-run/components/RunConfigForm'

export default function NewRunPage() {
  return (
    <div className="max-w-[640px] animate-fade-up">
      {/* Page header */}
      <div className="mb-8">
        <div
          className="apex-label mb-3"
        >
          Intelligence Engine
        </div>
        <h1
          className="text-[28px] font-bold tracking-tight mb-2"
          style={{
            color: 'var(--text-high)',
            fontFamily: 'var(--font-manrope)',
            letterSpacing: '-0.03em',
          }}
        >
          New Analysis
        </h1>
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--text-mid)' }}
        >
          Configure a multi-agent analysis run. Your AI team will research market data,
          debate investment thesis, and deliver a structured decision.
        </p>
      </div>

      <RunConfigForm />
    </div>
  )
}
