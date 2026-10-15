import base64
import logging
import mimetypes
import re
from typing import List, Optional, Tuple
from app.domain.models import GenerationOptions, StudyPlanInspection, EnrichedConceptResult
from app.ports.card_generator_port import ICardGeneratorPort
from app.ports.anki_bridge_port import IAnkiBridgePort

logger = logging.getLogger(__name__)


class InspectMaterialUseCase:
    """Orchestrates pre-flight pedagogical diagnostic of study material."""

    def __init__(
        self,
        card_generator: ICardGeneratorPort,
        anki_bridge: Optional[IAnkiBridgePort] = None,
        store: Optional[Any] = None,
    ):
        self._card_generator = card_generator
        self._anki_bridge = anki_bridge
        self._store = store

    async def execute(
        self,
        text: str,
        options: GenerationOptions,
        source_note_id: Optional[int] = None,
        media_files: Optional[List[str]] = None,
    ) -> StudyPlanInspection:
        if not text or not text.strip():
            raise ValueError("El texto educativo a diagnosticar no puede estar vacío.")

        # Inject Phase 2 Learning Plan Contract directives if approved
        if self._store and options.deck_name:
            contract = self._store.get_learning_contract(options.deck_name)
            if contract and contract.get("status") == "approved":
                directives = [
                    f"Nivel Cognitivo Requerido (Bloom): {contract.get('bloom_level')}",
                    f"Profundidad Operativa: {contract.get('operational_depth')}",
                ]
                ex = contract.get("exclusion_boundary") or []
                if ex:
                    directives.append(f"Frontera de Exclusión (PROHIBIDO incluir en tarjetas): {', '.join(ex)}")
                contract_txt = "\n".join(directives)
                if options.custom_instructions:
                    options.custom_instructions = f"{options.custom_instructions}\n\n[Contrato Pedagógico de Aprendizaje]:\n{contract_txt}"
                else:
                    options.custom_instructions = f"[Contrato Pedagógico de Aprendizaje]:\n{contract_txt}"

        # Inject beginner first-principles directive if learner level is beginner
        diff_str = str(getattr(options.difficulty_level, "value", options.difficulty_level)).lower()
        if diff_str == "beginner":
            beginner_dir = (
                "[Perfil del Aprendiz: PRINCIPIANTE]\n"
                "- Aplica rigor absoluto de primeros principios: explica el 'por qué' causal de cada fenómeno desde la base.\n"
                "- No asumas familiaridad con acrónimos ni jerga técnica sin descomponerla previamente.\n"
                "- Diseña prerrequisitos exhaustivos ante cualquier salto conceptual para evitar lagunas fundacionales."
            )
            if options.custom_instructions:
                options.custom_instructions = f"{options.custom_instructions}\n\n{beginner_dir}"
            else:
                options.custom_instructions = beginner_dir

        media_parts: List[Tuple[bytes, str]] = []
        files_to_fetch = list(media_files or [])
        if not files_to_fetch and text:
            extracted = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', text)
            if extracted:
                files_to_fetch = list(dict.fromkeys(extracted))

        # Enforce maximum 8 diagrams per note inspection for multimodal cognitive stability
        files_to_fetch = files_to_fetch[:8]

        if files_to_fetch and self._anki_bridge:
            for filename in files_to_fetch:
                try:
                    b64_str = await self._anki_bridge.retrieve_media_base64(filename)
                    if b64_str:
                        file_bytes = base64.b64decode(b64_str)
                        mime_type = mimetypes.guess_type(filename)[0] or "image/png"
                        media_parts.append((file_bytes, mime_type))
                        logger.info(
                            "Retrieved multimodal media '%s' (%s, %d bytes) for inspection",
                            filename,
                            mime_type,
                            len(file_bytes),
                        )
                except Exception as e:
                    logger.warning("Failed to retrieve media file '%s' for inspection: %s", filename, e)

        logger.info(
            "Executing InspectMaterialUseCase for text length=%d, media_parts=%d",
            len(text),
            len(media_parts),
        )
        result = await self._card_generator.inspect_material(
            text=text.strip(),
            options=options,
            media_parts=media_parts if media_parts else None,
        )
        result.source_text = text.strip()
        result.source_note_id = source_note_id
        result.inherited_media_files = files_to_fetch

        # Auto-register detected prerequisites as orphan gaps for Phase 4
        if self._store and options.deck_name and result.prerequisites:
            for p in result.prerequisites:
                try:
                    from app.services.deck_dag_service import slugify_concept
                    pslug = slugify_concept(p.concept)
                    if pslug:
                        self._store.upsert_concept_node(
                            deck_name=options.deck_name,
                            concept_id=pslug,
                            name=p.concept,
                            description=p.reason,
                        )
                except Exception as prereq_err:
                    logger.debug("Could not auto-register prerequisite '%s': %s", p.concept, prereq_err)

        return result

    async def execute_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> StudyPlanInspection:
        if not file_bytes:
            raise ValueError("El archivo multimedia a diagnosticar no puede estar vacío.")

        logger.info(
            "Executing InspectMaterialUseCase for media mime=%s, bytes=%d, has_text=%s",
            mime_type,
            len(file_bytes),
            bool(text),
        )
        result = await self._card_generator.inspect_material_from_media(
            file_bytes, mime_type, options, text=text
        )
        if text and text.strip():
            result.source_text = text.strip()
        return result



class EnrichPrerequisiteUseCase:
    """Orchestrates asynchronous synthesis of foundational prerequisite concepts."""

    def __init__(self, card_generator: ICardGeneratorPort):
        self._card_generator = card_generator

    async def execute(
        self, concept: str, search_query: str, context_topic: Optional[str] = None
    ) -> EnrichedConceptResult:
        if not concept or not concept.strip():
            raise ValueError("El concepto a enriquecer no puede estar vacío.")

        logger.info("Executing EnrichPrerequisiteUseCase for concept='%s'", concept)
        return await self._card_generator.enrich_prerequisite(
            concept.strip(), search_query.strip(), context_topic
        )
