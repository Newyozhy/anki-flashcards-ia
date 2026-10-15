import React, { useState } from 'react';
import { Key, X, ExternalLink, Check } from 'lucide-react';
import { useModalEscape } from '../utils/useModalEscape';

interface ApiKeyModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiKey: string;
  onSaveKey: (key: string) => void;
}

export const ApiKeyModal: React.FC<ApiKeyModalProps> = ({
  isOpen,
  onClose,
  apiKey,
  onSaveKey,
}) => {
  const [tempKey, setTempKey] = useState(apiKey);
  const [savedToast, setSavedToast] = useState(false);

  useModalEscape(isOpen, onClose);

  if (!isOpen) return null;

  const handleSave = () => {
    onSaveKey(tempKey.trim());
    setSavedToast(true);
    setTimeout(() => {
      setSavedToast(false);
      onClose();
    }, 800);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="api-key-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-fade-in"
    >
      <div className="relative w-full max-w-md rounded-2xl border border-slate-700/60 bg-slate-900/90 p-6 shadow-2xl shadow-indigo-950/40">
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar modal de API Key"
          className="absolute right-4 top-4 rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="flex items-center gap-3 mb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
            <Key className="h-5 w-5" />
          </div>
          <div>
            <h3 id="api-key-modal-title" className="text-lg font-semibold text-white">Configurar Gemini API Key</h3>
            <p className="text-xs text-slate-400">Gratuito en Google AI Studio</p>
          </div>
        </div>

        <p className="text-sm text-slate-300 mb-4 leading-relaxed">
          Podés usar la key configurada en el archivo <code className="text-xs bg-slate-800 px-1.5 py-0.5 rounded text-indigo-300">.env</code> del backend o ingresar una acá directamente:
        </p>

        <div className="space-y-3">
          <input
            type="password"
            value={tempKey}
            onChange={(e) => setTempKey(e.target.value)}
            aria-label="Gemini API Key"
            placeholder="AIzaSy..."
            className="w-full rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all font-mono"
          />

          <div className="flex items-center justify-between text-xs text-slate-400 pt-1">
            <span>¿No tenés una API Key?</span>
            <a
              href="https://aistudio.google.com/app/apikey"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 hover:underline"
            >
              Obtener gratis <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-all shadow-lg shadow-indigo-600/20 active:scale-95"
          >
            {savedToast ? (
              <>
                <Check className="h-4 w-4 text-emerald-300" />
                Guardado
              </>
            ) : (
              'Guardar Clave'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
