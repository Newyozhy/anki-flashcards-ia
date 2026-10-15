import type {
  AnkiStatus,
  OllamaStatus,
  ExportResult,
  Flashcard,
  GenerationOptions,
  PrerequisiteItem,
  StudyPlanInspection,
  GenerateCardsResponse,
  DeckAuditReport,
  PedagogicalAuditResult,
  DeckNoteRecord,
  PrerequisiteMatch,
  MatchStudyPlanResponse,
  SyncDeckIndexResponse,
  CoreTheme,
  RefactorNotePreviewResponse,
  ApplyRefactorResponse,
  CoverageGapStatus,
  CoveredFacet,
  OrphanGap,
  TopicCoverageAuditRequest,
  TopicCoverageAuditResponse,
  DeckAuditSummary,
  ListDeckAuditsResponse,
  DeckCoverageMapNode,
  DeckCoverageMapEdge,
  DeckCoverageMapResponse,
  AuditQualityBatchRequest,
  AuditQualityBatchResponse,
  DeckClustersResponse,
  SemanticClusterItem,
  DeckDuplicatesResponse,
  DeckConceptDAG,
  ExtractOntologyBatchRequest,
  ExtractOntologyBatchResponse,
  DeckInterviewForm,
  LearningPlanContract,
  ExamBlueprint,
  BlueprintAlignmentSummary,
  SanitationQueueResponse,
  TransactionalReplaceRequest,
  TransactionalReplaceResponse,
  SanitationCoverageLedgerInput,
  SocraticChallengeResponse,
  SocraticEvaluateRequest,
  SocraticEvaluateResponse,
  PreserveOptimalResponse,
  DeckExpansionQueueResponse,
  PedagogicalDeckAuditResult,
  PedagogicalOrderViolation,
} from '../types';


export type {
  PrerequisiteItem,
  PrerequisiteMatch,
  MatchStudyPlanResponse,
  SyncDeckIndexResponse,
  CoreTheme,
  CoverageGapStatus,
  CoveredFacet,
  OrphanGap,
  TopicCoverageAuditRequest,
  TopicCoverageAuditResponse,
  DeckAuditSummary,
  ListDeckAuditsResponse,
  DeckCoverageMapNode,
  DeckCoverageMapEdge,
  DeckCoverageMapResponse,
  AuditQualityBatchRequest,
  AuditQualityBatchResponse,
  DeckClustersResponse,
  SemanticClusterItem,
  PedagogicalOrderViolation,
  PedagogicalDeckAuditResult,
};


const API_BASE_URL = 'http://127.0.0.1:8000/api';

export const DEFAULT_TIMEOUT_MS = 30000;
export const AI_TIMEOUT_MS = 120000;

export class ApiTimeoutError extends Error {
  constructor(timeoutMs: number, url: string) {
    const seconds = Math.round(timeoutMs / 1000);
    super(`Tiempo de espera agotado (${seconds}s) al conectar con el servidor (${url}). Verificá que el backend esté ejecutándose.`);
    this.name = 'ApiTimeoutError';
  }
}

export class PartialStreamError extends Error {
  public partialCards: Flashcard[];
  constructor(message: string, partialCards: Flashcard[]) {
    super(message);
    this.name = 'PartialStreamError';
    this.partialCards = partialCards;
  }
}

export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS
): Promise<Response> {
  const { signal: externalSignal, ...restOptions } = options;
  const controller = new AbortController();

  let timeoutId: ReturnType<typeof setTimeout> | null = null;
  if (timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      controller.abort(new ApiTimeoutError(timeoutMs, url));
    }, timeoutMs);
  }

  const handleExternalAbort = () => {
    controller.abort(externalSignal?.reason || new Error('Operación cancelada por el usuario.'));
  };

  if (externalSignal) {
    if (externalSignal.aborted) {
      if (timeoutId) clearTimeout(timeoutId);
      throw externalSignal.reason || new Error('Operación cancelada.');
    }
    externalSignal.addEventListener('abort', handleExternalAbort, { once: true });
  }

  try {
    const response = await fetch(url, {
      ...restOptions,
      signal: controller.signal,
    });
    return response;
  } catch (err: any) {
    if (controller.signal.aborted) {
      const reason = controller.signal.reason;
      if (reason instanceof Error) throw reason;
      throw new Error(String(reason) || 'Petición cancelada o agotada por tiempo.');
    }
    throw err;
  } finally {
    if (timeoutId) clearTimeout(timeoutId);
    if (externalSignal) {
      externalSignal.removeEventListener('abort', handleExternalAbort);
    }
  }
}



