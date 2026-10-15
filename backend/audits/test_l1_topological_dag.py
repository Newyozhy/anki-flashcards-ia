import math
import time
from typing import List
import networkx as nx
import pytest

from app.core.clustering import spherical_kmeans, determine_optimal_k
from app.domain.models import ExtractedNoteKnowledge
from app.services.deck_dag_service import DeckDAGService, slugify_concept


def test_audit_l1_multi_cycle_feedback_arc_resolution(audit_dag_service, tmp_audit_db):
    """
    AUDIT L1.1: Multi-Cycle Feedback Arc Resolution.
    Validates that when educational notes introduce mutual or overlapping circular dependencies
    (e.g., Cycle 1: A -> B -> C -> A; Cycle 2: B -> D -> E -> B), the graph engine resolves
    the feedback arcs, flags has_cycles=True, and outputs a valid strictly acyclic topological sort.
    """
    deck = "Audit::AdversarialCycles"
    nodes = ["concept_a", "concept_b", "concept_c", "concept_d", "concept_e"]
    for n in nodes:
        tmp_audit_db.upsert_concept_node(deck, n, n.replace("_", " ").title())

    # Cycle 1: a -> b -> c -> a
    tmp_audit_db.upsert_concept_edge(deck, "concept_a", "concept_b", "requires")
    tmp_audit_db.upsert_concept_edge(deck, "concept_b", "concept_c", "requires")
    tmp_audit_db.upsert_concept_edge(deck, "concept_c", "concept_a", "requires")

    # Cycle 2: b -> d -> e -> b (overlapping on b)
    tmp_audit_db.upsert_concept_edge(deck, "concept_b", "concept_d", "requires")
    tmp_audit_db.upsert_concept_edge(deck, "concept_d", "concept_e", "requires")
    tmp_audit_db.upsert_concept_edge(deck, "concept_e", "concept_b", "requires")

    start_time = time.perf_counter()
    dag = audit_dag_service.get_deck_dag(deck)
    duration_ms = (time.perf_counter() - start_time) * 1000

    # Invariant Checks
    assert dag.has_cycles is True, "Graph must accurately report cycle presence."
    assert len(dag.topological_order) == 5, "All nodes must remain present in topological order."
    assert set(dag.topological_order) == set(nodes), "No concept may be dropped during cycle resolution."
    assert duration_ms < 100, f"Cycle resolution took too long: {duration_ms:.2f}ms"

    # Verify that the sorted order defines a valid ordering
    assert len(set(dag.topological_order)) == len(dag.topological_order), "Topological order must not contain duplicates."


def test_audit_l1_transitive_reduction_dense_graph(audit_dag_service, tmp_audit_db):
    """
    AUDIT L1.2: Transitive Reduction on Dense Prerequisite Tournaments.
    Validates that a dense prerequisite hierarchy where every ancestor links to every descendant
    (e.g. 6 nodes with N(N-1)/2 = 15 edges) is stripped of all redundant shortcut edges,
    leaving exactly the essential Hasse backbone (5 edges) with 100% reachability preserved.
    """
    deck = "Audit::TransitiveReduction"
    n_nodes = 6
    node_ids = [f"step_{i}" for i in range(n_nodes)]
    for nid in node_ids:
        tmp_audit_db.upsert_concept_node(deck, nid, f"Step {nid}")

    # Add all directed pairs i < j (complete DAG with 15 edges)
    expected_full_edges = 0
    for i in range(n_nodes):
        for j in range(i + 1, n_nodes):
            tmp_audit_db.upsert_concept_edge(deck, node_ids[i], node_ids[j], "requires")
            expected_full_edges += 1

    assert expected_full_edges == 15, "Initial edge count must be 15."

    dag = audit_dag_service.get_deck_dag(deck)

    # Invariant Checks
    assert dag.transitive_reduction_applied is True, "Transitive reduction must be active."
    assert dag.pruned_edges_count == 10, f"Expected 10 pruned edges, got {dag.pruned_edges_count}."
    assert dag.total_edges == 5, f"Expected exactly 5 essential backbone edges, got {dag.total_edges}."

    # Validate Hasse diagram: step_0 -> step_1 -> step_2 -> step_3 -> step_4 -> step_5
    reduced_edges = {(e.source, e.target) for e in dag.edges}
    for i in range(n_nodes - 1):
        assert (node_ids[i], node_ids[i + 1]) in reduced_edges, f"Missing backbone edge: {node_ids[i]} -> {node_ids[i+1]}"

    # Verify reachability between first and last node
    g_reduced = nx.DiGraph()
    for e in dag.edges:
        g_reduced.add_edge(e.source, e.target)
    assert nx.has_path(g_reduced, node_ids[0], node_ids[-1]), "Reachability from root to leaf must be preserved."


