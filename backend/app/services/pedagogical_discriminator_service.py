import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.formatting import extract_breadcrumb_and_body
from app.domain.models import (
    CardType,
    ExtractedFacet,
    FacetComparisonResult,
    FacetDiscriminationVerdict,
    FacetType,
    Flashcard,
    PedagogicalAuditResult,
)

logger = logging.getLogger(__name__)


def _stem_word(w: str) -> str:
    """Lightweight Spanish/English stemmer for conceptual root normalization."""
    w = w.lower()
    for suffix in ("aciones", "amiento", "amientos", "amente", "ación", "acion", "icion", "ición", "ciones", "encias", "encia", "ancias", "ancia"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    for suffix in ("ales", "ados", "adas", "idos", "idas", "idad", "idades", "ando", "iendo", "ores", "oras", "ivos", "ivas"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    for suffix in ("ado", "ada", "ido", "ida", "ivo", "iva", "oso", "osa", "ico", "ica", "ito", "ita", "ero", "era"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            return w[:-len(suffix)]
    if w.endswith("es") and len(w) >= 4:
        return w[:-2]
    if w.endswith("s") and len(w) >= 4:
        w = w[:-1]
    if w.endswith(("a", "e", "o")) and len(w) >= 4:
        return w[:-1]
    return w


def _tokenize_core_words(text: str) -> Set[str]:
    """Extract normalized content keywords ignoring Spanish/English stop words."""
    stop_words = {
        "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "a",
        "con", "por", "para", "que", "es", "son", "se", "su", "sus", "al", "y", "o",
        "the", "a", "an", "of", "in", "to", "for", "with", "by", "is", "are", "on", "at",
        "un", "una", "dos", "tres", "patron", "patrón", "forma", "mediante", "cual", "cuál",
        "que", "qué", "donde", "dónde", "cuando", "cuándo", "como", "cómo"
    }
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    words = cleaned.split()
    return {_stem_word(w) for w in words if len(w) > 2 and w not in stop_words}


class PedagogicalDiscriminatorService:
    """
    Layer 2: Multi-Level Pedagogical Anti-Redundancy & Cognitive Facet Discriminator.
    Guarantees:
    - Level 1: Intra-batch anti-redundancy (same cognitive facet and target fact).
    - Level 2: Global deck anti-redundancy (via vector K-NN pre-filter and facet contrast).
    - Distinguishes between entity-sharing complementary facets (desirable) vs redundant facts (prohibited).
    """

    def __init__(
        self,
        store: Optional[Any] = None,
        embedding_adapter: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ):
        self._store = store
        self._embedding_adapter = embedding_adapter
        self._llm_client = llm_client

    def extract_facet(self, card: Flashcard) -> ExtractedFacet:
        """
        Extract the cognitive facet dimension and atomic retrieval fact from a flashcard.
        Uses deterministic heuristic extraction with support for LLM enhancement.
        """
        breadcrumb, body = extract_breadcrumb_and_body(card.front)
        raw_text = f"{body} {card.back or ''}".strip()

        # 1. Detect Entity
        entity = breadcrumb if breadcrumb else "General"
        # If breadcrumb is hierarchical (A > B > C), the entity is typically the leaf or subtopic
        if ">" in entity:
            parts = [p.strip() for p in entity.split(">")]
            entity = parts[-1] if parts else entity

        # 2. Detect Facet Type via syntactic / interrogative intent
        facet_type = FacetType.OTHER
        facet_label = "Aspecto General"
        target_fact = ""

        lower_front = body.lower()

        # Stop condition / Termination
        if any(term in lower_front for term in ["condición de salida", "condicion de salida", "finaliza", "termina", "condición de parada", "final answer"]):
            facet_type = FacetType.STOP_CONDITION
            facet_label = "Condición de Salida / Terminación"
            target_fact = card.back or "Estado de parada o Final Answer"

        # Data source / Origin of observation
        elif any(term in lower_front for term in ["de dónde proviene", "de donde proviene", "origen", "fuente de", "observación proviene", "observation proviene"]):
            facet_type = FacetType.DATA_SOURCE_ORIGIN
            facet_label = "Procedencia y Origen de Datos"
            target_fact = card.back or "Entorno externo o resultado de herramienta"

        # Differentiation / Contrast
        elif any(term in lower_front for term in ["diferencia", "difiere", "frente a", "comparado con", "vs", "versus", "ventaja frente", "limitación principal"]):
            facet_type = FacetType.DIFFERENTIATION_CONTRAST
            facet_label = "Matriz de Contraste y Mitigación de Errores"
            target_fact = card.back or "Diferenciación conceptual"

        # Causal Mechanism / Architectural Reason (Arquetipo C)
        elif any(term in lower_front for term in ["por qué", "por que", "causa raíz", "causa raiz", "mecanismo de recuperación", "mecanismo de recuperacion"]):
            facet_type = FacetType.MECHANISM_CYCLE
            facet_label = "Mecanismo Causal y Razón Arquitectónica"
            target_fact = card.back or body

        # Failure / Trap / Vulnerability / Error Propagation
        elif any(term in lower_front for term in ["trampa", "error común", "error comun", "alucinación", "alucinaciones", "fallo", "fallas", "riesgo", "qué sucede con un error", "que sucede con un error", "propaga", "propagación"]):
            facet_type = FacetType.FAILURE_TRAP
            facet_label = "Punto de Falla y Mitigación de Errores"
            target_fact = card.back or "Mecanismo de mitigación o propagación de fallo"

        # Mechanism / Execution cycle / Interleaving
        elif any(term in lower_front for term in ["intercala", "componentes", "bucle", "ciclo", "secuencia", "paso completo", "thought", "action", "observation"]):
            facet_type = FacetType.MECHANISM_CYCLE
            facet_label = "Mecanismo y Ciclo de Ejecución"
            # If cloze, extract cloze target as core fact
            cloze_matches = re.findall(r"\{\{[cC]\d+::([^}]+?)(?:::.*?)?\}\}", body)
            if cloze_matches:
                target_fact = " ".join(cloze_matches)
            else:
                target_fact = card.back or body

        # Definition / Function
        elif any(term in lower_front for term in ["qué es", "que es", "definición", "concepto", "para qué sirve"]):
            facet_type = FacetType.DEFINITION_FUNCTION
            facet_label = "Definición y Propósito Fundamental"
            target_fact = card.back or body

        else:
            # Fallback for clozes
            cloze_matches = re.findall(r"\{\{[cC]\d+::([^}]+?)(?:::.*?)?\}\}", body)
            if cloze_matches:
                target_fact = " ".join(cloze_matches)
                facet_label = f"Oclusión: {target_fact[:30]}"
            else:
                target_fact = card.back or body[:50]

        return ExtractedFacet(
            entity=entity,
            facet_type=facet_type,
            facet_label=facet_label,
            target_retrieval_fact=target_fact.strip(),
        )

    def discriminate_pair(
        self,
        candidate_card: Flashcard,
        existing_text: str,
        existing_back: Optional[str] = None,
        existing_note_id: Optional[int] = None,
        existing_card_id: Optional[str] = None,
    ) -> FacetComparisonResult:
        """
        Compare a candidate flashcard against an existing note or sibling batch card.
        Returns whether it is a complementary facet or a redundant collision.
        """
        cand_facet = self.extract_facet(candidate_card)

        # Create temporary pseudo-card for existing text to extract its facet
        existing_card = Flashcard(front=existing_text, back=existing_back or existing_text)
        exist_facet = self.extract_facet(existing_card)

        # Tokenize only the target atomic fact (not the facet label) to prevent artificial overlap
        cand_tokens = _tokenize_core_words(cand_facet.target_retrieval_fact)
        exist_tokens = _tokenize_core_words(exist_facet.target_retrieval_fact)

        intersection = cand_tokens.intersection(exist_tokens)
        min_len = min(len(cand_tokens), len(exist_tokens)) if cand_tokens and exist_tokens else 1
        overlap_ratio = len(intersection) / min_len if min_len > 0 else 0.0

        # Tokenize question body (excluding breadcrumbs)
        _, cand_q_body = extract_breadcrumb_and_body(candidate_card.front)
        _, exist_q_body = extract_breadcrumb_and_body(existing_text)
        cand_q_tokens = _tokenize_core_words(cand_q_body)
        exist_q_tokens = _tokenize_core_words(exist_q_body)
        q_intersection = cand_q_tokens.intersection(exist_q_tokens)
        min_q_len = min(len(cand_q_tokens), len(exist_q_tokens)) if cand_q_tokens and exist_q_tokens else 1
        q_overlap_ratio = len(q_intersection) / min_q_len if min_q_len > 0 else 0.0

        # Collision Rule:
        # 1. Same facet type
        is_same_facet = cand_facet.facet_type == exist_facet.facet_type
        has_critical_fact_collision = is_same_facet and overlap_ratio >= 0.65
        has_question_collision = is_same_facet and q_overlap_ratio >= 0.55

        # 2. Specific failure/trap and error propagation overlap
        is_failure_collision = (
            cand_facet.facet_type == FacetType.FAILURE_TRAP
            and exist_facet.facet_type == FacetType.FAILURE_TRAP
            and (len(intersection) >= 1 or q_overlap_ratio >= 0.35)
            and any(elem.startswith(("propag", "cascad", "magnif", "fall")) for elem in cand_tokens | cand_q_tokens)
            and any(elem.startswith(("propag", "cascad", "magnif", "fall")) for elem in exist_tokens | exist_q_tokens)
        )

        # 3. Exact key phrase match (e.g. "intercalación de razonamiento y acciones")
        cand_clean_fact = re.sub(r"[^\w\s]", "", cand_facet.target_retrieval_fact.lower())
        exist_clean_fact = re.sub(r"[^\w\s]", "", exist_facet.target_retrieval_fact.lower())
        exact_subphrase = (len(cand_clean_fact) > 12 and cand_clean_fact in exist_clean_fact) or (
            len(exist_clean_fact) > 12 and exist_clean_fact in cand_clean_fact
        )

        # 4. Cross-facet or general high fact overlap
        has_high_fact_overlap = overlap_ratio >= 0.70

        if (is_same_facet and (has_critical_fact_collision or has_question_collision)) or is_failure_collision or exact_subphrase or has_high_fact_overlap:
            if is_failure_collision:
                reason = "Colisión de objetivo cognitivo: Ambas tarjetas evalúan el mismo punto de falla y riesgo de propagación de errores en cascada."
            elif has_question_collision:
                reason = (
                    f"Colisión de objetivo cognitivo: Ambas tarjetas evalúan la misma faceta "
                    f"('{cand_facet.facet_label}') y formulan la misma pregunta de contraste clave."
                )
            else:
                reason = (
                    f"Colisión de objetivo cognitivo: Ambas tarjetas evalúan la misma faceta "
                    f"('{cand_facet.facet_label}') y el mismo hecho atómico ('{cand_facet.target_retrieval_fact}')."
                )
            return FacetComparisonResult(
                verdict=FacetDiscriminationVerdict.REDUNDANT_COLLISION,
                candidate_entity=cand_facet.entity,
                candidate_facet=cand_facet.facet_label,
                colliding_note_id=int(existing_note_id) if existing_note_id is not None else None,
                colliding_card_id=str(existing_card_id) if existing_card_id is not None else None,
                colliding_snippet=existing_text[:80] + "..." if len(existing_text) > 80 else existing_text,
                reasoning=reason,
                confidence_score=round(max(overlap_ratio, q_overlap_ratio, 0.9), 2),
            )

        return FacetComparisonResult(
            verdict=FacetDiscriminationVerdict.FACETED_COMPLEMENT,
            candidate_entity=cand_facet.entity,
            candidate_facet=cand_facet.facet_label,
            colliding_note_id=None,
            colliding_card_id=None,
            colliding_snippet=None,
            reasoning=(
                f"Faceta complementaria válida: La tarjeta evalúa '{cand_facet.facet_label}', "
                f"lo cual difiere del objetivo de la nota de referencia ('{exist_facet.facet_label}')."
            ),
            confidence_score=1.0,
        )

    async def audit_batch(
        self,
        cards: List[Flashcard],
        deck_name: Optional[str] = None,
        exclude_note_ids: Optional[List[int]] = None,
    ) -> List[PedagogicalAuditResult]:
        """
        Audit a batch of flashcards against Level 1 (Intra-batch) and Level 2 (Global Deck Vector K-NN).
        """
        results: List[PedagogicalAuditResult] = []
        approved_batch_cards: List[Tuple[Flashcard, ExtractedFacet]] = []

        for card in cards:
            cand_facet = self.extract_facet(card)
            intra_collision: Optional[FacetComparisonResult] = None
            global_collision: Optional[FacetComparisonResult] = None

            # 1. Level 1: Intra-batch discrimination
            for approved_card, approved_facet in approved_batch_cards:
                comparison = self.discriminate_pair(
                    candidate_card=card,
                    existing_text=approved_card.front,
                    existing_back=approved_card.back,
                    existing_card_id=approved_card.id,
                )
                if comparison.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION:
                    intra_collision = comparison
                    break

            # 2. Level 2: Global Deck vector search (if store and deck_name provided)
            if not intra_collision and self._store and deck_name and self._embedding_adapter:
                try:
                    if hasattr(self._embedding_adapter, "get_embedding"):
                        query_vec = await self._embedding_adapter.get_embedding(card.front)
                    elif hasattr(self._embedding_adapter, "embed_single"):
                        query_vec = await self._embedding_adapter.embed_single(card.front)
                    else:
                        query_vec = None
                    if query_vec:
                        similar_notes = self._store.semantic_search(
                            deck_name=deck_name,
                            query_embedding=query_vec,
                            top_k=3,
                            min_similarity=0.75,
                            exclude_note_ids=exclude_note_ids or [],
                        )
                        for note in similar_notes:
                            note_front = note.get("front", "")
                            note_back = note.get("back", "")
                            note_id = note.get("note_id")
                            comparison = self.discriminate_pair(
                                candidate_card=card,
                                existing_text=note_front,
                                existing_back=note_back,
                                existing_note_id=note_id,
                            )
                            if comparison.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION:
                                global_collision = comparison
                                break
                except Exception as e:
                    logger.warning("Global deck vector search skipped due to error: %s", e)

            # Determine composite verdict
            is_approved = (intra_collision is None) and (global_collision is None)
            feedback = ""
            if intra_collision:
                feedback = f"⚠️ Colisión intra-lote: {intra_collision.reasoning}"
            elif global_collision:
                feedback = f"⚠️ Colisión global en mazo: {global_collision.reasoning}"
            else:
                feedback = f"✅ Aprobada: Faceta '{cand_facet.facet_label}' complementaria."

            audit_res = PedagogicalAuditResult(
                card_id=card.id,
                card_front=card.front,
                extracted_facet=cand_facet,
                intra_batch_collision=intra_collision,
                global_deck_collision=global_collision,
                is_approved=is_approved,
                audit_feedback=feedback,
            )
            results.append(audit_res)

            if is_approved:
                approved_batch_cards.append((card, cand_facet))

        return results
