import React, { useState } from 'react';
import {
  Brain,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Layers,
  Sparkles,
  RefreshCw,
  X,
  ArrowRight,
  HelpCircle,
} from 'lucide-react';
import type { StudyPlanInspection } from '../types';

interface ActiveStudyPlanBannerProps {
  inspection: StudyPlanInspection;
  isGenerating: boolean;
  hasGeneratedCards?: boolean;
  generatedCount?: number;
  lastGenerationError?: string | null;
  onOpenCockpit: () => void;
  onGenerateApproved: () => void;
  onClearInspection: () => void;
}

export const ActiveStudyPlanBanner: React.FC<ActiveStudyPlanBannerProps> = ({
  inspection,
  isGenerating,
  hasGeneratedCards = false,
  generatedCount,
  lastGenerationError,
  onOpenCockpit,
  onGenerateApproved,
  onClearInspection,
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(true);
  const [expandedPrereqId, setExpandedPrereqId] = useState<string | null>(null);

  const selectedPrereqs = inspection.prerequisites.filter((p) => p.selected);
  const selectedThemes = inspection.core_themes.filter((t) => t.selected);
  const themeCardsTotal = selectedThemes.reduce((sum, t) => sum + t.recommended_cards, 0);
  const prereqCardsTotal = selectedPrereqs.reduce(
    (sum, p) =>
      sum +
      (p.mode === 'deep_dive'
        ? p.deep_card_count === 0
          ? p.recommended_deep_cards || 3
          : p.deep_card_count || p.recommended_deep_cards || 3
        : 1),
    0
  );
  const grandTotalCards = themeCardsTotal + prereqCardsTotal;

  const score = inspection.self_sufficiency_score;
  const scoreBadge =
    score >= 80
      ? 'border-emerald-500/40 bg-emerald-950/40 text-emerald-400'
      : score >= 50
      ? 'border-amber-500/40 bg-amber-950/40 text-amber-400'
      : 'border-rose-500/40 bg-rose-950/40 text-rose-400';

  return (
    <section className={`rounded-2xl border p-5 shadow-xl backdrop-blur-sm transition-all animate-fade-in ${
      hasGeneratedCards
        ? 'border-emerald-500/40 bg-gradient-to-b from-emerald-950/20 via-slate-900/90 to-slate-950/90 shadow-emerald-950/20'
        : 'border-indigo-500/30 bg-gradient-to-b from-indigo-950/30 via-slate-900/90 to-slate-950/90 shadow-indigo-950/20'
    }`}>
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div className="flex items-start sm:items-center gap-3">
          <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border shadow-inner ${
            hasGeneratedCards
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
              : 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400'
          }`}>
            {hasGeneratedCards ? <CheckCircle2 className="h-5 w-5" /> : <Brain className="h-5 w-5" />}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                hasGeneratedCards
                  ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                  : 'text-indigo-400 bg-indigo-500/10 border-indigo-500/20'
              }`}>
                {hasGeneratedCards ? '✓ Plan Generado y en Pantalla' : 'Plan de Estudio Activo'}
              </span>
              <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${scoreBadge}`}>
                Autosuficiencia: {score}%
              </span>
            </div>
            <h3 className="text-base font-bold text-white mt-1 flex items-center gap-2">
              <span>{inspection.topic_name}</span>
              <span className="text-xs font-normal text-slate-400">
                {hasGeneratedCards
                  ? `(${generatedCount || grandTotalCards} flashcards en mazo abajo)`
                  : `(${grandTotalCards} tarjetas planificadas)`}
              </span>
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 bg-slate-800/80 hover:bg-slate-700/80 transition-colors border border-slate-700"
          >
            <span>{isExpanded ? 'Ocultar Cola' : 'Ver Cola y Descubrimientos'}</span>
            {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          <button
            type="button"
            onClick={onOpenCockpit}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-indigo-300 bg-indigo-950/60 hover:bg-indigo-900/60 border border-indigo-500/40 transition-colors"
          >
            <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
            <span>Editar Diagnóstico</span>
          </button>

          <button
            type="button"
            onClick={onClearInspection}
            aria-label="Descartar este plan de estudio"
            title="Descartar este plan de estudio"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Demand Peak / Transient Error Notice Banner */}
      {lastGenerationError && (
        <div className="mt-4 rounded-xl border border-amber-500/40 bg-amber-950/40 p-3.5 flex items-start justify-between gap-3 text-amber-200 animate-fade-in">
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="h-4 w-4 shrink-0 text-amber-400 mt-0.5" />
            <div className="text-xs space-y-1">
              <p className="font-semibold text-amber-300">
                La API experimentó un pico de demanda o saturación temporal.
              </p>
              <p className="text-amber-200/80">
                ¡Tu diagnóstico y los conceptos investigados siguen intactos! Podés reintentar generar las tarjetas ahora mismo.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onGenerateApproved}
            disabled={isGenerating}
            className="shrink-0 flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold text-amber-950 bg-amber-400 hover:bg-amber-300 transition-colors shadow-sm disabled:opacity-50"
          >
            {isGenerating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            <span>Reintentar Ahora</span>
          </button>
        </div>
      )}

      {/* Expandable Scaffolding Queue & Discoveries */}
      {isExpanded && (
        <div className="mt-4 space-y-4 pt-2">
          {/* Section: Prerequisite queue */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className={`h-4 w-4 ${hasGeneratedCards ? 'text-emerald-400' : 'text-amber-400'}`} />
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                  {hasGeneratedCards
                    ? `Fundamentos Base Incluidos en Mazo (${selectedPrereqs.length} generados)`
                    : `Cola de Fundamentos Previos (${selectedPrereqs.length} en cola)`}
                </h4>
              </div>
              <span className="text-[11px] text-slate-400">
                {hasGeneratedCards
                  ? 'Tarjetas base generadas como `[Fundamento > Concepto]` (visibles en el mazo abajo)'
                  : 'Se generarán como tarjetas base `[Fundamento > Concepto]`'}
              </span>
            </div>

            {selectedPrereqs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/40 p-4 text-center text-xs text-slate-400">
                No seleccionaste conceptos previos para investigar. Podés agregarlos en "Editar Diagnóstico".
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                {selectedPrereqs.map((prereq) => {
                  const prereqKey = prereq.id || prereq.concept;
                  const isPrereqExpanded = expandedPrereqId === prereqKey;
                  return (
                    <div
                      key={prereqKey}
                      className={`rounded-xl border p-3.5 space-y-2 transition-colors ${
                        hasGeneratedCards
                          ? 'border-emerald-500/20 bg-slate-950/60 hover:border-emerald-500/40'
                          : 'border-indigo-500/20 bg-slate-950/60 hover:border-indigo-500/40'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-0.5">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-bold text-white">{prereq.concept}</span>
                            {hasGeneratedCards ? (
                              <span className="rounded bg-emerald-500/20 border border-emerald-500/30 px-1.5 py-0.2 text-[9px] font-bold text-emerald-300">
                                ✓ En Mazo
                              </span>
                            ) : (
                              <span className="rounded bg-indigo-500/20 border border-indigo-500/30 px-1.5 py-0.2 text-[9px] font-semibold text-indigo-300">
                                En Cola
                              </span>
                            )}
                            {prereq.mode === 'deep_dive' && (
                              <span className="rounded bg-purple-500/20 border border-purple-500/30 px-1.5 py-0.2 text-[9px] font-bold text-purple-300">
                                {prereq.deep_card_count === 0
                                  ? '✨ Sub-evento (Auto - Densidad IA)'
                                  : `✨ Sub-evento (${prereq.deep_card_count || 4} cards)`}
                              </span>
                            )}
                          </div>
                          <p className="text-[11px] text-slate-400 line-clamp-2">{prereq.reason}</p>
                        </div>

                        {prereq.isEnriching ? (
                          <div className="flex items-center gap-1 text-[10px] text-indigo-300 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-500/30 animate-pulse">
                            <Loader2 className="h-3 w-3 animate-spin text-indigo-400" />
                            <span>Investigando...</span>
                          </div>
                        ) : prereq.enriched_summary ? (
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedPrereqId(isPrereqExpanded ? null : prereq.id)
                            }
                            className="flex items-center gap-1 text-[10px] font-semibold text-emerald-300 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/30 hover:bg-emerald-900/40 transition-colors"
                          >
                            <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                            <span>Descubrimiento</span>
                            {isPrereqExpanded ? (
                              <ChevronUp className="h-2.5 w-2.5" />
                            ) : (
                              <ChevronDown className="h-2.5 w-2.5" />
                            )}
                          </button>
                        ) : (
                          <span className="text-[10px] text-slate-400 bg-slate-800/60 px-2 py-0.5 rounded">
                            Pendiente
                          </span>
                        )}
                      </div>

                      {/* Expanded Takeaway & Findings */}
                      {isPrereqExpanded && prereq.enriched_summary && (
                        <div className="rounded-lg border border-slate-800 bg-slate-900/90 p-2.5 text-[11px] text-slate-300 space-y-1.5 animate-fade-in">
                          <div className="font-semibold text-indigo-300 flex items-center gap-1">
                            <HelpCircle className="h-3 w-3 text-indigo-400" />
                            <span>Síntesis Conceptual Encontrada:</span>
                          </div>
                          <p className="text-slate-300 leading-relaxed whitespace-pre-line text-[11px]">
                            {prereq.enriched_summary}
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Action Row */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-800/80 pt-3">
            <div className="text-xs text-slate-400">
              {hasGeneratedCards ? (
                <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  <span>
                    <strong>{generatedCount || grandTotalCards} flashcards</strong> ya generadas e incluidas en el mazo abajo (Ejes + Fundamentos).
                  </span>
                </div>
              ) : (
                <span>
                  Ejes temáticos activos: <strong className="text-slate-200">{selectedThemes.length} subtemas</strong> ({themeCardsTotal} tarjetas) +{' '}
                  <strong className="text-slate-200">{selectedPrereqs.length} fundamentos en cola</strong>
                </span>
              )}
            </div>

            <button
              type="button"
              onClick={onGenerateApproved}
              disabled={isGenerating || grandTotalCards === 0}
              className={`w-full sm:w-auto flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-xs font-bold text-white shadow-lg transition-all cursor-pointer disabled:opacity-50 disabled:pointer-events-none ${
                hasGeneratedCards
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-600 shadow-emerald-600/30 hover:from-emerald-500 hover:to-teal-500'
                  : 'bg-gradient-to-r from-indigo-500 to-indigo-600 shadow-indigo-600/30 hover:from-indigo-600 hover:to-indigo-700'
              }`}
            >
              {isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Generando {grandTotalCards} Tarjetas con Andamiaje...</span>
                </>
              ) : hasGeneratedCards ? (
                <>
                  <RefreshCw className="h-4 w-4 text-emerald-200" />
                  <span>Regenerar Mazo Completo ({hasGeneratedCards && generatedCount ? generatedCount : grandTotalCards})</span>
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 text-indigo-200" />
                  <span>Generar {grandTotalCards} Flashcards Aprobadas</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </section>
  );
};