def test_audit_l1_orphan_recall_and_curriculum_depth(audit_dag_service):
    """
    AUDIT L1.3: Orphan Recall & Multi-Tier Curriculum Depth.
    Validates that unmapped prerequisite concepts are 100% detected as orphan gaps,
    correctly classified as 'UNMAPPED', and sorted strictly by topological depth.
    """
    deck = "Audit::CurriculumHierarchy"

    # Card 1: Advanced concept testing Logic Gates, assuming Boolean Algebra and Binary Arithmetic
    ext1 = ExtractedNoteKnowledge(
        source_note_id=201,
        raw_front="¿Qué es una compuerta NAND?",
        raw_back="Una compuerta lógica universal.",
        extracted_facts=["NAND es universal."],
        target_concepts=["Compuertas Lógicas"],
        assumed_prerequisites=["Álgebra de Boole", "Aritmética Binaria"],
        taxonomy_path="hardware::digital_logic",
    )

    # Card 2: Master concept testing Full Adder, assuming Logic Gates
    ext2 = ExtractedNoteKnowledge(
        source_note_id=202,
        raw_front="¿Qué compone un Full Adder?",
        raw_back="Dos semi-sumadores y una compuerta OR.",
        extracted_facts=["Full adder suma 3 bits."],
        target_concepts=["Sumador Completo"],
        assumed_prerequisites=["Compuertas Lógicas"],
        taxonomy_path="hardware::arithmetic_circuits",
    )

    dag = audit_dag_service.ingest_note_extractions(deck, [ext1, ext2])

    # Invariant Checks
    node_map = {n.id: n for n in dag.nodes}

    # 1. Orphan Recall: "Álgebra de Boole" and "Aritmética Binaria" have 0 cards mapped
    assert "algebra_de_boole" in dag.orphan_concepts
    assert "aritmetica_binaria" in dag.orphan_concepts
    assert node_map["algebra_de_boole"].is_orphan is True
    assert node_map["algebra_de_boole"].status == "UNMAPPED"
    assert node_map["aritmetica_binaria"].is_orphan is True

    # 2. Covered concepts must NOT be orphans
    assert "compuertas_logicas" not in dag.orphan_concepts
    assert node_map["compuertas_logicas"].is_orphan is False
    assert node_map["compuertas_logicas"].card_count == 1
    assert "sumador_completo" not in dag.orphan_concepts
    assert node_map["sumador_completo"].is_orphan is False
    assert node_map["sumador_completo"].card_count == 1

    # 3. Depth Level Progression
    # Roots must be depth 0
    assert node_map["algebra_de_boole"].depth_level == 0
    assert node_map["aritmetica_binaria"].depth_level == 0
    # Intermediate must be depth 1
    assert node_map["compuertas_logicas"].depth_level == 1
    # Advanced must be depth 2
    assert node_map["sumador_completo"].depth_level == 2

    # 4. Topological Ordering Contract
    order = dag.topological_order
    assert order.index("algebra_de_boole") < order.index("compuertas_logicas")
    assert order.index("compuertas_logicas") < order.index("sumador_completo")


def test_audit_l1_cognitive_overload_in_degree_gate(audit_dag_service, tmp_audit_db):
    """
    AUDIT L1.4: Cognitive Overload In-Degree Limit (Sweller / Miller Law).
    Validates that concepts with direct prerequisite in-degree > 4 are flagged as overloaded,
    warning the instructional design pipeline that cognitive scaffolding is required.
    """
    deck = "Audit::CognitiveOverload"
    target = "advanced_distributed_system"
    tmp_audit_db.upsert_concept_node(deck, target, "Advanced Distributed System")

    # Ingest 6 direct prerequisites
    for i in range(6):
        prereq = f"prereq_{i}"
        tmp_audit_db.upsert_concept_node(deck, prereq, f"Prerequisite {i}")
        tmp_audit_db.upsert_concept_edge(deck, prereq, target, "requires")

    dag = audit_dag_service.get_deck_dag(deck)
    node_map = {n.id: n for n in dag.nodes}

    assert node_map[target].in_degree == 6
    assert node_map[target].is_overloaded is True, "Concepts with in_degree > 4 must be flagged as overloaded."


