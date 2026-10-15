import React, { useState, useMemo, useEffect, useRef, useCallback } from 'react';
import { Search, FolderPlus, Check, X, Folder, Layers, Pin } from 'lucide-react';
import { useModalEscape } from '../utils/useModalEscape';

interface DeckPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  availableDecks: string[];
  selectedDeck: string;
  onSelectDeck: (deckName: string) => void;
}

export const DeckPickerModal: React.FC<DeckPickerModalProps> = ({
  isOpen,
  onClose,
  availableDecks,
  selectedDeck,
  onSelectDeck,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [newDeckInput, setNewDeckInput] = useState('');
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const [pinnedDecks, setPinnedDecks] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('ankicraft_pinned_decks');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const togglePin = (deckName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPinnedDecks((prev) => {
      const next = prev.includes(deckName)
        ? prev.filter((d) => d !== deckName)
        : [deckName, ...prev];
      try {
        localStorage.setItem('ankicraft_pinned_decks', JSON.stringify(next));
      } catch (err) {
        console.error('Failed to save pinned decks to localStorage:', err);
      }
      return next;
    });
  };

  const handleClose = useCallback(() => {
    setSearchQuery('');
    setNewDeckInput('');
    setIsCreatingNew(false);
    onClose();
  }, [onClose]);

  useModalEscape(isOpen, handleClose);

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => searchInputRef.current?.focus(), 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Filter and sort decks: pinned decks first, then alphabetically / search matches
  const filteredDecks = useMemo(() => {
    const base = !searchQuery.trim()
      ? availableDecks
      : availableDecks.filter((deck) => deck.toLowerCase().includes(searchQuery.toLowerCase()));

    return [...base].sort((a, b) => {
      const aPinned = pinnedDecks.includes(a);
      const bPinned = pinnedDecks.includes(b);
      if (aPinned && !bPinned) return -1;
      if (!aPinned && bPinned) return 1;
      return a.localeCompare(b);
    });
  }, [availableDecks, searchQuery, pinnedDecks]);

  if (!isOpen) return null;

  const handleSelect = (deck: string) => {
    onSelectDeck(deck);
    handleClose();
  };

  const handleCreateNew = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = newDeckInput.trim();
    if (clean) {
      onSelectDeck(clean);
      handleClose();
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="deck-picker-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-4 animate-fade-in"
    >
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700/70 bg-slate-900/95 shadow-2xl shadow-indigo-950/50 flex flex-col max-h-[85vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 p-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <Folder className="h-4 w-4" />
            </div>
            <div>
              <h3 id="deck-picker-modal-title" className="text-sm font-semibold text-white">Seleccionar Mazo de Anki</h3>
              <p className="text-[11px] text-slate-400">
                {availableDecks.length} mazos detectados en tu Anki Desktop
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={handleClose}
            aria-label="Cerrar selector de mazo"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Search Bar */}
        <div className="p-4 border-b border-slate-800/80 bg-slate-950/40 space-y-3">
          <div className="relative flex items-center">
            <Search className="absolute left-3.5 h-4 w-4 text-slate-400 pointer-events-none" />
            <input
              ref={searchInputRef}
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Buscar mazo de Anki"
              placeholder="Buscar mazo (ej. Inglés, Cálculo, Medicina)..."
              className="w-full rounded-xl border border-slate-700/80 bg-slate-900/90 pl-10 pr-4 py-2.5 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all font-medium"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-3 text-slate-400 hover:text-slate-200 text-xs"
              >
                Limpiar
              </button>
            )}
          </div>

          {/* Toggle Create New Deck inline */}
          {!isCreatingNew ? (
            <button
              type="button"
              onClick={() => setIsCreatingNew(true)}
              className="w-full text-left inline-flex items-center gap-2 rounded-xl border border-dashed border-indigo-500/30 bg-indigo-500/5 px-3 py-2 text-xs font-medium text-indigo-300 hover:bg-indigo-500/10 transition-colors"
            >
              <FolderPlus className="h-4 w-4" />
              <span>+ Crear un nuevo mazo personalizado...</span>
            </button>
          ) : (
            <form onSubmit={handleCreateNew} className="flex gap-2 animate-fade-in">
              <input
                type="text"
                value={newDeckInput}
                onChange={(e) => setNewDeckInput(e.target.value)}
                aria-label="Nombre del nuevo mazo"
                placeholder="Nombre del mazo (soporta submazos con ::)"
                autoFocus
                className="flex-1 rounded-xl border border-indigo-500 bg-slate-950 px-3 py-2 text-xs text-white focus:outline-none"
              />
              <button
                type="submit"
                className="rounded-xl bg-indigo-600 px-3 py-2 text-xs font-semibold text-white hover:bg-indigo-500"
              >
                Crear
              </button>
              <button
                type="button"
                onClick={() => setIsCreatingNew(false)}
                className="rounded-xl bg-slate-800 px-2.5 py-2 text-xs text-slate-400 hover:text-white"
              >
                Cancelar
              </button>
            </form>
          )}
        </div>

        {/* Deck List */}
        <div className="flex-1 overflow-y-auto p-3 space-y-1 divide-y divide-slate-800/40">
          {filteredDecks.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-400">
              No se encontraron mazos que coincidan con &quot;{searchQuery}&quot;
            </div>
          ) : (
            filteredDecks.map((deck) => {
              const isSelected = selectedDeck === deck;
              const isPinned = pinnedDecks.includes(deck);
              // Parse hierarchical parts with ::
              const parts = deck.split('::');

              return (
                <div
                  key={deck}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleSelect(deck)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleSelect(deck);
                    }
                  }}
                  className={`w-full flex items-center justify-between rounded-xl px-3.5 py-2.5 text-left text-xs sm:text-sm transition-all group cursor-pointer ${
                    isSelected
                      ? 'bg-indigo-600/20 text-indigo-200 border border-indigo-500/40 font-semibold'
                      : isPinned
                      ? 'bg-slate-800/40 text-slate-200 hover:bg-slate-800/70 border border-amber-500/20'
                      : 'text-slate-300 hover:bg-slate-800/70 hover:text-white border border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2.5 overflow-hidden">
                    <button
                      type="button"
                      onClick={(e) => togglePin(deck, e)}
                      aria-pressed={isPinned}
                      aria-label={isPinned ? `Desfijar mazo ${deck}` : `Fijar mazo ${deck}`}
                      className={`p-1 rounded-lg transition-all ${
                        isPinned
                          ? 'text-amber-400 hover:text-amber-300 hover:bg-amber-400/20'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 opacity-40 group-hover:opacity-100'
                      }`}
                      title={isPinned ? 'Desfijar mazo' : 'Fijar mazo al inicio'}
                    >
                      <Pin className={`h-3.5 w-3.5 ${isPinned ? 'fill-amber-400 rotate-45' : ''}`} />
                    </button>

                    <Layers
                      className={`h-4 w-4 shrink-0 ${
                        isSelected
                          ? 'text-indigo-400'
                          : isPinned
                          ? 'text-amber-400/80'
                          : 'text-slate-400 group-hover:text-indigo-400'
                      }`}
                    />
                    <div className="truncate flex items-center gap-1.5">
                      {parts.length > 1 ? (
                        <>
                          <span className="text-slate-400 text-xs">
                            {parts.slice(0, -1).join(' / ')} /
                          </span>
                          <span className="font-semibold text-white truncate">
                            {parts[parts.length - 1]}
                          </span>
                        </>
                      ) : (
                        <span className="font-medium text-white">{deck}</span>
                      )}
                      {isPinned && (
                        <span className="ml-1.5 rounded-full bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.2 text-[9px] font-bold text-amber-300">
                          Fijado
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {isSelected && (
                      <div className="flex h-5 w-5 items-center justify-center rounded-full bg-indigo-500 text-white shadow-sm">
                        <Check className="h-3 w-3" />
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 p-3 bg-slate-950/60 flex items-center justify-between text-[11px] text-slate-400">
          <span>Hacé clic en cualquier mazo para seleccionarlo</span>
          <button
            type="button"
            onClick={handleClose}
            className="text-slate-300 hover:text-white font-medium"
          >
            Cerrar
          </button>
        </div>
      </div>
    </div>
  );
};
