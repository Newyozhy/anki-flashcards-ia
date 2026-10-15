import asyncio
import base64
import json
import logging
import math
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from google import genai
from google.genai import types

from app.core.config import settings
from app.core.clustering import spherical_kmeans, determine_optimal_k
from app.domain.models import (
    CoreTheme,
    CoreThemeItem,
    PrerequisiteItem,
    PrerequisiteMatch,
    PrerequisiteMatchStatus,
    MatchPrerequisitesResponse,
    MatchThemesResponse,
    MatchStudyPlanResponse,
    SyncDeckIndexResponse,
    RefactorNotePreviewResponse,
    ApplyRefactorResponse,
    CoverageGapStatus,
    CoveredFacet,
    OrphanGap,
    TopicCoverageAuditRequest,
    TopicCoverageAuditResponse,
    UpdateGapStatusRequest,
    DeckCoverageMapNode,
    DeckCoverageMapEdge,
    DeckCoverageMapResponse,
    DeckAuditSummary,
    ListDeckAuditsResponse,
    SemanticClusterItem,
    DeckClustersResponse,
    DiscoverClustersRequest,
    AuditQualityBatchRequest,
    NoteQualityAuditItem,
    AuditQualityBatchResponse,
    DuplicateNotePair,
    DeckDuplicatesResponse,
)
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.ports.embedding_port import IEmbeddingPort
from app.ports.card_generator_port import ICardGeneratorPort
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.services.semantic_auditor_agent import SemanticAuditorAgent

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = (
        cleaned.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return " ".join(cleaned.split()).strip()


class DeckIntelligenceService:
    """Orchestrates deck indexing, vector embeddings, and semantic prerequisite cognitive arbitration."""

    def __init__(
        self,
        anki_bridge: IAnkiBridgePort,
        embedding_port: IEmbeddingPort,
        store: DeckKnowledgeStore,
        card_generator: Optional[ICardGeneratorPort] = None,
    ):
        self._anki_bridge = anki_bridge
        self._embedding_port = embedding_port
        self._store = store
        self._card_generator = card_generator
        self._semantic_auditor = SemanticAuditorAgent(
            anki_bridge=self._anki_bridge,
            store=self._store,
        )
        self._sync_locks: Dict[str, asyncio.Lock] = {}

    def _get_deck_lock(self, deck_name: str) -> asyncio.Lock:
        """Ensure only one sync/indexing job runs per deck concurrently."""
        if deck_name not in self._sync_locks:
            self._sync_locks[deck_name] = asyncio.Lock()
        return self._sync_locks[deck_name]

    async def sync_deck_index(
        self, deck_name: str, api_key: Optional[str] = None
    ) -> SyncDeckIndexResponse:
        """Fetch notes from Anki desktop, compute vector embeddings for new notes, and persist into SQLite store."""
        async with self._get_deck_lock(deck_name):
            start_time = time.time()
            logger.info("Starting deck index synchronization for '%s'...", deck_name)

            # 1. Fetch notes from Anki Desktop
            anki_notes = await self._anki_bridge.get_deck_notes(deck_name)
            total_notes = len(anki_notes)

            if not anki_notes:
                duration = round(time.time() - start_time, 2)
                logger.info(
                    "Deck '%s' has 0 notes or Anki is unreachable. Duration: %.2fs",
                    deck_name,
                    duration,
                )
                return SyncDeckIndexResponse(
                    deck_name=deck_name,
                    total_notes=0,
                    newly_indexed=0,
                    duration_seconds=duration,
                )

            # 2. Identify notes needing embeddings: either new or existing with NULL embedding
            notes_with_emb = {n["note_id"] for n in self._store.get_all_notes_with_embeddings(deck_name)}
            notes_to_index = [n for n in anki_notes if int(n["note_id"]) not in notes_with_emb]

            # 2b. Cleanup obsolete records in indexed_notes if notes were deleted in Anki Desktop
            anki_ids = {int(n["note_id"]) for n in anki_notes}
            all_indexed_ids = self._store.get_indexed_note_ids(deck_name)
            obsolete_in_store = [nid for nid in all_indexed_ids if nid not in anki_ids]
            if obsolete_in_store:
                logger.info(
                    "Purging %d obsolete notes from store index that no longer exist in Anki for deck '%s'",
                    len(obsolete_in_store),
                    deck_name,
                )
                self._store.delete_note_embeddings(deck_name, obsolete_in_store)

            if not notes_to_index:
                duration = round(time.time() - start_time, 2)
                logger.info(
                    "All %d notes in deck '%s' are already indexed and embedded. Duration: %.2fs",
                    total_notes,
                    deck_name,
                    duration,
                )
                return SyncDeckIndexResponse(
                    deck_name=deck_name,
                    total_notes=total_notes,
                    newly_indexed=0,
                    duration_seconds=duration,
                )

            # 3. Prepare clean text representations
            texts_to_embed = []
            for note in notes_to_index:
                front = note.get("clean_front") or _strip_html(note.get("front", ""))
                back = note.get("clean_back") or _strip_html(note.get("back", ""))
                tags_list = note.get("tags", [])
                tags_str = ", ".join(tags_list) if isinstance(tags_list, list) else str(tags_list)
                clean_repr = f"{front} | {back} | tags: {tags_str}".strip()
                if hasattr(note, "clean_text"):
                    note.clean_text = clean_repr
                try:
                    note["clean_text"] = clean_repr
                except Exception:
                    pass
                texts_to_embed.append(clean_repr)

            # 4. Generate embeddings via IEmbeddingPort
            logger.info(
                "Generating embeddings for %d new notes in deck '%s'...",
                len(texts_to_embed),
                deck_name,
            )
            embeddings = await self._embedding_port.embed_texts(texts_to_embed)

            for note, emb in zip(notes_to_index, embeddings):
                if hasattr(note, "embedding"):
                    note.embedding = emb
                try:
                    note["embedding"] = emb
                except Exception:
                    pass

            # 5. Save note embeddings in SQLite
            self._store.save_note_embeddings(deck_name, notes_to_index)

            duration = round(time.time() - start_time, 2)
            logger.info(
                "Successfully indexed %d new notes (total: %d) for deck '%s' in %.2fs",
                len(notes_to_index),
                total_notes,
                deck_name,
                duration,
            )

            return SyncDeckIndexResponse(
                deck_name=deck_name,
                total_notes=total_notes,
                newly_indexed=len(notes_to_index),
                duration_seconds=duration,
            )

    def _evaluate_cognitive_arbiter_heuristic(
        self,
        prerequisite: PrerequisiteItem,
        candidate_note: Dict,
        similarity: float,
    ) -> Tuple[PrerequisiteMatchStatus, str, str, float]:
        """Pedagogical cognitive arbitration using atomic heuristics (traps, breadcrumbs, answer length)."""
        front = candidate_note.get("front", "")
        back = candidate_note.get("back", "")
        explanation = candidate_note.get("explanation", "") or ""

        clean_front = _strip_html(front)
        clean_back = _strip_html(back)
        clean_exp = _strip_html(explanation).lower()

        # Check for hypercorrection protocol (trap detection)
        has_trap = (
            "trampa frecuente" in clean_exp
            or "error común" in clean_exp
            or "trampa" in clean_exp
            or "trampa frecuente" in clean_back.lower()
        )

        # Check breadcrumbs in front
        has_breadcrumb = clean_front.startswith("[") or " > " in clean_front

        # Check word length of back answer
        back_words = len(clean_back.split())

        # Strong coverage threshold calibrated across dense embeddings (>= 0.76)
        if similarity >= 0.76:
            # High quality atomic card: has trap protocol and concise answer (<= 25 words)
            if has_trap and back_words <= 25:
                return (
                    PrerequisiteMatchStatus.DOMINATED,
                    "Ya dominado en tu mazo con buena calidad (tarjeta atómica con protocolo de hipercorrección).",
                    "keep_existing",
                    round(min(1.0, similarity + 0.05), 2),
                )
            # Cognitive debt: covers concept but is too long or lacks trap protocol
            elif back_words > 25 or not has_trap or not has_breadcrumb:
                debt_reasons = []
                if back_words > 25:
                    debt_reasons.append(f"respuesta extensa ({back_words} palabras)")
                if not has_trap:
                    debt_reasons.append("sin protocolo de hipercorrección '⚠️ Trampa frecuente'")
                if not has_breadcrumb:
                    debt_reasons.append("sin jerarquía de contexto (breadcrumbs)")

                debt_desc = ", ".join(debt_reasons)
                return (
                    PrerequisiteMatchStatus.COGNITIVE_DEBT,
                    f"Detectado en mazo pero presenta deuda cognitiva ({debt_desc}). Se recomienda refactorizar o actualizar.",
                    "refactor_existing",
                    round(min(1.0, similarity), 2),
                )
            else:
                return (
                    PrerequisiteMatchStatus.COMPLEMENTARY,
                    "Cubre el concepto pero desde una perspectiva complementaria o alternativa.",
                    "study_complementary",
                    round(similarity, 2),
                )
        elif similarity >= 0.68:
            # 0.68 <= similarity < 0.76: Genuine topical proximity / complementary
            return (
                PrerequisiteMatchStatus.COMPLEMENTARY,
                "Proximidad semántica parcial detectada en tu mazo. Se recomienda añadir como concepto complementario.",
                "study_complementary",
                round(similarity, 2),
            )
        else:
            # Below 0.68: Background domain noise floor -> GAP
            return (
                PrerequisiteMatchStatus.GAP,
                "Concepto no detectado en tu mazo actual (similitud por debajo del umbral de confianza). Requiere creación.",
                "create_new",
                0.0,
            )

    async def _ensure_deck_indexed(self, deck_name: str, api_key: Optional[str] = None) -> int:
        """Helper to check indexing stats and trigger auto-sync under deck lock if empty or missing embeddings."""
        stats = self._store.get_deck_stats(deck_name)
        total_indexed = stats.get("total_indexed", 0)
        notes_with_emb = self._store.get_all_notes_with_embeddings(deck_name)
        if total_indexed == 0 or len(notes_with_emb) < total_indexed:
            try:
                sync_res = await self.sync_deck_index(deck_name, api_key=api_key)
                total_indexed = sync_res.total_notes
            except Exception as e:
                logger.warning("Automatic sync failed for deck '%s': %s", deck_name, e)
        return total_indexed

    async def _match_items_with_embeddings(
        self,
        deck_name: str,
        items: List[Any],
        embeddings: List[Optional[List[float]]],
        is_theme: bool = False,
        exclude_note_ids: Optional[List[int]] = None,
        api_key: Optional[str] = None,
        ai_provider: Optional[str] = None,
    ) -> List[PrerequisiteMatch]:
        """Match items against indexed notes using precomputed embeddings and semantic quality auditing."""
        item_candidates: List[List[Dict[str, Any]]] = []
        all_candidates_by_id: Dict[int, Dict[str, Any]] = {}

        for item, query_emb in zip(items, embeddings):
            if not query_emb:
                item_candidates.append([])
                continue

            try:
                candidates = self._store.semantic_search(
                    deck_name=deck_name,
                    query_embedding=query_emb,
                    top_k=3,
                    min_similarity=0.68,
                    exclude_note_ids=exclude_note_ids,
                )
            except Exception as err:
                logger.warning("Vector search error: %s", err)
                candidates = []

            item_candidates.append(candidates)
            for c in candidates:
                nid = int(c["note_id"])
                if nid not in all_candidates_by_id:
                    all_candidates_by_id[nid] = c

        # Check for unreviewed candidate notes that require semantic quality audit
        unreviewed = [
            c for c in all_candidates_by_id.values()
            if not c.get("quality_status") or c.get("quality_status") == "unreviewed"
        ]
        if unreviewed:
            try:
                audited = await self._semantic_auditor.audit_notes_batch(
                    notes=unreviewed,
                    deck_name=deck_name,
                    ai_provider=ai_provider,
                    api_key=api_key,
                )
                audited_by_id = {int(a["note_id"]): a for a in audited}
                for c in all_candidates_by_id.values():
                    nid = int(c["note_id"])
                    if nid in audited_by_id:
                        a_data = audited_by_id[nid]
                        c["quality_status"] = a_data.get("quality_status")
                        c["quality_score"] = a_data.get("quality_score")
                        c["quality_feedback"] = a_data.get("quality_feedback")
                        c["violation_type"] = a_data.get("violation_type")
            except Exception as audit_err:
                logger.warning("Batch auditing of unreviewed candidates failed: %s", audit_err)

        matches: List[PrerequisiteMatch] = []
        for item, candidates in zip(items, item_candidates):
            concept_name = (
                getattr(item, "concept", None)
                or getattr(item, "theme", None)
                or getattr(item, "title", "Concepto")
            )

            if not candidates:
                matches.append(
                    PrerequisiteMatch(
                        concept=concept_name,
                        status=PrerequisiteMatchStatus.GAP,
                        confidence=0.95,
                        matched_note_id=None,
                        matched_note_front=None,
                        similarity_score=0.0,
                        verdict_explanation=(
                            "Eje temático nuevo en tu mazo. Requiere creación."
                            if is_theme
                            else "Concepto no detectado en tu mazo actual. Requiere creación."
                        ),
                        suggested_action="create_new",
                    )
                )
                continue

            best = candidates[0]
            nid = int(best["note_id"])
            updated_c = all_candidates_by_id.get(nid, best)
            sim = float(updated_c.get("similarity", 0.0))
            matched_front = _strip_html(updated_c.get("front", ""))[:120]

            raw_note_text = (
                (updated_c.get("front") or "") + " " +
                (updated_c.get("back") or "") + " " +
                (updated_c.get("explanation") or "")
            )
            media_files = updated_c.get("media_files") or re.findall(
                r'<img[^>]+src=["\']([^"\']+)["\']', raw_note_text
            )

            q_status = updated_c.get("quality_status") or "unreviewed"
            if q_status in ("debt", "broken"):
                q_status = "bad"
            q_score = updated_c.get("quality_score")
            q_feedback = updated_c.get("quality_feedback") or ""
            v_type = updated_c.get("violation_type")

            conf = round(min(1.0, sim), 2)
            should_replace = False

            if sim >= 0.76:
                if q_status == "bad":
                    status = PrerequisiteMatchStatus.COGNITIVE_DEBT
                    suggested_action = "create_new"
                    should_replace = False
                    fb_part = f": {q_feedback}" if q_feedback else ""
                    verdict = f"Colisión con Nota #{nid} con deuda cognitiva{fb_part}. Se generarán tarjetas atómicas para este eje y se registrará en el ledger."
                elif q_status in ("optimal", "preevaluated"):
                    status = PrerequisiteMatchStatus.DOMINATED
                    suggested_action = "keep_existing"
                    should_replace = False
                    fb_part = f": {q_feedback}" if q_feedback else ""
                    verdict = f"Ya dominado en tu mazo con alta calidad atómica (Nota #{nid}){fb_part}"
                else:
                    status = PrerequisiteMatchStatus.COGNITIVE_DEBT
                    suggested_action = "create_new"
                    should_replace = False
                    verdict = f"Colisión semántica con Nota #{nid} (sin revisar). Se generarán tarjetas atómicas y se registrará en el ledger."
            elif 0.68 <= sim < 0.76:
                status = PrerequisiteMatchStatus.COMPLEMENTARY
                suggested_action = "study_complementary"
                should_replace = False
                verdict = f"Proximidad semántica parcial ({round(sim * 100)}%). Cubre una perspectiva complementaria."
            else:
                status = PrerequisiteMatchStatus.GAP
                suggested_action = "create_new"
                verdict = (
                    "Eje temático nuevo en tu mazo. Requiere creación."
                    if is_theme
                    else "Concepto no detectado en tu mazo actual. Requiere creación."
                )

            matches.append(
                PrerequisiteMatch(
                    concept=concept_name,
                    status=status,
                    confidence=conf,
                    matched_note_id=nid,
                    matched_note_front=matched_front,
                    similarity_score=sim,
                    verdict_explanation=verdict,
                    suggested_action=suggested_action,
                    media_files=media_files,
                    should_replace=should_replace,
                    quality_status=q_status,
                    quality_score=q_score,
                    quality_feedback=q_feedback,
                    violation_type=v_type,
                )
            )

        return matches

    async def match_prerequisites(
        self,
        deck_name: str,
        prerequisites: List[PrerequisiteItem],
        api_key: Optional[str] = None,
        exclude_note_ids: Optional[List[int]] = None,
    ) -> MatchPrerequisitesResponse:
        """Perform semantic search and cognitive arbitration for each prerequisite against the target deck."""
        logger.info(
            "Evaluating %d prerequisites against deck '%s'...",
            len(prerequisites),
            deck_name,
        )

        if not prerequisites:
            return MatchPrerequisitesResponse(
                deck_name=deck_name,
                matches=[],
                total_indexed_notes=0,
            )

        total_indexed = await self._ensure_deck_indexed(deck_name, api_key)

        if total_indexed == 0:
            return MatchPrerequisitesResponse(
                deck_name=deck_name,
                matches=[
                    PrerequisiteMatch(
                        concept=p.concept,
                        status=PrerequisiteMatchStatus.GAP,
                        confidence=0.95,
                        verdict_explanation="Mazo no indexado aún o sin notas. Requiere creación.",
                        suggested_action="create_new",
                    )
                    for p in prerequisites
                ],
                total_indexed_notes=0,
            )

        search_queries = [
            f"{p.concept}. {p.reason}. {p.search_query}".strip()
            for p in prerequisites
        ]
        try:
            query_embeddings = await self._embedding_port.embed_texts(search_queries)
        except Exception as err:
            logger.warning("Batch embedding for prerequisites failed: %s", err)
            query_embeddings = [None] * len(prerequisites)

        matches = await self._match_items_with_embeddings(
            deck_name=deck_name,
            items=prerequisites,
            embeddings=query_embeddings,
            is_theme=False,
            exclude_note_ids=exclude_note_ids,
            api_key=api_key,
        )

        return MatchPrerequisitesResponse(
            deck_name=deck_name,
            matches=matches,
            total_indexed_notes=total_indexed,
        )

    async def match_themes(
        self,
        deck_name: str,
        themes: List[CoreThemeItem],
        api_key: Optional[str] = None,
        exclude_note_ids: Optional[List[int]] = None,
    ) -> MatchThemesResponse:
        """Perform semantic search and cognitive arbitration for core themes against target deck."""
        logger.info(
            "Evaluating %d core themes against deck '%s'...",
            len(themes),
            deck_name,
        )

        if not themes:
            return MatchThemesResponse(
                deck_name=deck_name,
                matches=[],
                total_indexed_notes=0,
            )

        total_indexed = await self._ensure_deck_indexed(deck_name, api_key)

        if total_indexed == 0:
            return MatchThemesResponse(
                deck_name=deck_name,
                matches=[
                    PrerequisiteMatch(
                        concept=getattr(t, "theme", None) or t.title,
                        status=PrerequisiteMatchStatus.GAP,
                        confidence=0.95,
                        verdict_explanation="Eje temático nuevo en tu mazo. Requiere creación.",
                        suggested_action="create_new",
                    )
                    for t in themes
                ],
                total_indexed_notes=0,
            )

        theme_queries = [
            f"{getattr(t, 'theme', None) or t.title}. {t.description}".strip()
            for t in themes
        ]
        try:
            query_embeddings = await self._embedding_port.embed_texts(theme_queries)
        except Exception as err:
            logger.warning("Batch embedding for themes failed: %s", err)
            query_embeddings = [None] * len(themes)

        matches = await self._match_items_with_embeddings(
            deck_name=deck_name,
            items=themes,
            embeddings=query_embeddings,
            is_theme=True,
            exclude_note_ids=exclude_note_ids,
            api_key=api_key,
        )

        return MatchThemesResponse(
            deck_name=deck_name,
            matches=matches,
            total_indexed_notes=total_indexed,
        )

    async def match_study_plan(
        self,
        deck_name: str,
        prerequisites: List[PrerequisiteItem],
        themes: List[CoreThemeItem],
        api_key: Optional[str] = None,
        exclude_note_ids: Optional[List[int]] = None,
        source_note_id: Optional[int] = None,
    ) -> MatchStudyPlanResponse:
        """Unified matching of both prerequisites and core themes with a single batched embedding request and ledger memory."""
        logger.info(
            "Evaluating study plan for deck '%s': %d prerequisites, %d themes (source_note_id=%s)...",
            deck_name,
            len(prerequisites),
            len(themes),
            source_note_id,
        )

        active_source_id = source_note_id or (exclude_note_ids[0] if exclude_note_ids else None)
        ledger_entries: List[Dict[str, Any]] = []
        if active_source_id:
            try:
                ledger_entries = self._store.get_ledger_entries_for_note(deck_name, int(active_source_id))
            except Exception as le_err:
                logger.warning("Failed to retrieve ledger entries for note %s: %s", active_source_id, le_err)

        total_indexed = await self._ensure_deck_indexed(deck_name, api_key)

        prereq_queries = [
            f"{p.concept}. {p.reason}. {p.search_query}".strip()
            for p in prerequisites
        ]
        theme_queries = [
            f"{getattr(t, 'theme', None) or t.title}. {t.description}".strip()
            for t in themes
        ]
        all_queries = prereq_queries + theme_queries

        if not all_queries:
            return MatchStudyPlanResponse(
                deck_name=deck_name,
                prerequisite_matches=[],
                theme_matches=[],
                total_indexed_notes=total_indexed,
            )

        if total_indexed == 0:
            prereq_matches = [
                PrerequisiteMatch(
                    concept=p.concept,
                    status=PrerequisiteMatchStatus.GAP,
                    confidence=0.95,
                    verdict_explanation="Mazo no indexado aún o sin notas. Requiere creación.",
                    suggested_action="create_new",
                )
                for p in prerequisites
            ]
            theme_matches = [
                PrerequisiteMatch(
                    concept=getattr(t, "theme", None) or t.title,
                    status=PrerequisiteMatchStatus.GAP,
                    confidence=0.95,
                    verdict_explanation="Eje temático nuevo en tu mazo. Requiere creación.",
                    suggested_action="create_new",
                )
                for t in themes
            ]
        else:
            try:
                all_embeddings = await self._embedding_port.embed_texts(all_queries)
            except Exception as err:
                logger.warning("Batch embedding for study plan failed: %s", err)
                all_embeddings = [None] * len(all_queries)

            prereq_embeddings = all_embeddings[: len(prerequisites)]
            theme_embeddings = all_embeddings[len(prerequisites) :]

            prereq_matches = await self._match_items_with_embeddings(
                deck_name=deck_name,
                items=prerequisites,
                embeddings=prereq_embeddings,
                is_theme=False,
                exclude_note_ids=exclude_note_ids,
                api_key=api_key,
            )

            theme_matches = await self._match_items_with_embeddings(
                deck_name=deck_name,
                items=themes,
                embeddings=theme_embeddings,
                is_theme=True,
                exclude_note_ids=exclude_note_ids,
                api_key=api_key,
            )

        # Apply sanitation coverage ledger memory for themes covered in sibling turns
        if ledger_entries:
            for idx, tm in enumerate(theme_matches):
                tm_title = (tm.concept or "").strip().lower()
                for entry in ledger_entries:
                    covered_title = (entry.get("covered_concept_title") or "").strip().lower()
                    if covered_title and (covered_title == tm_title or covered_title in tm_title or tm_title in covered_title):
                        created_ids = entry.get("created_atomic_note_ids") or []
                        ids_str = ", ".join(f"#{cid}" for cid in created_ids) if created_ids else "tarjetas previas"
                        facet_part = f" ({entry.get('covered_facet_summary')})" if entry.get("covered_facet_summary") else ""
                        theme_matches[idx] = PrerequisiteMatch(
                            concept=tm.concept,
                            status=PrerequisiteMatchStatus.DOMINATED,
                            confidence=0.98,
                            matched_note_id=entry.get("source_sanitized_note_id"),
                            matched_note_front=f"Cubierto en turno de Nota #{entry.get('source_sanitized_note_id')}",
                            similarity_score=1.0,
                            verdict_explanation=(
                                f"Eje temático ya dominado y cubierto en el turno de la Nota #{entry.get('source_sanitized_note_id')}{facet_part}. "
                                f"Tarjetas atómicas generadas: {ids_str}."
                            ),
                            suggested_action="keep_existing",
                            should_replace=False,
                            quality_status="optimal",
                        )
                        break

        return MatchStudyPlanResponse(
            deck_name=deck_name,
            prerequisite_matches=prereq_matches,
            theme_matches=theme_matches,
            total_indexed_notes=total_indexed,
        )

    async def _call_ai_refactor(
        self,
        system_instruction: str,
        user_prompt: str,
        ai_provider: str = "gemini",
        local_model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke AI provider to generate structured JSON for refactoring."""
        # 1. Custom or Mock Card Generator override
        if self._card_generator and hasattr(self._card_generator, "refactor_card"):
            return await self._card_generator.refactor_card(
                system_instruction=system_instruction,
                user_prompt=user_prompt,
            )

        # 2. Local Ollama Provider
        if ai_provider.lower() == "ollama":
            import httpx
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": local_model or "qwen2.5:14b",
                "system": system_instruction,
                "prompt": user_prompt,
                "stream": False,
                "format": "json",
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_json = data.get("response", "{}")
                return json.loads(raw_json)

        # 3. Google Gemini Provider
        effective_key = api_key or settings.GEMINI_API_KEY
        if not effective_key:
            raise ValueError(
                "GEMINI_API_KEY no encontrada. Por favor configura tu clave o ingrésala en la aplicación."
            )

        client = genai.Client(
            api_key=effective_key,
            http_options=types.HttpOptions(timeout=60000),
        )
        tier_models = list(dict.fromkeys([settings.GEMINI_MODEL] + getattr(settings, "GEMINI_TIER_MODELS", [])))
        last_error = None
        for model_name in tier_models:
            try:
                logger.info("Calling Gemini tier '%s' for note refactoring...", model_name)
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=[user_prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )
                text = response.text or "{}"
                text = re.sub(r"^```(?:json)?\s*", "", text.strip())
                text = re.sub(r"\s*```$", "", text.strip())
                return json.loads(text)
            except Exception as e:
                msg = str(e).lower()
                logger.warning("Gemini tier '%s' failed for refactoring: %s", model_name, e)
                last_error = e
                if any(err_sig in msg for err_sig in ("503", "429", "unavailable", "high demand", "resource_exhausted")):
                    continue
                continue

        if last_error:
            raise last_error
        return {
            "diff_summary": "Reestructuración atómica aplicada.",
            "archetype": "Arquetipo C: Pregunta Atómica",
        }

    async def preview_refactor_note(
        self,
        note_id: int,
        concept_context: Optional[str] = None,
        deck_name: Optional[str] = None,
        ai_provider: str = "gemini",
        local_model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> RefactorNotePreviewResponse:
        """Generate an AI-driven atomic preview for a note with cognitive debt, preserving FSRS memory intervals."""
        logger.info("Generating refactor preview for note #%d...", note_id)

        # 1. Fetch note info from Anki Desktop
        notes_info = None
        if hasattr(self._anki_bridge, "get_notes_info"):
            notes_info = await self._anki_bridge.get_notes_info([note_id])
        elif hasattr(self._anki_bridge, "_invoke"):
            notes_info = await self._anki_bridge._invoke("notesInfo", notes=[note_id])

        if not notes_info:
            raise ValueError(f"No se encontró la nota #{note_id} en Anki Desktop.")

        note_data = notes_info[0]
        model_name = note_data.get("modelName", "Basic")
        resolved_deck_name = deck_name or note_data.get("deckName", "General")

        raw_fields = note_data.get("fields", {})
        original_fields: Dict[str, str] = {}
        for k, v in raw_fields.items():
            if isinstance(v, dict):
                original_fields[k] = v.get("value", "")
            else:
                original_fields[k] = str(v)

        # 2. Extract embedded images to ensure non-destructive preservation
        all_text = " ".join(original_fields.values())
        existing_images = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', all_text)

        # 3. Formulate prompts for Cognitive Refactoring
        system_instruction = (
            "Eres un docente experto en neurociencia del aprendizaje y algoritmos FSRS / SM-2. "
            "Tu tarea es refactorizar esta tarjeta de Anki con deuda cognitiva (extensa, ambigua o sin hipercorrección) "
            "para transformarla en una tarjeta atómica de retención máxima bajo el Principio de Información Mínima de Wozniak:\n"
            "1. Anverso (front): Pregunta atómica directa o Cloze prompt. "
            "Para tarjetas cloze, usa estrictamente {{c1::palabra}}.\n"
            "2. Reverso (back): Respuesta directa, concisa, máximo 15 palabras.\n"
            "3. Síntesis / Extra (explanation): Diagrama ASCII o tabla y OBLIGATORIAMENTE la sección '⚠️ Trampa frecuente / Error común:'. "
            "Preserva cualquier etiqueta de imagen <img src='...'> existente.\n"
            "4. Resumen de mejoras (diff_summary): 1-2 oraciones explicando qué deuda cognitiva se eliminó.\n"
            "5. Arquetipo cognitivo (archetype): Uno de: 'Arquetipo C: Pregunta Atómica', 'Arquetipo A: Cloze Contextualizado', "
            "'Arquetipo B: Matriz de Contraste', 'Arquetipo D: Tarjeta Radar'.\n\n"
            "Responde estrictamente en formato JSON con los campos:\n"
            "{\n"
            '  "breadcrumb": "...",\n'
            '  "front": "...",\n'
            '  "back": "...",\n'
            '  "explanation": "...",\n'
            '  "diff_summary": "...",\n'
            '  "archetype": "..."\n'
            "}"
        )

        user_prompt = (
            f"Por favor refactoriza la siguiente tarjeta de Anki (Modelo: '{model_name}'):\n\n"
            f"Campos actuales:\n"
            + "\n".join(f"- {k}: {v}" for k, v in original_fields.items())
            + (f"\n\nContexto pedagógico: {concept_context}" if concept_context else "")
            + (f"\n\nImágenes embebidas a preservar: {', '.join(existing_images)}" if existing_images else "")
        )

        ai_res = await self._call_ai_refactor(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            ai_provider=ai_provider,
            local_model=local_model,
            api_key=api_key,
        )

        # 4. Non-destructive image preservation
        explanation = ai_res.get("explanation", "")
        for img in existing_images:
            img_tag = f'<img src="{img}">'
            if img not in explanation and img not in ai_res.get("back", "") and img not in ai_res.get("front", ""):
                explanation = f"{explanation}\n\n{img_tag}".strip()

        # 5. Intelligently map refactored content to the actual fields of the note's model
        refactored_fields = dict(original_fields)
        field_names = list(original_fields.keys())

        has_breadcrumb = any(f.lower() == "breadcrumb" for f in field_names)
        breadcrumb_val = ai_res.get("breadcrumb", "") or (concept_context or "")
        raw_front = ai_res.get("front", "")

        f_field = next((f for f in field_names if f.lower() in ("front", "text", "pregunta", "titulo")), None)
        if has_breadcrumb:
            b_field = next(f for f in field_names if f.lower() == "breadcrumb")
            refactored_fields[b_field] = breadcrumb_val
            clean_front = re.sub(r"^\[.*?\]\s*", "", raw_front).strip()
            if f_field:
                refactored_fields[f_field] = clean_front
        else:
            if f_field:
                if breadcrumb_val and not raw_front.startswith("["):
                    refactored_fields[f_field] = f"[{breadcrumb_val}] {raw_front}".strip()
                else:
                    refactored_fields[f_field] = raw_front

        raw_back = ai_res.get("back", "")
        b_back_field = next((f for f in field_names if f.lower() in ("back", "respuesta", "respuestas", "back extra")), None)
        if b_back_field:
            refactored_fields[b_back_field] = raw_back

        has_tip = any(f.lower() == "tip" for f in field_names)
        has_extra = any(f.lower() == "extra" for f in field_names)

        if has_tip and has_extra:
            tip_field = next(f for f in field_names if f.lower() == "tip")
            extra_field = next(f for f in field_names if f.lower() == "extra")
            refactored_fields[tip_field] = explanation
            refactored_fields[extra_field] = ""
        elif has_extra:
            extra_field = next(f for f in field_names if f.lower() == "extra")
            refactored_fields[extra_field] = explanation
        elif has_tip:
            tip_field = next(f for f in field_names if f.lower() == "tip")
            refactored_fields[tip_field] = explanation
        elif not has_extra and not has_tip and b_back_field:
            if explanation:
                refactored_fields[b_back_field] = f"{raw_back}<br><br><small>{explanation}</small>"

        return RefactorNotePreviewResponse(
            note_id=note_id,
            deck_name=resolved_deck_name,
            model_name=model_name,
            original_fields=original_fields,
            refactored_fields=refactored_fields,
            diff_summary=ai_res.get(
                "diff_summary",
                "Reestructuración atómica bajo el Principio de Información Mínima con trampa diagnóstica."
            ),
            cognitive_archetype=ai_res.get("archetype", "Arquetipo C: Pregunta Atómica"),
        )

    async def apply_refactor_note(
        self,
        note_id: int,
        deck_name: str,
        fields: Dict[str, str],
        api_key: Optional[str] = None,
    ) -> ApplyRefactorResponse:
        """Update note fields in Anki Desktop in-place and re-index updated embedding in SQLite."""
        logger.info("Applying in-place refactor for note #%d in deck '%s'...", note_id, deck_name)
        success = await self._anki_bridge.update_note_fields(note_id, fields)
        if not success:
            return ApplyRefactorResponse(
                success=False,
                note_id=note_id,
                message=f"Fallo al actualizar los campos de la nota #{note_id} en Anki Desktop.",
            )

        # Re-compute and update embedding in SQLite store
        try:
            front_val = fields.get("Front") or fields.get("front") or fields.get("Text") or fields.get("Titulo") or ""
            back_val = fields.get("Back") or fields.get("back") or fields.get("respuesta") or fields.get("respuestas") or ""
            exp_val = fields.get("Extra") or fields.get("Tip") or fields.get("explanation") or ""
            clean_text = f"{_strip_html(front_val)} | {_strip_html(back_val)}".strip()

            embedding = await self._embedding_port.embed_single(clean_text)
            updated_note = {
                "note_id": note_id,
                "front": front_val,
                "back": back_val,
                "explanation": exp_val,
                "clean_text": clean_text,
                "embedding": embedding,
            }
            self._store.save_note_embeddings(deck_name, [updated_note])
            logger.info("Updated embedding for note #%d in deck '%s'.", note_id, deck_name)
        except Exception as store_err:
            logger.warning("Could not re-index note #%d in SQLite store: %s", note_id, store_err)

        return ApplyRefactorResponse(
            success=True,
            note_id=note_id,
            message=f"Nota #{note_id} refactorizada con éxito en Anki preservando su historial FSRS.",
        )

    async def _call_ai_topic_audit(
        self,
        system_instruction: str,
        user_prompt: str,
        ai_provider: str = "gemini",
        local_model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke AI provider to generate structured JSON for thematic coverage audit."""
        # 1. Custom or Mock Card Generator override
        if self._card_generator and hasattr(self._card_generator, "audit_topic_coverage"):
            return await self._card_generator.audit_topic_coverage(
                system_instruction=system_instruction,
                user_prompt=user_prompt,
            )

        # 2. Local Ollama Provider
        if ai_provider.lower() == "ollama":
            import httpx

            url = "http://localhost:11434/api/generate"
            payload = {
                "model": local_model or "qwen2.5:14b",
                "system": system_instruction,
                "prompt": user_prompt,
                "stream": False,
                "format": "json",
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_json = data.get("response", "{}")
                return json.loads(raw_json)

        # 3. Google Gemini Provider with Tiered Fallback
        effective_key = api_key or settings.GEMINI_API_KEY
        if not effective_key:
            raise ValueError(
                "GEMINI_API_KEY no encontrada. Por favor configura tu clave o ingrésala en la aplicación."
            )

        client = genai.Client(
            api_key=effective_key,
            http_options=types.HttpOptions(timeout=60000),
        )
        tier_models = list(dict.fromkeys([settings.GEMINI_MODEL] + getattr(settings, "GEMINI_TIER_MODELS", [])))
        last_error = None
        for model_name in tier_models:
            try:
                logger.info("Calling Gemini tier '%s' for topic coverage audit...", model_name)
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=[user_prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )
                text = response.text or "{}"
                text = re.sub(r"^```(?:json)?\s*", "", text.strip())
                text = re.sub(r"\s*```$", "", text.strip())
                return json.loads(text)
            except Exception as e:
                msg = str(e).lower()
                logger.warning("Gemini tier '%s' failed for topic audit: %s", model_name, e)
                last_error = e
                if any(err_sig in msg for err_sig in ("503", "429", "unavailable", "high demand", "resource_exhausted")):
                    continue
                continue

        # Secondary fallback: local Ollama
        try:
            logger.info("Gemini tiers exhausted. Attempting fallback to local Ollama for topic audit...")
            import httpx

            url = "http://localhost:11434/api/generate"
            payload = {
                "model": local_model or "qwen2.5:14b",
                "system": system_instruction,
                "prompt": user_prompt,
                "stream": False,
                "format": "json",
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_json = data.get("response", "{}")
                    return json.loads(raw_json)
        except Exception as ollama_err:
            logger.warning("Ollama fallback failed for topic audit: %s", ollama_err)

        if last_error:
            raise last_error

        return {
            "coverage_percentage": 0,
            "summary_assessment": "No se pudo completar el análisis de cobertura temática.",
            "covered_facets": [],
            "orphan_gaps": [],
        }

    async def audit_topic_coverage(
        self,
        deck_name: str,
        topic: str,
        description: Optional[str] = None,
        top_k: int = 10,
        save_audit: bool = True,
        api_key: Optional[str] = None,
    ) -> TopicCoverageAuditResponse:
        """Perform a pedagogical thematic audit over an Anki deck comparing against target domain topic."""
        logger.info("Auditing topic coverage for '%s' in deck '%s'...", topic, deck_name)
        await self._ensure_deck_indexed(deck_name, api_key)

        query = f"{topic}. {description or ''}".strip()
        candidates = []
        try:
            query_emb = await self._embedding_port.embed_single(query)
            if query_emb:
                candidates = self._store.semantic_search(
                    deck_name=deck_name,
                    query_embedding=query_emb,
                    top_k=top_k,
                    min_similarity=0.65,
                )
        except Exception as err:
            logger.warning("Vector search error during topic audit for '%s': %s", topic, err)
            candidates = []

        system_instruction = (
            "Eres un docente experto en neurociencia del aprendizaje, diseño curricular y algoritmos FSRS/Anki. "
            "Tu tarea es realizar una auditoría temática exhaustiva para determinar qué tan cubierto está un tema "
            "o eje curricular en el mazo de Anki del usuario a partir de las notas encontradas.\n\n"
            "Instrucciones de auditoría:\n"
            "1. Evalúa qué facetas o subconceptos esenciales del tema YA están cubiertos adecuadamente por las tarjetas analizadas.\n"
            "2. Identifica con precisión qué vacíos huérfanos ('orphan gaps') o lagunas críticas faltan por cubrir para alcanzar dominio completo.\n"
            "3. Para cada vacío huérfano, define prioridad ('high', 'medium', 'low') y un 'suggested_front' con jerarquía de contexto (ej: '[Tema > Subtema] ¿Cuál es el mecanismo...?').\n"
            "4. Asigna un porcentaje de cobertura entero (0 a 100) y un resumen pedagógico ('summary_assessment').\n\n"
            "Responde estrictamente en formato JSON válido con la siguiente estructura:\n"
            "{\n"
            '  "coverage_percentage": 75,\n'
            '  "summary_assessment": "...",\n'
            '  "covered_facets": [\n'
            '    {\n'
            '      "facet": "Nombre de la faceta cubierta",\n'
            '      "description": "Explicación de qué aspectos cubre la tarjeta",\n'
            '      "matched_note_ids": [101],\n'
            '      "quality_score": 1.0\n'
            '    }\n'
            '  ],\n'
            '  "orphan_gaps": [\n'
            '    {\n'
            '      "gap_title": "Nombre del concepto o laguna faltante",\n'
            '      "reason": "Por qué es necesario para evitar confusión o lagunas",\n'
            '      "priority": "high",\n'
            '      "suggested_front": "[Tema > Subtema] Pregunta atómica..."\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        candidates_text = (
            "\n\n".join(
                [
                    f"Nota #{c['note_id']} (Similitud: {c.get('similarity', 0.0)}):\n"
                    f"- Anverso: {_strip_html(c.get('front', ''))}\n"
                    f"- Reverso: {_strip_html(c.get('back', ''))}\n"
                    f"- Extra: {_strip_html(c.get('explanation', '') or '')}\n"
                    f"- Tags: {', '.join(c.get('tags', [])) if isinstance(c.get('tags'), list) else c.get('tags')}"
                    for c in candidates
                ]
            )
            if candidates
            else "No se encontraron notas existentes coincidentes en el mazo."
        )

        user_prompt = (
            f"Tema objetivo a auditar: {topic}\n"
            f"Descripción o alcance pedagógico: {description or 'Cobertura completa del tema'}\n\n"
            f"Tarjetas existentes encontradas en el mazo ({len(candidates)} notas):\n\n"
            f"{candidates_text}\n\n"
            "Por favor realiza la auditoría de cobertura temática y genera el JSON estricto."
        )

        ai_res = await self._call_ai_topic_audit(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            api_key=api_key,
        )

        raw_percentage = ai_res.get("coverage_percentage", 0)
        try:
            coverage_percentage = max(0, min(100, int(raw_percentage)))
        except Exception:
            coverage_percentage = 0

        summary_assessment = str(ai_res.get("summary_assessment", ""))

        covered_facets: List[CoveredFacet] = []
        for f in ai_res.get("covered_facets", []):
            try:
                matched_nids = [int(nid) for nid in f.get("matched_note_ids", [])]
            except Exception:
                matched_nids = []
            try:
                q_score = float(f.get("quality_score", 1.0))
            except Exception:
                q_score = 1.0

            covered_facets.append(
                CoveredFacet(
                    facet=str(f.get("facet", "Faceta")),
                    description=str(f.get("description", "")),
                    matched_note_ids=matched_nids,
                    quality_score=q_score,
                )
            )

        orphan_gaps: List[OrphanGap] = []
        for g in ai_res.get("orphan_gaps", []):
            orphan_gaps.append(
                OrphanGap(
                    gap_title=str(g.get("gap_title", "Laguna temática")),
                    reason=str(g.get("reason", "")),
                    priority=str(g.get("priority", "high")),
                    suggested_front=g.get("suggested_front"),
                    status=CoverageGapStatus.PENDING,
                    generated_note_id=None,
                )
            )

        created_at = datetime.now(timezone.utc).isoformat()
        audit_id = None
        if save_audit:
            audit_id = self._store.save_coverage_audit(
                deck_name=deck_name,
                topic=topic,
                description=description,
                coverage_percentage=coverage_percentage,
                covered_facets=[f.model_dump() for f in covered_facets],
                orphan_gaps=[g.model_dump() for g in orphan_gaps],
                summary_assessment=summary_assessment,
            )

        return TopicCoverageAuditResponse(
            audit_id=audit_id,
            deck_name=deck_name,
            topic=topic,
            coverage_percentage=coverage_percentage,
            covered_facets=covered_facets,
            orphan_gaps=orphan_gaps,
            summary_assessment=summary_assessment,
            created_at=created_at,
        )

    async def list_coverage_audits(self, deck_name: str) -> ListDeckAuditsResponse:
        """List all historical thematic coverage audits for a deck."""
        audits_raw = self._store.list_coverage_audits(deck_name)
        summaries: List[DeckAuditSummary] = []
        for a in audits_raw:
            gaps = a.get("orphan_gaps") or []
            pending_count = sum(
                1
                for g in gaps
                if (g.get("status") if isinstance(g, dict) else getattr(g, "status", None))
                in (CoverageGapStatus.PENDING.value, "pending")
            )
            summaries.append(
                DeckAuditSummary(
                    id=a["id"],
                    topic=a["topic"],
                    coverage_percentage=a.get("coverage_percentage", 0),
                    total_facets=len(a.get("covered_facets") or []),
                    total_gaps=len(gaps),
                    pending_gaps=pending_count,
                    created_at=a.get("created_at") or "",
                )
            )
        return ListDeckAuditsResponse(deck_name=deck_name, audits=summaries)

    async def get_coverage_audit(self, audit_id: int) -> Optional[TopicCoverageAuditResponse]:
        """Retrieve full details of a specific coverage audit by ID."""
        row = self._store.get_coverage_audit(audit_id)
        if not row:
            return None

        facets = [
            CoveredFacet(
                facet=f.get("facet", "Faceta"),
                description=f.get("description", ""),
                matched_note_ids=f.get("matched_note_ids", []),
                quality_score=float(f.get("quality_score", 1.0)),
            )
            for f in (row.get("covered_facets") or [])
        ]

        gaps = [
            OrphanGap(
                gap_title=g.get("gap_title", ""),
                reason=g.get("reason", ""),
                priority=g.get("priority", "high"),
                suggested_front=g.get("suggested_front"),
                status=CoverageGapStatus(g.get("status", "pending"))
                if g.get("status") in CoverageGapStatus._value2member_map_
                else CoverageGapStatus.PENDING,
                generated_note_id=g.get("generated_note_id"),
            )
            for g in (row.get("orphan_gaps") or [])
        ]

        return TopicCoverageAuditResponse(
            audit_id=row["id"],
            deck_name=row["deck_name"],
            topic=row["topic"],
            coverage_percentage=row.get("coverage_percentage", 0),
            covered_facets=facets,
            orphan_gaps=gaps,
            summary_assessment=row.get("summary_assessment") or "",
            created_at=row.get("created_at") or "",
        )

    async def update_gap_status(
        self,
        audit_id: int,
        gap_index: int,
        status: CoverageGapStatus,
        generated_note_id: Optional[int] = None,
    ) -> bool:
        """Update resolution status and optional linked note ID of an orphan gap."""
        status_val = status.value if hasattr(status, "value") else str(status)
        return self._store.update_gap_status(
            audit_id=audit_id,
            gap_index=gap_index,
            status=status_val,
            generated_note_id=generated_note_id,
        )

    async def _label_cluster_with_llm(
        self,
        medoid_notes: List[Dict],
        api_key: Optional[str] = None,
        ai_provider: Optional[str] = None,
        local_model: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Prompt LLM to extract a concise Thematic Family title and pedagogical scope."""
        cards_text = "\n".join([
            f"- Pregunta: {_strip_html(n.get('front', ''))[:100]} | Respuesta: {_strip_html(n.get('back', ''))[:80]}"
            for n in medoid_notes[:5]
        ])

        system_instruction = (
            "Eres un Arquitecto Principal de Currículo Cognitivo y Ciencias del Aprendizaje. "
            "Tu tarea es analizar tarjetas representativas de un cluster conceptual y nombrar su Eje Temático."
        )
        user_prompt = f"""Analiza las siguientes tarjetas representativas de un cluster conceptual:
{cards_text}

Genera un título temático preciso para este grupo y su alcance pedagógico.
REGLAS ESTRICTAS:
1. El título ('thematic_family') DEBE SER CONCISO: de 2 a 4 palabras como máximo (ejemplos: 'Modelos de Despliegue Cloud', 'Arquitectura de Agentes IA', 'Optimización de Costos y FinOps').
2. NUNCA uses nombres genéricos como 'General', 'Varios', 'Conceptos' o 'Repetición Espaciada'.
3. Responde ESTRICTAMENTE en formato JSON con la siguiente estructura:
{{
  "thematic_family": "Título conciso (máximo 4 palabras en español)",
  "pedagogical_scope": "Una sola oración en español resumiendo el alcance conceptual de este eje."
}}"""

        effective_provider = (ai_provider or "gemini").lower()

        # 1. Local Ollama if explicitly requested
        if effective_provider in ("ollama", "local"):
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(
                        "http://127.0.0.1:11434/api/generate",
                        json={
                            "model": local_model or "qwen2.5:14b",
                            "system": system_instruction,
                            "prompt": user_prompt,
                            "stream": False,
                            "format": "json",
                            "options": {"temperature": 0.2, "num_predict": 256},
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        parsed = json.loads(data.get("response", "{}"))
                        title = parsed.get("thematic_family") or parsed.get("title") or "Eje Temático"
                        scope = parsed.get("pedagogical_scope") or parsed.get("scope") or "Eje conceptual descubierto."
                        return title.strip(), scope.strip()
            except Exception as err:
                logger.warning("Local Ollama cluster labeling failed: %s", err)

        # 2. Gemini API with Tiered Fallback
        effective_key = api_key or settings.GEMINI_API_KEY
        if effective_key:
            try:
                client = genai.Client(
                    api_key=effective_key,
                    http_options=types.HttpOptions(timeout=30000),
                )
                tier_models = list(
                    dict.fromkeys(
                        ["gemini-2.5-flash", settings.GEMINI_MODEL, settings.GEMINI_FALLBACK_MODEL]
                        + getattr(settings, "GEMINI_TIER_MODELS", [])
                    )
                )
                for m_name in tier_models:
                    try:
                        res = await asyncio.to_thread(
                            client.models.generate_content,
                            model=m_name,
                            contents=[user_prompt],
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction,
                                response_mime_type="application/json",
                                temperature=0.2,
                            ),
                        )
                        text = res.text or "{}"
                        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
                        text = re.sub(r"\s*```$", "", text.strip())
                        parsed = json.loads(text)
                        title = parsed.get("thematic_family") or parsed.get("title") or "Eje Temático"
                        scope = parsed.get("pedagogical_scope") or parsed.get("scope") or "Eje conceptual descubierto."
                        return title.strip(), scope.strip()
                    except Exception as tier_err:
                        logger.debug("Gemini tier '%s' failed for cluster label: %s", m_name, tier_err)
                        continue
            except Exception as e:
                logger.warning("Gemini cluster labeling error: %s", e)

        # 3. Secondary fallback to Ollama
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "http://127.0.0.1:11434/api/generate",
                    json={
                        "model": local_model or "qwen2.5:14b",
                        "system": system_instruction,
                        "prompt": user_prompt,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0.2, "num_predict": 256},
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    parsed = json.loads(data.get("response", "{}"))
                    title = parsed.get("thematic_family") or parsed.get("title") or "Eje Temático"
                    scope = parsed.get("pedagogical_scope") or parsed.get("scope") or "Eje conceptual descubierto."
                    return title.strip(), scope.strip()
        except Exception:
            pass

        # 4. Deterministic fallback from top front card
        if medoid_notes:
            first_front = _strip_html(medoid_notes[0].get("front", ""))
            first_words = " ".join(first_front.split()[:3])
            return f"Eje: {first_words}" if first_words else "Eje Temático", "Familia conceptual agrupada semánticamente."
        return "Eje Temático", "Familia conceptual descubierta."

    async def discover_and_apply_semantic_clusters(
        self,
        deck_name: str,
        force_refresh: bool = False,
        api_key: Optional[str] = None,
        ai_provider: Optional[str] = None,
        local_model: Optional[str] = None,
        k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Discover unsupervised semantic clusters from vector embeddings and persist thematic families."""
        await self._ensure_deck_indexed(deck_name, api_key)

        if not force_refresh:
            existing = self._store.get_deck_clusters(deck_name)
            if existing:
                notes_with_emb = self._store.get_all_notes_with_embeddings(deck_name)
                total_clustered = sum(len(c.get("note_ids", [])) for c in existing)
                if abs(total_clustered - len(notes_with_emb)) <= 3:
                    return existing

        notes_with_emb = self._store.get_all_notes_with_embeddings(deck_name)
        if not notes_with_emb:
            return []

        cluster_items = [{"note_id": n["note_id"], "vec": n["embedding"]} for n in notes_with_emb]
        kmeans_result = spherical_kmeans(cluster_items, k=k)

        notes_by_id = {n["note_id"]: n for n in notes_with_emb}
        clusters_to_save: List[Dict[str, Any]] = []

        for cl in kmeans_result.clusters:
            medoids = [notes_by_id[nid] for nid in cl.representative_note_ids if nid in notes_by_id]
            title, scope = await self._label_cluster_with_llm(
                medoids,
                api_key=api_key,
                ai_provider=ai_provider,
                local_model=local_model,
            )
            clusters_to_save.append({
                "cluster_index": cl.cluster_index,
                "title": title,
                "scope": scope,
                "note_ids": cl.note_ids,
                "centroid_note_ids": cl.representative_note_ids,
            })

        self._store.save_deck_clusters(deck_name, clusters_to_save)
        logger.info(
            "Successfully discovered and saved %d semantic clusters for deck '%s'.",
            len(clusters_to_save),
            deck_name,
        )
        return clusters_to_save

    def _extract_category_for_note(self, note: Dict) -> str:
        """Extract primary categorization from note breadcrumbs, clusters, or tags."""
        front = note.get("front", "") or ""
        clean_f = _strip_html(front).strip()

        # 1. Breadcrumbs in front: [Category > Subcategory] or [Category]
        bc_match = re.match(r"^\[\s*([^>\]]+?)(?:\s*>|\])", clean_f)
        if bc_match:
            cat = bc_match.group(1).strip()
            if cat and cat.lower() != "general":
                return cat

        # 2. Discovered semantic cluster label
        cluster_name = note.get("cluster_name")
        if cluster_name and cluster_name.strip():
            c_clean = cluster_name.strip()
            if c_clean.lower() != "general":
                return c_clean

        # 3. First tag
        tags = note.get("tags", [])
        if isinstance(tags, list) and tags:
            first_tag = str(tags[0]).strip()
            if first_tag and first_tag.lower() != "general":
                return first_tag

        return "General"

    def _evaluate_note_health(self, note: Dict) -> str:
        """Evaluate note health based on persistent quality status.

        Canonical states:
        - 'unreviewed' (gray): Legacy or uninspected cards.
        - 'bad' (red): Monolith, slide dump, ambiguous, broken or non-atomic notes.
        - 'preevaluated' (cyan): System-generated atomic cards.
        - 'optimal' (green): Verified high pedagogical quality.
        """
        status = note.get("quality_status")
        if status in ("debt", "broken"):
            return "bad"
        if status in ("unreviewed", "bad", "preevaluated", "optimal"):
            return status
        return "unreviewed"

    async def get_deck_coverage_map(
        self, deck_name: str, api_key: Optional[str] = None
    ) -> DeckCoverageMapResponse:
        """Construct a hierarchical DAG coverage map with honest quality classification and orphan gaps."""
        await self._ensure_deck_indexed(deck_name, api_key)
        notes = self._store.get_all_indexed_notes(deck_name)

        # Auto-discover clusters if not present and deck has enough notes
        existing_clusters = self._store.get_deck_clusters(deck_name)
        if not existing_clusters and len(notes) >= 3:
            try:
                await self.discover_and_apply_semantic_clusters(deck_name, api_key=api_key)
                notes = self._store.get_all_indexed_notes(deck_name)
            except Exception as cl_err:
                logger.warning("Auto-discovery of semantic clusters failed for '%s': %s", deck_name, cl_err)

        root_id = f"deck:{deck_name}"
        nodes: List[DeckCoverageMapNode] = []
        edges: List[DeckCoverageMapEdge] = []

        # Group notes by extracted cluster
        clusters: Dict[str, List[Dict]] = {}
        for n in notes:
            cat = self._extract_category_for_note(n)
            clusters.setdefault(cat, []).append(n)

        # Retrieve pending orphan gaps from coverage audits
        audits = self._store.list_coverage_audits(deck_name)
        cluster_gaps: Dict[str, List[Tuple[int, int, Dict]]] = {}
        for audit in audits:
            audit_id = audit["id"]
            topic = audit.get("topic", "General")
            target_cluster = next((c for c in clusters if c.lower() == topic.lower()), topic)
            for idx, gap in enumerate(audit.get("orphan_gaps") or []):
                gap_status = gap.get("status") if isinstance(gap, dict) else getattr(gap, "status", None)
                if gap_status in (CoverageGapStatus.PENDING.value, "pending"):
                    cluster_gaps.setdefault(target_cluster, []).append((audit_id, idx, gap))

        # Also include registered orphan concepts discovered during material inspection or blueprint alignment
        # that have 0 target cards mapped
        registered_concepts = self._store.get_deck_concepts(deck_name)
        card_mappings = self._store.get_card_concept_mappings(deck_name)
        mapped_concept_ids = {m["concept_id"] for m in card_mappings if m.get("role") == "target"}
        existing_gap_names = {
            gap.get("gap_title", "").lower().strip()
            for gaps in cluster_gaps.values()
            for _, _, gap in gaps
        }

        for c_idx, concept in enumerate(registered_concepts):
            cid = concept.get("id") or f"c_{c_idx}"
            cname = concept.get("name") or cid
            if cid not in mapped_concept_ids and cname.lower().strip() not in existing_gap_names:
                tax = concept.get("taxonomy_path") or "General"
                target_cluster = next(
                    (c for c in clusters if c.lower() == tax.lower()),
                    tax if tax.lower() != "general" else "General"
                )
                gap_dict = {
                    "gap_title": cname,
                    "reason": concept.get("description") or "Concepto prerrequisito huérfano detectado en diagnóstico",
                    "status": "pending",
                    "concept_id": cid,
                }
                cluster_gaps.setdefault(target_cluster, []).append((0, c_idx + 1000, gap_dict))
                existing_gap_names.add(cname.lower().strip())

        # Ensure all clusters are registered
        all_cluster_names = sorted(list(set(list(clusters.keys()) + list(cluster_gaps.keys()))))

        optimal_count = 0
        preevaluated_count = 0
        bad_count = 0
        gap_count = 0
        unreviewed_count = 0

        # Build Cluster nodes and their connected children (Notes and Gaps)
        for cat_name in all_cluster_names:
            cluster_id = f"cluster:{cat_name}"
            cat_notes = clusters.get(cat_name, [])
            cat_gaps = cluster_gaps.get(cat_name, [])

            cluster_has_gap = len(cat_gaps) > 0
            cluster_has_bad = False
            cluster_has_optimal = False
            cluster_has_preevaluated = False
            cluster_has_unreviewed = False

            # Notes
            for n in cat_notes:
                health = self._evaluate_note_health(n)
                if health == "optimal":
                    optimal_count += 1
                    cluster_has_optimal = True
                elif health == "preevaluated":
                    preevaluated_count += 1
                    cluster_has_preevaluated = True
                elif health == "bad":
                    bad_count += 1
                    cluster_has_bad = True
                else:
                    unreviewed_count += 1
                    cluster_has_unreviewed = True

                clean_front = _strip_html(n.get("front", ""))
                clean_back = _strip_html(n.get("back", ""))
                if not clean_front.strip():
                    clean_front = f"Nota #{n['note_id']} [Contenido Visual / Sin Texto]"
                label = clean_front[:60] + ("..." if len(clean_front) > 60 else "")
                note_node_id = f"note:{n['note_id']}"

                clean_back_preview = clean_back[:80] + "..." if len(clean_back) > 80 else clean_back
                if not clean_back_preview.strip():
                    clean_back_preview = "[Contenido Visual / Multimedia]"
                details_text = f"Reverso: {clean_back_preview}"
                if n.get("quality_feedback"):
                    details_text += f"\nEvaluación: {n['quality_feedback']}"

                nodes.append(
                    DeckCoverageMapNode(
                        id=note_node_id,
                        label=label,
                        type="note",
                        health=health,
                        note_id=int(n["note_id"]),
                        details=details_text,
                        quality_score=n.get("quality_score"),
                        quality_feedback=n.get("quality_feedback"),
                    )
                )
                edges.append(
                    DeckCoverageMapEdge(
                        source=cluster_id,
                        target=note_node_id,
                    )
                )

            # Gaps
            for audit_id, idx, gap in cat_gaps:
                gap_count += 1
                gap_node_id = f"gap:{audit_id}_{idx}"
                gap_title = gap.get("gap_title", "Laguna temática")
                nodes.append(
                    DeckCoverageMapNode(
                        id=gap_node_id,
                        label=gap_title,
                        type="gap",
                        health="gap",
                        details=gap.get("reason", ""),
                    )
                )
                edges.append(
                    DeckCoverageMapEdge(
                        source=cluster_id,
                        target=gap_node_id,
                    )
                )

            # Determine cluster health
            if cluster_has_gap:
                c_health = "gap"
            elif cluster_has_bad:
                c_health = "bad"
            elif cluster_has_optimal:
                c_health = "optimal"
            elif cluster_has_preevaluated:
                c_health = "preevaluated"
            else:
                c_health = "unreviewed"

            nodes.append(
                DeckCoverageMapNode(
                    id=cluster_id,
                    label=cat_name,
                    type="cluster",
                    health=c_health,
                )
            )
            edges.append(
                DeckCoverageMapEdge(
                    source=root_id,
                    target=cluster_id,
                )
            )

        audited_count = optimal_count + preevaluated_count + bad_count
        deck_health_percentage = (
            round(((optimal_count + preevaluated_count) / audited_count) * 100, 1) if audited_count > 0 else 0.0
        )

        # Deck Root Node Health
        if gap_count > 0:
            root_health = "gap"
        elif bad_count > 0:
            root_health = "bad"
        elif optimal_count > 0:
            root_health = "optimal"
        elif preevaluated_count > 0:
            root_health = "preevaluated"
        else:
            root_health = "unreviewed"

        root_node = DeckCoverageMapNode(
            id=root_id,
            label=deck_name,
            type="deck",
            health=root_health,
        )
        nodes.insert(0, root_node)

        return DeckCoverageMapResponse(
            deck_name=deck_name,
            total_nodes=len(nodes),
            nodes=nodes,
            edges=edges,
            optimal_count=optimal_count,
            preevaluated_count=preevaluated_count,
            bad_count=bad_count,
            debt_count=bad_count,
            gap_count=gap_count,
            unreviewed_count=unreviewed_count,
            broken_count=0,
            audited_count=audited_count,
            deck_health_percentage=deck_health_percentage,
        )

    async def audit_quality_batch(
        self,
        deck_name: str,
        batch_size: int = 5,
        note_ids: Optional[List[int]] = None,
        api_key: Optional[str] = None,
        ai_provider: Optional[str] = None,
        local_model: Optional[str] = None,
    ) -> AuditQualityBatchResponse:
        """Audit a micro-batch of flashcards against strict neurocognitive learning laws."""
        await self._ensure_deck_indexed(deck_name, api_key)
        notes_to_audit = self._store.get_notes_for_audit(deck_name, limit=batch_size, note_ids=note_ids)
        if not notes_to_audit:
            stats = self._store.get_deck_stats(deck_name)
            return AuditQualityBatchResponse(
                deck_name=deck_name,
                batch_size=batch_size,
                audited_count=0,
                items=[],
                deck_stats=stats,
            )

        audited_results = await self._semantic_auditor.audit_notes_batch(
            notes=notes_to_audit,
            deck_name=deck_name,
            ai_provider=ai_provider,
            api_key=api_key,
            local_model=local_model,
        )

        audit_items: List[NoteQualityAuditItem] = []
        for aud, note in zip(audited_results, notes_to_audit):
            nid = aud["note_id"]
            front = note.get("front", "") or ""
            back = note.get("back", "") or ""
            q_status = aud.get("quality_status", "optimal")
            q_score = float(aud.get("quality_score", 0.5))
            v_type = aud.get("violation_type")
            feedback = aud.get("quality_feedback", "Evaluación cognitiva completada.")
            sisters = aud.get("atomic_sister_cards_recommended", [])

            audit_item = NoteQualityAuditItem(
                note_id=nid,
                front=front,
                back=back,
                quality_status=q_status,
                quality_score=q_score,
                violation_type=v_type,
                quality_feedback=feedback,
                atomic_sister_cards_recommended=sisters if isinstance(sisters, list) else [],
                audited_at=aud.get("audited_at"),
            )
            audit_items.append(audit_item)

        stats = self._store.get_deck_stats(deck_name)

        return AuditQualityBatchResponse(
            deck_name=deck_name,
            batch_size=batch_size,
            audited_count=len(audit_items),
            items=audit_items,
            deck_stats=stats,
        )

    async def find_deck_duplicates(
        self,
        deck_name: str,
        min_similarity: float = 0.88,
        api_key: Optional[str] = None,
    ) -> DeckDuplicatesResponse:
        """Detect redundant and near-duplicate flashcards within an indexed deck."""
        await self._ensure_deck_indexed(deck_name, api_key)
        notes = self._store.get_all_notes_with_embeddings(deck_name)

        if len(notes) < 2:
            return DeckDuplicatesResponse(
                deck_name=deck_name,
                min_similarity=min_similarity,
                total_pairs=0,
                pairs=[],
            )

        # Normalize all vectors upfront
        normalized_notes = []
        for n in notes:
            vec = n.get("embedding", [])
            norm_val = math.sqrt(sum(x * x for x in vec))
            if norm_val > 0:
                normalized_notes.append({
                    "note_id": n["note_id"],
                    "front": _strip_html(n.get("front", ""))[:140],
                    "cluster_name": n.get("cluster_name"),
                    "vec": [x / norm_val for x in vec],
                })

        pairs: List[DuplicateNotePair] = []
        n_len = len(normalized_notes)

        for i in range(n_len):
            n1 = normalized_notes[i]
            v1 = n1["vec"]
            for j in range(i + 1, n_len):
                n2 = normalized_notes[j]
                sim = sum(a * b for a, b in zip(v1, n2["vec"]))
                if sim >= min_similarity:
                    pairs.append(
                        DuplicateNotePair(
                            note_id_1=n1["note_id"],
                            note_id_2=n2["note_id"],
                            front_1=n1["front"],
                            front_2=n2["front"],
                            similarity=round(sim, 4),
                            cluster_1=n1["cluster_name"],
                            cluster_2=n2["cluster_name"],
                        )
                    )

        # Sort pairs descending by similarity score
        pairs.sort(key=lambda p: p.similarity, reverse=True)

        return DeckDuplicatesResponse(
            deck_name=deck_name,
            min_similarity=min_similarity,
            total_pairs=len(pairs),
            pairs=pairs,
        )



