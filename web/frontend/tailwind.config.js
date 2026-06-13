/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"DM Serif Display"', 'Georgia', 'serif'],
        sans: ['"Inter Tight"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      colors: {
        market: {
          DEFAULT: '#0a0e17',
          50: '#f0f4ff',
          100: '#d0d9f0',
          200: '#a1b3d9',
          300: '#738dbf',
          400: '#4a66a3',
          500: '#2a4382',
          600: '#1a2b5e',
          700: '#0f1d42',
          800: '#08102a',
          900: '#040817',
        },
        financial: {
          bg: '#0a0e17',
          surface: '#111827',
          card: '#1a2235',
          border: '#1e293b',
          'border-light': '#334155',
          text: '#f1f5f9',
          'text-secondary': '#94a3b8',
          'text-muted': '#64748b',
        },
        agent: {
          market: '#38bdf8',       // sky-400 - Market Analyst
          sentiment: '#a78bfa',    // violet-400 - Sentiment Analyst
          news: '#34d399',         // emerald-400 - News Analyst
          fundamentals: '#f472b6', // pink-400 - Fundamentals Analyst
          research: '#fb923c',     // orange-400 - Research
          trader: '#fbbf24',       // amber-400 - Trader
          risk: '#ef4444',         // red-500 - Risk
        },
        signal: {
          buy: '#10b981',
          sell: '#ef4444',
          hold: '#f59e0b',
        },
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'noise': "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E\")",
      },
      animation: {
        'pulse-glow': 'pulseGlow 2s ease-in-out infinite',
        'slide-up': 'slideUp 0.3s ease-out',
        'fade-in': 'fadeIn 0.3s ease-out',
        'data-flow': 'dataFlow 2s linear infinite',
        'gradient-shift': 'gradientShift 6s ease infinite',
        'breathing': 'breathing 3s ease-in-out infinite',
      },
      keyframes: {
        pulseGlow: {
          '0%, 100%': { boxShadow: '0 0 8px rgba(56, 189, 248, 0.3)' },
          '50%': { boxShadow: '0 0 20px rgba(56, 189, 248, 0.6)' },
        },
        slideUp: {
          '0%': { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        dataFlow: {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' },
        },
        gradientShift: {
          '0%, 100%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
        },
        breathing: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
      },
    },
  },
  plugins: [],
};
