import React, { useState } from 'react';
import {
  Layers,
  Plus,
  Trash2,
  Send,
  Download,
  Brain,
  Sparkles,
  CheckCircle2,
  Loader2,
} from 'lucide-react';
import type { Flashcard } from '../types';
import { FlashcardItem } from './FlashcardItem';
import { CardFullscreenModal } from './CardFullscreenModal';

interface FlashcardGridProps {
  cards: Flashcard[];
  deckName: string;
  sourceNoteId?: number | null;
  onUpdateCard: (card: Flashcard) => void;
  onDeleteCard: (id: string) => void;
  onAddManualCard: () => void;
  onClearCards: () => void;
  onExportToAnki: () => void;
  onExportToApkg: () => void;
  onPreserveOptimal?: () => void;
  isExportingAnki: boolean;
  isExportingApkg: boolean;
  isAnkiConnected: boolean;
  onOpenAuditModal?: () => void;
  auditScore?: number | null;
}

export const FlashcardGrid: React.FC<FlashcardGridProps> = ({
  cards,
  deckName,
  sourceNoteId,
  onUpdateCard,
  onDeleteCard,
  onAddManualCard,
  onClearCards,
  onExportToAnki,
  onExportToApkg,
  onPreserveOptimal,
  isExportingAnki,
  isExportingApkg,
  isAnkiConnected,
  onOpenAuditModal,
  auditScore,
}) => {
  const [fullscreenIndex, setFullscreenIndex] = useState<number | null>(null);

  if (cards.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-12 text-center backdrop-blur-sm">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600/10 border border-indigo-500/20 text-indigo-400 mb-4">
          <Layers className="h-7 w-7" />
        </div>
        <h3 className="text-base font-semibold text-white">Todavía no hay flashcards generadas</h3>
        <p className="mt-1 text-xs text-slate-400 max-w-sm leading-relaxed">
          {sourceNoteId
            ? `Seleccioná la nota #${sourceNoteId} y ejecutá la inspección o generación para obtener tarjetas atómicas.`
            : 'Pegá texto educativo o subí una imagen/PDF arriba y presioná Generar Flashcards para ver la magia de Gemini en acción.'}
        </p>
      </div>
    );
  }

  const isSanitationMode = sourceNoteId !== undefined && sourceNoteId !== null;

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Grid Top Toolbar */}
      <div
        className={`flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 rounded-2xl border p-4 backdrop-blur-xl ${
          isSanitationMode
            ? 'border-teal-500/40 bg-gradient-to-r from-slate-900 via-teal-950/20 to-slate-900 shadow-xl shadow-teal-950/20'
            : 'border-slate-800 bg-slate-900/70'
        }`}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`flex h-7 w-7 items-center justify-center rounded-lg text-xs font-bold text-white shadow-md ${
                isSanitationMode ? 'bg-teal-600' : 'bg-indigo-600'
              }`}
            >
              {cards.length}
            </span>
            <div>
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <span>{isSanitationMode ? 'Tarjetas Atómicas Propuestas' : 'Tarjetas Generadas'}</span>
                {isSanitationMode && (
                  <span className="font-mono text-[10px] font-bold text-teal-300 bg-teal-950/60 px-2 py-0.5 rounded-full border border-teal-500/30">
                    Sustitución Nota #{sourceNoteId}
                  </span>
                )}
              </h3>
              <p className="text-[11px] text-slate-400">
                Destino: <span className={`${isSanitationMode ? 'text-teal-300' : 'text-indigo-300'} font-medium`}>{deckName}</span>
              </p>
            </div>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          {isSanitationMode ? (
            /* Contextual Action Bar for Sanitation Mode */
            <>
              {onOpenAuditModal && auditScore !== undefined && auditScore !== null && (
                <button
                  type="button"
                  onClick={onOpenAuditModal}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/40 bg-indigo-950/60 hover:bg-indigo-900/60 px-3 py-1.5 text-xs font-semibold text-indigo-200 hover:text-white transition-all shadow-sm active:scale-95 cursor-pointer"
                  title="Abrir Auditor Neurocognitivo y Linter de Calidad"
                >
                  <Brain className="h-3.5 w-3.5 text-indigo-400" />
                  <span>🧠 Calidad: {auditScore}/100</span>
                </button>
              )}

              <button
                type="button"
                onClick={onAddManualCard}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 px-2.5 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white transition-all cursor-pointer"
                title="Agregar tarjeta manual"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Agregar</span>
              </button>

              <button
                type="button"
                onClick={onClearCards}
                className="inline-flex items-center gap-1.5 rounded-xl border border-rose-900/40 bg-rose-950/20 px-2.5 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-900/30 transition-all cursor-pointer"
                title="Descartar tarjetas generadas"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>Limpiar</span>
              </button>

              {onPreserveOptimal && (
                <button
                  type="button"
                  onClick={onPreserveOptimal}
                  disabled={isExportingAnki}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-all active:scale-95 disabled:opacity-50 cursor-pointer"
                  title="Conservar la nota original como óptima en el índice sin sustitución"
                >
                  <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                  <span>Conservar como Óptima</span>
                </button>
              )}

              <button
                type="button"
                onClick={onExportToAnki}
                disabled={isExportingAnki || !isAnkiConnected}
                className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-bold text-white transition-all shadow-md active:scale-95 cursor-pointer ${
                  isAnkiConnected
                    ? 'bg-gradient-to-r from-emerald-600 via-teal-600 to-cyan-600 hover:from-emerald-500 hover:to-cyan-500 shadow-teal-600/30'
                    : 'bg-slate-800 text-slate-400 border border-slate-700 opacity-60'
                }`}
                title={
                  isAnkiConnected
                    ? `Aprobar tarjetas, sustituir nota #${sourceNoteId} en Anki y avanzar`
                    : 'Anki Desconectado'
                }
              >
                {isExportingAnki ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Sustituyendo en Anki...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    <span>Aprobar, Sustituir Nota #{sourceNoteId} y Siguiente ▶</span>
                  </>
                )}
              </button>
            </>
          ) : (
            /* Standard Action Bar for Ingest Mode */
            <>
              {onOpenAuditModal && (
                <button
                  type="button"
                  onClick={onOpenAuditModal}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/40 bg-gradient-to-r from-indigo-950/70 to-purple-950/70 hover:from-indigo-600/30 hover:to-purple-600/30 px-3.5 py-1.5 text-xs font-semibold text-indigo-200 hover:text-white transition-all shadow-sm active:scale-95 cursor-pointer"
                  title="Abrir Auditor Neurocognitivo y Linter de Calidad"
                >
                  <Brain className="h-3.5 w-3.5 text-indigo-400" />
                  <span>Auditor Neurocognitivo</span>
                  {auditScore !== undefined && auditScore !== null && (
                    <span className="rounded-md bg-emerald-500/20 px-1.5 py-0.2 text-[10px] font-bold text-emerald-300 border border-emerald-500/30">
                      {auditScore}/100
                    </span>
                  )}
                </button>
              )}

              <button
                type="button"
                onClick={onAddManualCard}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white transition-all cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Agregar Manual</span>
              </button>

              <button
                type="button"
                onClick={onClearCards}
                className="inline-flex items-center gap-1.5 rounded-xl border border-rose-900/40 bg-rose-950/20 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-900/30 transition-all cursor-pointer"
              >
                <Trash2 className="h-3.5 w-3.5" />
                <span>Limpiar</span>
              </button>

              <button
                type="button"
                onClick={onExportToAnki}
                disabled={isExportingAnki}
                className={`inline-flex items-center gap-1.5 rounded-xl px-4 py-1.5 text-xs font-semibold text-white transition-all shadow-md cursor-pointer ${
                  isAnkiConnected
                    ? 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-emerald-950/40 active:scale-95'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                }`}
                title={
                  isAnkiConnected
                    ? 'Inyectar cartas automáticamente en Anki Desktop abierto'
                    : 'Anki Desktop no detectado en localhost:8765'
                }
              >
                <Send className={`h-3.5 w-3.5 ${isExportingAnki ? 'animate-spin' : ''}`} />
                <span>
                  {isExportingAnki
                    ? 'Enviando a Anki...'
                    : isAnkiConnected
                    ? 'Sincronizar a Anki Desktop'
                    : 'Anki Desconectado'}
                </span>
              </button>

              <button
                type="button"
                onClick={onExportToApkg}
                disabled={isExportingApkg}
                className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/40 bg-indigo-600/20 px-3.5 py-1.5 text-xs font-semibold text-indigo-300 hover:bg-indigo-600/30 hover:text-white transition-all shadow-sm active:scale-95 cursor-pointer"
                title="Descargar archivo empaquetado para importar con doble clic"
              >
                <Download className={`h-3.5 w-3.5 ${isExportingApkg ? 'animate-spin' : ''}`} />
                <span>{isExportingApkg ? 'Generando .apkg...' : 'Descargar .apkg'}</span>
              </button>
            </>
          )}
        </div>
      </div>

      {/* Cards 3D Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {cards.map((card, index) => (
          <FlashcardItem
            key={card.id}
            card={card}
            index={index}
            onUpdate={onUpdateCard}
            onDelete={onDeleteCard}
            onOpenFullscreen={() => setFullscreenIndex(index)}
          />
        ))}
      </div>

      {/* Fullscreen Card Modal */}
      <CardFullscreenModal
        isOpen={fullscreenIndex !== null}
        card={fullscreenIndex !== null ? cards[fullscreenIndex] : null}
        index={fullscreenIndex ?? 0}
        totalCards={cards.length}
        onClose={() => setFullscreenIndex(null)}
        onPrev={() => setFullscreenIndex((prev) => (prev !== null && prev > 0 ? prev - 1 : prev))}
        onNext={() =>
          setFullscreenIndex((prev) =>
            prev !== null && prev < cards.length - 1 ? prev + 1 : prev
          )
        }
      />
    </div>
  );
};
