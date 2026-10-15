import logging
from typing import List, Optional, AsyncGenerator, Dict, Any, Tuple
from app.domain.models import (
    Flashcard,
    GenerationOptions,
    GenerateCardsResponse,
    GenerationBatchEvent,
    CognitiveAuditFinding,
    PedagogicalAuditResult,
)
from app.ports.card_generator_port import ICardGeneratorPort
from app.services.cognitive_auditor_service import CognitiveAuditorService
from app.services.pedagogical_discriminator_service import PedagogicalDiscriminatorService

logger = logging.getLogger(__name__)


class GenerateCardsUseCase:
    """Use case to orchestrate AI card generation adhering to spaced-repetition principles and neurocognitive auditing."""

    def __init__(
        self,
        card_generator: ICardGeneratorPort,
        cognitive_auditor: Optional[CognitiveAuditorService] = None,
        pedagogical_discriminator: Optional[PedagogicalDiscriminatorService] = None,
        store: Optional[Any] = None,
        dag_service: Optional[Any] = None,
    ):
        self._card_generator = card_generator
        self._cognitive_auditor = cognitive_auditor or CognitiveAuditorService()
        self._pedagogical_discriminator = pedagogical_discriminator or PedagogicalDiscriminatorService(store=store)
        self._store = store
        self._dag_service = dag_service

    def _apply_learning_contract(self, options: GenerationOptions) -> None:
        """Inject Phase 2 approved Learning Plan Contract directives into generation options."""
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

    def _apply_mutual_negative_boundaries(self, options: GenerationOptions, text: str) -> None:
        """
        Dynamically discover and inject Mutual Negative Boundaries from the cluster or DAG.
        Enforces zero pedagogical repetition without compressing or sacrificing depth.
        """
        if options.neighbor_concepts is None and self._store and options.deck_name:
            try:
                boundaries = self._store.get_cluster_sibling_boundaries(
                    deck_name=options.deck_name,
                    note_id=options.source_note_id,
                    text_context=text,
                    limit=12,
                )
                if boundaries:
                    options.neighbor_concepts = boundaries
            except Exception:
                pass

    def _apply_dag_pedagogical_context(self, options: GenerationOptions, text: str) -> None:
        """
        Query the deck's pedagogical DAG and inject curriculum constraints, prerequisites,
        depth level, and boundary directives into generation options.
        """
        if not options.deck_name:
            return

        dag_svc = self._dag_service
        if not dag_svc and self._store:
            from app.services.deck_dag_service import DeckDAGService
            dag_svc = DeckDAGService(store=self._store)
            self._dag_service = dag_svc

        if dag_svc:
            try:
                target = getattr(options, "target_concept", None)
                dag_ctx = dag_svc.get_pedagogical_context_for_generation(
                    deck_name=options.deck_name,
                    concept_name=target,
                    text_sample=text,
                )
                if dag_ctx:
                    logger.info(
                        "Injected DAG curriculum context for concept '%s' (depth %d, %d ancestors, %d descendants)",
                        dag_ctx.concept_name,
                        dag_ctx.depth_level,
                        len(dag_ctx.ancestors),
                        len(dag_ctx.descendants),
                    )
                    # Merge negative boundaries into neighbor_concepts
                    if not options.neighbor_concepts:
                        options.neighbor_concepts = dag_ctx.negative_boundaries[:12]
                    else:
                        merged = list(dict.fromkeys(options.neighbor_concepts + dag_ctx.negative_boundaries))
                        options.neighbor_concepts = merged[:16]

                    # Append prompt directive to custom_instructions
                    directive = dag_ctx.prompt_directive
                    if options.custom_instructions:
                        options.custom_instructions = f"{options.custom_instructions}\n\n{directive}"
                    else:
                        options.custom_instructions = directive
            except Exception as err:
                logger.warning("Could not apply DAG pedagogical context: %s", err)

    async def _apply_pedagogical_audit(
        self,
        cards: List[Flashcard],
        audit_report: Optional[Any],
        deck_name: Optional[str],
    ) -> Tuple[List[Flashcard], Optional[Any], List[PedagogicalAuditResult]]:
        """Run Layer 2 facet discrimination and flag any collisions into audit findings."""
        pedagogical_results = await self._pedagogical_discriminator.audit_batch(
            cards,
            deck_name=deck_name,
        )
        if audit_report and getattr(audit_report, "card_reports", None):
            for card, p_res in zip(cards, pedagogical_results):
                if not p_res.is_approved:
                    for cr in audit_report.card_reports:
                        if cr.card_id == card.id:
                            cr.score = max(0, cr.score - 30)
                            cr.passed = False
                            cr.findings.append(
                                CognitiveAuditFinding(
                                    rule="PEDAGOGICAL_REDUNDANCY_COLLISION",
                                    severity="VIOLATION",
                                    message=p_res.audit_feedback,
                                    original_snippet=card.front,
                                    corrected_snippet="Colisión de objetivo cognitivo detectada",
                                    auto_fixed=False,
                                )
                            )
        return cards, audit_report, pedagogical_results

    async def execute_from_text(
        self, text: str, options: GenerationOptions
    ) -> GenerateCardsResponse:
        """Validate input, generate cards from raw text, and audit/refine them across Layer 1 and Layer 2."""
        self._apply_learning_contract(options)
        cleaned_text = text.strip()
        if not cleaned_text:
            if options.prerequisites_context or options.selected_themes:
                theme_lines = "\n".join(f"- {t}" for t in (options.selected_themes or []))
                cleaned_text = (
                    f"Ejes Temáticos y Contenido Educativo Aprobado:\n{theme_lines}\n\n"
                    f"Contexto Fundacional:\n{options.prerequisites_context or ''}"
                ).strip()
            else:
                raise ValueError("Educational text cannot be empty.")
        self._apply_mutual_negative_boundaries(options, cleaned_text)
        self._apply_dag_pedagogical_context(options, cleaned_text)
        raw_cards = await self._card_generator.generate_from_text(cleaned_text, options)
        # Layer 1: Deterministic Syntax & Formats
        final_cards, audit_report = self._cognitive_auditor.audit_deck(raw_cards)
        # Layer 2: Pedagogical Anti-Redundancy & Facet Discrimination
        final_cards, audit_report, pedagogical_results = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )

        return GenerateCardsResponse(
            cards=final_cards,
            audit_report=audit_report,
            pedagogical_results=pedagogical_results,
        )

    async def execute_from_text_stream(
        self, text: str, options: GenerationOptions
    ) -> AsyncGenerator[GenerationBatchEvent, None]:
        """Progressively stream flashcards per micro-batch as they are generated."""
        self._apply_learning_contract(options)
        cleaned_text = text.strip()
        if not cleaned_text:
            if options.prerequisites_context or options.selected_themes:
                theme_lines = "\n".join(f"- {t}" for t in (options.selected_themes or []))
                cleaned_text = (
                    f"Ejes Temáticos y Contenido Educativo Aprobado:\n{theme_lines}\n\n"
                    f"Contexto Fundacional:\n{options.prerequisites_context or ''}"
                ).strip()
            else:
                raise ValueError("Educational text cannot be empty.")
        self._apply_mutual_negative_boundaries(options, cleaned_text)
        self._apply_dag_pedagogical_context(options, cleaned_text)

        accumulated_cards: List[Flashcard] = []
        last_total = 1
        async for label, cards, current, total in self._card_generator.generate_from_text_stream(
            cleaned_text, options
        ):
            last_total = total
            accumulated_cards.extend(cards)
            yield GenerationBatchEvent(
                event_type="batch",
                batch_label=label,
                cards=cards,
                current_batch=current,
                total_batches=total,
                accumulated_count=len(accumulated_cards),
            )

        final_cards, audit_report = self._cognitive_auditor.audit_deck(accumulated_cards)
        final_cards, audit_report, _ = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )
        yield GenerationBatchEvent(
            event_type="done",
            batch_label="done",
            cards=final_cards,
            current_batch=last_total,
            total_batches=last_total,
            accumulated_count=len(final_cards),
            audit_report=audit_report,
        )

    async def execute_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> GenerateCardsResponse:
        """Validate input, generate cards from image or PDF bytes, and audit across Layer 1 and Layer 2 with multi-image support."""
        if not file_bytes and not media_parts:
            raise ValueError("File content cannot be empty.")
        self._apply_learning_contract(options)
        self._apply_mutual_negative_boundaries(options, text or "")
        self._apply_dag_pedagogical_context(options, text or "")
        raw_cards = await self._card_generator.generate_from_media(
            file_bytes, mime_type, options, text=text, media_parts=media_parts
        )
        final_cards, audit_report = self._cognitive_auditor.audit_deck(raw_cards)
        final_cards, audit_report, pedagogical_results = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )
        return GenerateCardsResponse(
            cards=final_cards,
            audit_report=audit_report,
            pedagogical_results=pedagogical_results,
        )

    async def execute_from_media_stream(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> AsyncGenerator[GenerationBatchEvent, None]:
        """Progressively stream flashcards per micro-batch from media with multi-image support."""
        if not file_bytes and not media_parts:
            raise ValueError("File content cannot be empty.")
        self._apply_learning_contract(options)
        self._apply_mutual_negative_boundaries(options, text or "")
        self._apply_dag_pedagogical_context(options, text or "")

        accumulated_cards: List[Flashcard] = []
        last_total = 1
        async for label, cards, current, total in self._card_generator.generate_from_media_stream(
            file_bytes, mime_type, options, text=text, media_parts=media_parts
        ):
            last_total = total
            accumulated_cards.extend(cards)
            yield GenerationBatchEvent(
                event_type="batch",
                batch_label=label,
                cards=cards,
                current_batch=current,
                total_batches=total,
                accumulated_count=len(accumulated_cards),
            )

        final_cards, audit_report = self._cognitive_auditor.audit_deck(accumulated_cards)
        final_cards, audit_report, _ = await self._apply_pedagogical_audit(
            final_cards, audit_report, options.deck_name
        )
        yield GenerationBatchEvent(
            event_type="done",
            batch_label="done",
            cards=final_cards,
            current_batch=last_total,
            total_batches=last_total,
            accumulated_count=len(final_cards),
            audit_report=audit_report,
        )

