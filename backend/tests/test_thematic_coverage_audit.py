import json
import tempfile
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    CoverageGapStatus,
    CoveredFacet,
    OrphanGap,
    TopicCoverageAuditRequest,
    TopicCoverageAuditResponse,
    UpdateGapStatusRequest,
    DeckCoverageMapResponse,
    ListDeckAuditsResponse,
)
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.ports.embedding_port import IEmbeddingPort
from app.ports.card_generator_port import ICardGeneratorPort
from app.services.deck_intelligence_service import DeckIntelligenceService
from app.main import app
from app.api.deps import (
    get_deck_knowledge_store,
    get_deck_intelligence_service,
    get_anki_connect_adapter,
)


class MockAnkiBridge(IAnkiBridgePort):
    def __init__(self, notes: List[dict]):
        self.notes = notes
        self.updated_fields = {}

    async def check_status(self):
        return None

    async def get_deck_names(self):
        return ["Medicina::Cardio"]

    async def export_cards(self, deck_name: str, cards):
        return None

    async def get_deck_notes(self, deck_name: str) -> List[dict]:
        return self.notes

    async def get_notes_info(self, note_ids: List[int]) -> List[dict]:
        return []

    async def retrieve_media_base64(self, filename: str):
        return None

    async def update_note_fields(self, note_id: int, fields):
        self.updated_fields[note_id] = fields
        return True

    async def delete_notes(self, note_ids):
        return True


class MockEmbeddingPort(IEmbeddingPort):
    def __init__(self, vector_map: Optional[dict] = None):
        self.vector_map = vector_map or {}
        self.default_vector = [1.0, 0.0, 0.0]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        results = []
        for t in texts:
            matched = False
            for k, vec in self.vector_map.items():
                if k.lower() in t.lower():
                    results.append(vec)
                    matched = True
                    break
            if not matched:
                results.append(self.default_vector)
        return results

    async def embed_single(self, text: str) -> List[float]:
        res = await self.embed_texts([text])
        return res[0]


class MockCardGeneratorForAudit:
    async def audit_topic_coverage(self, system_instruction: str, user_prompt: str):
        return {
            "coverage_percentage": 70,
            "summary_assessment": "Buena cobertura en diagnóstico, pero falta el pilar de SGLT2i.",
            "covered_facets": [
                {
                    "facet": "Diagnóstico clínico",
                    "description": "Criterios clínicos cubiertos",
                    "matched_note_ids": [101],
                    "quality_score": 0.95,
                }
            ],
            "orphan_gaps": [
                {
                    "gap_title": "Inhibidores SGLT2",
                    "reason": "Reducción de hospitalización en IC",
                    "priority": "high",
                    "suggested_front": "[Cardio > Farmacología] ¿Efecto de empagliflozina en IC?",
                },
                {
                    "gap_title": "Sacubitrilo / Valsartán",
                    "reason": "Mecanismo ARNI",
                    "priority": "medium",
                    "suggested_front": "[Cardio > Farmacología] ¿Cuándo iniciar ARNI?",
                },
            ],
        }


