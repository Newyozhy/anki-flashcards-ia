import pytest
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import ExtractedNoteKnowledge
from app.services.deck_dag_service import DeckDAGService, slugify_concept
from app.services.ontology_extractor_service import OntologyExtractorService


@pytest.fixture
def in_memory_store(tmp_path):
    db_file = tmp_path / "test_dag.db"
    return DeckKnowledgeStore(db_path=str(db_file))


@pytest.fixture
def dag_service(in_memory_store):
    return DeckDAGService(store=in_memory_store)


def test_slugify_concept():
    assert slugify_concept("OCI Route Table") == "oci_route_table"
    assert slugify_concept("  VCN & Subnets (v1) ") == "vcn_and_subnets_v1"
    assert slugify_concept("¿Qué es un CIDR?") == "que_es_un_cidr"
    assert slugify_concept("") == ""


def test_store_concept_nodes_and_edges(in_memory_store):
    deck = "Oracle Cloud"
    in_memory_store.upsert_concept_node(
        deck_name=deck,
        concept_id="oci_vcn",
        name="Virtual Cloud Network (VCN)",
        taxonomy_path="oci::networking",
        depth_level=0,
    )
    in_memory_store.upsert_concept_node(
        deck_name=deck,
        concept_id="oci_route_table",
        name="OCI Route Table",
        taxonomy_path="oci::networking::routing",
        depth_level=1,
    )
    in_memory_store.upsert_concept_edge(
        deck_name=deck,
        source_id="oci_vcn",
        target_id="oci_route_table",
        relation_type="requires",
    )
    in_memory_store.link_card_to_concept(
        deck_name=deck,
        note_id=101,
        concept_id="oci_route_table",
        role="target",
    )

    concepts = in_memory_store.get_deck_concepts(deck)
    assert len(concepts) == 2
    concept_ids = {c["id"] for c in concepts}
    assert concept_ids == {"oci_vcn", "oci_route_table"}

    edges = in_memory_store.get_deck_edges(deck)
    assert len(edges) == 1
    assert edges[0]["source"] == "oci_vcn"
    assert edges[0]["target"] == "oci_route_table"

    mappings = in_memory_store.get_card_concept_mappings(deck)
    assert len(mappings) == 1
    assert mappings[0]["note_id"] == 101
    assert mappings[0]["concept_id"] == "oci_route_table"


def test_dag_topological_sort_and_depth(dag_service):
    deck = "Oracle Cloud"

    # Card 1 defines Route Table, assumes VCN
    ext1 = ExtractedNoteKnowledge(
        source_note_id=101,
        raw_front="¿Qué es un Route Table?",
        raw_back="Es una tabla de reglas virtuales para subnets.",
        extracted_facts=["Route tables dirigen tráfico fuera de subnets."],
        target_concepts=["OCI Route Table"],
        assumed_prerequisites=["OCI VCN"],
        taxonomy_path="oci::networking::routing",
    )

    # Card 2 defines Internet Gateway, assumes Route Table and VCN
    ext2 = ExtractedNoteKnowledge(
        source_note_id=102,
        raw_front="¿Qué es un Internet Gateway en OCI?",
        raw_back="Es un router virtual que conecta una VCN pública a Internet.",
        extracted_facts=["Internet Gateway conecta la VCN a Internet."],
        target_concepts=["OCI Internet Gateway"],
        assumed_prerequisites=["OCI Route Table", "OCI VCN"],
        taxonomy_path="oci::networking::gateways",
    )

    dag = dag_service.ingest_note_extractions(deck, [ext1, ext2])

    assert dag.total_concepts == 3
    # Transitive reduction pruned redundant skip-edge 'oci_vcn' -> 'oci_internet_gateway'
    assert dag.total_edges == 2
    assert dag.transitive_reduction_applied is True
    assert dag.pruned_edges_count == 1
    assert not dag.has_cycles

    # Topological order MUST place prerequisites before target concepts
    # 'oci_vcn' -> 'oci_route_table' -> 'oci_internet_gateway'
    order = dag.topological_order
    assert order.index("oci_vcn") < order.index("oci_route_table")
    assert order.index("oci_route_table") < order.index("oci_internet_gateway")

    # Check depth levels and degrees
    node_map = {n.id: n for n in dag.nodes}
    assert node_map["oci_vcn"].depth_level == 0
    assert node_map["oci_route_table"].depth_level == 1
    assert node_map["oci_internet_gateway"].depth_level == 2
    assert node_map["oci_internet_gateway"].in_degree == 1
    assert node_map["oci_internet_gateway"].is_overloaded is False

    # Check orphan detection and formal statuses:
    # 'oci_vcn' is assumed as prerequisite in both cards, but NO card has 'oci_vcn' as target concept!
    assert "oci_vcn" in dag.orphan_concepts
    assert node_map["oci_vcn"].is_orphan is True
    assert node_map["oci_vcn"].status == "UNMAPPED"
    assert node_map["oci_route_table"].is_orphan is False
    assert node_map["oci_internet_gateway"].is_orphan is False


