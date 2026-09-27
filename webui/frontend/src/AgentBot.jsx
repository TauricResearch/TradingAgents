/** Cute station robot — SVG inspired by the round cyan-eyed bot. */
export default function AgentBot({
  accent = '#2ee6d6',
  state = 'idle',
  speaking = false,
  size = 52,
  title,
}) {
  const id = accent.replace('#', '')
  return (
    <svg
      className={`bot bot-${state}${speaking ? ' speaking' : ''}`}
      width={size}
      height={Math.round(size * 1.22)}
      viewBox="0 0 80 98"
      aria-hidden={!title}
      role={title ? 'img' : 'presentation'}
    >
      {title && <title>{title}</title>}
      <defs>
        <radialGradient id={`body-${id}`} cx="38%" cy="28%" r="72%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="55%" stopColor="#e8edf4" />
          <stop offset="100%" stopColor="#b7c0ce" />
        </radialGradient>
        <radialGradient id={`head-${id}`} cx="40%" cy="30%" r="70%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="70%" stopColor="#eef2f7" />
          <stop offset="100%" stopColor="#c5ceda" />
        </radialGradient>
        <radialGradient id={`eye-${id}`} cx="40%" cy="40%" r="60%">
          <stop offset="0%" stopColor="#ecfffb" />
          <stop offset="45%" stopColor={accent} />
          <stop offset="100%" stopColor="#0b6b63" />
        </radialGradient>
        <filter id={`glow-${id}`} x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="1.6" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <ellipse className="bot-shadow" cx="40" cy="92" rx="18" ry="4.2" fill="#000" />

      {speaking && (
        <g className="bot-bubbles">
          <rect x="58" y="10" width="16" height="11" rx="5" fill="#f4f7fb" />
          <rect x="66" y="24" width="10" height="7" rx="3.5" fill="#f4f7fb" />
        </g>
      )}

      <g className="bot-figure">
        <line className="antenna" x1="28" y1="18" x2="22" y2="4" stroke="#d7dde6" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="21" cy="3" r="2.4" fill={accent} />
        <line className="antenna" x1="52" y1="18" x2="58" y2="4" stroke="#d7dde6" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="59" cy="3" r="2.4" fill={accent} />

        <g className="arm arm-l">
          <path d="M18 48 C8 52, 8 62, 16 66" fill="none" stroke="#d5dce6" strokeWidth="5.5" strokeLinecap="round" />
        </g>
        <g className="arm arm-r">
          <path d="M62 48 C72 52, 72 62, 64 66" fill="none" stroke="#d5dce6" strokeWidth="5.5" strokeLinecap="round" />
        </g>

        <ellipse cx="40" cy="62" rx="22" ry="20" fill={`url(#body-${id})`} />
        <ellipse cx="40" cy="54" rx="16" ry="8" fill="#ffffff" opacity="0.35" />

        <ellipse cx="40" cy="30" rx="20" ry="18" fill={`url(#head-${id})`} />

        <g className="eyes" filter={`url(#glow-${id})`}>
          <ellipse className="eye" cx="32" cy="30" rx="5.2" ry="6.2" fill={`url(#eye-${id})`} />
          <ellipse className="eye" cx="48" cy="30" rx="5.2" ry="6.2" fill={`url(#eye-${id})`} />
          <ellipse cx="30.6" cy="28" rx="1.5" ry="2" fill="#fff" opacity="0.85" />
          <ellipse cx="46.6" cy="28" rx="1.5" ry="2" fill="#fff" opacity="0.85" />
        </g>

        <g className="leg leg-l">
          <rect x="29" y="78" width="7" height="11" rx="3.4" fill="#d7dee8" />
        </g>
        <g className="leg leg-r">
          <rect x="44" y="78" width="7" height="11" rx="3.4" fill="#d7dee8" />
        </g>
      </g>
    </svg>
  )
}
