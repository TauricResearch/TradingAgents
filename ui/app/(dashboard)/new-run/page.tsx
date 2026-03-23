import RunConfigForm from '@/features/new-run/components/RunConfigForm'

export default function NewRunPage() {
  return (
    <div className="max-w-[660px] animate-fade-up">
      {/* Page header */}
      <div className="mb-8">
        <div className="apex-label mb-3" style={{ color: 'var(--accent)', opacity: 0.7 }}>
          Intelligence Engine
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-syne)',
            fontSize: '32px',
            fontWeight: 800,
            letterSpacing: '-0.04em',
            color: 'var(--text-high)',
            lineHeight: 1.1,
            marginBottom: '10px',
          }}
        >
          New Analysis
        </h1>
        <p
          className="text-sm leading-relaxed"
          style={{ color: 'var(--text-mid)', maxWidth: '480px', lineHeight: 1.7 }}
        >
          Configure a multi-agent analysis run. Your AI team will research market data,
          debate investment thesis, and deliver a structured decision.
        </p>
      </div>

      <RunConfigForm />
    </div>
  )
}