def test_dag_cycle_resolution(dag_service, in_memory_store):
    deck = "Test Cycles"
    # Artificially create a cycle: A -> B -> C -> A
    in_memory_store.upsert_concept_node(deck, "node_a", "Node A")
    in_memory_store.upsert_concept_node(deck, "node_b", "Node B")
    in_memory_store.upsert_concept_node(deck, "node_c", "Node C")

    in_memory_store.upsert_concept_edge(deck, "node_a", "node_b", "requires")
    in_memory_store.upsert_concept_edge(deck, "node_b", "node_c", "requires")
    in_memory_store.upsert_concept_edge(deck, "node_c", "node_a", "requires")

    dag = dag_service.get_deck_dag(deck)
    assert dag.has_cycles is True
    # Verify that cycle resolution produced a valid topological order without crashing
    assert len(dag.topological_order) == 3


@pytest.mark.asyncio
async def test_ontology_extractor_heuristic_fallback(in_memory_store, dag_service):
    extractor = OntologyExtractorService(
        store=in_memory_store,
        dag_service=dag_service,
        gemini_api_key=None,
        groq_api_key=None,
    )

    note = {
        "note_id": 501,
        "front": "¿Qué es un Load Balancer en OCI?",
        "back": "Distribuye el tráfico entre instancias de backend.",
        "tags": ["oci", "load_balancing"],
    }

    extraction = await extractor.extract_note_knowledge(note, ai_provider="none")
    assert extraction.source_note_id == 501
    assert len(extraction.extracted_facts) > 0
    assert len(extraction.target_concepts) > 0
    assert "load" in extraction.target_concepts[0].lower() or "balancer" in extraction.target_concepts[0].lower()


def test_slugify_concept_symbols_and_unicode():
    """Q2 regression: Preserve symbols and unicode characters safely."""
    assert slugify_concept("C++") == "c_plus_plus"
    assert slugify_concept("C#") == "c_sharp"
    assert slugify_concept("C") == "c"
    assert slugify_concept("SFP+") == "sfp_plus"
    assert slugify_concept("C++ / C#") == "c_plus_plus_slash_c_sharp"
    assert slugify_concept("SFP+ & GPON B+") == "sfp_plus_and_gpon_b_plus"
    assert slugify_concept("Network+") == "network_plus"
    # Unicode (Kanji / Kana / Cyrillic) should be preserved without collapsing
    assert "日本語" in slugify_concept("日本語 (Kanji)")
    assert "ルーティング" in slugify_concept("ルーティング (Routing)")
    assert slugify_concept("ルーティング (Routing)") != "unnamed_concept"


def test_hierarchical_cycle_breaking_removes_inverted_edge(dag_service, in_memory_store):
    """Q1 regression: Cycle between general concept and specific concept must remove inverted edge (specific -> general)."""
    deck = "Hierarchical Cycle Deck"
    in_memory_store.upsert_concept_node(deck, "c_gen", "OCI Networking", taxonomy_path="oci::networking")
    in_memory_store.upsert_concept_node(deck, "c_spec", "OCI Subnet CIDR", taxonomy_path="oci::networking::subnets::cidr")

    # Correct hierarchical edge: general -> specific
    in_memory_store.upsert_concept_edge(deck, "c_gen", "c_spec", "requires")
    # Inverted edge creating artificial cycle: specific -> general
    in_memory_store.upsert_concept_edge(deck, "c_spec", "c_gen", "requires")

    dag = dag_service.get_deck_dag(deck)
    assert dag.has_cycles is True
    # The topological order must place general (c_gen) before specific (c_spec)
    assert dag.topological_order.index("c_gen") < dag.topological_order.index("c_spec")


