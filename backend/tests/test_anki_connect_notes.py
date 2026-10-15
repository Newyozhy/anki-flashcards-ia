from unittest.mock import AsyncMock, patch
import pytest
from app.adapters.anki.anki_connect_adapter import AnkiConnectAdapter
from app.domain.models import CardType


@pytest.fixture
def adapter():
    return AnkiConnectAdapter(base_url="http://localhost:8765")


@pytest.mark.asyncio
async def test_get_deck_notes_normalization(adapter):
    mock_find_notes = [101, 102, 103]
    mock_notes_info = [
        {
            "noteId": 101,
            "modelName": "Gramatica",
            "tags": ["Verb-to-be"],
            "fields": {
                "Titulo": {"value": "Recordar You"},
                "preguntas": {"value": "Que significados tiene You?"},
                "respuestas": {"value": "You significa tu o usted"},
                "imagen": {"value": '<img src="grammar_diagram.png">'},
            },
        },
        {
            "noteId": 102,
            "modelName": "Input",
            "tags": ["Vocabulary"],
            "fields": {
                "Front": {"value": "<b>Pitted</b>"},
                "Explanation": {"value": "deshuesado"},
                "Sentence": {"value": "Pitted olives are delicious."},
                "Translation": {"value": "Las aceitunas deshuesadas son ricas."},
                "Image": {"value": '<img src="olive.png">'},
            },
        },
        {
            "noteId": 103,
            "modelName": "AnkiCraft Pro (Cloze)",
            "tags": ["networking"],
            "fields": {
                "Text": {"value": "[Redes > L4] {{c1::TCP}} es un protocolo orientado a conexion."},
                "Back Extra": {"value": "TCP"},
                "Extra": {"value": "⚠️ Trampa frecuente: no confundir con UDP."},
            },
        },
    ]

    async def mock_invoke(action, **params):
        if action == "findNotes":
            return mock_find_notes
        if action == "notesInfo":
            return mock_notes_info
        return None

    with patch.object(adapter, "_invoke", side_effect=mock_invoke):
        notes = await adapter.get_deck_notes("English::General")

    assert len(notes) == 3

    # Check Gramatica note
    n1 = notes[0]
    assert n1.note_id == 101
    assert "Recordar You" in n1.front
    assert "Que significados tiene You?" in n1.front
    assert n1.back == "You significa tu o usted"
    assert "grammar_diagram.png" in n1.media_files
    assert n1.card_type == CardType.BASIC

    # Check Input note
    n2 = notes[1]
    assert n2.note_id == 102
    assert n2.front == "<b>Pitted</b>"
    assert n2.back == "deshuesado"
    assert "Pitted olives" in n2.explanation
    assert "olive.png" in n2.media_files

    # Check Cloze note
    n3 = notes[2]
    assert n3.note_id == 103
    assert n3.card_type == CardType.CLOZE
    assert "{{c1::TCP}}" in n3.front


@pytest.mark.asyncio
async def test_retrieve_media_base64(adapter):
    with patch.object(adapter, "_invoke", new_callable=AsyncMock) as mock_inv:
        mock_inv.return_value = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        res = await adapter.retrieve_media_base64("pixel.png")
        assert res is not None
        assert res.startswith("iVBOR")
        mock_inv.assert_called_once_with("retrieveMediaFile", filename="pixel.png")


@pytest.mark.asyncio
async def test_update_note_fields(adapter):
    with patch.object(adapter, "_invoke", new_callable=AsyncMock) as mock_inv:
        mock_inv.return_value = None
        ok = await adapter.update_note_fields(1001, {"Front": "New Question", "Back": "New Answer"})
        assert ok is True
        mock_inv.assert_called_once_with(
            "updateNoteFields",
            note={"id": 1001, "fields": {"Front": "New Question", "Back": "New Answer"}},
        )


@pytest.mark.asyncio
async def test_delete_notes(adapter):
    with patch.object(adapter, "_invoke", new_callable=AsyncMock) as mock_inv:
        mock_inv.return_value = None
        ok = await adapter.delete_notes([1001, 1002])
        assert ok is True
        mock_inv.assert_called_once_with("deleteNotes", notes=[1001, 1002])


def test_api_get_deck_notes():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.api.deps import get_anki_connect_adapter

    mock_records = [
        {
            "note_id": 999,
            "deck_name": "Test::Deck",
            "model_name": "Basic",
            "card_type": "basic",
            "front": "What is Python?",
            "back": "A programming language",
            "explanation": "Interpreted and versatile",
            "tags": ["coding"],
            "raw_fields": {"Front": "What is Python?", "Back": "A programming language"},
            "media_files": [],
        }
    ]

    mock_adapter = AsyncMock()
    mock_adapter.get_deck_notes.return_value = mock_records

    app.dependency_overrides[get_anki_connect_adapter] = lambda: mock_adapter
    client = TestClient(app)

    try:
        response = client.get("/api/anki/decks/Test::Deck/notes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["note_id"] == 999
        assert data[0]["deck_name"] == "Test::Deck"
        assert data[0]["front"] == "What is Python?"
    finally:
        app.dependency_overrides.pop(get_anki_connect_adapter, None)

