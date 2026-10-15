import json
import logging
import base64
import mimetypes
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from app.api.deps import (
    get_card_generator_adapter,
    get_export_deck_service,
    get_generate_cards_service,
    get_anki_connect_adapter,
    get_genanki_file_adapter,
    get_inspect_material_service,
    get_enrich_prerequisite_service,
    get_deck_knowledge_store,
    get_deck_intelligence_service,
    get_deck_dag_service,
    get_ontology_extractor_service,
    get_deck_interview_service,
    get_sanitation_service,
    get_deck_expansion_service,
    get_exam_blueprint_service,
    get_socratic_red_teaming_service,
)

from app.adapters.ai.ollama_adapter import OllamaCardGeneratorAdapter
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.core.logging_config import get_recent_log_lines
from app.domain.models import (
    AnkiStatus,
    OllamaStatus,
    CardType,
    ExportRequest,
    ExportResult,
    Flashcard,
    GenerationOptions,
    StudyPlanInspection,
    InspectMaterialRequest,
    EnrichPrerequisiteRequest,
    EnrichedConceptResult,
    GenerateCardsResponse,
    GenerationBatchEvent,
    DeckNoteRecord,
    MatchPrerequisitesRequest,
    MatchPrerequisitesResponse,
    MatchThemesRequest,
    MatchThemesResponse,
    MatchStudyPlanRequest,
    MatchStudyPlanResponse,
    SyncDeckIndexResponse,
    RefactorNotePreviewRequest,
    RefactorNotePreviewResponse,
    ApplyRefactorRequest,
    ApplyRefactorResponse,
    TopicCoverageAuditRequest,
    TopicCoverageAuditResponse,
    UpdateGapStatusRequest,
    DeckCoverageMapResponse,
    ListDeckAuditsResponse,
    SemanticClusterItem,
    DeckClustersResponse,
    DiscoverClustersRequest,
    AuditQualityBatchRequest,
    AuditQualityBatchResponse,
    DuplicateNotePair,
    DeckDuplicatesResponse,
    DeckConceptDAG,
    ExtractOntologyBatchRequest,
    ExtractOntologyBatchResponse,
    DeckInterviewForm,
    LearningPlanContract,
    SynthesizeContractRequest,
    RefineContractRequest,
    ApproveContractRequest,
    SanitationQueueResponse,
    TransactionalReplaceRequest,
    TransactionalReplaceResponse,
    PreserveOptimalResponse,
    PedagogicalDeckAuditResult,
    DeckExpansionQueueResponse,
    FulfillConceptRequest,

    ExamBlueprint,
    ParseBlueprintRequest,
    BlueprintAlignmentSummary,
    SocraticChallengeResponse,
    SocraticEvaluateRequest,
    SocraticEvaluateResponse,
)

from app.services.export_deck_service import ExportDeckUseCase
from app.services.generate_cards_service import GenerateCardsUseCase
from app.services.deck_intelligence_service import DeckIntelligenceService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/anki/status", response_model=AnkiStatus)
async def check_anki_status(
    export_service: ExportDeckUseCase = Depends(get_export_deck_service),
):
    """Query local Anki Desktop connectivity and list existing decks."""
    return await export_service.get_anki_status()


@router.get("/anki/decks/{deck_name:path}/notes", response_model=List[DeckNoteRecord])
async def get_deck_notes(
    deck_name: str,
    anki_bridge=Depends(get_anki_connect_adapter),
    store: DeckKnowledgeStore = Depends(get_deck_knowledge_store),
):
    """Retrieve all notes and their fields belonging to a specific Anki deck, enriched with quality audits."""
    try:
        notes = await anki_bridge.get_deck_notes(deck_name)
        if not notes:
            return []

        # Enrich notes with indexed/audited quality metadata from SQLite
        try:
            indexed_notes = store.get_all_indexed_notes(deck_name)
            indexed_by_id = {n["note_id"]: n for n in indexed_notes}
            for n in notes:
                idx_data = indexed_by_id.get(n.note_id)
                if idx_data:
                    q_status = idx_data.get("quality_status") or "unreviewed"
                    if q_status in ("debt", "broken"):
                        q_status = "bad"
                    n.quality_status = q_status
                    n.quality_score = idx_data.get("quality_score")
                    n.quality_feedback = idx_data.get("quality_feedback")
                    n.audited_at = idx_data.get("audited_at")
                else:
                    n.quality_status = "unreviewed"
        except Exception as store_err:
            logger.warning("Could not enrich deck notes with store metadata: %s", store_err)

        return notes
    except Exception as e:
        logger.error("Failed to fetch notes for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener notas del mazo '{deck_name}': {str(e)}",
        )


@router.get("/anki/notes/{note_id}", response_model=DeckNoteRecord)
async def get_anki_note_by_id(
    note_id: int,
    anki_bridge: AnkiConnectAdapter = Depends(get_anki_connect_adapter),
    store: DeckKnowledgeStore = Depends(get_deck_knowledge_store),
):
    """Fetch full note details from Anki by note_id, enriched with quality audit status."""
    if note_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nota #{note_id} no encontrada en Anki Desktop.",
        )
    try:
        note = await anki_bridge.get_note_by_id(note_id)
        if not note:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nota #{note_id} no encontrada en Anki Desktop.",
            )
        try:
            db_note = store.get_indexed_note(note_id)
            if db_note:
                q_status = db_note.get("quality_status") or "unreviewed"
                if q_status in ("debt", "broken"):
                    q_status = "bad"
                note.quality_status = q_status
                note.quality_score = db_note.get("quality_score")
                note.quality_feedback = db_note.get("quality_feedback")
                note.audited_at = db_note.get("audited_at")
        except Exception as store_err:
            logger.warning("Could not enrich note #%d from SQLite: %s", note_id, store_err)
        return note
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch note #%d: %s", note_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener nota #{note_id}: {str(e)}",
        )