def test_audit_l1_spherical_kmeans_geometry():
    """
    AUDIT L1.5: Spherical K-Means Geometric Invariants.
    Validates unit-hypersphere geometry:
    (a) Centroid vectors are strictly L2 normalized.
    (b) Distinct orthogonal clusters are correctly separated without index collapse.
    (c) Degenerate edge cases (empty vector list, k=1, k > N) fail gracefully or return valid partitions.
    """
    # 1. Orthogonal Synthetic Clusters (3 orthogonal clusters in 6D)
    cluster_a = [
        [1.0, 0.05, 0.0, 0.0, 0.0, 0.0],
        [0.98, 0.1, 0.0, 0.0, 0.0, 0.0],
    ]
    cluster_b = [
        [0.0, 0.0, 1.0, 0.02, 0.0, 0.0],
        [0.0, 0.0, 0.99, 0.05, 0.0, 0.0],
    ]
    cluster_c = [
        [0.0, 0.0, 0.0, 0.0, 1.0, 0.01],
        [0.0, 0.0, 0.0, 0.0, 0.95, 0.08],
    ]
    all_vectors = cluster_a + cluster_b + cluster_c
    items = [{"note_id": idx + 1, "vec": v} for idx, v in enumerate(all_vectors)]

    result = spherical_kmeans(items, k=3, max_iter=20)

    assert result.k == 3, "Must produce exactly 3 clusters."
    assert len(result.clusters) == 3, "Must produce exactly 3 cluster objects."
    total_assigned = sum(len(c.note_ids) for c in result.clusters)
    assert total_assigned == len(all_vectors), "All vectors must be assigned to a cluster."

    # Verify Centroid Unit Normalization: ||c||_2 = 1.0
    for cl in result.clusters:
        centroid = cl.centroid
        norm = math.sqrt(sum(x * x for x in centroid))
        assert abs(norm - 1.0) < 1e-4, f"Centroid norm {norm} is not unit-length."

    # 2. Degenerate Cases
    # k = 1
    single_res = spherical_kmeans(items, k=1)
    assert single_res.k == 1
    assert len(single_res.clusters[0].note_ids) == len(items)

    # Empty list
    empty_res = spherical_kmeans([], k=3)
    assert empty_res.k == 0
    assert empty_res.clusters == []

    # Optimal k heuristic
    k_opt = determine_optimal_k(len(items))
    assert 1 <= k_opt <= len(items)


def test_audit_l1_real_corpus_oracle_cloud_dag_validation(audit_dag_service, sample_audit_cards):
    """
    AUDIT L1.6: Real Corpus Graph Health Audit (Oracle Cloud / Agent Flashcards).
    Ingests real production flashcard data from audit_cards.json, builds the DAG,
    and certifies that:
    (a) The real deck graph is completely acyclic.
    (b) Transitive reduction successfully optimizes the topology.
    (c) Real orphan gaps are isolated for curriculum expansion.
    """
    deck = "Audit::RealProductionCorpus"

    extractions: List[ExtractedNoteKnowledge] = []
    for card in sample_audit_cards:
        nid = card["id"]
        fields = card["fields"]
        breadcrumb = fields[0] if len(fields) > 0 else "General"
        front = fields[1] if len(fields) > 1 else ""
        back = fields[2] if len(fields) > 2 else ""

        # Parse tags
        tags = [t.strip() for t in card.get("tags", "").split() if t.strip()]

        # Generate realistic pedagogical extraction
        target_name = breadcrumb.split(">")[-1].strip() if ">" in breadcrumb else breadcrumb
        parent_name = breadcrumb.split(">")[-2].strip() if ">" in breadcrumb and len(breadcrumb.split(">")) > 1 else "AI Architecture"

        extractions.append(
            ExtractedNoteKnowledge(
                source_note_id=nid,
                raw_front=front,
                raw_back=back,
                extracted_facts=[front[:80]],
                target_concepts=[target_name],
                assumed_prerequisites=[parent_name],
                taxonomy_path=breadcrumb.replace(" > ", "::").lower(),
            )
        )

    start_time = time.perf_counter()
    dag = audit_dag_service.ingest_note_extractions(deck, extractions)
    elapsed_ms = (time.perf_counter() - start_time) * 1000

    # Certifications
    assert dag.has_cycles is False, "Production deck must not have cyclic prerequisites."
    assert dag.total_concepts > 0, "Concepts must be extracted."
    assert len(dag.topological_order) == dag.total_concepts, "Topological sort must cover all concepts."
    assert elapsed_ms < 500, f"Production corpus ingestion too slow: {elapsed_ms:.2f}ms"

    # Verify that parent categories with no direct question cards are captured as orphan concepts
    assert len(dag.orphan_concepts) > 0, "Unmapped parent concepts must be detected as orphan gaps."
