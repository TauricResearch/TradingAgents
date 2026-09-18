import React from 'react';
import { X, Keyboard, Command } from 'lucide-react';

interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ShortcutsModal: React.FC<ShortcutsModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  const shortcuts = [
    { key: 'N', desc: 'Launch New Multi-Agent Analysis' },
    { key: '1', desc: 'Navigate to Live Arena (Terminal)' },
    { key: '2', desc: 'Navigate to Report Center' },
    { key: '3', desc: 'Navigate to Memory Log & Reflections' },
    { key: 'S', desc: 'Open Terminal Settings & API Keys' },
    { key: '/', desc: 'Focus Analysis Runs Search' },
    { key: '?', desc: 'Toggle Keyboard Shortcuts Sheet' },
    { key: 'Esc', desc: 'Close any modal or off-canvas drawer' },
  ];

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-dark-950/80 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-md bg-dark-900 border border-dark-700/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-5 py-4 border-b border-dark-700/80 flex items-center justify-between bg-dark-850/60">
          <div className="flex items-center space-x-2.5">
            <div className="w-8 h-8 rounded-lg bg-dark-800 border border-dark-700 flex items-center justify-center text-brand-cyan">
              <Keyboard className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold font-mono text-slate-100">Keyboard Shortcuts</h3>
              <p className="text-[11px] text-slate-400">Institutional Power-User Navigation</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-2.5">
          {shortcuts.map((sc) => (
            <div
              key={sc.key}
              className="flex items-center justify-between py-1.5 px-2.5 rounded-lg hover:bg-dark-850/50 transition-colors"
            >
              <span className="text-xs text-slate-300">{sc.desc}</span>
              <kbd className="px-2.5 py-1 rounded bg-dark-800 border border-dark-600 font-mono text-xs font-bold text-brand-cyan shadow-sm min-w-[28px] text-center">
                {sc.key}
              </kbd>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-dark-700/60 bg-dark-950/60 flex items-center justify-between text-[11px] text-slate-500 font-mono">
          <span className="flex items-center space-x-1">
            <Command className="w-3.5 h-3.5" />
            <span>TradingAgents Pro Terminal</span>
          </span>
          <span>Press ESC to close</span>
        </div>
      </div>
    </div>
  );
};
