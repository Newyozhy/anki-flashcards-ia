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
  SanitationCoverageLedgerInput,
  DeckConceptDAG,
} from './types';

import { Sparkles, Compass, Image as ImageIcon, Search } from 'lucide-react';

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
const SocraticNodeMasteryModal = React.lazy(() =>
  import('./components/SocraticNodeMasteryModal').then((m) => ({
    default: m.SocraticNodeMasteryModal,
  }))
);
const PedagogicalOrderAuditModal = React.lazy(() =>
  import('./components/PedagogicalOrderAuditModal').then((m) => ({
    default: m.PedagogicalOrderAuditModal,
  }))
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
  const [isPedagogicalAuditOpen, setIsPedagogicalAuditOpen] = useState<boolean>(false);
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

  // Main Intent Switcher: Sanitation (v2.0 default) vs Ingest (free-form)
  const [appMode, setAppMode] = useState<'sanitation' | 'ingest'>('sanitation');

  // Deck Concept DAG State
  const [deckDAG, setDeckDAG] = useState<DeckConceptDAG | null>(null);

  const fetchDeckDAG = useCallback(async (deckName: string) => {
    if (!deckName) return null;
    try {
      const dag = await api.getDeckConceptDAG(deckName);
      setDeckDAG(dag);
      return dag;
    } catch (err) {
      console.warn('Could not fetch deck DAG:', err);
      return null;
    }
  }, []);

  // Socratic Mastery Modal State
  const [socraticModalState, setSocraticModalState] = useState<{
    isOpen: boolean;
    conceptName: string;
  } | null>(null);

  // Deterministic Topological Sanitation Queue State
  const [sanitationQueue, setSanitationQueue] = useState<SanitationQueueResponse | null>(null);
  const [isProcessingSanitationReplace, setIsProcessingSanitationReplace] = useState<boolean>(false);

  const fetchSanitationQueue = useCallback(async (deckName: string) => {
    if (!deckName) return null;
    try {
      const q = await api.getSanitationQueue(deckName);
      setSanitationQueue(q);
      return q;
    } catch (err) {
      console.warn('Could not fetch sanitation queue:', err);
      return null;
    }
  }, []);

  // Fetch sanitation queue and DAG when deck changes or on mount
  useEffect(() => {
    if (!options.deck_name) return;
    const timer = setTimeout(() => {
      void fetchSanitationQueue(options.deck_name);
      void fetchDeckDAG(options.deck_name);
    }, 0);
    return () => clearTimeout(timer);
  }, [options.deck_name, fetchSanitationQueue, fetchDeckDAG]);

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

  const handleSanitizeConceptInQueue = async (conceptTitle: string) => {
    setIsDeckStudioOpen(false);
    try {
      const q = await fetchSanitationQueue(options.deck_name);
      if (!q || q.notes.length === 0) {
        addToast('info', `No hay notas pendientes de saneamiento en '${options.deck_name}'.`);
        return;
      }

      const titleLower = conceptTitle.trim().toLowerCase();

      // 1. Precise lookup via Concept DAG nodes and cards_mapped
      let matchingItem: DeckNoteRecord | undefined;
      const dag = deckDAG || (await fetchDeckDAG(options.deck_name));
      if (dag?.nodes) {
        const matchingNode = dag.nodes.find(
          (n) => n.name.toLowerCase() === titleLower || n.id.toLowerCase() === titleLower
        );
        if (matchingNode && matchingNode.cards_mapped?.length > 0) {
          const mappedSet = new Set(matchingNode.cards_mapped);
          matchingItem = q.notes.find((item) => mappedSet.has(item.note_id));
        }
      }

      // 2. Lookup via note tags
      if (!matchingItem) {
        matchingItem = q.notes.find((item) =>
          item.tags.some(
            (t) => t.toLowerCase() === titleLower || t.toLowerCase().includes(titleLower)
          )
        );
      }

      // 3. Fallback to clean text / front substring match
      if (!matchingItem) {
        matchingItem = q.notes.find(
          (item) =>
            (item.clean_front || item.front || '').toLowerCase().includes(titleLower) ||
            (item.clean_text || '').toLowerCase().includes(titleLower)
        );
      }

      if (matchingItem) {
        addToast('info', `Enfocando nota #${matchingItem.note_id} de '${conceptTitle}'.`);
        await handleInspectSanitationNote(matchingItem, options.deck_name);
      } else {
        addToast(
          'info',
          `No se encontró nota específica para '${conceptTitle}'. Enfocando primera nota de la cola.`
        );
        await handleInspectSanitationNote(q.notes[0], options.deck_name);
      }
    } catch (err: any) {
      addToast('error', `Error al consultar cola de saneamiento: ${err.message || 'Error'}`);
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

      let generatedCards = genResult.cards;

      // Assign inherited media diagrams deterministically based on card.source_images and theme.associated_diagrams
      if (approvedPlan.inherited_media_files && approvedPlan.inherited_media_files.length > 0) {
        const themeDiagramMap = new Map<string, string[]>();
        if (approvedPlan.core_themes) {
          for (const theme of approvedPlan.core_themes) {
            if (theme.associated_diagrams && theme.associated_diagrams.length > 0) {
              themeDiagramMap.set(theme.title.toLowerCase(), theme.associated_diagrams);
            }
          }
        }

        generatedCards = generatedCards.map((card) => {
          const cardContent = `${card.front} ${card.back} ${card.explanation || ''}`;
          const diagramsForCard = new Set<string>(card.source_images || []);
          if (approvedPlan.core_themes) {
            for (const theme of approvedPlan.core_themes) {
              const themeLower = theme.title.toLowerCase();
              const hasTag = card.tags?.some((t) => t.toLowerCase() === themeLower);
              const hasText = cardContent.toLowerCase().includes(themeLower);
              if ((hasTag || hasText) && theme.associated_diagrams) {
                for (const d of theme.associated_diagrams) {
                  diagramsForCard.add(d);
                }
              }
            }
          }

          const diagramsToInject = Array.from(diagramsForCard).filter(
            (d) => !cardContent.includes(d.trim())
          );

          if (diagramsToInject.length === 0) return card;

          const mediaTags = diagramsToInject
            .map((m) => `<div class="inherited-media mt-2"><img src="${m}" alt="Diagrama conceptual" /></div>`)
            .join('\n');

          return {
            ...card,
            explanation: card.explanation
              ? `${card.explanation}\n\n${mediaTags}`
              : mediaTags,
            source_images: Array.from(diagramsForCard),
          };
        });
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

  // Unified Export to AnkiConnect / Transactional Sanitation (H-10)
  const handleExportToAnki = async () => {
    if (cards.length === 0) return;
    setIsExportingAnki(true);
    setIsProcessingSanitationReplace(true);
    try {
      const originNoteId = selectedAnkiCard?.note_id ?? inspection?.source_note_id ?? null;

      if (originNoteId) {
        // H-10 Single Official Sanitation Path: Transactional Replacement with Ledger & DAG update
        const targetConcepts = inspection?.core_themes
          ?.filter((t) => t.selected !== false)
          ?.map((t) => t.title) || [];

        const pendingCollisions: SanitationCoverageLedgerInput[] = [];
        if (inspection?.core_themes) {
          for (const t of inspection.core_themes) {
            if (
              t.selected !== false &&
              t.match_info?.matched_note_id &&
              t.match_info.status === 'cognitive_debt'
            ) {
              pendingCollisions.push({
                colliding_note_id: t.match_info.matched_note_id,
                concept_title: t.title,
              });
            }
          }
        }

        const res = await api.replaceNoteTransactionally(
          options.deck_name,
          originNoteId,
          cards,
          targetConcepts,
          pendingCollisions
        );

        triggerConfetti();
        addToast(
          'success',
          `🎉 Nota #${res.deleted_note_id} sustituida con éxito`,
          `Se crearon ${res.created_cards_count} tarjetas atómicas óptimas (splicing local ordenado). Restan ${res.remaining_in_queue} notas por sanear.`
        );

        const currentConceptName =
          inspection?.topic_name || (targetConcepts && targetConcepts[0]) || '';

        // Clear current card state, audit report, and inspection
        setCards([]);
        setSelectedAnkiCard(null);
        setAuditReport(null);
        setInspection(null);
        localStorage.removeItem('ankicraft_generated_cards');
        localStorage.removeItem('ankicraft_audit_report');
        sessionStorage.removeItem('ankicraft_selected_anki_card');
        sessionStorage.removeItem('ankicraft_active_inspection');

        // Refresh DAG and check if the sanitized concept node reached SUFFICIENT or 0 debt remains
        const updatedDAG = await fetchDeckDAG(options.deck_name);
        const refreshedQueue = await fetchSanitationQueue(options.deck_name);

        if (currentConceptName && updatedDAG?.nodes) {
          const matchingNode = updatedDAG.nodes.find(
            (n) =>
              n.name.toLowerCase() === currentConceptName.toLowerCase() ||
              n.id.toLowerCase() === currentConceptName.toLowerCase()
          );
          if (matchingNode) {
            const hasPendingDebt =
              refreshedQueue?.notes.some((n) =>
                matchingNode.cards_mapped?.includes(n.note_id)
              ) ?? false;

            if (
              matchingNode.status === 'SUFFICIENT' ||
              (!hasPendingDebt && matchingNode.status !== 'MASTERED')
            ) {
              setSocraticModalState({
                isOpen: true,
                conceptName: matchingNode.name || currentConceptName,
              });
            }
          }
        }

        // Auto-advance to next note if available
        if (refreshedQueue && refreshedQueue.notes.length > 0) {
          const nextItem = refreshedQueue.notes[0];
          await handleInspectSanitationNote(nextItem, options.deck_name);
        } else if (refreshedQueue && refreshedQueue.notes.length === 0) {
          addToast(
            'success',
            '🏆 ¡Mazo 100% Saneado!',
            '¡Misión cumplida! Se sanearon todas las notas de este mazo. Verificando orden pedagógico en Anki...'
          );
          setIsPedagogicalAuditOpen(true);
        }

      } else {
        // Pure creation of brand new cards (no origin note)
        const result = await api.exportToAnki(options.deck_name, cards);
        if (result.success) {
          triggerConfetti();
          addToast(
            'success',
            '¡Sincronización Exitosa!',
            result.message || `Cartas inyectadas en el mazo '${options.deck_name}'.`
          );
          setCards([]);
          setInspection(null);
          localStorage.removeItem('ankicraft_generated_cards');

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
      }

      fetchAnkiStatus();
      if (options.deck_name) {
        api.syncDeckIndex(options.deck_name, apiKey).catch((err) => {
          console.warn('Silent auto-sync after export failed:', err);
        });
        void fetchSanitationQueue(options.deck_name);
      }
    } catch (err: any) {
      addToast(
        'error',
        'Error de comunicación con Anki',
        err.message || 'Asegurate de que Anki Desktop esté abierto con el plugin AnkiConnect.'
      );
    } finally {
      setIsExportingAnki(false);
      setIsProcessingSanitationReplace(false);
    }
  };

  // Preserve existing note as optimal without rewriting or deleting in Anki
  const handlePreserveOptimal = async () => {
    const noteId = selectedAnkiCard?.note_id || inspection?.source_note_id;
    if (!noteId || !options.deck_name) return;
    try {
      setIsProcessingSanitationReplace(true);
      await api.preserveNoteOptimal(options.deck_name, noteId);
      addToast('success', 'Nota conservada', `La nota #${noteId} fue catalogada como óptima sin alterar Anki.`);
      handleClearInspection();
      setCards([]);
      setSelectedAnkiCard(null);
      void fetchSanitationQueue(options.deck_name);
    } catch (err: any) {
      console.error(err);
      addToast('error', 'Error al conservar nota', err.message || 'No se pudo conservar la nota.');
    } finally {
      setIsProcessingSanitationReplace(false);
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

      {/* Primary Intent Mode Switcher Tabs */}
      <div className="border-b border-slate-800/80 bg-slate-950/60 backdrop-blur-md">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-2 py-2.5">
            <button
              type="button"
              onClick={() => setAppMode('sanitation')}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                appMode === 'sanitation'
                  ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-600/25 ring-1 ring-indigo-400/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <span>🛠️ Saneamiento Curricular</span>
              {sanitationQueue && sanitationQueue.pending_count > 0 && (
                <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold text-amber-300 border border-amber-500/30">
                  {sanitationQueue.pending_count}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => setAppMode('ingest')}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                appMode === 'ingest'
                  ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-600/25 ring-1 ring-indigo-400/40'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <span>➕ Ingesta Libre / Material Nuevo</span>
            </button>
          </div>
        </div>
      </div>

      <main className="mx-auto flex-1 w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        {appMode === 'sanitation' ? (
          /* SANITATION SPLIT-PANE WORKSPACE (v2.0) */
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Left Column (lg:col-span-4): Persistent Topological Curation Queue */}
            <div className="lg:col-span-4 space-y-4">
              <CurationQueueBanner
                queue={curationQueue}
                sanitationQueue={sanitationQueue}
                dag={deckDAG}
                onAnalyzeItem={handleAnalyzeQueuedItem}
                onAnalyzeSanitationNote={handleInspectSanitationNote}
                onDismissItem={handleDismissCurationItem}
                onClearQueue={handleClearCurationQueue}
                isInspecting={isInspecting}
                activeNoteId={selectedAnkiCard?.note_id || inspection?.source_note_id || null}
                mode="panel"
              />
            </div>

            {/* Right Column (lg:col-span-8): Active Turn Workspace */}
            <div className="lg:col-span-8 space-y-5">
              {/* Active Note Compact Header */}
              {(selectedAnkiCard || inspection?.source_note_id) && (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-indigo-500/40 bg-gradient-to-r from-slate-900 via-indigo-950/30 to-slate-900 p-4 shadow-lg shadow-indigo-950/20 backdrop-blur-xl animate-fade-in">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-indigo-500/20 border border-indigo-500/40 text-indigo-300">
                      <Compass className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs font-bold text-indigo-300 bg-indigo-950/80 px-2 py-0.5 rounded-lg border border-indigo-800/50">
                          Nota #{selectedAnkiCard?.note_id || inspection?.source_note_id}
                        </span>
                        {inspection?.topic_name && (
                          <span className="text-xs font-semibold text-white bg-slate-800 px-2 py-0.5 rounded-lg border border-slate-700">
                            {inspection.topic_name}
                          </span>
                        )}
                        {(selectedAnkiCard?.media_files?.length || inspection?.inherited_media_files?.length) ? (
                          <span className="inline-flex items-center gap-1 text-[10px] text-cyan-300 bg-cyan-950/40 px-2 py-0.5 rounded-lg border border-cyan-800/50">
                            <ImageIcon className="h-3 w-3" />
                            {(selectedAnkiCard?.media_files?.length || inspection?.inherited_media_files?.length)} diagramas
                          </span>
                        ) : null}
                      </div>
                      <p className="text-xs text-slate-300 line-clamp-1 mt-1 italic">
                        "{selectedAnkiCard?.clean_front || selectedAnkiCard?.front || inspection?.source_text?.slice(0, 100) || ''}"
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {inspection && (
                      <button
                        type="button"
                        onClick={() => setIsInspectionModalOpen(true)}
                        className="inline-flex items-center gap-1.5 rounded-xl border border-indigo-500/40 bg-indigo-950/60 hover:bg-indigo-900/60 px-3 py-1.5 text-xs font-semibold text-indigo-200 hover:text-white transition-all shadow-sm active:scale-95 cursor-pointer"
                        title="Re-abrir Cockpit de Diagnóstico y Andamiaje Cognitivo"
                      >
                        <Search className="h-3.5 w-3.5 text-indigo-400" />
                        <span>Re-abrir Cockpit</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={handlePreserveOptimal}
                      disabled={isExportingAnki || isProcessingSanitationReplace}
                      className="inline-flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 hover:bg-slate-700 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-all active:scale-95 disabled:opacity-50 cursor-pointer"
                      title="Marca la nota original como óptima en el índice sin sustitución"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-amber-400" />
                      <span>Conservar como Óptima</span>
                    </button>
                  </div>
                </div>
              )}

              {/* Active Study Plan Banner (if inspection exists) */}
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

              {/* Workspace Content: Loading, Cards Grid or Empty Prompt */}
              {isGenerating ? (
                <LoadingSkeleton
                  count={options.target_count > 6 ? 6 : options.target_count || 4}
                  variant="cards"
                  label={
                    options.ai_provider === 'ollama'
                      ? `Sintetizando microlotes atómicos con ${options.local_model || 'Ollama Local'}...`
                      : 'Sintetizando flashcards atómicas con Gemini...'
                  }
                />
              ) : cards.length > 0 ? (
                <FlashcardGrid
                  cards={cards}
                  deckName={options.deck_name}
                  sourceNoteId={selectedAnkiCard?.note_id || inspection?.source_note_id || null}
                  onUpdateCard={handleUpdateCard}
                  onDeleteCard={handleDeleteCard}
                  onAddManualCard={handleAddManualCard}
                  onClearCards={handleClearCards}
                  onExportToAnki={handleExportToAnki}
                  onExportToApkg={handleExportToApkg}
                  onPreserveOptimal={handlePreserveOptimal}
                  isExportingAnki={isExportingAnki}
                  isExportingApkg={isExportingApkg}
                  isAnkiConnected={ankiStatus.is_connected}
                  onOpenAuditModal={() => setIsAuditModalOpen(true)}
                  auditScore={auditReport?.average_quality_score}
                />
              ) : (selectedAnkiCard || inspection?.source_note_id) ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/40 p-12 text-center backdrop-blur-sm space-y-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                    <Compass className="h-6 w-6" />
                  </div>
                  <h3 className="text-base font-semibold text-white">
                    Nota #{selectedAnkiCard?.note_id || inspection?.source_note_id} cargada para saneamiento
                  </h3>
                  <p className="text-xs text-slate-400 max-w-md leading-relaxed">
                    El material de la tarjeta está listo. Abrí el Cockpit para validar el andamiaje cognitivo o generá directamente las tarjetas atómicas propuestas.
                  </p>
                  <div className="pt-2 flex items-center gap-3">
                    {inspection && (
                      <button
                        type="button"
                        onClick={() => setIsInspectionModalOpen(true)}
                        className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 text-xs font-bold shadow-md shadow-indigo-600/30 transition-all cursor-pointer"
                      >
                        <Search className="h-4 w-4" />
                        <span>Abrir Cockpit de Diagnóstico</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        if (inspection) {
                          void handleConfirmGenerateFromInspection(inspection);
                        } else if (selectedAnkiCard) {
                          void handleInspectSanitationNote(selectedAnkiCard, options.deck_name);
                        }
                      }}
                      className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white px-4 py-2 text-xs font-bold shadow-md shadow-emerald-950/40 transition-all cursor-pointer"
                    >
                      <Sparkles className="h-4 w-4" />
                      <span>Sintetizar Flashcards Atómicas</span>
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-16 text-center backdrop-blur-sm space-y-3">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600/10 border border-indigo-500/20 text-indigo-400">
                    <Compass className="h-7 w-7" />
                  </div>
                  <h3 className="text-base font-semibold text-white">Workspace de Saneamiento Curricular</h3>
                  <p className="text-xs text-slate-400 max-w-md leading-relaxed">
                    Seleccioná una nota con deuda cognitiva en la Cola Topológica a la izquierda para iniciar su reestructuración pedagógica hacia la atomicidad.
                  </p>
                  {sanitationQueue && sanitationQueue.notes.length > 0 && (
                    <button
                      type="button"
                      onClick={() =>
                        handleInspectSanitationNote(sanitationQueue.notes[0], options.deck_name)
                      }
                      className="mt-2 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white px-5 py-2.5 text-xs font-bold shadow-lg shadow-indigo-600/30 active:scale-95 transition-all cursor-pointer"
                    >
                      <span>⚡ Sanear Siguiente en Turno (Nota #{sanitationQueue.notes[0].note_id})</span>
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* INGEST MODE (Free-form generation) */
          <div className="space-y-8">
            {/* Top Hero banner */}
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

            {/* Cards Grid */}
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
              )}
            </div>
          </div>
        )}
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
            onSanitizeConceptInQueue={handleSanitizeConceptInQueue}
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

        {/* Socratic Node Mastery Certification Challenge Modal */}
        {socraticModalState && (
          <SocraticNodeMasteryModal
            isOpen={socraticModalState.isOpen}
            onClose={() => setSocraticModalState(null)}
            deckName={options.deck_name}
            conceptName={socraticModalState.conceptName}
            apiKey={apiKey}
            onMasteryAchieved={(cName) => {
              addToast(
                'success',
                `🎖️ ¡Maestría Certificada en '${cName}'!`,
                'El nodo del Grafo de Precedencia ha sido certificado como MASTERED.'
              );
              void fetchSanitationQueue(options.deck_name);
              if (options.deck_name) {
                api.getDeckConceptDAG(options.deck_name).then(setDeckDAG).catch(() => {});
              }
            }}
          />
        )}

        {/* Pedagogical Order Audit Modal */}
        {isPedagogicalAuditOpen && (
          <PedagogicalOrderAuditModal
            isOpen={isPedagogicalAuditOpen}
            onClose={() => setIsPedagogicalAuditOpen(false)}
            deckName={options.deck_name}
            onAligned={() => {
              void fetchSanitationQueue(options.deck_name);
              if (options.deck_name) {
                api.getDeckConceptDAG(options.deck_name).then(setDeckDAG).catch(() => {});
              }
            }}
          />
        )}
      </Suspense>


      <ToastContainer toasts={toasts} onDismiss={removeToast} />
    </div>
  );
};

export default App;