export const api = {
  async getDeckNotes(deckName: string): Promise<DeckNoteRecord[]> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/notes`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al obtener notas del mazo '${deckName}' (${response.status})`);
    }
    return await response.json();
  },
  async getNoteById(noteId: number): Promise<DeckNoteRecord> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/anki/notes/${noteId}`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al obtener la nota #${noteId} (${response.status})`);
    }
    return await response.json();
  },
  async getAnkiStatus(): Promise<AnkiStatus> {
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/anki/status`);
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      return await response.json();
    } catch (err: any) {
      return {
        is_connected: false,
        available_decks: [],
        error_message: err.message || 'Error de conexión con el backend',
      };
    }
  },

  async getOllamaStatus(): Promise<OllamaStatus> {
    try {
      const response = await fetchWithTimeout(`${API_BASE_URL}/ollama/status`);
      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }
      return await response.json();
    } catch (err: any) {
      return {
        is_available: false,
        models: [],
        active_model: 'llama3.2:3b',
        error_message: err.message || 'Error de conexión con Ollama',
      };
    }
  },

  async generateFromText(
    text: string,
    options: GenerationOptions,
    apiKey?: string
  ): Promise<GenerateCardsResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const payload = {
      text,
      ...options,
      neighbor_concepts: options.neighbor_concepts,
      source_note_id: options.source_note_id,
      target_concept: options.target_concept,
      media_filenames: options.media_filenames,
    };

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/generate/text`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    }, AI_TIMEOUT_MS);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al generar tarjetas (${response.status})`);
    }

    const data = await response.json();
    if (Array.isArray(data)) {
      return { cards: data };
    }
    return data;
  },

  async generateFromTextStream(
    text: string,
    options: GenerationOptions,
    onBatch: (batchCards: Flashcard[], progress: { batchLabel: string; current: number; total: number; accumulatedCount: number }) => void,
    apiKey?: string,
    signal?: AbortSignal
  ): Promise<GenerateCardsResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const payload = {
      text,
      card_type: options.card_type,
      target_count: options.target_count,
      difficulty_level: options.difficulty_level,
      language: options.language,
      deck_name: options.deck_name,
      custom_instructions: options.custom_instructions,
      prerequisites_context: options.prerequisites_context,
      selected_themes: options.selected_themes,
      ai_provider: options.ai_provider,
      local_model: options.local_model,
      neighbor_concepts: options.neighbor_concepts,
      source_note_id: options.source_note_id,
      target_concept: options.target_concept,
      media_filenames: options.media_filenames,
    };

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/generate/text-stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal,
    }, AI_TIMEOUT_MS);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al generar tarjetas (${response.status})`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      return await this.generateFromText(text, options, apiKey);
    }

    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedCards: Flashcard[] = [];
    let auditReport: DeckAuditReport | undefined = undefined;
    let pedagogicalResults: PedagogicalAuditResult[] | undefined = undefined;

    try {
      while (true) {
        if (signal?.aborted) {
          throw new PartialStreamError('Generación cancelada por el usuario.', accumulatedCards);
        }
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';

        for (const block of blocks) {
          const trimmed = block.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.replace(/^data:\s*/, '');
          try {
            const event = JSON.parse(jsonStr);
            if (event.event_type === 'batch') {
              if (event.cards && event.cards.length > 0) {
                onBatch(event.cards, {
                  batchLabel: event.batch_label || '',
                  current: event.current_batch || 1,
                  total: event.total_batches || 1,
                  accumulatedCount: event.accumulated_count || accumulatedCards.length + event.cards.length,
                });
                accumulatedCards.push(...event.cards);
              }
            } else if (event.event_type === 'done') {
              if (event.cards && event.cards.length > 0) {
                accumulatedCards = event.cards;
              }
              auditReport = event.audit_report;
              pedagogicalResults = event.pedagogical_results;
            } else if (event.event_type === 'error') {
              throw new PartialStreamError(event.message || 'Error durante la generación de microlotes', accumulatedCards);
            }
          } catch (e: any) {
            if (e instanceof PartialStreamError) throw e;
            if (e.message?.includes('microlotes')) throw e;
            console.warn('Error parsing SSE event:', e, jsonStr);
          }
        }
      }
    } catch (streamErr: any) {
      if (accumulatedCards.length > 0 && !(streamErr instanceof PartialStreamError)) {
        throw new PartialStreamError(streamErr.message || 'Error durante la lectura del flujo de tarjetas', accumulatedCards);
      }
      throw streamErr;
    } finally {
      reader.releaseLock();
    }

    return {
      cards: accumulatedCards,
      audit_report: auditReport,
      pedagogical_results: pedagogicalResults,
    };
  },

  async generateFromFileStream(
    file: File,
    options: GenerationOptions,
    onBatch: (batchCards: Flashcard[], progress: { batchLabel: string; current: number; total: number; accumulatedCount: number }) => void,
    apiKey?: string,
    text?: string,
    signal?: AbortSignal
  ): Promise<GenerateCardsResponse> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const formData = new FormData();
    formData.append('file', file);
    if (text?.trim()) {
      formData.append('text', text.trim());
    }
    formData.append('card_type', options.card_type);
    formData.append('target_count', options.target_count.toString());
    formData.append('difficulty_level', options.difficulty_level);
    formData.append('language', options.language);
    formData.append('deck_name', options.deck_name);
    if (options.custom_instructions) {
      formData.append('custom_instructions', options.custom_instructions);
    }
    if (options.prerequisites_context) {
      formData.append('prerequisites_context', options.prerequisites_context);
    }
    if (options.selected_themes && options.selected_themes.length > 0) {
      formData.append('selected_themes', JSON.stringify(options.selected_themes));
    }
    if (options.ai_provider) {
      formData.append('ai_provider', options.ai_provider);
    }
    if (options.local_model) {
      formData.append('local_model', options.local_model);
    }
    if (options.target_concept) {
      formData.append('target_concept', options.target_concept);
    }

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/generate/file-stream`, {
      method: 'POST',
      headers,
      body: formData,
      signal,
    }, AI_TIMEOUT_MS);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al procesar archivo (${response.status})`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      return await this.generateFromFile(file, options, apiKey, text);
    }

    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let accumulatedCards: Flashcard[] = [];
    let auditReport: DeckAuditReport | undefined = undefined;
    let pedagogicalResults: PedagogicalAuditResult[] | undefined = undefined;

    try {
      while (true) {
        if (signal?.aborted) {
          throw new PartialStreamError('Generación cancelada por el usuario.', accumulatedCards);
        }
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split('\n\n');
        buffer = blocks.pop() || '';

        for (const block of blocks) {
          const trimmed = block.trim();
          if (!trimmed.startsWith('data:')) continue;
          const jsonStr = trimmed.replace(/^data:\s*/, '');
          try {
            const event = JSON.parse(jsonStr);
            if (event.event_type === 'batch') {
              if (event.cards && event.cards.length > 0) {
                onBatch(event.cards, {
                  batchLabel: event.batch_label || '',
                  current: event.current_batch || 1,
                  total: event.total_batches || 1,
                  accumulatedCount: event.accumulated_count || accumulatedCards.length + event.cards.length,
                });
                accumulatedCards.push(...event.cards);
              }
            } else if (event.event_type === 'done') {
              if (event.cards && event.cards.length > 0) {
                accumulatedCards = event.cards;
              }
              auditReport = event.audit_report;
              pedagogicalResults = event.pedagogical_results;
            } else if (event.event_type === 'error') {
              throw new PartialStreamError(event.message || 'Error durante la generación de microlotes', accumulatedCards);
            }
          } catch (e: any) {
            if (e instanceof PartialStreamError) throw e;
            if (e.message?.includes('microlotes')) throw e;
            console.warn('Error parsing SSE event:', e, jsonStr);
          }
        }
      }
    } catch (streamErr: any) {
      if (accumulatedCards.length > 0 && !(streamErr instanceof PartialStreamError)) {
        throw new PartialStreamError(streamErr.message || 'Error durante la lectura del flujo de tarjetas', accumulatedCards);
      }
      throw streamErr;
    } finally {
      reader.releaseLock();
    }

    return {
      cards: accumulatedCards,
      audit_report: auditReport,
      pedagogical_results: pedagogicalResults,
    };
  },

  async generateFromFile(
    file: File,
    options: GenerationOptions,
    apiKey?: string,
    text?: string
  ): Promise<GenerateCardsResponse> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const formData = new FormData();
    formData.append('file', file);
    if (text?.trim()) {
      formData.append('text', text.trim());
    }
    formData.append('card_type', options.card_type);
    formData.append('target_count', options.target_count.toString());
    formData.append('difficulty_level', options.difficulty_level);
    formData.append('language', options.language);
    formData.append('deck_name', options.deck_name);
    if (options.custom_instructions) {
      formData.append('custom_instructions', options.custom_instructions);
    }
    if (options.prerequisites_context) {
      formData.append('prerequisites_context', options.prerequisites_context);
    }
    if (options.selected_themes && options.selected_themes.length > 0) {
      formData.append('selected_themes', JSON.stringify(options.selected_themes));
    }
    if (options.ai_provider) {
      formData.append('ai_provider', options.ai_provider);
    }
    if (options.local_model) {
      formData.append('local_model', options.local_model);
    }
    if (options.target_concept) {
      formData.append('target_concept', options.target_concept);
    }

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/generate/file`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al procesar archivo (${response.status})`);
    }

    const data = await response.json();
    if (Array.isArray(data)) {
      return { cards: data };
    }
    return data;
  },

  async exportToAnki(
    deckName: string,
    cards: Flashcard[],
    _obsoleteNoteIds?: number[]
  ): Promise<ExportResult> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/export/anki`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        deck_name: deckName,
        cards,
      }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Fallo al exportar a Anki (${response.status})`);
    }

    return await response.json();
  },

  async exportToApkg(deckName: string, cards: Flashcard[]): Promise<Blob> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/export/apkg`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deck_name: deckName, cards }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al descargar .apkg (${response.status})`);
    }

    return await response.blob();
  },

  async inspectMaterial(
    text: string,
    options: GenerationOptions,
    apiKey?: string,
    sourceNoteId?: number,
    mediaFiles?: string[],
    signal?: AbortSignal
  ): Promise<StudyPlanInspection> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const payload = {
      text,
      options,
      source_note_id: sourceNoteId,
      media_files: mediaFiles || [],
    };

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/inspect`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal,
    }, AI_TIMEOUT_MS);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Fallo en el análisis del material (${response.status})`);
    }

    return await response.json();
  },

  async inspectMaterialFromFile(
    file: File,
    options: GenerationOptions,
    apiKey?: string,
    text?: string,
    signal?: AbortSignal
  ): Promise<StudyPlanInspection> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const formData = new FormData();
    formData.append('file', file);
    if (text?.trim()) {
      formData.append('text', text.trim());
    }
    formData.append('card_type', options.card_type);
    formData.append('target_count', options.target_count.toString());
    formData.append('difficulty_level', options.difficulty_level);
    formData.append('language', options.language);
    formData.append('deck_name', options.deck_name);
    if (options.custom_instructions) {
      formData.append('custom_instructions', options.custom_instructions);
    }
    if (options.ai_provider) {
      formData.append('ai_provider', options.ai_provider);
    }
    if (options.local_model) {
      formData.append('local_model', options.local_model);
    }

    const response = await fetchWithTimeout(`${API_BASE_URL}/cards/inspect/file`, {
      method: 'POST',
      headers,
      body: formData,
      signal,
    }, AI_TIMEOUT_MS);

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Fallo en el análisis del archivo (${response.status})`
      );
    }

    return await response.json();
  },


  async syncDeckIndex(deckName: string, apiKey?: string): Promise<SyncDeckIndexResponse> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/sync-index`,
      {
        method: 'POST',
        headers,
      }
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Fallo al sincronizar índice del mazo '${deckName}' (${response.status})`
      );
    }

    return await response.json();
  },

  async getDeckIndexStatus(
    deckName: string
  ): Promise<{ deck_name: string; total_indexed: number; last_indexed_at?: string }> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/index-status`
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Fallo al consultar estado del mazo '${deckName}' (${response.status})`
      );
    }

    return await response.json();
  },

  async matchStudyPlan(
    deckName: string,
    prerequisites: PrerequisiteItem[],
    themes: CoreTheme[],
    apiKey?: string,
    excludeNoteIds?: number[],
    sourceNoteId?: number
  ): Promise<MatchStudyPlanResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }

    const payload = {
      deck_name: deckName,
      prerequisites,
      core_themes: themes,
      exclude_note_ids: excludeNoteIds || [],
      source_note_id: sourceNoteId,
    };

    const response = await fetchWithTimeout(`${API_BASE_URL}/anki/decks/match-study-plan`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Fallo al evaluar plan de estudio semánticamente (${response.status})`
      );
    }

    return await response.json();
  },

  async previewRefactorNote(
    noteId: number,
    conceptContext?: string,
    deckName?: string,
    apiKey?: string,
    aiProvider?: string,
    localModel?: string
  ): Promise<RefactorNotePreviewResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const payload = {
      note_id: noteId,
      concept_context: conceptContext,
      deck_name: deckName,
      ai_provider: aiProvider || 'gemini',
      local_model: localModel,
    };
    const response = await fetchWithTimeout(`${API_BASE_URL}/anki/notes/${noteId}/refactor-preview`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Fallo al generar vista previa de refactorización (${response.status})`
      );
    }
    return await response.json();
  },

  async applyRefactorNote(
    noteId: number,
    deckName: string,
    fields: Record<string, string>,
    apiKey?: string
  ): Promise<ApplyRefactorResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const payload = {
      note_id: noteId,
      deck_name: deckName,
      fields,
    };
    const response = await fetchWithTimeout(`${API_BASE_URL}/anki/notes/${noteId}/apply-refactor`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Fallo al aplicar refactorización en Anki (${response.status})`
      );
    }
    return await response.json();
  },

  async getRecentLogs(limit: number = 150): Promise<{ lines: string[] }> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/logs/recent?limit=${limit}`);
    if (!response.ok) {
      return { lines: [] };
    }
    return await response.json();
  },

  async auditTopicCoverage(
    deckName: string,
    request: TopicCoverageAuditRequest,
    apiKey?: string
  ): Promise<TopicCoverageAuditResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/audit-topic-coverage`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error en la auditoría de cobertura para '${deckName}' (${response.status})`
      );
    }
    return await response.json();
  },

  async listCoverageAudits(
    deckName: string,
    apiKey?: string
  ): Promise<ListDeckAuditsResponse> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/audits`,
      { headers }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al listar auditorías para '${deckName}' (${response.status})`
      );
    }
    return await response.json();
  },

  async getCoverageAudit(
    auditId: number,
    apiKey?: string
  ): Promise<TopicCoverageAuditResponse> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(`${API_BASE_URL}/anki/decks/audits/${auditId}`, { headers });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al obtener la auditoría #${auditId} (${response.status})`
      );
    }
    return await response.json();
  },

  async updateGapStatus(
    auditId: number,
    gapIndex: number,
    status: CoverageGapStatus,
    generatedNoteId?: number,
    apiKey?: string
  ): Promise<{ success: boolean; status: CoverageGapStatus; audit_id?: number; gap_index?: number; generated_note_id?: number }> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const payload = {
      status,
      generated_note_id: generatedNoteId,
    };
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/audits/${auditId}/gaps/${gapIndex}`,
      {
        method: 'PATCH',
        headers,
        body: JSON.stringify(payload),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al actualizar estado del vacío #${gapIndex} (${response.status})`
      );
    }
    return await response.json();
  },

  async getDeckCoverageMap(
    deckName: string,
    apiKey?: string
  ): Promise<DeckCoverageMapResponse> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/coverage-map`,
      { headers }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al obtener mapa de cobertura para '${deckName}' (${response.status})`
      );
    }
    return await response.json();
  },

  async auditQualityBatch(
    deckName: string,
    options?: AuditQualityBatchRequest,
    apiKey?: string
  ): Promise<AuditQualityBatchResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/audit-quality-batch`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(options || {}),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al auditar lote de calidad para '${deckName}' (${response.status})`
      );
    }
    return await response.json();
  },

  async getDeckSemanticClusters(deckName: string): Promise<DeckClustersResponse> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/semantic-clusters`
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al obtener clusters semánticos para '${deckName}' (${response.status})`
      );
    }
    return await response.json();
  },

  async discoverDeckSemanticClusters(
    deckName: string,
    options?: { forceRefresh?: boolean; k?: number; aiProvider?: string; localModel?: string },
    apiKey?: string
  ): Promise<DeckClustersResponse> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/semantic-clusters`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({
          force_refresh: options?.forceRefresh ?? false,
          forceRefresh: options?.forceRefresh ?? false,
          ai_provider: options?.aiProvider,
          local_model: options?.localModel,
          k: options?.k,
        }),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al descubrir clusters semánticos para '${deckName}' (${response.status})`
      );
    }
    return await response.json();
  },

  async getDeckDuplicates(
    deckName: string,
    minSimilarity: number = 0.88,
    apiKey?: string
  ): Promise<DeckDuplicatesResponse> {
    const headers: Record<string, string> = {};
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/duplicates?min_similarity=${minSimilarity}`,
      { headers }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Error al detectar duplicados para '${deckName}' (${response.status})`
      );
    }
    return await response.json();
  },

  async getDeckConceptDAG(deckName: string): Promise<DeckConceptDAG> {
    const response = await fetchWithTimeout(`${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/dag`);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al obtener DAG de conceptos (${response.status})`);
    }
    return await response.json();
  },

  async extractDeckOntology(
    deckName: string,
    batchSize: ExtractOntologyBatchRequest | number = 25,
    apiKey?: string,
    forceReextract: boolean = false
  ): Promise<ExtractOntologyBatchResponse> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['x-gemini-api-key'] = apiKey.trim();

    const payload: ExtractOntologyBatchRequest =
      typeof batchSize === 'number'
        ? { batch_size: batchSize, force_reextract: forceReextract }
        : { ...batchSize, force_reextract: batchSize.force_reextract ?? forceReextract };

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/extract-ontology`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al extraer ontología (${response.status})`);
    }
    return await response.json();
  },

  async getDeckLearningContract(deckName: string): Promise<LearningPlanContract | null> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/interview/contract`
    );
    if (!response.ok) return null;
    return await response.json();
  },

  async generateDeckInterviewForm(deckName: string, apiKey?: string): Promise<DeckInterviewForm> {
    const headers: Record<string, string> = {};
    if (apiKey) headers['x-gemini-api-key'] = apiKey.trim();

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/interview/form`,
      { method: 'POST', headers }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al generar formulario (${response.status})`);
    }
    return await response.json();
  },

  async synthesizeDeckContract(
    deckName: string,
    answers: Record<string, string>,
    apiKey?: string
  ): Promise<LearningPlanContract> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['x-gemini-api-key'] = apiKey.trim();

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/interview/synthesize`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({ answers }),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al sintetizar contrato (${response.status})`);
    }
    return await response.json();
  },

  async refineDeckContract(
    deckName: string,
    currentContract: LearningPlanContract,
    userFeedback: string,
    apiKey?: string
  ): Promise<LearningPlanContract> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['x-gemini-api-key'] = apiKey.trim();

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/interview/refine`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({ current_contract: currentContract, user_feedback: userFeedback }),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al refinar contrato (${response.status})`);
    }
    return await response.json();
  },

  async approveDeckContract(
    deckName: string,
    contract: LearningPlanContract
  ): Promise<LearningPlanContract> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/interview/approve`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ contract }),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al aprobar contrato (${response.status})`);
    }
    return await response.json();
  },

  async parseDeckBlueprintText(
    deckName: string,
    rawText?: string,
    examName?: string,
    searchWeb?: boolean,
    apiKey?: string
  ): Promise<ExamBlueprint> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['x-gemini-api-key'] = apiKey.trim();

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/blueprint/parse-text`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify({
          raw_text: rawText,
          exam_name: examName,
          search_web: Boolean(searchWeb),
        }),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al analizar temario (${response.status})`);
    }
    return await response.json();
  },

  async parseDeckBlueprintFile(
    deckName: string,
    file: File,
    examName?: string,
    apiKey?: string
  ): Promise<ExamBlueprint> {
    const headers: Record<string, string> = {};
    if (apiKey) headers['x-gemini-api-key'] = apiKey.trim();

    const formData = new FormData();
    formData.append('file', file);
    if (examName) formData.append('exam_name', examName);

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/blueprint/parse-file`,
      {
        method: 'POST',
        headers,
        body: formData,
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al procesar archivo de temario (${response.status})`);
    }
    return await response.json();
  },

  async alignDeckBlueprint(
    deckName: string,
    blueprint: ExamBlueprint,
    minSimilarity?: number,
    apiKey?: string
  ): Promise<BlueprintAlignmentSummary> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey) headers['x-gemini-api-key'] = apiKey.trim();

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/blueprint/align?min_similarity=${minSimilarity || 0.68}`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(blueprint),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al contrastar temario con mazo (${response.status})`);
    }
    return await response.json();
  },

  async getSanitationQueue(deckName: string): Promise<SanitationQueueResponse> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/sanitation-queue`
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al obtener cola de saneamiento (${response.status})`);
    }
    return await response.json();
  },

  async replaceNoteTransactionally(
    deckName: string,
    sourceNoteIdOrPayload: number | TransactionalReplaceRequest,
    newCards?: Flashcard[],
    targetConcepts?: string[],
    pendingLedgerCollisions?: SanitationCoverageLedgerInput[]
  ): Promise<TransactionalReplaceResponse> {
    const payload: TransactionalReplaceRequest =
      typeof sourceNoteIdOrPayload === 'number'
        ? {
            source_note_id: sourceNoteIdOrPayload,
            new_cards: newCards || [],
            target_concepts: targetConcepts || [],
            pending_ledger_collisions: pendingLedgerCollisions || [],
          }
        : sourceNoteIdOrPayload;

    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/replace-note`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error en sustitución transaccional (${response.status})`);
    }
    return await response.json();
  },

  async preserveNoteOptimal(
    deckName: string,
    noteId: number
  ): Promise<PreserveOptimalResponse> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/notes/${noteId}/preserve-optimal`,
      {
        method: 'POST',
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al conservar nota como óptima (${response.status})`);
    }
    return await response.json();
  },

  async generateSocraticChallenge(
    deckName: string,
    conceptId: string,
    apiKey?: string
  ): Promise<SocraticChallengeResponse> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/nodes/${encodeURIComponent(conceptId)}/socratic-challenge`,
      {
        method: 'POST',
        headers,
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al generar reto socrático (${response.status})`);
    }
    return await response.json();
  },

  async evaluateSocraticChallenge(
    deckName: string,
    conceptId: string,
    payload: SocraticEvaluateRequest,
    apiKey?: string
  ): Promise<SocraticEvaluateResponse> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (apiKey?.trim()) {
      headers['x-gemini-api-key'] = apiKey.trim();
    }
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/nodes/${encodeURIComponent(conceptId)}/socratic-evaluate`,
      {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al evaluar reto socrático (${response.status})`);
    }
    return await response.json();
  },

  async getExpansionQueue(deckName: string): Promise<DeckExpansionQueueResponse> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/expansion-queue`
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al obtener cola de expansión (${response.status})`);
    }
    return await response.json();
  },

  async linkConceptCards(
    deckName: string,
    conceptId: string,
    noteIds: number[]
  ): Promise<{ success: boolean; deck_name: string; concept_id: string; linked_count: number }> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/expansion/link-concept`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          concept_id: conceptId,
          note_ids: noteIds,
        }),
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al vincular tarjetas al concepto (${response.status})`);
    }
    return await response.json();
  },

  async repositionDeckTopologically(
    deckName: string
  ): Promise<{
    success: boolean;
    deck_name: string;
    message: string;
    repositioned_count: number;
    sanitized_count?: number;
    backlog_count?: number;
  }> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/reposition`,
      {
        method: 'POST',
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al reordenar tarjetas en Anki (${response.status})`);
    }
    return await response.json();
  },

  async auditPedagogicalDeckOrder(
    deckName: string
  ): Promise<PedagogicalDeckAuditResult> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/pedagogical-order/audit`,
      {
        method: 'GET',
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al auditar orden pedagógico (${response.status})`);
    }
    return await response.json();
  },

  async alignPedagogicalDeckOrder(
    deckName: string
  ): Promise<{
    success: boolean;
    deck_name: string;
    message: string;
    repositioned_count: number;
    sanitized_count?: number;
    backlog_count?: number;
  }> {
    const response = await fetchWithTimeout(
      `${API_BASE_URL}/anki/decks/${encodeURIComponent(deckName)}/pedagogical-order/align`,
      {
        method: 'POST',
      }
    );
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Error al alinear orden pedagógico en Anki (${response.status})`);
    }
    return await response.json();
  },
};




export const getMediaUrl = (filename: string): string => {
  if (!filename) return '';
  const trimmed = filename.trim();
  if (!trimmed) return '';
  if (
    trimmed.startsWith('http://') ||
    trimmed.startsWith('https://') ||
    trimmed.startsWith('data:') ||
    trimmed.startsWith('blob:') ||
    trimmed.includes('/api/anki/media/')
  ) {
    return trimmed;
  }
  let clean = trimmed.replace(/^\/+/, '');
  try {
    clean = decodeURIComponent(clean);
  } catch {
    // Keep original if malformed percent-encoding
  }
  return `${API_BASE_URL}/anki/media/${encodeURIComponent(clean)}`;
};

export const sanitizeHtmlForWeb = (html: string): string => {
  if (!html) return '';
  return html
    .replace(/<(script|iframe|object|embed|style)\b[^>]*>[\s\S]*?<\/\1>/gi, '')
    .replace(/<\/?(?:script|iframe|object|embed|style|link|meta)\b[^>]*\/?>/gi, '')
    .replace(/\s+on[a-zA-Z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, '')
    .replace(
      /\b(href|src)\s*=\s*(["'])\s*(?:javascript:|vbscript:|data:\s*text\/html)[^"']*\2/gi,
      '$1=$2#$2'
    )
    .replace(
      /\b(href|src)\s*=\s*(?:javascript:|vbscript:|data:\s*text\/html)[^\s>]*/gi,
      '$1="#"'
    );
};

export const rewriteMediaUrlsForWeb = (html: string): string => {
  if (!html) return '';
  const sanitized = sanitizeHtmlForWeb(html);
  return sanitized.replace(
    /<img([^>]*?)\bsrc=["']([^"']+)["']([^>]*)>/gi,
    (_match, before, src, after) => {
      return `<img${before}src="${getMediaUrl(src)}"${after}>`;
    }
  );
};


