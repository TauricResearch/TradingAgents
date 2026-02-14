import { X, Info } from 'lucide-react';
import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';

interface InfoModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  icon?: ReactNode;
}

export default function InfoModal({ isOpen, onClose, title, children, icon }: InfoModalProps) {
  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 overflow-y-auto">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative min-h-screen flex items-center justify-center p-4">
        <div className="relative w-full max-w-md bg-white dark:bg-slate-800 rounded-2xl shadow-xl">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-100 dark:border-slate-700">
            <div className="flex items-center gap-2">
              {icon || <Info className="w-5 h-5 text-nifty-600 dark:text-nifty-400" />}
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">{title}</h3>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Content */}
          <div className="p-4 max-h-[70vh] overflow-y-auto">
            {children}
          </div>

          {/* Footer */}
          <div className="p-4 border-t border-gray-100 dark:border-slate-700 flex justify-end">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-nifty-600 text-white rounded-lg text-sm font-medium hover:bg-nifty-700 transition-colors"
            >
              Got it
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}

// Reusable info button component
interface InfoButtonProps {
  onClick: () => void;
  className?: string;
  size?: 'sm' | 'md';
}

export function InfoButton({ onClick, className = '', size = 'sm' }: InfoButtonProps) {
  const sizeClasses = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4';

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      className={`inline-flex items-center justify-center p-0.5 rounded-full text-gray-400 hover:text-nifty-600 dark:hover:text-nifty-400 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors ${className}`}
      title="Learn more"
    >
      <Info className={sizeClasses} />
    </button>
  );
}
