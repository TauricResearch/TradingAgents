import { useId } from 'react'

/** A friendly companion with soft ceramic panels and a smiling display. */
export default function AgentBot({ accent = '#74dac5', state = 'idle', size = 52, title }) {
  const id = useId().replace(/:/g, '')
  return (
    <svg className={`bot bot-${state}`} width={size} height={size * 1.18}
      viewBox="0 0 100 118" aria-hidden={!title} role={title ? 'img' : 'presentation'}>
      {title && <title>{title}</title>}
      <defs>
        <linearGradient id={`${id}-shell`} x1="0" y1="0" x2="0.8" y2="1">
          <stop stopColor="#fff" /><stop offset="0.6" stopColor="#edf3f6" />
          <stop offset="1" stopColor="#bdcdd8" />
        </linearGradient>
        <linearGradient id={`${id}-screen`} x2="0" y2="1">
          <stop stopColor="#243e4c" /><stop offset="1" stopColor="#132630" />
        </linearGradient>
      </defs>
      <ellipse className="bot-shadow" cx="50" cy="110" rx="26" ry="4" fill="#091b22" opacity=".16" />
      <g className="bot-figure">
        <path d="M50 17V9" stroke="#b8cbd5" strokeWidth="4" strokeLinecap="round" />
        <circle cx="50" cy="7" r="4" fill={accent} />
        <g className="leg leg-l"><rect x="33" y="87" width="12" height="19" rx="6" fill="#c6d5de" />
          <rect x="29" y="99" width="18" height="8" rx="4" fill={`url(#${id}-shell)`} /></g>
        <g className="leg leg-r"><rect x="55" y="87" width="12" height="19" rx="6" fill="#c6d5de" />
          <rect x="53" y="99" width="18" height="8" rx="4" fill={`url(#${id}-shell)`} /></g>
        <g className="arm arm-l"><path d="M27 68Q15 69 17 84" fill="none" stroke="#dce7ed" strokeWidth="9" strokeLinecap="round" />
          <circle cx="17" cy="85" r="5" fill="#eef4f7" /></g>
        <g className="arm arm-r"><path d="M73 68Q85 69 83 84" fill="none" stroke="#dce7ed" strokeWidth="9" strokeLinecap="round" />
          <circle cx="83" cy="85" r="5" fill="#eef4f7" /></g>
        <rect x="27" y="59" width="46" height="37" rx="17" fill={`url(#${id}-shell)`} />
        <rect x="40" y="71" width="20" height="11" rx="5.5" fill={accent} opacity=".18" />
        <path d="M46 76h8" stroke={accent} strokeWidth="3" strokeLinecap="round" />
        <rect x="13" y="32" width="9" height="18" rx="4.5" fill="#bbcfd9" />
        <rect x="78" y="32" width="9" height="18" rx="4.5" fill="#bbcfd9" />
        <rect x="19" y="17" width="62" height="48" rx="21" fill={`url(#${id}-shell)`} />
        <rect x="26" y="26" width="48" height="30" rx="13" fill={`url(#${id}-screen)`} />
        <path d="M31 30Q47 26 65 30" stroke="#fff" strokeWidth="2" opacity=".09" fill="none" />
        <g className="eyes" fill={accent}>
          <rect className="eye" x="35" y="34" width="6" height="9" rx="3" />
          <rect className="eye" x="59" y="34" width="6" height="9" rx="3" />
        </g>
        <path d="M45 46Q50 51 55 46" fill="none" stroke={accent} strokeWidth="2" strokeLinecap="round" />
        <ellipse cx="33" cy="46" rx="3" ry="1.5" fill="#edb8c2" opacity=".55" />
        <ellipse cx="67" cy="46" rx="3" ry="1.5" fill="#edb8c2" opacity=".55" />
      </g>
    </svg>
  )
}