def test_store_coverage_audit_lifecycle():
    """Verify SQLite Knowledge Store audit persistence, retrieval, gap update, and note extraction."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_store_audit.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        # 1. Save coverage audit
        covered_facets = [
            {
                "facet": "Criterios de Framingham",
                "description": "Diagnóstico de IC",
                "matched_note_ids": [101],
                "quality_score": 1.0,
            }
        ]
        orphan_gaps = [
            {
                "gap_title": "Inhibidores SGLT2",
                "reason": "Pilar terapéutico clave",
                "priority": "high",
                "suggested_front": "[Cardio] ¿Efecto de empagliflozina en IC?",
                "status": "pending",
                "generated_note_id": None,
            },
            {
                "gap_title": "Sacubitrilo/Valsartán",
                "reason": "ARNI en IC",
                "priority": "high",
                "suggested_front": "[Cardio] ¿Indicación de ARNI?",
                "status": "pending",
                "generated_note_id": None,
            },
        ]

        audit_id = store.save_coverage_audit(
            deck_name="Medicina::Cardio",
            topic="Insuficiencia Cardíaca",
            description="Diagnóstico y tratamiento",
            coverage_percentage=65,
            covered_facets=covered_facets,
            orphan_gaps=orphan_gaps,
            summary_assessment="Cubre diagnóstico básico pero faltan pilares farmacológicos modernos.",
        )
        assert audit_id > 0

        # 2. Get coverage audit
        audit = store.get_coverage_audit(audit_id)
        assert audit is not None
        assert audit["id"] == audit_id
        assert audit["deck_name"] == "Medicina::Cardio"
        assert audit["topic"] == "Insuficiencia Cardíaca"
        assert audit["coverage_percentage"] == 65
        assert len(audit["covered_facets"]) == 1
        assert len(audit["orphan_gaps"]) == 2
        assert audit["orphan_gaps"][0]["status"] == "pending"

        # 3. Update gap status
        ok = store.update_gap_status(
            audit_id=audit_id,
            gap_index=0,
            status="in_curation",
            generated_note_id=888,
        )
        assert ok is True

        # Invalid index returns False
        assert store.update_gap_status(audit_id=audit_id, gap_index=99, status="resolved") is False
        assert store.update_gap_status(audit_id=9999, gap_index=0, status="resolved") is False

        # Verify update persisted
        updated_audit = store.get_coverage_audit(audit_id)
        assert updated_audit["orphan_gaps"][0]["status"] == "in_curation"
        assert updated_audit["orphan_gaps"][0]["generated_note_id"] == 888
        assert updated_audit["orphan_gaps"][1]["status"] == "pending"

        # 4. List coverage audits
        audits_list = store.list_coverage_audits("Medicina::Cardio")
        assert len(audits_list) == 1
        assert audits_list[0]["id"] == audit_id
        assert audits_list[0]["topic"] == "Insuficiencia Cardíaca"

        # List for deck without audits
        assert store.list_coverage_audits("NonExistentDeck") == []

        # 5. Indexed notes extraction without BLOBs
        mock_notes = [
            {
                "note_id": 101,
                "front": "Front text",
                "back": "Back text",
                "explanation": "Exp text",
                "tags": ["tag1", "tag2"],
                "embedding": [0.1, 0.2, 0.3],
            }
        ]
        store.save_note_embeddings("Medicina::Cardio", mock_notes)
        all_notes = store.get_all_indexed_notes("Medicina::Cardio")
        assert len(all_notes) == 1
        assert all_notes[0]["note_id"] == 101
        assert all_notes[0]["tags"] == ["tag1", "tag2"]
        assert all_notes[0]["front"] == "Front text"
        assert "embedding" not in all_notes[0]


@pytest.mark.asyncio
async def test_audit_topic_coverage_service_flow():
    """Verify audit_topic_coverage AI orchestration, JSON parsing, and gap checklist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_audit_service.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        mock_notes = [
            {
                "note_id": 101,
                "deck_name": "Farmacología",
                "front": "[Cardio > IC] ¿Criterios mayores de Framingham?",
                "back": "Ortopnea, DPN, ingurgitación yugular.",
                "explanation": "⚠️ Trampa frecuente: edemas maleolares son criterio menor.",
                "tags": ["cardio", "diagnostico"],
            }
        ]
        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort({"insuficiencia": [1.0, 0.0, 0.0]})
        card_generator = MockCardGeneratorForAudit()

        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
            card_generator=card_generator,
        )

        # Pre-index deck
        await service.sync_deck_index("Farmacología")

        # Run audit
        audit_res = await service.audit_topic_coverage(
            deck_name="Farmacología",
            topic="Insuficiencia Cardíaca",
            description="Manejo clínico integral",
            top_k=5,
            save_audit=True,
        )

        assert isinstance(audit_res, TopicCoverageAuditResponse)
        assert audit_res.audit_id is not None
        assert audit_res.deck_name == "Farmacología"
        assert audit_res.topic == "Insuficiencia Cardíaca"
        assert audit_res.coverage_percentage == 70
        assert len(audit_res.covered_facets) == 1
        assert audit_res.covered_facets[0].matched_note_ids == [101]
        assert len(audit_res.orphan_gaps) == 2
        assert audit_res.orphan_gaps[0].gap_title == "Inhibidores SGLT2"
        assert audit_res.orphan_gaps[0].status == CoverageGapStatus.PENDING

        # Check list audits through service
        list_res = await service.list_coverage_audits("Farmacología")
        assert isinstance(list_res, ListDeckAuditsResponse)
        assert len(list_res.audits) == 1
        assert list_res.audits[0].total_gaps == 2
        assert list_res.audits[0].pending_gaps == 2

        # Update gap status via service
        updated = await service.update_gap_status(
            audit_id=audit_res.audit_id,
            gap_index=0,
            status=CoverageGapStatus.RESOLVED,
            generated_note_id=303,
        )
        assert updated is True

        # Check updated gap count
        list_res2 = await service.list_coverage_audits("Farmacología")
        assert list_res2.audits[0].pending_gaps == 1

        # Check get_coverage_audit
        single_res = await service.get_coverage_audit(audit_res.audit_id)
        assert single_res is not None
        assert single_res.orphan_gaps[0].status == CoverageGapStatus.RESOLVED
        assert single_res.orphan_gaps[0].generated_note_id == 303
        assert single_res.orphan_gaps[1].status == CoverageGapStatus.PENDING


