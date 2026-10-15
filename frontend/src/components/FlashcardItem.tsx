import React, { useState } from 'react';
import { RotateCw, Edit3, Trash2, Check, X, Tag, Lightbulb, Compass, Maximize2, Image as ImageIcon } from 'lucide-react';
import type { Flashcard } from '../types';
import { CardContentRenderer } from './CardContentRenderer';

interface FlashcardItemProps {
  card: Flashcard;
  index: number;
  onUpdate: (updatedCard: Flashcard) => void;
  onDelete: (id: string) => void;
  onOpenFullscreen?: () => void;
}

export const FlashcardItem: React.FC<FlashcardItemProps> = React.memo(({
  card,
  index,
  onUpdate,
  onDelete,
  onOpenFullscreen,
}) => {
  const [isFlipped, setIsFlipped] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // Edit draft states
  const [draftFront, setDraftFront] = useState(card.front);
  const [draftBack, setDraftBack] = useState(card.back);
  const [draftTags, setDraftTags] = useState(card.tags.join(', '));
  const [draftExplanation, setDraftExplanation] = useState(card.explanation || '');

  const handleSaveEdit = () => {
    onUpdate({
      ...card,
      front: draftFront.trim(),
      back: draftBack.trim(),
      tags: draftTags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
      explanation: draftExplanation.trim() || undefined,
    });
    setIsEditing(false);
  };

  const handleCancelEdit = () => {
    setDraftFront(card.front);
    setDraftBack(card.back);
    setDraftTags(card.tags.join(', '));
    setDraftExplanation(card.explanation || '');
    setIsEditing(false);
  };

  // Helper to extract breadcrumb if formatted like [Macro > Sub] Question
  const breadcrumbMatch = card.front.match(/^\[(.*?)\]\s*(.*)$/s);
  const breadcrumb = breadcrumbMatch ? breadcrumbMatch[1] : null;
  const mainFrontText = breadcrumbMatch ? breadcrumbMatch[2] : card.front;

  const isPrerequisiteCard =
    card.tags.some((t) => t.toLowerCase() === 'prerrequisito' || t.toLowerCase() === 'fundamentos') ||
    (breadcrumb ? breadcrumb.toLowerCase().includes('fundamento') : false);

  const sourceImages = card.source_images && card.source_images.length > 0
    ? card.source_images
    : card.source_image ? [card.source_image] : [];

  if (isEditing) {
    return (
      <div className="rounded-2xl border border-indigo-500/50 bg-slate-900/90 p-5 shadow-xl shadow-indigo-950/40 space-y-4 animate-fade-in">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <span className="text-xs font-semibold text-indigo-400">Editando Tarjeta #{index + 1}</span>
          <div className="flex items-center gap-1">
            <button
              onClick={handleSaveEdit}
              className="inline-flex items-center gap-1 rounded-lg bg-emerald-600/20 text-emerald-300 border border-emerald-500/30 px-2.5 py-1 text-xs font-semibold hover:bg-emerald-600/30 transition-colors"
            >
              <Check className="h-3.5 w-3.5" /> Guardar
            </button>
            <button
              onClick={handleCancelEdit}
              className="inline-flex items-center gap-1 rounded-lg bg-slate-800 text-slate-300 px-2.5 py-1 text-xs hover:bg-slate-700 transition-colors"
            >
              <X className="h-3.5 w-3.5" /> Cancelar
            </button>
          </div>
        </div>

        <div className="space-y-3 text-xs">
          <div>
            <label htmlFor={`front-${card.id}`} className="font-medium text-slate-300 block mb-1">Anverso (con [Ruta Jerárquica])</label>
            <textarea
              id={`front-${card.id}`}
              rows={3}
              value={draftFront}
              onChange={(e) => setDraftFront(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 p-2.5 text-slate-100 focus:border-indigo-500 focus:outline-none font-mono text-xs"
            />
          </div>

          <div>
            <label htmlFor={`back-${card.id}`} className="font-medium text-slate-300 block mb-1">Reverso / Respuesta Atómica (&lt; 15 palabras)</label>
            <textarea
              id={`back-${card.id}`}
              rows={2}
              value={draftBack}
              onChange={(e) => setDraftBack(e.target.value)}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 p-2.5 text-slate-100 focus:border-indigo-500 focus:outline-none"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label htmlFor={`tags-${card.id}`} className="font-medium text-slate-300 block mb-1">Etiquetas (separadas por coma)</label>
              <input
                id={`tags-${card.id}`}
                type="text"
                value={draftTags}
                onChange={(e) => setDraftTags(e.target.value)}
                placeholder="redes, hardware"
                className="w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-slate-100 focus:border-indigo-500 focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor={`extra-${card.id}`} className="font-medium text-slate-300 block mb-1">Campo Extra (Diagrama ASCII / Tabla / Mnemotecnia)</label>
              <textarea
                id={`extra-${card.id}`}
                rows={2}
                value={draftExplanation}
                onChange={(e) => setDraftExplanation(e.target.value)}
                placeholder="Tabla resumen o diagrama ASCII..."
                className="w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-slate-100 focus:border-indigo-500 focus:outline-none font-mono text-[11px]"
              />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div id={`card-${card.id}`} className="perspective-1000 min-h-[300px] w-full">
      <div
        className={`relative h-full w-full min-h-[300px] rounded-2xl transition-transform duration-500 transform-style-3d shadow-xl shadow-black/40 ${
          isFlipped ? 'rotate-y-180' : ''
        }`}
      >
        {/* FRONT SIDE */}
        <div
          className={`absolute inset-0 backface-hidden flex flex-col justify-between rounded-2xl border p-5 backdrop-blur-xl transition-all overflow-hidden ${
            isPrerequisiteCard
              ? 'border-emerald-500/40 bg-gradient-to-b from-emerald-950/20 via-slate-900/90 to-slate-950/90 hover:border-emerald-500/60 shadow-lg shadow-emerald-950/30'
              : 'border-slate-800 bg-slate-900/80 hover:border-slate-700/80'
          }`}
        >
          <div>
            {/* Header badges & actions */}
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2 mb-2.5">
              <div className="flex items-center gap-2 overflow-hidden max-w-[75%]">
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold border ${
                    isPrerequisiteCard
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30'
                  }`}
                >
                  {index + 1}
                </span>

                {isPrerequisiteCard && (
                  <span className="truncate rounded-md bg-emerald-950/80 border border-emerald-500/40 px-2 py-0.5 text-[9px] font-bold text-emerald-300 uppercase tracking-wider flex items-center gap-1 shadow-sm">
                    <Compass className="h-2.5 w-2.5" /> Fundamento Base
                  </span>
                )}

                {card.archetype && (
                  <span className="truncate rounded-md bg-indigo-950/70 border border-indigo-700/40 px-2 py-0.5 text-[9px] font-medium text-indigo-300 uppercase tracking-wider">
                    {card.archetype.replace('Arquetipo ', '')}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1 shrink-0">
                {onOpenFullscreen && (
                  <button
                    type="button"
                    onClick={onOpenFullscreen}
                    aria-label="Ver tarjeta en pantalla completa"
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-indigo-300 transition-colors"
                    title="Ver en pantalla completa"
                  >
                    <Maximize2 className="h-3.5 w-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => {
                    setDraftFront(card.front);
                    setDraftBack(card.back);
                    setDraftTags(card.tags.join(', '));
                    setDraftExplanation(card.explanation || '');
                    setIsEditing(true);
                  }}
                  aria-label="Editar tarjeta"
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
                  title="Editar tarjeta"
                >
                  <Edit3 className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(card.id)}
                  aria-label="Eliminar tarjeta"
                  className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-rose-400 transition-colors"
                  title="Eliminar tarjeta"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Hierarchical Breadcrumbs */}
            {breadcrumb && (
              <div
                className={`mb-2.5 inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-mono ${
                  isPrerequisiteCard
                    ? 'bg-emerald-950/60 border-emerald-500/30 text-emerald-300'
                    : 'bg-slate-950/90 border-slate-800 text-indigo-300'
                }`}
              >
                <Compass className={`h-3 w-3 shrink-0 ${isPrerequisiteCard ? 'text-emerald-400' : 'text-indigo-400'}`} />
                <span className="truncate">{breadcrumb}</span>
              </div>
            )}

            {/* Front text / Question with rich markdown, tables, and clozes */}
            <div className="overflow-y-auto max-h-[145px] pr-1 space-y-2">
              <CardContentRenderer
                content={mainFrontText}
                mode="front"
                className="text-sm font-medium text-white"
              />

              {/* Source Images chips if present */}
              {sourceImages.length > 0 && (
                <div className="pt-1 flex flex-wrap gap-1">
                  {sourceImages.map((img, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 rounded bg-slate-950 border border-cyan-800/50 px-1.5 py-0.5 text-[10px] text-cyan-300 font-mono shadow-xs"
                      title={img}
                    >
                      <ImageIcon className="h-2.5 w-2.5 shrink-0" />
                      <span className="truncate max-w-[130px]">{img}</span>
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Footer & Flip Trigger */}
          <div className="border-t border-slate-800/80 pt-2.5 flex items-center justify-between mt-2">
            <div className="flex flex-wrap gap-1 max-w-[65%] overflow-hidden">
              {card.tags.slice(0, 2).map((tag, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-0.5 rounded-md bg-slate-950 border border-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400"
                >
                  <Tag className="h-2.5 w-2.5" />
                  {tag}
                </span>
              ))}
            </div>

            <button
              type="button"
              onClick={() => setIsFlipped(true)}
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-semibold transition-all shadow-sm active:scale-95 ${
                isPrerequisiteCard
                  ? 'bg-emerald-600/20 border-emerald-500/30 text-emerald-300 hover:bg-emerald-600/30 hover:text-white'
                  : 'bg-indigo-600/20 border-indigo-500/30 text-indigo-300 hover:bg-indigo-600/30 hover:text-white'
              }`}
            >
              <span>Ver Respuesta</span>
              <RotateCw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* BACK SIDE */}
        <div
          className={`absolute inset-0 backface-hidden rotate-y-180 flex flex-col justify-between rounded-2xl border p-5 backdrop-blur-xl overflow-hidden ${
            isPrerequisiteCard
              ? 'border-emerald-500/50 bg-gradient-to-b from-emerald-950/30 via-slate-900/95 to-slate-950/95 shadow-2xl shadow-emerald-950/50'
              : 'border-indigo-500/40 bg-slate-900/95 shadow-2xl shadow-indigo-950/50'
          }`}
        >
          <div className="overflow-y-auto max-h-[220px] pr-1">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-2 mb-2.5">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 flex items-center gap-1">
                  <Check className="h-3.5 w-3.5" /> Recuperación Activa
                </span>
                {isPrerequisiteCard && (
                  <span className="rounded-md bg-emerald-950/80 border border-emerald-500/40 px-1.5 py-0.5 text-[9px] font-bold text-emerald-300 uppercase tracking-wider">
                    Fundamento Base
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-slate-400">Tarjeta #{index + 1}</span>
                {onOpenFullscreen && (
                  <button
                    type="button"
                    onClick={onOpenFullscreen}
                    aria-label="Ver tarjeta en pantalla completa"
                    className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-indigo-300 transition-colors"
                    title="Ver en pantalla completa"
                  >
                    <Maximize2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>

            {/* Back Answer with rich rendering */}
            {card.back && (
              <div className="mb-3">
                <CardContentRenderer
                  content={card.back}
                  mode="back"
                  className="text-sm font-semibold text-white"
                />
              </div>
            )}

            {/* Campo Extra (Validación Pasiva) */}
            {card.explanation && (
              <div className="rounded-xl border border-indigo-500/20 bg-indigo-950/30 p-2.5 space-y-1 text-xs text-indigo-200">
                <div className="flex items-center gap-1 text-[10px] font-bold text-amber-400 uppercase tracking-wider">
                  <Lightbulb className="h-3 w-3" /> Campo Extra (Refresco Visual Pasivo)
                </div>
                <div className="bg-slate-950/60 p-2.5 rounded-lg border border-indigo-900/40 text-slate-200 text-xs max-w-[65ch]">
                  <CardContentRenderer content={card.explanation} mode="extra" />
                </div>
              </div>
            )}

            {/* Source Images chips if present */}
            {sourceImages.length > 0 && (
              <div className="mt-2.5 flex flex-wrap gap-1">
                {sourceImages.map((img, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center gap-1 rounded bg-slate-950 border border-cyan-800/50 px-1.5 py-0.5 text-[10px] text-cyan-300 font-mono shadow-xs"
                    title={img}
                  >
                    <ImageIcon className="h-2.5 w-2.5 shrink-0 text-cyan-400" />
                    <span className="truncate max-w-[130px]">{img}</span>
                  </span>
                ))}
              </div>
            )}

            {/* Pedagogical Justification */}
            {card.justification && (
              <div className="mt-2.5 rounded-xl border border-amber-500/25 bg-amber-950/30 p-2.5 text-xs text-amber-200 space-y-1 shadow-xs">
                <span className="font-bold flex items-center gap-1 text-[10px] uppercase text-amber-400 tracking-wider">
                  <Lightbulb className="h-3 w-3 shrink-0" /> Justificación Pedagógica
                </span>
                <p className="text-[11px] text-slate-300 italic leading-relaxed">{card.justification}</p>
              </div>
            )}
          </div>

          <div className="border-t border-slate-800/80 pt-2.5 flex justify-end mt-2">
            <button
              type="button"
              onClick={() => setIsFlipped(false)}
              className="inline-flex items-center gap-1.5 rounded-xl bg-slate-800 border border-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white transition-all active:scale-95"
            >
              <span>Voltear al Frente</span>
              <RotateCw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});
