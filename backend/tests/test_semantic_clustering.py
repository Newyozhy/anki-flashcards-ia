import pytest
from unittest.mock import AsyncMock, patch

from app.core.clustering import (
    normalize_vector,
    dot_product,
    determine_optimal_k,
    spherical_kmeans,
)
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.services.deck_intelligence_service import DeckIntelligenceService


def test_vector_normalization_and_dot_product():
    v1 = [3.0, 4.0]
    norm1 = normalize_vector(v1)
    assert pytest.approx(norm1[0], 0.001) == 0.6
    assert pytest.approx(norm1[1], 0.001) == 0.8

    # Dot product of identical normalized vectors is 1.0
    sim = dot_product(norm1, norm1)
    assert pytest.approx(sim, 0.001) == 1.0

    # Orthogonal vectors have dot product 0.0
    v2 = [-4.0, 3.0]
    norm2 = normalize_vector(v2)
    assert pytest.approx(dot_product(norm1, norm2), 0.001) == 0.0


def test_determine_optimal_k():
    assert determine_optimal_k(2) == 2
    assert determine_optimal_k(10) == 3
    assert determine_optimal_k(25) == 4
    assert determine_optimal_k(85) == 5
    assert determine_optimal_k(150) == 6


def test_spherical_kmeans_synthetic_clusters():
    # 3 distinct orthogonal synthetic clusters in 4 dimensions
    # Cluster A: centered near [1, 0, 0, 0]
    # Cluster B: centered near [0, 1, 0, 0]
    # Cluster C: centered near [0, 0, 1, 0]
    items = [
        {"note_id": 1, "vec": [0.95, 0.05, 0.0, 0.0]},
        {"note_id": 2, "vec": [0.90, 0.10, 0.0, 0.0]},
        {"note_id": 3, "vec": [0.98, 0.02, 0.0, 0.0]},
        {"note_id": 10, "vec": [0.05, 0.95, 0.0, 0.0]},
        {"note_id": 11, "vec": [0.10, 0.90, 0.0, 0.0]},
        {"note_id": 12, "vec": [0.02, 0.98, 0.0, 0.0]},
        {"note_id": 20, "vec": [0.0, 0.0, 0.95, 0.05]},
        {"note_id": 21, "vec": [0.0, 0.0, 0.90, 0.10]},
        {"note_id": 22, "vec": [0.0, 0.0, 0.98, 0.02]},
    ]

    res = spherical_kmeans(items, k=3, seed=42)
    assert res.k == 3
    assert len(res.clusters) == 3

    # Every item must be partitioned
    all_assigned = []
    for c in res.clusters:
        all_assigned.extend(c.note_ids)
        assert len(c.representative_note_ids) > 0
    assert sorted(all_assigned) == [1, 2, 3, 10, 11, 12, 20, 21, 22]


def test_deck_knowledge_store_cluster_persistence(tmp_path):
    db_path = str(tmp_path / "test_clusters.db")
    store = DeckKnowledgeStore(db_path=db_path)

    # Insert notes
    notes = [
        {"note_id": 101, "front": "Note 1", "back": "Ans 1", "embedding": [1.0, 0.0, 0.0]},
        {"note_id": 102, "front": "Note 2", "back": "Ans 2", "embedding": [0.0, 1.0, 0.0]},
    ]
    store.save_note_embeddings("TestDeck", notes)

    clusters_to_save = [
        {
            "cluster_index": 0,
            "title": "Redes Cloud",
            "scope": "Conceptos de conectividad VCN y subredes.",
            "note_ids": [101],
            "centroid_note_ids": [101],
        },
        {
            "cluster_index": 1,
            "title": "Almacenamiento",
            "scope": "Volúmenes en bloque y buckets de objetos.",
            "note_ids": [102],
            "centroid_note_ids": [102],
        },
    ]

    store.save_deck_clusters("TestDeck", clusters_to_save)
    retrieved = store.get_deck_clusters("TestDeck")
    assert len(retrieved) == 2
    assert retrieved[0]["title"] == "Redes Cloud"
    assert retrieved[0]["note_ids"] == [101]
    assert retrieved[1]["title"] == "Almacenamiento"
    assert retrieved[1]["note_ids"] == [102]

    # Verify indexed_notes has cluster_name updated
    indexed = store.get_all_indexed_notes("TestDeck")
    assert len(indexed) == 2
    n101 = next(n for n in indexed if n["note_id"] == 101)
    n102 = next(n for n in indexed if n["note_id"] == 102)
    assert n101["cluster_name"] == "Redes Cloud"
    assert n102["cluster_name"] == "Almacenamiento"


@pytest.mark.asyncio
async def test_deck_intelligence_service_category_extraction():
    store = AsyncMock()
    anki_bridge = AsyncMock()
    embedding_port = AsyncMock()
    service = DeckIntelligenceService(
        anki_bridge=anki_bridge,
        embedding_port=embedding_port,
        store=store,
    )

    # 1. Breadcrumbs priority
    note_with_bc = {"front": "[Bases de Datos > NoSQL] Qué es MongoDB?", "cluster_name": "Cluster IA", "tags": ["tag1"]}
    assert service._extract_category_for_note(note_with_bc) == "Bases de Datos"

    # 2. Cluster name priority if no breadcrumbs
    note_with_cluster = {"front": "Qué es un agente?", "cluster_name": "Arquitectura de Agentes", "tags": ["tag1"]}
    assert service._extract_category_for_note(note_with_cluster) == "Arquitectura de Agentes"

    # 3. First tag priority if no breadcrumbs and no cluster
    note_with_tag = {"front": "Qué es un agente?", "cluster_name": None, "tags": ["Redes", "DevOps"]}
    assert service._extract_category_for_note(note_with_tag) == "Redes"

    # 4. Fallback to General
    note_naked = {"front": "Concepto suelto", "cluster_name": None, "tags": []}
    assert service._extract_category_for_note(note_naked) == "General"