@pytest.mark.asyncio
async def test_deck_coverage_map_hierarchy_and_health():
    """Verify get_deck_coverage_map builds DAG clusters, notes with health, and orphan gaps."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_coverage_map.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        # Sample notes:
        # Note 1: Optimal (atomic, short, has trap)
        # Note 2: Debt (>25 words, no trap)
        # Note 3: Note with tags as cluster
        mock_notes = [
            {
                "note_id": 501,
                "deck_name": "Cardiología",
                "front": "[Cardio > Beta-bloqueantes] ¿Mecanismo de acción de metoprolol?",
                "back": "Bloqueador selectivo de los receptores beta-1 adrenérgicos.",
                "explanation": "⚠️ Trampa frecuente / Error común: precaución en asma severa.",
                "tags": ["farmaco"],
                "quality_status": "optimal",
            },
            {
                "note_id": 502,
                "deck_name": "Cardiología",
                "front": "[Cardio > Diuréticos] ¿Cómo actúa la furosemida en el asa de Henle?",
                "back": (
                    "Inhibe de forma potente el cotransportador de sodio potasio y dos cloruros en la porción "
                    "ascendente gruesa del asa de Henle bloqueando la reabsorción normal de solutos e impidiendo la "
                    "concentración adecuada de la orina produciendo diuresis masiva en insuficiencia cardíaca aguda descompensada."
                ),
                "explanation": "Ver detalles en Goodman & Gilman.",
                "tags": ["farmaco"],
                "quality_status": "debt",
            },
            {
                "note_id": 503,
                "deck_name": "Cardiología",
                "front": "¿Efecto adverso característico del enalapril?",
                "back": "Tos seca intratable por acumulación de bradicinina.",
                "explanation": "⚠️ Trampa frecuente: sustituir por ARA-II si la tos es limitante.",
                "tags": ["IECA", "Renal"],
                "quality_status": "optimal",
            },
        ]

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort()

        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        # Index the deck
        await service.sync_deck_index("Cardiología")

        # Save an audit with a pending orphan gap for topic "IECA"
        store.save_coverage_audit(
            deck_name="Cardiología",
            topic="IECA",
            description="Inhibidores de la ECA",
            coverage_percentage=50,
            covered_facets=[{"facet": "Efectos adversos", "description": "Tos", "matched_note_ids": [503], "quality_score": 1.0}],
            orphan_gaps=[
                {
                    "gap_title": "Estenosis bilateral de arteria renal",
                    "reason": "Contraindicación absoluta de IECA",
                    "priority": "high",
                    "suggested_front": "[IECA] ¿Por qué está contraindicado en estenosis bilateral?",
                    "status": "pending",
                    "generated_note_id": None,
                }
            ],
            summary_assessment="Falta contraindicación crítica.",
        )

        map_res = await service.get_deck_coverage_map("Cardiología")

        assert isinstance(map_res, DeckCoverageMapResponse)
        assert map_res.deck_name == "Cardiología"
        assert map_res.total_nodes == len(map_res.nodes)

        # Verify Root Node
        root = next((n for n in map_res.nodes if n.type == "deck"), None)
        assert root is not None
        assert root.id == "deck:Cardiología"

        # Verify Clusters
        clusters = [n for n in map_res.nodes if n.type == "cluster"]
        cluster_labels = [c.label for c in clusters]
        assert "Cardio" in cluster_labels
        assert "IECA" in cluster_labels

        # Verify Notes
        notes = [n for n in map_res.nodes if n.type == "note"]
        assert len(notes) == 3

        note_501 = next(n for n in notes if n.note_id == 501)
        assert note_501.health == "optimal"

        note_502 = next(n for n in notes if n.note_id == 502)
        assert note_502.health == "bad"

        note_503 = next(n for n in notes if n.note_id == 503)
        assert note_503.health == "optimal"

        # Verify Gaps
        gaps = [n for n in map_res.nodes if n.type == "gap"]
        assert len(gaps) == 1
        assert gaps[0].label == "Estenosis bilateral de arteria renal"
        assert gaps[0].health == "gap"

        # Verify Counts
        assert map_res.optimal_count == 2
        assert map_res.bad_count == 1
        assert map_res.gap_count == 1

        # Verify DAG Edges
        # Deck -> Clusters
        deck_edges = [e for e in map_res.edges if e.source == "deck:Cardiología"]
        assert len(deck_edges) == len(clusters)

        # Cluster -> Note edges
        cardio_edges = [e for e in map_res.edges if e.source == "cluster:Cardio"]
        assert any(e.target == "note:501" for e in cardio_edges)
        assert any(e.target == "note:502" for e in cardio_edges)

        # Cluster -> Gap edge
        ieca_edges = [e for e in map_res.edges if e.source == "cluster:IECA"]
        assert any(e.target == gaps[0].id for e in ieca_edges)


def test_coverage_audit_api_routes():
    """Verify HTTP endpoints for audit topic coverage, list audits, gap updates, and map."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_api_audit.db"
        mock_store = DeckKnowledgeStore(db_path=str(db_path))

        mock_notes = [
            {
                "note_id": 701,
                "deck_name": "Neuro",
                "front": "[Neuro > Epilepsia] ¿Mecanismo de acción del levetiracetam?",
                "back": "Modulación de la proteína de vesícula sináptica SV2A.",
                "explanation": "⚠️ Trampa frecuente: no induce enzimas hepáticas del citocromo P450.",
                "tags": ["anticonvulsivantes"],
                "quality_status": "optimal",
            }
        ]
        mock_anki = MockAnkiBridge(mock_notes)
        mock_emb = MockEmbeddingPort({"epilepsia": [1.0, 0.0, 0.0]})
        mock_gen = MockCardGeneratorForAudit()

        mock_service = DeckIntelligenceService(
            anki_bridge=mock_anki,
            embedding_port=mock_emb,
            store=mock_store,
            card_generator=mock_gen,
        )

        app.dependency_overrides[get_deck_knowledge_store] = lambda: mock_store
        app.dependency_overrides[get_deck_intelligence_service] = lambda api_key=None: mock_service
        app.dependency_overrides[get_anki_connect_adapter] = lambda: mock_anki

        client = TestClient(app)

        try:
            # 1. POST /api/anki/decks/{deck_name}/audit-topic-coverage
            audit_req = {
                "topic": "Epilepsia",
                "description": "Fármacos antiepilépticos",
                "top_k": 5,
                "save_audit": True,
            }
            res = client.post("/api/anki/decks/Neuro/audit-topic-coverage", json=audit_req)
            assert res.status_code == 200, res.text
            audit_data = res.json()
            assert audit_data["deck_name"] == "Neuro"
            assert audit_data["topic"] == "Epilepsia"
            assert audit_data["coverage_percentage"] == 70
            assert len(audit_data["orphan_gaps"]) == 2
            audit_id = audit_data["audit_id"]
            assert audit_id is not None

            # 2. GET /api/anki/decks/{deck_name}/audits
            res_list = client.get("/api/anki/decks/Neuro/audits")
            assert res_list.status_code == 200
            list_data = res_list.json()
            assert len(list_data["audits"]) == 1
            assert list_data["audits"][0]["topic"] == "Epilepsia"
            assert list_data["audits"][0]["pending_gaps"] == 2

            # 3. GET /api/anki/decks/audits/{audit_id}
            res_single = client.get(f"/api/anki/decks/audits/{audit_id}")
            assert res_single.status_code == 200
            single_data = res_single.json()
            assert single_data["audit_id"] == audit_id

            # 4. PATCH /api/anki/decks/audits/{audit_id}/gaps/{gap_index}
            patch_req = {
                "status": "resolved",
                "generated_note_id": 999,
            }
            res_patch = client.patch(f"/api/anki/decks/audits/{audit_id}/gaps/0", json=patch_req)
            assert res_patch.status_code == 200
            patch_data = res_patch.json()
            assert patch_data["success"] is True
            assert patch_data["status"] == "resolved"

            # Verify pending count decreased
            res_list_after = client.get("/api/anki/decks/Neuro/audits")
            assert res_list_after.json()["audits"][0]["pending_gaps"] == 1

            # 5. GET /api/anki/decks/{deck_name}/coverage-map
            res_map = client.get("/api/anki/decks/Neuro/coverage-map")
            assert res_map.status_code == 200
            map_data = res_map.json()
            assert map_data["deck_name"] == "Neuro"
            assert map_data["total_nodes"] > 0
            assert map_data["optimal_count"] >= 1
            assert map_data["gap_count"] >= 1

            # 6. Test 404 on nonexistent audit
            res_404 = client.get("/api/anki/decks/audits/99999")
            assert res_404.status_code == 404

        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_deck_coverage_map_unreviewed_honest_neutral():
    """Verify that unreviewed cards default to gray 'unreviewed' state with 0% audited health."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_unreviewed_map.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        # Raw notes without explicit quality audit (e.g. legacy or empty image occlusion)
        mock_notes = [
            {
                "note_id": 901,
                "deck_name": "Oracle Cloud",
                "front": "OCI VCN Architecture",
                "back": "<img src='diagram.png'>",  # 0 text words, previously triggered false optimal!
                "explanation": "",
                "tags": ["oci"],
            },
            {
                "note_id": 902,
                "deck_name": "Oracle Cloud",
                "front": "IAM Policies in OCI",
                "back": "Allow group SecOps to manage all-resources in compartment Production",
                "explanation": "",
                "tags": ["oci"],
            },
        ]

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort()
        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        await service.sync_deck_index("Oracle Cloud")

        # 1. Unreviewed State
        map_res = await service.get_deck_coverage_map("Oracle Cloud")

        assert map_res.optimal_count == 0
        assert map_res.debt_count == 0
        assert map_res.gap_count == 0
        assert map_res.broken_count == 0
        assert map_res.unreviewed_count == 2
        assert map_res.audited_count == 0
        assert map_res.deck_health_percentage == 0.0

        # Note nodes must be 'unreviewed'
        note_nodes = [n for n in map_res.nodes if n.type == "note"]
        assert len(note_nodes) == 2
        for n in note_nodes:
            assert n.health == "unreviewed"

        # Cluster node must be 'unreviewed'
        cluster_node = next(n for n in map_res.nodes if n.type == "cluster")
        assert cluster_node.health == "unreviewed"

        # Root node must be 'unreviewed'
        root_node = next(n for n in map_res.nodes if n.type == "deck")
        assert root_node.health == "unreviewed"

        # 2. Store stats should also report audited_count = 0
        stats = store.get_deck_stats("Oracle Cloud")
        assert stats["total_indexed"] == 2
        assert stats["audited_count"] == 0
        assert stats["unreviewed_count"] == 2
        assert stats["deck_health_percentage"] == 0.0

        # 3. Simulate Phase 3 audit: update Note 901 as 'optimal' with feedback
        store.update_note_quality(
            deck_name="Oracle Cloud",
            note_id=901,
            quality_status="optimal",
            quality_score=0.95,
            quality_feedback="Imagen con diagrama claro y prompt enfocado.",
        )

        map_res_audited = await service.get_deck_coverage_map("Oracle Cloud")
        assert map_res_audited.optimal_count == 1
        assert map_res_audited.unreviewed_count == 1
        assert map_res_audited.audited_count == 1
        assert map_res_audited.deck_health_percentage == 100.0

        note_901 = next(n for n in map_res_audited.nodes if n.note_id == 901)
        assert note_901.health == "optimal"
        assert note_901.quality_score == 0.95
        assert "diagrama claro" in note_901.details


@pytest.mark.asyncio
async def test_deck_coverage_map_preevaluated_status_lifecycle():
    """Verify newly generated/exported notes receive 'preevaluated' status, count towards health, and survive re-indexing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_preevaluated.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        # 1. Mark newly generated notes as preevaluated
        store.mark_notes_preevaluated("AWS Architect", [1001, 1002])

        stats = store.get_deck_stats("AWS Architect")
        assert stats["total_indexed"] == 2
        assert stats["optimal_count"] == 2
        assert stats["audited_count"] == 2
        assert stats["unreviewed_count"] == 0
        assert stats["deck_health_percentage"] == 100.0

        # 2. Simulate subsequent Anki sync with unreviewed notes
        # save_note_embeddings should NOT overwrite optimal to unreviewed
        store.save_note_embeddings(
            "AWS Architect",
            [
                {
                    "note_id": 1001,
                    "front": "[AWS > S3] ¿Propósito de S3 Glacier?",
                    "back": "Almacenamiento de bajo costo para archivado.",
                    "explanation": "Extra info",
                    "tags": ["Storage"],
                    "quality_status": "unreviewed",  # Raw sync default
                }
            ],
        )

        stats_after_sync = store.get_deck_stats("AWS Architect")
        assert stats_after_sync["optimal_count"] == 2

        # 3. Verify coverage map reports optimal
        mock_bridge = MagicMock()
        mock_bridge.get_deck_notes = AsyncMock(return_value=[])
        service = DeckIntelligenceService(
            anki_bridge=mock_bridge,
            embedding_port=None,
            store=store,
        )

        cov_map = await service.get_deck_coverage_map("AWS Architect")
        assert cov_map.optimal_count == 2
        assert cov_map.deck_health_percentage == 100.0
        node_1001 = next(n for n in cov_map.nodes if n.note_id == 1001)
        assert node_1001.health == "optimal"