@router.get("/anki/media/{filename}")
async def get_anki_media(
    filename: str,
    anki_bridge: AnkiConnectAdapter = Depends(get_anki_connect_adapter),
):
    """Retrieve an image or audio media file from Anki Desktop collection.media and stream it."""
    try:
        b64 = await anki_bridge.retrieve_media_base64(filename)
        if not b64:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Media file '{filename}' not found in Anki.")
        media_bytes = base64.b64decode(b64)
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"
            if filename.lower().endswith((".jpg", ".jpeg")):
                mime_type = "image/jpeg"
            elif filename.lower().endswith(".png"):
                mime_type = "image/png"
            elif filename.lower().endswith(".webp"):
                mime_type = "image/webp"
            elif filename.lower().endswith(".mp3"):
                mime_type = "audio/mpeg"
        return Response(
            content=media_bytes,
            media_type=mime_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve media '%s': %s", filename, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/ollama/status", response_model=OllamaStatus)
async def check_ollama_status():
    """Query local Ollama instance connectivity and available models."""
    adapter = OllamaCardGeneratorAdapter()
    res = await adapter.check_availability()
    return OllamaStatus(
        is_available=res.get("is_available", False),
        models=res.get("models", []),
        running_models=res.get("running_models", []),
        active_model=res.get("active_model", "qwen2.5:14b"),
        error_message=res.get("error"),
    )


class TextGenerationRequest(GenerationOptions):
    text: str


def _format_friendly_error(e: Exception) -> str:
    err_str = str(e).lower()
    if "503" in err_str or "unavailable" in err_str or "high demand" in err_str:
        return (
            "Los servidores de Google Gemini están experimentando una alta demanda temporal en su nivel gratuito (Error 503). "
            "El sistema intentó reintentar automáticamente con backoff. Por favor aguardá unos segundos y volvé a presionar Generar."
        )
    if "api_key" in err_str or "401" in err_str or "403" in err_str:
        return (
            "La clave API de Gemini no fue proporcionada o es inválida. Por favor verificala en el botón 'API Key' arriba a la derecha."
        )
    return f"Fallo en generación con IA: {str(e)}"


