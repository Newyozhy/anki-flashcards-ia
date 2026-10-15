import tempfile
from pathlib import Path
import pytest
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore, _cosine_similarity


def test_cosine_similarity_edge_cases():
    """Verify vector cosine math for identical, orthogonal, opposite, and mismatched vectors."""
    # Identical vectors -> 1.0
    assert pytest.approx(_cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1e-4) == 1.0

    # Orthogonal vectors -> 0.0
    assert pytest.approx(_cosine_similarity([1.0, 0.0], [0.0, 1.0]), 1e-4) == 0.0

    # Opposite vectors -> -1.0
    assert pytest.approx(_cosine_similarity([1.0, 0.0], [-1.0, 0.0]), 1e-4) == -1.0

    # Empty or zero vectors
    assert _cosine_similarity([], []) == 0.0
    assert _cosine_similarity([0.0, 0.0], [0.0, 0.0]) == 0.0
    assert _cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_deck_knowledge_store_crud_and_search():
    """Verify SQLite persistence, float32 embedding packing/unpacking, and semantic similarity search."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_knowledge.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        deck_name = "Ciencias::Física"

        # Initially empty
        assert store.get_indexed_note_ids(deck_name) == set()
        stats = store.get_deck_stats(deck_name)
        assert stats["total_indexed"] == 0
        assert stats["last_indexed_at"] is None

        # Prepare 3 notes with normalized 3D vectors
        # Note 1: [1.0, 0.0, 0.0] - Termodinámica
        # Note 2: [0.0, 1.0, 0.0] - Electromagnetismo
        # Note 3: [0.7071, 0.7071, 0.0] - Física Estadística (mix)
        notes = [
            {
                "note_id": 101,
                "front": "¿Qué establece el primer principio de la termodinámica?",
                "back": "La energía no se crea ni se destruye, solo se transforma.",
                "explanation": "⚠️ Trampa frecuente: no confundir conservación con entropía.",
                "tags": ["física", "termodinámica"],
                "clean_text": "primer principio termodinamica | conservacion energia",
                "embedding": [1.0, 0.0, 0.0],
            },
            {
                "note_id": 102,
                "front": "¿Qué describe la Ley de Gauss?",
                "back": "El flujo del campo eléctrico a través de una superficie cerrada.",
                "explanation": "⚠️ Trampa frecuente: es proporcional a la carga neta encerrada.",
                "tags": ["física", "electromagnetismo"],
                "clean_text": "ley de gauss | flujo electrico",
                "embedding": [0.0, 1.0, 0.0],
            },
            {
                "note_id": 103,
                "front": "¿Qué relaciona la distribución de Maxwell-Boltzmann?",
                "back": "La velocidad de las partículas con la temperatura del sistema.",
                "explanation": None,
                "tags": ["física", "estadística"],
                "clean_text": "maxwell boltzmann | distribucion velocidades",
                "embedding": [0.707106, 0.707106, 0.0],
            },
        ]

        store.save_note_embeddings(deck_name, notes)

        # Check indexed IDs
        indexed_ids = store.get_indexed_note_ids(deck_name)
        assert indexed_ids == {101, 102, 103}

        # Check stats
        stats = store.get_deck_stats(deck_name)
        assert stats["total_indexed"] == 3
        assert stats["last_indexed_at"] is not None

        # Search with vector aligned with Note 1 ([1.0, 0.0, 0.0])
        results = store.semantic_search(
            deck_name=deck_name,
            query_embedding=[1.0, 0.0, 0.0],
            top_k=5,
            min_similarity=0.4,
        )

        assert len(results) == 2
        # Note 1 should be highest (similarity ~1.0)
        assert results[0]["note_id"] == 101
        assert pytest.approx(results[0]["similarity"], 1e-2) == 1.0
        assert "termodinámica" in results[0]["tags"]

        # Note 3 should be second (similarity ~0.7071)
        assert results[1]["note_id"] == 103
        assert pytest.approx(results[1]["similarity"], 1e-2) == 0.71

        # Note 2 has similarity 0.0, below min_similarity 0.4, so it should not appear
        result_ids = [r["note_id"] for r in results]
        assert 102 not in result_ids


def test_deck_knowledge_store_delete_note_embeddings():
    """Verify deleting obsolete note embeddings updates the index and metadata counts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_delete.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        deck_name = "Ciencias::Física"
        notes = [
            {
                "note_id": 201,
                "front": "Front 1",
                "back": "Back 1",
                "embedding": [1.0, 0.0, 0.0],
            },
            {
                "note_id": 202,
                "front": "Front 2",
                "back": "Back 2",
                "embedding": [0.0, 1.0, 0.0],
            },
            {
                "note_id": 203,
                "front": "Front 3",
                "back": "Back 3",
                "embedding": [0.0, 0.0, 1.0],
            },
        ]
        store.save_note_embeddings(deck_name, notes)
        assert store.get_indexed_note_ids(deck_name) == {201, 202, 203}
        assert store.get_deck_stats(deck_name)["total_indexed"] == 3

        # Delete note 202
        store.delete_note_embeddings(deck_name, [202])
        assert store.get_indexed_note_ids(deck_name) == {201, 203}
        assert store.get_deck_stats(deck_name)["total_indexed"] == 2

        # Deleting empty list does nothing
        store.delete_note_embeddings(deck_name, [])
        assert store.get_indexed_note_ids(deck_name) == {201, 203}

        # Delete remaining notes
        store.delete_note_embeddings(deck_name, [201, 203])
        assert store.get_indexed_note_ids(deck_name) == set()
        assert store.get_deck_stats(deck_name)["total_indexed"] == 0


