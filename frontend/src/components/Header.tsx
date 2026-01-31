import { Link, useLocation } from 'react-router-dom';
import { TrendingUp, BarChart3, History, Menu, X, Sparkles, Settings } from 'lucide-react';
import { useState } from 'react';
import ThemeToggle from './ThemeToggle';
import { useSettings } from '../contexts/SettingsContext';

export default function Header() {
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { openSettings } = useSettings();

  const navItems = [
    { path: '/', label: 'Dashboard', icon: BarChart3 },
    { path: '/history', label: 'History', icon: History },
    { path: '/about', label: 'How It Works', icon: Sparkles },
  ];

  const isActive = (path: string) => location.pathname === path;

  return (
    <header className="bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700 sticky top-0 z-50 transition-colors">
      <div className="max-w-7xl mx-auto px-3 sm:px-4 lg:px-6">
        <div className="flex justify-between items-center h-12">
          {/* Logo */}
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-nifty-500 to-nifty-700 rounded-lg flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-white" />
            </div>
            <span className="font-display font-bold gradient-text text-sm">Nifty50 AI</span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-0.5" aria-label="Main navigation">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                aria-current={isActive(path) ? 'page' : undefined}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-nifty-500 ${
                  isActive(path)
                    ? 'bg-nifty-50 dark:bg-nifty-900/30 text-nifty-700 dark:text-nifty-400'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-800 hover:text-gray-900 dark:hover:text-gray-100'
                }`}
              >
                <Icon className="w-3.5 h-3.5" aria-hidden="true" />
                {label}
              </Link>
            ))}
          </nav>

          {/* Settings, Theme Toggle & Mobile Menu */}
          <div className="flex items-center gap-2">
            {/* Settings Button */}
            <button
              onClick={openSettings}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors text-gray-600 dark:text-gray-300"
              aria-label="Open settings"
              title="Settings"
            >
              <Settings className="w-4 h-4" />
            </button>
            <div className="hidden md:block">
              <ThemeToggle />
            </div>
            <div className="md:hidden">
              <ThemeToggle compact />
            </div>
            <button
              className="md:hidden p-1.5 rounded-md hover:bg-gray-100 dark:hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-nifty-500 transition-colors text-gray-600 dark:text-gray-300"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label={mobileMenuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={mobileMenuOpen}
              aria-controls="mobile-menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" aria-hidden="true" /> : <Menu className="w-5 h-5" aria-hidden="true" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <nav id="mobile-menu" className="md:hidden py-2 border-t border-gray-100 dark:border-slate-700 animate-in slide-in-from-top-2 duration-200" aria-label="Mobile navigation">
            {navItems.map(({ path, label, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                onClick={() => setMobileMenuOpen(false)}
                aria-current={isActive(path) ? 'page' : undefined}
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  isActive(path)
                    ? 'bg-nifty-50 dark:bg-nifty-900/30 text-nifty-700 dark:text-nifty-400'
                    : 'text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-slate-800'
                }`}
              >
                <Icon className="w-4 h-4" aria-hidden="true" />
                {label}
              </Link>
            ))}
          </nav>
        )}
      </div>
    </header>
  );
}