@router.post("/cards/inspect", response_model=StudyPlanInspection)
async def inspect_material(
    payload: InspectMaterialRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Diagnose educational content, evaluate self-sufficiency, detect missing prerequisites and plan atomic card counts."""
    try:
        service = get_inspect_material_service(
            provider=payload.options.ai_provider,
            api_key=x_gemini_api_key,
            local_model=payload.options.local_model,
        )
        return await service.execute(
            text=payload.text,
            options=payload.options,
            source_note_id=payload.source_note_id,
            media_files=payload.media_files,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("Material inspection failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_format_friendly_error(e),
        )


@router.post("/cards/enrich-prerequisite", response_model=EnrichedConceptResult)
async def enrich_prerequisite(
    payload: EnrichPrerequisiteRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Asynchronously synthesize foundational prerequisite concept to avoid orphan or isolated knowledge."""
    try:
        service = get_enrich_prerequisite_service(
            provider=payload.ai_provider,
            api_key=x_gemini_api_key,
            local_model=payload.local_model,
        )
        return await service.execute(
            concept=payload.concept,
            search_query=payload.search_query,
            context_topic=payload.context_topic,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("Prerequisite enrichment failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_format_friendly_error(e),
        )


@router.post("/cards/generate/text", response_model=GenerateCardsResponse)
async def generate_cards_from_text(
    payload: TextGenerationRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Generate flashcards from raw educational text using Gemini or local Ollama."""
    try:
        service = get_generate_cards_service(
            provider=payload.ai_provider,
            api_key=x_gemini_api_key,
            local_model=payload.local_model,
        )
        options = GenerationOptions(
            card_type=payload.card_type,
            target_count=payload.target_count,
            difficulty_level=payload.difficulty_level,
            language=payload.language,
            deck_name=payload.deck_name,
            custom_instructions=payload.custom_instructions,
            prerequisites_context=payload.prerequisites_context,
            selected_themes=payload.selected_themes,
            ai_provider=payload.ai_provider,
            local_model=payload.local_model,
            neighbor_concepts=payload.neighbor_concepts,
            source_note_id=payload.source_note_id,
        )
        return await service.execute_from_text(payload.text, options)
    except ValueError as ve:
        logger.warning("Validation or Value error during text generation: %s", ve)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("Text generation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_format_friendly_error(e),
        )


@router.post("/cards/generate/text-stream")
async def generate_cards_from_text_stream(
    payload: TextGenerationRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Progressively stream generated flashcards in micro-batches using Server-Sent Events (SSE)."""
    try:
        service = get_generate_cards_service(
            provider=payload.ai_provider,
            api_key=x_gemini_api_key,
            local_model=payload.local_model,
        )
        options = GenerationOptions(
            card_type=payload.card_type,
            target_count=payload.target_count,
            difficulty_level=payload.difficulty_level,
            language=payload.language,
            deck_name=payload.deck_name,
            custom_instructions=payload.custom_instructions,
            prerequisites_context=payload.prerequisites_context,
            selected_themes=payload.selected_themes,
            ai_provider=payload.ai_provider,
            local_model=payload.local_model,
            neighbor_concepts=payload.neighbor_concepts,
            source_note_id=payload.source_note_id,
        )

        async def _event_generator():
            try:
                async for event in service.execute_from_text_stream(payload.text, options):
                    yield f"data: {event.model_dump_json()}\n\n"
            except Exception as exc:
                logger.error("Error during streaming generation: %s", exc)
                err_event = GenerationBatchEvent(
                    event_type="error",
                    message=_format_friendly_error(exc),
                )
                yield f"data: {err_event.model_dump_json()}\n\n"

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error("Failed to initialize text streaming: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_format_friendly_error(e),
        )


@router.post("/cards/inspect/file", response_model=StudyPlanInspection)
async def inspect_material_from_file(
    file: UploadFile = File(...),
    text: Optional[str] = Form(None),
    card_type: CardType = Form(CardType.BASIC),
    target_count: int = Form(0),
    difficulty_level: str = Form("intermediate"),
    language: str = Form("es"),
    deck_name: str = Form("General"),
    custom_instructions: Optional[str] = Form(None),
    ai_provider: str = Form("gemini"),
    local_model: str = Form("llama3.2:3b"),
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Diagnose educational document or image (with optional accompanying text), evaluate self-sufficiency, and detect mandatory deep subtopics."""
    try:
        content_bytes = await file.read()
        mime_type = file.content_type or "application/octet-stream"

        service = get_inspect_material_service(
            provider=ai_provider,
            api_key=x_gemini_api_key,
            local_model=local_model,
        )
        options = GenerationOptions(
            card_type=card_type,
            target_count=target_count,
            difficulty_level=difficulty_level,
            language=language,
            deck_name=deck_name,
            custom_instructions=custom_instructions,
            ai_provider=ai_provider,
            local_model=local_model,
        )
        return await service.execute_from_media(content_bytes, mime_type, options, text=text)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("File material inspection failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_format_friendly_error(e),
        )


@router.post("/cards/generate/file", response_model=GenerateCardsResponse)
async def generate_cards_from_file(
    file: UploadFile = File(...),
    text: Optional[str] = Form(None),
    card_type: CardType = Form(CardType.BASIC),
    target_count: int = Form(0),
    difficulty_level: str = Form("intermediate"),
    language: str = Form("es"),
    deck_name: str = Form("General"),
    custom_instructions: Optional[str] = Form(None),
    prerequisites_context: Optional[str] = Form(None),
    selected_themes: Optional[str] = Form(None),
    ai_provider: str = Form("gemini"),
    local_model: str = Form("llama3.2:3b"),
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Generate flashcards from uploaded document (PDF) or image (PNG/JPEG/WEBP) with optional accompanying text."""
    try:
        content_bytes = await file.read()
        mime_type = file.content_type or "application/octet-stream"

        parsed_themes = None
        if selected_themes:
            try:
                parsed_themes = json.loads(selected_themes)
            except Exception:
                parsed_themes = [t.strip() for t in selected_themes.split(",") if t.strip()]

        service = get_generate_cards_service(
            provider=ai_provider,
            api_key=x_gemini_api_key,
            local_model=local_model,
        )
        options = GenerationOptions(
            card_type=card_type,
            target_count=target_count,
            difficulty_level=difficulty_level,
            language=language,
            deck_name=deck_name,
            custom_instructions=custom_instructions,
            prerequisites_context=prerequisites_context,
            selected_themes=parsed_themes,
            ai_provider=ai_provider,
            local_model=local_model,
        )
        return await service.execute_from_media(content_bytes, mime_type, options, text=text)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("File generation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_format_friendly_error(e),
        )


@router.post("/cards/generate/file-stream")
async def generate_cards_from_file_stream(
    file: UploadFile = File(...),
    text: Optional[str] = Form(None),
    card_type: CardType = Form(CardType.BASIC),
    target_count: int = Form(0),
    difficulty_level: str = Form("intermediate"),
    language: str = Form("es"),
    deck_name: str = Form("General"),
    custom_instructions: Optional[str] = Form(None),
    prerequisites_context: Optional[str] = Form(None),
    selected_themes: Optional[str] = Form(None),
    ai_provider: str = Form("gemini"),
    local_model: str = Form("llama3.2:3b"),
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Progressively stream generated flashcards from file in micro-batches using Server-Sent Events (SSE)."""
    try:
        content_bytes = await file.read()
        mime_type = file.content_type or "application/octet-stream"

        parsed_themes = None
        if selected_themes:
            try:
                parsed_themes = json.loads(selected_themes)
            except Exception:
                parsed_themes = [t.strip() for t in selected_themes.split(",") if t.strip()]

        service = get_generate_cards_service(
            provider=ai_provider,
            api_key=x_gemini_api_key,
            local_model=local_model,
        )
        options = GenerationOptions(
            card_type=card_type,
            target_count=target_count,
            difficulty_level=difficulty_level,
            language=language,
            deck_name=deck_name,
            custom_instructions=custom_instructions,
            prerequisites_context=prerequisites_context,
            selected_themes=parsed_themes,
            ai_provider=ai_provider,
            local_model=local_model,
        )

        async def _event_generator():
            try:
                async for event in service.execute_from_media_stream(
                    content_bytes, mime_type, options, text=text
                ):
                    yield f"data: {event.model_dump_json()}\n\n"
            except Exception as exc:
                logger.error("Error during streaming file generation: %s", exc)
                err_event = GenerationBatchEvent(
                    event_type="error",
                    message=_format_friendly_error(exc),
                )
                yield f"data: {err_event.model_dump_json()}\n\n"

        return StreamingResponse(
            _event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.error("Failed to initialize file streaming: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=_format_friendly_error(e),
        )


@router.post("/cards/export/anki", response_model=ExportResult)
async def export_to_anki(
    payload: ExportRequest,
    export_service: ExportDeckUseCase = Depends(get_export_deck_service),
):
    """Directly push cards to local Anki Desktop via AnkiConnect."""
    if not payload.cards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionaron tarjetas para exportar.",
        )
    return await export_service.export_to_anki(
        payload.deck_name, payload.cards
    )


@router.post("/cards/export/apkg")
async def export_to_apkg(
    payload: ExportRequest,
    export_service: ExportDeckUseCase = Depends(get_export_deck_service),
):
    """Generate and download a standalone .apkg package file."""
    if not payload.cards:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No se proporcionaron tarjetas para exportar.",
        )
    result = await export_service.export_to_apkg(payload.deck_name, payload.cards)
    if not result.success or not result.apkg_file_path:
        err_msg = result.message or "Fallo al generar archivo .apkg"
        code = status.HTTP_400_BAD_REQUEST if "No cards" in err_msg else status.HTTP_500_INTERNAL_SERVER_ERROR
        raise HTTPException(
            status_code=code,
            detail=err_msg,
        )
    return FileResponse(
        path=result.apkg_file_path,
        media_type="application/octet-stream",
        filename=f"{payload.deck_name.replace('::', '_')}.apkg",
    )


@router.post("/anki/decks/{deck_name:path}/sync-index", response_model=SyncDeckIndexResponse)
async def sync_deck_index(
    deck_name: str,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Synchronize Anki deck notes into local SQLite semantic vector store."""
    try:
        service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.sync_deck_index(deck_name, api_key=x_gemini_api_key)
    except Exception as e:
        logger.error("Failed to sync index for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al sincronizar índice del mazo '{deck_name}': {str(e)}",
        )


@router.get("/anki/decks/{deck_name:path}/index-status")
async def get_deck_index_status(
    deck_name: str,
    store: DeckKnowledgeStore = Depends(get_deck_knowledge_store),
):
    """Query semantic index statistics (total indexed notes and last sync date)."""
    return store.get_deck_stats(deck_name)


@router.post("/anki/decks/match-prerequisites", response_model=MatchPrerequisitesResponse)
async def match_prerequisites(
    payload: MatchPrerequisitesRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Evaluate prerequisite concepts against target deck's semantic knowledge index."""
    try:
        service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.match_prerequisites(
            deck_name=payload.deck_name,
            prerequisites=payload.prerequisites,
            api_key=x_gemini_api_key,
            exclude_note_ids=payload.exclude_note_ids,
        )
    except Exception as e:
        logger.error("Failed to match prerequisites for deck '%s': %s", payload.deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en coincidencia semántica con el mazo '{payload.deck_name}': {str(e)}",
        )


@router.post("/anki/decks/match-themes", response_model=MatchThemesResponse)
async def match_themes(
    payload: MatchThemesRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Evaluate core themes against target deck's semantic knowledge index to prevent duplicates."""
    try:
        service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.match_themes(
            deck_name=payload.deck_name,
            themes=payload.themes,
            api_key=x_gemini_api_key,
            exclude_note_ids=payload.exclude_note_ids,
        )
    except Exception as e:
        logger.error("Failed to match core themes for deck '%s': %s", payload.deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en coincidencia semántica de ejes temáticos con el mazo '{payload.deck_name}': {str(e)}",
        )


@router.post("/anki/decks/match-study-plan", response_model=MatchStudyPlanResponse)
async def match_study_plan(
    payload: MatchStudyPlanRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Unified semantic evaluation of both prerequisites and core themes against target deck."""
    try:
        service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.match_study_plan(
            deck_name=payload.deck_name,
            prerequisites=payload.prerequisites,
            themes=payload.core_themes,
            api_key=x_gemini_api_key,
            exclude_note_ids=payload.exclude_note_ids,
            source_note_id=payload.source_note_id,
        )
    except Exception as e:
        logger.error("Failed to match study plan for deck '%s': %s", payload.deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en evaluación semántica del plan de estudio con el mazo '{payload.deck_name}': {str(e)}",
        )


@router.get("/logs/recent")
async def get_recent_logs(
    limit: int = 150,
):
    """Retrieve recent application log lines for live execution monitoring."""
    lines = get_recent_log_lines(max_lines=limit)
    return {"lines": lines}


@router.post("/anki/notes/{note_id}/refactor-preview", response_model=RefactorNotePreviewResponse)
async def preview_refactor_note(
    note_id: int,
    payload: Optional[RefactorNotePreviewRequest] = None,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Generate an AI-driven atomic preview for an existing note in Anki, preserving FSRS review history."""
    try:
        service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        concept_ctx = payload.concept_context if payload else None
        deck_nm = payload.deck_name if payload else None
        provider = payload.ai_provider if payload else "gemini"
        l_model = payload.local_model if payload else None

        return await service.preview_refactor_note(
            note_id=note_id,
            concept_context=concept_ctx,
            deck_name=deck_nm,
            ai_provider=provider,
            local_model=l_model,
            api_key=x_gemini_api_key,
        )
    except Exception as e:
        logger.error("Failed to generate refactor preview for note %d: %s", note_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar vista previa de refactorización para la nota #{note_id}: {str(e)}",
        )


@router.post("/anki/notes/{note_id}/apply-refactor", response_model=ApplyRefactorResponse)
async def apply_refactor_note(
    note_id: int,
    payload: ApplyRefactorRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Apply atomic refactoring in-place to an existing note in Anki Desktop."""
    try:
        service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.apply_refactor_note(
            note_id=note_id,
            deck_name=payload.deck_name,
            fields=payload.fields,
            api_key=x_gemini_api_key,
        )
    except Exception as e:
        logger.error("Failed to apply refactor for note %d: %s", note_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al aplicar la refactorización a la nota #{note_id}: {str(e)}",
        )


@router.get("/anki/decks/audits/{audit_id}", response_model=TopicCoverageAuditResponse)
async def get_coverage_audit(
    audit_id: int,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Retrieve full details of a specific thematic coverage audit by ID."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        audit = await service.get_coverage_audit(audit_id=audit_id)
        if not audit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Auditoría #{audit_id} no encontrada.",
            )
        return audit
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get coverage audit %d: %s", audit_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener la auditoría #{audit_id}: {str(e)}",
        )


@router.patch("/anki/decks/audits/{audit_id}/gaps/{gap_index}")
async def update_gap_status(
    audit_id: int,
    gap_index: int,
    payload: UpdateGapStatusRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Update resolution status and optional generated note ID of an orphan gap."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        success = await service.update_gap_status(
            audit_id=audit_id,
            gap_index=gap_index,
            status=payload.status,
            generated_note_id=payload.generated_note_id,
        )
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se pudo actualizar el estado del vacío #{gap_index} en la auditoría #{audit_id}.",
            )
        return {
            "success": True,
            "audit_id": audit_id,
            "gap_index": gap_index,
            "status": payload.status,
            "generated_note_id": payload.generated_note_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update gap status for audit %d gap %d: %s", audit_id, gap_index, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al actualizar estado del vacío: {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/audit-topic-coverage", response_model=TopicCoverageAuditResponse)
async def audit_topic_coverage(
    deck_name: str,
    payload: TopicCoverageAuditRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Perform a thematic coverage audit over an Anki deck comparing against a target topic."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.audit_topic_coverage(
            deck_name=deck_name,
            topic=payload.topic,
            description=payload.description,
            top_k=payload.top_k,
            save_audit=payload.save_audit,
            api_key=x_gemini_api_key,
        )
    except Exception as e:
        logger.error("Failed to audit topic coverage for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en auditoría de cobertura temática para '{deck_name}': {str(e)}",
        )


@router.get("/anki/decks/{deck_name:path}/audits", response_model=ListDeckAuditsResponse)
async def list_coverage_audits(
    deck_name: str,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """List historical thematic coverage audits for a deck."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.list_coverage_audits(deck_name=deck_name)
    except Exception as e:
        logger.error("Failed to list coverage audits for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al listar auditorías para '{deck_name}': {str(e)}",
        )


@router.get("/anki/decks/{deck_name:path}/coverage-map", response_model=DeckCoverageMapResponse)
async def get_deck_coverage_map(
    deck_name: str,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Generate a hierarchical DAG coverage map for an Anki deck."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)
        return await service.get_deck_coverage_map(deck_name=deck_name, api_key=x_gemini_api_key)
    except Exception as e:
        logger.error("Failed to generate coverage map for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar mapa de cobertura para '{deck_name}': {str(e)}",
        )


@router.get("/anki/decks/{deck_name:path}/semantic-clusters", response_model=DeckClustersResponse)
async def get_deck_semantic_clusters(
    deck_name: str,
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Retrieve persisted semantic clusters for an indexed Anki deck."""
    try:
        clusters = service._store.get_deck_clusters(deck_name)
        return DeckClustersResponse(
            deck_name=deck_name,
            clusters=[SemanticClusterItem(**c) for c in clusters],
        )
    except Exception as e:
        logger.error("Failed to get semantic clusters for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al recuperar clusters semánticos para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/semantic-clusters", response_model=DeckClustersResponse)
async def discover_deck_semantic_clusters(
    deck_name: str,
    payload: Optional[DiscoverClustersRequest] = None,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Trigger unsupervised Spherical K-Means clustering and LLM thematic labeling for a deck."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)

        req = payload or DiscoverClustersRequest()
        discovered = await service.discover_and_apply_semantic_clusters(
            deck_name=deck_name,
            force_refresh=req.force_refresh,
            api_key=x_gemini_api_key,
            ai_provider=req.ai_provider,
            local_model=req.local_model,
            k=req.k,
        )
        return DeckClustersResponse(
            deck_name=deck_name,
            clusters=[SemanticClusterItem(**c) for c in discovered],
        )
    except Exception as e:
        logger.error("Failed to discover semantic clusters for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al descubrir clusters semánticos para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/audit-quality-batch", response_model=AuditQualityBatchResponse)
async def audit_deck_quality_batch(
    deck_name: str,
    payload: Optional[AuditQualityBatchRequest] = None,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Audit a micro-batch of deck notes against strict neurocognitive learning laws."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)

        req = payload or AuditQualityBatchRequest()
        return await service.audit_quality_batch(
            deck_name=deck_name,
            batch_size=req.batch_size,
            note_ids=req.note_ids,
            api_key=x_gemini_api_key,
            ai_provider=req.ai_provider,
            local_model=req.local_model,
        )
    except Exception as e:
        logger.error("Failed to audit quality batch for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al auditar lote de calidad para '{deck_name}': {str(e)}",
        )


@router.get("/anki/decks/{deck_name:path}/duplicates", response_model=DeckDuplicatesResponse)
async def get_deck_duplicates(
    deck_name: str,
    min_similarity: float = 0.88,
    x_gemini_api_key: Optional[str] = Header(default=None),
    service: DeckIntelligenceService = Depends(get_deck_intelligence_service),
):
    """Detect redundant and near-duplicate notes in a deck by vector cosine proximity."""
    try:
        if x_gemini_api_key and not getattr(service, "_is_mock", False):
            service = get_deck_intelligence_service(api_key=x_gemini_api_key)

        return await service.find_deck_duplicates(
            deck_name=deck_name,
            min_similarity=min_similarity,
            api_key=x_gemini_api_key,
        )
    except Exception as e:
        logger.error("Failed to detect duplicates for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al detectar duplicados para '{deck_name}': {str(e)}",
        )


@router.get("/anki/decks/{deck_name:path}/dag", response_model=DeckConceptDAG)
async def get_deck_concept_dag(
    deck_name: str,
    dag_service=Depends(get_deck_dag_service),
):
    """Retrieve the topological concept DAG for a deck, including depth levels, topological sort, and orphan prerequisite gaps."""
    try:
        return dag_service.get_deck_dag(deck_name)
    except Exception as e:
        logger.error("Failed to retrieve concept DAG for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener el DAG de conceptos para '{deck_name}': {str(e)}",
        )


@router.delete("/anki/decks/{deck_name:path}/dag")
async def clear_deck_concept_dag(
    deck_name: str,
    store: DeckKnowledgeStore = Depends(get_deck_knowledge_store),
):
    """Purge stored concept DAG ontology for a deck."""
    try:
        store.clear_deck_dag(deck_name)
        return {"success": True, "message": f"DAG de conceptos purgado para el mazo '{deck_name}'"}
    except Exception as e:
        logger.error("Failed to clear concept DAG for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al purgar DAG de conceptos para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/extract-ontology", response_model=ExtractOntologyBatchResponse)
async def extract_deck_ontology_batch(
    deck_name: str,
    req: ExtractOntologyBatchRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
    anki_bridge=Depends(get_anki_connect_adapter),
    store: DeckKnowledgeStore = Depends(get_deck_knowledge_store),
):
    """Run bottom-up micro-extraction on deck notes and update the topological concept DAG."""
    try:
        extractor = get_ontology_extractor_service(api_key=x_gemini_api_key)

        # 1. Fetch deck notes from AnkiConnect
        all_notes = await anki_bridge.get_deck_notes(deck_name)
        if not all_notes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No se encontraron notas en el mazo '{deck_name}' o AnkiConnect no está conectado.",
            )

        notes_dict = [
            {
                "note_id": n.note_id,
                "front": n.front,
                "back": n.back,
                "tags": n.tags,
            }
            for n in all_notes
        ]

        # 2. Filter notes if specific note_ids requested, otherwise prioritize unextracted notes
        if req.note_ids:
            target_ids = set(req.note_ids)
            target_notes = [n for n in notes_dict if n["note_id"] in target_ids]
        else:
            already_extracted = {
                e["source_note_id"] for e in store.get_all_deck_extracted_knowledge(deck_name)
            }
            unextracted = [n for n in notes_dict if n["note_id"] not in already_extracted]
            target_notes = notes_dict if getattr(req, "force_reextract", False) else unextracted

        if not target_notes:
            dag_summary = get_deck_dag_service().get_deck_dag(deck_name)
            return ExtractOntologyBatchResponse(
                deck_name=deck_name,
                processed_notes_count=0,
                remaining_unextracted_count=0,
                extracted_knowledge=[],
                dag_summary=dag_summary,
            )

        # 3. Extract batch and update DAG
        return await extractor.extract_deck_batch(
            deck_name=deck_name,
            notes=target_notes,
            batch_size=req.batch_size,
            ai_provider=req.ai_provider,
            api_key=x_gemini_api_key,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to extract ontology for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al extraer ontología para '{deck_name}': {str(e)}",
        )


# -----------------------------------------------------------------------------
# Phase 2: Socratic Interview & Learning Plan Contract Endpoints
# -----------------------------------------------------------------------------

@router.get("/anki/decks/{deck_name:path}/interview/contract", response_model=Optional[LearningPlanContract])
async def get_deck_learning_contract(
    deck_name: str,
    service=Depends(get_deck_interview_service),
):
    """Retrieve existing learning plan contract for a deck if already negotiated or approved."""
    return service.get_learning_contract(deck_name)


@router.post("/anki/decks/{deck_name:path}/interview/form", response_model=DeckInterviewForm)
async def generate_deck_interview_form(
    deck_name: str,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Dynamically generate a non-generic 4-slot interview form tailored to the deck's DAG."""
    try:
        service = get_deck_interview_service(api_key=x_gemini_api_key)
        return await service.generate_interview_form(deck_name, api_key=x_gemini_api_key)
    except Exception as e:
        logger.error("Failed to generate interview form for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar formulario contextual para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/interview/synthesize", response_model=LearningPlanContract)
async def synthesize_deck_contract(
    deck_name: str,
    req: SynthesizeContractRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Synthesize formal LearningPlanContract preview from user's responses to the 4 slots."""
    try:
        service = get_deck_interview_service(api_key=x_gemini_api_key)
        return await service.synthesize_contract(deck_name, req.answers, api_key=x_gemini_api_key)
    except Exception as e:
        logger.error("Failed to synthesize contract for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al sintetizar contrato para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/interview/refine", response_model=LearningPlanContract)
async def refine_deck_contract(
    deck_name: str,
    req: RefineContractRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Refine an existing contract preview using natural language feedback."""
    try:
        service = get_deck_interview_service(api_key=x_gemini_api_key)
        return await service.refine_contract(
            deck_name=deck_name,
            current_contract=req.current_contract,
            user_feedback=req.user_feedback,
            api_key=x_gemini_api_key,
        )
    except Exception as e:
        logger.error("Failed to refine contract for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al refinar contrato para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/interview/approve", response_model=LearningPlanContract)
async def approve_deck_contract(
    deck_name: str,
    req: ApproveContractRequest,
):
    """Approve and lock the LearningPlanContract in the database to unlock sanitization."""
    try:
        service = get_deck_interview_service()
        return service.approve_contract(deck_name, req.contract)
    except Exception as e:
        logger.error("Failed to approve contract for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al aprobar contrato para '{deck_name}': {str(e)}",
        )


# -----------------------------------------------------------------------------
# Optional Exam Blueprint & Syllabus Endpoints
# -----------------------------------------------------------------------------

@router.post("/anki/decks/{deck_name:path}/blueprint/parse-text", response_model=ExamBlueprint)
async def parse_deck_blueprint_text(
    deck_name: str,
    req: ParseBlueprintRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Parse raw text syllabus or search web to extract structured ExamBlueprint."""
    try:
        service = get_exam_blueprint_service(api_key=x_gemini_api_key)
        return await service.parse_blueprint(
            raw_text=req.raw_text,
            exam_name=req.exam_name,
            search_web=req.search_web,
            api_key=x_gemini_api_key,
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error("Failed to parse blueprint for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al analizar el temario para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/blueprint/parse-file", response_model=ExamBlueprint)
async def parse_deck_blueprint_file(
    deck_name: str,
    file: UploadFile = File(...),
    exam_name: Optional[str] = Form(default=None),
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Extract raw text from uploaded PDF/TXT/MD blueprint and structure with AI."""
    try:
        service = get_exam_blueprint_service(api_key=x_gemini_api_key)
        content_bytes = await file.read()
        filename = (file.filename or "").lower()

        if filename.endswith(".pdf"):
            raw_text = service.extract_text_from_pdf(content_bytes)
        else:
            raw_text = content_bytes.decode("utf-8", errors="replace")

        if not raw_text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo proporcionado no contiene texto legible.",
            )

        name_to_use = exam_name or file.filename or "Temario Oficial"
        return await service.parse_blueprint(
            raw_text=raw_text,
            exam_name=name_to_use,
            search_web=False,
            api_key=x_gemini_api_key,
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error("Failed to parse blueprint file for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al procesar archivo de temario: {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/blueprint/align", response_model=BlueprintAlignmentSummary)
async def align_deck_blueprint(
    deck_name: str,
    blueprint: ExamBlueprint,
    min_similarity: float = 0.68,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Cross-reference structured blueprint against deck cards and detect curriculum gaps."""
    try:
        service = get_exam_blueprint_service(api_key=x_gemini_api_key)
        return await service.align_blueprint_with_deck(
            deck_name=deck_name,
            blueprint=blueprint,
            min_similarity_threshold=min_similarity,
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error("Failed to align blueprint for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al contrastar temario con el mazo: {str(e)}",
        )


# =========================================================================
# PHASE 3: SURGICAL SANITIZATION & TRANSACTIONAL REPLACEMENT
# =========================================================================

@router.get("/anki/decks/{deck_name:path}/sanitation-queue", response_model=SanitationQueueResponse)
async def get_deck_sanitation_queue(
    deck_name: str,
    sanitation_service = Depends(get_sanitation_service),
):
    """Retrieve the queue of notes pending surgical sanitation for a deck."""
    try:
        return await sanitation_service.get_sanitation_queue(deck_name)
    except Exception as e:
        logger.error("Failed to fetch sanitation queue for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener cola de saneamiento para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/replace-note", response_model=TransactionalReplaceResponse)
async def replace_deck_note(
    deck_name: str,
    req: TransactionalReplaceRequest,
    sanitation_service = Depends(get_sanitation_service),
):
    """Atomically substitute an obsolete note with verified atomic flashcards."""
    try:
        return await sanitation_service.replace_note_transactionally(
            deck_name=deck_name,
            source_note_id=req.source_note_id,
            new_cards=req.new_cards,
            target_concepts=req.target_concepts,
            pending_ledger_collisions=req.pending_ledger_collisions,
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        )
    except Exception as e:
        logger.error(
            "Failed transactional replace for note %d in deck '%s': %s",
            req.source_note_id,
            deck_name,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en sustitución transaccional para la nota #{req.source_note_id}: {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/notes/{note_id}/preserve-optimal", response_model=PreserveOptimalResponse)
async def preserve_deck_note_optimal(
    deck_name: str,
    note_id: int,
    sanitation_service = Depends(get_sanitation_service),
):
    """Mark an existing high-quality note directly as optimal without deleting or modifying in Anki."""
    try:
        return await sanitation_service.mark_note_as_optimal_preserved(deck_name, note_id)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve),
        )
    except Exception as e:
        logger.error("Failed to preserve note %d as optimal in deck '%s': %s", note_id, deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al conservar la nota #{note_id} como óptima: {str(e)}",
        )



@router.get(
    "/anki/decks/{deck_name:path}/pedagogical-order/audit",
    response_model=PedagogicalDeckAuditResult,
)
async def audit_pedagogical_deck_order(
    deck_name: str,
    sanitation_service = Depends(get_sanitation_service),
):
    """Deterministically audit Anki new queue ordering against curriculum DAG depths and prerequisites (0-LLM)."""
    try:
        return await sanitation_service.audit_pedagogical_deck_order(deck_name)
    except Exception as e:
        logger.error("Failed to audit pedagogical order for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al auditar orden pedagógico del mazo: {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/pedagogical-order/align")
@router.post("/anki/decks/{deck_name:path}/reposition")
async def reposition_deck_topologically(
    deck_name: str,
    sanitation_service = Depends(get_sanitation_service),
):
    """Reposition cards in Anki new queue following the curriculum topological order once sanitized."""
    try:
        return await sanitation_service.reposition_deck_topologically(deck_name)
    except Exception as e:
        logger.error("Failed to reposition deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al reordenar tarjetas topológicamente en Anki: {str(e)}",
        )



# =========================================================================
# PHASE 4: TOPOLOGICAL EXPANSION & CURRICULUM GAP FULFILLMENT
# =========================================================================

@router.get("/anki/decks/{deck_name:path}/expansion-queue", response_model=DeckExpansionQueueResponse)
async def get_deck_expansion_queue(
    deck_name: str,
    expansion_service = Depends(get_deck_expansion_service),
):
    """Retrieve uncovered curriculum concepts ordered topologically for expansion."""
    try:
        return await expansion_service.get_expansion_queue(deck_name)
    except Exception as e:
        logger.error("Failed to fetch expansion queue for deck '%s': %s", deck_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al obtener cola de expansión para '{deck_name}': {str(e)}",
        )


@router.post("/anki/decks/{deck_name:path}/expansion/link-concept")
async def link_concept_cards(
    deck_name: str,
    req: FulfillConceptRequest,
    expansion_service = Depends(get_deck_expansion_service),
):
    """Link newly created flashcards to a concept node, resolving its orphan gap status."""
    try:
        for nid in req.note_ids:
            if nid < -9223372036854775808 or nid > 9223372036854775807:
                raise ValueError(f"Note ID {nid} exceeds valid 64-bit integer bounds.")
        success = expansion_service.link_cards_to_concept(
            deck_name=deck_name,
            concept_id=req.concept_id,
            note_ids=req.note_ids,
        )
        return {
            "success": success,
            "deck_name": deck_name,
            "concept_id": req.concept_id,
            "linked_count": len(req.note_ids),
        }
    except (ValueError, OverflowError) as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parámetros inválidos para vincular concepto: {str(ve)}",
        )
    except Exception as e:
        logger.error(
            "Failed to link cards to concept '%s' in deck '%s': %s",
            req.concept_id,
            deck_name,
            e,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al vincular tarjetas al concepto '{req.concept_id}': {str(e)}",
        )


@router.post(
    "/anki/decks/{deck_name:path}/nodes/{concept_id}/socratic-challenge",
    response_model=SocraticChallengeResponse,
)
async def generate_socratic_challenge(
    deck_name: str,
    concept_id: str,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Generate an interactive Socratic integration or counterfactual question for a DAG node in SUFFICIENT status."""
    try:
        service = get_socratic_red_teaming_service(api_key=x_gemini_api_key)
        return await service.generate_challenge(deck_name, concept_id)
    except Exception as e:
        logger.error("Failed to generate Socratic challenge for node '%s': %s", concept_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar el reto socrático para el nodo '{concept_id}': {str(e)}",
        )


@router.post(
    "/anki/decks/{deck_name:path}/nodes/{concept_id}/socratic-evaluate",
    response_model=SocraticEvaluateResponse,
)
async def evaluate_socratic_challenge(
    deck_name: str,
    concept_id: str,
    payload: SocraticEvaluateRequest,
    x_gemini_api_key: Optional[str] = Header(default=None),
):
    """Evaluate learner's mental model response to Socratic challenge. If score >= 0.75, certifies node as MASTERED."""
    try:
        service = get_socratic_red_teaming_service(api_key=x_gemini_api_key)
        return await service.evaluate_response(deck_name, payload)
    except Exception as e:
        logger.error("Failed to evaluate Socratic response for node '%s': %s", concept_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al evaluar la respuesta socrática para el nodo '{concept_id}': {str(e)}",
        )









