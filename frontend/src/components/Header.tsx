import React from 'react';
import { Layers, RefreshCw, Key, CheckCircle2, AlertTriangle, Cpu, Zap } from 'lucide-react';
import type { AnkiStatus, OllamaStatus } from '../types';

interface HeaderProps {
  ankiStatus: AnkiStatus;
  isLoadingAnki: boolean;
  onRefreshAnki: () => void;
  onOpenApiKeyModal: () => void;
  hasCustomKey: boolean;
  ollamaStatus?: OllamaStatus;
  aiProvider?: 'gemini' | 'ollama';
  localModel?: string;
  onProviderChange?: (provider: 'gemini' | 'ollama') => void;
  onModelChange?: (model: string) => void;
  onOpenDeckStudio?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  ankiStatus,
  isLoadingAnki,
  onRefreshAnki,
  onOpenApiKeyModal,
  hasCustomKey,
  ollamaStatus,
  aiProvider = 'gemini',
  localModel = 'llama3.2:3b',
  onProviderChange,
  onModelChange,
  onOpenDeckStudio,
}) => {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-xl transition-all">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        {/* Brand identity */}
        <div className="flex items-center gap-3">
          <div className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 shadow-lg shadow-indigo-500/25">
            <Layers className="h-5 w-5 text-white" />
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75"></span>
              <span className="relative inline-flex h-3 w-3 rounded-full bg-indigo-500"></span>
            </span>
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-lg font-bold tracking-tight text-white sm:text-xl">
                AnkiCraft <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">AI</span>
              </h1>
              {aiProvider === 'ollama' ? (
                <span className="rounded-full bg-purple-500/20 px-2 py-0.5 text-[10px] font-bold text-purple-300 border border-purple-500/30 flex items-center gap-1">
                  <Cpu className="h-3 w-3" />
                  <span>Ollama Local ({localModel})</span>
                </span>
              ) : (
                <span className="rounded-full bg-indigo-500/10 px-2 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-500/20">
                  Gemini 3.8 Flash
                </span>
              )}
            </div>
            <p className="hidden text-xs text-slate-400 sm:block">
              Generador Inteligente de Flashcards con Spaced Repetition
            </p>
          </div>
        </div>

        {/* Status Indicators & Controls */}
        <div className="flex items-center gap-2 sm:gap-3 flex-wrap justify-end">
          {/* AI Provider Switcher */}
          <div className="flex items-center rounded-xl border border-slate-700/80 bg-slate-900/90 p-1 text-xs shadow-sm">
            <button
              type="button"
              onClick={() => onProviderChange?.('gemini')}
              className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                aiProvider === 'gemini'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Google Gemini Cloud (Multimodal, alta velocidad)"
            >
              <span>☁️ Cloud (Gemini)</span>
            </button>

            <button
              type="button"
              onClick={() => onProviderChange?.('ollama')}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                aiProvider === 'ollama'
                  ? 'bg-purple-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title={
                ollamaStatus?.is_available
                  ? `Ollama Local Activo en GPU (127.0.0.1:11434)${
                      ollamaStatus?.running_models && ollamaStatus.running_models.length > 0
                        ? ` • Precargado en VRAM: ${ollamaStatus.running_models.join(', ')}`
                        : ' • Ningún modelo en VRAM (se cargará al generar)'
                    }`
                  : 'Ollama Local no detectado en localhost:11434'
              }
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  ollamaStatus?.is_available ? 'bg-emerald-400' : 'bg-rose-400'
                }`}
              />
              <span>🖥️ Local (GPU)</span>
            </button>
          </div>

          {/* Local Model Selector */}
          {aiProvider === 'ollama' && (
            <div className="flex items-center gap-1.5">
              <select
                value={localModel}
                onChange={(e) => onModelChange?.(e.target.value)}
                aria-label="Seleccionar modelo local de Ollama"
                className="h-8 rounded-xl border border-purple-500/40 bg-purple-950/40 px-2 text-xs font-bold text-purple-200 focus:outline-none cursor-pointer"
                title="Seleccionar modelo local de Ollama"
              >
                {ollamaStatus?.models && ollamaStatus.models.length > 0 ? (
                  ollamaStatus.models.map((m) => {
                    const isWarm = ollamaStatus.running_models?.includes(m);
                    return (
                      <option key={m} value={m} className="bg-slate-900 text-white">
                        {isWarm ? `⚡ ${m} (En VRAM)` : m}
                      </option>
                    );
                  })
                ) : (
                  <>
                    <option value="qwen2.5:14b" className="bg-slate-900 text-white">qwen2.5:14b (Recomendado)</option>
                    <option value="qwen2.5vl:7b" className="bg-slate-900 text-white">qwen2.5vl:7b (Multimodal)</option>
                    <option value="llama3.2:3b" className="bg-slate-900 text-white">llama3.2:3b (Rápido)</option>
                  </>
                )}
              </select>

              {ollamaStatus?.running_models?.includes(localModel || '') && (
                <span
                  className="hidden sm:inline-flex items-center gap-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 px-2 py-1 text-[10px] font-bold text-emerald-300"
                  title="Este modelo está actualmente cargado en la memoria de tu GPU Radeon (respuesta instantánea)"
                >
                  <Zap className="h-3 w-3 text-emerald-400" />
                  <span>En VRAM</span>
                </span>
              )}
            </div>
          )}

          {/* AnkiConnect Status Pill */}
          <div
            className={`flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-medium backdrop-blur-md transition-all ${
              ankiStatus.is_connected
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300 shadow-sm shadow-emerald-950/40'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-300'
            }`}
            title={
              ankiStatus.is_connected
                ? `Anki Desktop Conectado (${ankiStatus.version}) - ${ankiStatus.available_decks.length} mazos encontrados`
                : 'Anki Desktop no detectado en localhost:8765. Se usará exportación a archivo .apkg'
            }
          >
            {ankiStatus.is_connected ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
                </span>
                <span className="hidden sm:inline">Anki Desktop:</span> Conectado
              </>
            ) : (
              <>
                <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
                <span className="hidden sm:inline">Anki:</span> Modo .apkg
              </>
            )}

            <button
              type="button"
              onClick={onRefreshAnki}
              disabled={isLoadingAnki}
              aria-label="Volver a comprobar conexión con Anki"
              className="ml-1 rounded-md p-0.5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
              title="Volver a comprobar conexión con Anki"
            >
              <RefreshCw className={`h-3 w-3 ${isLoadingAnki ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* Deck Studio Button */}
          {onOpenDeckStudio && (
            <button
              type="button"
              onClick={onOpenDeckStudio}
              className="flex items-center gap-1.5 rounded-xl border border-indigo-500/40 bg-gradient-to-r from-indigo-600/20 to-violet-600/20 px-3 py-1.5 text-xs font-bold text-indigo-200 hover:border-indigo-400 hover:text-white transition-all shadow-sm active:scale-95 cursor-pointer"
              title="Abrir Deck Studio: Auditoría Temática, Grafo DAG y Auditor de Deuda"
            >
              <span>🏛️ Deck Studio</span>
            </button>
          )}

          {/* Gemini API Key Button */}
          {aiProvider === 'gemini' && (
            <button
              onClick={onOpenApiKeyModal}
              aria-label="Configurar API Key de Gemini"
              className={`flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium transition-all ${
                hasCustomKey
                  ? 'border-indigo-500/40 bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20'
                  : 'border-slate-700 bg-slate-800/80 text-slate-300 hover:border-slate-600 hover:bg-slate-800'
              }`}
            >
              <Key className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">API Key</span>
              {hasCustomKey && <CheckCircle2 className="h-3 w-3 text-indigo-400" />}
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
