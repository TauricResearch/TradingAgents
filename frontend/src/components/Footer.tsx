import { TrendingUp, Github, Twitter } from 'lucide-react';
import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer className="bg-white dark:bg-slate-900 border-t border-gray-200 dark:border-slate-700 mt-auto transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        {/* Compact single-row layout */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
          {/* Brand */}
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-gradient-to-br from-nifty-500 to-nifty-700 rounded-lg flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <span className="font-display font-bold text-sm gradient-text">Nifty50 AI</span>
          </div>

          {/* Links */}
          <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
            <Link to="/" className="hover:text-nifty-600 dark:hover:text-nifty-400">Dashboard</Link>
            <Link to="/history" className="hover:text-nifty-600 dark:hover:text-nifty-400">History</Link>
            <Link to="/about" className="hover:text-nifty-600 dark:hover:text-nifty-400">How It Works</Link>
            <span className="text-gray-300 dark:text-gray-600">|</span>
            <a href="#" className="hover:text-nifty-600 dark:hover:text-nifty-400">Disclaimer</a>
            <a href="#" className="hover:text-nifty-600 dark:hover:text-nifty-400">Privacy</a>
          </div>

          {/* Social & Copyright */}
          <div className="flex items-center gap-3">
            <a href="#" className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
              <Github className="w-4 h-4" />
            </a>
            <a href="#" className="text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300">
              <Twitter className="w-4 h-4" />
            </a>
            <span className="text-xs text-gray-400 dark:text-gray-500">© {new Date().getFullYear()}</span>
          </div>
        </div>

        {/* Compact Disclaimer */}
        <p className="text-[10px] text-gray-400 dark:text-gray-500 text-center mt-3 leading-relaxed">
          AI-generated recommendations for educational purposes only. Not financial advice. Do your own research.
        </p>
      </div>
    </footer>
  );
}
