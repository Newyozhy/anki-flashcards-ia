import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  Search,
  Folder,
  Layers,
  Check,
  X,
  ArrowLeft,
  Tag,
  AlertCircle,
  Loader2,
  Sparkles,
  FileQuestion,
  Eye,
  RefreshCw,
} from 'lucide-react';
import type { DeckNoteRecord } from '../types';
import { api, rewriteMediaUrlsForWeb } from '../services/api';
import { stripHtmlAndDecode } from '../utils/clozeParser';

interface AnkiCardPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  availableDecks: string[];
  initialDeck?: string;
  onSelectCard: (card: DeckNoteRecord) => void;
  selectedCardId?: number | null;
}

export const AnkiCardPickerModal: React.FC<AnkiCardPickerModalProps> = ({
  isOpen,
  onClose,
  availableDecks,
  initialDeck,
  onSelectCard,
  selectedCardId,
}) => {
  const [currentDeck, setCurrentDeck] = useState<string>(() => {
    if (initialDeck && availableDecks.includes(initialDeck)) {
      return initialDeck;
    }
    return availableDecks[0] || initialDeck || 'General';
  });
  const [isPickingDeck, setIsPickingDeck] = useState<boolean>(false);
  const [deckSearchQuery, setDeckSearchQuery] = useState<string>('');
  const [cardSearchQuery, setCardSearchQuery] = useState<string>('');
  const [qualityFilter, setQualityFilter] = useState<'all' | 'unreviewed' | 'bad' | 'preevaluated' | 'optimal'>('all');

  const [cards, setCards] = useState<DeckNoteRecord[]>([]);
  const [isLoadingCards, setIsLoadingCards] = useState<boolean>(false);
  const [cardsError, setCardsError] = useState<string | null>(null);
  const [activeCard, setActiveCard] = useState<DeckNoteRecord | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);

  const cardSearchRef = useRef<HTMLInputElement>(null);
  const deckSearchRef = useRef<HTMLInputElement>(null);

  // Load cards whenever currentDeck changes and modal is open
  useEffect(() => {
    if (!isOpen || !currentDeck || isPickingDeck) return;

    let isMounted = true;
    const loadCards = async () => {
      setIsLoadingCards(true);
      setCardsError(null);
      try {
        const data = await api.getDeckNotes(currentDeck);
        if (!isMounted) return;
        setCards(data);
        if (data.length > 0) {
          // If a card was already selected in this deck, keep it active; otherwise select the first card
          const existing = selectedCardId ? data.find((c) => c.note_id === selectedCardId) : null;
          setActiveCard(existing || data[0]);
        } else {
          setActiveCard(null);
        }
      } catch (err: any) {
        if (!isMounted) return;
        setCardsError(err.message || 'No se pudieron cargar las tarjetas del mazo.');
        setCards([]);
        setActiveCard(null);
      } finally {
        if (isMounted) setIsLoadingCards(false);
      }
    };

    void loadCards();

    return () => {
      isMounted = false;
    };
  }, [isOpen, currentDeck, isPickingDeck, reloadKey, selectedCardId]);

  // Focus search inputs appropriately
  useEffect(() => {
    if (isOpen) {
      if (isPickingDeck) {
        setTimeout(() => deckSearchRef.current?.focus(), 60);
      } else {
        setTimeout(() => cardSearchRef.current?.focus(), 60);
      }
    }
  }, [isOpen, isPickingDeck]);

  // Keyboard navigation: Escape closes modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;
      if (e.key === 'Escape') {
        if (isPickingDeck) {
          setIsPickingDeck(false);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isPickingDeck, onClose]);

  // Filter decks
  const filteredDecks = useMemo(() => {
    if (!deckSearchQuery.trim()) return availableDecks;
    const q = deckSearchQuery.toLowerCase();
    return availableDecks.filter((d) => d.toLowerCase().includes(q));
  }, [availableDecks, deckSearchQuery]);

  // Priority order for sorting: bad (0), unreviewed (1), preevaluated (2), optimal (3)
  const getQualityPriority = (status?: string): number => {
    const s = status || 'unreviewed';
    if (s === 'bad' || s === 'debt' || s === 'broken') return 0;
    if (s === 'unreviewed') return 1;
    if (s === 'preevaluated') return 2;
    if (s === 'optimal') return 3;
    return 1;
  };

  // Filter cards in the selected deck by search query and canonical quality filter
  const filteredCards = useMemo(() => {
    let result = cards;
    if (qualityFilter !== 'all') {
      result = result.filter((c) => {
        const s = c.quality_status || 'unreviewed';
        if (qualityFilter === 'bad') return s === 'bad' || (s as string) === 'debt' || (s as string) === 'broken';
        return s === qualityFilter;
      });
    }
    if (cardSearchQuery.trim()) {
      const q = cardSearchQuery.toLowerCase();
      result = result.filter((c) => {
        if (c.note_id.toString().includes(q)) return true;
        if (c.model_name.toLowerCase().includes(q)) return true;
        if (c.tags.some((t) => t.toLowerCase().includes(q))) return true;
        if (c.front.toLowerCase().includes(q)) return true;
        if (c.back.toLowerCase().includes(q)) return true;
        return Object.values(c.raw_fields).some((val) => val.toLowerCase().includes(q));
      });
    }
    // Sort: bad and unreviewed first, preevaluated and optimal last
    return [...result].sort((a, b) => {
      const pA = getQualityPriority(a.quality_status);
      const pB = getQualityPriority(b.quality_status);
      if (pA !== pB) return pA - pB;
      return b.note_id - a.note_id;
    });
  }, [cards, qualityFilter, cardSearchQuery]);

  if (!isOpen) return null;

  const handleSelectDeck = (deck: string) => {
    setCurrentDeck(deck);
    setIsPickingDeck(false);
    setCardSearchQuery('');
  };

  const handleConfirmSelection = (card: DeckNoteRecord) => {
    onSelectCard(card);
    onClose();
  };

  // Helper to extract a display title from card fields
  const getCardDisplayTitle = (card: DeckNoteRecord): string => {
    if (card.front && card.front.trim()) {
      const cleaned = stripHtmlAndDecode(card.front);
      if (cleaned) return cleaned;
    }
    const entries = Object.entries(card.raw_fields);
    if (entries.length > 0) {
      const firstNonEmpty = entries.find(([, val]) => stripHtmlAndDecode(val).length > 0);
      if (firstNonEmpty) {
        return stripHtmlAndDecode(firstNonEmpty[1]);
      }
    }
    return `Tarjeta #${card.note_id}`;
  };

  // Helper to render canonical quality badge
  const renderQualityBadge = (status?: string, score?: number) => {
    const s = status || 'unreviewed';
    if (s === 'optimal') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-emerald-950/80 border border-emerald-600/40 px-1.5 py-0.5 text-[9px] font-bold text-emerald-300 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Óptima {score !== undefined && score !== null ? `(${Math.round(score * 100)}%)` : ''}
        </span>
      );
    }
    if (s === 'preevaluated') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-cyan-950/80 border border-cyan-600/40 px-1.5 py-0.5 text-[9px] font-bold text-cyan-300 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
          Pre-evaluada
        </span>
      );
    }
    if (s === 'bad' || s === 'debt' || s === 'broken') {
      return (
        <span className="inline-flex items-center gap-1 rounded bg-rose-950/80 border border-rose-600/40 px-1.5 py-0.5 text-[9px] font-bold text-rose-300 shrink-0">
          <span className="h-1.5 w-1.5 rounded-full bg-rose-400" />
          Mala {score !== undefined && score !== null ? `(${Math.round(score * 100)}%)` : ''}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded bg-slate-800/90 border border-slate-700 px-1.5 py-0.5 text-[9px] font-medium text-slate-400 shrink-0">
        <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
        Sin evaluar
      </span>
    );
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="anki-card-picker-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md p-3 sm:p-5 animate-fade-in"
    >
      <div className="relative w-full max-w-5xl rounded-2xl border border-slate-700/80 bg-slate-900/95 shadow-2xl shadow-indigo-950/60 flex flex-col h-[90vh] max-h-[850px] overflow-hidden">
        
        {/* Top Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3.5 bg-slate-950/60 shrink-0">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <Sparkles className="h-4 w-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 id="anki-card-picker-modal-title" className="text-sm font-semibold text-white">Explorador de Tarjetas de Anki</h3>
                <span className="rounded-md bg-indigo-600/20 border border-indigo-500/30 px-2 py-0.5 text-[10px] font-bold text-indigo-300">
                  Material Educativo
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Seleccioná una tarjeta de tu colección para diagnosticar, auditar o planificar flashcards
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar explorador de tarjetas"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
            title="Cerrar modal (Esc)"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* VIEW 1: Pick Deck View */}
        {isPickingDeck ? (
          <div className="flex-1 flex flex-col overflow-hidden p-4 sm:p-6 space-y-4">
            <div className="flex items-center justify-between">
              <button
                type="button"
                onClick={() => setIsPickingDeck(false)}
                className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 transition-colors font-medium"
              >
                <ArrowLeft className="h-4 w-4" />
                <span>Volver al explorador de tarjetas</span>
              </button>
              <span className="text-xs text-slate-400">{availableDecks.length} mazos en tu Anki</span>
            </div>

            {/* Deck Search Bar */}
            <div className="relative">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
              <input
                ref={deckSearchRef}
                type="text"
                value={deckSearchQuery}
                onChange={(e) => setDeckSearchQuery(e.target.value)}
                aria-label="Buscar mazo de Anki"
                placeholder="Buscar mazo de Anki..."
                className="w-full rounded-xl border border-slate-700/80 bg-slate-950/70 pl-10 pr-4 py-2.5 text-xs sm:text-sm text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all font-medium"
              />
            </div>

            {/* Decks List */}
            <div className="flex-1 overflow-y-auto space-y-1.5 pr-1">
              {filteredDecks.length === 0 ? (
                <div className="py-12 text-center text-xs text-slate-400">
                  No se encontraron mazos que coincidan con &quot;{deckSearchQuery}&quot;
                </div>
              ) : (
                filteredDecks.map((deck) => {
                  const isSelected = currentDeck === deck;
                  const parts = deck.split('::');

                  return (
                    <button
                      key={deck}
                      type="button"
                      onClick={() => handleSelectDeck(deck)}
                      className={`w-full flex items-center justify-between rounded-xl px-4 py-3 text-left text-xs sm:text-sm transition-all group ${
                        isSelected
                          ? 'bg-indigo-600/20 text-indigo-200 border border-indigo-500/40 font-semibold'
                          : 'text-slate-300 hover:bg-slate-800/70 hover:text-white border border-transparent'
                      }`}
                    >
                      <div className="flex items-center gap-3 overflow-hidden">
                        <Layers
                          className={`h-4 w-4 shrink-0 ${
                            isSelected ? 'text-indigo-400' : 'text-slate-400 group-hover:text-indigo-400'
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
                        </div>
                      </div>

                      {isSelected && (
                        <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-indigo-500 text-white shadow-sm">
                          <Check className="h-3 w-3" />
                        </div>
                      )}
                    </button>
                  );
                })
              )}
            </div>
          </div>
        ) : (
          /* VIEW 2: Cards Explorer & Dynamic Fields Inspector */
          <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
            {/* Left Column: Deck Info & Cards List */}
            <div className="w-full md:w-5/12 border-b md:border-b-0 md:border-r border-slate-800 flex flex-col shrink-0 bg-slate-950/30">
              
              {/* Deck Info Bar & Switcher */}
              <div className="p-3 border-b border-slate-800/80 bg-slate-950/50 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 overflow-hidden">
                  <Folder className="h-4 w-4 text-indigo-400 shrink-0" />
                  <div className="truncate">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block">Mazo Activo</span>
                    <span className="text-xs font-semibold text-white truncate block" title={currentDeck}>
                      {currentDeck}
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setIsPickingDeck(true)}
                  className="rounded-lg bg-slate-800 hover:bg-slate-700/80 border border-slate-700 px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:text-white transition-all shrink-0"
                >
                  Cambiar Mazo
                </button>
              </div>

              {/* Cards Search Input */}
              <div className="p-3 border-b border-slate-800/60">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
                  <input
                    ref={cardSearchRef}
                    type="text"
                    value={cardSearchQuery}
                    onChange={(e) => setCardSearchQuery(e.target.value)}
                    aria-label="Filtrar tarjetas en este mazo"
                    placeholder="Filtrar tarjetas en este mazo..."
                    className="w-full rounded-xl border border-slate-700/80 bg-slate-900/90 pl-9 pr-3 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
                  />
                  {cardSearchQuery && (
                    <button
                      type="button"
                      onClick={() => setCardSearchQuery('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 text-[10px]"
                    >
                      Limpiar
                    </button>
                  )}
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-400 mt-1.5 px-0.5">
                  <span>{filteredCards.length} de {cards.length} tarjetas</span>
                  {isLoadingCards && (
                    <span className="inline-flex items-center gap-1 text-indigo-400">
                      <Loader2 className="h-3 w-3 animate-spin" /> Cargando...
                    </span>
                  )}
                </div>
              </div>

              {/* Quality Filter Tabs */}
              <div className="flex items-center gap-1 px-3 py-1.5 border-b border-slate-800/60 overflow-x-auto text-[11px] font-medium bg-slate-950/40 shrink-0">
                {[
                  { id: 'all', label: 'Todas' },
                  { id: 'unreviewed', label: 'Sin evaluar' },
                  { id: 'bad', label: 'Mala' },
                  { id: 'preevaluated', label: 'Pre-evaluadas' },
                  { id: 'optimal', label: 'Óptimas' },
                ].map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setQualityFilter(f.id as any)}
                    className={`px-2 py-0.5 rounded-md transition-colors cursor-pointer shrink-0 ${
                      qualityFilter === f.id
                        ? 'bg-indigo-600 text-white font-semibold'
                        : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              {/* Cards List */}
              <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {isLoadingCards ? (
                  <div className="py-16 text-center text-xs text-slate-400 space-y-2">
                    <Loader2 className="h-6 w-6 text-indigo-400 animate-spin mx-auto" />
                    <p>Cargando tarjetas desde Anki Desktop...</p>
                  </div>
                ) : cardsError ? (
                  <div className="p-5 text-center text-xs space-y-3 rounded-2xl border border-rose-500/30 bg-rose-950/20 m-2">
                    <AlertCircle className="h-6 w-6 text-rose-400 mx-auto" />
                    <p className="text-rose-200 font-bold">Error al comunicar con Anki Desktop</p>
                    <p className="text-slate-300 text-[11px] leading-relaxed max-w-xs mx-auto">
                      {cardsError.includes('AnkiConnect') || cardsError.includes('fetch') || cardsError.includes('tiempo')
                        ? 'Verificá que Anki Desktop esté abierto y que el complemento AnkiConnect esté activo en el puerto 8765.'
                        : cardsError}
                    </p>
                    <div className="pt-1 flex items-center justify-center">
                      <button
                        type="button"
                        onClick={() => setReloadKey((k) => k + 1)}
                        className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 px-3.5 py-1.5 text-xs font-semibold text-white cursor-pointer shadow-md shadow-indigo-600/20 active:scale-95 transition-all"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        <span>Reintentar Conexión</span>
                      </button>
                    </div>
                  </div>
                ) : filteredCards.length === 0 ? (
                  <div className="py-16 text-center text-xs text-slate-400 space-y-1 px-4">
                    <FileQuestion className="h-6 w-6 text-slate-400 mx-auto mb-2" />
                    <p className="font-medium text-slate-300">
                      {cards.length === 0
                        ? 'Este mazo no tiene tarjetas registradas.'
                        : 'Ninguna tarjeta coincide con tu búsqueda.'}
                    </p>
                    <p className="text-[11px] text-slate-400">
                      {cards.length === 0 ? 'Probá cambiando de mazo arriba.' : 'Probá con otra palabra clave.'}
                    </p>
                  </div>
                ) : (
                  filteredCards.map((card) => {
                    const isActive = activeCard?.note_id === card.note_id;
                    const title = getCardDisplayTitle(card);

                    return (
                      <button
                        key={card.note_id}
                        type="button"
                        onClick={() => setActiveCard(card)}
                        className={`w-full flex flex-col items-start rounded-xl p-2.5 text-left transition-all ${
                          isActive
                            ? 'bg-indigo-600/25 border border-indigo-500/50 shadow-md shadow-indigo-950/30'
                            : 'hover:bg-slate-800/60 border border-transparent text-slate-300'
                        }`}
                      >
                        <div className="w-full flex items-center justify-between gap-1.5 mb-1">
                          <div className="flex items-center gap-1.5 overflow-hidden">
                            <span className="text-[10px] font-mono text-slate-400 shrink-0">
                              #{card.note_id}
                            </span>
                            {renderQualityBadge(card.quality_status, card.quality_score)}
                          </div>
                          <span className="rounded bg-slate-800 border border-slate-700/80 px-1.5 py-0.5 text-[9px] font-medium text-slate-300 truncate max-w-[100px] shrink-0">
                            {card.model_name}
                          </span>
                        </div>

                        <p className="text-xs font-medium text-slate-100 line-clamp-2 leading-snug w-full">
                          {title}
                        </p>

                        {card.tags.length > 0 && (
                          <div className="mt-1.5 flex items-center gap-1 flex-wrap overflow-hidden max-h-5">
                            {card.tags.slice(0, 3).map((tag) => (
                              <span
                                key={tag}
                                className="inline-flex items-center gap-0.5 rounded px-1.5 py-0.2 text-[9px] font-medium bg-slate-900 border border-slate-700/60 text-slate-400"
                              >
                                <Tag className="h-2 w-2" />
                                {tag}
                              </span>
                            ))}
                            {card.tags.length > 3 && (
                              <span className="text-[9px] text-slate-400">
                                +{card.tags.length - 3}
                              </span>
                            )}
                          </div>
                        )}
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            {/* Right Column: Dynamic Fields Inspector & Preview */}
            <div className="flex-1 flex flex-col overflow-hidden bg-slate-900/50">
              {activeCard ? (
                <>
                  {/* Card Inspector Header */}
                  <div className="p-4 border-b border-slate-800 bg-slate-950/40 flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2.5 overflow-hidden">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 shrink-0">
                        <Eye className="h-4 w-4" />
                      </div>
                      <div className="truncate">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs font-bold text-white">Nota #{activeCard.note_id}</span>
                          <span className="rounded bg-indigo-950/80 border border-indigo-700/50 px-2 py-0.2 text-[10px] font-semibold text-indigo-300">
                            {activeCard.model_name}
                          </span>
                          {renderQualityBadge(activeCard.quality_status, activeCard.quality_score)}
                        </div>
                        <span className="text-[11px] text-slate-400 truncate block">
                          Mazo: {activeCard.deck_name}
                        </span>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleConfirmSelection(activeCard)}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2 text-xs shadow-lg shadow-indigo-600/30 transition-all active:scale-95 shrink-0"
                    >
                      <Check className="h-4 w-4" />
                      <span>Seleccionar Tarjeta</span>
                    </button>
                  </div>

                  {/* Quality Feedback Callout if audited */}
                  {activeCard.quality_feedback && (
                    <div className="px-5 py-2.5 bg-slate-950/40 border-b border-slate-800/80 text-xs">
                      <div className="flex items-center gap-1.5 font-semibold text-slate-300 mb-0.5">
                        <Sparkles className="h-3.5 w-3.5 text-indigo-400" />
                        <span>Diagnóstico de Calidad Cognitiva</span>
                      </div>
                      <p className="text-[11px] text-slate-400 italic">
                        {activeCard.quality_feedback}
                      </p>
                    </div>
                  )}

                  {/* Tags list */}
                  {activeCard.tags.length > 0 && (
                    <div className="px-5 py-2 border-b border-slate-800/60 bg-slate-950/20 flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mr-1">
                        Etiquetas:
                      </span>
                      {activeCard.tags.map((tag) => (
                        <span
                          key={tag}
                          className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] bg-slate-800/80 border border-slate-700 text-slate-300"
                        >
                          <Tag className="h-2.5 w-2.5 text-indigo-400" />
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Dynamic Fields Inspector */}
                  <div className="flex-1 overflow-y-auto p-5 space-y-4">
                    <div className="flex items-center justify-between pb-1 border-b border-slate-800/60">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Campos del Modelo ({Object.keys(activeCard.raw_fields).length})
                      </span>
                      <span className="text-[10px] text-slate-400">
                        Visualización completa de la tarjeta
                      </span>
                    </div>

                    <div className="space-y-3">
                      {Object.entries(activeCard.raw_fields).map(([fieldName, fieldValue]) => {
                        const hasContent = Boolean(fieldValue && fieldValue.trim().length > 0);
                        const processedHtml = rewriteMediaUrlsForWeb(fieldValue);

                        return (
                          <div
                            key={fieldName}
                            className="rounded-xl border border-slate-800/90 bg-slate-950/60 p-3.5 space-y-2 hover:border-slate-700/80 transition-colors"
                          >
                            <div className="flex items-center justify-between">
                              <span className="rounded-md bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 text-[11px] font-semibold text-indigo-300">
                                {fieldName}
                              </span>
                              {!hasContent && (
                                <span className="text-[10px] italic text-slate-400">(campo vacío)</span>
                              )}
                            </div>

                            {hasContent ? (
                              <div
                                className="text-xs sm:text-sm text-slate-200 leading-relaxed overflow-x-auto break-words [&_img]:max-h-64 [&_img]:rounded-lg [&_img]:my-2 [&_b]:text-white [&_b]:font-bold [&_table]:border-collapse [&_th]:border [&_th]:border-slate-700 [&_th]:p-1.5 [&_td]:border [&_td]:border-slate-800 [&_td]:p-1.5"
                                dangerouslySetInnerHTML={{ __html: processedHtml }}
                              />
                            ) : (
                              <p className="text-xs text-slate-400 italic">—</p>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>

                  {/* Bottom Action Footer */}
                  <div className="p-3 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs">
                    <span className="text-slate-400 text-[11px]">
                      Se usará el contenido de esta tarjeta para diagnosticar y planificar
                    </span>
                    <button
                      type="button"
                      onClick={() => handleConfirmSelection(activeCard)}
                      className="inline-flex items-center gap-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-4 py-2 text-xs shadow-md shadow-indigo-600/30 transition-all active:scale-95"
                    >
                      <Check className="h-4 w-4" />
                      <span>Seleccionar esta Tarjeta</span>
                    </button>
                  </div>
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-slate-400 space-y-2">
                  <FileQuestion className="h-10 w-10 text-slate-600 mb-1" />
                  <p className="text-sm font-medium text-slate-300">Ninguna tarjeta seleccionada</p>
                  <p className="text-xs text-slate-400 max-w-sm">
                    Elegí una tarjeta del listado izquierdo para previsualizar todos sus campos y datos.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
