import io
import pytest
import pypdf
from unittest.mock import AsyncMock, MagicMock

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    BlueprintDomain,
    BlueprintObjective,
    ExamBlueprint,
)
from app.services.exam_blueprint_service import ExamBlueprintService


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_blueprint_store.db"
    return DeckKnowledgeStore(db_path=str(db_file))


def test_extract_text_from_pdf_in_memory():
    # Create an in-memory PDF with pypdf
    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    
    # We can write bytes to stream
    pdf_bytes_io = io.BytesIO()
    writer.write(pdf_bytes_io)
    pdf_bytes = pdf_bytes_io.getvalue()

    store_mock = MagicMock()
    emb_mock = MagicMock()
    service = ExamBlueprintService(store=store_mock, embedding_port=emb_mock)
    
    # Even if blank, extract_text_from_pdf shouldn't crash
    extracted = service.extract_text_from_pdf(pdf_bytes)
    assert isinstance(extracted, str)


@pytest.mark.asyncio
async def test_align_blueprint_detects_covered_and_gaps(temp_store):
    deck = "Oracle Cloud Test"
    
    # Index one note in deck
    temp_store.save_note_embeddings(
        deck_name=deck,
        notes=[
            {
                "note_id": 101,
                "front": "¿Qué es una VCN en Oracle Cloud?",
                "back": "Una Virtual Cloud Network es una red privada en la nube.",
                "explanation": "Networking OCI",
                "clean_text": "VCN Oracle Cloud Virtual Cloud Network red privada",
                "embedding": [0.9, 0.1, 0.0],
            }
        ],
    )

    # Mock embedding adapter
    mock_emb = MagicMock()
    # 2 objectives:
    # Obj 1: closely matches note (vector [0.89, 0.11, 0.0]) -> high similarity
    # Obj 2: completely different (vector [0.0, 0.0, 1.0]) -> gap
    embeddings_mock = AsyncMock(return_value=[
        [0.89, 0.11, 0.0],
        [0.0, 0.0, 1.0],
    ])
    mock_emb.get_embeddings = embeddings_mock
    mock_emb.embed_texts = embeddings_mock

    service = ExamBlueprintService(store=temp_store, embedding_port=mock_emb)

    blueprint = ExamBlueprint(
        exam_name="1Z0-1085-24 OCI Foundations",
        provider="Oracle",
        source_type="upload_pdf",
        domains=[
            BlueprintDomain(
                domain_id="D1",
                name="Networking",
                weight_pct=30.0,
                objectives=[
                    BlueprintObjective(
                        objective_id="1.1",
                        title="VCN Architecture",
                        description="Understand Virtual Cloud Network basics",
                    ),
                    BlueprintObjective(
                        objective_id="1.2",
                        title="FastConnect and BGP",
                        description="Configure dedicated private circuits",
                    ),
                ],
            )
        ],
        total_objectives=2,
    )

    result = await service.align_blueprint_with_deck(deck, blueprint, min_similarity_threshold=0.68)

    assert result.total_objectives == 2
    assert result.covered_count == 1
    assert result.gap_count == 1
    assert result.created_gaps_count == 1

    # Verify gap was persisted in coverage audits
    audits = temp_store.list_coverage_audits(deck)
    assert len(audits) >= 1
    assert any(a["topic"] == "Networking" for a in audits)

    # Verify orphan gap was recorded
    net_audit = next(a for a in audits if a["topic"] == "Networking")
    orphan_gaps = net_audit["orphan_gaps"]
    assert len(orphan_gaps) == 1
    assert "FastConnect and BGP" in orphan_gaps[0]["gap_title"]