def test_deck_knowledge_store_semantic_search_exclude_note_ids():
    """Verify that semantic_search accurately filters out notes specified in exclude_note_ids."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_exclude.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        deck_name = "Ciencias::Física"
        notes = [
            {
                "note_id": 301,
                "front": "Termodinámica",
                "back": "Conservación",
                "embedding": [1.0, 0.0, 0.0],
            },
            {
                "note_id": 302,
                "front": "Física Estadística",
                "back": "Entropía",
                "embedding": [0.8, 0.6, 0.0],
            },
            {
                "note_id": 303,
                "front": "Electromagnetismo",
                "back": "Maxwell",
                "embedding": [0.0, 1.0, 0.0],
            },
        ]
        store.save_note_embeddings(deck_name, notes)

        # 1. Search without exclusions (query: [1.0, 0.0, 0.0]) -> matches 301 (sim 1.0) and 302 (sim 0.8)
        res_all = store.semantic_search(
            deck_name=deck_name,
            query_embedding=[1.0, 0.0, 0.0],
            min_similarity=0.4,
        )
        assert len(res_all) == 2
        assert res_all[0]["note_id"] == 301
        assert res_all[1]["note_id"] == 302

        # 2. Exclude source note 301
        res_excluded = store.semantic_search(
            deck_name=deck_name,
            query_embedding=[1.0, 0.0, 0.0],
            min_similarity=0.4,
            exclude_note_ids=[301],
        )
        assert len(res_excluded) == 1
        assert res_excluded[0]["note_id"] == 302
        assert all(r["note_id"] != 301 for r in res_excluded)

        # 3. Exclude both 301 and 302 -> No candidates match above threshold
        res_none = store.semantic_search(
            deck_name=deck_name,
            query_embedding=[1.0, 0.0, 0.0],
            min_similarity=0.4,
            exclude_note_ids=[301, 302],
        )
        assert len(res_none) == 0


def test_deck_knowledge_store_content_deduplication():
    """Verify that saving a note with identical front/back under a new note_id purges the obsolete record."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_dedup.db"
        store = DeckKnowledgeStore(db_path=str(db_path))
        deck = "Test::Dedup"

        # 1. Insert original note #100
        store.save_note_embeddings(
            deck,
            [
                {
                    "note_id": 100,
                    "front": "Concept Front",
                    "back": "Concept Back",
                    "embedding": [1.0, 0.0],
                }
            ],
        )
        assert store.get_indexed_note_ids(deck) == {100}

        # 2. Insert same content under new note #200 (re-generation scenario)
        store.save_note_embeddings(
            deck,
            [
                {
                    "note_id": 200,
                    "front": "Concept Front",
                    "back": "Concept Back",
                    "embedding": [1.0, 0.0],
                }
            ],
        )
        # Note #100 must be purged, only #200 remains
        assert store.get_indexed_note_ids(deck) == {200}
        stats = store.get_deck_stats(deck)
        assert stats["total_indexed"] == 1


