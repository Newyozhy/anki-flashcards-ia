import React from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  title: string;
  message?: string;
}

interface ToastProps {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export const ToastContainer: React.FC<ToastProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md w-full px-4 sm:px-0"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role={toast.type === 'error' ? 'alert' : 'status'}
          className={`flex items-start justify-between gap-3 rounded-2xl border p-4 shadow-2xl backdrop-blur-xl animate-fade-in ${
            toast.type === 'success'
              ? 'border-emerald-500/30 bg-slate-900/95 text-emerald-300 shadow-emerald-950/30'
              : toast.type === 'error'
              ? 'border-rose-500/30 bg-slate-900/95 text-rose-300 shadow-rose-950/30'
              : 'border-indigo-500/30 bg-slate-900/95 text-indigo-300 shadow-indigo-950/30'
          }`}
        >
          <div className="flex items-start gap-3">
            {toast.type === 'success' && <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-400 mt-0.5" />}
            {toast.type === 'error' && <AlertCircle className="h-5 w-5 shrink-0 text-rose-400 mt-0.5" />}
            {toast.type === 'info' && <Info className="h-5 w-5 shrink-0 text-indigo-400 mt-0.5" />}
            <div>
              <h4 className="text-xs font-semibold text-white">{toast.title}</h4>
              {toast.message && <p className="mt-0.5 text-xs text-slate-300 leading-relaxed">{toast.message}</p>}
            </div>
          </div>

          <button
            type="button"
            onClick={() => onDismiss(toast.id)}
            aria-label="Cerrar notificación"
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
};
