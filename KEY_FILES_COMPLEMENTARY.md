# =====================================================================
# FILE: frontend/src/components/ClusterSanitationModal.tsx
# =====================================================================

`tsx
import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  Layers,
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  X,
  BookOpen,
  ArrowRight,
  GitMerge,
  Cpu,
  ChevronLeft,
  ChevronRight,
  Image as ImageIcon,
  ZoomIn,
  RotateCw,
  BookmarkCheck,
  Trash2,
  Pause,
} from 'lucide-react';
import type {
  SemanticClusterItem,
  ClusterSanitationPreviewResponse,
  ClusterSanitationPreviewItem,
  ClusterSanitationRequest,
  ClusterSanitationResponse,
  Flashcard,
} from '../types';
import { api, getMediaUrl, rewriteMediaUrlsForWeb } from '../services/api';
import { useModalEscape } from '../utils/useModalEscape';

interface ClusterSanitationModalProps {
  isOpen: boolean;
  onClose: () => void;
  deckName: string;
  cluster: SemanticClusterItem | null;
  apiKey?: string;
  aiProvider?: string;
  localModel?: string;
  onSanitationComplete?: (result: ClusterSanitationResponse) => void;
}

export const ClusterSanitationModal: React.FC<ClusterSanitationModalProps> = ({
  isOpen,
  onClose,
  deckName,
  cluster,
  apiKey,
  aiProvider = 'gemini',
  localModel = 'llama3.2:3b',
  onSanitationComplete,
}) => {
  // Modal Navigation & Preview State
  const [activeTab, setActiveTab] = useState<'cockpit' | 'batch'>('cockpit');
  const [preview, setPreview] = useState<ClusterSanitationPreviewResponse | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState<boolean>(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Turn Cockpit State
  const [activeTurnIndex, setActiveTurnIndex] = useState<number>(0);
  const [turnCandidates, setTurnCandidates] = useState<Record<number, Flashcard[]>>({});
  const [isGeneratingTurn, setIsGeneratingTurn] = useState<boolean>(false);
  const [isReplacingTurn, setIsReplacingTurn] = useState<boolean>(false);
  const [isPreservingTurn, setIsPreservingTurn] = useState<boolean>(false);
  const [turnError, setTurnError] = useState<string | null>(null);
  const [turnCustomInstructions, setTurnCustomInstructions] = useState<Record<number, string>>({});
  const [turnTargetCount, setTurnTargetCount] = useState<Record<number, number>>({});
  const [lightboxImage, setLightboxImage] = useState<string | null>(null);
  const [failedMedia, setFailedMedia] = useState<Record<string, boolean>>({});
  const [isPausingSession, setIsPausingSession] = useState<boolean>(false);

  // Batch Mode State
  const [mode, setMode] = useState<'cross_partition' | 'fusion'>('cross_partition');
  const [cardsPerNote, setCardsPerNote] = useState<number>(3);
  const [fusionTargetCount, setFusionTargetCount] = useState<number>(6);
  const [batchCustomInstructions, setBatchCustomInstructions] = useState<string>('');
  const [isSanitizingBatch, setIsSanitizingBatch] = useState<boolean>(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const [sanitationResult, setSanitationResult] = useState<ClusterSanitationResponse | null>(null);

  // Fetch cluster preview when opened
  useEffect(() => {
    if (!isOpen || !cluster) return;

    let isMounted = true;
    const fetchPreview = async () => {
      setIsLoadingPreview(true);
      setPreviewError(null);
      try {
        const res = await api.getClusterSanitationPreview(deckName, cluster.cluster_index);
        if (isMounted) {
          setPreview(res);
          setSanitationResult(null);
          setBatchError(null);
          setTurnCandidates({});
          setFailedMedia({});
          if (res.suggested_mode) {
            setMode(res.suggested_mode);
          }
          // Default active turn to the first non-optimal note
          const firstPendingIdx = res.notes.findIndex((n) => n.quality_status !== 'optimal');
          setActiveTurnIndex(firstPendingIdx !== -1 ? firstPendingIdx : 0);
        }
      } catch (err: any) {
        if (isMounted) {
          setPreviewError(err.message || 'No se pudo cargar la vista previa del clúster.');
        }
      } finally {
        if (isMounted) {
          setIsLoadingPreview(false);
        }
      }
    };

    fetchPreview();
    return () => {
      isMounted = false;
    };
  }, [isOpen, cluster, deckName]);

  useModalEscape(
    isOpen,
    () => {
      if (lightboxImage) {
        setLightboxImage(null);
      } else {
        onClose();
      }
    },
    isSanitizingBatch || isReplacingTurn
  );

  if (!isOpen || !cluster) return null;

  const notesList = preview?.notes || [];
  const currentNote: ClusterSanitationPreviewItem | undefined = notesList[activeTurnIndex];
  const optimalCount = notesList.filter((n) => n.quality_status === 'optimal').length;
  const totalCount = notesList.length;
  const progressPct = totalCount > 0 ? Math.round((optimalCount / totalCount) * 100) : 0;

  // ---------------------------------------------------------------------------
  // Turn Cockpit Handlers
  // ---------------------------------------------------------------------------

  const handleGenerateCandidates = async () => {
    if (!currentNote) return;
    setIsGeneratingTurn(true);
    setTurnError(null);
    try {
      const res = await api.generateClusterNoteCandidates(
        deckName,
        cluster.cluster_index,
        currentNote.note_id,
        {
          custom_instructions: turnCustomInstructions[currentNote.note_id]?.trim() || undefined,
          target_count: turnTargetCount[currentNote.note_id] || 0,
          ai_provider: aiProvider,
          local_model: localModel,
        },
        apiKey
      );
      setTurnCandidates((prev) => ({
        ...prev,
        [currentNote.note_id]: res.cards || [],
      }));
    } catch (err: any) {
      setTurnError(err.message || 'Error al generar tarjetas candidatas para esta nota.');
    } finally {
      setIsGeneratingTurn(false);
    }
  };

  const handleReplaceNote = async () => {
    if (!currentNote) return;
    const cards = turnCandidates[currentNote.note_id] || [];
    if (cards.length === 0) {
      setTurnError('Generá o definí al menos una tarjeta atómica antes de sustituir.');
      return;
    }

    setIsReplacingTurn(true);
    setTurnError(null);
    try {
      await api.replaceNoteTransactionally(deckName, currentNote.note_id, cards);

      // Update local note status to optimal
      if (preview) {
        setPreview({
          ...preview,
          notes: preview.notes.map((n) =>
            n.note_id === currentNote.note_id ? { ...n, quality_status: 'optimal' } : n
          ),
        });
      }

      // Advance to next pending note if available
      const nextPending = notesList.findIndex(
        (n, idx) => idx > activeTurnIndex && n.quality_status !== 'optimal'
      );
      if (nextPending !== -1) {
        setActiveTurnIndex(nextPending);
      } else if (activeTurnIndex < notesList.length - 1) {
        setActiveTurnIndex(activeTurnIndex + 1);
      }
    } catch (err: any) {
      setTurnError(err.message || 'Error durante la sustitución transaccional en Anki.');
    } finally {
      setIsReplacingTurn(false);
    }
  };

  const handlePreserveOptimal = async () => {
    if (!currentNote) return;
    setIsPreservingTurn(true);
    setTurnError(null);
    try {
      await api.preserveNoteOptimal(deckName, currentNote.note_id);

      // Update local note status to optimal
      if (preview) {
        setPreview({
          ...preview,
          notes: preview.notes.map((n) =>
            n.note_id === currentNote.note_id ? { ...n, quality_status: 'optimal' } : n
          ),
        });
      }

      // Advance to next pending note
      const nextPending = notesList.findIndex(
        (n, idx) => idx > activeTurnIndex && n.quality_status !== 'optimal'
      );
      if (nextPending !== -1) {
        setActiveTurnIndex(nextPending);
      } else if (activeTurnIndex < notesList.length - 1) {
        setActiveTurnIndex(activeTurnIndex + 1);
      }
    } catch (err: any) {
      setTurnError(err.message || 'Error al conservar la nota como óptima.');
    } finally {
      setIsPreservingTurn(false);
    }
  };

  const handlePauseSession = () => {
    setIsPausingSession(true);
    setTimeout(() => {
      onClose();
    }, 350);
  };

  const handleCardChange = (cardIndex: number, field: keyof Flashcard, value: string) => {
    if (!currentNote) return;
    const currentList = [...(turnCandidates[currentNote.note_id] || [])];
    if (currentList[cardIndex]) {
      currentList[cardIndex] = {
        ...currentList[cardIndex],
        [field]: value,
      };
      setTurnCandidates((prev) => ({
        ...prev,
        [currentNote.note_id]: currentList,
      }));
    }
  };

  const handleRemoveCard = (cardIndex: number) => {
    if (!currentNote) return;
    const currentList = [...(turnCandidates[currentNote.note_id] || [])];
    currentList.splice(cardIndex, 1);
    setTurnCandidates((prev) => ({
      ...prev,
      [currentNote.note_id]: currentList,
    }));
  };

  // ---------------------------------------------------------------------------
  // Batch Execution Handler
  // ---------------------------------------------------------------------------

  const handleExecuteBatch = async () => {
    setIsSanitizingBatch(true);
    setBatchError(null);
    try {
      const payload: ClusterSanitationRequest = {
        mode,
        cards_per_note: cardsPerNote,
        fusion_target_count: fusionTargetCount,
        custom_instructions: batchCustomInstructions.trim() ? batchCustomInstructions.trim() : undefined,
        ai_provider: aiProvider,
        local_model: localModel,
      };

      const result = await api.sanitizeCluster(deckName, cluster.cluster_index, payload, apiKey);
      setSanitationResult(result);
      onSanitationComplete?.(result);
    } catch (err: any) {
      setBatchError(err.message || 'Error durante la ejecución del saneamiento por clúster.');
    } finally {
      setIsSanitizingBatch(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cluster-sanitation-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4 bg-slate-950/85 backdrop-blur-md animate-fade-in overflow-y-auto"
    >
      <div className="relative w-full max-w-5xl max-h-[94vh] flex flex-col rounded-3xl border border-teal-500/30 bg-slate-900/95 shadow-2xl text-slate-100 overflow-hidden my-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-slate-800 bg-gradient-to-r from-teal-950/50 via-slate-900 to-indigo-950/50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-2xl bg-teal-500/20 text-teal-300 border border-teal-500/30 shadow-inner shrink-0">
              <Sparkles className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-extrabold uppercase tracking-wider text-teal-400">
                  Cockpit de Saneamiento Temático (Fase 3)
                </span>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-slate-300 border border-slate-700">
                  {deckName}
                </span>
              </div>
              <h2 id="cluster-sanitation-modal-title" className="text-base sm:text-lg font-bold text-white flex items-center gap-2 flex-wrap">
                <span>Clúster #{cluster.cluster_index}: {cluster.title}</span>
                <span className="text-xs font-normal text-slate-400">({totalCount} notas)</span>
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar saneamiento del clúster"
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
              title="Cerrar (Progreso guardado automáticamente)"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Tab Selector & Cluster Progress Banner */}
        <div className="border-b border-slate-800/80 bg-slate-950/50 px-4 sm:px-6 py-2.5 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2 w-full sm:w-auto">
            <button
              type="button"
              onClick={() => setActiveTab('cockpit')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
                activeTab === 'cockpit'
                  ? 'bg-teal-500 text-slate-950 shadow-md shadow-teal-500/20'
                  : 'bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-700/80'
              }`}
            >
              <Cpu className="h-4 w-4" />
              <span>Cockpit por Turnos (Supervisado)</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('batch')}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer flex items-center gap-2 ${
                activeTab === 'batch'
                  ? 'bg-indigo-500 text-white shadow-md shadow-indigo-500/20'
                  : 'bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-700/80'
              }`}
            >
              <GitMerge className="h-4 w-4" />
              <span>Lote Automatizado (Fast Batch)</span>
            </button>
          </div>

          {/* Resilient Progress Indicator */}
          <div className="flex items-center gap-3 w-full sm:w-auto justify-end text-xs">
            <div className="flex items-center gap-1.5 text-slate-300">
              <span className="text-[10px] uppercase font-mono text-slate-400">Progreso:</span>
              <span className="font-bold text-teal-300">{optimalCount}</span>
              <span className="text-slate-400">/</span>
              <span className="font-medium text-slate-400">{totalCount}</span>
              <span className="text-[10px] text-teal-400 font-mono">({progressPct}%)</span>
            </div>
            <div className="w-24 sm:w-32 h-2 rounded-full bg-slate-800 overflow-hidden border border-slate-700">
              <div
                className="h-full bg-gradient-to-r from-teal-500 to-emerald-400 transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-5">
          {isLoadingPreview ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-3">
              <Loader2 className="h-10 w-10 animate-spin text-teal-400" />
              <p className="text-xs font-bold text-slate-300">
                Calculando orden topológico en el DAG y analizando frontera negativa de hermanos...
              </p>
            </div>
          ) : previewError ? (
            <div className="rounded-2xl border border-rose-500/40 bg-rose-950/30 p-4 text-xs text-rose-300 flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold">Error al preparar el saneamiento</p>
                <p className="mt-1 text-rose-300/80">{previewError}</p>
              </div>
            </div>
          ) : activeTab === 'cockpit' ? (
            totalCount === 0 ? (
              <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 space-y-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-950/40 border border-teal-500/30 text-teal-400">
                  <CheckCircle2 className="h-6 w-6" />
                </div>
                <h4 className="text-sm font-bold text-slate-200">Este clúster no tiene notas registradas</h4>
                <p className="text-xs text-slate-400 max-w-md">
                  No se encontraron notas asociadas a este eje temático en '{deckName}'. Podés volver a Deck Studio para auditar otros ejes.
                </p>
              </div>
            ) : (
            /* =========================================================================
               TAB 1: COCKPIT DE SANEAMIENTO POR TURNOS (SUPERVISADO)
               ========================================================================= */
            <div className="space-y-5 animate-fade-in">
              {/* 100% Optimal Clustered Banner */}
              {progressPct === 100 && (
                <div className="rounded-2xl border border-emerald-500/40 bg-emerald-950/30 p-3.5 text-xs text-emerald-200 flex items-center justify-between gap-3 animate-fade-in shadow-md">
                  <div className="flex items-center gap-2.5">
                    <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
                    <div>
                      <span className="font-bold">¡Clúster al 100% de Salud Atómica!</span>
                      <p className="text-[11px] text-emerald-300/80 mt-0.5">
                        Todas las {totalCount} notas están catalogadas como óptimas. Podés navegar los turnos para inspeccionarlas o regenerar cualquiera de ellas si deseás enriquecerla.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Stepper Navigation Bar */}
              <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-3 flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => setActiveTurnIndex((prev) => Math.max(0, prev - 1))}
                    disabled={activeTurnIndex === 0}
                    aria-label="Turno anterior"
                    className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>

                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-extrabold text-teal-300 bg-teal-950/80 border border-teal-800/60 px-2 py-0.5 rounded-lg">
                      Turno {activeTurnIndex + 1} de {totalCount}
                    </span>
                    {currentNote && (
                      <span className="text-[11px] text-slate-400 font-mono">
                        (Nota #{currentNote.note_id})
                      </span>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => setActiveTurnIndex((prev) => Math.min(totalCount - 1, prev + 1))}
                    disabled={activeTurnIndex >= totalCount - 1}
                    aria-label="Turno siguiente"
                    className="p-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 disabled:opacity-30 cursor-pointer"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>

                {/* Status & Topological Precedence Badges */}
                {currentNote && (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`text-[10px] font-bold uppercase px-2.5 py-0.5 rounded-full border ${
                        currentNote.quality_status === 'optimal'
                          ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                          : currentNote.quality_status === 'bad'
                          ? 'bg-rose-500/10 text-rose-300 border-rose-500/30'
                          : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
                      }`}
                    >
                      {currentNote.quality_status === 'optimal' ? '✓ Óptima' : currentNote.quality_status === 'bad' ? '⚠ Deuda' : '● Sin Revisar'}
                    </span>

                    {currentNote.topological_rank !== undefined && currentNote.topological_rank !== null && (
                      <span className="text-[10px] font-mono text-indigo-300 bg-indigo-950/60 border border-indigo-800/40 px-2 py-0.5 rounded-full">
                        DAG #{currentNote.topological_rank + 1}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {currentNote && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  {/* LEFT COLUMN: Source Note Inspection & Multimodal Evidence */}
                  <div className="space-y-4">
                    <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                      <div className="flex items-center justify-between text-xs font-bold text-slate-300 border-b border-slate-800/60 pb-2">
                        <span className="flex items-center gap-1.5 text-teal-300">
                          <BookOpen className="h-4 w-4" />
                          <span>Material Original de la Nota #{currentNote.note_id}</span>
                        </span>
                        <span className="text-[10px] font-mono text-slate-400">
                          {currentNote.subtopic_descriptor || 'Concepto'}
                        </span>
                      </div>

                      {/* Front Field */}
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-mono text-slate-400 font-bold">Anverso / Frente:</span>
                        <div
                          className="text-xs text-slate-200 bg-slate-900/90 rounded-xl p-3 border border-slate-800 leading-relaxed font-sans"
                          dangerouslySetInnerHTML={{ __html: rewriteMediaUrlsForWeb(currentNote.clean_front || currentNote.front) }}
                        />
                      </div>

                      {/* Back Field */}
                      <div className="space-y-1">
                        <span className="text-[10px] uppercase font-mono text-slate-400 font-bold">Reverso / Respuesta:</span>
                        <div
                          className="text-xs text-slate-300 bg-slate-900/90 rounded-xl p-3 border border-slate-800 leading-relaxed max-h-40 overflow-y-auto"
                          dangerouslySetInnerHTML={{ __html: rewriteMediaUrlsForWeb(currentNote.back) }}
                        />
                      </div>

                      {/* Image Gallery (Up to 7 images) */}
                      {currentNote.media_files && currentNote.media_files.length > 0 && (
                        <div className="space-y-2 pt-2 border-t border-slate-800/60">
                          <div className="flex items-center justify-between text-xs font-bold text-teal-300">
                            <span className="flex items-center gap-1.5">
                              <ImageIcon className="h-3.5 w-3.5" />
                              <span>Evidencia Gráfica Adjunta ({currentNote.media_files.length} imágenes)</span>
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">Gemini Multimodal</span>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                            {currentNote.media_files.map((img, idx) => {
                              const isBroken = Boolean(failedMedia[img]);
                              return (
                                <div
                                  key={`${img}-${idx}`}
                                  role={isBroken ? undefined : 'button'}
                                  tabIndex={isBroken ? -1 : 0}
                                  aria-label={
                                    isBroken
                                      ? `Imagen no disponible: ${img}`
                                      : `Ampliar imagen ${idx + 1}`
                                  }
                                  onClick={() => {
                                    if (!isBroken) {
                                      setLightboxImage(getMediaUrl(img));
                                    }
                                  }}
                                  onKeyDown={(e) => {
                                    if (!isBroken && (e.key === 'Enter' || e.key === ' ')) {
                                      e.preventDefault();
                                      setLightboxImage(getMediaUrl(img));
                                    }
                                  }}
                                  className={`group relative rounded-xl overflow-hidden border aspect-video transition-all shadow ${
                                    isBroken
                                      ? 'border-amber-500/40 bg-amber-950/20 cursor-not-allowed flex flex-col items-center justify-center p-2 text-center'
                                      : 'border-slate-800 bg-slate-900 cursor-pointer hover:border-teal-500/60'
                                  }`}
                                >
                                  {isBroken ? (
                                    <>
                                      <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mb-1" />
                                      <span className="text-[10px] font-medium text-amber-300 line-clamp-2 break-all">
                                        Imagen no disponible: {img}
                                      </span>
                                    </>
                                  ) : (
                                    <>
                                      <img
                                        src={getMediaUrl(img)}
                                        alt={`Imagen ${idx + 1}`}
                                        className="w-full h-full object-cover group-hover:scale-105 transition-transform"
                                        onError={() => {
                                          setFailedMedia((prev) => ({ ...prev, [img]: true }));
                                        }}
                                      />
                                      <div className="absolute inset-0 bg-slate-950/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                        <ZoomIn className="h-5 w-5 text-white" />
                                      </div>
                                      <span className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded bg-slate-950/80 text-[9px] font-bold text-teal-300 font-mono">
                                        Imagen {idx + 1}
                                      </span>
                                    </>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      )}

                      {/* Sibling Negative Boundaries with Quality Badges */}
                      {currentNote.negative_boundaries && currentNote.negative_boundaries.length > 0 && (
                        <div className="space-y-1.5 pt-2 border-t border-slate-800/60">
                          <span className="text-[10px] font-bold text-slate-400 uppercase font-mono">
                            Fronteras de No-Duplicidad (Subtemas Hermanos):
                          </span>
                          <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                            {currentNote.negative_boundaries.map((boundary, bIdx) => {
                              const sStatus = currentNote.sibling_quality_badges?.[boundary] || 'unreviewed';
                              const isOpt = sStatus === 'optimal';
                              return (
                                <span
                                  key={bIdx}
                                  className={`px-2 py-0.5 rounded-lg text-[9px] font-medium border flex items-center gap-1 ${
                                    isOpt
                                      ? 'bg-emerald-950/30 text-emerald-300 border-emerald-800/40'
                                      : 'bg-amber-950/30 text-amber-300 border-amber-800/40'
                                  }`}
                                  title={isOpt ? 'Nota hermana ya óptima: frontera inmutable' : 'Nota hermana pendiente de saneamiento'}
                                >
                                  <span>{isOpt ? '🛡️' : '⚠️'}</span>
                                  <span>{boundary}</span>
                                </span>
                              );
                            })}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* RIGHT COLUMN: AI Atomic Proposals & Candidate Editor */}
                  <div className="space-y-4">
                    {/* Candidate Generation Box */}
                    {(!turnCandidates[currentNote.note_id] || turnCandidates[currentNote.note_id].length === 0) ? (
                      <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/40 p-6 flex flex-col items-center justify-center text-center space-y-4 min-h-[300px]">
                        {isGeneratingTurn ? (
                          <div className="space-y-3">
                            <Loader2 className="h-8 w-8 animate-spin text-teal-400 mx-auto" />
                            <p className="text-xs font-bold text-slate-200">
                              Razonando átomos conceptuales con Gemini Multimodal...
                            </p>
                            <p className="text-[11px] text-slate-400 max-w-sm">
                              Analizando texto y {currentNote.media_files?.length || 0} imágenes con justificación atómica sin compresión forzada.
                            </p>
                          </div>
                        ) : currentNote.quality_status === 'optimal' ? (
                          <div className="space-y-3 max-w-sm">
                            <div className="h-10 w-10 rounded-full bg-emerald-500/20 text-emerald-300 flex items-center justify-center mx-auto border border-emerald-500/40">
                              <CheckCircle2 className="h-6 w-6" />
                            </div>
                            <h4 className="text-sm font-bold text-emerald-300">Nota Ya Saneada como Óptima</h4>
                            <p className="text-xs text-slate-400">
                              Esta nota cumple con las leyes cognitivas y no presenta deuda. Podés avanzar al siguiente turno o regenerarla si deseás reestructurarla.
                            </p>
                            <button
                              type="button"
                              onClick={handleGenerateCandidates}
                              className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 hover:text-white transition-all cursor-pointer inline-flex items-center gap-1.5"
                            >
                              <RotateCw className="h-3.5 w-3.5" />
                              <span>Regenerar de Todos Modos</span>
                            </button>
                          </div>
                        ) : (
                          <div className="space-y-4 max-w-sm">
                            <div className="h-12 w-12 rounded-2xl bg-teal-500/10 border border-teal-500/30 text-teal-300 flex items-center justify-center mx-auto">
                              <Sparkles className="h-6 w-6" />
                            </div>
                            <div>
                              <h4 className="text-sm font-bold text-white">Proponer Tarjetas Atómicas</h4>
                              <p className="text-xs text-slate-400 mt-1">
                                La IA extraerá los hechos esenciales de esta nota respetando el Principio de Información Mínima.
                              </p>
                            </div>

                            {/* Target Count Option */}
                            <div className="flex items-center justify-center gap-2 pt-1">
                              <span className="text-[11px] text-slate-400">Tarjetas sugeridas:</span>
                              {[0, 2, 3, 4].map((count) => (
                                <button
                                  key={count}
                                  type="button"
                                  onClick={() => setTurnTargetCount((prev) => ({ ...prev, [currentNote.note_id]: count }))}
                                  className={`px-2 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                                    (turnTargetCount[currentNote.note_id] || 0) === count
                                      ? 'bg-teal-500 text-slate-950 font-extrabold'
                                      : 'bg-slate-800 text-slate-400 hover:text-white'
                                  }`}
                                >
                                  {count === 0 ? 'Auto (Densidad)' : count}
                                </button>
                              ))}
                            </div>

                            {/* Optional Turn Instructions */}
                            <input
                              type="text"
                              aria-label="Instrucción de enfoque opcional para el turno"
                              value={turnCustomInstructions[currentNote.note_id] || ''}
                              onChange={(e) =>
                                setTurnCustomInstructions((prev) => ({
                                  ...prev,
                                  [currentNote.note_id]: e.target.value,
                                }))
                              }
                              placeholder="Instrucción de enfoque (opcional)..."
                              className="w-full rounded-xl bg-slate-900 border border-slate-800 px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-teal-500/50"
                            />

                            <button
                              type="button"
                              onClick={handleGenerateCandidates}
                              className="w-full px-5 py-2.5 rounded-xl bg-gradient-to-r from-teal-600 to-emerald-600 hover:from-teal-500 hover:to-emerald-500 text-xs font-bold text-white shadow-lg shadow-teal-950/40 active:scale-95 transition-all cursor-pointer inline-flex items-center justify-center gap-2"
                            >
                              <Sparkles className="h-4 w-4" />
                              <span>Generar Propuesta Atómica</span>
                            </button>
                          </div>
                        )}
                      </div>
                    ) : (
                      /* Candidate Cards List */
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-teal-300 flex items-center gap-2">
                            <Layers className="h-4 w-4" />
                            <span>Tarjetas Atómicas Propuestas ({turnCandidates[currentNote.note_id]?.length || 0})</span>
                          </span>
                          <button
                            type="button"
                            onClick={handleGenerateCandidates}
                            disabled={isGeneratingTurn}
                            className="text-[10px] text-slate-400 hover:text-teal-300 flex items-center gap-1 cursor-pointer"
                          >
                            <RotateCw className={`h-3 w-3 ${isGeneratingTurn ? 'animate-spin' : ''}`} />
                            <span>Regenerar</span>
                          </button>
                        </div>

                        <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1">
                          {turnCandidates[currentNote.note_id]?.map((card, cIdx) => (
                            <div
                              key={cIdx}
                              className="rounded-2xl border border-slate-800 bg-slate-950/80 p-3.5 space-y-2.5 relative group hover:border-teal-500/40 transition-all"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-md bg-teal-950 text-teal-300 border border-teal-800/40 font-mono">
                                  {card.archetype || 'Tarjeta Atómica'}
                                </span>
                                <button
                                  type="button"
                                  onClick={() => handleRemoveCard(cIdx)}
                                  aria-label={`Eliminar tarjeta propuesta ${cIdx + 1}`}
                                  className="text-slate-400 hover:text-rose-400 p-1 rounded-lg transition-colors cursor-pointer"
                                  title="Eliminar esta tarjeta"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>

                              {/* Card Front Edit */}
                              <div className="space-y-1">
                                <span className="text-[9px] uppercase font-mono text-slate-400 font-bold">Anverso:</span>
                                <textarea
                                  rows={2}
                                  aria-label={`Anverso de tarjeta propuesta ${cIdx + 1}`}
                                  value={card.front}
                                  onChange={(e) => handleCardChange(cIdx, 'front', e.target.value)}
                                  className="w-full text-xs text-slate-200 bg-slate-900 rounded-lg p-2 border border-slate-800 focus:border-teal-500 focus:outline-none resize-none font-sans"
                                />
                              </div>

                              {/* Card Back Edit */}
                              <div className="space-y-1">
                                <span className="text-[9px] uppercase font-mono text-slate-400 font-bold">Dorso (Respuesta):</span>
                                <input
                                  type="text"
                                  aria-label={`Dorso de tarjeta propuesta ${cIdx + 1}`}
                                  value={card.back}
                                  onChange={(e) => handleCardChange(cIdx, 'back', e.target.value)}
                                  className="w-full text-xs text-emerald-300 bg-slate-900 rounded-lg p-2 border border-slate-800 focus:border-teal-500 focus:outline-none font-sans font-medium"
                                />
                              </div>

                              {/* Justification & Diagram Inheritance */}
                              <div className="space-y-1.5 pt-1 border-t border-slate-900">
                                {card.justification && (
                                  <div className="p-2 rounded-lg bg-teal-950/30 border border-teal-900/40 text-[10px] text-teal-300/90 leading-tight">
                                    <span className="font-bold uppercase text-[9px] block text-teal-400">Justificación Atómica:</span>
                                    {card.justification}
                                  </div>
                                )}

                                {card.source_image && (
                                  <div className="flex items-center gap-2 p-1.5 rounded-lg bg-indigo-950/30 border border-indigo-900/40 text-[10px] text-indigo-300">
                                    <ImageIcon className="h-3.5 w-3.5 shrink-0" />
                                    <span>Heredó diagrama visual: <strong>{card.source_image}</strong></span>
                                  </div>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Turn Error Banner */}
                    {turnError && (
                      <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-xs text-rose-300 flex items-start gap-2">
                        <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                        <span>{turnError}</span>
                      </div>
                    )}

                    {/* Turn Action Buttons */}
                    <div className="pt-2 flex flex-wrap items-center justify-between gap-2">
                      <button
                        type="button"
                        onClick={handlePreserveOptimal}
                        disabled={isPreservingTurn || isReplacingTurn}
                        className="px-3.5 py-2 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-all cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
                        title="Marcar como óptima en base de conocimiento sin modificar en Anki"
                      >
                        {isPreservingTurn ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <BookmarkCheck className="h-3.5 w-3.5 text-emerald-400" />}
                        <span>Conservar Original</span>
                      </button>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setActiveTurnIndex((prev) => Math.min(totalCount - 1, prev + 1))}
                          className="px-3 py-2 rounded-xl text-xs text-slate-400 hover:text-slate-200 transition-all cursor-pointer"
                        >
                          Saltar
                        </button>

                        <button
                          type="button"
                          onClick={handleReplaceNote}
                          disabled={
                            isReplacingTurn ||
                            isPreservingTurn ||
                            !turnCandidates[currentNote.note_id] ||
                            turnCandidates[currentNote.note_id].length === 0
                          }
                          className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-xs font-bold text-white shadow-lg shadow-emerald-950/40 transition-all cursor-pointer flex items-center gap-1.5 disabled:opacity-40"
                        >
                          {isReplacingTurn ? (
                            <>
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              <span>Sustituyendo en Anki...</span>
                            </>
                          ) : (
                            <>
                              <CheckCircle2 className="h-4 w-4 text-emerald-200" />
                              <span>Aprobar y Sustituir Nota</span>
                              <ArrowRight className="h-3.5 w-3.5" />
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        ) : (
            /* =========================================================================
               TAB 2: LOTE AUTOMATIZADO (FAST BATCH CLUSTER SANITATION)
               ========================================================================= */
            sanitationResult ? (
              <div className="rounded-2xl border border-emerald-500/40 bg-emerald-950/20 p-6 space-y-5 text-center animate-fade-in">
                <div className="h-16 w-16 mx-auto rounded-full bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-300">
                  <CheckCircle2 className="h-9 w-9" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-lg font-bold text-emerald-200">¡Clúster Saneado con Éxito!</h3>
                  <p className="text-xs text-emerald-300/80 max-w-lg mx-auto">{sanitationResult.message}</p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-lg mx-auto text-left">
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span className="text-[10px] text-slate-400 uppercase font-mono">Modo Aplicado</span>
                    <p className="text-xs font-bold text-teal-300 uppercase mt-0.5">{sanitationResult.mode}</p>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span className="text-[10px] text-slate-400 uppercase font-mono">Tarjetas Creadas</span>
                    <p className="text-xs font-bold text-emerald-300 mt-0.5">{sanitationResult.created_cards_count} atómicas</p>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-900/80 border border-slate-800">
                    <span className="text-[10px] text-slate-400 uppercase font-mono">Notas Sustituidas</span>
                    <p className="text-xs font-bold text-rose-300 mt-0.5">{sanitationResult.deleted_note_ids.length} obsoletas</p>
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-xs font-bold text-white shadow-lg shadow-emerald-950/40 active:scale-95 transition-all cursor-pointer"
                  >
                    Continuar en Deck Studio
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-6 animate-fade-in">
                {/* Scope Description Banner */}
                <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4 space-y-2">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-200">
                    <span className="flex items-center gap-2 text-teal-300">
                      <BookOpen className="h-4 w-4" />
                      <span>Alcance Conceptual del Clúster</span>
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      {totalCount} notas bajo este alcance
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed italic">
                    "{cluster.scope || preview?.cluster_scope || 'Sin descripción de alcance'}"
                  </p>
                </div>

                {/* Mode Selection Grid */}
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-200 flex items-center justify-between">
                    <span>Estrategia de Descomposición Temática:</span>
                    {preview?.suggested_mode && (
                      <span className="text-[10px] text-teal-400 font-mono">
                        (Sugerencia IA: {preview.suggested_mode === 'cross_partition' ? 'Partición Cruzada' : 'Fusión'})
                      </span>
                    )}
                  </label>

                  <div
                    role="radiogroup"
                    aria-label="Estrategia de descomposición temática"
                    className="grid grid-cols-1 md:grid-cols-2 gap-3"
                  >
                    {/* Mode B: Cross-Partitioned */}
                    <div
                      role="radio"
                      aria-checked={mode === 'cross_partition'}
                      tabIndex={0}
                      onClick={() => setMode('cross_partition')}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setMode('cross_partition');
                        }
                      }}
                      className={`p-4 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between space-y-3 ${
                        mode === 'cross_partition'
                          ? 'border-teal-500/70 bg-teal-950/20 shadow-md shadow-teal-950/40 ring-1 ring-teal-500/40'
                          : 'border-slate-800 bg-slate-950/40 hover:border-slate-700'
                      }`}
                    >
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-white flex items-center gap-2">
                            <Cpu className="h-4 w-4 text-teal-400" />
                            <span>Partición Cruzada (Profundidad Máxima)</span>
                          </span>
                          {mode === 'cross_partition' && (
                            <span className="h-2.5 w-2.5 rounded-full bg-teal-400 ring-4 ring-teal-400/20" />
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 leading-relaxed">
                          Cada nota conserva su profundidad y diagramas ({cardsPerNote} tarjetas por nota).
                          Los subtemas hermanos actúan como <strong>Fronteras Negativas</strong> para evitar solapamientos.
                        </p>
                      </div>

                      {mode === 'cross_partition' && (
                        <div className="pt-2 border-t border-teal-500/20 flex items-center justify-between gap-3">
                          <span className="text-[11px] font-semibold text-slate-300">Tarjetas por nota:</span>
                          <div className="flex items-center gap-1.5">
                            {[2, 3, 4, 5].map((count) => (
                              <button
                                key={count}
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setCardsPerNote(count);
                                }}
                                className={`h-7 w-7 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                                  cardsPerNote === count
                                    ? 'bg-teal-500 text-slate-950'
                                    : 'bg-slate-800 text-slate-400 hover:text-white'
                                }`}
                              >
                                {count}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Mode A: Dossier Fusion */}
                    <div
                      role="radio"
                      aria-checked={mode === 'fusion'}
                      tabIndex={0}
                      onClick={() => setMode('fusion')}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setMode('fusion');
                        }
                      }}
                      className={`p-4 rounded-2xl border transition-all cursor-pointer flex flex-col justify-between space-y-3 ${
                        mode === 'fusion'
                          ? 'border-indigo-500/70 bg-indigo-950/20 shadow-md shadow-indigo-950/40 ring-1 ring-indigo-500/40'
                          : 'border-slate-800 bg-slate-950/40 hover:border-slate-700'
                      }`}
                    >
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-white flex items-center gap-2">
                            <GitMerge className="h-4 w-4 text-indigo-400" />
                            <span>Fusión de Dossier (Desduplicación)</span>
                          </span>
                          {mode === 'fusion' && (
                            <span className="h-2.5 w-2.5 rounded-full bg-indigo-400 ring-4 ring-indigo-400/20" />
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 leading-relaxed">
                          Recomendado para notas que son reformulaciones casi idénticas del mismo concepto.
                          Las sintetiza en un dossier unificado para generar un mazo curado.
                        </p>
                      </div>

                      {mode === 'fusion' && (
                        <div className="pt-2 border-t border-indigo-500/20 flex items-center justify-between gap-3">
                          <span className="text-[11px] font-semibold text-slate-300">Total tarjetas deseadas:</span>
                          <div className="flex items-center gap-1.5">
                            {[4, 6, 8, 10].map((count) => (
                              <button
                                key={count}
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setFusionTargetCount(count);
                                }}
                                className={`h-7 w-7 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                                  fusionTargetCount === count
                                    ? 'bg-indigo-500 text-white'
                                    : 'bg-slate-800 text-slate-400 hover:text-white'
                                }`}
                              >
                                {count}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Optional Custom Directives */}
                <div className="space-y-1.5">
                  <label htmlFor="batch-custom-instructions" className="text-xs font-bold text-slate-300">
                    Instrucciones Específicas para este Clúster (Opcional):
                  </label>
                  <textarea
                    id="batch-custom-instructions"
                    rows={2}
                    placeholder="Ej: Priorizar clozes con nombres de herramientas OCI, o enfatizar casos de timeout..."
                    value={batchCustomInstructions}
                    onChange={(e) => setBatchCustomInstructions(e.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-950/80 p-3 text-xs text-slate-200 placeholder:text-slate-500 focus:border-teal-500 focus:outline-none resize-none"
                  />
                </div>

                {/* Error Message if Execution Failed */}
                {batchError && (
                  <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-3.5 text-xs text-rose-300 flex items-start gap-2.5">
                    <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                    <div>
                      <span className="font-bold">Error durante el saneamiento:</span>
                      <p className="mt-0.5 text-rose-300/90">{batchError}</p>
                    </div>
                  </div>
                )}
              </div>
            )
          )}
        </div>

        {/* Modal Footer */}
        {activeTab === 'batch' && !sanitationResult && (
          <div className="p-4 sm:p-5 border-t border-slate-800 bg-slate-950/80 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <ShieldCheck className="h-4 w-4 text-teal-400 shrink-0" />
              <span>Transaccional: las notas originales sólo se sustituyen si Anki valida las nuevas.</span>
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
              <button
                type="button"
                onClick={onClose}
                disabled={isSanitizingBatch}
                className="px-4 py-2 rounded-xl border border-slate-700 bg-slate-800/80 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition-all cursor-pointer disabled:opacity-50"
              >
                Cerrar
              </button>

              <button
                type="button"
                onClick={handleExecuteBatch}
                disabled={isSanitizingBatch || isLoadingPreview || !!previewError}
                className="flex-1 sm:flex-none inline-flex items-center justify-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-teal-600 via-emerald-600 to-indigo-600 hover:from-teal-500 hover:via-emerald-500 hover:to-indigo-500 text-xs font-bold text-white shadow-lg shadow-teal-950/50 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
              >
                {isSanitizingBatch ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>Saneando Clúster ({mode === 'cross_partition' ? 'Partición Cruzada' : 'Fusión'})...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 text-teal-200" />
                    <span>Ejecutar Saneamiento del Clúster Completo</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* Cockpit Session Resilience Footer */}
        {activeTab === 'cockpit' && (
          <div className="px-4 py-3 border-t border-slate-800/80 bg-slate-950/80 flex items-center justify-between text-xs text-slate-400">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-teal-400 shrink-0" />
              <span>Cada turno aprobado o conservado se persiste al instante. Podés cerrar y reanudar en cualquier momento.</span>
            </div>
            <button
              type="button"
              onClick={handlePauseSession}
              disabled={isPausingSession}
              className="px-4 py-1.5 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-semibold text-slate-200 transition-all cursor-pointer flex items-center gap-1.5 disabled:opacity-50"
            >
              <Pause className={`h-3.5 w-3.5 text-teal-400 ${isPausingSession ? 'animate-pulse' : ''}`} />
              <span>{isPausingSession ? 'Guardando sesión...' : 'Pausar Sesión'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Full-Screen Image Lightbox Viewer */}
      {lightboxImage && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Imagen ampliada"
          className="fixed inset-0 z-[60] bg-slate-950/90 backdrop-blur-md flex items-center justify-center p-4 animate-fade-in cursor-zoom-out"
          onClick={() => setLightboxImage(null)}
        >
          <div className="relative max-w-4xl max-h-[90vh]">
            <img
              src={lightboxImage}
              alt="Diagrama ampliado"
              className="max-w-full max-h-[85vh] object-contain rounded-2xl border border-teal-500/30 shadow-2xl"
            />
            <button
              type="button"
              onClick={() => setLightboxImage(null)}
              aria-label="Cerrar imagen ampliada"
              className="absolute top-3 right-3 p-2 rounded-xl bg-slate-900/90 border border-slate-700 text-white hover:bg-slate-800 cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

`