def test_get_cluster_sibling_boundaries():
    """Verify that cluster sibling boundaries extract neighbor concepts and exclude current note."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_boundaries.db"
        store = DeckKnowledgeStore(db_path=str(db_path))
        deck = "Test::Agents"

        # 1. Insert 3 notes in same cluster
        notes = [
            {
                "note_id": 101,
                "front": "[AI Agents > Execution > Agent Loop] ¿Cómo opera el bucle iterativo?",
                "back": "Thought -> Action -> Observation.",
                "embedding": [1.0, 0.0],
            },
            {
                "note_id": 102,
                "front": "[AI Agents > Tools > Tool Schemas] ¿Qué define el schema JSON?",
                "back": "Firma y parámetros de la herramienta.",
                "embedding": [0.9, 0.1],
            },
            {
                "note_id": 103,
                "front": "[AI Agents > Prompting > ReAct Pattern] ¿Por qué ReAct reduce alucinaciones?",
                "back": "Grounding en observaciones externas.",
                "embedding": [0.8, 0.2],
            },
        ]
        store.save_note_embeddings(deck, notes)

        # 2. Save cluster linking 101, 102, 103
        store.save_deck_clusters(
            deck,
            [
                {
                    "cluster_index": 0,
                    "title": "Arquitectura Agentes IA",
                    "scope": "Bucle, herramientas y patrones de razonamiento.",
                    "note_ids": [101, 102, 103],
                }
            ],
        )

        # 3. Request boundaries for Note 101 (Agent Loop)
        boundaries_for_101 = store.get_cluster_sibling_boundaries(deck, note_id=101)
        # Must include sibling concepts (Tool Schemas, ReAct Pattern)
        assert "Tool Schemas" in boundaries_for_101
        assert "ReAct Pattern" in boundaries_for_101
        # Must NOT include Note 101 itself (Agent Loop)
        assert "Agent Loop" not in boundaries_for_101

        # 4. Request boundaries for Note 102 (Tool Schemas)
        boundaries_for_102 = store.get_cluster_sibling_boundaries(deck, note_id=102)
        assert "Agent Loop" in boundaries_for_102
        assert "ReAct Pattern" in boundaries_for_102
        assert "Tool Schemas" not in boundaries_for_102


def test_sanitation_coverage_ledger_crud():
    """Verify sanitation_coverage_ledger insertion, retrieval, JSON parsing, and cascading note cleanup."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_ledger.db"
        store = DeckKnowledgeStore(db_path=str(db_path))
        deck = "Redes::Modelo OSI"

        # Initially empty ledger for colliding note 200
        entries = store.get_ledger_entries_for_note(deck, note_id=200)
        assert entries == []

        # Record coverage from Note 100 into colliding Note 200
        lid = store.record_ledger_coverage(
            deck_name=deck,
            source_note_id=100,
            colliding_note_id=200,
            concept_title="Encapsulamiento PDU",
            facet_summary="Diferencia de headers entre L2 y L3",
            created_atomic_note_ids=[1001, 1002, 1003],
        )
        assert lid > 0

        # Also save fake extracted knowledge for Note 200 to test cascade delete
        store.save_note_extracted_knowledge(
            deck_name=deck,
            note_id=200,
            raw_front="Monolito",
            raw_back="Explicación",
            extracted_facts=["f1"],
            target_concepts=["c1"],
            assumed_prerequisites=[],
            taxonomy_path="osi",
        )

        # Retrieve ledger entries
        entries = store.get_ledger_entries_for_note(deck, note_id=200)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["id"] == lid
        assert entry["source_sanitized_note_id"] == 100
        assert entry["colliding_pending_note_id"] == 200
        assert entry["covered_concept_title"] == "Encapsulamiento PDU"
        assert entry["covered_facet_summary"] == "Diferencia de headers entre L2 y L3"
        assert entry["created_atomic_note_ids"] == [1001, 1002, 1003]

        # Purge ledger and extracted knowledge for Note 200
        deleted_count = store.delete_ledger_entries_for_note(deck, note_id=200)
        assert deleted_count == 1
        assert store.get_ledger_entries_for_note(deck, note_id=200) == []

        # Extracted knowledge must also be purged
        assert store.get_note_extracted_knowledge(deck, note_id=200) is None


def test_concept_node_stage_id_and_preevaluated_migration():
    """Verify concept_nodes stage_id persistence and preevaluated -> optimal status migration."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_stage_mig.db"
        store = DeckKnowledgeStore(db_path=str(db_path))
        deck = "Cloud::AWS"

        # 1. Upsert concept with stage_id
        store.upsert_concept_node(
            deck_name=deck,
            concept_id="vpc_peering",
            name="VPC Peering",
            taxonomy_path="aws::vpc",
            depth_level=2,
            stage_id="stage_2_advanced",
        )

        concepts = store.get_deck_concepts(deck)
        assert len(concepts) == 1
        assert concepts[0]["id"] == "vpc_peering"
        assert concepts[0]["stage_id"] == "stage_2_advanced"

        # 2. Insert a note directly with quality_status='preevaluated' using raw connection
        with store._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO indexed_notes (deck_name, note_id, front, back, clean_text, quality_status, updated_at)
                VALUES (?, ?, ?, ?, ?, 'preevaluated', '2026-01-01')
                """,
                (deck, 555, "Q", "A", "Q A"),
            )
            conn.commit()

        # Re-initialize store DB on the same file to trigger migrations
        store2 = DeckKnowledgeStore(db_path=str(db_path))

        with store2._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT quality_status FROM indexed_notes WHERE note_id = 555")
            row = cursor.fetchone()
            # Must be migrated to optimal
            assert row["quality_status"] == "optimal"



