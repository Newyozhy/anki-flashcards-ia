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
import { DeckPickerModal } from './DeckPickerModal';
import { DeckInterviewModal } from './DeckInterviewModal';
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
  onSanitizeConceptInQueue?: (conceptTitle: string) => void;
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
  onSanitizeConceptInQueue,
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

  useModalEscape(
    isOpen,
    onClose,
    isDeckPickerModalOpen || isInterviewModalOpen
  );

  if (!isOpen) return null;

  // Compute KPI metrics for canonical 3 states: optimal, bad, unreviewed
  const noteNodes = (coverageMap?.nodes || []).filter((n: DeckCoverageMapNode) => n.type === 'note');
  const unreviewedCount = coverageMap?.unreviewed_count ?? 0;
  const badCount = (coverageMap?.bad_count ?? 0) + (coverageMap?.debt_count ?? 0) + (coverageMap?.broken_count ?? 0);
  const optimalCount = coverageMap?.optimal_count ?? 0;

  const totalNotes =
    noteNodes.length ||
    (coverageMap
      ? optimalCount + badCount + unreviewedCount
      : 0);

  const auditedCount =
    coverageMap?.audited_count ?? (optimalCount + badCount);

  const hasAudited = auditedCount > 0;
  const totalQualityCards = optimalCount;
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
                                onClick={() => {
                                  onClose();
                                  onSanitizeConceptInQueue?.(cluster.title);
                                }}
                                className="inline-flex items-center gap-1 rounded-lg bg-teal-600/80 hover:bg-teal-500 px-2 py-1 text-[10px] font-bold text-white transition-all active:scale-95 cursor-pointer shadow-xs"
                                title="Sanear este eje temático en la cola principal topológica"
                              >
                                <Sparkles className="h-3 w-3 text-teal-200" />
                                <span>Sanear este Eje en Cola Principal</span>
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
                                  : 'bg-rose-900/50 text-rose-300'
                              }`}
                            >
                              {item.quality_status === 'optimal' ? '🟢 Óptima' : '🔴 Mala'}
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
    </div>
  );
};
