import pytest
import os
from app.domain.models import Flashcard, CardType, GenerationOptions, Deck
from app.adapters.anki.genanki_file_adapter import GenankiFileAdapter
from app.services.export_deck_service import ExportDeckUseCase
from app.adapters.anki.anki_connect_adapter import AnkiConnectAdapter
from fastapi.testclient import TestClient
from app.main import app


def test_flashcard_domain_model():
    """Verify Flashcard entity creation, breadcrumbs and archetype."""
    card = Flashcard(
        card_type=CardType.BASIC,
        archetype="Arquetipo C: Pregunta Atómica",
        front="[Biología > Célula] ¿Cuál es la función de la mitocondria?",
        back="Producción de ATP celular.",
        tags=["biologia", "celula"],
        explanation="💡 Diagrama de la membrana interna mitocondrial",
    )
    assert card.id is not None
    assert card.card_type == CardType.BASIC
    assert card.archetype == "Arquetipo C: Pregunta Atómica"
    assert len(card.tags) == 2

    # Verify Auto options
    options = GenerationOptions(target_count=0)
    assert options.target_count == 0


@pytest.mark.asyncio
async def test_genanki_file_adapter_export(tmp_path):
    """Verify .apkg generation using GenankiFileAdapter."""
    adapter = GenankiFileAdapter(export_dir=str(tmp_path))
    cards = [
        Flashcard(
            card_type=CardType.BASIC,
            front="Pregunta 1",
            back="Respuesta 1",
            tags=["test"],
        ),
        Flashcard(
            card_type=CardType.CLOZE,
            front="El sol es una {{c1::estrella}}.",
            back="En el centro del sistema solar.",
            tags=["astronomia"],
        ),
    ]

    result = await adapter.export_cards("TestDeck", cards)
    assert result.success is True
    assert result.cards_exported_count == 2
    assert result.apkg_file_path is not None
    assert os.path.exists(result.apkg_file_path)


def test_fastapi_root_endpoint():
    """Verify root health check endpoint."""
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "gemini_model" in data


def test_fastapi_ollama_status_endpoint():
    """Verify Ollama status endpoint contract."""
    client = TestClient(app)
    response = client.get("/api/ollama/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_available" in data
    assert "models" in data
    assert "active_model" in data


def test_fastapi_anki_media_endpoint():
    """Verify Anki media streaming proxy endpoint."""
    from unittest.mock import AsyncMock, patch
    from app.api.deps import get_anki_connect_adapter

    mock_bridge = AsyncMock()
    # 1x1 transparent PNG in base64
    mock_bridge.retrieve_media_base64.return_value = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    app.dependency_overrides[get_anki_connect_adapter] = lambda: mock_bridge
    try:
        client = TestClient(app)
        res = client.get("/api/anki/media/test_image.png")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert len(res.content) > 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_export_deck_use_case_exports_new_cards_as_optimal():
    """Verify ExportDeckUseCase pushes new cards to AnkiConnect and marks them as optimal in store (H-10 single commit path)."""
    from unittest.mock import AsyncMock, MagicMock
    from app.domain.models import AnkiStatus, ExportResult

    mock_anki_connect = AsyncMock()
    mock_anki_connect.check_status.return_value = AnkiStatus(is_connected=True, available_decks=["Medicina"])
    mock_anki_connect.export_cards.return_value = ExportResult(
        success=True,
        cards_exported_count=2,
        destination="anki_connect",
        message="Created 2 cards",
        created_note_ids=[101, 102],
    )

    mock_apkg = AsyncMock()
    mock_store = MagicMock()

    use_case = ExportDeckUseCase(
        anki_connect_bridge=mock_anki_connect,
        apkg_bridge=mock_apkg,
        store=mock_store,
    )

    cards = [
        Flashcard(card_type=CardType.BASIC, front="Q1", back="A1"),
        Flashcard(card_type=CardType.BASIC, front="Q2", back="A2"),
    ]

    res = await use_case.export_to_anki(
        deck_name="Medicina",
        cards=cards,
    )

    assert res.success is True
    assert res.cards_exported_count == 2
    mock_anki_connect.export_cards.assert_awaited_once()
    mock_store.mark_notes_optimal.assert_called_once_with("Medicina", [101, 102])


@pytest.mark.asyncio
async def test_generate_cards_use_case_empty_text_fallback_with_options():
    """Verify that GenerateCardsUseCase reconstructs educational context if text is empty but themes/prereqs exist."""
    from unittest.mock import AsyncMock
    from app.services.generate_cards_service import GenerateCardsUseCase

    mock_generator = AsyncMock()
    mock_generator.generate_from_text.return_value = [
        Flashcard(card_type=CardType.BASIC, front="Front 1", back="Back 1")
    ]

    use_case = GenerateCardsUseCase(card_generator=mock_generator)
    options = GenerationOptions(
        selected_themes=["Tema 1 (~3 tarjetas)"],
        prerequisites_context="- Concepto A: Detalle",
        target_count=26,
    )

    result = await use_case.execute_from_text("", options)
    assert len(result.cards) == 1
    # Verify that generator was called with synthesized text, NOT empty string
    called_text = mock_generator.generate_from_text.call_args[0][0]
    assert "Tema 1 (~3 tarjetas)" in called_text
    assert "Concepto A: Detalle" in called_text




