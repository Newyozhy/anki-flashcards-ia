import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    ConceptEdge,
    ConceptNode,
    DAGPedagogicalContext,
    DeckConceptDAG,
    ExtractedNoteKnowledge,
)

logger = logging.getLogger(__name__)


def slugify_concept(name: str) -> str:
    """Normalize a concept string into a stable, deduplicated slug key.
    
    Example: 'OCI Route Table (VCN)' -> 'oci_route_table_vcn'
    'C++ / C#' -> 'c_plus_plus_slash_c_sharp'
    """
    if not name:
        return ""
    # 1. Map common technical symbols to avoid collapsions (e.g. SFP+, C#, TCP/IP)
    text = (
        name.replace("+", " plus ")
        .replace("#", " sharp ")
        .replace("&", " and ")
        .replace("/", " slash ")
    )
    # 2. Decompose diacritics via NFKD and strip Latin combining accents without discarding non-Latin characters
    norm = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in norm if unicodedata.category(c) != "Mn" or c in ("\u3099", "\u309a"))
    recomposed = unicodedata.normalize("NFC", without_accents)
    # 3. Clean non-alphanumeric unicode characters while preserving unicode words
    cleaned = re.sub(r"[^\w\s-]", " ", recomposed, flags=re.UNICODE)
    cleaned = re.sub(r"[\s_-]+", "_", cleaned).strip("_").lower()
    return cleaned or "unnamed_concept"