def test_stratified_generational_topological_sort_disjoint_branches(dag_service, in_memory_store):
    """G-02 regression: Topological order must strictly enforce depth generations across disjoint branches."""
    deck = "Disjoint Branches"
    # Branch A: A0 -> A1 -> A2
    in_memory_store.upsert_concept_node(deck, "a0", "Concept A0", depth_level=0)
    in_memory_store.upsert_concept_node(deck, "a1", "Concept A1", depth_level=1)
    in_memory_store.upsert_concept_node(deck, "a2", "Concept A2", depth_level=2)
    in_memory_store.upsert_concept_edge(deck, "a0", "a1", "requires")
    in_memory_store.upsert_concept_edge(deck, "a1", "a2", "requires")

    # Disjoint Branch B: B0 -> B1
    in_memory_store.upsert_concept_node(deck, "b0", "Concept B0", depth_level=0)
    in_memory_store.upsert_concept_node(deck, "b1", "Concept B1", depth_level=1)
    in_memory_store.upsert_concept_edge(deck, "b0", "b1", "requires")

    dag = dag_service.get_deck_dag(deck)
    order = dag.topological_order

    # Generational ordering guarantees:
    # All Level 0 nodes (a0, b0) MUST appear before ANY Level 1 nodes (a1, b1)
    # All Level 1 nodes (a1, b1) MUST appear before ANY Level 2 nodes (a2)
    pos_a0 = order.index("a0")
    pos_b0 = order.index("b0")
    pos_a1 = order.index("a1")
    pos_b1 = order.index("b1")
    pos_a2 = order.index("a2")

    assert max(pos_a0, pos_b0) < min(pos_a1, pos_b1), "Level 0 concepts must precede all Level 1 concepts"
    assert max(pos_a1, pos_b1) < pos_a2, "Level 1 concepts must precede all Level 2 concepts"


def test_multi_concept_card_placed_at_max_depth(dag_service, in_memory_store):
    """G-03 regression: Multi-concept card must be emitted at MAX concept depth, not min."""
    deck = "Multi Concept Deck"
    in_memory_store.upsert_concept_node(deck, "c_base", "Base Concept", depth_level=0)
    in_memory_store.upsert_concept_node(deck, "c_adv", "Advanced Concept", depth_level=2)
    in_memory_store.upsert_concept_edge(deck, "c_base", "c_adv", "requires")

    # Note 900 is mapped to BOTH base and advanced
    in_memory_store.link_card_to_concept(deck, 900, "c_base", role="target")
    in_memory_store.link_card_to_concept(deck, 900, "c_adv", role="target")

    # Note 800 is mapped ONLY to base
    in_memory_store.link_card_to_concept(deck, 800, "c_base", role="target")

    card_order = dag_service.get_topological_card_order(deck)
    # 800 belongs to c_base (level 0). 900 belongs to c_adv (level 2).
    # Therefore 800 must appear before 900!
    assert card_order.index(800) < card_order.index(900)


def test_intra_node_card_sorting_by_bloom_tier(dag_service, in_memory_store):
    """G-03 regression: Cards in same concept node must be sorted by Bloom tier, not note_id."""
    deck = "Intra Node Deck"
    in_memory_store.upsert_concept_node(deck, "c1", "Concept 1", depth_level=0)

    # Note 100 has smaller note_id but is a Tier 3 Contrast Matrix
    # Note 200 has larger note_id but is a Tier 1 Definition
    in_memory_store.save_note_embeddings(
        deck_name=deck,
        notes=[
            {
                "note_id": 100,
                "front": "Tabla comparativa entre A y B",
                "back": "Detalles",
                "tags": ["matriz"],
                "archetype": "B",
            },
            {
                "note_id": 200,
                "front": "¿Qué es el Concepto 1?",
                "back": "Definición fundamental",
                "tags": [],
                "archetype": "C",
            },
        ],
    )
    in_memory_store.link_card_to_concept(deck, 100, "c1", role="target")
    in_memory_store.link_card_to_concept(deck, 200, "c1", role="target")

    card_order = dag_service.get_topological_card_order(deck)
    # Note 200 (Tier 1) MUST appear before Note 100 (Tier 3)
    assert card_order == [200, 100]


def test_get_neighbor_concepts_colons(dag_service, in_memory_store):
    """G-05 regression: Taxonomy split by :: retrieves siblings correctly."""
    deck = "Taxonomy Deck"
    in_memory_store.upsert_concept_node(deck, "c_sub", "Subnet", taxonomy_path="oracle::networking::subnets")
    in_memory_store.upsert_concept_node(deck, "c_route", "Route Table", taxonomy_path="oracle::networking::routing")
    neighbors = dag_service.get_neighbor_concepts(deck, "Subnet")
    assert "Route Table" in neighbors


