import { TrendingUp, Github, Twitter } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer className="mt-auto border-t border-gray-200/50 dark:border-slate-700/30 bg-white/50 dark:bg-slate-900/50 transition-colors" style={{ backdropFilter: 'blur(8px)' }}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          {/* Brand */}
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #0ea5e9, #0369a1)' }}>
              <TrendingUp className="w-3.5 h-3.5 text-white" />
            </div>
            <span className="font-display font-bold text-sm gradient-text">Nifty50 AI</span>
          </div>

          {/* Links */}
          <div className="flex items-center gap-5 text-xs text-gray-500 dark:text-gray-400">
            <Link to="/" className="hover:text-gray-900 dark:hover:text-gray-200 transition-colors">Dashboard</Link>
            <Link to="/history" className="hover:text-gray-900 dark:hover:text-gray-200 transition-colors">History</Link>
            <Link to="/about" className="hover:text-gray-900 dark:hover:text-gray-200 transition-colors">How It Works</Link>
            <span className="text-gray-200 dark:text-gray-700">|</span>
            <a href="#disclaimer" title="AI-generated recommendations for educational purposes only. Not financial advice." className="hover:text-gray-900 dark:hover:text-gray-200 transition-colors">Disclaimer</a>
            <a href="#privacy" title="We don't collect any personal data. All analysis runs locally." className="hover:text-gray-900 dark:hover:text-gray-200 transition-colors">Privacy</a>
          </div>

          {/* Social & Copyright */}
          <div className="flex items-center gap-3">
            <a href="https://github.com/hemangjoshi37a/TradingAgents" target="_blank" rel="noopener noreferrer" className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
              <Github className="w-4 h-4" />
            </a>
            <a href="https://x.com/heaborla" target="_blank" rel="noopener noreferrer" className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
              <Twitter className="w-4 h-4" />
            </a>
            <span className="text-xs text-gray-400 dark:text-gray-500">&copy; {new Date().getFullYear()}</span>
          </div>
        </div>

        <p className="text-[11px] text-gray-400 dark:text-gray-500 text-center mt-4 leading-relaxed">
          AI-generated recommendations for educational purposes only. Not financial advice. Do your own research.
        </p>
      </div>
    </footer>
  );
}
