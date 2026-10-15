import React, { useState, useEffect, useRef } from 'react';
import {
  Brain,
  CheckCircle2,
  AlertTriangle,
  Search,
  Sparkles,
  Loader2,
  X,
  Layers,
  Plus,
  Minus,
  RefreshCw,
  Zap,
  Eye,
  Tag,
} from 'lucide-react';
import type { StudyPlanInspection, DeckNoteRecord } from '../types';
import { api, rewriteMediaUrlsForWeb } from '../services/api';
import { useModalEscape } from '../utils/useModalEscape';

interface MaterialInspectionCockpitProps {
  inspection: StudyPlanInspection;
  onClose: () => void;
  onConfirmGenerate: (approvedInspection: StudyPlanInspection) => void;
  isGeneratingCards: boolean;
  onUpdateInspection?: (updated: StudyPlanInspection) => void;
  onOpenDeckStudio?: (topic?: string, initialTab?: 'checklist' | 'dag' | 'debt' | 'duplicates' | 'expansion') => void;
  deckName?: string;
  apiKey?: string;
}

export const MaterialInspectionCockpit: React.FC<MaterialInspectionCockpitProps> = ({
  inspection: initialInspection,
  onClose,
  onConfirmGenerate,
  isGeneratingCards,
  onUpdateInspection,
  onOpenDeckStudio,
  deckName = 'General',
  apiKey,
}) => {
  const [inspection, setInspection] = useState<StudyPlanInspection>(() => ({
    ...initialInspection,
    prerequisites: (initialInspection.prerequisites || []).map((p) => ({ ...p, selected: false })),
  }));
  const [isSyncingDeck, setIsSyncingDeck] = useState<boolean>(false);
  const [isMatchingPrereqs, setIsMatchingPrereqs] = useState<boolean>(false);
  const [deckStats, setDeckStats] = useState<{ total_indexed: number; last_indexed_at?: string } | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  // Source Note Viewer State
  const [sourceNote, setSourceNote] = useState<DeckNoteRecord | null>(null);
  const [isLoadingSourceNote, setIsLoadingSourceNote] = useState<boolean>(false);
  const [isSourceNoteOpen, setIsSourceNoteOpen] = useState<boolean>(false);
  const [sourceNoteError, setSourceNoteError] = useState<string | null>(null);

  const handleToggleSourceNote = async () => {
    if (isSourceNoteOpen) {
      setIsSourceNoteOpen(false);
      return;
    }
    setIsSourceNoteOpen(true);
    if (!sourceNote && inspection.source_note_id) {
      setIsLoadingSourceNote(true);
      setSourceNoteError(null);
      try {
        const note = await api.getNoteById(inspection.source_note_id);
        setSourceNote(note);
      } catch (err: any) {
        setSourceNoteError(err.message || 'No se pudo cargar el contenido de la tarjeta original.');
      } finally {
        setIsLoadingSourceNote(false);
      }
    }
  };

  // Helper to update both local state and parent state in real time
  const updateInspection = (updater: (prev: StudyPlanInspection) => StudyPlanInspection) => {
    setInspection((prev) => {
      const next = updater(prev);
      queueMicrotask(() => {
        onUpdateInspection?.(next);
      });
      return next;
    });
  };

  const latestPropsRef = useRef({ initialInspection, onUpdateInspection });
  useEffect(() => {
    latestPropsRef.current = { initialInspection, onUpdateInspection };
  }, [initialInspection, onUpdateInspection]);

  // Load deck status and automatically match prerequisites and themes in parallel
  useEffect(() => {
    let isMounted = true;
    const loadStatusAndMatch = async () => {
      const currentInit = latestPropsRef.current.initialInspection;
      const hasUnmatchedPrereqs =
        currentInit.prerequisites.length > 0 &&
        currentInit.prerequisites.some((p) => !p.match_info);
      const hasUnmatchedThemes =
        currentInit.core_themes.length > 0 &&
        currentInit.core_themes.some((t) => !t.match_info);
      const shouldMatch = hasUnmatchedPrereqs || hasUnmatchedThemes;
      const excludeIds = initialInspection.source_note_id ? [initialInspection.source_note_id] : [];

      if (shouldMatch) {
        setIsMatchingPrereqs(true);
      }

      try {
        const [statusRes, matchRes] = await Promise.allSettled([
          api.getDeckIndexStatus(deckName),
          shouldMatch
            ? api.matchStudyPlan(
                deckName,
                currentInit.prerequisites,
                currentInit.core_themes,
                apiKey,
                excludeIds,
                currentInit.source_note_id
              )
            : Promise.resolve(null),
        ]);
        if (!isMounted) return;

        if (statusRes.status === 'fulfilled' && statusRes.value) {
          setDeckStats(statusRes.value);
        }

        if (
          matchRes.status === 'fulfilled' &&
          matchRes.value &&
          matchRes.value.total_indexed_notes > 0
        ) {
          const resolvedMatch = matchRes.value;
          setDeckStats((prev) =>
            prev
              ? { ...prev, total_indexed: resolvedMatch.total_indexed_notes }
              : { total_indexed: resolvedMatch.total_indexed_notes }
          );
          setInspection((prev) => {
            const updatedPrereqs = prev.prerequisites.map((p) => {
              const match = resolvedMatch.prerequisite_matches.find(
                (m) => m.concept.toLowerCase() === p.concept.toLowerCase()
              );
              if (match) {
                const shouldSelect = match.status === 'dominated' ? false : p.selected;
                return { ...p, match_info: match, selected: shouldSelect };
              }
              return p;
            });

            const updatedThemes = prev.core_themes.map((t) => {
              const match = resolvedMatch.theme_matches.find(
                (m) => m.concept.toLowerCase() === t.title.toLowerCase()
              );
              if (match) {
                const isDominated = match.status === 'dominated';
                return {
                  ...t,
                  match_info: match,
                  selected: isDominated ? false : t.selected,
                  recommended_cards: isDominated ? 0 : t.recommended_cards,
                };
              }
              return t;
            });

            const next = { ...prev, prerequisites: updatedPrereqs, core_themes: updatedThemes };
            queueMicrotask(() => {
              latestPropsRef.current.onUpdateInspection?.(next);
            });
            return next;
          });
        }
      } catch (err) {
        console.warn('Could not auto-match study plan against deck:', err);
      } finally {
        if (isMounted) setIsMatchingPrereqs(false);
      }
    };

    void loadStatusAndMatch();
    return () => {
      isMounted = false;
    };
  }, [deckName, initialInspection.source_note_id, apiKey]);

  const handleSyncDeck = async () => {
    setIsSyncingDeck(true);
    setSyncMessage(null);
    try {
      const res = await api.syncDeckIndex(deckName, apiKey);
      setDeckStats({ total_indexed: res.total_notes });
      setSyncMessage(`Indexadas ${res.newly_indexed} notas nuevas (${res.total_notes} total) en ${res.duration_seconds}s.`);

      // Immediately re-run semantic match with freshly indexed deck for both prereqs and themes
      setIsMatchingPrereqs(true);
      const excludeIds = inspection.source_note_id ? [inspection.source_note_id] : [];
      const matchRes = await api.matchStudyPlan(
        deckName,
        inspection.prerequisites,
        inspection.core_themes,
        apiKey,
        excludeIds,
        inspection.source_note_id
      );
      updateInspection((prev) => {
        const updatedPrereqs = prev.prerequisites.map((p) => {
          const match = matchRes.prerequisite_matches.find(
            (m) => m.concept.toLowerCase() === p.concept.toLowerCase()
          );
          if (match) {
            const shouldSelect = match.status === 'dominated' ? false : p.selected;
            return { ...p, match_info: match, selected: shouldSelect };
          }
          return p;
        });

        const updatedThemes = prev.core_themes.map((t) => {
          const match = matchRes.theme_matches.find(
            (m) => m.concept.toLowerCase() === t.title.toLowerCase()
          );
          if (match) {
            const isDominated = match.status === 'dominated';
            return {
              ...t,
              match_info: match,
              selected: isDominated ? false : t.selected,
              recommended_cards: isDominated ? 0 : t.recommended_cards,
            };
          }
          return t;
        });

        return { ...prev, prerequisites: updatedPrereqs, core_themes: updatedThemes };
      });
    } catch (err: any) {
      setSyncMessage(`Error de sincronización: ${err.message || 'Desconocido'}`);
    } finally {
      setIsSyncingDeck(false);
      setIsMatchingPrereqs(false);
    }
  };

  const handleMatchPrerequisites = async () => {
    setIsMatchingPrereqs(true);
    setSyncMessage(null);
    try {
      const excludeIds = inspection.source_note_id ? [inspection.source_note_id] : [];
      const matchRes = await api.matchStudyPlan(
        deckName,
        inspection.prerequisites,
        inspection.core_themes,
        apiKey,
        excludeIds,
        inspection.source_note_id
      );
      setDeckStats((prev) =>
        prev
          ? { ...prev, total_indexed: matchRes.total_indexed_notes }
          : { total_indexed: matchRes.total_indexed_notes }
      );
      updateInspection((prev) => {
        const updatedPrereqs = prev.prerequisites.map((p) => {
          const match = matchRes.prerequisite_matches.find(
            (m) => m.concept.toLowerCase() === p.concept.toLowerCase()
          );
          if (match) {
            const shouldSelect = match.status === 'dominated' ? false : p.selected;
            return { ...p, match_info: match, selected: shouldSelect };
          }
          return p;
        });

        const updatedThemes = prev.core_themes.map((t) => {
          const match = matchRes.theme_matches.find(
            (m) => m.concept.toLowerCase() === t.title.toLowerCase()
          );
          if (match) {
            const isDominated = match.status === 'dominated';
            return {
              ...t,
              match_info: match,
              selected: isDominated ? false : t.selected,
              recommended_cards: isDominated ? 0 : t.recommended_cards,
            };
          }
          return t;
        });

        return { ...prev, prerequisites: updatedPrereqs, core_themes: updatedThemes };
      });
    } catch (err: any) {
      setSyncMessage(`Error al comparar con mazo: ${err.message || 'Desconocido'}`);
    } finally {
      setIsMatchingPrereqs(false);
    }
  };

  // Toggle core theme selection
  const handleToggleTheme = (themeId: string) => {
    updateInspection((prev) => ({
      ...prev,
      core_themes: prev.core_themes.map((t) => {
        if (t.id === themeId) {
          const willSelect = !t.selected;
          const newRecommended = willSelect && t.recommended_cards === 0 ? 2 : t.recommended_cards;
          return { ...t, selected: willSelect, recommended_cards: newRecommended };
        }
        return t;
      }),
    }));
  };

  // Adjust recommended cards for a theme (allows 0)
  const handleAdjustThemeCards = (themeId: string, delta: number) => {
    updateInspection((prev) => ({
      ...prev,
      core_themes: prev.core_themes.map((t) => {
        if (t.id === themeId) {
          const newCount = Math.max(0, Math.min(15, t.recommended_cards + delta));
          return { ...t, recommended_cards: newCount, selected: newCount > 0 };
        }
        return t;
      }),
    }));
  };

  // Calculate totals
  const selectedThemesCount = inspection.core_themes.filter((t) => t.selected).length;
  const themeCardsTotal = inspection.core_themes
    .filter((t) => t.selected)
    .reduce((sum, t) => sum + t.recommended_cards, 0);

  const grandTotalCards = themeCardsTotal;

  // Self-sufficiency styling
  const score = inspection.self_sufficiency_score;
  const scoreColor =
    score >= 80
      ? 'text-emerald-400 border-emerald-500/40 bg-emerald-950/30'
      : score >= 50
      ? 'text-amber-400 border-amber-500/40 bg-amber-950/30'
      : 'text-rose-400 border-rose-500/40 bg-rose-950/30';

  // Close modal and ensure parent has latest state
  const handleCloseModal = () => {
    onUpdateInspection?.(inspection);
    onClose();
  };

  useModalEscape(true, handleCloseModal, isGeneratingCards);

  // Toggle diagram association for a theme
  const handleToggleThemeDiagram = (themeId: string, diagramName: string) => {
    updateInspection((prev) => {
      const updatedThemes = prev.core_themes.map((t) => {
        if (t.id !== themeId) return t;
        const currentDiags = t.associated_diagrams || [];
        const hasDiag = currentDiags.includes(diagramName);
        const nextDiags = hasDiag
          ? currentDiags.filter((d) => d !== diagramName)
          : [...currentDiags, diagramName];
        return { ...t, associated_diagrams: nextDiags };
      });
      return { ...prev, core_themes: updatedThemes };
    });
  };

  // Finalize plan before generation (H-03 Zero Debt Deletion: ONLY source_note_id may be retired)
  const handleApproveInspection = () => {
    const obsoleteIds: number[] = [];
    const mediaFiles: string[] = [];

    // Include ONLY the source note if marked to be retired
    if (
      inspection.source_note_id &&
      (inspection.obsolete_note_ids?.includes(inspection.source_note_id) ?? true)
    ) {
      obsoleteIds.push(inspection.source_note_id);
    }
    if (inspection.inherited_media_files && inspection.inherited_media_files.length > 0) {
      mediaFiles.push(...inspection.inherited_media_files);
    }

    // Media files from themes can still be collected into inherited_media_files
    inspection.prerequisites.forEach((p) => {
      if (p.match_info?.media_files && p.match_info.media_files.length > 0) {
        mediaFiles.push(...p.match_info.media_files);
      }
    });

    inspection.core_themes.forEach((t) => {
      if (t.match_info?.media_files && t.match_info.media_files.length > 0) {
        mediaFiles.push(...t.match_info.media_files);
      }
      if (t.associated_diagrams && t.associated_diagrams.length > 0) {
        mediaFiles.push(...t.associated_diagrams);
      }
    });

    const finalizedInspection: StudyPlanInspection = {
      ...inspection,
      obsolete_note_ids: Array.from(new Set(obsoleteIds)),
      inherited_media_files: Array.from(new Set(mediaFiles)),
    };

    onUpdateInspection?.(finalizedInspection);
    onConfirmGenerate(finalizedInspection);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="material-inspection-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-3 sm:p-4 backdrop-blur-md animate-fade-in"
    >
      <div className="relative flex max-h-[92vh] h-full sm:h-auto w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/95 shadow-2xl shadow-indigo-950/50">
        {/* Top Header */}
        <div className="shrink-0 flex items-center justify-between border-b border-slate-800 px-6 py-4 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/30 text-indigo-400">
              <Brain className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h2 id="material-inspection-modal-title" className="text-base font-bold text-white tracking-wide">
                  Diagnóstico Cognitivo & Andamiaje
                </h2>
                <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 border border-indigo-500/30">
                  Pre-Flight Cockpit
                </span>
                {/* Engine Telemetry Badge */}
                {inspection.provider_used === 'gemini' && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-cyan-500/15 border border-cyan-500/30 px-2 py-0.5 text-[10px] font-semibold text-cyan-300"
                    title={`Motor principal: ${inspection.model_used || 'Gemini 3.8 Flash'}`}
                  >
                    ⚡ Gemini 3.8 Flash
                  </span>
                )}
                {inspection.provider_used === 'nvidia' && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-300"
                    title={`Motor NVIDIA NIM: ${inspection.model_used || 'Llama 3.2 90B Vision'}`}
                  >
                    🛡️ NVIDIA NIM (Llama 3.2 90B)
                  </span>
                )}
                {inspection.provider_used === 'groq' && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 text-[10px] font-semibold text-amber-300"
                    title={`Motor Groq LPU: ${inspection.model_used || 'Qwen 3.8 27B / Llama 70B'}`}
                  >
                    ⚡ Groq LPU (Ultra-rápido)
                  </span>
                )}
                {inspection.provider_used === 'openrouter' && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-purple-500/15 border border-purple-500/30 px-2 py-0.5 text-[10px] font-semibold text-purple-300"
                    title={`Motor OpenRouter: ${inspection.model_used || 'openrouter/free'}`}
                  >
                    🌐 OpenRouter Free
                  </span>
                )}
                {inspection.fallback_occurred && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full bg-amber-500/20 border border-amber-500/40 px-2 py-0.5 text-[10px] font-bold text-amber-300"
                    title={`Conmutación por Fallback ejecutada: ${inspection.fallback_chain?.join(' -> ') || 'Cadena de contingencia activada'}`}
                  >
                    ⚠️ Conmutación por Fallback
                  </span>
                )}
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-indigo-500/15 border border-indigo-500/30 px-2 py-0.5 text-[10px] font-semibold text-indigo-300"
                  title="Estructura curricular acíclica calculada por teoría de grafos (NetworkX)"
                >
                  🌐 Grafo Acíclico (DAG)
                </span>
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 text-[10px] font-semibold text-emerald-300"
                  title="Reducción transitiva activa: atajos redundantes podados para evitar saltos cognitivos"
                >
                  ✂️ Reducción Transitiva
                </span>
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-cyan-500/15 border border-cyan-500/30 px-2 py-0.5 text-[10px] font-semibold text-cyan-300"
                  title="Filtro estricto según el Contrato Pedagógico de Fase 2"
                >
                  🎯 Delimitación por Contrato
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Auditoría curricular, atomización quirúrgica y preservación de dependencias en grafo
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleCloseModal}
            aria-label="Cerrar diagnóstico cognitivo"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Topic Title & Self-Sufficiency Gauge */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/70 p-5 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-indigo-400">
                  Tema Principal Detectado
                </span>
                <h3 className="text-lg font-bold text-slate-100 mt-0.5">
                  {inspection.topic_name}
                </h3>
              </div>

              {/* Gauge Badge */}
              <div className={`flex items-center gap-2.5 rounded-xl border px-3.5 py-2 ${scoreColor}`}>
                <div className="text-right">
                  <div className="text-[10px] uppercase tracking-wider font-semibold opacity-80">
                    Autosuficiencia
                  </div>
                  <div className="text-xl font-extrabold">{score}%</div>
                </div>
              </div>
            </div>

            {/* Verdict Explanation */}
            <div className="rounded-lg bg-slate-900/90 border border-slate-800/80 p-3 flex items-start gap-2.5">
              <AlertTriangle
                className={`h-4 w-4 shrink-0 mt-0.5 ${
                  score >= 80 ? 'text-emerald-400' : score >= 50 ? 'text-amber-400' : 'text-rose-400'
                }`}
              />
              <p className="text-xs text-slate-300 leading-relaxed">
                <span className="font-semibold text-slate-100">Diagnóstico Pedagógico: </span>
                {inspection.self_sufficiency_verdict}
              </p>
            </div>
          </div>

          {/* Origin Note Header Card (Alternativa 1) */}
          {inspection.source_note_id && (
            <div className="rounded-xl border border-indigo-500/40 bg-indigo-950/20 p-4 space-y-3 shadow-sm animate-fade-in">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                <div className="flex items-center gap-2.5">
                  <div className="p-1.5 rounded-lg bg-indigo-500/20 border border-indigo-500/30 text-indigo-400">
                    <Brain className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-white">
                        🔬 Tarjeta Original en Análisis: Nota #{inspection.source_note_id}
                      </span>
                      <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold text-indigo-300 border border-indigo-500/30">
                        Tarjeta Origen
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Esta nota ha sido excluida de la búsqueda semántica interna para evitar falsos positivos con ella misma.
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
                  {inspection.inherited_media_files && inspection.inherited_media_files.length > 0 && (
                    <span
                      className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500/20 px-2.5 py-1 text-xs font-semibold text-amber-300 border border-amber-500/40"
                      title="Las imágenes de la tarjeta original serán transferidas a las nuevas flashcards atómicas"
                    >
                      🖼️ {inspection.inherited_media_files.length} imagen(es)
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={handleToggleSourceNote}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/40 bg-indigo-900/40 hover:bg-indigo-800/60 px-2.5 py-1 text-xs font-semibold text-indigo-200 hover:text-white transition-all cursor-pointer"
                    title="Ver campos completos y contenido multimedia de la tarjeta original"
                  >
                    <Eye className="h-3.5 w-3.5 text-indigo-400" />
                    <span>{isSourceNoteOpen ? 'Ocultar original' : '👁️ Ver contenido original'}</span>
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2 rounded-lg bg-indigo-950/60 border border-indigo-500/30 px-3 py-2 text-[11px] text-indigo-200">
                <Sparkles className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                <span>
                  <strong>Fase 3 (Saneamiento Quirúrgico):</strong> Los ejes temáticos internos serán atomizados en tarjetas hermanas. Los prerrequisitos externos detectados se archivarán como brechas huérfanas en el grafo del mazo para la Fase 4.
                </span>
              </div>

              {/* Collapsible Source Note Content Viewer */}

              {isSourceNoteOpen && (
                <div className="rounded-xl border border-slate-700/80 bg-slate-900/90 p-4 space-y-3 animate-fade-in text-xs">
                  {isLoadingSourceNote ? (
                    <div className="py-6 flex items-center justify-center gap-2 text-slate-400">
                      <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
                      <span>Cargando contenido original desde Anki Desktop...</span>
                    </div>
                  ) : sourceNoteError ? (
                    <div className="py-3 px-4 rounded-lg bg-rose-950/40 border border-rose-800/50 text-rose-300 flex items-center justify-between">
                      <span>{sourceNoteError}</span>
                      <button
                        type="button"
                        onClick={handleToggleSourceNote}
                        className="text-xs text-rose-400 hover:underline cursor-pointer"
                      >
                        Reintentar
                      </button>
                    </div>
                  ) : sourceNote ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-2 flex-wrap">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-white">Modelo: {sourceNote.model_name}</span>
                          <span className="text-slate-400">|</span>
                          <span className="text-slate-400">Mazo: {sourceNote.deck_name}</span>
                        </div>
                        {sourceNote.tags.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            {sourceNote.tags.map((t) => (
                              <span
                                key={t}
                                className="inline-flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300 border border-slate-700"
                              >
                                <Tag className="h-2.5 w-2.5 text-indigo-400" />
                                {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Front and Back Cards */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 space-y-1">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-300">
                            Anverso (Front)
                          </span>
                          <div
                            className="text-slate-200 leading-relaxed max-h-48 overflow-y-auto prose prose-invert prose-xs"
                            dangerouslySetInnerHTML={{
                              __html: rewriteMediaUrlsForWeb(sourceNote.front || ''),
                            }}
                          />
                        </div>

                        <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-3 space-y-1">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-300">
                            Reverso (Back)
                          </span>
                          <div
                            className="text-slate-200 leading-relaxed max-h-48 overflow-y-auto prose prose-invert prose-xs"
                            dangerouslySetInnerHTML={{
                              __html: rewriteMediaUrlsForWeb(sourceNote.back || ''),
                            }}
                          />
                        </div>
                      </div>

                      {/* Raw Fields Preview if available */}
                      {Object.keys(sourceNote.raw_fields).length > 0 && (
                        <div className="pt-2 border-t border-slate-800/80 space-y-2">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                            Campos del Modelo ({Object.keys(sourceNote.raw_fields).length}):
                          </span>
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                            {Object.entries(sourceNote.raw_fields).map(([fieldName, fieldValue]) => (
                              <div
                                key={fieldName}
                                className="rounded-md border border-slate-800/80 bg-slate-950/40 p-2 text-[11px]"
                              >
                                <span className="font-semibold text-indigo-300 block mb-0.5">
                                  {fieldName}
                                </span>
                                <div
                                  className="text-slate-300 line-clamp-4 overflow-y-auto prose prose-invert prose-xs"
                                  dangerouslySetInnerHTML={{
                                    __html: rewriteMediaUrlsForWeb(fieldValue),
                                  }}
                                />
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
              )}

              {/* Single clean toggle for retiring source note */}
              <div className="rounded-lg bg-slate-900/90 border border-slate-800 p-2.5 flex items-center justify-between gap-3">
                <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-200 font-medium">
                  <input
                    type="checkbox"
                    checked={inspection.obsolete_note_ids?.includes(inspection.source_note_id) ?? true}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      updateInspection((prev) => {
                        const current = prev.obsolete_note_ids || [];
                        const next = checked
                          ? Array.from(new Set([...current, inspection.source_note_id!]))
                          : current.filter((id) => id !== inspection.source_note_id);
                        return { ...prev, obsolete_note_ids: next };
                      });
                    }}
                    className="h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                  />
                  <span>
                    Retirar esta nota original de Anki al exportar las nuevas tarjetas atómicas
                  </span>
                </label>
                <span className="text-[10px] text-slate-400 hidden sm:inline">
                  (Reemplazo atómico limpio)
                </span>
              </div>
            </div>
          )}

          {/* Section 1: Prerequisites & Missing Foundations (Read-Only DAG Preservation) */}
          <div className="space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
              <div className="flex items-center gap-2">
                <Layers className="h-4 w-4 text-cyan-400" />
                <h4 className="text-sm font-bold text-slate-100">
                  Prerrequisitos & Dependencias Causal-Pedagógicas
                </h4>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300 font-medium">
                  {inspection.prerequisites.length} en DAG
                </span>
              </div>

              {/* Semantic Deck Intelligence Controls */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-medium text-slate-300 border border-slate-700/80">
                  <Zap className="h-3 w-3 text-cyan-400" />
                  <span>Índice Semántico: <strong className="text-slate-100">{deckName}</strong> ({deckStats?.total_indexed ?? 0} notas)</span>
                </span>
                <button
                  type="button"
                  onClick={handleSyncDeck}
                  disabled={isSyncingDeck}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600/20 px-2.5 py-1 text-[11px] font-semibold text-indigo-300 border border-indigo-500/40 hover:bg-indigo-600/30 transition-all disabled:opacity-50"
                  title="Sincronizar e indexar vectorialmente las notas de este mazo de Anki"
                >
                  <RefreshCw className={`h-3 w-3 ${isSyncingDeck ? 'animate-spin text-indigo-400' : ''}`} />
                  <span>{isSyncingDeck ? 'Sincronizando...' : 'Sincronizar Mazo'}</span>
                </button>
                <button
                  type="button"
                  onClick={handleMatchPrerequisites}
                  disabled={isMatchingPrereqs || isSyncingDeck}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-purple-600/20 px-2.5 py-1 text-[11px] font-semibold text-purple-300 border border-purple-500/40 hover:bg-purple-600/30 transition-all disabled:opacity-50"
                  title="Auditar semánticamente qué prerrequisitos ya tienen cobertura en tu mazo"
                >
                  <Search className={`h-3 w-3 ${isMatchingPrereqs ? 'animate-spin text-purple-400' : ''}`} />
                  <span>{isMatchingPrereqs ? 'Analizando...' : 'Auditar Cobertura'}</span>
                </button>
              </div>
            </div>

            {/* Informational Banner: Strict Phase Separation */}
            <div className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-3.5 flex items-start gap-3 text-xs text-cyan-200">
              <Sparkles className="h-4 w-4 text-cyan-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <span className="font-bold text-white">Separación Estricta de Fases & Compilación Curricular: </span>
                <p className="leading-relaxed text-slate-300">
                  Estos prerrequisitos fueron identificados como dependencias causales y registrados en el <strong>Grafo del Mazo (DAG)</strong>. En esta <strong>Fase 3</strong> atomizamos exclusivamente el contenido de la tarjeta en pantalla. Para no desordenar el currículo, <strong>no se generan tarjetas de prerrequisitos en este lote</strong>; se archivan automáticamente como nodos huérfanos que serán expandidos en orden topológico durante la <strong>Fase 4 (Expansión Topológica)</strong>.
                </p>
              </div>
            </div>

            {syncMessage && (
              <div className="rounded-lg bg-indigo-950/40 border border-indigo-500/30 px-3 py-1.5 text-xs text-indigo-300 flex items-center justify-between">
                <span>{syncMessage}</span>
                <button
                  type="button"
                  onClick={() => setSyncMessage(null)}
                  aria-label="Cerrar mensaje de sincronización"
                  className="text-slate-400 hover:text-slate-200"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}

            {inspection.prerequisites.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/40 p-5 text-center text-xs text-slate-400 space-y-1">
                <CheckCircle2 className="h-5 w-5 text-emerald-400 mx-auto" />
                <p className="font-semibold text-slate-300">Sin prerrequisitos externos requeridos</p>
                <p className="text-[11px] text-slate-400">
                  El material es pedagógicamente autosuficiente para este lote de tarjetas.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {inspection.prerequisites.map((prereq, pIdx) => (
                  <div
                    key={prereq.id || prereq.concept || pIdx}
                    className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-4 space-y-2 transition-all"
                  >
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Tag className="h-3.5 w-3.5 text-cyan-400 shrink-0" />
                        <span className="text-xs font-bold text-white">{prereq.concept}</span>
                        {prereq.match_info ? (
                          prereq.match_info.status === 'dominated' ? (
                            <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/30">
                              🟢 Cubierto en tu mazo (Nota #{prereq.match_info.matched_note_id})
                            </span>
                          ) : (
                            <span className="rounded bg-amber-500/15 px-2 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-500/30">
                              🔴 Brecha huérfana en DAG (Se expandirá en Fase 4)
                            </span>
                          )
                        ) : (
                          <span className="rounded bg-cyan-500/15 px-2 py-0.5 text-[10px] font-semibold text-cyan-300 border border-cyan-500/30">
                            📌 Registrado en DAG (Fase 4)
                          </span>
                        )}
                      </div>

                      {onOpenDeckStudio && (
                        <button
                          type="button"
                          onClick={() => onOpenDeckStudio(prereq.concept, 'dag')}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/35 text-indigo-300 border border-indigo-500/40 px-2.5 py-1 text-[10px] font-semibold transition-all hover:scale-105 active:scale-95 shadow-xs cursor-pointer"
                          title="Ver nodo / brecha huérfana en el Grafo DAG"
                        >
                          <Search className="h-3 w-3 text-indigo-400" />
                          <span>Ver en Grafo</span>
                        </button>
                      )}
                    </div>

                    <p className="text-xs text-slate-300 leading-relaxed pl-5">
                      <span className="text-slate-400 font-medium">Justificación causal: </span>
                      {prereq.reason}
                    </p>

                    {prereq.match_info?.matched_note_front && (
                      <div className="ml-5 p-2 rounded-lg bg-slate-900/80 border border-slate-800 text-[11px] text-slate-300 italic">
                        Coincidencia existente: "{prereq.match_info.matched_note_front}"
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section 2: Core Themes Breakdown */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-indigo-400" />
                <h4 className="text-sm font-bold text-slate-100">
                  Ejes Temáticos del Material
                </h4>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-300 font-medium">
                  {selectedThemesCount} seleccionados
                </span>
              </div>
              <span className="text-[11px] text-slate-400 hidden sm:inline">
                Ajustá la cantidad atómica de tarjetas por subtema
              </span>
            </div>

            {inspection.core_themes.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/40 p-5 text-center text-xs text-slate-400 space-y-1">
                <Brain className="h-5 w-5 text-indigo-400 mx-auto" />
                <p className="font-semibold text-slate-300">No se desglosaron subtemas específicos</p>
                <p className="text-[11px] text-slate-400">
                  Se generarán tarjetas atómicas globales para el tema principal.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {inspection.core_themes.map((theme) => (
                <div
                  key={theme.id}
                  className={`flex flex-col justify-between rounded-xl border p-3.5 transition-all ${
                    theme.selected
                      ? 'border-indigo-500/40 bg-slate-950/70 shadow-sm'
                      : 'border-slate-800/60 bg-slate-950/30 opacity-60'
                  }`}
                >
                  <div className="space-y-2">
                    <div className="flex items-start gap-2.5">
                      <input
                        type="checkbox"
                        checked={theme.selected}
                        onChange={() => handleToggleTheme(theme.id)}
                        aria-label={`Seleccionar eje ${theme.title}`}
                        className="mt-0.5 h-4 w-4 rounded border-slate-700 bg-slate-900 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <h5 className="text-xs font-bold text-white">{theme.title}</h5>
                          {theme.match_info && (() => {
                            const isPriorTurn = theme.match_info.status === 'dominated' && (
                              theme.match_info.matched_note_front?.includes('Cubierto en turno') ||
                              theme.match_info.matched_note_front?.includes('Turno previo') ||
                              theme.match_info.matched_note_front?.includes('ledger')
                            );
                            if (isPriorTurn) {
                              return (
                                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/30">
                                  🛡️ Cubierto en turno previo
                                </span>
                              );
                            }
                            if (theme.match_info.status === 'dominated') {
                              return (
                                <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/30">
                                  🟢 Dominado en mazo
                                </span>
                              );
                            }
                            if (theme.match_info.status === 'cognitive_debt') {
                              return (
                                <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-500/30">
                                  🟡 Deuda en mazo
                                </span>
                              );
                            }
                            if (theme.match_info.status === 'complementary') {
                              return (
                                <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-300 border border-sky-500/30">
                                  🔵 Complementario
                                </span>
                              );
                            }
                            return (
                              <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300 border border-rose-500/30">
                                🔴 Nuevo en mazo
                              </span>
                            );
                          })()}
                        </div>
                        <p className="text-[11px] text-slate-400 line-clamp-2 mt-0.5">
                          {theme.description}
                        </p>

                        {/* Inherited Diagrams Assignment Controls */}
                        {inspection.inherited_media_files && inspection.inherited_media_files.length > 0 && (
                          <div className="mt-2 pt-1.5 border-t border-slate-800/60">
                            <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                              <span className="font-semibold text-slate-300">Diagramas vinculados:</span>
                              <span className="text-[9px] text-slate-500">
                                {theme.associated_diagrams?.length || 0} de {inspection.inherited_media_files.length}
                              </span>
                            </div>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              {inspection.inherited_media_files.map((diag, dIdx) => {
                                const isAssigned = theme.associated_diagrams?.includes(diag);
                                const role = theme.diagram_roles?.[diag];
                                return (
                                  <button
                                    key={dIdx}
                                    type="button"
                                    onClick={() => handleToggleThemeDiagram(theme.id, diag)}
                                    className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[10px] font-medium border transition-all cursor-pointer ${
                                      isAssigned
                                        ? 'bg-indigo-600/30 text-indigo-200 border-indigo-500/50 shadow-sm'
                                        : 'bg-slate-900/60 text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-300'
                                    }`}
                                    title={role ? `Rol funcional: ${role}` : `Alternar asignación de ${diag}`}
                                  >
                                    <span>{isAssigned ? '✓ 🖼️' : '+ 🖼️'}</span>
                                    <span className="truncate max-w-[120px]">{diag}</span>
                                    {role && (
                                      <span className="text-[9px] font-mono text-indigo-300 bg-indigo-950/60 px-1 rounded border border-indigo-800/40">
                                        {role}
                                      </span>
                                    )}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Collision & Duplicate Detection Banner */}
                    {theme.match_info && (() => {
                      const isPriorTurnCovered = theme.match_info.status === 'dominated' && (
                        theme.match_info.matched_note_front?.includes('Cubierto en turno') ||
                        theme.match_info.matched_note_front?.includes('Turno previo') ||
                        theme.match_info.matched_note_front?.includes('ledger')
                      );
                      const isOptimalCollision = !isPriorTurnCovered && (theme.match_info.status === 'dominated' || theme.match_info.quality_status === 'optimal');
                      const isCognitiveDebt = theme.match_info.status === 'cognitive_debt' || theme.match_info.quality_status === 'bad';
                      const isUnreviewedLegacy = !isPriorTurnCovered && !isOptimalCollision && !isCognitiveDebt && theme.match_info.status !== 'gap' && (theme.match_info.similarity_score ?? 0) >= 0.68;
                      const isGap = theme.match_info.status === 'gap';

                      return (
                        <div
                          className={`rounded-lg border p-2.5 text-xs transition-all ${
                            isPriorTurnCovered
                              ? 'border-emerald-500/40 bg-emerald-950/25 text-emerald-200'
                              : isOptimalCollision
                              ? 'border-amber-500/40 bg-amber-950/25 text-amber-200'
                              : isCognitiveDebt
                              ? 'border-purple-500/40 bg-purple-950/25 text-purple-200'
                              : isUnreviewedLegacy
                              ? 'border-sky-500/40 bg-sky-950/25 text-sky-200'
                              : isGap
                              ? 'border-indigo-500/40 bg-indigo-950/25 text-indigo-200'
                              : 'border-slate-800 bg-slate-900/60 text-slate-300'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1.5 flex-wrap">
                            {isPriorTurnCovered ? (
                              <span className="inline-flex items-center gap-1 rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/40">
                                🛡️ Cubierto en turno previo
                              </span>
                            ) : isOptimalCollision ? (
                              <span className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold text-amber-300 border border-amber-500/40">
                                ⚠️ Colisión con Tarjeta Ya Saneada
                              </span>
                            ) : isCognitiveDebt ? (
                              <span className="inline-flex items-center gap-1 rounded bg-purple-500/20 px-1.5 py-0.5 text-[10px] font-bold text-purple-300 border border-purple-500/40">
                                🔄 Absorción de Deuda Cognitiva
                              </span>
                            ) : isUnreviewedLegacy ? (
                              <span className="inline-flex items-center gap-1 rounded bg-sky-500/20 px-1.5 py-0.5 text-[10px] font-bold text-sky-300 border border-sky-500/40">
                                ℹ️ Nota Manual Pendiente de Saneamiento
                              </span>
                            ) : isGap ? (
                              <span className="inline-flex items-center gap-1 rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] font-bold text-indigo-300 border border-indigo-500/40">
                                ✨ Eje Inédito en Mazo
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-slate-300 border border-slate-700">
                                ℹ️ Coincidencia Parcial
                              </span>
                            )}

                            {theme.match_info.matched_note_id && (
                              <span className="font-mono text-[9px] text-slate-300 bg-slate-900/80 px-1.5 py-0.5 rounded border border-slate-700">
                                Nota #{theme.match_info.matched_note_id}
                                {theme.match_info.similarity_score > 0 &&
                                  ` • ${Math.round(theme.match_info.similarity_score * 100)}% similitud`}
                              </span>
                            )}
                          </div>

                          {theme.match_info.matched_note_front && (
                            <p className="mt-1.5 font-medium text-slate-200 italic line-clamp-1 bg-slate-900/80 px-2 py-1 rounded border border-slate-800 text-[10px]">
                              "{theme.match_info.matched_note_front}"
                            </p>
                          )}

                          <div className="mt-1.5 flex items-center justify-between gap-1.5 flex-wrap text-[10px]">
                            <span className="text-slate-300 leading-snug">
                              {isPriorTurnCovered
                                ? '🛡️ Cubierto por tarjetas atómicas generadas en un turno anterior. Desmarcado por defecto para evitar duplicidad.'
                                : isOptimalCollision
                                ? '💡 Ya tenés una tarjeta saneada de alta calidad con este concepto; desmarcala si deseás evitar duplicidad.'
                                : isCognitiveDebt
                                ? 'Esta nota vieja tiene deuda cognitiva. Al generar este eje atómico, se registrará en el Ledger para sustitución limpia.'
                                : isUnreviewedLegacy
                                ? 'Nota previa aún no saneada. Se mantiene SELECCIONADO para generar las tarjetas atómicas de alta calidad. La nota vieja podrá sanearse o descartarse en la cola.'
                                : isGap
                                ? 'Nuevo concepto que añadirá cobertura atómica sin colisiones.'
                                : 'Toca un aspecto relacionado pero no idéntico en tu mazo.'}
                            </span>

                            <button
                              type="button"
                              onClick={() => handleToggleTheme(theme.id)}
                              className={`font-semibold underline transition-colors shrink-0 ${
                                theme.selected
                                  ? 'text-rose-400 hover:text-rose-300'
                                  : 'text-emerald-400 hover:text-emerald-300'
                              }`}
                            >
                              {theme.selected ? 'Desmarcar eje' : 'Marcar para atomizar'}
                            </button>
                          </div>
                        </div>
                      );
                    })()}
                  </div>

                  {/* Stepper */}
                  <div className="mt-3 flex items-center justify-between border-t border-slate-800/80 pt-2">
                    <span className="text-[11px] text-slate-400 font-medium">Tarjetas atómicas:</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleAdjustThemeCards(theme.id, -1)}
                        disabled={!theme.selected || theme.recommended_cards <= 0}
                        aria-label={`Reducir tarjetas para ${theme.title}`}
                        className="rounded-lg border border-slate-700 bg-slate-900 p-1 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                      >
                        <Minus className="h-3 w-3" />
                      </button>
                      <span className="w-5 text-center text-xs font-bold text-indigo-300">
                        {theme.recommended_cards}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleAdjustThemeCards(theme.id, 1)}
                        disabled={!theme.selected || theme.recommended_cards >= 15}
                        aria-label={`Aumentar tarjetas para ${theme.title}`}
                        className="rounded-lg border border-slate-700 bg-slate-900 p-1 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                      >
                        <Plus className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        </div>

        {/* Footer Actions */}
        <div className="shrink-0 border-t border-slate-800 bg-slate-950/95 px-6 py-3.5 flex flex-col sm:flex-row items-center justify-between gap-3 z-10">
          <div className="flex items-center gap-2 text-xs text-slate-300">
            <span className="font-semibold text-white">Total Planificado:</span>
            <span className="rounded-md bg-indigo-500/20 px-2 py-0.5 text-xs font-bold text-indigo-300 border border-indigo-500/30">
              {grandTotalCards} flashcards
            </span>
            <span className="text-slate-400 text-[11px]">
              ({themeCardsTotal} tarjetas de ejes atómicos • prerrequisitos preservados para Fase 4)
            </span>
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto shrink-0">
            <button
              type="button"
              onClick={handleCloseModal}
              className="flex-1 sm:flex-none rounded-xl border border-slate-800 bg-slate-900 px-4 py-2.5 text-xs font-semibold text-slate-300 hover:bg-slate-800 hover:text-white transition-all cursor-pointer"
            >
              Cancelar
            </button>

            <button
              type="button"
              onClick={handleApproveInspection}
              disabled={isGeneratingCards || grandTotalCards === 0}
              className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 px-6 py-2.5 text-xs font-bold text-white shadow-lg shadow-indigo-600/30 hover:shadow-indigo-500/40 active:scale-[0.98] transition-all disabled:opacity-50 whitespace-nowrap cursor-pointer"
            >
              {isGeneratingCards ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Generando mazo...</span>
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  <span>Generar {grandTotalCards} Flashcards Aprobadas</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

    </div>
  );
};
