import React, { useState } from 'react';
import {
  X,
  Brain,
  CheckCircle2,
  AlertTriangle,
  Layers,
  Wrench,
  ChevronDown,
  ChevronUp,
  Sparkles,
  ShieldCheck,
  Check,
  EyeOff,
  ExternalLink,
} from 'lucide-react';
import type { DeckAuditReport, CognitiveAuditFinding } from '../types';
import { useModalEscape } from '../utils/useModalEscape';
import { CardContentRenderer } from './CardContentRenderer';

interface CognitiveAuditModalProps {
  report: DeckAuditReport;
  isOpen: boolean;
  onClose: () => void;
  onApplySuggestion?: (cardId: string, finding: CognitiveAuditFinding) => void;
  onIgnoreSuggestion?: (cardId: string, findingRule: string) => void;
  onFocusCard?: (cardId: string) => void;
}

type FilterType = 'all' | 'repaired' | 'sisters' | 'warnings';

export const CognitiveAuditModal: React.FC<CognitiveAuditModalProps> = ({
  report,
  isOpen,
  onClose,
  onApplySuggestion,
  onIgnoreSuggestion,
  onFocusCard,
}) => {
  const [filter, setFilter] = useState<FilterType>('all');
  const [expandedCardId, setExpandedCardId] = useState<string | null>(null);
  const [appliedFindings, setAppliedFindings] = useState<Record<string, boolean>>({});
  const [ignoredFindings, setIgnoredFindings] = useState<Record<string, boolean>>({});

  useModalEscape(isOpen, onClose);

  if (!isOpen) return null;

  const filteredCards = report.card_reports.filter((c) => {
    if (filter === 'repaired') {
      return c.findings.some((f) => f.auto_fixed);
    }
    if (filter === 'sisters') {
      return c.sister_cards_count > 1;
    }
    if (filter === 'warnings') {
      return c.findings.some((f) => f.severity === 'WARNING' || f.severity === 'VIOLATION');
    }
    return true;
  });

  const getScoreBadge = (score: number) => {
    if (score >= 90) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 text-xs font-bold text-emerald-400">
          <ShieldCheck className="h-3.5 w-3.5" />
          {score}/100 • Calidad Óptima
        </span>
      );
    }
    if (score >= 75) {
      return (
        <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 border border-amber-500/30 px-3 py-1 text-xs font-bold text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5" />
          {score}/100 • Aceptable
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-500/10 border border-rose-500/30 px-3 py-1 text-xs font-bold text-rose-400">
        <AlertTriangle className="h-3.5 w-3.5" />
        {score}/100 • Requiere Atención
      </span>
    );
  };

  const getSeverityBadge = (severity: string) => {
    switch (severity) {
      case 'VIOLATION':
        return (
          <span className="rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 px-1.5 py-0.5 text-[10px] font-bold">
            INFRACCIÓN ATÓMICA
          </span>
        );
      case 'WARNING':
        return (
          <span className="rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 px-1.5 py-0.5 text-[10px] font-bold">
            ADVERTENCIA
          </span>
        );
      default:
        return (
          <span className="rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 px-1.5 py-0.5 text-[10px] font-bold">
            MEJORA COGNITIVA
          </span>
        );
    }
  };

  const handleApply = (cardId: string, finding: CognitiveAuditFinding, findingIndex: number) => {
    const key = `${cardId}-${findingIndex}`;
    setAppliedFindings((prev) => ({ ...prev, [key]: true }));
    if (onApplySuggestion) {
      onApplySuggestion(cardId, finding);
    }
  };

  const handleIgnore = (cardId: string, rule: string, findingIndex: number) => {
    const key = `${cardId}-${findingIndex}`;
    setIgnoredFindings((prev) => ({ ...prev, [key]: true }));
    if (onIgnoreSuggestion) {
      onIgnoreSuggestion(cardId, rule);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cognitive-audit-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 backdrop-blur-md bg-slate-950/80 animate-fade-in"
    >
      <div className="relative flex flex-col w-full max-w-5xl max-h-[90vh] rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl shadow-indigo-950/50 overflow-hidden text-slate-100">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 p-5 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-md shadow-indigo-500/20">
              <Brain className="h-5 w-5 text-white" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h2 id="cognitive-audit-modal-title" className="text-lg font-bold text-white tracking-tight">
                  Auditor Neurocognitivo & Linter de Calidad
                </h2>
                {getScoreBadge(report.average_quality_score)}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Verificación de principios de neurociencia (Wozniak, Metcalfe) e integridad sintáctica para Anki.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar auditoría"
            className="rounded-xl p-2 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            title="Cerrar auditoría"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 bg-slate-900/50 border-b border-slate-800 text-xs">
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 flex flex-col justify-between">
            <span className="text-slate-400 text-[11px] font-medium flex items-center gap-1.5">
              <Layers className="h-3.5 w-3.5 text-indigo-400" />
              Tarjetas Auditadas
            </span>
            <span className="text-xl font-bold text-white mt-1">
              {report.total_cards_audited}
            </span>
          </div>

          <div className="rounded-xl border border-emerald-900/30 bg-emerald-950/20 p-3 flex flex-col justify-between">
            <span className="text-emerald-300 text-[11px] font-medium flex items-center gap-1.5">
              <Wrench className="h-3.5 w-3.5 text-emerald-400" />
              Auto-reparadas
            </span>
            <span className="text-xl font-bold text-emerald-400 mt-1">
              {report.total_cards_repaired}
            </span>
          </div>

          <div className="rounded-xl border border-purple-900/30 bg-purple-950/20 p-3 flex flex-col justify-between">
            <span className="text-purple-300 text-[11px] font-medium flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 text-purple-400" />
              Tarjetas Hermanas (Desacople)
            </span>
            <span className="text-xl font-bold text-purple-400 mt-1">
              {report.total_sister_cards_created}
            </span>
          </div>

          <div className="rounded-xl border border-indigo-900/30 bg-indigo-950/20 p-3 flex flex-col justify-between">
            <span className="text-indigo-300 text-[11px] font-medium flex items-center gap-1.5">
              <ShieldCheck className="h-3.5 w-3.5 text-indigo-400" />
              Puntuación Global
            </span>
            <span className="text-xl font-bold text-indigo-300 mt-1">
              {report.average_quality_score} <span className="text-xs text-slate-400 font-normal">/ 100</span>
            </span>
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex items-center gap-2 px-5 py-2.5 bg-slate-950/40 border-b border-slate-800 text-xs overflow-x-auto">
          <span className="text-slate-400 font-medium mr-1 text-[11px]">Filtrar:</span>
          <button
            type="button"
            onClick={() => setFilter('all')}
            className={`rounded-lg px-2.5 py-1 font-medium transition-all ${
              filter === 'all'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            Todas ({report.card_reports.length})
          </button>
          <button
            type="button"
            onClick={() => setFilter('repaired')}
            className={`rounded-lg px-2.5 py-1 font-medium transition-all ${
              filter === 'repaired'
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            Auto-reparadas ({report.total_cards_repaired})
          </button>
          <button
            type="button"
            onClick={() => setFilter('sisters')}
            className={`rounded-lg px-2.5 py-1 font-medium transition-all ${
              filter === 'sisters'
                ? 'bg-purple-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            Tarjetas Hermanas ({report.total_sister_cards_created})
          </button>
          <button
            type="button"
            onClick={() => setFilter('warnings')}
            className={`rounded-lg px-2.5 py-1 font-medium transition-all ${
              filter === 'warnings'
                ? 'bg-amber-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
            }`}
          >
            Advertencias ({report.card_reports.filter((c) => c.findings.some((f) => f.severity !== 'INFO')).length})
          </button>
        </div>

        {/* Table Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {filteredCards.length === 0 ? (
            <div className="text-center py-12 text-slate-400 text-sm">
              No hay registros bajo este filtro.
            </div>
          ) : (
            filteredCards.map((cardReport, idx) => {
              const isExpanded = expandedCardId === cardReport.card_id;
              const hasFixes = cardReport.findings.some((f) => f.auto_fixed);

              // Calculate stable, true card position in the batch
              const originalIndex = report.card_reports.findIndex((c) => c.card_id === cardReport.card_id);
              const stableCardNumber = originalIndex >= 0 ? originalIndex + 1 : idx + 1;

              return (
                <div
                  key={cardReport.card_id || idx}
                  className="rounded-xl border border-slate-800 bg-slate-950/70 p-3.5 transition-colors hover:border-slate-700"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                        {/* Stable Card Badge */}
                        <span className="rounded-lg bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 px-2 py-0.5 text-xs font-mono font-bold shadow-sm">
                          Tarjeta #{stableCardNumber}
                        </span>

                        {cardReport.card_id && (
                          <span className="text-[10px] font-mono text-slate-400">
                            ID: {cardReport.card_id.length > 8 ? cardReport.card_id.slice(-6) : cardReport.card_id}
                          </span>
                        )}

                        {onFocusCard && (
                          <button
                            type="button"
                            onClick={() => onFocusCard(cardReport.card_id)}
                            className="inline-flex items-center gap-1 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300 hover:text-white px-2 py-0.5 text-[10px] font-semibold transition-colors border border-slate-700/80"
                            title="Cerrar modal e ir a editar esta tarjeta"
                          >
                            <ExternalLink className="h-3 w-3" /> Ver en Editor
                          </button>
                        )}

                        {cardReport.passed ? (
                          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-semibold">
                            <CheckCircle2 className="h-3 w-3" /> Aprobada
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 font-semibold">
                            <AlertTriangle className="h-3 w-3" /> Reparada
                          </span>
                        )}
                        <span className="text-[11px] font-mono text-slate-400">
                          Score: {cardReport.score}/100
                        </span>
                        {cardReport.sister_cards_count > 1 && (
                          <span className="rounded bg-purple-500/20 text-purple-300 border border-purple-500/30 px-1.5 py-0.5 text-[10px] font-bold">
                            Desacoplada en {cardReport.sister_cards_count} Hermanas
                          </span>
                        )}
                        {hasFixes && (
                          <span className="rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 px-1.5 py-0.5 text-[10px] font-bold">
                            Auto-corregida
                          </span>
                        )}
                      </div>

                      <div className="text-xs text-slate-200 bg-slate-900/80 p-2 rounded-lg border border-slate-800/80">
                        <CardContentRenderer content={cardReport.card_front_preview} mode="back" />
                      </div>

                      {/* Findings list */}
                      {cardReport.findings.length > 0 && (
                        <div className="mt-2.5 space-y-2">
                          {cardReport.findings.map((f, fi) => {
                            const findingKey = `${cardReport.card_id}-${fi}`;
                            const isApplied = appliedFindings[findingKey];
                            const isIgnored = ignoredFindings[findingKey];

                            return (
                              <div
                                key={fi}
                                className="text-xs bg-slate-900/60 rounded-lg p-2.5 border border-slate-800/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5"
                              >
                                <div className="flex items-start gap-2 flex-1 min-w-0">
                                  <div className="shrink-0 mt-0.5">
                                    {getSeverityBadge(f.severity)}
                                  </div>
                                  <div className="flex-1 text-[11px] text-slate-300 leading-relaxed">
                                    {f.message}
                                    {f.auto_fixed && (
                                      <span className="ml-1.5 text-emerald-400 font-semibold">
                                        [✓ Corregido automáticamente]
                                      </span>
                                    )}
                                    {isApplied && (
                                      <span className="ml-1.5 text-emerald-400 font-bold">
                                        [✓ Sugerencia Aplicada al Editor]
                                      </span>
                                    )}
                                    {isIgnored && (
                                      <span className="ml-1.5 text-slate-400 font-semibold italic">
                                        [Excepción Aceptada / Ignorada]
                                      </span>
                                    )}
                                  </div>
                                </div>

                                {/* Interactive Action Buttons for Non-Autofixed Suggestions */}
                                {!f.auto_fixed && !isApplied && !isIgnored && (f.suggested_replacement || f.corrected_snippet) && (
                                  <div className="flex items-center gap-1.5 shrink-0 self-end sm:self-center">
                                    <button
                                      type="button"
                                      onClick={() => handleApply(cardReport.card_id, f, fi)}
                                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-600/30 hover:bg-emerald-600/50 text-emerald-300 border border-emerald-500/40 px-2.5 py-1 text-[11px] font-semibold transition-all shadow-sm active:scale-95"
                                      title="Aplicar la sugerencia automáticamente al contenido de la tarjeta"
                                    >
                                      <Check className="h-3 w-3" /> Aceptar Sugerencia
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => handleIgnore(cardReport.card_id, f.rule, fi)}
                                      className="inline-flex items-center gap-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white px-2 py-1 text-[11px] font-medium transition-all border border-slate-700 active:scale-95"
                                      title="Ignorar advertencia y mantener como excepción válida"
                                    >
                                      <EyeOff className="h-3 w-3" /> Ignorar
                                    </button>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {/* Expandable Before / After Comparison */}
                      {isExpanded && (
                        <div className="mt-3 pt-3 border-t border-slate-800/80 space-y-2 text-xs">
                          {cardReport.findings
                            .filter((f) => f.original_snippet || f.corrected_snippet || f.suggested_replacement)
                            .map((f, fi) => (
                              <div key={fi} className="space-y-1">
                                <span className="text-[11px] font-semibold text-slate-400">
                                  {f.auto_fixed ? `Detalle de Transformación (${f.rule}):` : `Diagnóstico y Sugerencia (${f.rule}):`}
                                </span>
                                {f.original_snippet && (
                                  <div className="rounded bg-rose-950/30 border border-rose-900/30 p-2 text-rose-200 text-[11px]">
                                    <span className="text-[10px] text-rose-400 font-bold block mb-0.5 uppercase">
                                      {f.auto_fixed ? "Antes (Emisión Cruda del LLM):" : "Fragmento Detectado en la Tarjeta:"}
                                    </span>
                                    <CardContentRenderer content={f.original_snippet} mode="back" />
                                  </div>
                                )}
                                {(f.suggested_replacement || f.corrected_snippet) && (
                                  <div className="rounded bg-emerald-950/30 border border-emerald-900/30 p-2 text-emerald-200 text-[11px]">
                                    <span className="text-[10px] text-emerald-400 font-bold block mb-0.5 uppercase">
                                      {f.auto_fixed ? "Después (Sanitizado para Anki y Memoria):" : "Sugerencia de Optimización Neurocognitiva:"}
                                    </span>
                                    <CardContentRenderer
                                      content={(f.suggested_replacement || f.corrected_snippet) ?? ''}
                                      mode="back"
                                    />
                                  </div>
                                )}
                              </div>
                            ))}
                        </div>
                      )}
                    </div>

                    <button
                      type="button"
                      aria-expanded={isExpanded}
                      aria-label={isExpanded ? 'Contraer detalles' : 'Ver comparación Antes / Después'}
                      onClick={() => setExpandedCardId(isExpanded ? null : cardReport.card_id)}
                      className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors shrink-0 mt-1"
                      title={isExpanded ? 'Contraer detalles' : 'Ver comparación Antes / Después'}
                    >
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4" />
                      ) : (
                        <ChevronDown className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 p-4 bg-slate-950/60 text-xs">
          <div className="flex items-center gap-2 text-slate-400 text-[11px]">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            <span>Todas las tarjetas cumplen el estándar de importación directa a Anki.</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl bg-indigo-600 px-4 py-2 font-semibold text-white shadow-lg shadow-indigo-600/30 hover:bg-indigo-500 transition-all text-xs"
          >
            Cerrar y Revisar Tarjetas
          </button>
        </div>
      </div>
    </div>
  );
};
