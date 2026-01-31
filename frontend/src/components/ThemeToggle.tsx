import { Sun, Moon, Monitor } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

interface ThemeToggleProps {
  compact?: boolean;
}

export default function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();

  const themes = [
    { value: 'light' as const, icon: Sun, label: 'Light' },
    { value: 'dark' as const, icon: Moon, label: 'Dark' },
    { value: 'system' as const, icon: Monitor, label: 'System' },
  ];

  if (compact) {
    // Simple cycling button for mobile
    const currentIndex = themes.findIndex(t => t.value === theme);
    const nextTheme = themes[(currentIndex + 1) % themes.length];
    const CurrentIcon = themes[currentIndex].icon;

    return (
      <button
        onClick={() => setTheme(nextTheme.value)}
        className="p-2 rounded-lg text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
        aria-label={`Current theme: ${theme}. Click to switch to ${nextTheme.label}`}
      >
        <CurrentIcon className="w-4 h-4" />
      </button>
    );
  }

  return (
    <div
      className="flex items-center gap-0.5 p-0.5 bg-gray-100 dark:bg-slate-700 rounded-lg"
      role="radiogroup"
      aria-label="Theme selection"
    >
      {themes.map(({ value, icon: Icon, label }) => {
        const isActive = theme === value;
        return (
          <button
            key={value}
            onClick={() => setTheme(value)}
            role="radio"
            aria-checked={isActive}
            aria-label={label}
            className={`p-1.5 rounded-md transition-all ${
              isActive
                ? 'bg-white dark:bg-slate-600 text-nifty-600 dark:text-nifty-400 shadow-sm'
                : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
          </button>
        );
      })}
    </div>
  );
}
