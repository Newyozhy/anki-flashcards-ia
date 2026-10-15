import json
import tempfile
from pathlib import Path
from typing import List, Optional
import pytest
from fastapi.testclient import TestClient

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    AuditQualityBatchRequest,
    AuditQualityBatchResponse,
)
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.ports.embedding_port import IEmbeddingPort
from app.services.deck_intelligence_service import DeckIntelligenceService
from app.main import app
from app.api.deps import (
    get_deck_knowledge_store,
    get_deck_intelligence_service,
)


class MockAnkiBridge(IAnkiBridgePort):
    def __init__(self, notes: List[dict]):
        self.notes = notes

    async def check_status(self):
        return None

    async def get_deck_names(self):
        return ["AI::Engineering"]

    async def export_cards(self, deck_name: str, cards):
        return None

    async def get_deck_notes(self, deck_name: str) -> List[dict]:
        return self.notes

    async def get_notes_info(self, note_ids: List[int]) -> List[dict]:
        return []

    async def retrieve_media_base64(self, filename: str):
        return None

    async def update_note_fields(self, note_id: int, fields):
        return True

    async def delete_notes(self, note_ids):
        return True


class MockEmbeddingPort(IEmbeddingPort):
    async def embed_texts(self, texts: List[str]) -> List[Optional[List[float]]]:
        return [[0.1] * 768 for _ in texts]

    async def embed_single(self, text: str) -> List[float]:
        return [0.1] * 768


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_knowledge.db"
        yield DeckKnowledgeStore(db_path=db_path)


@pytest.mark.asyncio
async def test_audit_quality_batch_service_heuristic_fallback(temp_store):
    sample_notes = [
        {
            "note_id": 101,
            "tags": ["ml"],
            "front": "¿Cuál es la función de pérdida para clasificación binaria?",
            "back": "Binary Cross-Entropy (BCE).",
            "explanation": "",
        },
        {
            "note_id": 102,
            "tags": ["architecture"],
            "front": "¿Qué es un AI Agent y cómo se compone?",
            "back": (
                "Un agente es un sistema compuesto por un LLM como núcleo cognitivo, memoria episódica, "
                "semántica y de trabajo, planificador con reactividad y descomposición en subtareas, "
                "herramientas (MCP, APIs, terminal), y un bucle de ejecución perception-action con reflexión continua y auto-evaluación exhaustiva de cada paso ejecutado."
            ),
            "explanation": "",
        },
    ]

    anki = MockAnkiBridge(sample_notes)
    embedder = MockEmbeddingPort()
    service = DeckIntelligenceService(anki_bridge=anki, embedding_port=embedder, store=temp_store)

    # 1. First sync deck
    await service.sync_deck_index("AI::Engineering")

    # Verify notes are initially unreviewed
    unreviewed = temp_store.get_notes_for_audit("AI::Engineering", limit=10)
    assert len(unreviewed) == 2
    assert all(n["quality_status"] == "unreviewed" for n in unreviewed)

    # 2. Run batch audit with heuristic fallback
    resp = await service.audit_quality_batch(
        deck_name="AI::Engineering",
        batch_size=5,
        ai_provider="heuristic",
    )

    assert resp.deck_name == "AI::Engineering"
    assert resp.audited_count == 2
    assert len(resp.items) == 2

    # Card 101 (short back < 25 words, no images) -> optimal
    card_101 = next(item for item in resp.items if item.note_id == 101)
    assert card_101.quality_status == "optimal"
    assert card_101.quality_score >= 0.8

    # Card 102 (long dense back > 25 words) -> bad (Principio de Información Mínima violation)
    card_102 = next(item for item in resp.items if item.note_id == 102)
    assert card_102.quality_status == "bad"
    assert card_102.violation_type == "ATOMICITY_MONOLITH"

    # Verify SQLite store updated
    remaining_unreviewed = temp_store.get_notes_for_audit("AI::Engineering", limit=10)
    assert len(remaining_unreviewed) == 0

    stats = temp_store.get_deck_stats("AI::Engineering")
    assert stats["optimal_count"] == 1
    assert stats["bad_count"] == 1
    assert stats["audited_count"] == 2
    assert stats["unreviewed_count"] == 0


def test_audit_quality_batch_api_endpoint(temp_store):
    sample_notes = [
        {
            "note_id": 201,
            "tags": ["python"],
            "front": "¿Qué retorna isinstance(True, int)?",
            "back": "True, porque bool hereda directamente de int en Python.",
            "explanation": "",
        },
    ]

    anki = MockAnkiBridge(sample_notes)
    embedder = MockEmbeddingPort()
    service = DeckIntelligenceService(anki_bridge=anki, embedding_port=embedder, store=temp_store)

    app.dependency_overrides[get_deck_knowledge_store] = lambda: temp_store
    app.dependency_overrides[get_deck_intelligence_service] = lambda: service

    client = TestClient(app)

    # Sync first
    sync_res = client.post("/api/anki/decks/AI::Engineering/sync-index")
    assert sync_res.status_code == 200

    # Call audit batch
    audit_res = client.post(
        "/api/anki/decks/AI::Engineering/audit-quality-batch",
        json={"batch_size": 5, "ai_provider": "heuristic"},
    )
    assert audit_res.status_code == 200
    data = audit_res.json()
    assert data["deck_name"] == "AI::Engineering"
    assert data["audited_count"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["note_id"] == 201

    app.dependency_overrides.clear()
