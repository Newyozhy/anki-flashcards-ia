import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertCircle,
  Sparkles,
  BookmarkPlus,
  Zap,
  ArrowRight,
  ShieldCheck,
  Check,
  Loader2,
  Calendar,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  TopicCoverageAuditResponse,
  OrphanGap,
  CoverageGapStatus,
} from '../types';

interface ThematicCoverageChecklistProps {
  audit: TopicCoverageAuditResponse;
  deckName?: string;
  apiKey?: string;
  onAuditUpdated?: (updatedAudit: TopicCoverageAuditResponse) => void;
  onEnqueueGap?: (gap: OrphanGap) => void;
  onGenerateFromGap?: (gap: OrphanGap) => void;
}

export const ThematicCoverageChecklist: React.FC<ThematicCoverageChecklistProps> = ({
  audit,
  deckName = audit.deck_name,
  apiKey,
  onAuditUpdated,
  onEnqueueGap,
  onGenerateFromGap,
}) => {
  const [updatingGapIndex, setUpdatingGapIndex] = useState<number | null>(null);
  const [gapFilter, setGapFilter] = useState<'all' | 'pending' | 'resolved'>('all');
  const [enqueuedGaps, setEnqueuedGaps] = useState<Record<number, boolean>>({});

  const coveragePct = audit.coverage_percentage;

  // Determine coverage badge colors
  const getCoverageColor = (pct: number) => {
    if (pct >= 80) return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30';
    if (pct >= 50) return 'text-amber-400 bg-amber-500/10 border-amber-500/30';
    return 'text-rose-400 bg-rose-500/10 border-rose-500/30';
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority.toLowerCase()) {
      case 'high':
      case 'alta':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 px-2 py-0.5 text-[10px] font-bold uppercase">
            Alta Prioridad
          </span>
        );
      case 'medium':
      case 'media':
        return (
          <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 text-[10px] font-bold uppercase">
            Media
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded bg-slate-800 text-slate-300 border border-slate-700 px-2 py-0.5 text-[10px] font-bold uppercase">
            Baja
          </span>
        );
    }
  };

  const handleToggleGapStatus = async (idx: number, currentStatus: CoverageGapStatus) => {
    const nextStatus: CoverageGapStatus =
      currentStatus === 'resolved' ? 'pending' : 'resolved';

    // Optimistic update
    const updatedGaps = [...audit.orphan_gaps];
    updatedGaps[idx] = {
      ...updatedGaps[idx],
      status: nextStatus,
    };

    const updatedAudit: TopicCoverageAuditResponse = {
      ...audit,
      orphan_gaps: updatedGaps,
    };

    onAuditUpdated?.(updatedAudit);

    if (audit.audit_id) {
      setUpdatingGapIndex(idx);
      try {
        await api.updateGapStatus(audit.audit_id, idx, nextStatus, undefined, apiKey);
      } catch (err) {
        console.error('Failed to persist gap status update:', err);
        // Rollback on failure
        updatedGaps[idx] = {
          ...updatedGaps[idx],
          status: currentStatus,
        };
        onAuditUpdated?.({
          ...audit,
          orphan_gaps: updatedGaps,
        });
      } finally {
        setUpdatingGapIndex(null);
      }
    }
  };

  const handleEnqueue = (gap: OrphanGap, idx: number) => {
    onEnqueueGap?.(gap);
    setEnqueuedGaps((prev) => ({ ...prev, [idx]: true }));
  };

  const filteredGaps = audit.orphan_gaps.map((gap, idx) => ({ gap, idx })).filter(({ gap }) => {
    if (gapFilter === 'pending') return gap.status !== 'resolved';
    if (gapFilter === 'resolved') return gap.status === 'resolved';
    return true;
  });

  const pendingCount = audit.orphan_gaps.filter((g) => g.status !== 'resolved').length;
  const resolvedCount = audit.orphan_gaps.filter((g) => g.status === 'resolved').length;

  return (
    <div className="space-y-6">
      {/* Metric Header Card */}
      <div className="relative overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 via-slate-900/90 to-indigo-950/30 p-5 sm:p-6 shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1.5 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-mono text-[11px] font-bold text-indigo-400 bg-indigo-950/60 px-2 py-0.5 rounded border border-indigo-900/50">
                {deckName}
              </span>
              {audit.audit_id && (
                <span className="font-mono text-[10px] text-slate-400 bg-slate-800/80 px-1.5 py-0.5 rounded border border-slate-700">
                  Auditoría #{audit.audit_id}
                </span>
              )}
              {audit.created_at && (
                <span className="inline-flex items-center gap-1 text-[10px] text-slate-400">
                  <Calendar className="h-3 w-3" />
                  {new Date(audit.created_at).toLocaleDateString()}
                </span>
              )}
            </div>
            <h2 className="text-xl sm:text-2xl font-black text-white tracking-tight break-words">
              {audit.topic}
            </h2>
          </div>

          {/* Coverage Percentage Badge */}
          <div className="flex items-center gap-3 shrink-0">
            <div
              className={`flex flex-col items-center justify-center rounded-2xl border px-4 py-2 text-center backdrop-blur-md ${getCoverageColor(
                coveragePct
              )}`}
            >
              <span className="text-2xl sm:text-3xl font-extrabold tracking-tight">
                {coveragePct}%
              </span>
              <span className="text-[10px] font-bold uppercase tracking-wider">
                Cobertura Temática
              </span>
            </div>
          </div>
        </div>

        {/* Linear Progress Bar */}
        <div className="mt-5 space-y-1.5">
          <div className="flex justify-between text-xs text-slate-400">
            <span>Progreso de dominio curricular</span>
            <span className="font-semibold text-slate-200">
              {audit.covered_facets.length} facetas cubiertas • {pendingCount} brechas pendientes
            </span>
          </div>
          <div className="h-2.5 w-full rounded-full bg-slate-800/80 overflow-hidden p-0.5 border border-slate-700/50">
            <div
              className={`h-full rounded-full transition-all duration-700 ${
                coveragePct >= 80
                  ? 'bg-gradient-to-r from-emerald-500 to-teal-400 shadow-sm shadow-emerald-500/50'
                  : coveragePct >= 50
                  ? 'bg-gradient-to-r from-amber-500 to-yellow-400 shadow-sm shadow-amber-500/50'
                  : 'bg-gradient-to-r from-rose-500 to-pink-500 shadow-sm shadow-rose-500/50'
              }`}
              style={{ width: `${Math.max(4, Math.min(100, coveragePct))}%` }}
            />
          </div>
        </div>

        {/* Pedagogical Assessment Banner */}
        {audit.summary_assessment && (
          <div className="mt-5 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-4 backdrop-blur-sm flex items-start gap-3">
            <Sparkles className="h-5 w-5 text-indigo-400 shrink-0 mt-0.5" />
            <div className="space-y-1 text-xs sm:text-sm">
              <span className="font-bold text-indigo-300">Diagnóstico Pedagógico de Cobertura:</span>
              <p className="text-slate-200 leading-relaxed">
                {audit.summary_assessment}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Section 1: Covered Facets */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              <ShieldCheck className="h-3.5 w-3.5" />
            </div>
            <h3 className="text-sm font-bold text-white tracking-wide">
              🟢 Facetas Cubiertas ({audit.covered_facets.length})
            </h3>
          </div>
          <span className="text-[11px] text-slate-400">
            Conceptos ya representados por tarjetas activas en tu mazo
          </span>
        </div>

        {audit.covered_facets.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-center text-xs text-slate-400">
            No se detectaron notas que cubran facetas de este tema en el mazo aún.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {audit.covered_facets.map((facet, idx) => (
              <div
                key={idx}
                className="flex flex-col justify-between rounded-xl border border-emerald-500/30 bg-emerald-950/10 p-3.5 hover:border-emerald-500/50 transition-all space-y-2"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <h4 className="text-xs font-bold text-emerald-300">
                      {facet.facet}
                    </h4>
                    {facet.quality_score && (
                      <span className="shrink-0 text-[10px] font-mono font-semibold text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/40">
                        {Math.round(facet.quality_score * 100)}% calidad
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-[11px] text-slate-300 leading-relaxed">
                    {facet.description}
                  </p>
                </div>

                {facet.matched_note_ids && facet.matched_note_ids.length > 0 && (
                  <div className="pt-2 border-t border-emerald-500/20 flex items-center gap-1.5 flex-wrap">
                    <span className="text-[10px] text-slate-400 font-medium">
                      Tarjetas:
                    </span>
                    {facet.matched_note_ids.map((nid) => (
                      <span
                        key={nid}
                        className="font-mono text-[10px] font-bold text-emerald-300 bg-slate-900/90 px-1.5 py-0.5 rounded border border-emerald-600/40 shadow-xs"
                      >
                        Nota #{nid}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Section 2: Orphan Gaps Checklist */}
      <div className="space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/30">
              <AlertCircle className="h-3.5 w-3.5" />
            </div>
            <h3 className="text-sm font-bold text-white tracking-wide">
              🔴 Brechas Cognitivas Huérfanas ({audit.orphan_gaps.length})
            </h3>
          </div>

          {/* Filter Bar */}
          <div className="flex items-center gap-1 bg-slate-900/90 p-1 rounded-xl border border-slate-800 text-[11px]">
            <button
              type="button"
              onClick={() => setGapFilter('all')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                gapFilter === 'all'
                  ? 'bg-slate-700 text-white font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Todas ({audit.orphan_gaps.length})
            </button>
            <button
              type="button"
              onClick={() => setGapFilter('pending')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                gapFilter === 'pending'
                  ? 'bg-rose-600/80 text-white font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Pendientes ({pendingCount})
            </button>
            <button
              type="button"
              onClick={() => setGapFilter('resolved')}
              className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                gapFilter === 'resolved'
                  ? 'bg-emerald-600/80 text-white font-bold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Resueltas ({resolvedCount})
            </button>
          </div>
        </div>

        {filteredGaps.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center text-xs text-slate-400 space-y-2">
            <CheckCircle2 className="h-8 w-8 text-emerald-400 mx-auto opacity-80" />
            <p className="font-semibold text-slate-300">
              {gapFilter === 'pending'
                ? '¡Excelente! No hay brechas pendientes en esta auditoría.'
                : 'No se encontraron brechas para este filtro.'}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredGaps.map(({ gap, idx }) => {
              const isResolved = gap.status === 'resolved';
              const isUpdating = updatingGapIndex === idx;
              const isEnqueued = enqueuedGaps[idx];

              return (
                <div
                  key={idx}
                  className={`group rounded-xl border p-4 transition-all duration-200 ${
                    isResolved
                      ? 'border-emerald-500/30 bg-emerald-950/10 opacity-70 hover:opacity-100'
                      : 'border-rose-500/30 bg-rose-950/15 hover:border-rose-500/50 shadow-sm'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {/* Checkbox */}
                    <button
                      type="button"
                      disabled={isUpdating}
                      aria-pressed={isResolved}
                      aria-label={isResolved ? 'Marcar brecha como pendiente' : 'Marcar brecha como resuelta'}
                      onClick={() => handleToggleGapStatus(idx, gap.status)}
                      className={`mt-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all ${
                        isResolved
                          ? 'border-emerald-500 bg-emerald-500 text-white'
                          : 'border-slate-600 bg-slate-900 hover:border-rose-400'
                      }`}
                      title={isResolved ? 'Marcar como pendiente' : 'Marcar como resuelta'}
                    >
                      {isUpdating ? (
                        <Loader2 className="h-3 w-3 animate-spin text-rose-300" />
                      ) : isResolved ? (
                        <Check className="h-3.5 w-3.5 stroke-[3]" />
                      ) : null}
                    </button>

                    {/* Gap Body */}
                    <div className="flex-1 min-w-0 space-y-2">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4
                            className={`text-sm font-bold ${
                              isResolved
                                ? 'line-through text-slate-400'
                                : 'text-slate-100'
                            }`}
                          >
                            {gap.gap_title}
                          </h4>
                          {getPriorityBadge(gap.priority)}
                          <span
                            className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
                              isResolved
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                                : gap.status === 'in_curation'
                                ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30'
                                : 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                            }`}
                          >
                            {isResolved
                              ? 'Resuelto'
                              : gap.status === 'in_curation'
                              ? 'En Curación'
                              : 'Pendiente'}
                          </span>
                        </div>
                      </div>

                      {/* Diagnostic Reason */}
                      <p className="text-xs text-slate-300 leading-relaxed">
                        {gap.reason}
                      </p>

                      {/* Suggested Atomic Question Card Preview */}
                      {gap.suggested_front && (
                        <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-3 space-y-1">
                          <div className="flex items-center gap-1.5 text-[10px] font-bold text-amber-400 uppercase tracking-wider">
                            <Sparkles className="h-3 w-3" />
                            <span>Pregunta Atómica Sugerida:</span>
                          </div>
                          <p className="font-mono text-xs text-slate-200 italic">
                            "{gap.suggested_front}"
                          </p>
                        </div>
                      )}

                      {/* Action Buttons */}
                      <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-800/80 flex-wrap">
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleEnqueue(gap, idx)}
                            disabled={isEnqueued || isResolved}
                            className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-all active:scale-95 shadow-sm ${
                              isEnqueued
                                ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 cursor-default'
                                : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600'
                            }`}
                            title="Agregar esta brecha a la cola de curación para resolverla más tarde"
                          >
                            <BookmarkPlus className="h-3.5 w-3.5 text-indigo-400" />
                            <span>{isEnqueued ? '✓ Encolada' : '📌 Encolar en Cola de Curación'}</span>
                          </button>

                          {onGenerateFromGap && (
                            <button
                              type="button"
                              onClick={() => onGenerateFromGap(gap)}
                              disabled={isResolved}
                              className="inline-flex items-center gap-1 rounded-lg bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 px-3 py-1.5 text-xs font-bold text-white transition-all active:scale-95 shadow-md shadow-amber-600/20 disabled:opacity-50"
                              title="Generar tarjeta de inmediato para cubrir esta brecha cognitiva"
                            >
                              <Zap className="h-3.5 w-3.5" />
                              <span>⚡ Generar Tarjeta</span>
                              <ArrowRight className="h-3 w-3 opacity-80" />
                            </button>
                          )}
                        </div>

                        <span className="text-[10px] text-slate-400">
                          {isResolved ? 'Marcado como dominado' : 'Requiere creación en Anki'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
