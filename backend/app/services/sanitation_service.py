import logging
import re
from typing import Any, Dict, List, Optional

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    CardType,
    DeckNoteRecord,
    Flashcard,
    PedagogicalDeckAuditResult,
    PedagogicalOrderViolation,
    PreserveOptimalResponse,
    SanitationCoverageLedgerInput,
    SanitationQueueResponse,
    TransactionalReplaceResponse,
)
from app.core.card_sorter import sort_flashcards_pedagogically
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.ports.embedding_port import IEmbeddingPort


logger = logging.getLogger(__name__)


def _extract_note_subtopic_descriptor(front: str) -> str:
    """Extract a concise subtopic descriptor from front text or breadcrumbs."""
    clean = re.sub(r"<[^>]+>", " ", front).strip()
    m = re.match(r"^\[(.*?)\]\s*(.*)", clean)
    if m:
        path = m.group(1).strip()
        leaf = path.split(">")[-1].strip() if ">" in path else path
        q = m.group(2).strip()
        if len(leaf) > 3:
            return leaf
        return q[:60].strip()
    first_line = clean.split("\n")[0].strip()
    return re.sub(r"\s+", " ", first_line)[:60].strip()


def _ensure_note_record(note: Any, deck_name: str = "") -> DeckNoteRecord:
    """Defensively normalize raw dictionaries or objects to DeckNoteRecord."""
    if isinstance(note, DeckNoteRecord):
        return note
    if isinstance(note, dict):
        nid = int(note.get("note_id") or note.get("noteId") or 0)
        m_name = str(note.get("model_name") or note.get("modelName") or "Basic")
        tags = note.get("tags") or []
        fields = note.get("fields") or {}
        if isinstance(fields, dict):
            f_val = fields.get("Front")
            front = note.get("front") or (f_val.get("value") if isinstance(f_val, dict) else f_val) or ""
            b_val = fields.get("Back")
            back = note.get("back") or (b_val.get("value") if isinstance(b_val, dict) else b_val) or ""
        else:
            front = note.get("front") or ""
            back = note.get("back") or ""
        return DeckNoteRecord(
            note_id=nid,
            deck_name=note.get("deck_name") or deck_name,
            model_name=m_name,
            card_type=CardType.BASIC,
            front=front or "",
            back=back or "",
            explanation=note.get("explanation"),
            clean_text=note.get("clean_text") or f"{front} {back}".strip(),
            clean_front=note.get("clean_front") or front,
            clean_back=note.get("clean_back") or back,
            tags=tags,
            card_ids=note.get("card_ids") or note.get("cards") or [],
            media_files=note.get("media_files") or [],
        )
    return note


