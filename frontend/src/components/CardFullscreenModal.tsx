import React, { useEffect, useState } from 'react';
import { X, ChevronLeft, ChevronRight, RotateCw, Compass, Lightbulb, Tag, Check } from 'lucide-react';
import type { Flashcard } from '../types';
import { CardContentRenderer } from './CardContentRenderer';

interface CardFullscreenModalProps {
  card: Flashcard | null;
  index: number;
  totalCards: number;
  isOpen: boolean;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}

export const CardFullscreenModal: React.FC<CardFullscreenModalProps> = ({
  card,
  index,
  totalCards,
  isOpen,
  onClose,
  onPrev,
  onNext,
}) => {
  const [flippedCardId, setFlippedCardId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'flip' | 'split'>('flip');
  const isFlipped = Boolean(card && flippedCardId === card.id);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowLeft') onPrev();
      if (e.key === 'ArrowRight') onNext();
      if (e.key === ' ' && viewMode === 'flip') {
        e.preventDefault();
        setFlippedCardId((prev) => (card && prev !== card.id ? card.id : null));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose, onPrev, onNext, viewMode, card]);

  if (!isOpen || !card) return null;

  const breadcrumbMatch = card.front.match(/^\[(.*?)\]\s*(.*)$/s);
  const breadcrumb = breadcrumbMatch ? breadcrumbMatch[1] : null;
  const mainFrontText = breadcrumbMatch ? breadcrumbMatch[2] : card.front;

  const isPrerequisiteCard =
    card.tags.some((t) => t.toLowerCase() === 'prerrequisito' || t.toLowerCase() === 'fundamentos') ||
    (breadcrumb ? breadcrumb.toLowerCase().includes('fundamento') : false);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Vista completa de tarjeta"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/85 backdrop-blur-md animate-fade-in"
    >
      {/* Modal Container */}
      <div className="relative w-full max-w-3xl flex flex-col max-h-[90vh] rounded-2xl border border-slate-700 bg-slate-900/95 shadow-2xl shadow-indigo-950/60 overflow-hidden">
        {/* Top Header Bar */}
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3.5 bg-slate-900/90">
          <div className="flex items-center gap-3">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold border ${
                isPrerequisiteCard
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                  : 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30'
              }`}
            >
              {index + 1}
            </span>
            <span className="text-xs font-medium text-slate-400">
              Tarjeta {index + 1} de {totalCards}
            </span>
            {isPrerequisiteCard ? (
              <span className="hidden sm:inline-flex items-center gap-1 rounded-md bg-emerald-950/80 border border-emerald-500/40 px-2 py-0.5 text-[10px] font-bold text-emerald-300 uppercase tracking-wider">
                <Compass className="h-3 w-3" /> Fundamento Base
              </span>
            ) : card.archetype ? (
              <span className="hidden sm:inline-block rounded-md bg-indigo-950/80 border border-indigo-700/40 px-2 py-0.5 text-[10px] font-semibold text-indigo-300 uppercase tracking-wider">
                {card.archetype.replace('Arquetipo ', '')}
              </span>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            {/* View Mode Switcher */}
            <div className="hidden sm:flex items-center rounded-lg bg-slate-950/60 p-0.5 border border-slate-800 text-[11px]">
              <button
                type="button"
                onClick={() => setViewMode('flip')}
                className={`px-2.5 py-1 rounded-md font-medium transition-all ${
                  viewMode === 'flip'
                    ? 'bg-indigo-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Modo Flip
              </button>
              <button
                type="button"
                onClick={() => setViewMode('split')}
                className={`px-2.5 py-1 rounded-md font-medium transition-all ${
                  viewMode === 'split'
                    ? 'bg-indigo-600 text-white shadow'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Frente + Reverso
              </button>
            </div>

            {/* Close Button */}
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar vista completa"
              className="rounded-xl p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
              title="Cerrar (Esc)"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Breadcrumbs Header */}
          {breadcrumb && (
            <div className="inline-flex items-center gap-1.5 rounded-lg bg-slate-950 border border-slate-800 px-3 py-1.5 text-xs font-mono text-indigo-300 shadow-sm">
              <Compass className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
              <span className="font-semibold tracking-wide">{breadcrumb}</span>
            </div>
          )}

          {/* VIEW MODE: SPLIT (Side-by-side or stacked front and back) */}
          {viewMode === 'split' ? (
            <div className="space-y-6">
              {/* Front Side */}
              <div className="rounded-2xl border border-slate-800 bg-slate-950/50 p-5 space-y-2">
                <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400 border-b border-slate-800 pb-1.5">
                  Anverso (Pregunta / Cloze)
                </div>
                <div className="text-base text-slate-100 max-w-[65ch]">
                  <CardContentRenderer content={mainFrontText} mode="front" />
                </div>
              </div>

              {/* Back Side */}
              {card.back && (
                <div className="rounded-2xl border border-emerald-900/30 bg-emerald-950/10 p-5 space-y-2">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-emerald-400 border-b border-emerald-900/30 pb-1.5 flex items-center gap-1">
                    <Check className="h-3.5 w-3.5" /> Respuesta Atómica
                  </div>
                  <div className="text-base text-slate-100 max-w-[65ch]">
                    <CardContentRenderer content={card.back} mode="back" />
                  </div>
                </div>
              )}

              {/* Campo Extra */}
              {card.explanation && (
                <div className="rounded-2xl border border-amber-900/30 bg-amber-950/10 p-5 space-y-2">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5 border-b border-amber-900/30 pb-1.5">
                    <Lightbulb className="h-4 w-4" /> Campo Extra (Síntesis Visual Pasiva)
                  </div>
                  <div className="text-sm text-slate-200 max-w-[65ch]">
                    <CardContentRenderer content={card.explanation} mode="extra" />
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* VIEW MODE: FLIP (Interactive Anki simulator) */
            <div className="flex flex-col items-center justify-center min-h-[320px]">
              <div className="w-full rounded-2xl border border-slate-700 bg-slate-950/70 p-6 shadow-xl space-y-5">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-indigo-400">
                    {isFlipped ? 'Reverso (Respuesta)' : 'Anverso (Estudio Activo)'}
                  </span>
                  <span className="text-[11px] text-slate-400 italic">
                    Presioná Barra Espaciadora o el botón para voltear
                  </span>
                </div>

                {!isFlipped ? (
                  <div className="text-base text-slate-100 min-h-[120px] max-w-[65ch] mx-auto">
                    <CardContentRenderer content={mainFrontText} mode="front" />
                  </div>
                ) : (
                  <div className="space-y-5 animate-fade-in">
                    {/* Front dimmed reminder */}
                    <div className="text-sm text-slate-400 border-l-2 border-slate-700 pl-3 py-1 opacity-75 max-w-[65ch] mx-auto">
                      <CardContentRenderer content={mainFrontText} mode="back" />
                    </div>

                    {/* Back answer */}
                    {card.back && (
                      <div className="text-base font-medium text-emerald-300 max-w-[65ch] mx-auto">
                        <CardContentRenderer content={card.back} mode="back" />
                      </div>
                    )}

                    {/* Campo Extra */}
                    {card.explanation && (
                      <div className="rounded-xl border border-amber-500/20 bg-amber-950/20 p-4 space-y-2 max-w-[65ch] mx-auto">
                        <div className="flex items-center gap-1.5 text-xs font-bold text-amber-400 uppercase tracking-wider">
                          <Lightbulb className="h-3.5 w-3.5" /> Campo Extra
                        </div>
                        <div className="text-sm text-slate-200 max-w-[65ch]">
                          <CardContentRenderer content={card.explanation} mode="extra" />
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <div className="pt-3 border-t border-slate-800/80 flex justify-center">
                  <button
                    type="button"
                    onClick={() =>
                      setFlippedCardId((prev) => (card && prev !== card.id ? card.id : null))
                    }
                    className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2 text-xs font-semibold shadow-lg shadow-indigo-950/50 transition-all active:scale-95"
                  >
                    <RotateCw className="h-4 w-4" />
                    <span>{isFlipped ? 'Voltear al Frente' : 'Ver Respuesta'}</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Tags Footer */}
          {card.tags && card.tags.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-slate-800">
              <span className="text-[11px] text-slate-400 font-medium mr-1">Etiquetas:</span>
              {card.tags.map((tag, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 rounded-md bg-slate-950 border border-slate-800 px-2 py-0.5 text-xs text-slate-300"
                >
                  <Tag className="h-2.5 w-2.5 text-slate-400" />
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Bottom Navigation Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 px-5 py-3 bg-slate-900/90">
          <button
            type="button"
            onClick={onPrev}
            disabled={index === 0}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <ChevronLeft className="h-4 w-4" />
            <span>Anterior</span>
          </button>

          <span className="text-xs text-slate-400">
            Navegá con las flechas ← y →
          </span>

          <button
            type="button"
            onClick={onNext}
            disabled={index === totalCards - 1}
            className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <span>Siguiente</span>
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};