import React, { useState, useMemo } from 'react';
import {
  Clock,
  Search,
  X,
  Trash2,
  ArrowRight,
  GitFork,
  Sparkles,
  Layers,
  ChevronDown,
  ChevronUp,
  Image as ImageIcon,
  Compass,
} from 'lucide-react';
import type {
  CurationQueueItem,
  SanitationQueueResponse,
  DeckNoteRecord,
  DeckConceptDAG,
} from '../types';

interface CurationQueueBannerProps {
  queue?: CurationQueueItem[];
  sanitationQueue?: SanitationQueueResponse | null;
  dag?: DeckConceptDAG | null;
  onAnalyzeItem?: (item: CurationQueueItem) => void;
  onAnalyzeSanitationNote?: (note: DeckNoteRecord, deckName: string) => void;
  onDismissItem?: (id: string) => void;
  onClearQueue?: () => void;
  isInspecting?: boolean;
  activeNoteId?: number | null;
  mode?: 'panel' | 'banner';
  className?: string;
}

export const CurationQueueBanner: React.FC<CurationQueueBannerProps> = ({
  queue = [],
  sanitationQueue = null,
  dag = null,
  onAnalyzeItem,
  onAnalyzeSanitationNote,
  onDismissItem,
  onClearQueue,
  isInspecting = false,
  activeNoteId = null,
  mode = 'panel',
  className = '',
}) => {
  const [groupingMode, setGroupingMode] = useState<'binary' | 'generational'>('generational');
  const [openGenerations, setOpenGenerations] = useState<Record<number, boolean>>({});
  const [isLevel0Open, setIsLevel0Open] = useState<boolean>(true);
  const [isLevel1Open, setIsLevel1Open] = useState<boolean>(true);
  const [isGapsOpen, setIsGapsOpen] = useState<boolean>(true);

  const hasManualQueue = queue && queue.length > 0;
  const hasSanitationNotes = Boolean(
    sanitationQueue && sanitationQueue.notes && sanitationQueue.notes.length > 0
  );

  const deckName = sanitationQueue?.deck_name || queue[0]?.deck_name || '';
  const pendingCount = sanitationQueue?.pending_count ?? queue.length;
  const sanitizedCount = sanitationQueue?.sanitized_count ?? 0;
  const totalNotes = sanitationQueue?.total_notes ?? (pendingCount + sanitizedCount);
  const sanitationPct = totalNotes > 0 ? Math.round((sanitizedCount / totalNotes) * 100) : 0;

  const sanitationNotes = useMemo(() => sanitationQueue?.notes || [], [sanitationQueue?.notes]);

  // Map note_id to its DAG node concept and deepest depth level (G-03)
  const noteToConceptMap = useMemo(() => {
    const map = new Map<number, { name: string; depth: number }>();
    if (dag?.nodes) {
      for (const node of dag.nodes) {
        if (node.cards_mapped) {
          for (const nid of node.cards_mapped) {
            const existing = map.get(nid);
            if (!existing || node.depth_level > existing.depth) {
              map.set(nid, { name: node.name, depth: node.depth_level });
            }
          }
        }
      }
    }
    return map;
  }, [dag]);

  // Binary Partition (Legacy): Level 0 vs Level 1+
  const { level0Notes, level1PlusNotes } = useMemo(() => {
    const l0: DeckNoteRecord[] = [];
    const l1: DeckNoteRecord[] = [];

    for (const note of sanitationNotes) {
      const mapped = noteToConceptMap.get(note.note_id);
      const isBaseByTag = note.tags.some((t) =>
        ['fundamento', 'fundamentos', 'raíz', 'base'].includes(t.toLowerCase())
      );
      const depth = mapped !== undefined ? mapped.depth : isBaseByTag ? 0 : 1;

      if (depth === 0) {
        l0.push(note);
      } else {
        l1.push(note);
      }
    }

    return { level0Notes: l0, level1PlusNotes: l1 };
  }, [sanitationNotes, noteToConceptMap]);

  // Generational Stratification: Dynamic groups by exact DAG depth_level
  const generationalGroups = useMemo(() => {
    const mapByDepth = new Map<number, DeckNoteRecord[]>();

    for (const note of sanitationNotes) {
      const mapped = noteToConceptMap.get(note.note_id);
      const isBaseByTag = note.tags.some((t) =>
        ['fundamento', 'fundamentos', 'raíz', 'base'].includes(t.toLowerCase())
      );
      const depth = mapped !== undefined ? mapped.depth : isBaseByTag ? 0 : 1;

      if (!mapByDepth.has(depth)) {
        mapByDepth.set(depth, []);
      }
      mapByDepth.get(depth)!.push(note);
    }

    const sortedDepths = Array.from(mapByDepth.keys()).sort((a, b) => a - b);
    const result: Array<{
      depth: number;
      label: string;
      badgeColor: string;
      notes: DeckNoteRecord[];
      startIdx: number;
    }> = [];

    let currentOffset = 0;
    for (const d of sortedDepths) {
      let label = `Nivel ${d}: Casos Avanzados y Bordes`;
      let badgeColor = 'text-amber-300 bg-amber-950/30 border-amber-500/30';

      if (d === 0) {
        label = 'Nivel 0: Conceptos Raíz (Fundamentos)';
        badgeColor = 'text-emerald-300 bg-emerald-950/30 border-emerald-500/30';
      } else if (d === 1) {
        label = 'Nivel 1: Conceptos Intermedios';
        badgeColor = 'text-indigo-300 bg-indigo-950/30 border-indigo-500/30';
      } else if (d === 2) {
        label = 'Nivel 2: Mecanismos y Especialización';
        badgeColor = 'text-purple-300 bg-purple-950/30 border-purple-500/30';
      }

      const notes = mapByDepth.get(d) || [];
      result.push({
        depth: d,
        label,
        badgeColor,
        notes,
        startIdx: currentOffset,
      });
      currentOffset += notes.length;
    }

    return result;
  }, [sanitationNotes, noteToConceptMap]);

  const toggleGeneration = (depth: number) => {
    setOpenGenerations((prev) => ({
      ...prev,
      [depth]: !(prev[depth] ?? true),
    }));
  };

  if (!hasManualQueue && !hasSanitationNotes) {
    return (
      <div
        className={`rounded-2xl border border-slate-800 bg-slate-900/60 p-5 text-center text-xs text-slate-400 ${className}`}
      >
        <Compass className="h-6 w-6 text-slate-500 mx-auto mb-2" />
        <p className="font-semibold text-slate-300">Cola Curricular al Día</p>
        <p className="text-[11px] text-slate-500 mt-1">
          No hay notas con deuda cognitiva ni brechas pendientes en este mazo.
        </p>
      </div>
    );
  }

  const stripHtml = (html?: string | null): string => {
    if (!html) return '';
    return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  };

  const renderNoteCard = (note: DeckNoteRecord, idx: number) => {
    const isFirstInQueue = sanitationNotes[0]?.note_id === note.note_id;
    const isActive = activeNoteId === note.note_id || (activeNoteId === null && isFirstInQueue);
    const isBad = note.quality_status === 'bad';
    const cleanFront = stripHtml(note.clean_front || note.front);
    const hasImages = Boolean(note.media_files && note.media_files.length > 0);
    const mapped = noteToConceptMap.get(note.note_id);
    const conceptLabel =
      mapped?.name ||
      note.tags.find(
        (t) => !['fundamentos', 'prerrequisito', 'fundamento'].includes(t.toLowerCase())
      );

    return (
      <div
        key={note.note_id}
        className={`group flex flex-col justify-between gap-2.5 rounded-xl border p-3 transition-all ${
          isActive
            ? 'border-indigo-500/70 bg-gradient-to-r from-indigo-950/60 via-slate-900 to-slate-900 shadow-md shadow-indigo-950/40 ring-1 ring-indigo-500/40'
            : 'border-slate-800/80 bg-slate-950/50 hover:border-slate-700 hover:bg-slate-900/60'
        }`}
      >
        <div className="space-y-1.5 min-w-0">
          {/* Header Row: Badges */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${
                isActive ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-400'
              }`}
            >
              {idx + 1}
            </span>

            {isActive && (
              <span className="inline-flex items-center gap-0.5 font-mono text-[9px] font-bold text-emerald-300 bg-emerald-950/70 px-1.5 py-0.2 rounded-full border border-emerald-500/40">
                <Clock className="h-2 w-2" /> En Turno
              </span>
            )}

            <span className="font-mono text-[9px] font-bold text-slate-300 bg-slate-900 px-1.5 py-0.2 rounded border border-slate-800">
              #{note.note_id}
            </span>

            {isBad ? (
              <span className="text-[9px] font-bold text-rose-300 bg-rose-950/50 px-1.5 py-0.2 rounded border border-rose-800/60">
                🔴 bad
              </span>
            ) : (
              <span className="text-[9px] font-bold text-slate-300 bg-slate-800/60 px-1.5 py-0.2 rounded border border-slate-700">
                ⚪ unreviewed
              </span>
            )}

            {conceptLabel && (
              <span
                className="truncate max-w-[140px] text-[9px] font-semibold text-indigo-300 bg-indigo-950/70 px-1.5 py-0.2 rounded border border-indigo-800/40"
                title={`Concepto DAG: ${conceptLabel}`}
              >
                [{conceptLabel}]
              </span>
            )}

            {hasImages && (
              <span
                className="inline-flex items-center gap-0.5 text-[9px] text-cyan-300 bg-cyan-950/40 px-1 py-0.2 rounded border border-cyan-800/50"
                title={`${note.media_files?.length} diagrama(s)`}
              >
                <ImageIcon className="h-2.5 w-2.5" />
                {note.media_files?.length}
              </span>
            )}
          </div>

          {/* Front snippet */}
          <p className="text-xs text-slate-200 line-clamp-2 leading-relaxed">
            {cleanFront || '(Nota sin texto en anverso)'}
          </p>
        </div>

        {/* Action Button */}
        <div className="flex items-center justify-end pt-1 border-t border-slate-800/50">
          <button
            type="button"
            onClick={() => onAnalyzeSanitationNote?.(note, deckName)}
            disabled={isInspecting}
            className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-bold transition-all cursor-pointer disabled:opacity-50 active:scale-95 ${
              isActive
                ? 'bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 text-white shadow-sm shadow-indigo-600/30 hover:brightness-110'
                : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
            }`}
            title={`Cargar nota #${note.note_id} e iniciar saneamiento curricular`}
          >
            <Search className="h-3 w-3" />
            <span>⚡ Sanear Nota</span>
            <ArrowRight className="h-3 w-3 opacity-70" />
          </button>
        </div>
      </div>
    );
  };

  return (
    <aside
      aria-label="Cola Topológica de Saneamiento"
      className={`rounded-2xl border border-indigo-500/30 bg-gradient-to-b from-slate-900/95 via-slate-900/90 to-slate-950/95 shadow-xl flex flex-col overflow-hidden ${
        mode === 'panel' ? 'h-full max-h-[calc(100vh-140px)]' : ''
      } ${className}`}
    >
      {/* Header & Global Progress */}
      <div className="border-b border-slate-800/80 p-4 bg-slate-950/60 shrink-0 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 shrink-0">
              <GitFork className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h3 className="text-xs sm:text-sm font-bold text-white truncate flex items-center gap-1.5">
                <span>Cola Topológica</span>
                {deckName && (
                  <span className="text-indigo-300 font-semibold truncate text-[11px]">
                    ({deckName})
                  </span>
                )}
              </h3>
              <p className="text-[10px] text-slate-400 truncate">
                Precedencia DAG • Raíces primero
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300 border border-amber-500/30">
              {pendingCount}
            </span>
            <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/30">
              {sanitationPct}%
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-[10px] text-slate-400">
            <span>Progreso Curricular</span>
            <span className="font-mono text-emerald-300">
              {sanitizedCount} / {totalNotes} saneadas
            </span>
          </div>
          <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-indigo-500 via-teal-500 to-emerald-400 transition-all duration-500"
              style={{ width: `${sanitationPct}%` }}
            />
          </div>
        </div>

        {/* View Mode Toggle Switch */}
        <div className="flex items-center justify-between pt-0.5">
          <span className="text-[10px] font-medium text-slate-400">
            Vista de Cola:
          </span>
          <div className="flex items-center rounded-lg bg-slate-900 border border-slate-800 p-0.5 text-[10px]">
            <button
              type="button"
              onClick={() => setGroupingMode('binary')}
              className={`px-2 py-0.5 rounded-md font-medium transition-all cursor-pointer ${
                groupingMode === 'binary'
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Raíz / Dep.
            </button>
            <button
              type="button"
              onClick={() => setGroupingMode('generational')}
              className={`px-2 py-0.5 rounded-md font-medium transition-all cursor-pointer ${
                groupingMode === 'generational'
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Niveles DAG
            </button>
          </div>
        </div>

        {hasManualQueue && onClearQueue && (
          <div className="flex justify-end pt-1">
            <button
              type="button"
              onClick={onClearQueue}
              className="inline-flex items-center gap-1 text-[10px] text-slate-400 hover:text-rose-400 transition-colors cursor-pointer"
              title="Vaciar las brechas manuales"
            >
              <Trash2 className="h-2.5 w-2.5" />
              <span>Limpiar brechas manuales</span>
            </button>
          </div>
        )}
      </div>

      {/* Scrollable Body: Grouped Notes */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
        {/* SECTION 0: Orphan Gaps (if any) */}
        {hasManualQueue && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setIsGapsOpen((prev) => !prev)}
              className="w-full flex items-center justify-between text-[11px] font-bold text-amber-300 uppercase tracking-wider bg-amber-950/30 border border-amber-500/30 px-2.5 py-1.5 rounded-lg cursor-pointer hover:bg-amber-950/50 transition-colors"
            >
              <span className="flex items-center gap-1.5">
                <Sparkles className="h-3 w-3" />
                <span>Brechas Huérfanas ({queue.length})</span>
              </span>
              {isGapsOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>

            {isGapsOpen && (
              <div className="space-y-2 pt-1">
                {queue.map((item, idx) => (
                  <div
                    key={item.id}
                    className="flex flex-col gap-2 rounded-xl border border-amber-500/30 bg-amber-950/20 p-2.5 hover:border-amber-500/50 transition-all"
                  >
                    <div className="flex items-start gap-2 min-w-0">
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-amber-900/60 text-[9px] font-bold text-amber-200 border border-amber-700 mt-0.5">
                        {idx + 1}
                      </span>
                      <div className="min-w-0 space-y-0.5">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className="font-mono text-[9px] font-bold text-rose-300 bg-rose-950/60 px-1.5 py-0.2 rounded border border-rose-900/50">
                            {item.note_id > 0 ? `#${item.note_id}` : '🔴 Brecha'}
                          </span>
                          <span className="text-[9px] text-amber-300/90 bg-amber-950/40 px-1.5 py-0.2 rounded border border-amber-900/40">
                            {item.matched_concept}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-200 font-medium line-clamp-2 italic">
                          "{item.front}"
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center justify-end gap-1.5 pt-1 border-t border-amber-900/30">
                      <button
                        type="button"
                        onClick={() => onAnalyzeItem?.(item)}
                        disabled={isInspecting}
                        className="inline-flex items-center gap-1 rounded-lg bg-gradient-to-r from-amber-600 to-orange-600 px-2 py-1 text-[10px] font-semibold text-white shadow-xs hover:brightness-110 active:scale-95 transition-all disabled:opacity-50 cursor-pointer"
                      >
                        <Search className="h-2.5 w-2.5" />
                        <span>Analizar</span>
                      </button>
                      {onDismissItem && (
                        <button
                          type="button"
                          onClick={() => onDismissItem(item.id)}
                          aria-label="Descartar de la cola"
                          className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors cursor-pointer"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {groupingMode === 'generational' ? (
          generationalGroups.map((group) => {
            const isOpen = openGenerations[group.depth] ?? true;
            return (
              <div key={group.depth} className="space-y-2">
                <button
                  type="button"
                  onClick={() => toggleGeneration(group.depth)}
                  className={`w-full flex items-center justify-between text-[11px] font-bold uppercase tracking-wider border px-2.5 py-1.5 rounded-lg cursor-pointer hover:brightness-125 transition-colors ${group.badgeColor}`}
                >
                  <span className="flex items-center gap-1.5">
                    <Layers className="h-3 w-3" />
                    <span>
                      {group.label} ({group.notes.length})
                    </span>
                  </span>
                  {isOpen ? (
                    <ChevronUp className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronDown className="h-3.5 w-3.5" />
                  )}
                </button>

                {isOpen && (
                  <div className="space-y-2 pt-0.5">
                    {group.notes.length === 0 ? (
                      <p className="text-[11px] text-slate-500 italic px-2">
                        No hay notas pendientes en este nivel.
                      </p>
                    ) : (
                      group.notes.map((note, idx) =>
                        renderNoteCard(note, group.startIdx + idx)
                      )
                    )}
                  </div>
                )}
              </div>
            );
          })
        ) : (
          <>
            {/* SECTION 1: Nivel 0: Conceptos Raíz (Fundamentos) */}
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setIsLevel0Open((prev) => !prev)}
                className="w-full flex items-center justify-between text-[11px] font-bold text-emerald-300 uppercase tracking-wider bg-emerald-950/30 border border-emerald-500/30 px-2.5 py-1.5 rounded-lg cursor-pointer hover:bg-emerald-950/50 transition-colors"
              >
                <span className="flex items-center gap-1.5">
                  <Compass className="h-3 w-3 text-emerald-400" />
                  <span>Nivel 0: Conceptos Raíz ({level0Notes.length})</span>
                </span>
                {isLevel0Open ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
              </button>

              {isLevel0Open && (
                <div className="space-y-2 pt-0.5">
                  {level0Notes.length === 0 ? (
                    <p className="text-[11px] text-slate-500 italic px-2">
                      No hay notas pendientes en nivel raíz.
                    </p>
                  ) : (
                    level0Notes.map((note, idx) => renderNoteCard(note, idx))
                  )}
                </div>
              )}
            </div>

            {/* SECTION 2: Nivel 1+: Conceptos Intermedios y Especialización */}
            <div className="space-y-2">
              <button
                type="button"
                onClick={() => setIsLevel1Open((prev) => !prev)}
                className="w-full flex items-center justify-between text-[11px] font-bold text-indigo-300 uppercase tracking-wider bg-indigo-950/30 border border-indigo-500/30 px-2.5 py-1.5 rounded-lg cursor-pointer hover:bg-indigo-950/50 transition-colors"
              >
                <span className="flex items-center gap-1.5">
                  <Layers className="h-3 w-3 text-indigo-400" />
                  <span>Nivel 1+: Conceptos Dependientes ({level1PlusNotes.length})</span>
                </span>
                {isLevel1Open ? (
                  <ChevronUp className="h-3.5 w-3.5" />
                ) : (
                  <ChevronDown className="h-3.5 w-3.5" />
                )}
              </button>

              {isLevel1Open && (
                <div className="space-y-2 pt-0.5">
                  {level1PlusNotes.length === 0 ? (
                    <p className="text-[11px] text-slate-500 italic px-2">
                      No hay notas pendientes en niveles intermedios.
                    </p>
                  ) : (
                    level1PlusNotes.map((note, idx) =>
                      renderNoteCard(note, level0Notes.length + idx)
                    )
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  );
};