def test_sqlite_stage_id_preservation_and_debt_demotion(in_memory_store, dag_service):
    """G-04 regression: stage_id must not be overwritten by None/stage_1, and debt must demote MASTERED/SUFFICIENT to RAW."""
    deck = "Stage Test Deck"
    # 1. Initially insert node at stage_2 with status SUFFICIENT and mapped optimal card
    in_memory_store.upsert_concept_node(
        deck_name=deck,
        concept_id="sufficient_concept",
        name="Sufficient Concept",
        depth_level=0,
        status="SUFFICIENT",
        stage_id="stage_2",
    )
    in_memory_store.save_note_embeddings(
        deck_name=deck,
        notes=[{
            "note_id": 888,
            "front": "Sufficient card",
            "back": "Content",
            "quality_status": "optimal",
        }],
    )

    concepts = in_memory_store.get_deck_concepts(deck)
    assert concepts[0]["stage_id"] == "stage_2"
    assert concepts[0]["status"] == "SUFFICIENT"

    # 2. Simulate ingest_note_extractions updating the node without passing stage_id
    dag_service.ingest_note_extractions(
        deck_name=deck,
        extractions=[
            ExtractedNoteKnowledge(
                source_note_id=888,
                target_concepts=["Sufficient Concept"],
                assumed_prerequisites=[],
            )
        ],
    )
    concepts = in_memory_store.get_deck_concepts(deck)
    # Must preserve stage_2 and SUFFICIENT!
    assert concepts[0]["stage_id"] == "stage_2"
    assert concepts[0]["status"] == "SUFFICIENT"

    # 3. Initially insert node at stage_2 with status MASTERED
    in_memory_store.upsert_concept_node(
        deck_name=deck,
        concept_id="c_mastered",
        name="Mastered Concept",
        depth_level=0,
        status="MASTERED",
        stage_id="stage_2",
    )

    # 4. Add a card with technical debt ('bad' status) mapped to this node
    in_memory_store.save_note_embeddings(
        deck_name=deck,
        notes=[{
            "note_id": 999,
            "front": "Bad card",
            "back": "Bad",
            "quality_status": "bad",
        }],
    )
    in_memory_store.link_card_to_concept(deck, 999, "c_mastered", role="target")

    # Recompute DAG depths and statuses
    dag = dag_service.get_deck_dag(deck, recompute_depths=True)
    node = next(n for n in dag.nodes if n.id == "c_mastered")

    # Since note 999 is 'bad', the node must demote from MASTERED to RAW!
    assert node.status == "RAW"
    # And stage_id must still be stage_2
    concepts_after = in_memory_store.get_deck_concepts(deck)
    mastered_node = next(c for c in concepts_after if c["id"] == "c_mastered")
    assert mastered_node["stage_id"] == "stage_2"


@pytest.mark.asyncio
async def test_extract_deck_batch_remaining_unextracted_count(in_memory_store, dag_service):
    """G-11 & Phase 2 regression: extract_deck_batch must populate remaining_unextracted_count."""
    extractor = OntologyExtractorService(
        store=in_memory_store,
        dag_service=dag_service,
        gemini_api_key=None,
    )
    deck = "Batch Test Deck"
    notes = [
        {"note_id": 1, "front": "¿Qué es X?", "back": "X es Y"},
        {"note_id": 2, "front": "¿Qué es Z?", "back": "Z es W"},
        {"note_id": 3, "front": "¿Qué es Q?", "back": "Q es R"},
    ]

    res = await extractor.extract_deck_batch(
        deck_name=deck,
        notes=notes,
        batch_size=2,
        ai_provider="none",
    )
    assert res.processed_notes_count == 2
    assert res.remaining_unextracted_count == 1
    assert len(res.extracted_knowledge) == 2


@pytest.mark.asyncio
async def test_ontology_extractor_canonical_concepts_in_prompt_and_empty_batch(in_memory_store, dag_service):
    """G-07 and G-11 regression: Prompt must inject canonical vocabulary and empty unextracted notes terminate immediately."""
    extractor = OntologyExtractorService(
        store=in_memory_store,
        dag_service=dag_service,
        gemini_api_key=None,
    )
    deck = "Vocabulary Injection Deck"
    in_memory_store.upsert_concept_node(deck, "oci_vcn", "Virtual Cloud Network (VCN)")
    in_memory_store.upsert_concept_node(deck, "oci_subnets", "Subnets")

    # 1. Test prompt injection
    prompt = extractor._build_user_prompt(
        note={"note_id": 42, "front": "¿Qué es VCN?", "back": "Red virtual", "tags": ["oci"]},
        known_concepts=["Virtual Cloud Network (VCN)", "Subnets"],
    )
    assert "VOCABULARIO CANÓNICO EXISTENTE EN EL GRAFO" in prompt
    assert "'Virtual Cloud Network (VCN)'" in prompt
    assert "REGLA DE CONVERGENCIA ONTOLÓGICA" in prompt

    # 2. Test empty batch termination without LLM call
    res_empty = await extractor.extract_deck_batch(
        deck_name=deck,
        notes=[],
        batch_size=10,
        ai_provider="none",
    )
    assert res_empty.processed_notes_count == 0
    assert res_empty.remaining_unextracted_count == 0
    assert res_empty.extracted_knowledge == []