class DeckDAGService:
    """Core pedagogical graph engine for constructing, sorting, and analyzing curriculum DAGs."""

    def __init__(self, store: DeckKnowledgeStore):
        self._store = store

    def ingest_note_extractions(
        self,
        deck_name: str,
        extractions: List[ExtractedNoteKnowledge],
    ) -> DeckConceptDAG:
        """Ingest batch of note extractions into SQLite and recompute the Deck DAG."""
        for ext in extractions:
            note_id = ext.source_note_id
            tax_path = ext.taxonomy_path or "general"

            # 1. Save raw extraction cache
            self._store.save_note_extracted_knowledge(
                deck_name=deck_name,
                note_id=note_id,
                raw_front=ext.raw_front,
                raw_back=ext.raw_back,
                extracted_facts=ext.extracted_facts,
                target_concepts=ext.target_concepts,
                assumed_prerequisites=ext.assumed_prerequisites,
                taxonomy_path=tax_path,
            )

            # 2. Upsert target concepts and link note
            target_slugs: List[str] = []
            for target_name in ext.target_concepts:
                target_slug = slugify_concept(target_name)
                if not target_slug:
                    continue
                target_slugs.append(target_slug)
                self._store.upsert_concept_node(
                    deck_name=deck_name,
                    concept_id=target_slug,
                    name=target_name.strip(),
                    taxonomy_path=tax_path,
                )
                self._store.link_card_to_concept(
                    deck_name=deck_name,
                    note_id=note_id,
                    concept_id=target_slug,
                    role="target",
                )

            # 3. Upsert prerequisite concepts, link note, and add precedence edges
            for prereq_name in ext.assumed_prerequisites:
                prereq_slug = slugify_concept(prereq_name)
                if not prereq_slug:
                    continue

                # Ensure prerequisite node exists (starts with depth_level=0)
                self._store.upsert_concept_node(
                    deck_name=deck_name,
                    concept_id=prereq_slug,
                    name=prereq_name.strip(),
                    taxonomy_path=tax_path,
                )
                self._store.link_card_to_concept(
                    deck_name=deck_name,
                    note_id=note_id,
                    concept_id=prereq_slug,
                    role="prerequisite",
                )

                # Directed edge: prerequisite -> target_concept (prerequisite MUST be learned before target)
                for target_slug in target_slugs:
                    if prereq_slug != target_slug:
                        self._store.upsert_concept_edge(
                            deck_name=deck_name,
                            source_id=prereq_slug,
                            target_id=target_slug,
                            relation_type="requires",
                        )

        # 4. Rebuild DAG with NetworkX and update depths
        return self.get_deck_dag(deck_name, recompute_depths=True)

    def get_deck_dag(self, deck_name: str, recompute_depths: bool = False) -> DeckConceptDAG:
        """Construct NetworkX graph from store, analyze topology, and return DeckConceptDAG."""
        raw_concepts = self._store.get_deck_concepts(deck_name)
        raw_edges = self._store.get_deck_edges(deck_name)
        raw_mappings = self._store.get_card_concept_mappings(deck_name)

        if not raw_concepts:
            return DeckConceptDAG(
                deck_name=deck_name,
                nodes=[],
                edges=[],
                topological_order=[],
                orphan_concepts=[],
                has_cycles=False,
                total_concepts=0,
                total_edges=0,
            )

        # Build card mapping index per concept
        cards_per_concept: Dict[str, Set[int]] = {}
        for m in raw_mappings:
            if m["role"] == "target":
                cards_per_concept.setdefault(m["concept_id"], set()).add(m["note_id"])

        # Construct NetworkX DiGraph for precedence ("requires")
        g = nx.DiGraph()

        # Add all nodes
        concept_dict: Dict[str, Dict[str, Any]] = {}
        for c in raw_concepts:
            cid = c["id"]
            concept_dict[cid] = c
            mapped_cards = sorted(list(cards_per_concept.get(cid, set())))
            g.add_node(
                cid,
                name=c["name"],
                taxonomy_path=c["taxonomy_path"],
                description=c.get("description"),
                depth_level=c.get("depth_level", 1),
                cards_mapped=mapped_cards,
                card_count=len(mapped_cards),
            )

        # Add precedence edges
        clean_edges: List[ConceptEdge] = []
        for e in raw_edges:
            src = e["source"]
            tgt = e["target"]
            rel = e["relation_type"]
            if src in concept_dict and tgt in concept_dict and src != tgt:
                g.add_edge(src, tgt, relation_type=rel)
                clean_edges.append(ConceptEdge(source=src, target=tgt, relation_type=rel))

        # Check for cycles
        has_cycles = not nx.is_directed_acyclic_graph(g)
        topological_order: List[str] = []

        if has_cycles:
            logger.warning(
                "Deck '%s' concept graph contains cycles! Resolving cycle feedback arcs for sorting.",
                deck_name,
            )
            # Create acyclic copy by breaking simple cycles using taxonomy depth and centrality heuristic (Q1)
            dag_copy = g.copy()
            while not nx.is_directed_acyclic_graph(dag_copy):
                cycle = nx.find_cycle(dag_copy, orientation="original")
                best_edge = (cycle[0][0], cycle[0][1])
                best_score = (-999999, -999999)
                for edge in cycle:
                    u, v = edge[0], edge[1]
                    tax_u = (concept_dict.get(u, {}).get("taxonomy_path") or "").replace("/", "::")
                    tax_v = (concept_dict.get(v, {}).get("taxonomy_path") or "").replace("/", "::")
                    depth_u = len([p for p in tax_u.split("::") if p])
                    depth_v = len([p for p in tax_v.split("::") if p])
                    centrality_diff = dag_copy.out_degree(u) - dag_copy.in_degree(u)
                    score = (depth_u - depth_v, -centrality_diff)
                    if score > best_score:
                        best_score = score
                        best_edge = (u, v)

                dag_copy.remove_edge(*best_edge)
                logger.info(
                    "Cycle detected in '%s'. Intelligently removed feedback edge: %s (score=%s)",
                    deck_name,
                    best_edge,
                    best_score,
                )
            calc_graph = dag_copy
        else:
            calc_graph = g

        # Apply Transitive Reduction (Pillar 1: Poda de redundancias topológicas A -> B -> C vs A -> C)
        pruned_edges_count = 0
        reduced_edges = clean_edges
        if nx.is_directed_acyclic_graph(calc_graph) and len(calc_graph.edges) > 0:
            try:
                tr_graph = nx.transitive_reduction(calc_graph)
                reduced_edge_set = set(tr_graph.edges())
                pruned_edges_count = max(0, len(clean_edges) - len(reduced_edge_set))
                if pruned_edges_count > 0:
                    logger.info(
                        "Transitive reduction pruned %d redundant skip-edges in deck '%s'.",
                        pruned_edges_count,
                        deck_name,
                    )
                reduced_edges = [
                    e for e in clean_edges if (e.source, e.target) in reduced_edge_set
                ]
                calc_graph = tr_graph
            except Exception as tr_err:
                logger.warning("Could not compute transitive reduction for deck '%s': %s", deck_name, tr_err)

        # Stratified generational topological order (G-02)
        topological_order = [
            node
            for generation in nx.topological_generations(calc_graph)
            for node in sorted(generation)
        ]

        # Check learning plan contract for exclusion boundaries (Pillar 3: Delimitación de alcance)
        contract_data = self._store.get_learning_contract(deck_name)
        exclusion_boundary: List[str] = []
        if contract_data and contract_data.get("exclusion_boundary"):
            exclusion_boundary = [
                e.lower().strip()
                for e in contract_data["exclusion_boundary"]
                if isinstance(e, str) and e.strip()
            ]

        # Retrieve indexed notes to compute formal node lifecycle statuses (Pillar 4: Trazabilidad)
        indexed_notes = self._store.get_all_indexed_notes(deck_name)
        note_quality_map = {n["note_id"]: n.get("quality_status", "unreviewed") for n in indexed_notes}

        # Compute depth levels and detect orphan concepts
        orphan_concepts: List[str] = []
        out_of_scope_concepts: List[str] = []
        node_models: List[ConceptNode] = []

        # Depth level = length of longest path from a root node
        depth_levels: Dict[str, int] = {}
        for node in topological_order:
            preds = list(calc_graph.predecessors(node))
            if not preds:
                depth_levels[node] = 0
            else:
                depth_levels[node] = 1 + max(depth_levels.get(p, 0) for p in preds)

        # Build domain models
        for cid, cdata in concept_dict.items():
            mapped_cards = sorted(list(cards_per_concept.get(cid, set())))
            card_count = len(mapped_cards)
            depth = depth_levels.get(cid, cdata.get("depth_level", 0))

            # Degrees from transitively reduced graph (Pillars 1 & 3: in-degree <= 4)
            in_deg = calc_graph.in_degree(cid) if calc_graph.has_node(cid) else 0
            out_deg = calc_graph.out_degree(cid) if calc_graph.has_node(cid) else 0
            is_overloaded = in_deg > 4

            # Scope determination (Pillar 3)
            c_name_lower = cdata["name"].lower()
            c_tax_lower = (cdata.get("taxonomy_path") or "").lower()
            is_out_of_scope = any(
                ex in c_name_lower or ex in c_tax_lower
                for ex in exclusion_boundary
            )
            is_in_scope = not is_out_of_scope
            if is_out_of_scope:
                out_of_scope_concepts.append(cid)

            # Node status determination (Pillar 4: UNMAPPED, RAW, SANITIZED, EXPANDED, MASTERED)
            db_status = cdata.get("status")
            is_orphan = card_count == 0
            if is_orphan:
                orphan_concepts.append(cid)
                status = "UNMAPPED"
            else:
                # Check mapped notes quality (G-06: technical debt demotes to canonical RAW)
                mapped_statuses = [note_quality_map.get(nid, "unreviewed") for nid in mapped_cards]
                has_debt = any(st in ("bad", "debt", "broken") for st in mapped_statuses)
                all_optimal = bool(mapped_statuses) and all(st == "optimal" for st in mapped_statuses)

                if has_debt:
                    status = "RAW"
                elif db_status in ("MASTERED", "SUFFICIENT", "EXPANDED"):
                    status = db_status
                elif all_optimal:
                    status = "SANITIZED"
                else:
                    status = "RAW"

            node_model = ConceptNode(
                id=cid,
                name=cdata["name"],
                deck_name=deck_name,
                taxonomy_path=cdata["taxonomy_path"],
                description=cdata.get("description"),
                depth_level=depth,
                cards_mapped=mapped_cards,
                card_count=card_count,
                is_orphan=is_orphan,
                status=status,
                is_in_scope=is_in_scope,
                in_degree=in_deg,
                out_degree=out_deg,
                is_overloaded=is_overloaded,
            )
            node_models.append(node_model)

            # Update depth, status, and scope in store if requested
            if recompute_depths:
                self._store.upsert_concept_node(
                    deck_name=deck_name,
                    concept_id=cid,
                    name=cdata["name"],
                    taxonomy_path=cdata["taxonomy_path"],
                    description=cdata.get("description"),
                    depth_level=depth,
                    status=status,
                    is_in_scope=is_in_scope,
                    stage_id=cdata.get("stage_id") or "stage_1",
                )

        return DeckConceptDAG(
            deck_name=deck_name,
            nodes=node_models,
            edges=reduced_edges,
            topological_order=topological_order,
            orphan_concepts=orphan_concepts,
            has_cycles=has_cycles,
            total_concepts=len(node_models),
            total_edges=len(reduced_edges),
            transitive_reduction_applied=True,
            pruned_edges_count=pruned_edges_count,
            out_of_scope_concepts=out_of_scope_concepts,
        )

    def get_neighbor_concepts(self, deck_name: str, concept_name: str) -> List[str]:
        """Retrieve neighboring concepts (prerequisites, dependents, and siblings) in the DAG to serve as a negative boundary."""
        dag = self.get_deck_dag(deck_name)
        norm_key = slugify_concept(concept_name)

        target_node = None
        for node in dag.nodes:
            if slugify_concept(node.name) == norm_key or node.id == norm_key:
                target_node = node
                break

        if not target_node:
            return []

        neighbors: Set[str] = set()
        target_id = target_node.id

        # 1. Edge-connected neighbors (predecessors and successors)
        for edge in dag.edges:
            if edge.source == target_id:
                node = next((n for n in dag.nodes if n.id == edge.target), None)
                if node:
                    neighbors.add(node.name)
            elif edge.target == target_id:
                node = next((n for n in dag.nodes if n.id == edge.source), None)
                if node:
                    neighbors.add(node.name)

        # 2. Sibling concepts sharing the same taxonomy branch (G-05)
        if target_node.taxonomy_path:
            norm_tax = target_node.taxonomy_path.replace("/", "::")
            parts = [p for p in norm_tax.split("::") if p]
            if len(parts) > 1:
                parent_prefix = "::".join(parts[:-1])
                for n in dag.nodes:
                    if n.id != target_id and n.taxonomy_path:
                        n_norm = n.taxonomy_path.replace("/", "::")
                        if n_norm.startswith(parent_prefix):
                            neighbors.add(n.name)

        return sorted(list(neighbors))

    def get_topological_card_order(self, deck_name: str) -> List[int]:
        """Compute the topological sequence of note IDs in the deck following curriculum dependencies.
        
        Fixes G-03:
        1. Multi-concept cards are scheduled at their MAXIMUM concept depth and topological index:
           concept*(n) = argmax_{c in C(n)} (depth_level[c], topo_index[c])
        2. Cards mapped to the same concept node are ordered using Bloom cognitive tiers.
        """
        dag = self.get_deck_dag(deck_name)
        topo_index = {cid: idx for idx, cid in enumerate(dag.topological_order)}
        depth_map = {n.id: n.depth_level for n in dag.nodes}

        # Build mapping of note_id -> set of concept_ids it is mapped to
        note_to_concepts: Dict[int, Set[str]] = {}
        for n in dag.nodes:
            for nid in n.cards_mapped:
                note_to_concepts.setdefault(nid, set()).add(n.id)

        # Assign each note to its highest dependency concept: max(depth_level, topo_index)
        concept_to_notes: Dict[str, List[int]] = {cid: [] for cid in dag.topological_order}
        for nid, cids in note_to_concepts.items():
            best_concept = max(
                cids,
                key=lambda c: (depth_map.get(c, 0), topo_index.get(c, 0)),
            )
            concept_to_notes[best_concept].append(nid)

        # Retrieve indexed notes to sort intra-node cards by Bloom pedagogical tier
        indexed_notes = {n["note_id"]: n for n in self._store.get_all_indexed_notes(deck_name)}
        ordered_note_ids: List[int] = []

        from app.core.card_sorter import get_card_pedagogical_rank
        from app.domain.models import Flashcard

        for cid in dag.topological_order:
            notes_in_node = concept_to_notes.get(cid, [])
            if not notes_in_node:
                continue

            # Sort notes intra-node using Flashcard proxy and get_card_pedagogical_rank
            def _note_sort_key(nid: int) -> Tuple[int, int]:
                ndata = indexed_notes.get(nid)
                if not ndata:
                    return (2, nid)
                proxy_card = Flashcard(
                    front=ndata.get("front") or "",
                    back=ndata.get("back") or "",
                    tags=ndata.get("tags") or [],
                    archetype=ndata.get("archetype") or "",
                    explanation=ndata.get("explanation") or "",
                )
                rank = get_card_pedagogical_rank(proxy_card)
                return (rank, nid)

            notes_in_node.sort(key=_note_sort_key)
            ordered_note_ids.extend(notes_in_node)

        return ordered_note_ids

    def get_pedagogical_context_for_generation(
        self,
        deck_name: str,
        concept_name: Optional[str] = None,
        text_sample: Optional[str] = None,
    ) -> Optional[DAGPedagogicalContext]:
        """Query the deck's DAG to extract curriculum precedence, depth, prerequisites, and scope boundaries."""
        dag = self.get_deck_dag(deck_name)
        if not dag.nodes:
            return None

        node_map = {node.id: node for node in dag.nodes}

        # 1. Match target node in DAG
        target_node = None
        if concept_name:
            norm_key = slugify_concept(concept_name)
            for node in dag.nodes:
                if (
                    node.id == norm_key
                    or slugify_concept(node.name) == norm_key
                    or concept_name.lower() in node.name.lower()
                ):
                    target_node = node
                    break

        if not target_node and text_sample:
            # Score each DAG node by presence in text sample
            text_lower = text_sample.lower()
            best_match = None
            best_score = 0
            for node in dag.nodes:
                node_lower = node.name.lower()
                if node_lower in text_lower:
                    score = len(node_lower)  # longer, more specific concept matches take precedence
                    if score > best_score:
                        best_score = score
                        best_match = node
            target_node = best_match

        if not target_node:
            return None

        # 2. Build NetworkX graph from DAG edges
        g = nx.DiGraph()
        for node in dag.nodes:
            g.add_node(node.id)
        for edge in dag.edges:
            if g.has_node(edge.source) and g.has_node(edge.target) and edge.source != edge.target:
                g.add_edge(edge.source, edge.target)

        # 3. Compute ancestors (prerequisites) and descendants (future topics)
        tid = target_node.id
        ancestor_ids = nx.ancestors(g, tid) if g.has_node(tid) else set()
        descendant_ids = nx.descendants(g, tid) if g.has_node(tid) else set()

        ancestor_names = sorted([node_map[aid].name for aid in ancestor_ids if aid in node_map])
        descendant_names = sorted([node_map[did].name for did in descendant_ids if did in node_map])

        # 4. Sibling concepts sharing same taxonomy branch
        siblings: Set[str] = set()
        if target_node.taxonomy_path:
            for n in dag.nodes:
                if n.id != tid and n.taxonomy_path == target_node.taxonomy_path:
                    siblings.add(n.name)
        sibling_names = sorted(list(siblings))

        # 5. Negative boundaries (forbidden topics for definition)
        neg_boundaries = sorted(list(set(ancestor_names + descendant_names + sibling_names)))

        # 6. Formulate precise prompt directive
        prereqs_desc = (
            ", ".join(f"'{a}'" for a in ancestor_names)
            if ancestor_names
            else "Fundamento raíz sin prerrequisitos previos en este mazo."
        )
        descendants_desc = (
            ", ".join(f"'{d}'" for d in descendant_names[:8])
            if descendant_names
            else "Nodo terminal / avanzado del plan de estudios actual."
        )

        directive_lines = [
            f"## [PLAN DE ESTUDIOS - GUÍA PEDAGÓGICA DEL GRAFO (DAG)]",
            f"- Concepto Objetivo: '{target_node.name}' (Nivel de Profundidad Curricular: Nivel {target_node.depth_level})",
            f"- CONOCIMIENTO PREVIO YA CONSOLIDADO (Prerrequisitos en el DAG): {prereqs_desc}.",
            f"  * REGLA DE ORO: Asumí estos conceptos como base conocida y asimilada por el estudiante. "
            f"PROHIBIDO TERMINANTEMENTE generar tarjetas introductorias que pregunten qué son o definan estos conceptos.",
            f"- TEMAS POSTERIORES (Descendientes en el DAG): {descendants_desc}.",
            f"  * REGLA DE ORO: Estos conceptos pertenecen a módulos curriculares posteriores. "
            f"NO te adelantes a explicarlos en este lote.",
            f"- FOCO EXCLUSIVO: Concentrá las tarjetas en la mecánica causal, arquitectura interna, discriminación y casos de falla específicos de '{target_node.name}'.",
        ]
        prompt_directive = "\n".join(directive_lines)

        return DAGPedagogicalContext(
            concept_id=target_node.id,
            concept_name=target_node.name,
            depth_level=target_node.depth_level,
            ancestors=ancestor_names,
            descendants=descendant_names,
            siblings=sibling_names,
            negative_boundaries=neg_boundaries,
            prompt_directive=prompt_directive,
        )

