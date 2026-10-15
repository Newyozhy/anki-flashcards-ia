import logging
from typing import Any, Dict, List, Optional, Set

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    DeckExpansionQueueResponse,
    ExpansionQueueItem,
)
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.services.deck_dag_service import DeckDAGService

logger = logging.getLogger(__name__)


class DeckExpansionService:
    """Service orchestrating Phase 4 topological curriculum expansion and orphan gap fulfillment."""

    def __init__(
        self,
        store: DeckKnowledgeStore,
        dag_service: DeckDAGService,
        anki_bridge: IAnkiBridgePort,
    ):
        self._store = store
        self._dag_service = dag_service
        self._anki_bridge = anki_bridge

    async def get_expansion_queue(self, deck_name: str) -> DeckExpansionQueueResponse:
        """Analyze deck DAG and return uncovered concepts ordered topologically (first principles first)."""
        # 1. Check Learning Plan Contract status
        contract_data = self._store.get_learning_contract(deck_name)
        contract_approved = bool(contract_data and contract_data.get("status") == "approved")

        # 2. Check live sanitation status
        pending_sanitation_count = 0
        try:
            all_notes = await self._anki_bridge.get_deck_notes(deck_name)
            indexed_notes = self._store.get_all_indexed_notes(deck_name)
            indexed_by_id = {n["note_id"]: n for n in indexed_notes}

            for note in all_notes:
                idx = indexed_by_id.get(note.note_id)
                q_status = idx.get("quality_status") if idx else "unreviewed"
                if q_status != "optimal":
                    pending_sanitation_count += 1
        except Exception as err:
            logger.warning("Could not verify live Anki notes for deck '%s': %s", deck_name, err)

        sanitation_completed = (pending_sanitation_count == 0)

        # 3. Retrieve computed DAG from NetworkX engine
        dag = self._dag_service.get_deck_dag(deck_name)

        # Build node and edge lookup
        node_lookup = {node.id: node for node in dag.nodes}
        
        # Build incoming (prerequisites) and outgoing (dependents) maps
        prereqs_map: Dict[str, List[str]] = {}
        dependents_map: Dict[str, List[str]] = {}

        for edge in dag.edges:
            src_node = node_lookup.get(edge.source)
            tgt_node = node_lookup.get(edge.target)
            if src_node and tgt_node:
                # Edge: source -> target means source is prerequisite of target
                prereqs_map.setdefault(edge.target, []).append(src_node.name)
                dependents_map.setdefault(edge.source, []).append(tgt_node.name)

        # 4. Construct expansion queue following topological order
        expansion_items: List[ExpansionQueueItem] = []
        total_orphans = 0

        for cid in dag.topological_order:
            node = node_lookup.get(cid)
            if not node:
                continue

            # Only queue concepts that are in scope according to the pedagogical contract (Pillar 3)
            if not getattr(node, "is_in_scope", True):
                continue

            if node.is_orphan or node.card_count == 0:
                total_orphans += 1
                prereqs = prereqs_map.get(cid, [])
                deps = dependents_map.get(cid, [])

                # Formulate high-context suggested prompt for generation
                if deps:
                    prompt_ctx = (
                        f"Fundamento pedagógico de '{node.name}'. "
                        f"Este concepto es prerrequisito necesario para comprender: {', '.join(deps[:3])}."
                    )
                else:
                    prompt_ctx = f"Explicación atómica y primeros principios de '{node.name}'."

                neighbors = self._dag_service.get_neighbor_concepts(deck_name, node.name)

                expansion_items.append(
                    ExpansionQueueItem(
                        concept_id=node.id,
                        concept_name=node.name,
                        taxonomy_path=node.taxonomy_path,
                        depth_level=node.depth_level,
                        prerequisites=prereqs,
                        dependents=deps,
                        is_orphan=True,
                        cards_count=node.card_count,
                        suggested_prompt=prompt_ctx,
                        neighbor_concepts=neighbors,
                    )
                )

        return DeckExpansionQueueResponse(
            deck_name=deck_name,
            contract_approved=contract_approved,
            sanitation_completed=sanitation_completed,
            pending_sanitation_count=pending_sanitation_count,
            total_orphans=total_orphans,
            total_concepts=dag.total_concepts,
            expansion_queue=expansion_items,
        )

    def link_cards_to_concept(
        self,
        deck_name: str,
        concept_id: str,
        note_ids: List[int],
    ) -> bool:
        """Link newly created flashcards to a concept node as target, resolving its orphan gap status."""
        if not note_ids:
            return False

        logger.info(
            "Linking %d cards to concept '%s' in deck '%s'.",
            len(note_ids),
            concept_id,
            deck_name,
        )

        for nid in note_ids:
            self._store.link_card_to_concept(
                deck_name=deck_name,
                note_id=int(nid),
                concept_id=concept_id,
                role="target",
            )

        return True