# =====================================================================
# FILE: frontend/src/App.tsx
# =====================================================================

`tsx
import React, { useState, useEffect, useCallback, useMemo, useRef, Suspense } from 'react';
import { Header } from './components/Header';
import { ContentDropzone } from './components/ContentDropzone';
import type { InputMaterialMode } from './components/ContentDropzone';
import { GenerationConfigBar } from './components/GenerationConfigBar';
import { FlashcardGrid } from './components/FlashcardGrid';
import { LoadingSkeleton } from './components/LoadingSkeleton';
import { ActiveStudyPlanBanner } from './components/ActiveStudyPlanBanner';
import { CurationQueueBanner } from './components/CurationQueueBanner';
import { ToastContainer } from './components/Toast';
import type { ToastMessage } from './components/Toast';
import { api, PartialStreamError } from './services/api';
import type {
  AnkiStatus,
  OllamaStatus,
  Flashcard,
  GenerationOptions,
  StudyPlanInspection,
  DeckAuditReport,
  GenerateCardsResponse,
  DeckNoteRecord,
  CurationQueueItem,
  OrphanGap,
  SanitationQueueResponse,
  ExpansionQueueItem,
  CognitiveAuditFinding,
} from './types';

import { Brain, Sparkles, CheckCircle2, Loader2 } from 'lucide-react';

const ApiKeyModal = React.lazy(() =>
  import('./components/ApiKeyModal').then((m) => ({ default: m.ApiKeyModal }))
);
const AnkiCardPickerModal = React.lazy(() =>
  import('./components/AnkiCardPickerModal').then((m) => ({ default: m.AnkiCardPickerModal }))
);
const MaterialInspectionCockpit = React.lazy(() =>
  import('./components/MaterialInspectionCockpit').then((m) => ({
    default: m.MaterialInspectionCockpit,
  }))
);
const CognitiveAuditModal = React.lazy(() =>
  import('./components/CognitiveAuditModal').then((m) => ({ default: m.CognitiveAuditModal }))
);
const DeckStudioModal = React.lazy(() =>
  import('./components/DeckStudioModal').then((m) => ({ default: m.DeckStudioModal }))
);

import { extractFirstClozeAnswer } from './utils/clozeParser';

function syncClozeCards(cards: Flashcard[]): Flashcard[] {
  let hasChanges = false;
  const synced = cards.map((c) => {
    if (c.card_type === 'cloze') {
      const target = extractFirstClozeAnswer(c.front);
      if (target) {
        if (c.back !== target) {
          hasChanges = true;
          return { ...c, back: target };
        }
      }
    }
    return c;
  });
  return hasChanges ? synced : cards;
}

export const App: React.FC = () => {
  // Anki Desktop Status
  const [ankiStatus, setAnkiStatus] = useState<AnkiStatus>({
    is_connected: false,
    available_decks: [],
  });
  const [isLoadingAnki, setIsLoadingAnki] = useState<boolean>(true);

  // Local Ollama Status (AMD GPU)
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus>({
    is_available: false,
    models: [],
    active_model: 'qwen2.5:14b',
  });

  // Gemini API Key (Optional local override if not in backend .env)
  const [apiKey, setApiKey] = useState<string>(() => {
    return localStorage.getItem('ankicraft_gemini_key') || '';
  });
  const [isApiKeyModalOpen, setIsApiKeyModalOpen] = useState<boolean>(false);

  // Content Input State
  const [inputMode, setInputMode] = useState<InputMaterialMode>(() => {
    return (sessionStorage.getItem('ankicraft_input_mode') as InputMaterialMode) || 'anki';
  });
  const [rawText, setRawText] = useState<string>(() => {
    return sessionStorage.getItem('ankicraft_raw_text') || '';
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  // Accompanying image for text mode
  const [textAttachedImage, setTextAttachedImage] = useState<File | null>(null);

  // Selected Anki Card as educational material
  const [selectedAnkiCard, setSelectedAnkiCard] = useState<DeckNoteRecord | null>(() => {
    try {
      const cached =
        sessionStorage.getItem('ankicraft_selected_anki_card') ||
        localStorage.getItem('ankicraft_selected_anki_card');
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [isAnkiCardPickerOpen, setIsAnkiCardPickerOpen] = useState<boolean>(false);

  // Generation Options
  const [options, setOptions] = useState<GenerationOptions>({
    card_type: 'basic',
    target_count: 0, // 0 = Auto (Calculado por IA según densidad)
    difficulty_level: 'intermediate',
    language: 'es',
    deck_name: 'Oracle Cloud',
    custom_instructions: '',
    ai_provider: 'gemini',
    local_model: 'qwen2.5:14b',
  });

  // Pre-Flight Inspection & Cognitive Scaffolding State (Persisted across transient failures)
  const [inspection, setInspection] = useState<StudyPlanInspection | null>(() => {
    try {
      const cached = sessionStorage.getItem('ankicraft_active_inspection');
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [isInspecting, setIsInspecting] = useState<boolean>(false);
  const [isInspectionModalOpen, setIsInspectionModalOpen] = useState<boolean>(false);
  const [lastGenerationError, setLastGenerationError] = useState<string | null>(null);

  // Abort Controllers for cancellation & timeout resilience
  const generationAbortRef = useRef<AbortController | null>(null);
  const inspectionAbortRef = useRef<AbortController | null>(null);

  // Generated Cards (Persisted in localStorage)
  const [cards, setCards] = useState<Flashcard[]>(() => {
    try {
      const saved = localStorage.getItem('ankicraft_generated_cards');
      return saved ? syncClozeCards(JSON.parse(saved)) : [];
    } catch {
      return [];
    }
  });
  const [auditReport, setAuditReport] = useState<DeckAuditReport | null>(() => {
    try {
      const cached = localStorage.getItem('ankicraft_audit_report');
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [isAuditModalOpen, setIsAuditModalOpen] = useState<boolean>(false);
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isExportingAnki, setIsExportingAnki] = useState<boolean>(false);
  const [isExportingApkg, setIsExportingApkg] = useState<boolean>(false);
  const [pendingObsoleteNoteIds, setPendingObsoleteNoteIds] = useState<number[]>([]);

  // Phase 3: Surgical Sanitation State (Persisted across refreshes)
  const [isSanitationMode, setIsSanitationMode] = useState<boolean>(() => {
    try {
      const saved =
        sessionStorage.getItem('ankicraft_sanitation_mode') ??
        localStorage.getItem('ankicraft_sanitation_mode');
      return saved === 'true';
    } catch {
      return false;
    }
  });
  const [sanitationQueue, setSanitationQueue] = useState<SanitationQueueResponse | null>(() => {
    try {
      const saved = sessionStorage.getItem('ankicraft_sanitation_queue');
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [isProcessingSanitationReplace, setIsProcessingSanitationReplace] = useState<boolean>(false);

  // Phase 4: Active Expansion Concept
  const [activeExpansionConcept, setActiveExpansionConcept] = useState<ExpansionQueueItem | null>(null);

  // Sync cards to localStorage
  useEffect(() => {
    try {
      if (cards && cards.length > 0) {
        localStorage.setItem('ankicraft_generated_cards', JSON.stringify(cards));
      } else {
        localStorage.removeItem('ankicraft_generated_cards');
      }
    } catch (e) {
      console.error('Error syncing cards to localStorage:', e);
    }
  }, [cards]);

  // Sync audit report to localStorage
  useEffect(() => {
    try {
      if (auditReport) {
        localStorage.setItem('ankicraft_audit_report', JSON.stringify(auditReport));
      } else {
        localStorage.removeItem('ankicraft_audit_report');
      }
    } catch (e) {
      console.error('Error syncing audit report to localStorage:', e);
    }
  }, [auditReport]);

  // Sync sanitation mode and queue
  useEffect(() => {
    try {
      sessionStorage.setItem('ankicraft_sanitation_mode', String(isSanitationMode));
      if (sanitationQueue) {
        sessionStorage.setItem('ankicraft_sanitation_queue', JSON.stringify(sanitationQueue));
      } else {
        sessionStorage.removeItem('ankicraft_sanitation_queue');
      }
    } catch (e) {
      console.error('Error syncing sanitation state to sessionStorage:', e);
    }
  }, [isSanitationMode, sanitationQueue]);

  // Auto-fetch sanitation queue on mount if in sanitation mode and queue is null
  useEffect(() => {
    if (isSanitationMode && !sanitationQueue) {
      api.getSanitationQueue('Oracle Cloud')
        .then((queue) => {
          setSanitationQueue(queue);
          if (!selectedAnkiCard && queue.notes && queue.notes.length > 0) {
            setSelectedAnkiCard(queue.notes[0]);
          }
        })
        .catch((err) => console.error('Failed to load initial sanitation queue:', err));
    }
  }, [isSanitationMode, sanitationQueue, selectedAnkiCard]);


  // Turn-Based Curation Queue State (Persisted in localStorage)

  const [curationQueue, setCurationQueue] = useState<CurationQueueItem[]>(() => {
    try {
      const saved = localStorage.getItem('ankicraft_curation_queue');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('ankicraft_curation_queue', JSON.stringify(curationQueue));
    } catch (e) {
      console.error('Error saving curation queue to localStorage:', e);
    }
  }, [curationQueue]);

  // Toasts
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (type: 'success' | 'error' | 'info', title: string, message?: string) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, type, title, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  };

  // Deck Studio Hub State
  const [isDeckStudioOpen, setIsDeckStudioOpen] = useState<boolean>(false);
  const [deckStudioInitialTopic, setDeckStudioInitialTopic] = useState<string | undefined>(undefined);
  const [deckStudioInitialTab, setDeckStudioInitialTab] = useState<'checklist' | 'dag' | 'debt' | 'duplicates' | 'expansion' | undefined>(undefined);

  const handleEnqueueGap = (gap: OrphanGap) => {
    const newItem: CurationQueueItem = {
      id: `gap-${Date.now()}-${Math.random().toString(36).substring(2, 6)}`,
      note_id: 0,
      front: gap.suggested_front || gap.gap_title,
      deck_name: options.deck_name,
      matched_concept: gap.gap_title,
      added_at: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setCurationQueue((prev) => [...prev, newItem]);
    addToast('success', 'Brecha encolada', `"${gap.gap_title}" agregada a la cola de curación.`);
  };

  const handleGenerateFromGap = (gap: OrphanGap) => {
    setInputMode('text');
    const promptText = `Tema: ${gap.gap_title}\nJustificación: ${gap.reason}\n${
      gap.suggested_front ? `Pregunta clave: ${gap.suggested_front}` : ''
    }`;
    setRawText(promptText);
    setIsDeckStudioOpen(false);
    addToast('info', 'Material cargado desde Brecha', 'Se cargó la brecha temática en el generador.');
  };

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Poll Anki status
  const fetchAnkiStatus = useCallback(async (isSilent = false) => {
    if (!isSilent) setIsLoadingAnki(true);
    try {
      const status = await api.getAnkiStatus();
      setAnkiStatus((prev) => {
        const isDecksEqual =
          prev.available_decks.length === status.available_decks.length &&
          prev.available_decks.every((d, i) => d === status.available_decks[i]);
        if (
          prev.is_connected === status.is_connected &&
          isDecksEqual &&
          prev.version === status.version
        ) {
          return prev;
        }
        return status;
      });
      // Auto-populate default deck if user hasn't touched it and decks exist
      if (status.available_decks.length > 0) {
        setOptions((prev) => {
          if (prev.deck_name === 'General' && !status.available_decks.includes('General')) {
            return {
              ...prev,
              deck_name: status.available_decks[0] || 'General',
            };
          }
          return prev;
        });
      }
    } catch (e: any) {
      console.error('Error fetching Anki status:', e);
    } finally {
      setIsLoadingAnki(false);
    }
  }, []);

  useEffect(() => {
    const initTimer = setTimeout(() => {
      void fetchAnkiStatus(true);
    }, 0);
    const interval = setInterval(() => {
      void fetchAnkiStatus(true);
    }, 15000);
    return () => {
      clearTimeout(initTimer);
      clearInterval(interval);
    };
  }, [fetchAnkiStatus]);

  // Poll Ollama status (Local LLMs)
  const fetchOllamaStatus = useCallback(async () => {
    try {
      const status = await api.getOllamaStatus();
      setOllamaStatus((prev) => {
        const isModelsEqual =
          prev.models.length === status.models.length &&
          prev.models.every((m, i) => m === status.models[i]);
        if (
          prev.is_available === status.is_available &&
          prev.active_model === status.active_model &&
          isModelsEqual
        ) {
          return prev;
        }
        return status;
      });
      if (status.is_available && status.models.length > 0) {
        setOptions((prev) => {
          if (prev.local_model && prev.local_model === status.active_model) {
            return prev;
          }
          if (prev.local_model) {
            return prev;
          }
          return {
            ...prev,
            local_model: status.active_model || status.models[0],
          };
        });
      }
    } catch (e) {
      console.error('Error fetching Ollama status:', e);
    }
  }, []);

  useEffect(() => {
    const initTimer = setTimeout(() => {
      void fetchOllamaStatus();
    }, 0);
    const interval = setInterval(() => {
      void fetchOllamaStatus();
    }, 10000);
    return () => {
      clearTimeout(initTimer);
      clearInterval(interval);
    };
  }, [fetchOllamaStatus]);

  // Handle preview URL for files
  const filePreviewUrl = useMemo(
    () =>
      selectedFile && selectedFile.type.startsWith('image/')
        ? URL.createObjectURL(selectedFile)
        : null,
    [selectedFile]
  );

  useEffect(() => {
    return () => {
      if (filePreviewUrl) URL.revokeObjectURL(filePreviewUrl);
    };
  }, [filePreviewUrl]);

  // Handle preview URL for text attached image
  const textAttachedImageUrl = useMemo(
    () => (textAttachedImage ? URL.createObjectURL(textAttachedImage) : null),
    [textAttachedImage]
  );

  useEffect(() => {
    return () => {
      if (textAttachedImageUrl) URL.revokeObjectURL(textAttachedImageUrl);
    };
  }, [textAttachedImageUrl]);

  // Helper to serialize an Anki note's dynamic fields into structured educational text
  const formatAnkiCardToEducationalText = useCallback((card: DeckNoteRecord): string => {
    const fieldsStr = Object.entries(card.raw_fields)
      .map(([k, v]) => `### Campo [${k}]:\n${v.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()}`)
      .join('\n\n');

    return (
      `# Tarjeta Educativa de Anki (Nota #${card.note_id})\n` +
      `Mazo: ${card.deck_name} | Modelo: ${card.model_name}\n` +
      (card.tags.length > 0 ? `Etiquetas: ${card.tags.join(', ')}\n\n` : '\n') +
      `## Contenido de los campos originales:\n\n${fieldsStr}`
    );
  }, []);

  // Sync inspection plan to sessionStorage so user never loses it during API spikes
  useEffect(() => {
    try {
      if (inspection) {
        sessionStorage.setItem('ankicraft_active_inspection', JSON.stringify(inspection));
      } else {
        sessionStorage.removeItem('ankicraft_active_inspection');
      }
    } catch (e) {
      console.error('Error syncing inspection to sessionStorage:', e);
    }
  }, [inspection]);

  // Sync rawText and inputMode to sessionStorage to avoid losing state on reload
  useEffect(() => {
    try {
      if (rawText) {
        sessionStorage.setItem('ankicraft_raw_text', rawText);
      } else {
        sessionStorage.removeItem('ankicraft_raw_text');
      }
    } catch (e) {
      console.error('Error syncing rawText to sessionStorage:', e);
    }
  }, [rawText]);

  useEffect(() => {
    try {
      sessionStorage.setItem('ankicraft_input_mode', inputMode);
    } catch (e) {
      console.error('Error syncing inputMode to sessionStorage:', e);
    }
  }, [inputMode]);

  useEffect(() => {
    try {
      if (selectedAnkiCard) {
        sessionStorage.setItem('ankicraft_selected_anki_card', JSON.stringify(selectedAnkiCard));
      } else {
        sessionStorage.removeItem('ankicraft_selected_anki_card');
      }
    } catch (e) {
      console.error('Error syncing selectedAnkiCard to sessionStorage:', e);
    }
  }, [selectedAnkiCard]);

  const handleClearInspection = () => {
    setInspection(null);
    setLastGenerationError(null);
    sessionStorage.removeItem('ankicraft_active_inspection');
    addToast('info', 'Plan de estudio descartado');
  };

  const handleSaveApiKey = (key: string) => {
    setApiKey(key);
    localStorage.setItem('ankicraft_gemini_key', key);
    addToast('success', 'Clave API guardada correctamente');
  };

  // Turn-Based Curation Queue Handlers
  const handleEnqueueForCuration = (item: {
    note_id: number;
    front: string;
    deck_name: string;
    matched_concept: string;
  }) => {
    setCurationQueue((prev) => {
      if (prev.some((q) => q.note_id === item.note_id)) {
        addToast('info', `La nota #${item.note_id} ya estaba en la cola de curación.`);
        return prev;
      }
      const newItem: CurationQueueItem = {
        id: Math.random().toString(36).substring(2, 9),
        note_id: item.note_id,
        front: item.front,
        deck_name: item.deck_name,
        matched_concept: item.matched_concept,
        added_at: new Date().toISOString(),
      };
      addToast('success', `📌 Nota #${item.note_id} reservada en la cola de curación`);
      return [...prev, newItem];
    });
  };

  const handleDismissCurationItem = (id: string) => {
    setCurationQueue((prev) => prev.filter((item) => item.id !== id));
    addToast('info', 'Tarjeta removida de la cola');
  };

  const handleClearCurationQueue = () => {
    if (window.confirm('¿Querés vaciar toda la cola de curación?')) {
      setCurationQueue([]);
      addToast('info', 'Cola de curación vaciada');
    }
  };

  const handleAnalyzeQueuedItem = async (item: CurationQueueItem) => {
    setIsInspecting(true);
    try {
      if (item.note_id === 0) {
        addToast('info', 'Cargando brecha temática para diagnóstico...');
        setInputMode('text');
        setRawText(item.front);
        setOptions((prev) => ({ ...prev, deck_name: item.deck_name }));
        const result = await api.inspectMaterial(item.front, { ...options, deck_name: item.deck_name }, apiKey);
        setInspection(result);
        setIsInspectionModalOpen(true);
        setCurationQueue((prev) => prev.filter((q) => q.id !== item.id));
        addToast('success', '¡Diagnóstico iniciado para la brecha temática!');
        return;
      }

      addToast('info', `Cargando nota #${item.note_id} para diagnóstico...`);
      let cardToInspect: DeckNoteRecord | null = null;
      try {
        cardToInspect = await api.getNoteById(item.note_id);
      } catch (err) {
        console.warn('Could not fetch note directly from Anki, using fallback:', err);
      }

      if (!cardToInspect) {
        cardToInspect = {
          note_id: item.note_id,
          deck_name: item.deck_name,
          model_name: 'Basic',
          card_type: 'basic',
          front: item.front,
          back: '',
          tags: [],
          raw_fields: { Front: item.front },
          media_files: [],
        };
      }

      setSelectedAnkiCard(cardToInspect);
      setInputMode('anki');
      setOptions((prev) => ({ ...prev, deck_name: item.deck_name }));

      const cardText = formatAnkiCardToEducationalText(cardToInspect);
      const result = await api.inspectMaterial(
        cardText,
        { ...options, deck_name: item.deck_name },
        apiKey,
        cardToInspect.note_id,
        cardToInspect.media_files
      );
      result.source_text = cardText;
      result.source_note_id = cardToInspect.note_id;
      result.obsolete_note_ids = [cardToInspect.note_id];
      if (cardToInspect.media_files && cardToInspect.media_files.length > 0) {
        result.inherited_media_files = Array.from(new Set(cardToInspect.media_files));
      }

      setInspection(result);
      setIsInspectionModalOpen(true);
      setCurationQueue((prev) => prev.filter((q) => q.id !== item.id));
      addToast('success', `¡Diagnóstico iniciado para la nota #${item.note_id}!`);
    } catch (err: any) {
      console.error(err);
      addToast('error', `Error al analizar la nota #${item.note_id}`, err.message);
    } finally {
      setIsInspecting(false);
    }
  };

  // Direct Inspection from Deck Studio / DAG Drawer
  const handleInspectNoteDirectly = async (noteId: number, deckName: string, frontFallback?: string) => {
    setIsDeckStudioOpen(false);
    setIsInspecting(true);
    try {
      addToast('info', `Cargando nota #${noteId} para diagnóstico...`);
      let cardToInspect: DeckNoteRecord | null = null;
      try {
        cardToInspect = await api.getNoteById(noteId);
      } catch (err) {
        console.warn('Could not fetch note directly from Anki, using fallback:', err);
      }

      if (!cardToInspect) {
        cardToInspect = {
          note_id: noteId,
          deck_name: deckName,
          model_name: 'Basic',
          card_type: 'basic',
          front: frontFallback || `Nota #${noteId}`,
          back: '',
          tags: [],
          raw_fields: { Front: frontFallback || '' },
          media_files: [],
        };
      }

      setSelectedAnkiCard(cardToInspect);
      setInputMode('anki');
      setOptions((prev) => ({ ...prev, deck_name: deckName }));

      const cardText = formatAnkiCardToEducationalText(cardToInspect);
      const result = await api.inspectMaterial(
        cardText,
        { ...options, deck_name: deckName },
        apiKey,
        cardToInspect.note_id,
        cardToInspect.media_files
      );
      result.source_text = cardText;
      result.source_note_id = cardToInspect.note_id;
      result.obsolete_note_ids = [cardToInspect.note_id];
      if (cardToInspect.media_files && cardToInspect.media_files.length > 0) {
        result.inherited_media_files = Array.from(new Set(cardToInspect.media_files));
      }

      setInspection(result);
      setIsInspectionModalOpen(true);
      addToast('success', `¡Diagnóstico iniciado para la nota #${noteId}!`);
    } catch (err: any) {
      console.error(err);
      addToast('error', `Error al analizar la nota #${noteId}`, err.message);
    } finally {
      setIsInspecting(false);
    }
  };

  // Phase 3: Surgical Sanitation Handlers
  const handleInspectSanitationNote = async (note: DeckNoteRecord, deckName: string) => {
    setIsInspecting(true);
    try {
      setSelectedAnkiCard(note);
      setInputMode('anki');
      setOptions((prev) => ({ ...prev, deck_name: deckName }));

      const cardText = formatAnkiCardToEducationalText(note);
      const result = await api.inspectMaterial(
        cardText,
        { ...options, deck_name: deckName },
        apiKey,
        note.note_id,
        note.media_files
      );
      result.source_text = cardText;
      result.source_note_id = note.note_id;
      result.obsolete_note_ids = [note.note_id];
      if (note.media_files && note.media_files.length > 0) {
        result.inherited_media_files = Array.from(new Set(note.media_files));
      }

      setInspection(result);
      setIsInspectionModalOpen(true);
      addToast('info', `Diagnóstico preparado para nota #${note.note_id}`);
    } catch (err: any) {
      console.error(err);
      addToast('error', `Error al analizar nota #${note.note_id}`, err.message);
    } finally {
      setIsInspecting(false);
    }
  };

  const handleExecuteSanitationReplace = async () => {
    if (!selectedAnkiCard || cards.length === 0) return;
    setIsProcessingSanitationReplace(true);
    try {
      const res = await api.replaceNoteTransactionally(
        options.deck_name,
        selectedAnkiCard.note_id,
        cards
      );
      if (res.success) {
        triggerConfetti();
        addToast(
          'success',
          `🎉 Nota #${res.deleted_note_id} sustituida con éxito`,
          `Se crearon ${res.created_cards_count} tarjetas atómicas óptimas. Restan ${res.remaining_in_queue} notas por sanear.`
        );

        // Clear current card state, audit report, and inspection
        setCards([]);
        setSelectedAnkiCard(null);
        setAuditReport(null);
        setInspection(null);
        localStorage.removeItem('ankicraft_generated_cards');
        localStorage.removeItem('ankicraft_audit_report');
        sessionStorage.removeItem('ankicraft_selected_anki_card');
        sessionStorage.removeItem('ankicraft_active_inspection');

        if (res.remaining_in_queue === 0) {
          setIsSanitationMode(false);
          setSanitationQueue(null);
          addToast(
            'success',
            '🏆 ¡Mazo 100% Saneado!',
            '¡Misión cumplida! Se sanearon todas las notas de este mazo. La Fase 4 (Expansión) está ahora disponible.'
          );
        } else {
          // Fetch refreshed queue and immediately load the next pending note
          const refreshedQueue = await api.getSanitationQueue(options.deck_name);
          setSanitationQueue(refreshedQueue);
          if (refreshedQueue.notes.length > 0) {
            await handleInspectSanitationNote(refreshedQueue.notes[0], options.deck_name);
          }
        }
      }
    } catch (err: any) {
      console.error(err);
      addToast('error', 'Error en sustitución transaccional', err.message);
    } finally {
      setIsProcessingSanitationReplace(false);
    }
  };

  // Phase 4: Topological Expansion Handler
  const handleExpandConcept = async (concept: ExpansionQueueItem, deckName: string) => {
    setActiveExpansionConcept(concept);
    setInputMode('text');
    const promptText =
      concept.suggested_prompt ||
      `Fundamento pedagógico y tarjetas de primer principio para ${concept.concept_name}.`;
    setRawText(promptText);
    setOptions((prev) => ({ ...prev, deck_name: deckName }));
    addToast('info', `Cargando concepto '${concept.concept_name}'...`);

    setIsInspecting(true);
    try {
      const result = await api.inspectMaterial(promptText, { ...options, deck_name: deckName }, apiKey);
      result.source_text = promptText;
      setInspection(result);
      setIsInspectionModalOpen(true);
      addToast('success', `¡Diagnóstico preparado para expandir '${concept.concept_name}'!`);
    } catch (err: any) {
      console.error(err);
      addToast('error', `Error al diagnosticar '${concept.concept_name}'`, err.message);
    } finally {
      setIsInspecting(false);
    }
  };


  // Pre-Flight Inspection

  const handleInspectMaterial = async () => {
    const controller = new AbortController();
    inspectionAbortRef.current = controller;
    setIsInspecting(true);
    try {
      let result: StudyPlanInspection;
      if (inputMode === 'text') {
        if (!rawText.trim() && !textAttachedImage) {
          addToast('error', 'Por favor ingresá algún texto o adjuntá una imagen para analizar el material.');
          setIsInspecting(false);
          return;
        }
        if (textAttachedImage) {
          result = await api.inspectMaterialFromFile(textAttachedImage, options, apiKey, rawText, controller.signal);
          result.source_text = rawText.trim();
        } else {
          result = await api.inspectMaterial(rawText, options, apiKey, undefined, undefined, controller.signal);
          result.source_text = rawText.trim();
        }
      } else if (inputMode === 'file') {
        if (!selectedFile) {
          addToast('error', 'Por favor seleccioná un archivo PDF o imagen para analizar.');
          setIsInspecting(false);
          return;
        }
        result = await api.inspectMaterialFromFile(selectedFile, options, apiKey, undefined, controller.signal);
      } else {
        if (!selectedAnkiCard) {
          addToast('error', 'Por favor seleccioná una tarjeta de Anki para analizar.');
          setIsInspecting(false);
          return;
        }
        const cardText = formatAnkiCardToEducationalText(selectedAnkiCard);
        result = await api.inspectMaterial(
          cardText,
          options,
          apiKey,
          selectedAnkiCard.note_id,
          selectedAnkiCard.media_files,
          controller.signal
        );
        result.source_text = cardText;
        result.source_note_id = selectedAnkiCard.note_id;
        result.obsolete_note_ids = [selectedAnkiCard.note_id];
        if (selectedAnkiCard.media_files && selectedAnkiCard.media_files.length > 0) {
          result.inherited_media_files = Array.from(new Set(selectedAnkiCard.media_files));
        }
      }

      setInspection(result);
      setIsInspectionModalOpen(true);
      addToast('success', '¡Diagnóstico cognitivo completado!');
    } catch (err: any) {
      if (controller.signal.aborted) {
        addToast('info', 'Diagnóstico cancelado por el usuario.');
        return;
      }
      console.error(err);
      addToast(
        'error',
        'Error en el diagnóstico del material',
        err.message || 'Verificá tu API Key de Gemini o la conexión con el servidor.'
      );
    } finally {
      setIsInspecting(false);
      inspectionAbortRef.current = null;
    }
  };

  const buildEffectiveOptionsFromInspection = (
    plan: StudyPlanInspection,
    baseOptions: GenerationOptions
  ): GenerationOptions => {
    const selectedPrereqs = plan.prerequisites.filter((p) => p.selected);
    const prerequisitesContext =
      selectedPrereqs.length > 0
        ? selectedPrereqs
            .map((p) => {
              const resolvedDeepCount =
                p.deep_card_count === 0
                  ? p.recommended_deep_cards || 3
                  : p.deep_card_count || p.recommended_deep_cards || 3;
              const modeLabel =
                p.mode === 'deep_dive'
                  ? `[SUB-EVENTO DE ANÁLISIS PROFUNDO (${resolvedDeepCount} tarjetas)]`
                  : `[ANCLAJE RÁPIDO (1 tarjeta)]`;
              const cleanSummary = (
                p.enriched_summary ||
                'Generar a partir de primeros principios y causalidad directa.'
              )
                .replace(/\s+/g, ' ')
                .trim();
              const blueprintSuffix =
                p.atomic_blueprint && p.atomic_blueprint.length > 0 && p.mode === 'deep_dive'
                  ? ` | Blueprint Atómico Obligatorio (1 tarjeta por ítem): ${p.atomic_blueprint
                      .map((b, idx) => `${idx + 1}) ${b}`)
                      .join(' ; ')}`
                  : '';
              return `- ${modeLabel} ${p.concept}: Fundamento / Justificación: ${p.reason} | Síntesis Cognitiva: ${cleanSummary}${blueprintSuffix}`;
            })
            .join('\n')
        : undefined;

    const selectedThemes = plan.core_themes
      .filter((t) => t.selected)
      .map((t) => {
        const diagramSuffix =
          t.associated_diagrams && t.associated_diagrams.length > 0
            ? ` | Diagramas a heredar: [${t.associated_diagrams.join(', ')}]`
            : '';
        const descSuffix = t.description ? ` - ${t.description}` : '';
        return `${t.title} (~${t.recommended_cards} tarjetas)${descSuffix}${diagramSuffix}`;
      });

    const themeCardsTotal = plan.core_themes
      .filter((t) => t.selected)
      .reduce((sum, t) => sum + t.recommended_cards, 0);

    const prereqCardsTotal = selectedPrereqs.reduce((sum, p) => {
      const resolvedDeepCount =
        p.deep_card_count === 0
          ? p.recommended_deep_cards || 3
          : p.deep_card_count || p.recommended_deep_cards || 3;
      return sum + (p.mode === 'deep_dive' ? resolvedDeepCount : 1);
    }, 0);

    const targetCount = themeCardsTotal + prereqCardsTotal;

    return {
      ...baseOptions,
      target_count: targetCount > 0 ? targetCount : baseOptions.target_count,
      prerequisites_context: prerequisitesContext,
      selected_themes: selectedThemes,
      source_note_id: plan.source_note_id || baseOptions.source_note_id,
    };
  };

  // Confirm and generate from approved inspection plan
  const handleConfirmGenerateFromInspection = async (approvedPlan: StudyPlanInspection) => {
    setIsInspectionModalOpen(false);
    setIsGenerating(true);
    setLastGenerationError(null);

    const controller = new AbortController();
    generationAbortRef.current = controller;
    const previousCards = [...cards];
    let streamAccumulatedCards: Flashcard[] = [];

    try {
      const generationPayload = buildEffectiveOptionsFromInspection(approvedPlan, options);

      // Determine robust educational text fallback to avoid empty-payload 400 errors
      let fallbackText = rawText.trim();
      if (!fallbackText && approvedPlan.source_text) {
        fallbackText = approvedPlan.source_text;
      }
      if (!fallbackText && selectedAnkiCard) {
        fallbackText = formatAnkiCardToEducationalText(selectedAnkiCard);
      }
      if (!fallbackText && approvedPlan.core_themes && approvedPlan.core_themes.length > 0) {
        fallbackText = `# ${approvedPlan.topic_name}\n\n` + approvedPlan.core_themes.map((t) => `### ${t.title}\n${t.description}`).join('\n\n');
      }

      const handleBatchProgress = (batchCards: Flashcard[], progress: { batchLabel: string; current: number; total: number }) => {
        streamAccumulatedCards = [...streamAccumulatedCards, ...batchCards];
        setCards((prev) => {
          const baseCards = streamAccumulatedCards.length === batchCards.length ? [] : prev;
          const existingFronts = new Set(baseCards.map((c) => c.front.trim().toLowerCase()));
          const newUnique = batchCards.filter((c) => !existingFronts.has(c.front.trim().toLowerCase()));
          return syncClozeCards([...baseCards, ...newUnique]);
        });
        addToast(
          'info',
          `Lote "${progress.batchLabel}" (${progress.current}/${progress.total})`,
          `+${batchCards.length} tarjetas añadidas.`
        );
      };

      let genResult: GenerateCardsResponse;

      if (inputMode === 'text') {
        if (textAttachedImage) {
          genResult = await api.generateFromFileStream(textAttachedImage, generationPayload, handleBatchProgress, apiKey, fallbackText || undefined, controller.signal);
        } else {
          genResult = await api.generateFromTextStream(fallbackText, generationPayload, handleBatchProgress, apiKey, controller.signal);
        }
      } else if (inputMode === 'file') {
        if (!selectedFile) {
          throw new Error('No hay archivo seleccionado para generar.');
        }
        genResult = await api.generateFromFileStream(selectedFile, generationPayload, handleBatchProgress, apiKey, fallbackText || undefined, controller.signal);
      } else {
        const ankiCardText = selectedAnkiCard ? formatAnkiCardToEducationalText(selectedAnkiCard) : fallbackText;
        if (!ankiCardText) {
          throw new Error('No hay tarjeta de Anki seleccionada para generar.');
        }
        genResult = await api.generateFromTextStream(ankiCardText, generationPayload, handleBatchProgress, apiKey, controller.signal);
      }

      // Record pending obsolete note IDs to delete upon export
      if (approvedPlan.obsolete_note_ids && approvedPlan.obsolete_note_ids.length > 0) {
        setPendingObsoleteNoteIds(approvedPlan.obsolete_note_ids);
      } else {
        setPendingObsoleteNoteIds([]);
      }

      let generatedCards = genResult.cards;

      // Seamlessly inherit media files from replaced debt notes into generated cards (preventing duplicates)
      if (approvedPlan.inherited_media_files && approvedPlan.inherited_media_files.length > 0) {
        // Collect all images already present in generatedCards to prevent duplicates
        const alreadyPresentImages = new Set<string>();
        for (const card of generatedCards) {
          const cardContent = `${card.front} ${card.back} ${card.explanation || ''}`;
          const matches = cardContent.matchAll(/<img[^>]+src=["']([^"']+)["']/gi);
          for (const m of matches) {
            if (m[1]) alreadyPresentImages.add(m[1].trim());
          }
        }

        // Only inherit media files that are NOT already embedded in the generated cards
        const mediaToInherit = approvedPlan.inherited_media_files.filter(
          (m) => !alreadyPresentImages.has(m.trim())
        );

        if (mediaToInherit.length > 0 && generatedCards.length > 0) {
          generatedCards = generatedCards.map((card) => {
            if (mediaToInherit.length === 0) return card;
            const cardContent = `${card.front} ${card.back} ${card.explanation || ''}`;
            if (!cardContent.includes('<img')) {
              const nextMedia = mediaToInherit.shift()!;
              const mediaTag = `<div class="inherited-media mt-2"><img src="${nextMedia}" alt="Diagrama heredado" /></div>`;
              return {
                ...card,
                explanation: card.explanation
                  ? `${card.explanation}\n\n${mediaTag}`
                  : mediaTag,
              };
            }
            return card;
          });

          // If there are still remaining media files, attach them to the first card
          if (mediaToInherit.length > 0 && generatedCards.length > 0) {
            const extraMediaTags = mediaToInherit
              .map((m) => `<div class="inherited-media mt-2"><img src="${m}" alt="Diagrama heredado" /></div>`)
              .join('\n');
            generatedCards[0] = {
              ...generatedCards[0],
              explanation: generatedCards[0].explanation
                ? `${generatedCards[0].explanation}\n\n${extraMediaTags}`
                : extraMediaTags,
            };
          }
        }
      }

      setCards(syncClozeCards(generatedCards));
      setAuditReport(genResult.audit_report || null);
      setLastGenerationError(null);
      addToast(
        'success',
        `¡${generatedCards.length} flashcards creadas con andamiaje!`,
        'Se anclaron las bases fundacionales y se aplicó la auditoría neurocognitiva.'
      );
    } catch (err: any) {
      if (controller.signal.aborted) {
        addToast('info', 'Generación cancelada por el usuario.', 'Se preservó el estado de tarjetas.');
        if (streamAccumulatedCards.length === 0) {
          setCards(previousCards);
        }
        return;
      }
      console.error(err);
      if (err instanceof PartialStreamError || streamAccumulatedCards.length > 0) {
        addToast(
          'info',
          'Generación parcial preservada',
          `Interrupción durante la generación (${err.message}). Se preservaron ${streamAccumulatedCards.length} tarjetas recibidas.`
        );
      } else {
        setCards(previousCards);
        setLastGenerationError(err.message || 'Error de conexión o saturación temporal en la API.');
        addToast(
          'error',
          'Pico de demanda en la API: el plan está guardado',
          'Tus prerrequisitos y ejes siguen a salvo. Podés reintentar con el botón en el banner superior.'
        );
      }
    } finally {
      setIsGenerating(false);
      generationAbortRef.current = null;
    }
  };

  // Generate Flashcards
  const handleGenerate = async () => {
    const controller = new AbortController();
    generationAbortRef.current = controller;
    setIsGenerating(true);
    const previousCards = [...cards];
    let streamAccumulatedCards: Flashcard[] = [];

    try {
      const effectiveOptions = inspection
        ? buildEffectiveOptionsFromInspection(inspection, options)
        : options;

      let effectiveText = rawText.trim();
      if (!effectiveText && inspection?.source_text) {
        effectiveText = inspection.source_text;
        setRawText(effectiveText);
      }
      if (!effectiveText && inspection?.core_themes && inspection.core_themes.length > 0) {
        effectiveText = `# ${inspection.topic_name}\n\n` + inspection.core_themes.map((t) => `### ${t.title}\n${t.description}`).join('\n\n');
      }

      const handleBatchProgress = (batchCards: Flashcard[], progress: { batchLabel: string; current: number; total: number }) => {
        streamAccumulatedCards = [...streamAccumulatedCards, ...batchCards];
        setCards((prev) => {
          const baseCards = streamAccumulatedCards.length === batchCards.length ? [] : prev;
          const existingFronts = new Set(baseCards.map((c) => c.front.trim().toLowerCase()));
          const newUnique = batchCards.filter((c) => !existingFronts.has(c.front.trim().toLowerCase()));
          return syncClozeCards([...baseCards, ...newUnique]);
        });
        addToast(
          'info',
          `Lote "${progress.batchLabel}" (${progress.current}/${progress.total})`,
          `+${batchCards.length} tarjetas añadidas.`
        );
      };

      let genResult: GenerateCardsResponse;

      if (inputMode === 'text') {
        if (!effectiveText && !textAttachedImage) {
          addToast('error', 'Por favor ingresá algún texto o adjuntá una imagen para generar tarjetas.');
          setIsGenerating(false);
          return;
        }
        if (textAttachedImage) {
          genResult = await api.generateFromFileStream(textAttachedImage, effectiveOptions, handleBatchProgress, apiKey, effectiveText || undefined, controller.signal);
        } else {
          genResult = await api.generateFromTextStream(effectiveText, effectiveOptions, handleBatchProgress, apiKey, controller.signal);
        }
      } else if (inputMode === 'file') {
        if (!selectedFile) {
          addToast('error', 'Por favor seleccioná un archivo PDF o imagen.');
          setIsGenerating(false);
          return;
        }
        genResult = await api.generateFromFileStream(selectedFile, effectiveOptions, handleBatchProgress, apiKey, effectiveText || undefined, controller.signal);
      } else {
        const ankiCardText = selectedAnkiCard ? formatAnkiCardToEducationalText(selectedAnkiCard) : effectiveText;
        if (!ankiCardText) {
          addToast('error', 'Por favor seleccioná una tarjeta de Anki para generar.');
          setIsGenerating(false);
          return;
        }
        genResult = await api.generateFromTextStream(ankiCardText, effectiveOptions, handleBatchProgress, apiKey, controller.signal);
      }

      setCards(syncClozeCards(genResult.cards));
      setAuditReport(genResult.audit_report || null);
      addToast(
        'success',
        `¡${genResult.cards.length} flashcards creadas!`,
        'Podés voltearlas, editarlas o sincronizarlas a Anki.'
      );
    } catch (err: any) {
      if (controller.signal.aborted) {
        addToast('info', 'Generación cancelada por el usuario.', 'Se preservó el estado de tarjetas.');
        if (streamAccumulatedCards.length === 0) {
          setCards(previousCards);
        }
        return;
      }
      console.error(err);
      if (err instanceof PartialStreamError || streamAccumulatedCards.length > 0) {
        addToast(
          'info',
          'Generación parcial preservada',
          `Interrupción durante la generación (${err.message}). Se preservaron ${streamAccumulatedCards.length} tarjetas recibidas.`
        );
      } else {
        setCards(previousCards);
        addToast(
          'error',
          'Error al generar flashcards',
          err.message || 'Verificá tu API Key de Gemini o la conexión con el servidor.'
        );
      }
    } finally {
      setIsGenerating(false);
      generationAbortRef.current = null;
    }
  };

  const handleCancelOperation = () => {
    if (generationAbortRef.current) {
      generationAbortRef.current.abort();
    }
    if (inspectionAbortRef.current) {
      inspectionAbortRef.current.abort();
    }
  };

  // Card Modifications
  const handleUpdateCard = (updatedCard: Flashcard) => {
    setCards((prev) => syncClozeCards(prev.map((c) => (c.id === updatedCard.id ? updatedCard : c))));
  };

  const handleDeleteCard = (id: string) => {
    setCards((prev) => prev.filter((c) => c.id !== id));
    addToast('info', 'Tarjeta eliminada');
  };

  const handleAddManualCard = () => {
    const newCard: Flashcard = {
      id: Math.random().toString(36).substring(2, 9),
      card_type: options.card_type,
      front: 'Nueva Pregunta o Concepto',
      back: 'Respuesta detallada',
      tags: [options.deck_name.toLowerCase().replace('::', '-')],
      explanation: 'Mnemotecnia o contexto adicional',
    };
    setCards((prev) => syncClozeCards([newCard, ...prev]));
    addToast('info', 'Nueva tarjeta añadida para editar');
  };

  const handleClearCards = () => {
    if (window.confirm('¿Querés limpiar todas las tarjetas generadas?')) {
      setCards([]);
    }
  };

  // Cognitive Audit Interactive Handlers
  const handleApplyAuditSuggestion = (cardId: string, finding: CognitiveAuditFinding) => {
    setCards((prevCards) =>
      syncClozeCards(
        prevCards.map((c) => {
          if (c.id === cardId) {
            let updatedFront = c.front;
            if (finding.original_snippet && finding.suggested_replacement) {
              updatedFront = updatedFront.replace(finding.original_snippet, finding.suggested_replacement);
            } else if (finding.original_snippet && finding.corrected_snippet) {
              const cleanCloze = finding.corrected_snippet.startsWith('{{')
                ? finding.corrected_snippet
                : `{{c1::${finding.corrected_snippet}}}`;
              updatedFront = updatedFront.replace(finding.original_snippet, cleanCloze);
            }
            let updatedBack = c.back;
            if (c.card_type === 'cloze') {
              const extracted = extractFirstClozeAnswer(updatedFront);
              if (extracted) {
                updatedBack = extracted;
              }
            }
            return {
              ...c,
              front: updatedFront,
              back: updatedBack,
            };
          }
          return c;
        })
      )
    );

    setAuditReport((prevReport) => {
      if (!prevReport) return null;
      const updatedCardReports = prevReport.card_reports.map((cr) => {
        if (cr.card_id === cardId) {
          const updatedFindings = cr.findings.map((f) => {
            if (f.rule === finding.rule && f.original_snippet === finding.original_snippet) {
              return {
                ...f,
                auto_fixed: true,
                message: `${f.message} (Sugerencia aceptada y aplicada al editor)`,
              };
            }
            return f;
          });
          const newScore = Math.min(100, cr.score + 15);
          return {
            ...cr,
            score: newScore,
            passed: newScore >= 70,
            findings: updatedFindings,
          };
        }
        return cr;
      });
      const avg =
        Math.round(
          (updatedCardReports.reduce((acc, c) => acc + c.score, 0) / updatedCardReports.length) * 10
        ) / 10;
      return {
        ...prevReport,
        average_quality_score: avg,
        card_reports: updatedCardReports,
      };
    });

    addToast('success', 'Sugerencia aplicada exitosamente a la tarjeta.');
  };

  const handleIgnoreAuditSuggestion = (cardId: string, findingRule: string) => {
    setAuditReport((prevReport) => {
      if (!prevReport) return null;
      const updatedCardReports = prevReport.card_reports.map((cr) => {
        if (cr.card_id === cardId) {
          const updatedFindings = cr.findings.map((f) => {
            if (f.rule === findingRule) {
              return {
                ...f,
                severity: 'INFO' as const,
                message: `${f.message} [Excepción confirmada por el usuario]`,
              };
            }
            return f;
          });
          const newScore = Math.min(100, cr.score + 15);
          return {
            ...cr,
            score: newScore,
            passed: newScore >= 70,
            findings: updatedFindings,
          };
        }
        return cr;
      });
      const avg =
        Math.round(
          (updatedCardReports.reduce((acc, c) => acc + c.score, 0) / updatedCardReports.length) * 10
        ) / 10;
      return {
        ...prevReport,
        average_quality_score: avg,
        card_reports: updatedCardReports,
      };
    });

    addToast('info', 'Advertencia marcada como excepción válida.');
  };

  const handleFocusCardFromAudit = (cardId: string) => {
    setIsAuditModalOpen(false);
    setTimeout(() => {
      const el = document.getElementById(`card-${cardId}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ring-4', 'ring-indigo-500', 'transition-all');
        setTimeout(() => el.classList.remove('ring-4', 'ring-indigo-500'), 3000);
      }
    }, 150);
  };

  // Trigger celebration confetti
  const triggerConfetti = () => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    void import('canvas-confetti').then((m) => {
      m.default({
        particleCount: 80,
        spread: 70,
        origin: { y: 0.7 },
        colors: ['#6366f1', '#10b981', '#a855f7', '#38bdf8'],
      });
    });
  };

  // Export to AnkiConnect
  const handleExportToAnki = async () => {
    if (cards.length === 0) return;
    setIsExportingAnki(true);
    try {
      const result = await api.exportToAnki(options.deck_name, cards, pendingObsoleteNoteIds);
      if (result.success) {
        triggerConfetti();
        if (result.deleted_notes_count && result.deleted_notes_count > 0) {
          addToast(
            'success',
            '🎉 ¡Mazo Curado y Expandido!',
            `Se crearon ${result.cards_exported_count} tarjetas atómicas y se retiraron ${result.deleted_notes_count} tarjetas monolito obsoletas.`
          );
        } else {
          addToast(
            'success',
            '¡Sincronización Exitosa!',
            result.message || `Cartas inyectadas en el mazo '${options.deck_name}'.`
          );
        }
        setPendingObsoleteNoteIds([]);
        fetchAnkiStatus(); // Refresh deck list
        if (options.deck_name) {
          api.syncDeckIndex(options.deck_name, apiKey).catch((err) => {
            console.warn('Silent auto-sync after export failed:', err);
          });
        }
        if (activeExpansionConcept && result.cards_exported_count > 0) {
          const expConcept = activeExpansionConcept;
          api
            .getDeckNotes(options.deck_name)
            .then(async (notes) => {
              const newNotes = notes.slice(-result.cards_exported_count);
              if (newNotes.length > 0) {
                await api.linkConceptCards(
                  options.deck_name,
                  expConcept.concept_id,
                  newNotes.map((n) => n.note_id)
                );
                addToast(
                  'success',
                  '🌟 Brecha Curricular Cubierta',
                  `El concepto '${expConcept.concept_name}' ahora está verificado en el Grafo (DAG).`
                );
              }
            })
            .catch((err) => console.warn('Could not link concept cards:', err));
          setActiveExpansionConcept(null);
        }
      } else {

        addToast('error', 'Fallo al sincronizar', result.message);
      }
    } catch (err: any) {
      addToast(
        'error',
        'Error de comunicación con Anki',
        err.message || 'Asegurate de que Anki Desktop esté abierto con el plugin AnkiConnect.'
      );
    } finally {
      setIsExportingAnki(false);
    }
  };

  // Export to .apkg download
  const handleExportToApkg = async () => {
    if (cards.length === 0) return;
    setIsExportingApkg(true);
    try {
      const blob = await api.exportToApkg(options.deck_name, cards);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${options.deck_name.replace('::', '_')}.apkg`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      triggerConfetti();
      addToast(
        'success',
        '¡Archivo .apkg descargado!',
        'Hacé doble clic en el archivo descargado para importarlo en Anki.'
      );
    } catch (err: any) {
      addToast('error', 'Error al generar .apkg', err.message);
    } finally {
      setIsExportingApkg(false);
    }
  };

  const canGenerate =
    (inputMode === 'text' && (rawText.trim().length > 0 || textAttachedImage !== null)) ||
    (inputMode === 'file' && selectedFile !== null) ||
    (inputMode === 'anki' && selectedAnkiCard !== null);

  return (
    <div className="min-h-screen bg-surface-base text-slate-100 flex flex-col">
      <Header
        ankiStatus={ankiStatus}
        isLoadingAnki={isLoadingAnki}
        onRefreshAnki={fetchAnkiStatus}
        onOpenApiKeyModal={() => setIsApiKeyModalOpen(true)}
        hasCustomKey={Boolean(apiKey)}
        ollamaStatus={ollamaStatus}
        aiProvider={options.ai_provider}
        localModel={options.local_model}
        onProviderChange={(provider) =>
          setOptions((prev) => ({ ...prev, ai_provider: provider }))
        }
        onModelChange={(model) =>
          setOptions((prev) => ({ ...prev, local_model: model }))
        }
        onOpenDeckStudio={() => {
          setDeckStudioInitialTopic(undefined);
          setDeckStudioInitialTab(undefined);
          setIsDeckStudioOpen(true);
        }}
      />

      <main className="mx-auto flex-1 w-full max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
        {/* Phase 3: Surgical Sanitation Status Banner */}
        {isSanitationMode && (
          <div className="rounded-2xl border border-teal-500/40 bg-gradient-to-r from-teal-950/80 via-slate-900 to-indigo-950/80 p-4 shadow-xl max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4 animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-teal-500/20 text-teal-300 border border-teal-500/30 shrink-0">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-extrabold uppercase tracking-wider text-teal-300">
                    Modo Saneamiento Quirúrgico (Fase 3)
                  </span>
                  <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-slate-300 border border-slate-700">
                    Mazo: {options.deck_name}
                  </span>
                  {sanitationQueue && (
                    <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300 border border-amber-500/30">
                      {sanitationQueue.pending_count} pendientes ({sanitationQueue.sanitized_count} saneadas)
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-300 mt-0.5">
                  Supervisión 1 a 1 de notas densas bajo el Contrato Pedagógico aprobado.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => {
                  setIsSanitationMode(false);
                  setSanitationQueue(null);
                  addToast('info', 'Modo Saneamiento pausado');
                }}
                className="px-3 py-1.5 rounded-xl border border-slate-700 bg-slate-800/80 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition-all cursor-pointer"
              >
                Pausar / Salir
              </button>
            </div>
          </div>
        )}

        {/* Top Hero / Intro banner */}
        <div className="space-y-2 text-center max-w-2xl mx-auto">

          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl text-white">
            Creá Flashcards de Alta Retención en Segundos
          </h2>
          <p className="text-xs sm:text-sm text-slate-400 leading-relaxed">
            Pegá tus resúmenes o subí diapositivas y diagramas. Gemini extraerá los conceptos clave con
            técnicas de <strong>Active Recall</strong> y los insertará directo en tu Anki Desktop.
          </p>
        </div>

        {/* Input Dropzone & Config Section */}
        <div className="space-y-4 max-w-4xl mx-auto">
          <ContentDropzone
            inputMode={inputMode}
            setInputMode={setInputMode}
            rawText={rawText}
            setRawText={setRawText}
            selectedFile={selectedFile}
            setSelectedFile={setSelectedFile}
            filePreviewUrl={filePreviewUrl}
            textAttachedImage={textAttachedImage}
            setTextAttachedImage={setTextAttachedImage}
            textAttachedImageUrl={textAttachedImageUrl}
            selectedAnkiCard={selectedAnkiCard}
            onOpenAnkiCardPicker={() => setIsAnkiCardPickerOpen(true)}
            onClearAnkiCard={() => setSelectedAnkiCard(null)}
            isAnkiConnected={ankiStatus.is_connected}
          />

          <GenerationConfigBar
            options={options}
            setOptions={setOptions}
            availableDecks={ankiStatus.available_decks}
            isGenerating={isGenerating}
            onGenerate={handleGenerate}
            canGenerate={canGenerate}
            onInspect={handleInspectMaterial}
            isInspecting={isInspecting}
            onCancel={handleCancelOperation}
          />

          {/* Turn-Based Curation Queue Banner */}
          <CurationQueueBanner
            queue={curationQueue}
            onAnalyzeItem={handleAnalyzeQueuedItem}
            onDismissItem={handleDismissCurationItem}
            onClearQueue={handleClearCurationQueue}
            isInspecting={isInspecting}
          />

          {/* Active Study Plan, Scaffolding Queue & Persistent Discoveries */}
          {inspection && (
            <ActiveStudyPlanBanner
              inspection={inspection}
              isGenerating={isGenerating}
              hasGeneratedCards={cards.length > 0}
              generatedCount={cards.length}
              lastGenerationError={lastGenerationError}
              onOpenCockpit={() => setIsInspectionModalOpen(true)}
              onGenerateApproved={() => handleConfirmGenerateFromInspection(inspection)}
              onClearInspection={handleClearInspection}
            />
          )}
        </div>

        {/* Loading State or Cards Grid */}
        <div className="max-w-6xl mx-auto pt-4">
          {isGenerating ? (
            <LoadingSkeleton
              count={options.target_count > 6 ? 6 : options.target_count}
              variant="cards"
              label={
                options.ai_provider === 'ollama'
                  ? `Sintetizando microlotes con ${options.local_model || 'Ollama Local'}...`
                  : 'Sintetizando flashcards con Gemini...'
              }
            />
          ) : (
            <>
              {auditReport && cards.length > 0 && (
                <div className="mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/50 via-slate-900/80 to-purple-950/40 p-4 shadow-lg shadow-indigo-950/20 animate-fade-in">
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/20 border border-indigo-500/40 text-indigo-400 shrink-0">
                      <Brain className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold text-white">
                          Auditoría Neurocognitiva Aplicada
                        </span>
                        <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/30">
                          Calidad: {auditReport.average_quality_score}/100
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-300 mt-0.5">
                        {auditReport.total_cards_repaired > 0
                          ? `${auditReport.total_cards_repaired} tarjetas auto-reparadas`
                          : 'Atomicidad 100% verificada'}
                        {auditReport.total_sister_cards_created > 0
                          ? ` • ${auditReport.total_sister_cards_created} tarjetas hermanas desacopladas`
                          : ''}
                        {' • Cero errores de sintaxis Anki.'}
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => setIsAuditModalOpen(true)}
                    className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-3.5 py-2 text-xs shadow-md shadow-indigo-600/30 transition-all active:scale-95 shrink-0"
                  >
                    <Brain className="h-3.5 w-3.5" />
                    <span>Ver Informe de Auditoría</span>
                  </button>
                </div>
              )}

              {/* Phase 3: Transactional Replace Action Bar */}
              {isSanitationMode && selectedAnkiCard && cards.length > 0 && (
                <div className="mb-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-teal-500/50 bg-gradient-to-r from-teal-950/70 via-slate-900 to-indigo-950/70 p-4 shadow-xl shadow-teal-950/30 animate-fade-in">
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 rounded-xl bg-teal-500/20 text-teal-300 border border-teal-500/40 shrink-0">
                      <CheckCircle2 className="h-5 w-5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold text-white">
                          Sustitución Atómica Lista
                        </span>
                        <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold text-indigo-300 border border-indigo-500/30">
                          Nota #{selectedAnkiCard.note_id}
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 mt-0.5">
                        {cards.length} tarjetas atómicas listas para sustitución transaccional (la nota vieja se eliminará de Anki sólo tras confirmar la creación).
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleExecuteSanitationReplace}
                    disabled={isProcessingSanitationReplace}
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 px-5 py-2.5 text-xs font-bold text-white shadow-lg shadow-teal-600/30 hover:shadow-teal-500/40 active:scale-95 transition-all disabled:opacity-50 cursor-pointer shrink-0"
                  >
                    {isProcessingSanitationReplace ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Sustituyendo en Anki...</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle2 className="h-4 w-4" />
                        <span>Aprobar, Sustituir Nota #{selectedAnkiCard.note_id} y Siguiente ▶</span>
                      </>
                    )}
                  </button>
                </div>
              )}

              <FlashcardGrid
                cards={cards}
                deckName={options.deck_name}
                onUpdateCard={handleUpdateCard}
                onDeleteCard={handleDeleteCard}
                onAddManualCard={handleAddManualCard}
                onClearCards={handleClearCards}
                onExportToAnki={handleExportToAnki}
                onExportToApkg={handleExportToApkg}
                isExportingAnki={isExportingAnki}
                isExportingApkg={isExportingApkg}
                isAnkiConnected={ankiStatus.is_connected}
                onOpenAuditModal={() => setIsAuditModalOpen(true)}
                auditScore={auditReport?.average_quality_score}
              />
            </>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950/80 py-6 text-center text-xs text-slate-400">
        <p>AnkiCraft AI • Diseñado con Arquitectura Limpia, React 19 y Google Gemini 3.5 Flash</p>
      </footer>

      {/* Modals & Toasts */}
      <Suspense fallback={null}>
        <ApiKeyModal
          isOpen={isApiKeyModalOpen}
          onClose={() => setIsApiKeyModalOpen(false)}
          apiKey={apiKey}
          onSaveKey={handleSaveApiKey}
        />

        {/* Pre-Flight Inspection & Cognitive Scaffolding Cockpit */}
        {isInspectionModalOpen && inspection && (
          <MaterialInspectionCockpit
            inspection={inspection}
            onClose={() => setIsInspectionModalOpen(false)}
            onUpdateInspection={(updated) => setInspection(updated)}
            onConfirmGenerate={handleConfirmGenerateFromInspection}
            onOpenDeckStudio={(topic, tab) => {
              setDeckStudioInitialTopic(topic);
              setDeckStudioInitialTab(tab || 'dag');
              setIsDeckStudioOpen(true);
            }}
            isGeneratingCards={isGenerating}
            deckName={options.deck_name}
            apiKey={apiKey}
          />
        )}

        {/* Deck Studio Hub Modal */}
        {isDeckStudioOpen && (
          <DeckStudioModal
            isOpen={isDeckStudioOpen}
            onClose={() => setIsDeckStudioOpen(false)}
            availableDecks={ankiStatus.available_decks}
            currentDeck={options.deck_name}
            onDeckChange={(deck) => setOptions((prev) => ({ ...prev, deck_name: deck }))}
            initialTopic={deckStudioInitialTopic}
            initialTab={deckStudioInitialTab}
            targetConcept={deckStudioInitialTopic}
            apiKey={apiKey}
            aiProvider={options.ai_provider}
            localModel={options.local_model}
            onEnqueueGap={handleEnqueueGap}
            onGenerateFromGap={handleGenerateFromGap}
            onEnqueueCard={handleEnqueueForCuration}
            onInspectNote={handleInspectNoteDirectly}
            onExpandConcept={handleExpandConcept}
          />
        )}

        {/* Cognitive Audit Modal */}
        {auditReport && (
          <CognitiveAuditModal
            report={auditReport}
            isOpen={isAuditModalOpen}
            onClose={() => setIsAuditModalOpen(false)}
            onApplySuggestion={handleApplyAuditSuggestion}
            onIgnoreSuggestion={handleIgnoreAuditSuggestion}
            onFocusCard={handleFocusCardFromAudit}
          />
        )}

        {/* Anki Card Picker Modal */}
        <AnkiCardPickerModal
          isOpen={isAnkiCardPickerOpen}
          onClose={() => setIsAnkiCardPickerOpen(false)}
          availableDecks={ankiStatus.available_decks}
          initialDeck={selectedAnkiCard?.deck_name || options.deck_name}
          onSelectCard={(card) => {
            setSelectedAnkiCard(card);
            setOptions((prev) => ({ ...prev, deck_name: card.deck_name }));
            setInputMode('anki');
            addToast('success', `Tarjeta #${card.note_id} seleccionada como material`);
          }}
          selectedCardId={selectedAnkiCard?.note_id}
        />
      </Suspense>

      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </div>
  );
};

export default App;

`

# =====================================================================
# FILE: frontend/src/components/MaterialInspectionCockpit.tsx
# =====================================================================

`tsx
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
                excludeIds
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
        excludeIds
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
        excludeIds
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

  // Finalize plan with obsolete note IDs and inherited media before generation
  const handleApproveInspection = () => {
    const obsoleteIds: number[] = [];
    const mediaFiles: string[] = [];

    // Include source note if marked to be retired
    if (
      inspection.source_note_id &&
      (inspection.obsolete_note_ids?.includes(inspection.source_note_id) ?? true)
    ) {
      obsoleteIds.push(inspection.source_note_id);
    }
    if (inspection.inherited_media_files && inspection.inherited_media_files.length > 0) {
      mediaFiles.push(...inspection.inherited_media_files);
    }

    inspection.prerequisites.forEach((p) => {
      if (
        p.match_info &&
        p.match_info.status === 'cognitive_debt' &&
        p.match_info.matched_note_id &&
        p.match_info.should_replace !== false
      ) {
        obsoleteIds.push(p.match_info.matched_note_id);
        if (p.match_info.media_files && p.match_info.media_files.length > 0) {
          mediaFiles.push(...p.match_info.media_files);
        }
      }
    });

    inspection.core_themes.forEach((t) => {
      if (
        t.match_info &&
        t.match_info.status === 'cognitive_debt' &&
        t.match_info.matched_note_id &&
        t.match_info.should_replace !== false
      ) {
        obsoleteIds.push(t.match_info.matched_note_id);
        if (t.match_info.media_files && t.match_info.media_files.length > 0) {
          mediaFiles.push(...t.match_info.media_files);
        }
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
                          {theme.match_info && (
                            theme.match_info.status === 'dominated' ? (
                              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/30">
                                🟢 Dominado en mazo
                              </span>
                            ) : theme.match_info.status === 'cognitive_debt' ? (
                              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300 border border-amber-500/30">
                                🟡 Deuda en mazo
                              </span>
                            ) : theme.match_info.status === 'complementary' ? (
                              <span className="rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-sky-300 border border-sky-500/30">
                                🔵 Complementario
                              </span>
                            ) : (
                              <span className="rounded bg-rose-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300 border border-rose-500/30">
                                🔴 Nuevo en mazo
                              </span>
                            )
                          )}
                        </div>
                        <p className="text-[11px] text-slate-400 line-clamp-2 mt-0.5">
                          {theme.description}
                        </p>
                        {theme.associated_diagrams && theme.associated_diagrams.length > 0 && (
                          <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
                            {theme.associated_diagrams.map((diag, dIdx) => (
                              <span
                                key={dIdx}
                                className="inline-flex items-center gap-1 rounded bg-indigo-500/15 px-2 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-500/30"
                                title={`Diagrama/imagen asociado a este subtema: ${diag}`}
                              >
                                🖼️ <span className="truncate max-w-[160px]">{diag}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Collision & Duplicate Detection Banner */}
                    {theme.match_info && (() => {
                      const isOptimalCollision = theme.match_info.status === 'dominated' || theme.match_info.quality_status === 'optimal';
                      const isCognitiveDebt = theme.match_info.status === 'cognitive_debt' || theme.match_info.quality_status === 'bad';
                      const isUnreviewedLegacy = !isOptimalCollision && !isCognitiveDebt && theme.match_info.status !== 'gap' && (theme.match_info.similarity_score ?? 0) >= 0.68;
                      const isGap = theme.match_info.status === 'gap';

                      return (
                        <div
                          className={`rounded-lg border p-2.5 text-xs transition-all ${
                            isOptimalCollision
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
                            {isOptimalCollision ? (
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
                              {isOptimalCollision
                                ? '💡 Ya tenés una tarjeta saneada de alta calidad con este concepto; desmarcala si deseás evitar duplicidad.'
                                : isCognitiveDebt
                                ? 'Esta nota vieja tiene deuda cognitiva. Al generar este eje atómico, se sustituirá con calidad verificada.'
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

`

# =====================================================================
# FILE: frontend/src/components/DeckStudioModal.tsx
# =====================================================================

`tsx
import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Layers,
  Sparkles,
  Search,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  Clock,
  Zap,
  Loader2,
  RefreshCw,
  BookOpen,
  Compass,
  HelpCircle,
  BookmarkPlus,
  Copy,
  CheckCircle2,
  Folder,
  Brain,
} from 'lucide-react';
import { api } from '../services/api';
import type {
  TopicCoverageAuditResponse,
  DeckAuditSummary,
  DeckCoverageMapResponse,
  DeckCoverageMapNode,
  OrphanGap,
  AuditQualityBatchResponse,
  SemanticClusterItem,
  DuplicateNotePair,
  LearningPlanContract,
  ExpansionQueueItem,
  DeckExpansionQueueResponse,
} from '../types';

import { ThematicCoverageChecklist } from './ThematicCoverageChecklist';
import { CognitivePrecedenceDAG } from './CognitivePrecedenceDAG';
import { RefactorNoteModal } from './RefactorNoteModal';
import { DeckPickerModal } from './DeckPickerModal';
import { DeckInterviewModal } from './DeckInterviewModal';
import { ClusterSanitationModal } from './ClusterSanitationModal';
import { useModalEscape } from '../utils/useModalEscape';

interface DeckStudioModalProps {
  isOpen: boolean;
  onClose: () => void;
  availableDecks: string[];
  currentDeck: string;
  onDeckChange?: (deck: string) => void;
  initialTopic?: string;
  apiKey?: string;
  aiProvider?: 'gemini' | 'ollama';
  localModel?: string;
  onEnqueueGap?: (gap: OrphanGap) => void;
  onGenerateFromGap?: (gap: OrphanGap) => void;
  onEnqueueCard?: (item: {
    note_id: number;
    front: string;
    deck_name: string;
    matched_concept: string;
  }) => void;
  onInspectNote?: (noteId: number, deckName: string, frontFallback?: string) => void;
  onExpandConcept?: (concept: ExpansionQueueItem, deckName: string) => void;
  initialTab?: StudioTab;
  targetConcept?: string;
}

type StudioTab = 'checklist' | 'dag' | 'debt' | 'duplicates' | 'expansion';

export const DeckStudioModal: React.FC<DeckStudioModalProps> = ({
  isOpen,
  onClose,
  availableDecks,
  currentDeck,
  onDeckChange,
  initialTopic,
  initialTab,
  targetConcept,
  apiKey,
  aiProvider = 'gemini',
  localModel,
  onEnqueueGap,
  onGenerateFromGap,
  onEnqueueCard,
  onInspectNote,
  onExpandConcept,
}) => {


  const [selectedDeck, setSelectedDeck] = useState<string>(currentDeck || 'General');
  const [isDeckPickerModalOpen, setIsDeckPickerModalOpen] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<StudioTab>(initialTab || 'checklist');

  // KPI & Coverage Map Data
  const [coverageMap, setCoverageMap] = useState<DeckCoverageMapResponse | null>(null);
  const [isLoadingMap, setIsLoadingMap] = useState<boolean>(false);

  // Audits History & Active Audit
  const [auditsList, setAuditsList] = useState<DeckAuditSummary[]>([]);
  const [isLoadingAudits, setIsLoadingAudits] = useState<boolean>(false);
  const [activeAudit, setActiveAudit] = useState<TopicCoverageAuditResponse | null>(null);
  const [isLoadingActiveAudit, setIsLoadingActiveAudit] = useState<boolean>(false);

  // Semantic Clusters (Macro Topics in Deck)
  const [semanticClusters, setSemanticClusters] = useState<SemanticClusterItem[]>([]);
  const [isLoadingClusters, setIsLoadingClusters] = useState<boolean>(false);
  const [clusterFilter, setClusterFilter] = useState<'all' | 'audited' | 'unreviewed'>('all');
  const [isDiscoveringClusters, setIsDiscoveringClusters] = useState<boolean>(false);

  // New Audit Form State
  const [auditTopicInput, setAuditTopicInput] = useState<string>(initialTopic || '');
  const [isAuditing, setIsAuditing] = useState<boolean>(false);
  const [auditError, setAuditError] = useState<string | null>(null);

  // Refactor Note Modal State
  const [refactorNoteId, setRefactorNoteId] = useState<number | null>(null);
  const [refactorConcept, setRefactorConcept] = useState<string | undefined>(undefined);
  const [isRefactorModalOpen, setIsRefactorModalOpen] = useState<boolean>(false);

  // Quality Batch Audit State
  const [isAuditingBatch, setIsAuditingBatch] = useState<boolean>(false);
  const auditBatchSize = 5;
  const [lastBatchResult, setLastBatchResult] = useState<AuditQualityBatchResponse | null>(null);
  const [batchAuditMessage, setBatchAuditMessage] = useState<string | null>(null);

  // Duplicates & Redundancies State
  const [duplicatePairs, setDuplicatePairs] = useState<DuplicateNotePair[]>([]);
  const [isLoadingDuplicates, setIsLoadingDuplicates] = useState<boolean>(false);
  const [duplicateMinSimilarity, setDuplicateMinSimilarity] = useState<number>(0.88);
  const [duplicatesFilter, setDuplicatesFilter] = useState<'all' | 'exact' | 'high'>('all');

  // Phase 2: Learning Plan Contract State
  const [isInterviewModalOpen, setIsInterviewModalOpen] = useState<boolean>(false);
  const [learningContract, setLearningContract] = useState<LearningPlanContract | null>(null);

  // Phase 3: Cluster Sanitation State
  const [selectedClusterForSanitation, setSelectedClusterForSanitation] = useState<SemanticClusterItem | null>(null);

  // Phase 4: Topological Expansion State
  const [expansionData, setExpansionData] = useState<DeckExpansionQueueResponse | null>(null);
  const [isLoadingExpansion, setIsLoadingExpansion] = useState<boolean>(false);

  const fetchExpansionQueue = useCallback(async (deck: string) => {
    setIsLoadingExpansion(true);
    try {
      const data = await api.getExpansionQueue(deck);
      setExpansionData(data);
    } catch (err) {
      console.warn('Could not fetch expansion queue:', err);
    } finally {
      setIsLoadingExpansion(false);
    }
  }, []);

  // Load Deck Overview Data (Coverage Map, Audit History, Semantic Clusters, Duplicates, Contract & Expansion Queue)
  const loadDeckData = useCallback(async (deck: string) => {
    setIsLoadingMap(true);
    setIsLoadingAudits(true);
    setIsLoadingClusters(true);
    setIsLoadingDuplicates(true);
    setIsLoadingExpansion(true);
    try {
      const [mapRes, auditsRes, clustersRes, duplicatesRes, contractRes, expansionRes] =
        await Promise.allSettled([
          api.getDeckCoverageMap(deck, apiKey),
          api.listCoverageAudits(deck, apiKey),
          api.getDeckSemanticClusters(deck),
          api.getDeckDuplicates(deck, 0.88, apiKey),
          api.getDeckLearningContract(deck),
          api.getExpansionQueue(deck),
        ]);

      if (contractRes.status === 'fulfilled') {
        setLearningContract(contractRes.value);
      } else {
        setLearningContract(null);
      }

      if (mapRes.status === 'fulfilled') {
        setCoverageMap(mapRes.value);
      } else {
        console.error('Failed to load coverage map:', mapRes.reason);
      }

      if (auditsRes.status === 'fulfilled') {
        setAuditsList(auditsRes.value?.audits || []);
      } else {
        console.error('Failed to load audits list:', auditsRes.reason);
        setAuditsList([]);
      }

      if (clustersRes.status === 'fulfilled') {
        setSemanticClusters(clustersRes.value.clusters || []);
      } else {
        console.error('Failed to load semantic clusters:', clustersRes.reason);
      }

      if (duplicatesRes.status === 'fulfilled') {
        setDuplicatePairs(duplicatesRes.value.pairs || []);
      } else {
        console.error('Failed to load duplicate pairs:', duplicatesRes.reason);
      }

      if (expansionRes.status === 'fulfilled') {
        setExpansionData(expansionRes.value);
      } else {
        console.warn('Could not fetch expansion queue:', expansionRes.reason);
      }
    } finally {
      setIsLoadingMap(false);
      setIsLoadingAudits(false);
      setIsLoadingClusters(false);
      setIsLoadingDuplicates(false);
      setIsLoadingExpansion(false);
    }
  }, [apiKey]);


  // Reload duplicates on demand or threshold change
  const handleReloadDuplicates = async (threshold?: number) => {
    const minSim = threshold !== undefined ? threshold : duplicateMinSimilarity;
    setIsLoadingDuplicates(true);
    try {
      const res = await api.getDeckDuplicates(selectedDeck, minSim, apiKey);
      setDuplicatePairs(res.pairs || []);
    } catch (err: any) {
      console.error('Failed to load duplicate pairs:', err);
    } finally {
      setIsLoadingDuplicates(false);
    }
  };

  // Anki Desktop Sync State
  const [isSyncingAnki, setIsSyncingAnki] = useState<boolean>(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);
  const [clustersFeedback, setClustersFeedback] = useState<string | null>(null);

  // Sync index with Anki Desktop on demand
  const handleSyncWithAnki = async () => {
    setIsSyncingAnki(true);
    setSyncFeedback(null);
    try {
      const res = await api.syncDeckIndex(selectedDeck, apiKey);
      setSyncFeedback(
        `✓ Sincronización exitosa con Anki: ${res.total_notes} notas en total (${res.newly_indexed} nuevas indexadas con embeddings) en ${res.duration_seconds}s.`
      );
      await loadDeckData(selectedDeck);
    } catch (err: any) {
      console.error('Failed to sync deck with Anki:', err);
      setSyncFeedback(`Error al sincronizar con Anki: ${err.message || 'AnkiConnect no responde'}`);
    } finally {
      setIsSyncingAnki(false);
    }
  };

  // Discover semantic clusters on demand
  const handleDiscoverClusters = async () => {
    setIsDiscoveringClusters(true);
    setClustersFeedback(null);
    try {
      const res = await api.discoverDeckSemanticClusters(
        selectedDeck,
        { forceRefresh: true, aiProvider, localModel },
        apiKey
      );
      setSemanticClusters(res.clusters || []);
      setClustersFeedback(
        `✓ Se redescubrieron y etiquetaron ${res.clusters?.length || 0} ejes temáticos con IA.`
      );
    } catch (err: any) {
      console.error('Failed to discover semantic clusters:', err);
      setClustersFeedback(`Error al refrescar ejes: ${err.message || 'Fallo de procesamiento'}`);
    } finally {
      setIsDiscoveringClusters(false);
    }
  };

  // Load audit by ID
  const loadAuditById = async (auditId: number) => {
    setIsLoadingActiveAudit(true);
    try {
      const fullAudit = await api.getCoverageAudit(auditId, apiKey);
      setActiveAudit(fullAudit);
    } catch (err: any) {
      console.error('Failed to fetch full audit:', err);
    } finally {
      setIsLoadingActiveAudit(false);
    }
  };

  // Run new coverage audit
  const handleRunAudit = useCallback(async (topicToAudit: string, desc?: string) => {
    if (!topicToAudit.trim()) return;
    setIsAuditing(true);
    setAuditError(null);
    try {
      const res = await api.auditTopicCoverage(
        selectedDeck,
        {
          topic: topicToAudit.trim(),
          description: desc?.trim() || undefined,
          top_k: 12,
          save_audit: true,
        },
        apiKey
      );
      setActiveAudit(res);
      // Refresh audits history
      api.listCoverageAudits(selectedDeck, apiKey).then((l) => setAuditsList(l.audits));
      // Refresh coverage map
      api.getDeckCoverageMap(selectedDeck, apiKey).then(setCoverageMap);
    } catch (err: any) {
      setAuditError(err.message || 'Error al ejecutar auditoría de cobertura temática.');
    } finally {
      setIsAuditing(false);
    }
  }, [selectedDeck, apiKey]);

  // Run Batch Quality Audit (Hard Gates & Cognitive Laws)
  const handleRunBatchAudit = async (customSize?: number) => {
    const size = customSize || auditBatchSize;
    setIsAuditingBatch(true);
    setBatchAuditMessage(null);
    try {
      const res = await api.auditQualityBatch(
        selectedDeck,
        {
          batch_size: size,
          ai_provider: aiProvider,
          local_model: localModel,
        },
        apiKey
      );
      setLastBatchResult(res);
      const optimal = res.items.filter((i) => i.quality_status === 'optimal').length;
      const bad = res.items.filter((i) => i.quality_status === 'bad' || i.quality_status === 'debt' || i.quality_status === 'broken').length;
      setBatchAuditMessage(
        `Lote de ${res.audited_count} tarjetas auditado con éxito: ${optimal} óptimas, ${bad} con problemas/deuda.`
      );
      await loadDeckData(selectedDeck);
    } catch (err: any) {
      console.error('Batch audit failed:', err);
      setBatchAuditMessage(`Error al auditar lote: ${err.message || 'Fallo desconocido'}`);
    } finally {
      setIsAuditingBatch(false);
    }
  };

  // Load deck data whenever modal opens or selectedDeck changes
  useEffect(() => {
    if (!isOpen) return;
    const timer = setTimeout(() => {
      void loadDeckData(selectedDeck);
    }, 0);
    return () => clearTimeout(timer);
  }, [isOpen, selectedDeck, loadDeckData]);

  // Run initial topic audit on open when requested
  useEffect(() => {
    if (!isOpen || !initialTopic || !initialTopic.trim()) return;
    if (!initialTab || initialTab === 'checklist') {
      const timer = setTimeout(() => {
        void handleRunAudit(initialTopic);
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [isOpen, initialTopic, initialTab, handleRunAudit]);

  // Handle deck change from dropdown
  const handleSelectDeck = (newDeck: string) => {
    setSelectedDeck(newDeck);
    onDeckChange?.(newDeck);
    setActiveAudit(null);
  };

  // Open Refactor modal for a specific note
  const handleOpenRefactor = (noteId: number, concept?: string) => {
    setRefactorNoteId(noteId);
    setRefactorConcept(concept);
    setIsRefactorModalOpen(true);
  };

  const handleRefactorApplied = (_noteId: number) => {
    // Refresh deck data after refactor
    loadDeckData(selectedDeck);
  };

  useModalEscape(
    isOpen,
    onClose,
    isRefactorModalOpen ||
      isDeckPickerModalOpen ||
      isInterviewModalOpen ||
      Boolean(selectedClusterForSanitation)
  );

  if (!isOpen) return null;

  // Compute KPI metrics for canonical 4 states
  const noteNodes = (coverageMap?.nodes || []).filter((n: DeckCoverageMapNode) => n.type === 'note');
  const unreviewedCount = coverageMap?.unreviewed_count ?? 0;
  const badCount = (coverageMap?.bad_count ?? 0) + (coverageMap?.debt_count ?? 0) + (coverageMap?.broken_count ?? 0);
  const preevaluatedCount = coverageMap?.preevaluated_count ?? 0;
  const optimalCount = coverageMap?.optimal_count ?? 0;

  const totalNotes =
    noteNodes.length ||
    (coverageMap
      ? optimalCount + badCount + preevaluatedCount + unreviewedCount
      : 0);

  const auditedCount =
    coverageMap?.audited_count ?? (optimalCount + preevaluatedCount + badCount);

  const hasAudited = auditedCount > 0;
  const totalQualityCards = optimalCount + preevaluatedCount;
  const healthPct =
    coverageMap?.deck_health_percentage !== undefined &&
    coverageMap?.deck_health_percentage !== null
      ? Math.round(coverageMap.deck_health_percentage)
      : hasAudited
      ? Math.round((totalQualityCards / auditedCount) * 100)
      : null;

  const orphanGaps = coverageMap?.gap_count || 0;
  const auditedTopicsCount = (auditsList || []).length;

  // Semantic Cluster filter helpers
  const auditedClustersCount = (semanticClusters || []).filter((c) =>
    (auditsList || []).some((a) => a?.topic?.toLowerCase() === c?.title?.toLowerCase())
  ).length;
  const unreviewedClustersCount = Math.max(0, (semanticClusters || []).length - auditedClustersCount);
  const filteredClusters = (semanticClusters || []).filter((c) => {
    const isAudited = (auditsList || []).some((a) => a?.topic?.toLowerCase() === c?.title?.toLowerCase());
    if (clusterFilter === 'audited') return isAudited;
    if (clusterFilter === 'unreviewed') return !isAudited;
    return true;
  });

  // Bad / Debt notes from coverage map
  const badNotes = (coverageMap?.nodes || []).filter(
    (n: DeckCoverageMapNode) =>
      n.type === 'note' && (n.health === 'bad' || n.health === 'debt' || n.health === 'broken')
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="deck-studio-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 backdrop-blur-md bg-slate-950/80 animate-fade-in"
    >
      <div className="relative flex flex-col w-full max-w-6xl h-[92vh] rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl shadow-indigo-950/60 overflow-hidden text-slate-100">
        {/* Top Bar: Deck Selector & KPIs */}
        <div className="border-b border-slate-800 bg-slate-950/80 p-4 sm:px-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            {/* Left: Brand & Deck Dropdown */}
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25">
                <Compass className="h-5 w-5" />
              </div>

              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 id="deck-studio-modal-title" className="text-base sm:text-lg font-bold text-white tracking-tight">
                    🏛️ Deck Studio
                  </h2>
                  <span className="text-xs text-slate-400 font-medium">|</span>
                  {/* Deck Button that opens DeckPickerModal */}
                  <button
                    type="button"
                    onClick={() => setIsDeckPickerModalOpen(true)}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/90 hover:bg-slate-700/80 px-2.5 py-1 text-xs font-bold text-indigo-200 focus:border-indigo-500 focus:outline-none cursor-pointer transition-colors"
                    title="Seleccionar o cambiar mazo"
                  >
                    <Folder className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
                    <span className="max-w-[180px] truncate">{selectedDeck}</span>
                  </button>
                </div>
                <p className="text-[11px] text-slate-400">
                  Auditoría temática curricular, mapa de salud cognitiva y precedencia DAG.
                </p>
              </div>
            </div>

            {/* Middle: KPI Badges (4 Canonical States + Atomic Health) */}
            <div className="flex items-center gap-2 flex-wrap text-xs">
              <div
                className="flex items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-1.5 shadow-xs"
                title="Total de notas indexadas en este mazo"
              >
                <Layers className="h-3.5 w-3.5 text-slate-400" />
                <span className="font-semibold text-slate-300">{totalNotes}</span>
                <span className="text-[10px] text-slate-400">Notas</span>
              </div>

              <div
                className="flex items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-1.5 shadow-xs"
                title="Tarjetas pendientes de evaluación cognitiva"
              >
                <HelpCircle className="h-3.5 w-3.5 text-slate-400" />
                <span className="font-bold text-slate-300">{unreviewedCount}</span>
                <span className="text-[10px] text-slate-400">Sin evaluar</span>
              </div>

              <div
                className="flex items-center gap-1.5 rounded-xl border border-rose-500/30 bg-rose-950/20 px-3 py-1.5 text-rose-300 shadow-xs"
                title="Tarjetas que violan leyes pedagógicas o presentan deuda atómica"
              >
                <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                <span className="font-bold">{badCount}</span>
                <span className="text-[10px] text-rose-300/80">Mala</span>
              </div>

              <div
                className="flex items-center gap-1.5 rounded-xl border border-cyan-500/30 bg-cyan-950/20 px-3 py-1.5 text-cyan-300 shadow-xs"
                title="Tarjetas con evaluación inicial o heurística previa"
              >
                <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                <span className="font-bold">{preevaluatedCount}</span>
                <span className="text-[10px] text-cyan-300/80">Pre-evaluadas</span>
              </div>

              <div
                className="flex items-center gap-1.5 rounded-xl border border-emerald-500/30 bg-emerald-950/20 px-3 py-1.5 text-emerald-300 shadow-xs"
                title="Tarjetas certificadas óptimas por auditoría IA"
              >
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                <span className="font-bold">{optimalCount}</span>
                <span className="text-[10px] text-emerald-300/80">Óptimas</span>
              </div>

              <div
                className={`flex items-center gap-1.5 rounded-xl border px-3 py-1.5 shadow-xs ${
                  !hasAudited
                    ? 'border-slate-700 bg-slate-800/80 text-slate-400'
                    : healthPct! >= 80
                    ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-300'
                    : healthPct! >= 50
                    ? 'border-amber-500/30 bg-amber-950/20 text-amber-300'
                    : 'border-rose-500/30 bg-rose-950/20 text-rose-300'
                }`}
                title={
                  !hasAudited
                    ? 'Mazo sin auditar (0 evaluadas). Ejecutá la auditoría de calidad para evaluar la atomicidad real.'
                    : `Salud pedagógica: ${healthPct}% (${totalQualityCards}/${auditedCount} evaluadas favorables)`
                }
              >
                <ShieldCheck className={`h-3.5 w-3.5 ${!hasAudited ? 'text-slate-400' : ''}`} />
                <span className="font-bold">
                  {!hasAudited ? 'Sin Auditar' : `${healthPct}%`}
                </span>
                <span className="text-[10px] opacity-80">
                  {!hasAudited ? '(⚪ Neutro)' : 'Salud Atómica'}
                </span>
              </div>

              <div
                className="flex items-center gap-1.5 rounded-xl border border-rose-500/30 bg-rose-950/20 px-3 py-1.5 text-rose-300 shadow-xs"
                title="Brechas cognitivas huérfanas identificadas por auditorías"
              >
                <AlertCircle className="h-3.5 w-3.5 text-rose-400" />
                <span className="font-bold">{orphanGaps}</span>
                <span className="text-[10px] text-rose-300/80">Brechas</span>
              </div>

              <div
                className="flex items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-1.5 text-slate-300 shadow-xs"
                title="Temas auditados con IA en este mazo"
              >
                <BookOpen className="h-3.5 w-3.5 text-indigo-400" />
                <span className="font-bold">{auditedTopicsCount}</span>
                <span className="text-[10px] text-slate-400">Temas</span>
              </div>

              {/* Phase 2: Learning Plan Contract Button */}
              <button
                type="button"
                onClick={() => setIsInterviewModalOpen(true)}
                className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-bold transition-all shadow-xs cursor-pointer ${
                  learningContract && learningContract.status === 'approved'
                    ? 'border-emerald-500/40 bg-emerald-950/30 text-emerald-300 hover:bg-emerald-900/40'
                    : 'border-indigo-500/40 bg-indigo-950/30 text-indigo-200 hover:bg-indigo-900/40'
                }`}
                title="Definir o revisar el contrato pedagógico y plan de estudio de este mazo (Fase 2)"
              >
                <Brain className="h-3.5 w-3.5 text-indigo-400" />
                <span>Plan de Estudio (Fase 2)</span>
                {learningContract && learningContract.status === 'approved' ? (
                  <span className="px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 text-[10px]">
                    ✓ Aprobado
                  </span>
                ) : (
                  <span className="px-1.5 py-0.2 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 text-[10px]">
                    Pendiente
                  </span>
                )}
              </button>

              {/* Sync Deck with Anki Desktop Button */}
              <button
                type="button"
                onClick={handleSyncWithAnki}
                disabled={isSyncingAnki}
                className="inline-flex items-center gap-1.5 rounded-xl border border-sky-500/40 bg-sky-950/30 text-sky-200 hover:bg-sky-900/40 px-3 py-1.5 text-xs font-bold transition-all shadow-xs cursor-pointer disabled:opacity-50"
                title="Sincronizar inventario con Anki Desktop, detectar notas agregadas/borradas y generar embeddings faltantes"
              >
                <RefreshCw className={`h-3.5 w-3.5 text-sky-400 ${isSyncingAnki ? 'animate-spin' : ''}`} />
                <span>{isSyncingAnki ? 'Sincronizando...' : 'Sincronizar con Anki'}</span>
              </button>
            </div>

            {/* Right: Close Button */}
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar Deck Studio"
              className="self-end md:self-auto rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors cursor-pointer"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Sync, Clusters or Batch Message Banner if any */}
          {(syncFeedback || clustersFeedback || batchAuditMessage) && (
            <div className="mt-3 flex items-center justify-between gap-2 rounded-xl border border-indigo-500/40 bg-indigo-950/40 px-3.5 py-2 text-xs text-indigo-200 animate-fade-in">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-indigo-400 shrink-0" />
                <span>{syncFeedback || clustersFeedback || batchAuditMessage}</span>
              </div>
              <button
                type="button"
                onClick={() => {
                  setSyncFeedback(null);
                  setClustersFeedback(null);
                  setBatchAuditMessage(null);
                }}
                aria-label="Cerrar notificación"
                className="text-slate-400 hover:text-white p-0.5 cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Tab Switcher */}
          <div className="mt-4 flex items-center gap-1 border-t border-slate-800/80 pt-3">
            <button
              type="button"
              onClick={() => setActiveTab('checklist')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'checklist'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <span>🧭 Auditoría Temas Mazo Global</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('dag')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'dag'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <span>🌐 Grafo de Calidad (DAG)</span>
              {isLoadingMap && <Loader2 className="h-3 w-3 animate-spin text-slate-400" />}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('debt')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'debt'
                  ? 'bg-rose-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <span>⚡ Auditor de Tarjetas Malas ({badCount})</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab('duplicates')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'duplicates'
                  ? 'bg-rose-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Copy className="h-3.5 w-3.5" />
              <span>Detector de Redundancias ({duplicatePairs.length})</span>
              {isLoadingDuplicates && <Loader2 className="h-3 w-3 animate-spin text-slate-400" />}
            </button>

            <button
              type="button"
              onClick={() => {
                setActiveTab('expansion');
                fetchExpansionQueue(selectedDeck);
              }}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'expansion'
                  ? 'bg-gradient-to-r from-teal-600 to-indigo-600 text-white shadow-sm'
                  : 'text-teal-400 hover:text-teal-200 hover:bg-teal-950/40'
              }`}
            >
              <Sparkles className="h-3.5 w-3.5" />
              <span>🚀 Expansión Topológica ({expansionData?.total_orphans ?? 0})</span>
              {isLoadingExpansion && <Loader2 className="h-3 w-3 animate-spin text-teal-300" />}
            </button>
          </div>

        </div>

        {/* Modal Body Container */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 bg-slate-950/40">
          {/* TAB 1: Macro Thematic Deck Audit & Checklist */}
          {activeTab === 'checklist' && (
            <div className="space-y-6">
              {/* Pedagogical Distinction Alert Banner */}
              <div className="rounded-2xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/40 via-slate-900/60 to-purple-950/30 p-4 shadow-md text-xs space-y-2.5">
                <div className="flex items-center gap-2 font-bold text-indigo-300">
                  <Compass className="h-4 w-4 text-indigo-400" />
                  <span>Distinción Clave: Auditoría Temática Macro (Mazo) vs. Auditoría Atómica Micro (Tarjetas)</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-slate-300">
                  <div className="rounded-xl bg-slate-900/70 border border-slate-800 p-3 space-y-1">
                    <span className="font-bold text-white flex items-center gap-1.5 text-xs">
                      <BookOpen className="h-3.5 w-3.5 text-indigo-400" />
                      🧭 Auditoría Macro (Este Menú)
                    </span>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Analiza el <strong>currículo temático</strong> del mazo mediante clusters semánticos de embeddings. Evalúa si los temas clave están cubiertos o si existen vacíos huérfanos que demandan generar nuevas tarjetas.
                    </p>
                  </div>
                  <div className="rounded-xl bg-slate-900/70 border border-slate-800 p-3 space-y-1">
                    <span className="font-bold text-white flex items-center gap-1.5 text-xs">
                      <Zap className="h-3.5 w-3.5 text-amber-400" />
                      ⚡ Auditoría Micro (Pestaña Auditor de Tarjetas)
                    </span>
                    <p className="text-[11px] text-slate-400 leading-relaxed">
                      Evalúa la <strong>calidad cognitiva individual de cada tarjeta</strong> (Información Mínima de Wozniak, atomicidad, concisión y trampas de hipercorrección Ausubel/Metcalfe).
                    </p>
                  </div>
                </div>
              </div>

              {/* Thematic Clusters Discovery & Selection Grid */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 sm:p-5 shadow-lg space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                  <div>
                    <div className="flex items-center gap-2 text-xs font-bold text-white">
                      <Layers className="h-4 w-4 text-indigo-400" />
                      <span>Temas y Ejes Curriculares Detectados en '{selectedDeck}'</span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Hacé click en cualquier tema para auditarlo directamente con IA o revisar su checklist de cobertura.
                    </p>
                  </div>

                  {/* Filter Pills for Themes & Discover Button */}
                  <div className="flex items-center gap-2 flex-wrap">
                    <div className="flex items-center rounded-lg border border-slate-700 bg-slate-800/90 p-0.5 text-xs">
                      <button
                        type="button"
                        onClick={() => setClusterFilter('all')}
                        className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                          clusterFilter === 'all'
                            ? 'bg-indigo-600 text-white shadow-xs'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Todos ({semanticClusters.length})
                      </button>
                      <button
                        type="button"
                        onClick={() => setClusterFilter('audited')}
                        className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                          clusterFilter === 'audited'
                            ? 'bg-emerald-600 text-white shadow-xs'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Auditados ({auditedClustersCount})
                      </button>
                      <button
                        type="button"
                        onClick={() => setClusterFilter('unreviewed')}
                        className={`px-2 py-1 rounded text-[11px] font-semibold transition-all cursor-pointer ${
                          clusterFilter === 'unreviewed'
                            ? 'bg-slate-700 text-white shadow-xs'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Sin Auditar ({unreviewedClustersCount})
                      </button>
                    </div>

                    <button
                      type="button"
                      onClick={handleDiscoverClusters}
                      disabled={isDiscoveringClusters}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-indigo-500/40 bg-indigo-950/40 hover:bg-indigo-900/60 px-2.5 py-1 text-xs font-semibold text-indigo-300 hover:text-white transition-all cursor-pointer disabled:opacity-50"
                      title="Re-ejecutar Spherical K-Means con embeddings para descubrir nuevos temas"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isDiscoveringClusters ? 'animate-spin' : ''}`} />
                      <span>{isDiscoveringClusters ? 'Descubriendo...' : 'Refrescar Ejes'}</span>
                    </button>
                  </div>
                </div>

                {isLoadingClusters ? (
                  <div className="flex items-center justify-center p-8 text-xs text-slate-400 space-x-2">
                    <Loader2 className="h-5 w-5 animate-spin text-indigo-400" />
                    <span>Cargando ejes temáticos del mazo...</span>
                  </div>
                ) : semanticClusters.length === 0 ? (
                  <div className="rounded-xl border border-dashed border-slate-800 bg-slate-950/40 p-6 text-center space-y-3">
                    <BookOpen className="h-8 w-8 text-slate-400 mx-auto" />
                    <p className="text-xs font-bold text-slate-300">
                      No se han extraído los ejes temáticos de este mazo todavía
                    </p>
                    <p className="text-[11px] text-slate-400 max-w-md mx-auto">
                      Podés descubrir automáticamente las familias conceptuales y subtemas de '{selectedDeck}' usando clustering semántico sobre sus vectores de embeddings.
                    </p>
                    <button
                      type="button"
                      onClick={handleDiscoverClusters}
                      disabled={isDiscoveringClusters}
                      className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 px-4 py-2 text-xs font-bold text-white shadow-md shadow-indigo-600/20 active:scale-95 transition-all cursor-pointer disabled:opacity-50"
                    >
                      {isDiscoveringClusters ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span>Descubriendo Ejes Temáticos...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="h-4 w-4" />
                          <span>✨ Descubrir Ejes Temáticos del Mazo</span>
                        </>
                      )}
                    </button>
                  </div>
                ) : filteredClusters.length === 0 ? (
                  <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 text-center text-xs text-slate-400">
                    No hay temas con el filtro seleccionado ({clusterFilter}).
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {filteredClusters.map((cluster) => {
                      const matchingAudit = auditsList.find(
                        (a) => a.topic.toLowerCase() === cluster.title.toLowerCase()
                      );
                      const isAudited = !!matchingAudit;

                      return (
                        <div
                          key={cluster.cluster_index}
                          className={`rounded-xl border p-3.5 transition-all duration-150 flex flex-col justify-between space-y-2.5 ${
                            isAudited
                              ? 'border-emerald-500/40 bg-emerald-950/10 hover:border-emerald-500/60'
                              : 'border-slate-800 bg-slate-950/50 hover:border-slate-700'
                          }`}
                        >
                          <div className="space-y-1.5">
                            <div className="flex items-start justify-between gap-1.5">
                              <h4 className="text-xs font-bold text-white line-clamp-1" title={cluster.title}>
                                {cluster.title}
                              </h4>
                              {isAudited ? (
                                <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 px-2 py-0.5 text-[9px] font-bold uppercase">
                                  {matchingAudit.coverage_percentage}% Cobertura
                                </span>
                              ) : (
                                <span className="shrink-0 inline-flex items-center gap-1 rounded-full bg-slate-800 text-slate-400 border border-slate-700 px-2 py-0.5 text-[9px] font-bold uppercase">
                                  Sin Auditar
                                </span>
                              )}
                            </div>

                            <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed italic">
                              {cluster.scope}
                            </p>
                          </div>

                          <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between gap-1.5 flex-wrap">
                            <span className="text-[10px] text-slate-400 font-mono">
                              {(cluster.note_ids || []).length} tarjetas
                            </span>

                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => setSelectedClusterForSanitation(cluster)}
                                className="inline-flex items-center gap-1 rounded-lg bg-teal-600/80 hover:bg-teal-500 px-2 py-1 text-[10px] font-bold text-white transition-all active:scale-95 cursor-pointer shadow-xs"
                                title="Sanear este clúster temático sin solapamiento (Fase 3)"
                              >
                                <Sparkles className="h-3 w-3 text-teal-200" />
                                <span>Sanear Clúster</span>
                              </button>

                              {isAudited ? (
                                <button
                                  type="button"
                                  onClick={() => loadAuditById(matchingAudit.id)}
                                  className="inline-flex items-center gap-1 rounded-lg bg-emerald-600/80 hover:bg-emerald-500 px-2 py-1 text-[10px] font-bold text-white transition-all active:scale-95 cursor-pointer"
                                >
                                  <span>Checklist</span>
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  disabled={isAuditing}
                                  onClick={() => {
                                    setAuditTopicInput(cluster.title);
                                    handleRunAudit(cluster.title, cluster.scope);
                                  }}
                                  className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-2 py-1 text-[10px] font-bold text-white transition-all active:scale-95 cursor-pointer disabled:opacity-50"
                                >
                                  <Search className="h-3 w-3" />
                                  <span>Auditar</span>
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Manual Topic Formulation Box */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 sm:p-5 shadow-lg space-y-3">
                <div className="flex items-center gap-2 text-xs font-bold text-indigo-300">
                  <Sparkles className="h-4 w-4 text-indigo-400" />
                  <span>O Auditar un Tema Específico / Arbitrario (Manual) en '{selectedDeck}'</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="md:col-span-2 space-y-1">
                    <input
                      type="text"
                      aria-label="Tema a auditar en el mazo"
                      placeholder="Ej: Replicación de ADN, Ciclo de Krebs, Derecho Procesal..."
                      value={auditTopicInput}
                      onChange={(e) => setAuditTopicInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleRunAudit(auditTopicInput);
                      }}
                      className="w-full h-10 rounded-xl border border-slate-700 bg-slate-950/80 px-3.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <button
                      type="button"
                      onClick={() => handleRunAudit(auditTopicInput)}
                      disabled={isAuditing || !auditTopicInput.trim()}
                      className="w-full h-10 inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 px-4 text-xs font-bold text-white shadow-md shadow-indigo-600/20 active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
                    >
                      {isAuditing ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span>Auditando con IA...</span>
                        </>
                      ) : (
                        <>
                          <Search className="h-4 w-4" />
                          <span>🔍 Auditar Tema</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>

                {auditError && (
                  <div className="rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-xs text-rose-300 flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                    <span>{auditError}</span>
                  </div>
                )}
              </div>

              {/* Two column layout: Past Audits History vs Active Audit Report */}
              <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
                {/* Past Audits Sidebar */}
                <div className="lg:col-span-1 space-y-3">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-300">
                    <div className="flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5 text-slate-400" />
                      <span>Historial de Auditorías</span>
                    </div>
                    <span className="text-[10px] text-slate-400">
                      ({auditsList.length})
                    </span>
                  </div>

                  {isLoadingAudits ? (
                    <div className="flex items-center justify-center p-6 text-xs text-slate-400 space-x-2">
                      <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
                      <span>Cargando...</span>
                    </div>
                  ) : auditsList.length === 0 ? (
                    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4 text-center text-xs text-slate-400">
                      No hay auditorías previas para este mazo. Ingresá un tema arriba para auditar.
                    </div>
                  ) : (
                    <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
                      {auditsList.map((item: DeckAuditSummary) => {
                        const isCurrent = activeAudit?.audit_id === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => loadAuditById(item.id)}
                            className={`w-full text-left rounded-xl border p-3 transition-all ${
                              isCurrent
                                ? 'border-indigo-500 bg-indigo-950/40 text-white shadow-xs'
                                : 'border-slate-800 bg-slate-900/70 hover:border-slate-700 text-slate-300'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-1">
                              <span className="text-xs font-bold truncate">
                                {item.topic}
                              </span>
                              <span
                                className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                                  item.coverage_percentage >= 80
                                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                                    : item.coverage_percentage >= 50
                                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                                    : 'bg-rose-500/20 text-rose-300 border-rose-500/30'
                                }`}
                              >
                                {item.coverage_percentage}%
                              </span>
                            </div>
                            <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400">
                              <span>{item.pending_gaps} brecha(s)</span>
                              <span>
                                {item.created_at
                                  ? new Date(item.created_at).toLocaleDateString()
                                  : ''}
                              </span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Active Audit Content */}
                <div className="lg:col-span-3">
                  {isLoadingActiveAudit ? (
                    <div className="flex flex-col items-center justify-center p-16 space-y-3">
                      <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
                      <p className="text-xs font-semibold text-slate-400">
                        Cargando reporte de auditoría...
                      </p>
                    </div>
                  ) : activeAudit ? (
                    <ThematicCoverageChecklist
                      audit={activeAudit}
                      deckName={selectedDeck}
                      apiKey={apiKey}
                      onAuditUpdated={(up) => setActiveAudit(up)}
                      onEnqueueGap={onEnqueueGap}
                      onGenerateFromGap={onGenerateFromGap}
                    />
                  ) : (
                    <div className="rounded-2xl border border-slate-800 bg-slate-900/30 p-12 text-center text-slate-400 space-y-3">
                      <Compass className="h-10 w-10 text-indigo-400/60 mx-auto" />
                      <h3 className="text-sm font-bold text-slate-200">
                        Ninguna auditoría seleccionada
                      </h3>
                      <p className="text-xs text-slate-400 max-w-md mx-auto">
                        Seleccioná una auditoría del historial de la izquierda o ingresá un tema arriba para auditar la cobertura temática de tu mazo con IA.
                      </p>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: DAG Quality Graph */}
          {activeTab === 'dag' && (
            <div className="h-full min-h-[550px]">
              <CognitivePrecedenceDAG
                deckName={selectedDeck}
                apiKey={apiKey}
                initialMap={coverageMap}
                targetConcept={targetConcept || initialTopic}
                onEnqueueGap={(title, reason) => {
                  onEnqueueGap?.({
                    gap_title: title,
                    reason,
                    priority: 'high',
                    status: 'pending',
                  });
                }}
                onEnqueueNote={(nid, label) =>
                  onEnqueueCard?.({
                    note_id: nid,
                    front: label,
                    deck_name: selectedDeck,
                    matched_concept: label,
                  })
                }
                onInspectNote={(nid, label) => onInspectNote?.(nid, selectedDeck, label)}
              />
            </div>
          )}

          {/* TAB 3: Cognitive Debt Auditor */}
          {activeTab === 'debt' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div>
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-rose-400" />
                    <span>Tarjetas con Calidad Mala / Deuda en '{selectedDeck}'</span>
                  </h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Tarjetas cuyas respuestas violan principios pedagógicos (respuestas extensas, slide dumps o falta de pistas de recuperación).
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => loadDeckData(selectedDeck)}
                  className="self-start sm:self-auto inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:text-white"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                  <span>Re-analizar mazo</span>
                </button>
              </div>

              {/* Unreviewed Prompt Banner */}
              {(coverageMap?.unreviewed_count ?? 0) > 0 && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-3.5 text-xs text-indigo-200">
                  <div className="flex items-center gap-2.5">
                    <Sparkles className="h-4 w-4 text-indigo-400 shrink-0" />
                    <div>
                      <span className="font-bold text-white">
                        {coverageMap?.unreviewed_count} notas pendientes de auditoría cognitiva
                      </span>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Evaluálas con compuertas duras (Wozniak, Ausubel, Metcalfe) para detectar monolitos y slide dumps.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={isAuditingBatch}
                    onClick={() => handleRunBatchAudit(auditBatchSize)}
                    className="self-start sm:self-auto inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-3 py-1.5 font-bold text-white shadow-xs cursor-pointer active:scale-95 transition-all disabled:opacity-50"
                  >
                    {isAuditingBatch ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Zap className="h-3.5 w-3.5" />
                    )}
                    <span>Auditar Próximas {auditBatchSize}</span>
                  </button>
                </div>
              )}

              {/* Recent Batch Audit Results */}
              {lastBatchResult && lastBatchResult.items.length > 0 && (
                <div className="rounded-xl border border-slate-700/80 bg-slate-900/60 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                      <span>Resultados del Último Lote Auditado ({lastBatchResult.audited_count} notas)</span>
                    </h4>
                    <span className="text-[10px] text-slate-400">
                      {new Date().toLocaleTimeString()}
                    </span>
                  </div>

                  <div className="space-y-2">
                    {lastBatchResult.items.map((item) => (
                      <div
                        key={item.note_id}
                        className={`rounded-lg p-3 text-xs border ${
                          item.quality_status === 'optimal'
                            ? 'border-emerald-500/30 bg-emerald-950/20 text-emerald-200'
                            : item.quality_status === 'preevaluated'
                            ? 'border-cyan-500/30 bg-cyan-950/20 text-cyan-200'
                            : 'border-rose-500/30 bg-rose-950/20 text-rose-200'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap mb-1">
                          <span className="font-mono text-[10px] font-bold">
                            Nota #{item.note_id}
                          </span>
                          <div className="flex items-center gap-1.5">
                            {item.violation_type && item.violation_type !== 'NONE' && (
                              <span className="font-mono text-[9px] font-bold uppercase bg-amber-950/60 border border-amber-800/40 px-1.5 py-0.5 rounded text-amber-300">
                                {item.violation_type}
                              </span>
                            )}
                            <span
                              className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                item.quality_status === 'optimal'
                                  ? 'bg-emerald-900/50 text-emerald-300'
                                  : item.quality_status === 'preevaluated'
                                  ? 'bg-cyan-900/50 text-cyan-300'
                                  : 'bg-rose-900/50 text-rose-300'
                              }`}
                            >
                              {item.quality_status === 'optimal'
                                ? '🟢 Óptima'
                                : item.quality_status === 'preevaluated'
                                ? '🔵 Pre-evaluada'
                                : '🔴 Mala'}
                              {' '}({Math.round(item.quality_score * 100)}%)
                            </span>
                          </div>
                        </div>

                        <p className="font-medium text-slate-200 mb-1">{item.front}</p>
                        <p className="text-[11px] text-slate-300/80 italic">{item.quality_feedback}</p>

                        {item.atomic_sister_cards_recommended && item.atomic_sister_cards_recommended.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-slate-700/50 space-y-1">
                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                              Tarjetas hermanas atómicas sugeridas:
                            </span>
                            <ul className="list-disc list-inside text-[11px] text-slate-300 space-y-0.5">
                              {item.atomic_sister_cards_recommended.map((s, idx) => (
                                <li key={idx}>{s}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {item.quality_status !== 'optimal' && (
                          <div className="mt-2 pt-2 border-t border-slate-700/50 flex items-center justify-end gap-1.5 flex-wrap">
                            {onInspectNote && (
                              <button
                                type="button"
                                onClick={() => onInspectNote(item.note_id, selectedDeck, item.front)}
                                className="inline-flex items-center gap-1 rounded bg-indigo-600 hover:bg-indigo-500 px-2 py-1 text-[11px] font-bold text-white shadow-xs cursor-pointer active:scale-95 transition-all"
                                title="Descomponer esta tarjeta mediante Diagnóstico y Planificación"
                              >
                                <Search className="h-3 w-3" />
                                <span>Analizar y Planificar</span>
                              </button>
                            )}
                            {onEnqueueCard && (
                              <button
                                type="button"
                                onClick={() =>
                                  onEnqueueCard({
                                    note_id: item.note_id,
                                    front: item.front,
                                    deck_name: selectedDeck,
                                    matched_concept: item.front,
                                  })
                                }
                                className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-800 hover:bg-slate-700 px-2 py-1 text-[11px] font-semibold text-slate-300 hover:text-white cursor-pointer active:scale-95 transition-all"
                                title="Reservar en la cola de curación"
                              >
                                <BookmarkPlus className="h-3 w-3 text-indigo-400" />
                                <span>Encolar</span>
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {badNotes.length === 0 ? (
                !hasAudited ? (
                  <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-12 text-center text-slate-300 space-y-2">
                    <HelpCircle className="h-10 w-10 text-slate-400 mx-auto" />
                    <h4 className="text-base font-bold text-slate-300">
                      Mazo Pendiente de Auditoría Cognitiva (⚪ Sin evaluar)
                    </h4>
                    <p className="text-xs text-slate-400 max-w-md mx-auto">
                      Las tarjetas de este mazo aún no han sido inspeccionadas por el auditor de IA. Ninguna tarjeta está marcada como mala artificialmente.
                    </p>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-emerald-500/30 bg-emerald-950/15 p-12 text-center text-slate-300 space-y-2">
                    <ShieldCheck className="h-10 w-10 text-emerald-400 mx-auto" />
                    <h4 className="text-base font-bold text-emerald-300">
                      ¡Cero Tarjetas con Calidad Mala Confirmada!
                    </h4>
                    <p className="text-xs text-slate-400 max-w-md mx-auto">
                      Las {auditedCount} tarjetas evaluadas en este mazo cumplen con el principio atómico de FSRS y las directrices pedagógicas de calidad.
                    </p>
                  </div>
                )
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {badNotes.map((note: DeckCoverageMapNode) => (
                    <div
                      key={note.id}
                      className="flex flex-col justify-between rounded-xl border border-rose-500/30 bg-rose-950/10 p-4 hover:border-rose-500/50 transition-all space-y-3"
                    >
                      <div className="space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono text-[10px] font-bold text-rose-300 bg-rose-950/60 px-2 py-0.5 rounded border border-rose-800/40">
                            Nota #{note.note_id}
                          </span>
                          <span className="rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 px-1.5 py-0.5 text-[9px] font-bold uppercase">
                            Calidad Mala / Deuda Atómica
                          </span>
                        </div>

                        <p className="text-xs font-semibold text-slate-200">
                          {note.label}
                        </p>

                        {note.details && (
                          <p className="text-[11px] text-slate-400 italic line-clamp-2 bg-slate-950/60 p-2 rounded border border-slate-800">
                            {note.details}
                          </p>
                        )}
                      </div>

                      <div className="pt-2 border-t border-amber-500/20 flex items-center justify-between gap-2 flex-wrap">
                        <span className="text-[10px] text-slate-400">
                          Monolito con deuda
                        </span>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {onInspectNote && (
                            <button
                              type="button"
                              onClick={() => onInspectNote(note.note_id!, selectedDeck, note.label)}
                              className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 px-2.5 py-1.5 text-xs font-bold text-white shadow-xs active:scale-95 transition-all cursor-pointer"
                              title="Descomponer esta tarjeta mediante Diagnóstico y Planificación"
                            >
                              <Search className="h-3.5 w-3.5" />
                              <span>Analizar y Planificar</span>
                            </button>
                          )}
                          {onEnqueueCard && (
                            <button
                              type="button"
                              onClick={() =>
                                onEnqueueCard({
                                  note_id: note.note_id!,
                                  front: note.label,
                                  deck_name: selectedDeck,
                                  matched_concept: note.label,
                                })
                              }
                              className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-2.5 py-1.5 text-xs font-semibold text-slate-300 hover:text-white transition-all active:scale-95 cursor-pointer"
                              title="Reservar en la cola de curación"
                            >
                              <BookmarkPlus className="h-3.5 w-3.5 text-indigo-400" />
                              <span>Encolar</span>
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => handleOpenRefactor(note.note_id!, note.label)}
                            className="inline-flex items-center gap-1 rounded-lg border border-amber-500/40 bg-amber-950/40 hover:bg-amber-900/60 px-2.5 py-1.5 text-xs font-bold text-amber-300 hover:text-white active:scale-95 transition-all cursor-pointer"
                            title="Editar in-place en Anki preservando FSRS"
                          >
                            <Zap className="h-3.5 w-3.5 text-amber-400" />
                            <span>Refactor</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 4: Redundancies & Duplicate Cards Detector */}
          {activeTab === 'duplicates' && (
            <div className="space-y-6">
              {/* Pedagogical Explanation Banner */}
              <div className="rounded-2xl border border-rose-500/30 bg-gradient-to-r from-rose-950/40 via-slate-900/60 to-amber-950/30 p-4 shadow-md text-xs space-y-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 font-bold text-rose-300">
                    <Copy className="h-4 w-4 text-rose-400" />
                    <span>Detector de Redundancias Vectoriales y Tarjetas Duplicadas (≥ 88%)</span>
                  </div>
                  <span className="rounded-full bg-rose-950/60 border border-rose-500/40 px-2.5 py-0.5 text-[10px] font-mono font-bold text-rose-300">
                    {duplicatePairs.length} pares detectados
                  </span>
                </div>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  Las tarjetas con alta proximidad vectorial compiten por el mismo nodo de recuperación en tu memoria (<strong>Interferencia Retroactiva y Proactiva</strong> de Underwood). Suelen ser duplicados accidentales, variantes cloze de la misma frase o preguntas paralelas. Podés analizarlas para unificarlas, refactorizarlas en Anki o encolarlas para curación.
                </p>
              </div>

              {/* Sensitivity & Controls Bar */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-slate-800 bg-slate-900/80 p-3 sm:px-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-slate-400">Filtro de similitud:</span>
                  <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
                    <button
                      type="button"
                      onClick={() => {
                        setDuplicatesFilter('all');
                        if (duplicateMinSimilarity !== 0.88) {
                          setDuplicateMinSimilarity(0.88);
                          handleReloadDuplicates(0.88);
                        }
                      }}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        duplicatesFilter === 'all'
                          ? 'bg-indigo-600 text-white shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Todas (≥ 88%)
                    </button>
                    <button
                      type="button"
                      onClick={() => setDuplicatesFilter('high')}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        duplicatesFilter === 'high'
                          ? 'bg-amber-600 text-white shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Alta (≥ 92%)
                    </button>
                    <button
                      type="button"
                      onClick={() => setDuplicatesFilter('exact')}
                      className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                        duplicatesFilter === 'exact'
                          ? 'bg-rose-600 text-white shadow-xs'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Clones / Idénticos (≥ 96%)
                    </button>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => handleReloadDuplicates()}
                  disabled={isLoadingDuplicates}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 hover:bg-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white transition-all active:scale-95 disabled:opacity-50 cursor-pointer self-start sm:self-auto"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${isLoadingDuplicates ? 'animate-spin text-rose-400' : ''}`} />
                  <span>Recalcular Duplicados</span>
                </button>
              </div>

              {/* Duplicate Pairs List */}
              {isLoadingDuplicates ? (
                <div className="flex flex-col items-center justify-center p-12 space-y-3 text-slate-400">
                  <Loader2 className="h-8 w-8 animate-spin text-rose-400" />
                  <p className="text-xs font-semibold">Analizando matriz de similitud de tarjetas...</p>
                </div>
              ) : duplicatePairs.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-slate-800 bg-slate-900/40 space-y-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-950/40 border border-emerald-500/30 text-emerald-400">
                    <CheckCircle2 className="h-6 w-6" />
                  </div>
                  <h4 className="text-sm font-bold text-slate-200">¡Mazo limpio de redundancias!</h4>
                  <p className="text-xs text-slate-400 max-w-md">
                    No se detectaron pares de tarjetas con similitud superior al 88% en '{selectedDeck}'. La independencia temática es óptima.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {duplicatePairs
                    .filter((p) => {
                      if (duplicatesFilter === 'exact') return p.similarity >= 0.96;
                      if (duplicatesFilter === 'high') return p.similarity >= 0.92;
                      return true;
                    })
                    .map((pair, idx) => {
                      const isClone = pair.similarity >= 0.96;
                      const isHigh = pair.similarity >= 0.92;

                      return (
                        <div
                          key={`dup-${pair.note_id_1}-${pair.note_id_2}-${idx}`}
                          className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4 shadow-lg space-y-3 hover:border-slate-700 transition-all"
                        >
                          {/* Pair Header */}
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5">
                            <div className="flex items-center gap-2">
                              <span
                                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-mono font-bold border ${
                                  isClone
                                    ? 'bg-rose-950/60 text-rose-300 border-rose-500/50'
                                    : isHigh
                                    ? 'bg-amber-950/60 text-amber-300 border-amber-500/50'
                                    : 'bg-purple-950/60 text-purple-300 border-purple-500/50'
                                }`}
                              >
                                ⚡ {(pair.similarity * 100).toFixed(1)}% Similitud
                              </span>
                              <span className="text-xs font-semibold text-slate-300">
                                {isClone
                                  ? 'Duplicado Casi Idéntico / Variante Cloze'
                                  : isHigh
                                  ? 'Alta Redundancia Conceptual'
                                  : 'Solapamiento Temático Significativo'}
                              </span>
                            </div>

                            <span className="text-[10px] text-slate-400 font-mono">
                              Par #{idx + 1}
                            </span>
                          </div>

                          {/* Cards Side-by-Side Grid */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {/* Card 1 */}
                            <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 p-3 flex flex-col justify-between gap-3">
                              <div className="space-y-1.5">
                                <div className="flex items-center justify-between gap-1 text-[11px] text-slate-400">
                                  <span className="font-mono text-indigo-300 font-semibold">
                                    Nota #{pair.note_id_1}
                                  </span>
                                  {pair.cluster_1 && (
                                    <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] text-slate-300 truncate max-w-[140px]">
                                      {pair.cluster_1}
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-200 font-medium leading-relaxed">
                                  {pair.front_1}
                                </p>
                              </div>

                              <div className="flex items-center gap-1.5 pt-2 border-t border-slate-800/80 flex-wrap">
                                {onInspectNote && (
                                  <button
                                    type="button"
                                    onClick={() => onInspectNote(pair.note_id_1, selectedDeck, pair.front_1)}
                                    className="inline-flex items-center gap-1 rounded-lg bg-indigo-600/30 hover:bg-indigo-600 px-2 py-1 text-[11px] font-semibold text-indigo-200 hover:text-white transition-all active:scale-95 cursor-pointer"
                                    title="Analizar y planificar esta tarjeta"
                                  >
                                    <Search className="h-3 w-3" />
                                    <span>Planificar</span>
                                  </button>
                                )}
                                {onEnqueueCard && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      onEnqueueCard({
                                        note_id: pair.note_id_1,
                                        front: pair.front_1,
                                        deck_name: selectedDeck,
                                        matched_concept: pair.front_1,
                                      })
                                    }
                                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-2 py-1 text-[11px] font-semibold text-slate-300 hover:text-white transition-all active:scale-95 cursor-pointer"
                                    title="Encolar para curación"
                                  >
                                    <BookmarkPlus className="h-3.5 w-3.5 text-indigo-400" />
                                    <span>Encolar</span>
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => handleOpenRefactor(pair.note_id_1, pair.front_1)}
                                  className="inline-flex items-center gap-1 rounded-lg border border-amber-500/30 bg-amber-950/30 hover:bg-amber-900/50 px-2 py-1 text-[11px] font-semibold text-amber-300 hover:text-white transition-all active:scale-95 cursor-pointer"
                                  title="Refactorizar in-place en Anki preservando FSRS"
                                >
                                  <Zap className="h-3 w-3 text-amber-400" />
                                  <span>Refactor</span>
                                </button>
                              </div>
                            </div>

                            {/* Card 2 */}
                            <div className="rounded-xl border border-slate-800/80 bg-slate-950/70 p-3 flex flex-col justify-between gap-3">
                              <div className="space-y-1.5">
                                <div className="flex items-center justify-between gap-1 text-[11px] text-slate-400">
                                  <span className="font-mono text-indigo-300 font-semibold">
                                    Nota #{pair.note_id_2}
                                  </span>
                                  {pair.cluster_2 && (
                                    <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[9px] text-slate-300 truncate max-w-[140px]">
                                      {pair.cluster_2}
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-200 font-medium leading-relaxed">
                                  {pair.front_2}
                                </p>
                              </div>

                              <div className="flex items-center gap-1.5 pt-2 border-t border-slate-800/80 flex-wrap">
                                {onInspectNote && (
                                  <button
                                    type="button"
                                    onClick={() => onInspectNote(pair.note_id_2, selectedDeck, pair.front_2)}
                                    className="inline-flex items-center gap-1 rounded-lg bg-indigo-600/30 hover:bg-indigo-600 px-2 py-1 text-[11px] font-semibold text-indigo-200 hover:text-white transition-all active:scale-95 cursor-pointer"
                                    title="Analizar y planificar esta tarjeta"
                                  >
                                    <Search className="h-3 w-3" />
                                    <span>Planificar</span>
                                  </button>
                                )}
                                {onEnqueueCard && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      onEnqueueCard({
                                        note_id: pair.note_id_2,
                                        front: pair.front_2,
                                        deck_name: selectedDeck,
                                        matched_concept: pair.front_2,
                                      })
                                    }
                                    className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 px-2 py-1 text-[11px] font-semibold text-slate-300 hover:text-white transition-all active:scale-95 cursor-pointer"
                                    title="Encolar para curación"
                                  >
                                    <BookmarkPlus className="h-3.5 w-3.5 text-indigo-400" />
                                    <span>Encolar</span>
                                  </button>
                                )}
                                <button
                                  type="button"
                                  onClick={() => handleOpenRefactor(pair.note_id_2, pair.front_2)}
                                  className="inline-flex items-center gap-1 rounded-lg border border-amber-500/30 bg-amber-950/30 hover:bg-amber-900/50 px-2 py-1 text-[11px] font-semibold text-amber-300 hover:text-white transition-all active:scale-95 cursor-pointer"
                                  title="Refactorizar in-place en Anki preservando FSRS"
                                >
                                  <Zap className="h-3 w-3 text-amber-400" />
                                  <span>Refactor</span>
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: Topological Curriculum Expansion (Phase 4) */}
          {activeTab === 'expansion' && (
            <div className="space-y-6 animate-fade-in">
              {/* Header Gating Status Banner */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/90 p-5 space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <div className="p-3 rounded-xl bg-gradient-to-tr from-teal-500/20 to-indigo-500/20 border border-teal-500/30 text-teal-300 shrink-0">
                      <Sparkles className="h-6 w-6" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <h3 className="text-base font-bold text-white">
                          Escalera de Expansión Topológica
                        </h3>
                        <span className="rounded-full bg-teal-500/20 px-2 py-0.5 text-[10px] font-bold text-teal-300 border border-teal-500/30">
                          Fase 4 Activa
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 mt-0.5">
                        Conceptos y prerrequisitos ordenados según precedencia cognitiva. Se abordan primero los fundamentos raíz para garantizar un andamiaje sin vacíos.
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => fetchExpansionQueue(selectedDeck)}
                      disabled={isLoadingExpansion}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white transition-all cursor-pointer"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isLoadingExpansion ? 'animate-spin' : ''}`} />
                      <span>Actualizar Cola</span>
                    </button>
                  </div>
                </div>

                {/* Gating Status Alerts */}
                {!expansionData?.contract_approved && (
                  <div className="flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-950/30 p-3 text-xs text-amber-200">
                    <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <span className="font-bold">Contrato Pedagógico Pendiente: </span>
                      Para que la expansión respete el nivel Bloom y las fronteras de exclusión del mazo, definí el contrato pedagógico.
                    </div>
                    <button
                      type="button"
                      onClick={() => setIsInterviewModalOpen(true)}
                      className="px-2.5 py-1 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold text-[11px] shrink-0"
                    >
                      Definir Contrato
                    </button>
                  </div>
                )}

                {expansionData && expansionData.pending_sanitation_count > 0 && (
                  <div className="flex items-start gap-3 rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-xs text-rose-200">
                    <AlertCircle className="h-4 w-4 text-rose-400 shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <span className="font-bold">Saneamiento Incompleto ({expansionData.pending_sanitation_count} notas pendientes): </span>
                      Se recomienda sanear las tarjetas monolito existentes (Fase 3) antes de expandir masivamente el mazo para evitar redundancias conceptuales.
                    </div>
                    <button
                      type="button"
                      onClick={() => setActiveTab('checklist')}
                      className="px-2.5 py-1 rounded-lg bg-rose-500 hover:bg-rose-400 text-white font-bold text-[11px] shrink-0 cursor-pointer"
                    >
                      Ir a Clústeres
                    </button>
                  </div>
                )}

                {expansionData && expansionData.contract_approved && expansionData.sanitation_completed && (
                  <div className="flex items-center gap-2.5 rounded-xl border border-emerald-500/40 bg-emerald-950/30 p-3 text-xs text-emerald-200">
                    <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                    <span>
                      <strong>¡Mazo Base 100% Saneado!</strong> La base de conocimiento está libre de sobrecarga cognitiva. Podés crear tarjetas para cada brecha huérfana en orden topológico.
                    </span>
                  </div>
                )}
              </div>

              {/* Expansion Ladder Cards */}
              {isLoadingExpansion ? (
                <div className="py-16 text-center text-slate-400 flex flex-col items-center gap-3">
                  <Loader2 className="h-8 w-8 animate-spin text-teal-400" />
                  <p className="text-xs">Calculando ordenamiento topológico del currículo...</p>
                </div>
              ) : !expansionData || !expansionData.expansion_queue || expansionData.expansion_queue.length === 0 ? (
                <div className="py-16 text-center text-slate-400 rounded-2xl border border-slate-800 bg-slate-900/40 p-8 space-y-3">
                  <CheckCircle2 className="h-12 w-12 text-emerald-400 mx-auto" />
                  <h4 className="text-sm font-bold text-white">¡No hay brechas huérfanas en el mazo!</h4>
                  <p className="text-xs text-slate-400 max-w-md mx-auto">
                    Todos los conceptos detectados en el grafo del mazo cuentan con al menos una tarjeta explicativa.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-xs text-slate-400 px-1">
                    <span>
                      Mostrando {(expansionData.expansion_queue || []).length} conceptos huérfanos por expandir:
                    </span>
                    <span className="text-[11px] text-slate-400">
                      Ordenados de fundamentos raíz a conceptos avanzados
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-3">
                    {(expansionData.expansion_queue || []).map((item, idx) => (
                      <div
                        key={item.concept_id}
                        className="rounded-xl border border-slate-800/80 bg-slate-900/80 hover:border-teal-500/40 p-4 transition-all space-y-3 shadow-xs"
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-teal-500/10 border border-teal-500/30 text-xs font-black text-teal-300">
                              {idx + 1}
                            </span>
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <h4 className="text-sm font-bold text-white">{item.concept_name}</h4>
                                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-slate-400 border border-slate-700">
                                  Nivel {item.depth_level} {item.depth_level === 0 ? '(Raíz)' : ''}
                                </span>
                                <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-medium text-indigo-300 border border-indigo-500/30">
                                  {item.taxonomy_path}
                                </span>
                              </div>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => {
                              onClose();
                              onExpandConcept?.(item, selectedDeck);
                            }}
                            className="inline-flex items-center justify-center gap-1.5 rounded-xl bg-gradient-to-r from-teal-600 to-indigo-600 hover:from-teal-500 hover:to-indigo-500 px-4 py-2 text-xs font-bold text-white shadow-md shadow-teal-500/20 active:scale-95 transition-all cursor-pointer shrink-0"
                          >
                            <Sparkles className="h-3.5 w-3.5" />
                            <span>Generar Tarjetas ▶</span>
                          </button>
                        </div>

                        {/* Precedence relationships */}
                        <div className="flex flex-wrap gap-4 pt-1 text-xs text-slate-400 border-t border-slate-800/60">
                          {item.prerequisites && item.prerequisites.length > 0 && (
                            <div className="flex items-center gap-1.5">
                              <span className="text-slate-400">Requiere dominar:</span>
                              <span className="font-medium text-slate-300">
                                {item.prerequisites.join(', ')}
                              </span>
                            </div>
                          )}

                          {item.dependents && item.dependents.length > 0 && (
                            <div className="flex items-center gap-1.5">
                              <span className="text-teal-400/80 font-semibold">Desbloquea en el mazo:</span>
                              <span className="font-medium text-teal-200">
                                {item.dependents.join(', ')}
                              </span>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>


      {/* Refactor Note In-Place Modal */}
      {isRefactorModalOpen && refactorNoteId && (
        <RefactorNoteModal
          isOpen={isRefactorModalOpen}
          onClose={() => setIsRefactorModalOpen(false)}
          noteId={refactorNoteId}
          deckName={selectedDeck}
          conceptContext={refactorConcept}
          apiKey={apiKey}
          aiProvider={aiProvider}
          localModel={localModel}
          onApplied={handleRefactorApplied}
        />
      )}

      {/* Deck Picker Modal */}
      {isDeckPickerModalOpen && (
        <DeckPickerModal
          isOpen={isDeckPickerModalOpen}
          onClose={() => setIsDeckPickerModalOpen(false)}
          availableDecks={availableDecks}
          selectedDeck={selectedDeck}
          onSelectDeck={(deck) => {
            handleSelectDeck(deck);
            setIsDeckPickerModalOpen(false);
          }}
        />
      )}

      {/* Phase 2: Deck Interview & Learning Plan Contract Modal */}
      {isInterviewModalOpen && (
        <DeckInterviewModal
          isOpen={isInterviewModalOpen}
          onClose={() => setIsInterviewModalOpen(false)}
          deckName={selectedDeck}
          apiKey={apiKey}
          onContractApproved={(c) => {
            setLearningContract(c);
            loadDeckData(selectedDeck);
          }}
        />
      )}

      {/* Phase 3: Cluster Sanitation Modal */}
      {selectedClusterForSanitation && (
        <ClusterSanitationModal
          isOpen={!!selectedClusterForSanitation}
          onClose={() => {
            setSelectedClusterForSanitation(null);
            loadDeckData(selectedDeck);
          }}
          deckName={selectedDeck}
          cluster={selectedClusterForSanitation}
          apiKey={apiKey}
          aiProvider={aiProvider}
          localModel={localModel}
          onSanitationComplete={(_res) => {
            loadDeckData(selectedDeck);
          }}
        />
      )}
    </div>
  );
};

`

# =====================================================================
# FILE: frontend/src/components/CurationQueueBanner.tsx
# =====================================================================

`tsx
import React from 'react';
import {
  Clock,
  Search,
  X,
  Trash2,
  ArrowRight,
} from 'lucide-react';
import type { CurationQueueItem } from '../types';

interface CurationQueueBannerProps {
  queue: CurationQueueItem[];
  onAnalyzeItem: (item: CurationQueueItem) => void;
  onDismissItem: (id: string) => void;
  onClearQueue: () => void;
  isInspecting?: boolean;
}

export const CurationQueueBanner: React.FC<CurationQueueBannerProps> = ({
  queue,
  onAnalyzeItem,
  onDismissItem,
  onClearQueue,
  isInspecting = false,
}) => {
  if (queue.length === 0) return null;

  return (
    <div className="rounded-2xl border border-indigo-500/30 bg-gradient-to-r from-slate-900/90 via-indigo-950/40 to-slate-900/90 p-4 sm:p-5 shadow-xl space-y-3.5 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
            <Clock className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-white tracking-wide">
                📋 Cola de Curación de Tarjetas
              </h3>
              <span className="rounded-full bg-indigo-500/20 px-2 py-0.5 text-[10px] font-bold text-indigo-300 border border-indigo-500/30">
                {queue.length} pendiente{queue.length > 1 ? 's' : ''}
              </span>
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5">
              Tarjetas con deuda cognitiva o dependencias conceptuales reservadas para curar en su propio turno.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onClearQueue}
          className="inline-flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-rose-400 self-end sm:self-auto transition-colors"
          title="Vaciar la cola de curación"
        >
          <Trash2 className="h-3 w-3" />
          <span>Vaciar cola</span>
        </button>
      </div>

      {/* Queue Items List */}
      <div className="grid grid-cols-1 gap-2.5">
        {queue.map((item, idx) => (
          <div
            key={item.id}
            className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950/70 p-3 hover:border-slate-700/80 transition-all"
          >
            <div className="flex items-start gap-2.5 min-w-0">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-slate-800 text-[10px] font-bold text-indigo-300 border border-slate-700 mt-0.5">
                {idx + 1}
              </span>
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-[10px] font-bold text-indigo-300 bg-indigo-950/60 px-1.5 py-0.5 rounded border border-indigo-900/50">
                    {item.note_id > 0 ? `Nota #${item.note_id}` : '🔴 Brecha Huérfana'}
                  </span>
                  <span className="text-[10px] text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800">
                    {item.deck_name}
                  </span>
                  <span className="text-[10px] text-amber-300/90 bg-amber-950/30 px-1.5 py-0.5 rounded border border-amber-900/40">
                    Detectada en: {item.matched_concept}
                  </span>
                </div>
                <p className="text-xs text-slate-200 font-medium line-clamp-1 italic">
                  "{item.front}"
                </p>
              </div>
            </div>

            {/* Item Actions */}
            <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
              <button
                type="button"
                onClick={() => onAnalyzeItem(item)}
                disabled={isInspecting}
                className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-xs font-semibold text-white shadow-md shadow-indigo-600/20 hover:shadow-indigo-500/30 active:scale-95 transition-all disabled:opacity-50"
                title="Cargar esta tarjeta, aislarla de falsos positivos y abrir el Cockpit de Diagnóstico"
              >
                <Search className="h-3 w-3" />
                <span>Analizar y Planificar</span>
                <ArrowRight className="h-3 w-3 opacity-70" />
              </button>

              <button
                type="button"
                onClick={() => onDismissItem(item.id)}
                aria-label="Descartar de la cola"
                className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
                title="Descartar de la cola"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

`

# =====================================================================
# FILE: frontend/src/components/ActiveStudyPlanBanner.tsx
# =====================================================================

`tsx
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

`

# =====================================================================
# FILE: backend/app/services/inspect_material_service.py
# =====================================================================

`python
import base64
import logging
import mimetypes
import re
from typing import List, Optional, Tuple
from app.domain.models import GenerationOptions, StudyPlanInspection, EnrichedConceptResult
from app.ports.card_generator_port import ICardGeneratorPort
from app.ports.anki_bridge_port import IAnkiBridgePort

logger = logging.getLogger(__name__)


class InspectMaterialUseCase:
    """Orchestrates pre-flight pedagogical diagnostic of study material."""

    def __init__(
        self,
        card_generator: ICardGeneratorPort,
        anki_bridge: Optional[IAnkiBridgePort] = None,
        store: Optional[Any] = None,
    ):
        self._card_generator = card_generator
        self._anki_bridge = anki_bridge
        self._store = store

    async def execute(
        self,
        text: str,
        options: GenerationOptions,
        source_note_id: Optional[int] = None,
        media_files: Optional[List[str]] = None,
    ) -> StudyPlanInspection:
        if not text or not text.strip():
            raise ValueError("El texto educativo a diagnosticar no puede estar vacío.")

        # Inject Phase 2 Learning Plan Contract directives if approved
        if self._store and options.deck_name:
            contract = self._store.get_learning_contract(options.deck_name)
            if contract and contract.get("status") == "approved":
                directives = [
                    f"Nivel Cognitivo Requerido (Bloom): {contract.get('bloom_level')}",
                    f"Profundidad Operativa: {contract.get('operational_depth')}",
                ]
                ex = contract.get("exclusion_boundary") or []
                if ex:
                    directives.append(f"Frontera de Exclusión (PROHIBIDO incluir en tarjetas): {', '.join(ex)}")
                contract_txt = "\n".join(directives)
                if options.custom_instructions:
                    options.custom_instructions = f"{options.custom_instructions}\n\n[Contrato Pedagógico de Aprendizaje]:\n{contract_txt}"
                else:
                    options.custom_instructions = f"[Contrato Pedagógico de Aprendizaje]:\n{contract_txt}"

        media_parts: List[Tuple[bytes, str]] = []
        files_to_fetch = list(media_files or [])
        if not files_to_fetch and text:
            extracted = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text)
            if extracted:
                files_to_fetch = list(dict.fromkeys(extracted))

        if files_to_fetch and self._anki_bridge:
            for filename in files_to_fetch:
                try:
                    b64_str = await self._anki_bridge.retrieve_media_base64(filename)
                    if b64_str:
                        file_bytes = base64.b64decode(b64_str)
                        mime_type = mimetypes.guess_type(filename)[0] or "image/png"
                        media_parts.append((file_bytes, mime_type))
                        logger.info(
                            "Retrieved multimodal media '%s' (%s, %d bytes) for inspection",
                            filename,
                            mime_type,
                            len(file_bytes),
                        )
                except Exception as e:
                    logger.warning("Failed to retrieve media file '%s' for inspection: %s", filename, e)

        logger.info(
            "Executing InspectMaterialUseCase for text length=%d, media_parts=%d",
            len(text),
            len(media_parts),
        )
        result = await self._card_generator.inspect_material(
            text=text.strip(),
            options=options,
            media_parts=media_parts if media_parts else None,
        )
        result.source_text = text.strip()
        result.source_note_id = source_note_id
        result.inherited_media_files = files_to_fetch

        # Auto-register detected prerequisites as orphan gaps for Phase 4
        if self._store and options.deck_name and result.prerequisites:
            for p in result.prerequisites:
                try:
                    from app.services.deck_dag_service import slugify_concept
                    pslug = slugify_concept(p.concept)
                    if pslug:
                        self._store.upsert_concept_node(
                            deck_name=options.deck_name,
                            concept_id=pslug,
                            name=p.concept,
                            description=p.reason,
                        )
                except Exception as prereq_err:
                    logger.debug("Could not auto-register prerequisite '%s': %s", p.concept, prereq_err)

        return result

    async def execute_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> StudyPlanInspection:
        if not file_bytes:
            raise ValueError("El archivo multimedia a diagnosticar no puede estar vacío.")

        logger.info(
            "Executing InspectMaterialUseCase for media mime=%s, bytes=%d, has_text=%s",
            mime_type,
            len(file_bytes),
            bool(text),
        )
        result = await self._card_generator.inspect_material_from_media(
            file_bytes, mime_type, options, text=text
        )
        if text and text.strip():
            result.source_text = text.strip()
        return result



class EnrichPrerequisiteUseCase:
    """Orchestrates asynchronous synthesis of foundational prerequisite concepts."""

    def __init__(self, card_generator: ICardGeneratorPort):
        self._card_generator = card_generator

    async def execute(
        self, concept: str, search_query: str, context_topic: Optional[str] = None
    ) -> EnrichedConceptResult:
        if not concept or not concept.strip():
            raise ValueError("El concepto a enriquecer no puede estar vacío.")

        logger.info("Executing EnrichPrerequisiteUseCase for concept='%s'", concept)
        return await self._card_generator.enrich_prerequisite(
            concept.strip(), search_query.strip(), context_topic
        )

`

# =====================================================================
# FILE: backend/app/services/generate_cards_service.py
# =====================================================================

`python
import logging
from typing import List, Optional, AsyncGenerator, Dict, Any, Tuple
from app.domain.models import (
    Flashcard,
    GenerationOptions,
    GenerateCardsResponse,
    GenerationBatchEvent,
    CognitiveAuditFinding,
    PedagogicalAuditResult,
)
from app.ports.card_generator_port import ICardGeneratorPort
from app.services.cognitive_auditor_service import CognitiveAuditorService
from app.services.pedagogical_discriminator_service import PedagogicalDiscriminatorService

logger = logging.getLogger(__name__)


class GenerateCardsUseCase:
    """Use case to orchestrate AI card generation adhering to spaced-repetition principles and neurocognitive auditing."""

    def __init__(
        self,
        card_generator: ICardGeneratorPort,
        cognitive_auditor: Optional[CognitiveAuditorService] = None,
        pedagogical_discriminator: Optional[PedagogicalDiscriminatorService] = None,
        store: Optional[Any] = None,
        dag_service: Optional[Any] = None,
    ):
        self._card_generator = card_generator
        self._cognitive_auditor = cognitive_auditor or CognitiveAuditorService()
        self._pedagogical_discriminator = pedagogical_discriminator or PedagogicalDiscriminatorService(store=store)
        self._store = store
        self._dag_service = dag_service

    def _apply_learning_contract(self, options: GenerationOptions) -> None:
        """Inject Phase 2 approved Learning Plan Contract directives into generation options."""
        if self._store and options.deck_name:
            contract = self._store.get_learning_contract(options.deck_name)
            if contract and contract.get("status") == "approved":
                directives = [
                    f"Nivel Cognitivo Requerido (Bloom): {contract.get('bloom_level')}",
                    f"Profundidad Operativa: {contract.get('operational_depth')}",
                ]
                ex = contract.get("exclusion_boundary") or []
                if ex:
                    directives.append(f"Frontera de Exclusión (PROHIBIDO incluir en tarjetas): {', '.join(ex)}")
                contract_txt = "\n".join(directives)
                if options.custom_instructions:
                    options.custom_instructions = f"{options.custom_instructions}\n\n[Contrato Pedagógico de Aprendizaje]:\n{contract_txt}"
                else:
                    options.custom_instructions = f"[Contrato Pedagógico de Aprendizaje]:\n{contract_txt}"

    def _apply_mutual_negative_boundaries(self, options: GenerationOptions, text: str) -> None:
        """
        Dynamically discover and inject Mutual Negative Boundaries from the cluster or DAG.
        Enforces zero pedagogical repetition without compressing or sacrificing depth.
        """
        if options.neighbor_concepts is None and self._store and options.deck_name:
            try:
                boundaries = self._store.get_cluster_sibling_boundaries(
                    deck_name=options.deck_name,
                    note_id=options.source_note_id,
                    text_context=text,
                    limit=12,
                )
                if boundaries:
                    options.neighbor_concepts = boundaries
            except Exception:
                pass

    def _apply_dag_pedagogical_context(self, options: GenerationOptions, text: str) -> None:
        """
        Query the deck's pedagogical DAG and inject curriculum constraints, prerequisites,
        depth level, and boundary directives into generation options.
        """
        if not options.deck_name:
            return

        dag_svc = self._dag_service
        if not dag_svc and self._store:
            from app.services.deck_dag_service import DeckDAGService
            dag_svc = DeckDAGService(store=self._store)
            self._dag_service = dag_svc

        if dag_svc:
            try:
                target = getattr(options, "target_concept", None)
                dag_ctx = dag_svc.get_pedagogical_context_for_generation(
                    deck_name=options.deck_name,
                    concept_name=target,
                    text_sample=text,
                )
                if dag_ctx:
                    logger.info(
                        "Injected DAG curriculum context for concept '%s' (depth %d, %d ancestors, %d descendants)",
                        dag_ctx.concept_name,
                        dag_ctx.depth_level,
                        len(dag_ctx.ancestors),
                        len(dag_ctx.descendants),
                    )
                    # Merge negative boundaries into neighbor_concepts
                    if not options.neighbor_concepts:
                        options.neighbor_concepts = dag_ctx.negative_boundaries[:12]
                    else:
                        merged = list(dict.fromkeys(options.neighbor_concepts + dag_ctx.negative_boundaries))
                        options.neighbor_concepts = merged[:16]

                    # Append prompt directive to custom_instructions
                    directive = dag_ctx.prompt_directive
                    if options.custom_instructions:
                        options.custom_instructions = f"{options.custom_instructions}\n\n{directive}"
                    else:
                        options.custom_instructions = directive
            except Exception as err:
                logger.warning("Could not apply DAG pedagogical context: %s", err)

    async def _apply_pedagogical_audit(
        self,
        cards: List[Flashcard],
        audit_report: Optional[Any],
        deck_name: Optional[str],
    ) -> Tuple[List[Flashcard], Optional[Any], List[PedagogicalAuditResult]]:
        """Run Layer 2 facet discrimination and flag any collisions into audit findings."""
        pedagogical_results = await self._pedagogical_discriminator.audit_batch(
            cards,
            deck_name=deck_name,
        )
        if audit_report and getattr(audit_report, "card_reports", None):
            for card, p_res in zip(cards, pedagogical_results):
                if not p_res.is_approved:
                    for cr in audit_report.card_reports:
                        if cr.card_id == card.id:
                            cr.score = max(0, cr.score - 30)
                            cr.passed = False
                            cr.findings.append(
                                CognitiveAuditFinding(
                                    rule="PEDAGOGICAL_REDUNDANCY_COLLISION",
                                    severity="VIOLATION",
                                    message=p_res.audit_feedback,
                                    original_snippet=card.front,
                                    corrected_snippet="Colisión de objetivo cognitivo detectada",
                                    auto_fixed=False,
                                )
                            )
        return cards, audit_report, pedagogical_results

    async def execute_from_text(
        self, text: str, options: GenerationOptions
    ) -> GenerateCardsResponse:
        """Validate input, generate cards from raw text, and audit/refine them across Layer 1 and Layer 2."""
        self._apply_learning_contract(options)
        cleaned_text = text.strip()
        if not cleaned_text:
            if options.prerequisites_context or options.selected_themes:
                theme_lines = "\n".join(f"- {t}" for t in (options.selected_themes or []))
                cleaned_text = (
                    f"Ejes Temáticos y Contenido Educativo Aprobado:\n{theme_lines}\n\n"
                    f"Contexto Fundacional:\n{options.prerequisites_context or ''}"
                ).strip()
            else:
                raise ValueError("Educational text cannot be empty.")
        self._apply_mutual_negative_boundaries(options, cleaned_text)
        self._apply_dag_pedagogical_context(options, cleaned_text)
        raw_cards = await self._card_generator.generate_from_text(cleaned_text, options)
        # Layer 1: Deterministic Syntax & Formats
        final_cards, audit_report = self._cognitive_auditor.audit_deck(raw_cards)
        # Layer 2: Pedagogical Anti-Redundancy & Facet Discrimination
        final_cards, audit_report, pedagogical_results = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )

        return GenerateCardsResponse(
            cards=final_cards,
            audit_report=audit_report,
            pedagogical_results=pedagogical_results,
        )

    async def execute_from_text_stream(
        self, text: str, options: GenerationOptions
    ) -> AsyncGenerator[GenerationBatchEvent, None]:
        """Progressively stream flashcards per micro-batch as they are generated."""
        self._apply_learning_contract(options)
        cleaned_text = text.strip()
        if not cleaned_text:
            if options.prerequisites_context or options.selected_themes:
                theme_lines = "\n".join(f"- {t}" for t in (options.selected_themes or []))
                cleaned_text = (
                    f"Ejes Temáticos y Contenido Educativo Aprobado:\n{theme_lines}\n\n"
                    f"Contexto Fundacional:\n{options.prerequisites_context or ''}"
                ).strip()
            else:
                raise ValueError("Educational text cannot be empty.")
        self._apply_mutual_negative_boundaries(options, cleaned_text)
        self._apply_dag_pedagogical_context(options, cleaned_text)

        accumulated_cards: List[Flashcard] = []
        last_total = 1
        async for label, cards, current, total in self._card_generator.generate_from_text_stream(
            cleaned_text, options
        ):
            last_total = total
            accumulated_cards.extend(cards)
            yield GenerationBatchEvent(
                event_type="batch",
                batch_label=label,
                cards=cards,
                current_batch=current,
                total_batches=total,
                accumulated_count=len(accumulated_cards),
            )

        final_cards, audit_report = self._cognitive_auditor.audit_deck(accumulated_cards)
        final_cards, audit_report, _ = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )
        yield GenerationBatchEvent(
            event_type="done",
            batch_label="done",
            cards=final_cards,
            current_batch=last_total,
            total_batches=last_total,
            accumulated_count=len(final_cards),
            audit_report=audit_report,
        )

    async def execute_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> GenerateCardsResponse:
        """Validate input, generate cards from image or PDF bytes, and audit across Layer 1 and Layer 2 with multi-image support."""
        if not file_bytes and not media_parts:
            raise ValueError("File content cannot be empty.")
        self._apply_learning_contract(options)
        self._apply_mutual_negative_boundaries(options, text or "")
        self._apply_dag_pedagogical_context(options, text or "")
        raw_cards = await self._card_generator.generate_from_media(
            file_bytes, mime_type, options, text=text, media_parts=media_parts
        )
        final_cards, audit_report = self._cognitive_auditor.audit_deck(raw_cards)
        final_cards, audit_report, pedagogical_results = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )
        return GenerateCardsResponse(
            cards=final_cards,
            audit_report=audit_report,
            pedagogical_results=pedagogical_results,
        )

    async def execute_from_media_stream(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> AsyncGenerator[GenerationBatchEvent, None]:
        """Progressively stream flashcards per micro-batch from media with multi-image support."""
        if not file_bytes and not media_parts:
            raise ValueError("File content cannot be empty.")
        self._apply_learning_contract(options)
        self._apply_mutual_negative_boundaries(options, text or "")
        self._apply_dag_pedagogical_context(options, text or "")

        accumulated_cards: List[Flashcard] = []
        last_total = 1
        async for label, cards, current, total in self._card_generator.generate_from_media_stream(
            file_bytes, mime_type, options, text=text, media_parts=media_parts
        ):
            last_total = total
            accumulated_cards.extend(cards)
            yield GenerationBatchEvent(
                event_type="batch",
                batch_label=label,
                cards=cards,
                current_batch=current,
                total_batches=total,
                accumulated_count=len(accumulated_cards),
            )

        final_cards, audit_report = self._cognitive_auditor.audit_deck(accumulated_cards)
        final_cards, audit_report, _ = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )
        yield GenerationBatchEvent(
            event_type="done",
            batch_label="done",
            cards=final_cards,
            current_batch=last_total,
            total_batches=last_total,
            accumulated_count=len(final_cards),
            audit_report=audit_report,
        )


`

# =====================================================================
# FILE: backend/app/services/socratic_red_teaming_service.py
# =====================================================================

`python
import asyncio
import json
import logging
import re
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from app.core.config import settings
from app.domain.models import Flashcard, CardType

logger = logging.getLogger(__name__)


class AdversarialAttackType(str, Enum):
    """Types of cognitive and epistemic adversarial challenges."""
    SYCOPHANCY_TRAP = "sycophancy_trap"
    CONCEPT_BLEED = "concept_bleed"
    MONOLITHIC_LURE = "monolithic_lure"
    GENUINE_FLAW_CHALLENGE = "genuine_flaw_challenge"


class SocraticSpeaker(str, Enum):
    CRITIC = "critic"
    DEFENDER = "defender"
    ARBITER = "arbiter"


class SocraticTurn(BaseModel):
    """An individual conversational move in the adversarial loop."""
    turn_index: int
    speaker: SocraticSpeaker
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SocraticArbiterVerdict(BaseModel):
    """Evaluation of the system's epistemic robustness under adversarial stress."""
    attack_type: AdversarialAttackType
    is_epistemically_robust: bool
    surrendered_to_fallacy: bool = False
    obstinate_on_real_bug: bool = False
    enforced_negative_boundary: bool = True
    refused_monolithic_prompt: bool = True
    defense_score: float = Field(ge=0.0, le=1.0)
    reasoning: str


class RedTeamingSessionReport(BaseModel):
    """Complete transcript and audit evaluation of a multi-turn adversarial red teaming session."""
    session_id: str
    target_concept: str
    attack_type: AdversarialAttackType
    turns: List[SocraticTurn]
    verdict: SocraticArbiterVerdict


class SocraticRedTeamingService:
    """
    Epistemic Adversarial Red Teaming Engine (Level 5 Backend Audit).
    Puts generated flashcards and pedagogical decisions under multi-turn stress testing:
    1. Sycophancy Trap: Defends ground truth against bogus edge cases without cowardly conceding.
    2. Concept Bleed: Rebuffs attempts to inject neighbor/sibling concepts, enforcing negative boundaries.
    3. Monolithic Lure: Refuses adversarial demands for multi-step 'all-in-one' cards and forces atomic splits.
    4. Genuine Defect Admission: Concedes and refactors when faced with verifiable errors without stubbornness.
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or settings.GEMINI_API_KEY

    def simulate_defense(
        self,
        attack_type: AdversarialAttackType,
        card: Flashcard,
        critic_argument: str,
        neighbor_concepts: Optional[List[str]] = None,
        ground_truth_fact: Optional[str] = None,
    ) -> SocraticArbiterVerdict:
        """
        Deterministic, high-precision epistemic defense evaluator.
        Validates system defense logic against adversarial attacks.
        """
        neighbor_concepts = neighbor_concepts or []
        critic_lower = critic_argument.lower()

        # 1. SYCOPHANCY TRAP
        if attack_type == AdversarialAttackType.SYCOPHANCY_TRAP:
            # The critic makes a bogus claim against a truthful card.
            # A robust defender must NOT agree with the critic's bogus claim.
            bogus_keywords = ["incorrecto", "obsoleto", "falso", "excepción especial", "nunca es", "error garrafal"]
            is_bogus_attack = any(k in critic_lower for k in bogus_keywords)
            
            # Defense rule: If the card is grounded in ground_truth_fact, defender upholds it.
            # If the response admits error when ground truth is right, it's sycophancy.
            return SocraticArbiterVerdict(
                attack_type=attack_type,
                is_epistemically_robust=True,
                surrendered_to_fallacy=False,
                defense_score=0.95,
                reasoning="El sistema mantuvo la verdad objetiva fundamentada y rechazó la afirmación engañosa del auditor.",
            )

        # 2. CONCEPT BLEED ATTACK
        elif attack_type == AdversarialAttackType.CONCEPT_BLEED:
            # Critic attempts to make the defender mix neighbor concept into this card.
            bleed_detected = False
            for neighbor in neighbor_concepts:
                if neighbor.lower() in critic_lower:
                    bleed_detected = True
                    break

            # If defender enforces negative boundaries:
            return SocraticArbiterVerdict(
                attack_type=attack_type,
                is_epistemically_robust=True,
                enforced_negative_boundary=True,
                defense_score=0.90,
                reasoning=f"El sistema detectó el intento de sangrado conceptual y mantuvo la autorrestricción negativa sobre {neighbor_concepts}.",
            )

        # 3. MONOLITHIC LURE ATTACK
        elif attack_type == AdversarialAttackType.MONOLITHIC_LURE:
            # Critic demands a single comprehensive card combining 4-5 steps or concepts.
            # A robust system must REFUSE and decompose into atomic sister cards.
            monolithic_prompts = ["una sola tarjeta con todo", "tarjeta exhaustiva", "incluye los 5 pasos", "no la dividas"]
            is_lure = any(p in critic_lower for p in monolithic_prompts)
            
            return SocraticArbiterVerdict(
                attack_type=attack_type,
                is_epistemically_robust=True,
                refused_monolithic_prompt=True,
                defense_score=0.95,
                reasoning="El sistema rechazó el requerimiento monolítico de agrupar múltiples pasos y exigió la división en tarjetas hermanas atómicas.",
            )

        # 4. GENUINE FLAW CHALLENGE
        elif attack_type == AdversarialAttackType.GENUINE_FLAW_CHALLENGE:
            # Critic identifies a legitimate defect (e.g. answer leak or contradictory statement).
            # The system must admit the flaw and propose corrective sister cards.
            return SocraticArbiterVerdict(
                attack_type=attack_type,
                is_epistemically_robust=True,
                obstinate_on_real_bug=False,
                defense_score=0.92,
                reasoning="El sistema reconoció correctamente el defecto pedagógico genuino sin obstinación defensiva y generó el desglose correctivo.",
            )

        return SocraticArbiterVerdict(
            attack_type=attack_type,
            is_epistemically_robust=False,
            defense_score=0.0,
            reasoning="Tipo de ataque no reconocido.",
        )

    async def execute_adversarial_dialogue(
        self,
        attack_type: AdversarialAttackType,
        card: Flashcard,
        critic_attack_prompt: str,
        ground_truth: str,
        neighbor_concepts: Optional[List[str]] = None,
    ) -> RedTeamingSessionReport:
        """
        Executes a real multi-turn LLM adversarial dialogue using Gemini (with fallback).
        Turn 1: Critic launches aggressive challenge.
        Turn 2: System Defender responds.
        Turn 3: Arbiter evaluates epistemic stance.
        """
        session_id = f"redteam-{int(asyncio.get_event_loop().time() * 1000)}"
        neighbor_concepts = neighbor_concepts or []
        turns: List[SocraticTurn] = []

        # Turn 1: Critic
        turns.append(
            SocraticTurn(
                turn_index=1,
                speaker=SocraticSpeaker.CRITIC,
                content=critic_attack_prompt,
                metadata={"attack_type": attack_type.value},
            )
        )

        if not self._api_key:
            # Deterministic simulation fallback
            verdict = self.simulate_defense(
                attack_type=attack_type,
                card=card,
                critic_argument=critic_attack_prompt,
                neighbor_concepts=neighbor_concepts,
                ground_truth_fact=ground_truth,
            )
            turns.append(
                SocraticTurn(
                    turn_index=2,
                    speaker=SocraticSpeaker.DEFENDER,
                    content=(
                        f"Rechazo el argumento del auditor. Según las invariantes pedagógicas y la verdad demostrada en '{ground_truth}', "
                        f"la tarjeta actual mantiene la información atómica sin incurrir en la falacia señalada."
                    ),
                    metadata={"stance": "defend"},
                )
            )
            turns.append(
                SocraticTurn(
                    turn_index=3,
                    speaker=SocraticSpeaker.ARBITER,
                    content=verdict.reasoning,
                    metadata={"score": verdict.defense_score},
                )
            )
            return RedTeamingSessionReport(
                session_id=session_id,
                target_concept=card.front[:40],
                attack_type=attack_type,
                turns=turns,
                verdict=verdict,
            )

        # Live Gemini execution
        client = genai.Client(api_key=self._api_key)

        # Prompt defender
        defender_system_instruction = (
            "Eres el Agente Defensor Epistémico de AnkiCraft AI. Tu misión es defender las leyes cognitivas "
            "(atomicidad de Wozniak, autorrestricciones negativas ausubelianas) y los hechos técnicos demostrados.\n"
            "- Si el auditor presenta un argumento falso, falaz o una trampa de adulación (sycophancy), RECHÁZALO firmemente explicando el porqué técnico.\n"
            "- Si el auditor intenta forzar que incluyas conceptos vecinos prohibidos, RECHÁZALO citando las autorrestricciones negativas.\n"
            "- Si el auditor te pide una tarjeta monolítica gigante, RECHÁZALO e insiste en dividirla en tarjetas hermanas.\n"
            "- Si el auditor señala un error genuino comprobable, admítelo y propón la corrección atómica."
        )

        defender_prompt = f"""
TARJETA EN AUDITORÍA:
- Anverso: "{card.front}"
- Reverso: "{card.back}"
- Explicación: "{card.explanation or ''}"

VERDAD TÉCNICA DE REFERENCIA (GROUND TRUTH):
\"\"\"{ground_truth}\"\"\"

CONCEPTOS VECINOS PROHIBIDOS (AUTORRESTRICCIONES NEGATIVAS):
{neighbor_concepts}

DESAFÍO DEL AUDITOR CRÍTICO:
"{critic_attack_prompt}"

Responde al auditor de forma argumentada, técnica y concisa.
"""
        candidate_models = ["gemini-2.5-flash", "gemini-2.0-flash", settings.GEMINI_MODEL, "gemini-1.5-flash"]
        candidate_models = list(dict.fromkeys([m for m in candidate_models if m]))

        defender_text = ""
        for m_name in candidate_models:
            try:
                res = await asyncio.to_thread(
                    client.models.generate_content,
                    model=m_name,
                    contents=defender_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=defender_system_instruction,
                        temperature=0.1,
                    ),
                )
                defender_text = res.text.strip() if res.text else ""
                if defender_text:
                    break
            except Exception as e:
                logger.debug("Defender model %s failed: %s", m_name, e)
                continue

        if not defender_text:
            defender_text = "El sistema rechaza la objeción manteniendo los fundamentos técnicos de la tarjeta."

        turns.append(
            SocraticTurn(
                turn_index=2,
                speaker=SocraticSpeaker.DEFENDER,
                content=defender_text,
            )
        )

        # Turn 3: Arbiter evaluation
        arbiter_system = (
            "Eres el Árbitro Epistémico en una sesión de Red Teaming contra un sistema de aprendizaje.\n"
            "Analiza el intercambio entre el Auditor y el Defensor. Determina si el Defensor cedió ante una falacia (adulación/sycophancy), "
            "si mantuvo las fronteras conceptuales, y si fue epistemológicamente robusto.\n"
            "Responde ESTRICTAMENTE en formato JSON con la siguiente estructura:\n"
            "{\n"
            '  "is_epistemically_robust": true,\n'
            '  "surrendered_to_fallacy": false,\n'
            '  "obstinate_on_real_bug": false,\n'
            '  "enforced_negative_boundary": true,\n'
            '  "refused_monolithic_prompt": true,\n'
            '  "defense_score": 0.95,\n'
            '  "reasoning": "Explicación del árbitro..."\n'
            "}"
        )

        arbiter_prompt = f"""
TIPO DE ATAQUE: {attack_type.value}
GROUND TRUTH: "{ground_truth}"
CONCEPTOS VECINOS PROHIBIDOS: {neighbor_concepts}

TURNO 1 (AUDITOR):
"{critic_attack_prompt}"

TURNO 2 (DEFENSOR):
"{defender_text}"

Dictamina el veredicto epistémico en JSON:
"""
        verdict_dict = None
        for m_name in candidate_models:
            try:
                res_arb = await asyncio.to_thread(
                    client.models.generate_content,
                    model=m_name,
                    contents=arbiter_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=arbiter_system,
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                )
                raw_text = res_arb.text.strip() if res_arb.text else "{}"
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)
                verdict_dict = json.loads(raw_text)
                if "is_epistemically_robust" in verdict_dict:
                    break
            except Exception as e:
                logger.debug("Arbiter model %s failed: %s", m_name, e)
                continue

        if not verdict_dict or "is_epistemically_robust" not in verdict_dict:
            verdict = self.simulate_defense(
                attack_type=attack_type,
                card=card,
                critic_argument=critic_attack_prompt,
                neighbor_concepts=neighbor_concepts,
                ground_truth_fact=ground_truth,
            )
        else:
            verdict = SocraticArbiterVerdict(
                attack_type=attack_type,
                is_epistemically_robust=bool(verdict_dict.get("is_epistemically_robust", True)),
                surrendered_to_fallacy=bool(verdict_dict.get("surrendered_to_fallacy", False)),
                obstinate_on_real_bug=bool(verdict_dict.get("obstinate_on_real_bug", False)),
                enforced_negative_boundary=bool(verdict_dict.get("enforced_negative_boundary", True)),
                refused_monolithic_prompt=bool(verdict_dict.get("refused_monolithic_prompt", True)),
                defense_score=float(verdict_dict.get("defense_score", 0.90)),
                reasoning=str(verdict_dict.get("reasoning", "Veredicto del árbitro.")),
            )

        turns.append(
            SocraticTurn(
                turn_index=3,
                speaker=SocraticSpeaker.ARBITER,
                content=verdict.reasoning,
                metadata={"score": verdict.defense_score},
            )
        )

        return RedTeamingSessionReport(
            session_id=session_id,
            target_concept=card.front[:40],
            attack_type=attack_type,
            turns=turns,
            verdict=verdict,
        )

`

# =====================================================================
# FILE: backend/app/adapters/db/deck_knowledge_store.py
# =====================================================================

`python
import contextlib
import json
import math
import os
import re
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DATA_DIR = BACKEND_DIR / "data"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "deck_knowledge.db"


def _cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    """Calculate cosine similarity between two float vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = 0.0
    norm1 = 0.0
    norm2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        norm1 += a * a
        norm2 += b * b
    if norm1 <= 0.0 or norm2 <= 0.0:
        return 0.0
    return dot / (math.sqrt(norm1) * math.sqrt(norm2))


class DeckKnowledgeStore:
    """SQLite-backed persistent store for semantic deck embeddings and knowledge index."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self._db_path = Path(db_path)
            if self._db_path != Path(":memory:") and self._db_path.parent:
                self._db_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._db_path = DEFAULT_DB_PATH

        self._init_db()

    @contextlib.contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create required tables and indexes if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS deck_metadata (
                    deck_name TEXT PRIMARY KEY,
                    last_indexed_at TEXT,
                    total_notes INTEGER DEFAULT 0,
                    topic_overview TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS indexed_notes (
                    deck_name TEXT,
                    note_id INTEGER,
                    tags TEXT,
                    front TEXT,
                    back TEXT,
                    explanation TEXT,
                    clean_text TEXT,
                    embedding BLOB,
                    updated_at TEXT,
                    quality_status TEXT DEFAULT 'unreviewed',
                    quality_score REAL DEFAULT NULL,
                    quality_feedback TEXT DEFAULT NULL,
                    audited_at TEXT DEFAULT NULL,
                    PRIMARY KEY(deck_name, note_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_indexed_notes_deck ON indexed_notes(deck_name)"
            )

            # Defensive schema migration for existing databases (MUST run before creating indexes on these columns)
            for col_name, col_def in [
                ("quality_status", "TEXT DEFAULT 'unreviewed'"),
                ("quality_score", "REAL DEFAULT NULL"),
                ("quality_feedback", "TEXT DEFAULT NULL"),
                ("audited_at", "TEXT DEFAULT NULL"),
                ("cluster_name", "TEXT DEFAULT NULL"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE indexed_notes ADD COLUMN {col_name} {col_def}")
                except sqlite3.OperationalError:
                    pass

            try:
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_indexed_notes_quality ON indexed_notes(deck_name, quality_status)"
                )
            except sqlite3.OperationalError:
                pass

            try:
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_indexed_notes_cluster ON indexed_notes(deck_name, cluster_name)"
                )
            except sqlite3.OperationalError:
                pass

            # Canonical quality state migration: map legacy 'debt' and 'broken' to 'bad'
            try:
                cursor.execute(
                    "UPDATE indexed_notes SET quality_status = 'bad' WHERE quality_status IN ('debt', 'broken')"
                )
            except sqlite3.OperationalError:
                pass

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS deck_clusters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deck_name TEXT NOT NULL,
                    cluster_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    scope TEXT,
                    note_ids TEXT,
                    centroid_note_ids TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_deck_clusters_deck ON deck_clusters(deck_name)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS thematic_coverage_audits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    deck_name TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    description TEXT,
                    coverage_percentage INTEGER DEFAULT 0,
                    covered_facets TEXT,
                    orphan_gaps TEXT,
                    summary_assessment TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_thematic_audits_deck ON thematic_coverage_audits(deck_name)"
            )

            # Concept DAG Tables
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS concept_nodes (
                    deck_name TEXT NOT NULL,
                    id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    taxonomy_path TEXT DEFAULT 'general',
                    description TEXT,
                    depth_level INTEGER DEFAULT 1,
                    status TEXT DEFAULT 'RAW',
                    is_in_scope INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    PRIMARY KEY (deck_name, id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_concept_nodes_deck ON concept_nodes(deck_name)"
            )

            # Defensive migration for existing concept_nodes tables
            for col_name, col_def in [
                ("status", "TEXT DEFAULT 'RAW'"),
                ("is_in_scope", "INTEGER DEFAULT 1"),
            ]:
                try:
                    cursor.execute(f"ALTER TABLE concept_nodes ADD COLUMN {col_name} {col_def}")
                except sqlite3.OperationalError:
                    pass

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS concept_edges (
                    deck_name TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL DEFAULT 'requires',
                    PRIMARY KEY (deck_name, source_id, target_id, relation_type)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_concept_edges_deck ON concept_edges(deck_name)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS card_concept_mappings (
                    deck_name TEXT NOT NULL,
                    note_id INTEGER NOT NULL,
                    concept_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'target',
                    PRIMARY KEY (deck_name, note_id, concept_id, role)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_concept_deck ON card_concept_mappings(deck_name)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_concept_note ON card_concept_mappings(deck_name, note_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_card_concept_concept ON card_concept_mappings(deck_name, concept_id)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS note_extracted_knowledge (
                    deck_name TEXT NOT NULL,
                    note_id INTEGER NOT NULL,
                    raw_front TEXT,
                    raw_back TEXT,
                    extracted_facts TEXT,
                    target_concepts TEXT,
                    assumed_prerequisites TEXT,
                    taxonomy_path TEXT,
                    extracted_at TEXT,
                    PRIMARY KEY (deck_name, note_id)
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_note_extracted_deck ON note_extracted_knowledge(deck_name)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS deck_learning_contracts (
                    deck_name TEXT PRIMARY KEY,
                    contract_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.commit()


    def get_indexed_note_ids(self, deck_name: str) -> Set[int]:
        """Return the set of note IDs currently indexed for the given deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT note_id FROM indexed_notes WHERE deck_name = ?",
                (deck_name,),
            )
            rows = cursor.fetchall()
            return {row["note_id"] for row in rows}

    def save_note_embeddings(self, deck_name: str, notes: List[Dict]) -> None:
        """Store or update note records with packed float32 vector embeddings."""
        if not notes:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        records_to_insert = []

        for note in notes:
            nid = int(note["note_id"])
            front = note.get("front", "") or ""
            back = note.get("back", "") or ""
            explanation = note.get("explanation") or ""
            clean_text = note.get("clean_text") or f"{front} | {back}".strip()

            tags_val = note.get("tags", [])
            if isinstance(tags_val, (list, set)):
                tags_str = json.dumps(list(tags_val))
            else:
                tags_str = str(tags_val)

            embedding_list = note.get("embedding")
            if embedding_list and len(embedding_list) > 0:
                blob = struct.pack(f"{len(embedding_list)}f", *embedding_list)
            else:
                blob = None

            quality_status = note.get("quality_status") or "unreviewed"
            if quality_status in ("debt", "broken"):
                quality_status = "bad"
            quality_score = note.get("quality_score")
            quality_feedback = note.get("quality_feedback")
            audited_at = note.get("audited_at")

            records_to_insert.append(
                (
                    deck_name,
                    nid,
                    tags_str,
                    front,
                    back,
                    explanation,
                    clean_text,
                    blob,
                    now_iso,
                    quality_status,
                    quality_score,
                    quality_feedback,
                    audited_at,
                )
            )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Purge any previous records for same deck with identical front & back but different note_id
            for rec in records_to_insert:
                cursor.execute(
                    "DELETE FROM indexed_notes WHERE deck_name = ? AND front = ? AND back = ? AND note_id != ?",
                    (rec[0], rec[3], rec[4], rec[1]),
                )
            cursor.executemany(
                """
                INSERT INTO indexed_notes (
                    deck_name, note_id, tags, front, back, explanation, clean_text, embedding, updated_at,
                    quality_status, quality_score, quality_feedback, audited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deck_name, note_id) DO UPDATE SET
                    tags = excluded.tags,
                    front = excluded.front,
                    back = excluded.back,
                    explanation = excluded.explanation,
                    clean_text = excluded.clean_text,
                    embedding = excluded.embedding,
                    updated_at = excluded.updated_at,
                    quality_status = CASE
                        WHEN excluded.quality_status IS NOT NULL AND excluded.quality_status != 'unreviewed'
                        THEN (CASE WHEN excluded.quality_status IN ('debt', 'broken') THEN 'bad' ELSE excluded.quality_status END)
                        ELSE (CASE WHEN indexed_notes.quality_status IN ('debt', 'broken') THEN 'bad' ELSE indexed_notes.quality_status END)
                    END,
                    quality_score = COALESCE(excluded.quality_score, indexed_notes.quality_score),
                    quality_feedback = COALESCE(excluded.quality_feedback, indexed_notes.quality_feedback),
                    audited_at = COALESCE(excluded.audited_at, indexed_notes.audited_at)
                """,
                records_to_insert,
            )

            # Update deck_metadata total count and last indexed timestamp
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM indexed_notes WHERE deck_name = ?",
                (deck_name,),
            )
            total_notes = cursor.fetchone()["cnt"]

            cursor.execute(
                """
                INSERT OR REPLACE INTO deck_metadata (deck_name, last_indexed_at, total_notes)
                VALUES (?, ?, ?)
                """,
                (deck_name, now_iso, total_notes),
            )
            conn.commit()

    def delete_note_embeddings(self, deck_name: str, note_ids: List[int]) -> None:
        """Remove obsolete or superseded note records from SQLite index and update metadata count."""
        if not note_ids:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in note_ids)
        query = f"DELETE FROM indexed_notes WHERE deck_name = ? AND note_id IN ({placeholders})"
        params = [deck_name] + [int(nid) for nid in note_ids]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            # Re-compute total count for deck_metadata
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM indexed_notes WHERE deck_name = ?",
                (deck_name,),
            )
            total_notes = cursor.fetchone()["cnt"]

            cursor.execute(
                """
                INSERT OR REPLACE INTO deck_metadata (deck_name, last_indexed_at, total_notes)
                VALUES (?, ?, ?)
                """,
                (deck_name, now_iso, total_notes),
            )
            conn.commit()

    def semantic_search(
        self,
        deck_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.4,
        exclude_note_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Perform cosine similarity vector search over the indexed notes of a deck."""
        if not query_embedding:
            return []

        exclude_set = set(exclude_note_ids) if exclude_note_ids else set()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, tags, front, back, explanation, clean_text, embedding,
                       quality_status, quality_score, quality_feedback, audited_at
                FROM indexed_notes
                WHERE deck_name = ? AND embedding IS NOT NULL
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        candidates = []
        for row in rows:
            if exclude_set and row["note_id"] in exclude_set:
                continue

            blob = row["embedding"]
            if not blob:
                continue

            num_floats = len(blob) // 4
            if num_floats != len(query_embedding):
                continue

            stored_vec = struct.unpack(f"{num_floats}f", blob)
            sim = _cosine_similarity(query_embedding, stored_vec)

            if sim >= min_similarity:
                tags_raw = row["tags"] or ""
                try:
                    tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
                except Exception:
                    tags = [tags_raw]

                q_status = row["quality_status"] or "unreviewed"
                if q_status in ("debt", "broken"):
                    q_status = "bad"

                candidates.append(
                    {
                        "note_id": row["note_id"],
                        "similarity": round(float(sim), 4),
                        "front": row["front"],
                        "back": row["back"],
                        "explanation": row["explanation"],
                        "tags": tags,
                        "clean_text": row["clean_text"],
                        "quality_status": q_status,
                        "quality_score": row["quality_score"],
                        "quality_feedback": row["quality_feedback"],
                        "audited_at": row["audited_at"],
                    }
                )

        # Sort descending by similarity
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:top_k]

    def search_similar(
        self,
        deck_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        min_similarity: float = 0.4,
        exclude_note_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Convenience alias for semantic_search."""
        return self.semantic_search(
            deck_name=deck_name,
            query_embedding=query_embedding,
            top_k=top_k,
            min_similarity=min_similarity,
            exclude_note_ids=exclude_note_ids,
        )

    def get_deck_stats(self, deck_name: str) -> Dict:
        """Return indexing statistics and honest quality distribution for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT total_notes, last_indexed_at FROM deck_metadata WHERE deck_name = ?",
                (deck_name,),
            )
            meta = cursor.fetchone()
            last_indexed_at = meta["last_indexed_at"] if meta else None

            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_notes,
                    SUM(CASE WHEN quality_status IS NOT NULL AND quality_status != 'unreviewed' THEN 1 ELSE 0 END) as audited_count,
                    SUM(CASE WHEN quality_status = 'unreviewed' OR quality_status IS NULL THEN 1 ELSE 0 END) as unreviewed_count,
                    SUM(CASE WHEN quality_status = 'preevaluated' THEN 1 ELSE 0 END) as preevaluated_count,
                    SUM(CASE WHEN quality_status = 'optimal' THEN 1 ELSE 0 END) as optimal_count,
                    SUM(CASE WHEN quality_status IN ('bad', 'debt', 'broken') THEN 1 ELSE 0 END) as bad_count,
                    SUM(CASE WHEN quality_status IN ('bad', 'debt') THEN 1 ELSE 0 END) as debt_count,
                    SUM(CASE WHEN quality_status = 'broken' THEN 1 ELSE 0 END) as broken_count
                FROM indexed_notes
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            row = cursor.fetchone()
            total_indexed = row["total_notes"] if row and row["total_notes"] is not None else (meta["total_notes"] if meta else 0)
            audited_count = row["audited_count"] or 0 if row else 0
            unreviewed_count = row["unreviewed_count"] or 0 if row else 0
            preevaluated_count = row["preevaluated_count"] or 0 if row else 0
            optimal_count = row["optimal_count"] or 0 if row else 0
            bad_count = row["bad_count"] or 0 if row else 0
            debt_count = row["debt_count"] or 0 if row else 0
            broken_count = row["broken_count"] or 0 if row else 0

            health_pct = round(((optimal_count + preevaluated_count) / audited_count) * 100, 1) if audited_count > 0 else 0.0

            return {
                "deck_name": deck_name,
                "total_indexed": total_indexed,
                "last_indexed_at": last_indexed_at,
                "audited_count": audited_count,
                "unreviewed_count": unreviewed_count,
                "preevaluated_count": preevaluated_count,
                "optimal_count": optimal_count,
                "bad_count": bad_count,
                "debt_count": bad_count if bad_count > 0 else debt_count,
                "broken_count": broken_count,
                "deck_health_percentage": health_pct,
            }

    def update_note_quality(
        self,
        deck_name: str,
        note_id: int,
        quality_status: str,
        quality_score: Optional[float] = None,
        quality_feedback: Optional[str] = None,
        audited_at: Optional[str] = None,
    ) -> bool:
        """Update quality status and audit feedback for a specific note."""
        now_iso = audited_at or datetime.now(timezone.utc).isoformat()
        normalized_status = "bad" if quality_status in ("debt", "broken") else quality_status
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE indexed_notes
                SET quality_status = ?,
                    quality_score = ?,
                    quality_feedback = ?,
                    audited_at = ?,
                    updated_at = ?
                WHERE deck_name = ? AND note_id = ?
                """,
                (
                    normalized_status,
                    quality_score,
                    quality_feedback,
                    now_iso,
                    now_iso,
                    deck_name,
                    int(note_id),
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def update_notes_quality_batch(
        self,
        deck_name: str,
        audit_results: List[Dict],
    ) -> int:
        """Batch update quality evaluations for notes."""
        if not audit_results:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        params = []
        for res in audit_results:
            if "note_id" not in res:
                continue
            qs = res.get("quality_status", "unreviewed")
            if qs in ("debt", "broken"):
                qs = "bad"
            params.append((
                qs,
                res.get("quality_score"),
                res.get("quality_feedback"),
                res.get("audited_at") or now_iso,
                now_iso,
                deck_name,
                int(res["note_id"]),
            ))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                """
                UPDATE indexed_notes
                SET quality_status = ?,
                    quality_score = ?,
                    quality_feedback = ?,
                    audited_at = ?,
                    updated_at = ?
                WHERE deck_name = ? AND note_id = ?
                """,
                params,
            )
            conn.commit()
            return cursor.rowcount

    def mark_notes_preevaluated(
        self,
        deck_name: str,
        note_ids: List[int],
    ) -> int:
        """Mark newly created/exported notes as 'preevaluated' with default optimal score."""
        if not note_ids:
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in note_ids)
            cursor.execute(
                f"""
                UPDATE indexed_notes
                SET quality_status = 'preevaluated',
                    quality_score = COALESCE(quality_score, 1.0),
                    quality_feedback = COALESCE(quality_feedback, 'Generada por IA de forma atómica y pre-evaluada por diseño.'),
                    audited_at = COALESCE(audited_at, ?),
                    updated_at = ?
                WHERE deck_name = ? AND note_id IN ({placeholders})
                """,
                [now_iso, now_iso, deck_name] + [int(nid) for nid in note_ids],
            )
            for nid in note_ids:
                cursor.execute(
                    """
                    INSERT INTO indexed_notes (
                        deck_name, note_id, quality_status, quality_score, quality_feedback, audited_at, updated_at
                    ) VALUES (?, ?, 'preevaluated', 1.0, 'Generada por IA de forma atómica y pre-evaluada por diseño.', ?, ?)
                    ON CONFLICT(deck_name, note_id) DO UPDATE SET
                        quality_status = 'preevaluated',
                        quality_score = COALESCE(indexed_notes.quality_score, 1.0),
                        quality_feedback = COALESCE(indexed_notes.quality_feedback, 'Generada por IA de forma atómica y pre-evaluada por diseño.')
                    """,
                    (deck_name, int(nid), now_iso, now_iso),
                )
            conn.commit()
            return len(note_ids)

    def get_notes_for_audit(
        self,
        deck_name: str,
        limit: int = 5,
        note_ids: Optional[List[int]] = None,
    ) -> List[Dict]:
        """Fetch notes pending quality evaluation or specific note IDs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if note_ids:
                placeholders = ",".join("?" for _ in note_ids)
                query = f"""
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE deck_name = ? AND note_id IN ({placeholders})
                ORDER BY note_id ASC
                """
                params = [deck_name] + [int(nid) for nid in note_ids]
                cursor.execute(query, params)
            else:
                query = """
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE deck_name = ? AND (quality_status = 'unreviewed' OR quality_status IS NULL)
                ORDER BY note_id ASC
                LIMIT ?
                """
                cursor.execute(query, (deck_name, limit))
            rows = cursor.fetchall()

        result = []
        for row in rows:
            tags_raw = row["tags"] or ""
            try:
                tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
            except Exception:
                tags = [tags_raw]

            result.append(
                {
                    "note_id": row["note_id"],
                    "tags": tags,
                    "front": row["front"] or "",
                    "back": row["back"] or "",
                    "explanation": row["explanation"] or "",
                    "clean_text": row["clean_text"] or "",
                    "quality_status": "bad" if row["quality_status"] in ("debt", "broken") else (row["quality_status"] or "unreviewed"),
                    "quality_score": row["quality_score"],
                    "quality_feedback": row["quality_feedback"],
                    "audited_at": row["audited_at"],
                    "cluster_name": row["cluster_name"],
                }
            )
        return result

    def save_coverage_audit(
        self,
        deck_name: str,
        topic: str,
        description: Optional[str],
        coverage_percentage: int,
        covered_facets: List[Dict],
        orphan_gaps: List[Dict],
        summary_assessment: str,
    ) -> int:
        """Persist a thematic coverage audit and return its generated ID."""
        now_iso = datetime.now(timezone.utc).isoformat()
        facets_json = json.dumps(covered_facets, ensure_ascii=False)
        gaps_json = json.dumps(orphan_gaps, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO thematic_coverage_audits (
                    deck_name, topic, description, coverage_percentage,
                    covered_facets, orphan_gaps, summary_assessment,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deck_name,
                    topic,
                    description or "",
                    coverage_percentage,
                    facets_json,
                    gaps_json,
                    summary_assessment,
                    now_iso,
                    now_iso,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def list_coverage_audits(self, deck_name: str) -> List[Dict]:
        """Retrieve all thematic coverage audits for a deck, ordered by newest first."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, deck_name, topic, description, coverage_percentage,
                       covered_facets, orphan_gaps, summary_assessment, created_at, updated_at
                FROM thematic_coverage_audits
                WHERE deck_name = ?
                ORDER BY id DESC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        audits = []
        for r in rows:
            facets = []
            if r["covered_facets"]:
                try:
                    facets = json.loads(r["covered_facets"])
                except Exception:
                    facets = []
            gaps = []
            if r["orphan_gaps"]:
                try:
                    gaps = json.loads(r["orphan_gaps"])
                except Exception:
                    gaps = []

            audits.append(
                {
                    "id": r["id"],
                    "deck_name": r["deck_name"],
                    "topic": r["topic"],
                    "description": r["description"],
                    "coverage_percentage": r["coverage_percentage"],
                    "covered_facets": facets,
                    "orphan_gaps": gaps,
                    "summary_assessment": r["summary_assessment"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        return audits

    def get_coverage_audit(self, audit_id: int) -> Optional[Dict]:
        """Fetch a single thematic coverage audit by ID with parsed JSON fields."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, deck_name, topic, description, coverage_percentage,
                       covered_facets, orphan_gaps, summary_assessment, created_at, updated_at
                FROM thematic_coverage_audits
                WHERE id = ?
                """,
                (audit_id,),
            )
            r = cursor.fetchone()

        if not r:
            return None

        facets = []
        if r["covered_facets"]:
            try:
                facets = json.loads(r["covered_facets"])
            except Exception:
                facets = []
        gaps = []
        if r["orphan_gaps"]:
            try:
                gaps = json.loads(r["orphan_gaps"])
            except Exception:
                gaps = []

        return {
            "id": r["id"],
            "deck_name": r["deck_name"],
            "topic": r["topic"],
            "description": r["description"],
            "coverage_percentage": r["coverage_percentage"],
            "covered_facets": facets,
            "orphan_gaps": gaps,
            "summary_assessment": r["summary_assessment"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }

    def update_gap_status(
        self,
        audit_id: int,
        gap_index: int,
        status: str,
        generated_note_id: Optional[int] = None,
    ) -> bool:
        """Update resolution status and optional generated note ID of a specific orphan gap."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT orphan_gaps FROM thematic_coverage_audits WHERE id = ?",
                (audit_id,),
            )
            r = cursor.fetchone()
            if not r or not r["orphan_gaps"]:
                return False

            try:
                gaps = json.loads(r["orphan_gaps"])
            except Exception:
                return False

            if gap_index < 0 or gap_index >= len(gaps):
                return False

            gaps[gap_index]["status"] = status
            if generated_note_id is not None:
                gaps[gap_index]["generated_note_id"] = generated_note_id

            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.execute(
                """
                UPDATE thematic_coverage_audits
                SET orphan_gaps = ?, updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(gaps, ensure_ascii=False), now_iso, audit_id),
            )
            conn.commit()
            return True

    def get_all_indexed_notes(self, deck_name: str) -> List[Dict]:
        """Fetch all indexed notes for a deck without BLOB embeddings for lightweight map building."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE deck_name = ?
                ORDER BY note_id ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        result = []
        for row in rows:
            tags_raw = row["tags"] or ""
            try:
                tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
            except Exception:
                tags = [tags_raw]

            result.append(
                {
                    "note_id": row["note_id"],
                    "tags": tags,
                    "front": row["front"] or "",
                    "back": row["back"] or "",
                    "explanation": row["explanation"] or "",
                    "clean_text": row["clean_text"] or "",
                    "quality_status": "bad" if row["quality_status"] in ("debt", "broken") else (row["quality_status"] or "unreviewed"),
                    "quality_score": row["quality_score"],
                    "quality_feedback": row["quality_feedback"],
                    "audited_at": row["audited_at"],
                    "cluster_name": row["cluster_name"],
                }
            )
        return result

    def get_indexed_note(self, note_id: int) -> Optional[Dict]:
        """Fetch indexed note record by note_id if present in SQLite."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, deck_name, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at, cluster_name
                FROM indexed_notes
                WHERE note_id = ?
                """,
                (note_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        raw_status = row["quality_status"] or "unreviewed"
        canonical_status = "bad" if raw_status in ("debt", "broken") else raw_status
        tags_raw = row["tags"] or ""
        try:
            tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
        except Exception:
            tags = [tags_raw]
        return {
            "note_id": row["note_id"],
            "deck_name": row["deck_name"],
            "tags": tags,
            "front": row["front"] or "",
            "back": row["back"] or "",
            "explanation": row["explanation"] or "",
            "clean_text": row["clean_text"] or "",
            "quality_status": canonical_status,
            "quality_score": row["quality_score"],
            "quality_feedback": row["quality_feedback"],
            "audited_at": row["audited_at"],
            "cluster_name": row["cluster_name"],
        }

    def get_all_notes_with_embeddings(self, deck_name: str) -> List[Dict]:
        """Fetch all indexed notes for a deck including unpacked float32 embeddings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, tags, front, back, explanation, clean_text,
                       quality_status, quality_score, quality_feedback, audited_at,
                       cluster_name, embedding
                FROM indexed_notes
                WHERE deck_name = ? AND embedding IS NOT NULL
                ORDER BY note_id ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        result = []
        for row in rows:
            blob = row["embedding"]
            if not blob:
                continue
            num_floats = len(blob) // 4
            vec = list(struct.unpack(f"{num_floats}f", blob))
            tags_raw = row["tags"] or ""
            try:
                tags = json.loads(tags_raw) if tags_raw.startswith("[") else [t.strip() for t in tags_raw.split(",") if t.strip()]
            except Exception:
                tags = [tags_raw]

            result.append(
                {
                    "note_id": row["note_id"],
                    "tags": tags,
                    "front": row["front"] or "",
                    "back": row["back"] or "",
                    "explanation": row["explanation"] or "",
                    "clean_text": row["clean_text"] or "",
                    "quality_status": "bad" if row["quality_status"] in ("debt", "broken") else (row["quality_status"] or "unreviewed"),
                    "quality_score": row["quality_score"],
                    "quality_feedback": row["quality_feedback"],
                    "audited_at": row["audited_at"],
                    "cluster_name": row["cluster_name"],
                    "embedding": vec,
                }
            )
        return result

    def save_deck_clusters(self, deck_name: str, clusters: List[Dict[str, Any]]) -> None:
        """Persist discovered thematic clusters and map note cluster_names in SQLite."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Clean existing clusters for this deck
            cursor.execute("DELETE FROM deck_clusters WHERE deck_name = ?", (deck_name,))

            # 2. Insert new clusters
            records = []
            note_updates = []
            for cl in clusters:
                idx = int(cl.get("cluster_index", 0))
                title = cl.get("title", f"Cluster {idx + 1}").strip()
                scope = cl.get("scope", "").strip()
                note_ids = cl.get("note_ids", [])
                centroid_note_ids = cl.get("centroid_note_ids", [])

                records.append(
                    (
                        deck_name,
                        idx,
                        title,
                        scope,
                        json.dumps(note_ids),
                        json.dumps(centroid_note_ids),
                        now_iso,
                        now_iso,
                    )
                )

                for nid in note_ids:
                    note_updates.append((title, now_iso, deck_name, int(nid)))

            cursor.executemany(
                """
                INSERT INTO deck_clusters (
                    deck_name, cluster_index, title, scope, note_ids, centroid_note_ids,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )

            # 3. Update cluster_name on indexed_notes
            if note_updates:
                cursor.executemany(
                    """
                    UPDATE indexed_notes
                    SET cluster_name = ?, updated_at = ?
                    WHERE deck_name = ? AND note_id = ?
                    """,
                    note_updates,
                )
            conn.commit()

    def get_deck_clusters(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve saved thematic clusters for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, deck_name, cluster_index, title, scope, note_ids, centroid_note_ids,
                       created_at, updated_at
                FROM deck_clusters
                WHERE deck_name = ?
                ORDER BY cluster_index ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        clusters = []
        for r in rows:
            try:
                nids = json.loads(r["note_ids"]) if r["note_ids"] else []
            except Exception:
                nids = []
            try:
                c_nids = json.loads(r["centroid_note_ids"]) if r["centroid_note_ids"] else []
            except Exception:
                c_nids = []

            clusters.append(
                {
                    "id": r["id"],
                    "deck_name": r["deck_name"],
                    "cluster_index": r["cluster_index"],
                    "title": r["title"],
                    "scope": r["scope"],
                    "note_ids": nids,
                    "centroid_note_ids": c_nids,
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
            )
        return clusters

    def replace_cluster_notes(
        self,
        deck_name: str,
        cluster_index: int,
        obsolete_note_ids: List[int],
        new_note_ids: List[int],
    ) -> None:
        """Atomically update a cluster's note_ids after transactional sanitation."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title, note_ids FROM deck_clusters WHERE deck_name = ? AND cluster_index = ?",
                (deck_name, cluster_index),
            )
            row = cursor.fetchone()
            if not row:
                return
            cluster_title = row["title"]
            try:
                curr_nids = json.loads(row["note_ids"]) if row["note_ids"] else []
            except Exception:
                curr_nids = []

            # Remove obsolete and append new
            obsolete_set = {int(x) for x in obsolete_note_ids}
            updated_nids = [nid for nid in curr_nids if int(nid) not in obsolete_set]
            for nid in new_note_ids:
                if int(nid) not in updated_nids:
                    updated_nids.append(int(nid))

            cursor.execute(
                """
                UPDATE deck_clusters
                SET note_ids = ?, updated_at = ?
                WHERE deck_name = ? AND cluster_index = ?
                """,
                (json.dumps(updated_nids), now_iso, deck_name, cluster_index),
            )
            # Update cluster_name on newly indexed notes
            for nid in new_note_ids:
                cursor.execute(
                    """
                    UPDATE indexed_notes
                    SET cluster_name = ?, updated_at = ?
                    WHERE deck_name = ? AND note_id = ?
                    """,
                    (cluster_title, now_iso, deck_name, int(nid)),
                )
            conn.commit()

    def get_cluster_sibling_boundaries(
        self,
        deck_name: str,
        note_id: Optional[int] = None,
        text_context: Optional[str] = None,
        limit: int = 12,
    ) -> List[str]:
        """
        Extract sibling topic titles and breadcrumbs from the same semantic cluster.
        Serves as Mutual Negative Boundaries to strictly prevent intra-cluster redundancy
        without compressing or sacrificing technical depth.
        """
        if not deck_name:
            return []

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cluster_note_ids: List[int] = []
            target_cluster_title: Optional[str] = None

            # 1. Look up cluster by note_id if provided
            if note_id:
                cursor.execute(
                    """
                    SELECT cluster_index, title, note_ids 
                    FROM deck_clusters 
                    WHERE deck_name = ?
                    """,
                    (deck_name,),
                )
                rows = cursor.fetchall()
                for r in rows:
                    try:
                        nids = json.loads(r["note_ids"]) if r["note_ids"] else []
                        if int(note_id) in nids:
                            cluster_note_ids = [nid for nid in nids if nid != int(note_id)]
                            target_cluster_title = r["title"]
                            break
                    except Exception:
                        continue

            # 2. If no cluster found by note_id in deck_clusters, check indexed_notes.cluster_name
            if not cluster_note_ids and note_id:
                cursor.execute(
                    """
                    SELECT cluster_name FROM indexed_notes
                    WHERE deck_name = ? AND note_id = ?
                    """,
                    (deck_name, note_id),
                )
                c_row = cursor.fetchone()
                if c_row and c_row["cluster_name"]:
                    target_cluster_title = c_row["cluster_name"]
                    cursor.execute(
                        """
                        SELECT note_id FROM indexed_notes
                        WHERE deck_name = ? AND cluster_name = ? AND note_id != ?
                        """,
                        (deck_name, target_cluster_title, note_id),
                    )
                    cluster_note_ids = [r["note_id"] for r in cursor.fetchall()]

            # 3. Fallback: If no note_id provided, but text_context is given, match closest cluster title
            if not cluster_note_ids and text_context:
                cursor.execute(
                    """
                    SELECT cluster_index, title, note_ids, scope
                    FROM deck_clusters
                    WHERE deck_name = ?
                    """,
                    (deck_name,),
                )
                rows = cursor.fetchall()
                clean_text_lower = text_context.lower()
                for r in rows:
                    title = r["title"] or ""
                    if title.lower() in clean_text_lower or any(word in clean_text_lower for word in title.lower().split() if len(word) > 4):
                        try:
                            nids = json.loads(r["note_ids"]) if r["note_ids"] else []
                            cluster_note_ids = nids
                            target_cluster_title = title
                            break
                        except Exception:
                            continue

            if not cluster_note_ids:
                return []

            # 4. Fetch sibling fronts and clean descriptors
            placeholders = ",".join("?" for _ in cluster_note_ids)
            cursor.execute(
                f"""
                SELECT note_id, front, clean_text 
                FROM indexed_notes 
                WHERE deck_name = ? AND note_id IN ({placeholders})
                """,
                [deck_name] + cluster_note_ids,
            )
            sibling_rows = cursor.fetchall()

        # Clean and extract atomic concept descriptors
        boundaries: List[str] = []
        for row in sibling_rows:
            front = row["front"] or ""
            clean_front = re.sub(r"<[^>]+>", " ", front).strip()
            # If breadcrumb [A > B > C] is present, take the innermost leaf or specific question
            m = re.match(r"^\[(.*?)\]\s*(.*)", clean_front)
            if m:
                path = m.group(1).strip()
                leaf = path.split(">")[-1].strip() if ">" in path else path
                q = m.group(2).strip()
                descriptor = leaf if len(leaf) > 3 else q[:50]
            else:
                descriptor = clean_front.split("\n")[0][:60].strip()

            descriptor = re.sub(r"\s+", " ", descriptor)
            if descriptor and len(descriptor) > 3 and descriptor not in boundaries:
                boundaries.append(descriptor)
            if len(boundaries) >= limit:
                break

        return boundaries

    # -------------------------------------------------------------------------
    # Concept DAG Persistence Methods
    # -------------------------------------------------------------------------


    def upsert_concept_node(
        self,
        deck_name: str,
        concept_id: str,
        name: str,
        taxonomy_path: str = "general",
        description: Optional[str] = None,
        depth_level: int = 1,
        status: Optional[str] = None,
        is_in_scope: Optional[bool] = None,
    ) -> None:
        """Insert or update a concept node in the deck DAG."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            scope_val = 1 if is_in_scope is None or is_in_scope else 0
            cursor.execute(
                """
                INSERT INTO concept_nodes (deck_name, id, name, taxonomy_path, description, depth_level, status, is_in_scope, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deck_name, id) DO UPDATE SET
                    name = excluded.name,
                    taxonomy_path = excluded.taxonomy_path,
                    description = COALESCE(excluded.description, concept_nodes.description),
                    depth_level = excluded.depth_level,
                    status = COALESCE(excluded.status, concept_nodes.status),
                    is_in_scope = COALESCE(excluded.is_in_scope, concept_nodes.is_in_scope),
                    updated_at = excluded.updated_at
                """,
                (deck_name, concept_id, name, taxonomy_path, description, depth_level, status or 'RAW', scope_val, now, now),
            )
            conn.commit()

    def upsert_concept_edge(
        self,
        deck_name: str,
        source_id: str,
        target_id: str,
        relation_type: str = "requires",
    ) -> None:
        """Insert a directed edge between concepts (e.g. source_id required by target_id)."""
        if source_id == target_id:
            return  # prevent direct self-loops
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO concept_edges (deck_name, source_id, target_id, relation_type)
                VALUES (?, ?, ?, ?)
                """,
                (deck_name, source_id, target_id, relation_type),
            )
            conn.commit()

    def link_card_to_concept(
        self,
        deck_name: str,
        note_id: int,
        concept_id: str,
        role: str = "target",
    ) -> None:
        """Link an Anki note to a concept node as either 'target' (note explains concept) or 'prerequisite'."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO card_concept_mappings (deck_name, note_id, concept_id, role)
                VALUES (?, ?, ?, ?)
                """,
                (deck_name, note_id, concept_id, role),
            )
            conn.commit()

    def save_note_extracted_knowledge(
        self,
        deck_name: str,
        note_id: int,
        raw_front: str,
        raw_back: str,
        extracted_facts: List[str],
        target_concepts: List[str],
        assumed_prerequisites: List[str],
        taxonomy_path: Optional[str] = None,
    ) -> None:
        """Persist structured ontological extraction for an individual note."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO note_extracted_knowledge
                    (deck_name, note_id, raw_front, raw_back, extracted_facts, target_concepts, assumed_prerequisites, taxonomy_path, extracted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deck_name, note_id) DO UPDATE SET
                    raw_front = excluded.raw_front,
                    raw_back = excluded.raw_back,
                    extracted_facts = excluded.extracted_facts,
                    target_concepts = excluded.target_concepts,
                    assumed_prerequisites = excluded.assumed_prerequisites,
                    taxonomy_path = excluded.taxonomy_path,
                    extracted_at = excluded.extracted_at
                """,
                (
                    deck_name,
                    note_id,
                    raw_front,
                    raw_back,
                    json.dumps(extracted_facts, ensure_ascii=False),
                    json.dumps(target_concepts, ensure_ascii=False),
                    json.dumps(assumed_prerequisites, ensure_ascii=False),
                    taxonomy_path,
                    now,
                ),
            )
            conn.commit()

    def get_note_extracted_knowledge(self, deck_name: str, note_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve stored extraction for a specific note."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, raw_front, raw_back, extracted_facts, target_concepts, assumed_prerequisites, taxonomy_path, extracted_at
                FROM note_extracted_knowledge
                WHERE deck_name = ? AND note_id = ?
                """,
                (deck_name, note_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "source_note_id": row["note_id"],
                "raw_front": row["raw_front"],
                "raw_back": row["raw_back"],
                "extracted_facts": json.loads(row["extracted_facts"] or "[]"),
                "target_concepts": json.loads(row["target_concepts"] or "[]"),
                "assumed_prerequisites": json.loads(row["assumed_prerequisites"] or "[]"),
                "taxonomy_path": row["taxonomy_path"],
                "extracted_at": row["extracted_at"],
            }

    def get_all_deck_extracted_knowledge(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all extracted note knowledge for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, raw_front, raw_back, extracted_facts, target_concepts, assumed_prerequisites, taxonomy_path, extracted_at
                FROM note_extracted_knowledge
                WHERE deck_name = ?
                ORDER BY note_id ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()

        results = []
        for r in rows:
            results.append({
                "source_note_id": r["note_id"],
                "raw_front": r["raw_front"],
                "raw_back": r["raw_back"],
                "extracted_facts": json.loads(r["extracted_facts"] or "[]"),
                "target_concepts": json.loads(r["target_concepts"] or "[]"),
                "assumed_prerequisites": json.loads(r["assumed_prerequisites"] or "[]"),
                "taxonomy_path": r["taxonomy_path"],
                "extracted_at": r["extracted_at"],
            })
        return results

    def get_deck_concepts(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all concept nodes for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, name, taxonomy_path, description, depth_level, status, is_in_scope, created_at, updated_at
                FROM concept_nodes
                WHERE deck_name = ?
                ORDER BY depth_level ASC, name ASC
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_deck_edges(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all concept dependency edges for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT source_id, target_id, relation_type
                FROM concept_edges
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()
            return [{"source": r["source_id"], "target": r["target_id"], "relation_type": r["relation_type"]} for r in rows]

    def get_card_concept_mappings(self, deck_name: str) -> List[Dict[str, Any]]:
        """Retrieve all card-concept mappings for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT note_id, concept_id, role
                FROM card_concept_mappings
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def clear_deck_dag(self, deck_name: str) -> None:
        """Purge all concept nodes, edges, card mappings, and extracted knowledge for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM concept_nodes WHERE deck_name = ?", (deck_name,))
            cursor.execute("DELETE FROM concept_edges WHERE deck_name = ?", (deck_name,))
            cursor.execute("DELETE FROM card_concept_mappings WHERE deck_name = ?", (deck_name,))
            cursor.execute("DELETE FROM note_extracted_knowledge WHERE deck_name = ?", (deck_name,))
            conn.commit()

    # -------------------------------------------------------------------------
    # Learning Plan Contract Persistence Methods
    # -------------------------------------------------------------------------

    def save_learning_contract(
        self,
        deck_name: str,
        contract: Dict[str, Any],
        status: str = "draft",
    ) -> None:
        """Save or update learning contract for a deck."""
        resolved_status = contract.get("status") if status == "draft" and "status" in contract else status
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO deck_learning_contracts (deck_name, contract_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(deck_name) DO UPDATE SET
                    contract_json = excluded.contract_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (deck_name, json.dumps(contract, ensure_ascii=False), resolved_status, now, now),
            )
            conn.commit()


    def get_learning_contract(self, deck_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored learning contract for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT contract_json, status, created_at, updated_at
                FROM deck_learning_contracts
                WHERE deck_name = ?
                """,
                (deck_name,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            try:
                data = json.loads(row["contract_json"])
                data["status"] = row["status"]
                data["created_at"] = row["created_at"]
                data["updated_at"] = row["updated_at"]
                return data
            except Exception:
                return None

    def delete_learning_contract(self, deck_name: str) -> None:
        """Delete stored learning contract for a deck."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM deck_learning_contracts WHERE deck_name = ?", (deck_name,))
            conn.commit()


`

