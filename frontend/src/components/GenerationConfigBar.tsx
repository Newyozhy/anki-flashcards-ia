import React, { useState } from 'react';
import { Sparkles, Sliders, ChevronDown, ChevronUp, Folder, Search, Brain, Wand2, X } from 'lucide-react';
import type { CardType, GenerationOptions } from '../types';
import { DeckPickerModal } from './DeckPickerModal';

export type CognitiveArchetypeMode =
  | 'auto'
  | 'archetype_a'
  | 'archetype_b'
  | 'archetype_c'
  | 'archetype_d'
  | 'archetype_e';

interface GenerationConfigBarProps {
  options: GenerationOptions;
  setOptions: React.Dispatch<React.SetStateAction<GenerationOptions>>;
  availableDecks: string[];
  isGenerating: boolean;
  onGenerate: () => void;
  canGenerate: boolean;
  onInspect?: () => void;
  isInspecting?: boolean;
  onCancel?: () => void;
}

export const GenerationConfigBar: React.FC<GenerationConfigBarProps> = ({
  options,
  setOptions,
  availableDecks,
  isGenerating,
  onGenerate,
  canGenerate,
  onInspect,
  isInspecting,
  onCancel,
}) => {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isDeckModalOpen, setIsDeckModalOpen] = useState(false);
  const [archetypeMode, setArchetypeMode] = useState<CognitiveArchetypeMode>('auto');

  // Handle archetype change
  const handleArchetypeChange = (mode: CognitiveArchetypeMode) => {
    setArchetypeMode(mode);
    if (mode === 'auto') {
      setOptions((prev) => ({
        ...prev,
        card_type: 'basic' as CardType,
        custom_instructions: '',
      }));
    } else if (mode === 'archetype_a') {
      setOptions((prev) => ({
        ...prev,
        card_type: 'cloze' as CardType,
        custom_instructions: 'Priorizar exclusivamente Arquetipo A: Cloze Contextualizado.',
      }));
    } else if (mode === 'archetype_b') {
      setOptions((prev) => ({
        ...prev,
        card_type: 'cloze' as CardType,
        custom_instructions: 'Priorizar exclusivamente Arquetipo B: Matriz de Contraste con tablas Markdown.',
      }));
    } else if (mode === 'archetype_c') {
      setOptions((prev) => ({
        ...prev,
        card_type: 'basic' as CardType,
        custom_instructions: 'Priorizar exclusivamente Arquetipo C: Pregunta Atómica con Restricción (< 15 palabras).',
      }));
    } else if (mode === 'archetype_d') {
      setOptions((prev) => ({
        ...prev,
        card_type: 'basic' as CardType,
        custom_instructions: 'Priorizar exclusivamente Arquetipo D: Tarjeta Radar (Índice estructural).',
      }));
    } else if (mode === 'archetype_e') {
      setOptions((prev) => ({
        ...prev,
        card_type: 'basic' as CardType,
        custom_instructions: 'Priorizar exclusivamente Arquetipo E: Mini-Escenario / Caso Aplicado (situación breve y decisión/diagnóstico).',
      }));
    }
  };

  // Format deck name visually if it has ::
  const deckParts = options.deck_name.split('::');

  return (
    <>
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-xl shadow-xl space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* 1. Target Deck: Trigger for Searchable Modal */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Folder className="h-3.5 w-3.5 text-indigo-400" />
                Mazo de Destino
              </label>
              {availableDecks.length > 0 && (
                <span className="text-[10px] font-medium text-emerald-400">
                  {availableDecks.length} en Anki
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={() => setIsDeckModalOpen(true)}
              className="w-full flex h-10 items-center justify-between rounded-xl border border-slate-700/80 bg-slate-950/90 px-3 py-2 text-left hover:border-indigo-500/70 hover:bg-slate-900/90 transition-all group"
            >
              <div className="truncate flex items-center gap-1.5 text-xs">
                {deckParts.length > 1 ? (
                  <>
                    <span className="text-slate-400 truncate max-w-[80px]">
                      {deckParts.slice(0, -1).join('/')} /
                    </span>
                    <span className="font-semibold text-white truncate">
                      {deckParts[deckParts.length - 1]}
                    </span>
                  </>
                ) : (
                  <span className="font-semibold text-white truncate">
                    {options.deck_name || 'Seleccionar mazo...'}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1 text-slate-400 group-hover:text-indigo-300 text-xs shrink-0">
                <Search className="h-3.5 w-3.5" />
                <span className="hidden sm:inline text-[11px]">Buscar</span>
              </div>
            </button>
            <p className="text-[11px] text-slate-400">Hacé clic para buscar entre tus mazos</p>
          </div>

          {/* 2. Cognitive Archetype Mode Selector */}
          <div className="space-y-1.5">
            <label htmlFor="cognitive-archetype-select" className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Brain className="h-3.5 w-3.5 text-indigo-400" />
              Arquetipo Cognitivo
            </label>

            <select
              id="cognitive-archetype-select"
              value={archetypeMode}
              onChange={(e) => handleArchetypeChange(e.target.value as CognitiveArchetypeMode)}
              className="w-full h-10 rounded-xl border border-slate-700/80 bg-slate-950/90 px-3 text-xs font-medium text-slate-100 focus:border-indigo-500 focus:outline-none transition-all"
            >
              <option value="auto">🌟 Auto / Balanceado (Recomendado)</option>
              <option value="archetype_a">📝 Arquetipo A: Cloze Contextualizado</option>
              <option value="archetype_b">📊 Arquetipo B: Matriz de Contraste</option>
              <option value="archetype_c">🎯 Arquetipo C: Pregunta Atómica (&lt; 15 pal)</option>
              <option value="archetype_d">🧭 Arquetipo D: Tarjeta Radar</option>
              <option value="archetype_e">⚡ Arquetipo E: Mini-Escenario Aplicado</option>
            </select>

            <p className="text-[11px] text-slate-400 truncate">
              {archetypeMode === 'auto'
                ? 'La IA selecciona el arquetipo según cada dato'
                : archetypeMode === 'archetype_b'
                ? 'Tablas de contraste para conceptos similares'
                : archetypeMode === 'archetype_e'
                ? 'Mini-casos y escenarios de transferencia cognitiva'
                : 'Formato atómico con reglas FSRS'}
            </p>
          </div>

          {/* 3. Card Count Selector (Auto + Custom Number Input) */}
          <div className="space-y-1.5">
            <label htmlFor="card-count-input" className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <Wand2 className="h-3.5 w-3.5 text-indigo-400" />
              Cantidad de Tarjetas
            </label>

            <div className="flex items-center gap-2 h-10">
              {/* Auto Button */}
              <button
                type="button"
                onClick={() => setOptions((prev) => ({ ...prev, target_count: 0 }))}
                className={`flex h-full items-center justify-center gap-1.5 px-3.5 rounded-xl border text-xs font-semibold transition-all shrink-0 ${
                  options.target_count === 0
                    ? 'border-indigo-500/60 bg-indigo-600/30 text-indigo-200 shadow-sm shadow-indigo-950/40 ring-1 ring-indigo-500/40'
                    : 'border-slate-800 bg-slate-950/80 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                }`}
                title="La IA evalúa la densidad conceptual del material"
              >
                <Sparkles className="h-3.5 w-3.5 text-amber-300 shrink-0" />
                <span>Auto</span>
              </button>

              {/* Custom Number Input */}
              <div className="relative flex-1 h-full">
                <input
                  id="card-count-input"
                  type="number"
                  min="1"
                  max="100"
                  aria-label="Cantidad personalizada de tarjetas"
                  placeholder="Personalizado..."
                  value={options.target_count > 0 ? options.target_count : ''}
                  onChange={(e) => {
                    const rawVal = e.target.value.trim();
                    if (!rawVal) {
                      setOptions((prev) => ({ ...prev, target_count: 0 }));
                    } else {
                      const val = parseInt(rawVal, 10);
                      if (!isNaN(val) && val > 0) {
                        setOptions((prev) => ({ ...prev, target_count: Math.min(100, val) }));
                      }
                    }
                  }}
                  className={`w-full h-full rounded-xl border px-3 text-xs font-medium text-slate-100 placeholder-slate-500 bg-slate-950/90 focus:border-indigo-500 focus:outline-none transition-all ${
                    options.target_count > 0
                      ? 'border-indigo-500/60 ring-1 ring-indigo-500/40 text-indigo-200 font-semibold'
                      : 'border-slate-800'
                  }`}
                  title="Ingresá una cantidad de tarjetas personalizada"
                />
                {options.target_count > 0 && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 font-medium pointer-events-none">
                    tarjetas
                  </span>
                )}
              </div>
            </div>

            <p className="text-[11px] text-slate-400 truncate">
              {options.target_count === 0
                ? 'Densidad calculada automáticamente por IA'
                : `Objetivo fijado en ${options.target_count} tarjeta(s)`}
            </p>
          </div>

          {/* 4. Single Prominent Action Button: Analizar y Planificar */}
          <div className="flex flex-col justify-end space-y-1.5">
            <button
              type="button"
              onClick={onInspect || onGenerate}
              disabled={!canGenerate || isGenerating || isInspecting}
              className="group relative inline-flex h-10 w-full items-center justify-center gap-2 overflow-hidden rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 px-4 text-xs font-bold text-white shadow-lg shadow-indigo-600/25 hover:shadow-indigo-500/40 transition-all duration-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
              title="Diagnostica autosuficiencia y prerrequisitos antes de generar"
            >
              {isInspecting || isGenerating ? (
                <Sparkles className="h-4 w-4 animate-spin text-amber-300" />
              ) : (
                <Brain className="h-4 w-4 text-indigo-200 transition-transform group-hover:scale-110" />
              )}
              <span className="text-xs sm:text-sm font-bold tracking-wide">
                {isInspecting
                  ? 'Diagnosticando...'
                  : isGenerating
                  ? 'Razonando...'
                  : '🔍 Analizar y Planificar'}
              </span>
            </button>
            {(isInspecting || isGenerating) && onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 px-2 py-1 text-xs font-semibold transition-all cursor-pointer shadow-xs"
              >
                <X className="h-3 w-3 text-rose-400" />
                <span>Cancelar operación</span>
              </button>
            )}
            <p className="text-[11px] text-slate-400 truncate text-center">
              Revisión previa de autosuficiencia y temas
            </p>
          </div>
        </div>

        {/* Advanced Pedagogical Collapsible */}
        <div className="border-t border-slate-800/80 pt-2">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            <Sliders className="h-3.5 w-3.5" />
            <span>Configuración pedagógica y reglas FSRS</span>
            {showAdvanced ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          </button>

          {showAdvanced && (
            <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 rounded-xl border border-slate-800/70 bg-slate-950/60 p-4 animate-fade-in">
              <div className="space-y-1.5">
                <label htmlFor="difficulty-level-select" className="text-xs font-medium text-slate-300">Nivel de Profundidad Cognitiva</label>
                <select
                  id="difficulty-level-select"
                  value={options.difficulty_level}
                  onChange={(e) =>
                    setOptions((prev) => ({
                      ...prev,
                      difficulty_level: e.target.value as GenerationOptions['difficulty_level'],
                    }))
                  }
                  className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 focus:border-indigo-500 focus:outline-none"
                >
                  <option value="beginner">Principiante (Conceptos clave y definiciones directas)</option>
                  <option value="intermediate">Intermedio (Relaciones causa-efecto y contrastes)</option>
                  <option value="advanced">Avanzado (Casos clínicos, excepciones y análisis crítico)</option>
                </select>
              </div>

              <div className="space-y-1.5">
                <label htmlFor="custom-instructions-input" className="text-xs font-medium text-slate-300">
                  {options.ai_provider === 'ollama'
                    ? `Instrucción Adicional para ${options.local_model || 'Ollama Local'}`
                    : 'Instrucción Adicional para Gemini'}
                </label>
                <input
                  id="custom-instructions-input"
                  type="text"
                  value={options.custom_instructions || ''}
                  onChange={(e) =>
                    setOptions((prev) => ({
                      ...prev,
                      custom_instructions: e.target.value,
                    }))
                  }
                  placeholder="Ej: Foco en fórmulas matemáticas en LaTeX"
                  className="w-full rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Deck Picker Modal */}
      <DeckPickerModal
        isOpen={isDeckModalOpen}
        onClose={() => setIsDeckModalOpen(false)}
        availableDecks={availableDecks}
        selectedDeck={options.deck_name}
        onSelectDeck={(deck) => setOptions((prev) => ({ ...prev, deck_name: deck }))}
      />
    </>
  );
};