class SanitationService:
    """Service orchestrating surgical note sanitization, topological queueing, and transactional card substitution."""

    def __init__(
        self,
        anki_bridge: IAnkiBridgePort,
        store: DeckKnowledgeStore,
        dag_service: Optional[Any] = None,
        embedding_port: Optional[IEmbeddingPort] = None,
    ):
        self._anki_bridge = anki_bridge
        self._store = store
        self._dag_service = dag_service
        self._embedding_port = embedding_port

    async def get_sanitation_queue(self, deck_name: str) -> SanitationQueueResponse:
        """Fetch all deck notes, check quality status, and return queue of notes pending atomic sanitization.

        Deterministic 0-LLM queue sorted by:
        1. Active stage first
        2. Depth level ASC (mapped nodes have min node depth; unmapped notes have depth 999)
        3. 'bad' before 'unreviewed'
        4. Topological DAG rank
        """
        # 1. Fetch live notes from Anki
        raw_notes = await self._anki_bridge.get_deck_notes(deck_name)
        all_notes = [_ensure_note_record(n, deck_name) for n in (raw_notes or [])]
        total_notes = len(all_notes)

        # 2. Get indexed status from SQLite
        indexed_notes = self._store.get_all_indexed_notes(deck_name)
        indexed_by_id = {n["note_id"]: n for n in indexed_notes}

        # 3. Check Learning Plan Contract and active stage
        contract_data = self._store.get_learning_contract(deck_name)
        contract_approved = bool(contract_data and contract_data.get("status") == "approved")
        contract_version = contract_data.get("version") if contract_data else None

        active_stage_id = "stage_1"
        if contract_data and "stages" in contract_data:
            stages = contract_data["stages"]
            for s in stages:
                if isinstance(s, dict) and not s.get("is_completed", False):
                    active_stage_id = s.get("stage_id", "stage_1")
                    break
                elif hasattr(s, "is_completed") and not s.is_completed:
                    active_stage_id = getattr(s, "stage_id", "stage_1")
                    break

        # 4. Get DAG information
        if not self._dag_service:
            from app.services.deck_dag_service import DeckDAGService
            self._dag_service = DeckDAGService(self._store)

        dag = self._dag_service.get_deck_dag(deck_name)
        topo_order = self._dag_service.get_topological_card_order(deck_name)
        topo_rank = {nid: idx for idx, nid in enumerate(topo_order)}

        # Build map: note_id -> list of mapped concept nodes
        node_by_id = {node.id: node for node in dag.nodes}
        mappings = self._store.get_card_concept_mappings(deck_name)
        note_to_nodes: Dict[int, List[Any]] = {}
        for m in mappings:
            # Pedagogical invariant: A card's curricular depth is determined exclusively by its TARGET concept,
            # never by its prerequisites (which are by definition at lower depths).
            if m.get("role") == "target":
                nid = m["note_id"]
                cid = m["concept_id"]
                if cid in node_by_id:
                    note_to_nodes.setdefault(nid, []).append(node_by_id[cid])

        pending_notes: List[DeckNoteRecord] = []
        sanitized_count = 0

        for note in all_notes:
            idx = indexed_by_id.get(note.note_id)
            if idx:
                q_status = idx.get("quality_status") or "unreviewed"
                if q_status in ("debt", "broken"):
                    q_status = "bad"
                note.quality_status = q_status
                note.quality_score = idx.get("quality_score")
                note.quality_feedback = idx.get("quality_feedback")
                note.audited_at = idx.get("audited_at")
            else:
                note.quality_status = "unreviewed"

            if note.quality_status == "optimal":
                sanitized_count += 1
            else:
                pending_notes.append(note)

        # Sort criteria:
        # 1. Active stage: 0 if belongs to active stage, else 1
        # 2. depth_level ASC: min(node.depth_level) or 999
        # 3. quality: 'bad' (0) before 'unreviewed' (1)
        # 4. topo_index: rank in topological sort or 999999
        def _sort_key(n: DeckNoteRecord):
            nodes = note_to_nodes.get(n.note_id, [])
            if nodes:
                is_active = 0 if any(getattr(node, "stage_id", "stage_1") == active_stage_id for node in nodes) else 1
                depth = min(getattr(node, "depth_level", 999) for node in nodes)
            else:
                is_active = 1
                depth = 999

            q_rank = 0 if n.quality_status == "bad" else 1
            t_rank = topo_rank.get(n.note_id, 999999)

            return (is_active, depth, q_rank, t_rank)

        pending_notes.sort(key=_sort_key)

        return SanitationQueueResponse(
            deck_name=deck_name,
            total_notes=total_notes,
            pending_count=len(pending_notes),
            sanitized_count=sanitized_count,
            contract_approved=contract_approved,
            contract_version=contract_version,
            notes=pending_notes,
        )

    async def replace_note_transactionally(
        self,
        deck_name: str,
        source_note_id: int,
        new_cards: List[Flashcard],
        target_concepts: Optional[List[str]] = None,
        pending_ledger_collisions: Optional[List[SanitationCoverageLedgerInput]] = None,
    ) -> TransactionalReplaceResponse:
        """Atomically insert new atomic cards into Anki, update mappings and ledger, and delete obsolete note."""
        if not new_cards:
            raise ValueError("No se proporcionaron tarjetas atómicas nuevas para sustituir la nota.")

        logger.info(
            "Initiating transactional replacement for note %d in deck '%s' with %d new cards.",
            source_note_id,
            deck_name,
            len(new_cards),
        )

        # Step 0: Pedagogical cognitive sorting of the atomic card batch (0-LLM)
        sorted_new_cards = sort_flashcards_pedagogically(new_cards)

        # Query original card's queue position before deletion for local slot splicing
        original_due = None
        orig_is_new_queue = False
        try:
            orig_card_ids = await self._anki_bridge.get_note_cards([source_note_id])
            if orig_card_ids:
                infos = await self._anki_bridge.get_cards_info(orig_card_ids)
                new_dues = [
                    c.get("due")
                    for c in infos
                    if isinstance(c, dict) and c.get("queue") == 0 and c.get("due") is not None
                ]
                if new_dues:
                    original_due = min(new_dues)
                    orig_is_new_queue = True
        except Exception as pos_err:
            logger.warning("Could not query original queue position for note %d: %s", source_note_id, pos_err)

        # Step 1: Add new cards via AnkiConnect using cognitively sorted cards
        created_notes_raw = await self._anki_bridge.create_notes(
            deck_name=deck_name,
            cards=sorted_new_cards,
        )
        if hasattr(created_notes_raw, "created_note_ids"):
            created_note_ids = created_notes_raw.created_note_ids or []
        elif isinstance(created_notes_raw, dict) and "created_note_ids" in created_notes_raw:
            created_note_ids = created_notes_raw["created_note_ids"] or []
        elif isinstance(created_notes_raw, list):
            created_note_ids = created_notes_raw
        else:
            created_note_ids = []

        if not created_note_ids or len(created_note_ids) == 0:
            logger.error(
                "AnkiConnect failed to create new cards for note %d. Aborting deletion to prevent data loss.",
                source_note_id,
            )
            raise RuntimeError(
                f"Fallo en AnkiConnect al crear tarjetas atómicas. La nota original #{source_note_id} se mantuvo intacta."
            )

        # Step 1b: Local Splicing: reposition newly created cards into original slot ONLY if in new queue (Q4)
        if orig_is_new_queue and original_due is not None:
            try:
                created_card_ids = await self._anki_bridge.get_note_cards(created_note_ids)
                if created_card_ids:
                    await self._anki_bridge.reposition_cards(
                        card_ids=created_card_ids,
                        starting_from=original_due,
                        step=1,
                        shift=True,
                    )
                    logger.info(
                        "Local splicing successful: repositioned %d cards into slot #%d (shift=True).",
                        len(created_card_ids),
                        original_due,
                    )
            except Exception as splice_err:
                logger.warning("Local splicing failed for note %d: %s", source_note_id, splice_err)
        else:
            logger.info(
                "Local splicing skipped for note %d: original note was not in new cards queue (queue != 0).",
                source_note_id,
            )

        logger.info(
            "Successfully created %d new notes in Anki (IDs: %s). Proceeding to delete obsolete note %d.",
            len(created_note_ids),
            created_note_ids,
            source_note_id,
        )

        # Step 2: Delete obsolete original note in Anki
        deleted_count = await self._anki_bridge.delete_notes([source_note_id])
        if deleted_count == 0:
            logger.warning(
                "Obsolete note %d was not deleted from Anki (might have been removed manually).",
                source_note_id,
            )

        # Step 3: Compute real embeddings and index new cards as optimal in knowledge store
        texts = [f"{card.front} | {card.back}" for card in sorted_new_cards]
        embeddings = [None] * len(sorted_new_cards)
        if self._embedding_port:
            try:
                embeddings = await self._embedding_port.embed_texts(texts)
            except Exception as emb_err:
                logger.warning("Failed to generate embeddings for new cards: %s", emb_err)

        records_to_index = []
        for i, (cid, card) in enumerate(zip(created_note_ids, sorted_new_cards)):
            records_to_index.append(
                {
                    "note_id": cid,
                    "front": card.front,
                    "back": card.back,
                    "explanation": card.explanation or "",
                    "tags": card.tags or [deck_name.lower().replace("::", "-")],
                    "quality_status": "optimal",
                    "quality_score": 1.0,
                    "quality_feedback": "Tarjeta atómica generada bajo Contrato Pedagógico de Fase 2",
                    "embedding": embeddings[i] if i < len(embeddings) else None,
                }
            )
        self._store.save_note_embeddings(deck_name, records_to_index)


        # Step 4: Transfer/assign links in card_concept_mappings
        deck_concepts = self._store.get_deck_concepts(deck_name)
        concept_lookup = {c["name"].lower(): c["id"] for c in deck_concepts}
        concept_lookup.update({c["id"].lower(): c["id"] for c in deck_concepts})

        resolved_concept_ids: List[str] = []
        if target_concepts:
            for tc in target_concepts:
                tc_lower = tc.strip().lower()
                if tc_lower in concept_lookup:
                    resolved_concept_ids.append(concept_lookup[tc_lower])
                else:
                    from app.services.deck_dag_service import slugify_concept
                    slug_id = slugify_concept(tc)
                    resolved_concept_ids.append(slug_id)
                    # Automatically register new concept into concept_nodes so it enters the DAG
                    self._store.upsert_concept_node(
                        deck_name=deck_name,
                        concept_id=slug_id,
                        name=tc,
                        taxonomy_path=f"{deck_name} > {tc}",
                        description=f"Concepto curricular introducido en saneamiento: {tc}",
                        depth_level=1,
                        status="SANITIZED",
                        is_in_scope=True,
                    )
        else:
            # Fallback to existing concepts of the source note
            existing_mappings = self._store.get_card_concept_mappings(deck_name)
            resolved_concept_ids = [
                m["concept_id"] for m in existing_mappings if m["note_id"] == source_note_id
            ]

        for cid in created_note_ids:
            for conc_id in resolved_concept_ids:
                self._store.link_card_to_concept(deck_name, cid, conc_id, role="target")

        # Step 5: Clean up old note in SQLite & purge consumed ledger
        with self._store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM indexed_notes WHERE deck_name = ? AND note_id = ?", (deck_name, source_note_id))
            cursor.execute("DELETE FROM card_concept_mappings WHERE deck_name = ? AND note_id = ?", (deck_name, source_note_id))
            cursor.execute("DELETE FROM note_extracted_knowledge WHERE deck_name = ? AND note_id = ?", (deck_name, source_note_id))
            conn.commit()

        # Purge consumed ledger entries for the note whose turn just completed
        self._store.delete_ledger_entries_for_note(deck_name, source_note_id)

        # Step 6: Record pending ledger collisions if any
        if pending_ledger_collisions:
            for col in pending_ledger_collisions:
                self._store.record_ledger_coverage(
                    deck_name=deck_name,
                    source_note_id=source_note_id,
                    colliding_note_id=col.colliding_note_id,
                    concept_title=col.concept_title,
                    facet_summary=col.facet_summary,
                    created_atomic_note_ids=created_note_ids,
                )

        # Step 7: Recompute DAG with recompute_depths=True
        if not self._dag_service:
            from app.services.deck_dag_service import DeckDAGService
            self._dag_service = DeckDAGService(self._store)
        try:
            self._dag_service.get_deck_dag(deck_name, recompute_depths=True)
        except Exception as dag_err:
            logger.warning("Failed to recompute DAG after note replacement: %s", dag_err)

        # Step 8: Calculate remaining in queue
        queue = await self.get_sanitation_queue(deck_name)

        return TransactionalReplaceResponse(
            success=True,
            deck_name=deck_name,
            deleted_note_id=source_note_id,
            created_note_ids=created_note_ids,
            created_cards_count=len(created_note_ids),
            message=f"Nota #{source_note_id} sustituida con éxito por {len(created_note_ids)} tarjetas atómicas.",
            remaining_in_queue=queue.pending_count,
        )

    async def mark_note_as_optimal_preserved(
        self, deck_name: str, note_id: int
    ) -> PreserveOptimalResponse:
        """Mark an existing high-quality note directly as optimal in knowledge store without rewriting or deleting in Anki."""
        raw_notes = await self._anki_bridge.get_deck_notes(deck_name)
        all_notes = [_ensure_note_record(n, deck_name) for n in (raw_notes or [])]
        target = next((n for n in all_notes if n.note_id == note_id), None)
        if not target:
            raise ValueError(f"No se encontró la nota #{note_id} en el mazo '{deck_name}'.")

        records_to_index = [
            {
                "note_id": note_id,
                "front": target.front,
                "back": target.back,
                "explanation": target.explanation or "",
                "tags": target.tags or [deck_name.lower().replace("::", "-")],
                "quality_status": "optimal",
                "quality_score": 1.0,
                "quality_feedback": "Conservada manualmente como óptima por el usuario en Cockpit de Saneamiento",
            }
        ]
        self._store.save_note_embeddings(deck_name, records_to_index)
        # Purge any consumed ledger entries for this preserved note
        self._store.delete_ledger_entries_for_note(deck_name, note_id)

        queue = await self.get_sanitation_queue(deck_name)

        return PreserveOptimalResponse(
            success=True,
            deck_name=deck_name,
            note_id=note_id,
            message=f"Nota #{note_id} conservada como óptima. No se realizaron cambios destructivos en Anki.",
            quality_status="optimal",
            remaining_in_queue=queue.pending_count,
        )

    async def audit_pedagogical_deck_order(self, deck_name: str) -> PedagogicalDeckAuditResult:
        """Deterministically audit Anki new queue ordering against curriculum DAG depths and prerequisites (0-LLM)."""
        if not self._dag_service:
            from app.services.deck_dag_service import DeckDAGService
            self._dag_service = DeckDAGService(self._store)

        # 1. Fetch live notes & their cards from Anki
        raw_live = await self._anki_bridge.get_deck_notes(deck_name)
        live_notes = [_ensure_note_record(n, deck_name) for n in (raw_live or [])]
        if not live_notes:
            return PedagogicalDeckAuditResult(
                deck_name=deck_name,
                total_cards=0,
                sanitized_cards=0,
                inversions_count=0,
                is_pedagogically_sound=True,
                violations=[],
                recommendation="El mazo está vacío en Anki.",
            )

        # 2. Query quality statuses from SQLite
        indexed_notes = self._store.get_all_indexed_notes(deck_name)
        quality_map = {n["note_id"]: n.get("quality_status", "unreviewed") for n in indexed_notes}

        # 3. Get DAG nodes, depths and mappings
        dag = self._dag_service.get_deck_dag(deck_name)
        node_by_id = {node.id: node for node in dag.nodes}
        mappings = self._store.get_card_concept_mappings(deck_name)
        note_to_concept: Dict[int, Any] = {}
        for m in mappings:
            if m.get("role") == "target" and m["concept_id"] in node_by_id:
                note_to_concept[m["note_id"]] = node_by_id[m["concept_id"]]

        # 4. Fetch all card IDs & their metadata (due position)
        all_card_ids: List[int] = []
        for n in live_notes:
            all_card_ids.extend(n.card_ids or [])

        card_infos = await self._anki_bridge.get_cards_info(all_card_ids)
        card_due_map = {
            c["cardId"]: c.get("due", 999999)
            for c in card_infos
            if isinstance(c, dict) and "cardId" in c
        }

        # 5. Build sanitized items list: each item has (note_id, concept_name, depth_level, min_due)
        sanitized_items = []
        unsanitized_dues = []

        for n in live_notes:
            q_status = quality_map.get(n.note_id, "unreviewed")
            cids = n.card_ids or []
            dues = [card_due_map.get(cid, 999999) for cid in cids]
            min_due = min(dues) if dues else 999999

            if q_status == "optimal":
                conc = note_to_concept.get(n.note_id)
                depth = getattr(conc, "depth_level", 0) if conc else 0
                cname = getattr(conc, "name", "General") if conc else "General"
                sanitized_items.append({
                    "note_id": n.note_id,
                    "concept_name": cname,
                    "depth_level": depth,
                    "due": min_due,
                })
            else:
                unsanitized_dues.append(min_due)

        # 6. Detect Curricular Inversions among sanitized cards
        sanitized_items.sort(key=lambda x: x["due"])
        violations: List[PedagogicalOrderViolation] = []

        for i in range(len(sanitized_items)):
            for j in range(i + 1, len(sanitized_items)):
                item_earlier = sanitized_items[i]
                item_later = sanitized_items[j]

                # If an earlier card has higher depth than a later card: Inversion!
                if item_earlier["depth_level"] > item_later["depth_level"] and item_earlier["due"] < item_later["due"]:
                    violations.append(
                        PedagogicalOrderViolation(
                            higher_depth_note_id=item_earlier["note_id"],
                            lower_depth_note_id=item_later["note_id"],
                            higher_concept=item_earlier["concept_name"],
                            lower_concept=item_later["concept_name"],
                            higher_depth=item_earlier["depth_level"],
                            lower_depth=item_later["depth_level"],
                            higher_due=item_earlier["due"],
                            lower_due=item_later["due"],
                            reason=f"La nota #{item_earlier['note_id']} de Nivel {item_earlier['depth_level']} ('{item_earlier['concept_name']}', slot #{item_earlier['due']}) precede a la nota #{item_later['note_id']} de Nivel {item_later['depth_level']} ('{item_later['concept_name']}', slot #{item_later['due']}).",
                        )
                    )

        # Check if unsanitized backlog cards appear before sanitized cards
        if unsanitized_dues and sanitized_items:
            min_unsanitized = min(unsanitized_dues)
            max_sanitized = max(item["due"] for item in sanitized_items)
            if min_unsanitized < max_sanitized:
                violations.append(
                    PedagogicalOrderViolation(
                        higher_depth_note_id=0,
                        lower_depth_note_id=sanitized_items[-1]["note_id"],
                        higher_concept="Backlog no saneado",
                        lower_concept=sanitized_items[-1]["concept_name"],
                        higher_depth=999,
                        lower_depth=sanitized_items[-1]["depth_level"],
                        higher_due=min_unsanitized,
                        lower_due=max_sanitized,
                        reason=f"Existen tarjetas no saneadas del backlog en slot #{min_unsanitized} antes de tarjetas saneadas que llegan hasta el slot #{max_sanitized}.",
                    )
                )

        inversions_count = len(violations)
        is_sound = inversions_count == 0

        recommendation = (
            "✅ El orden del mazo es 100% pedagógico. No se detectaron inversiones de conceptos."
            if is_sound
            else f"⚠️ Se detectaron {inversions_count} inversiones de orden pedagógico. Se recomienda alinear la cola de Anki con el grafo curricular."
        )

        return PedagogicalDeckAuditResult(
            deck_name=deck_name,
            total_cards=len(all_card_ids),
            sanitized_cards=len(sanitized_items),
            inversions_count=inversions_count,
            is_pedagogically_sound=is_sound,
            violations=violations[:25],
            recommendation=recommendation,
        )

    async def reposition_deck_topologically(
        self, deck_name: str, only_sanitized: bool = True
    ) -> Dict[str, Any]:
        """Reposition cards in Anki new queue following the DAG curriculum topological order.
        
        Prioritizes sanitized cards (Level 0 -> Level 1 -> ...) at the front of the queue,
        followed by unsanitized backlog cards.
        """
        if not self._dag_service:
            from app.services.deck_dag_service import DeckDAGService
            self._dag_service = DeckDAGService(self._store)

        # 1. Get live notes to map note_id -> card_ids
        raw_live = await self._anki_bridge.get_deck_notes(deck_name)
        live_notes = [_ensure_note_record(n, deck_name) for n in (raw_live or [])]
        if not live_notes:
            return {
                "success": False,
                "deck_name": deck_name,
                "message": "No se encontraron notas en Anki para este mazo.",
                "repositioned_count": 0,
            }

        note_to_cards: Dict[int, List[int]] = {n.note_id: (n.card_ids or []) for n in live_notes}

        # 2. Get quality statuses from SQLite
        indexed_notes = self._store.get_all_indexed_notes(deck_name)
        quality_map = {n["note_id"]: n.get("quality_status", "unreviewed") for n in indexed_notes}

        # 3. Get note IDs ordered by DAG topological sort
        ordered_note_ids = self._dag_service.get_topological_card_order(deck_name)

        # 4. Separate sanitized notes vs unsanitized notes
        sanitized_card_ids: List[int] = []
        seen_sanitized_notes = set()

        # Follow DAG topological order for sanitized notes
        for nid in ordered_note_ids:
            if quality_map.get(nid) == "optimal":
                cids = note_to_cards.get(nid, [])
                sanitized_card_ids.extend(cids)
                seen_sanitized_notes.add(nid)

        # Include any remaining sanitized notes not in DAG
        for n in live_notes:
            if quality_map.get(n.note_id) == "optimal" and n.note_id not in seen_sanitized_notes:
                sanitized_card_ids.extend(n.card_ids or [])
                seen_sanitized_notes.add(n.note_id)

        # Backlog: all unsanitized notes in their original relative order
        backlog_card_ids: List[int] = []
        for n in live_notes:
            if n.note_id not in seen_sanitized_notes:
                backlog_card_ids.extend(n.card_ids or [])

        # Combined: sanitized first (Level 0 -> Level 1 -> ...), then backlog
        final_ordered_card_ids = sanitized_card_ids + backlog_card_ids

        if not final_ordered_card_ids:
            return {
                "success": False,
                "deck_name": deck_name,
                "message": "No se encontraron tarjetas físicas para ordenar en Anki.",
                "repositioned_count": 0,
            }

        # 5. Invoke AnkiConnect reposition (shift=False since we order the entire deck from index 0)
        success = await self._anki_bridge.reposition_cards(
            final_ordered_card_ids, starting_from=0, step=1, shift=False
        )

        return {
            "success": success,
            "deck_name": deck_name,
            "message": f"Cola de Anki alineada: {len(sanitized_card_ids)} tarjetas saneadas ordenadas topológicamente desde Nivel 0, seguidas por {len(backlog_card_ids)} tarjetas del backlog."
            if success
            else "Fallo al comunicar ordenamiento con AnkiConnect.",
            "repositioned_count": len(final_ordered_card_ids) if success else 0,
            "sanitized_count": len(sanitized_card_ids),
            "backlog_count": len(backlog_card_ids),
        }

