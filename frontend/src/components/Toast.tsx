import React, { useState, useEffect } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

type ToastListener = (toasts: ToastItem[]) => void;

class ToastManager {
  private toasts: ToastItem[] = [];
  private listeners: Set<ToastListener> = new Set();

  subscribe(listener: ToastListener) {
    this.listeners.add(listener);
    listener([...this.toasts]);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private notify() {
    this.listeners.forEach((listener) => listener([...this.toasts]));
  }

  show(type: ToastType, message: string, duration: number = 4000) {
    const id = Math.random().toString(36).substring(2, 9);
    const toast: ToastItem = { id, type, message, duration };
    this.toasts = [...this.toasts, toast];
    this.notify();

    if (duration > 0) {
      setTimeout(() => {
        this.remove(id);
      }, duration);
    }
  }

  remove(id: string) {
    this.toasts = this.toasts.filter((t) => t.id !== id);
    this.notify();
  }

  success(message: string, duration?: number) {
    this.show('success', message, duration);
  }

  error(message: string, duration?: number) {
    this.show('error', message, duration);
  }

  warning(message: string, duration?: number) {
    this.show('warning', message, duration);
  }

  info(message: string, duration?: number) {
    this.show('info', message, duration);
  }
}

export const toast = new ToastManager();
if (typeof window !== 'undefined') {
  (window as any).toast = toast;
}

export const ToastContainer: React.FC = () => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    return toast.subscribe((updatedToasts) => {
      setToasts(updatedToasts);
    });
  }, []);

  return (
    <div className="fixed bottom-5 right-5 z-[9999] flex flex-col space-y-2 pointer-events-none max-w-sm w-full px-4 sm:px-0">
      {toasts.map((t) => {
        const icons = {
          success: <CheckCircle2 className="w-4 h-4 text-brand-emerald shrink-0" />,
          error: <XCircle className="w-4 h-4 text-brand-rose shrink-0" />,
          warning: <AlertTriangle className="w-4 h-4 text-brand-amber shrink-0" />,
          info: <Info className="w-4 h-4 text-brand-cyan shrink-0" />,
        };

        const borderStyles = {
          success: 'border-brand-emerald/40 bg-dark-900/95 shadow-brand-emerald/10 text-slate-100',
          error: 'border-brand-rose/40 bg-dark-900/95 shadow-brand-rose/10 text-slate-100',
          warning: 'border-brand-amber/40 bg-dark-900/95 shadow-brand-amber/10 text-slate-100',
          info: 'border-brand-cyan/40 bg-dark-900/95 shadow-brand-cyan/10 text-slate-100',
        };

        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-center justify-between p-3.5 rounded-xl border shadow-xl backdrop-blur-md transition-all duration-300 animate-slide-in ${borderStyles[t.type]}`}
          >
            <div className="flex items-center space-x-2.5 mr-2">
              {icons[t.type]}
              <span className="text-xs font-medium leading-tight">{t.message}</span>
            </div>
            <button
              onClick={() => toast.remove(t.id)}
              className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-dark-800 transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
