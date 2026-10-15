import pytest
from unittest.mock import AsyncMock, patch
from app.adapters.ai.ollama_adapter import OllamaCardGeneratorAdapter
from app.domain.models import GenerationOptions, CardType


@pytest.mark.asyncio
async def test_ollama_adapter_availability_check():
    """Verify Ollama adapter reports status when service is up."""
    adapter = OllamaCardGeneratorAdapter(base_url="http://127.0.0.1:11434")
    status = await adapter.check_availability()
    assert "is_available" in status
    assert "active_model" in status


@pytest.mark.asyncio
async def test_ollama_adapter_mock_generation():
    """Verify Ollama adapter correctly formats prompts and parses JSON flashcards."""
    adapter = OllamaCardGeneratorAdapter()

    fake_response_data = {
        "message": {
            "content": (
                '{"cards": [{'
                '"archetype": "Arquetipo C: Pregunta Atómica", '
                '"front": "[Redes > TCP] ¿Qué puerto utiliza DNS por defecto?", '
                '"back": "Puerto 53 UDP/TCP.", '
                '"tags": ["redes"], '
                '"explanation": "⚠️ Trampa frecuente / Error común: Olvidar que DNS también usa TCP para transferencias de zona."'
                '}]}'
            )
        }
    }

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: fake_response_data

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        options = GenerationOptions(deck_name="Redes")
        cards = await adapter.generate_from_text("Contenido sobre DNS y puertos", options)

        assert len(cards) == 1
        card = cards[0]
        assert card.card_type == CardType.BASIC
        assert "[Redes > TCP]" in card.front
        assert "Puerto 53" in card.back
        assert "⚠️ Trampa frecuente" in card.explanation


@pytest.mark.asyncio
async def test_ollama_adapter_target_count_and_prereqs_in_payload():
    """Verify Ollama adapter partitions multi-batch requests (prereqs + themes) and preserves prerequisite tags."""
    adapter = OllamaCardGeneratorAdapter()

    responses = [
        {
            "message": {
                "content": '{"cards": [{"front": "[Fundamentos > IP] ¿Qué es IP?", "back": "Protocolo de red.", "tags": ["redes"]}]}'
            }
        },
        {
            "message": {
                "content": '{"cards": [{"front": "[Cloud > VPC] ¿Qué es una subred privada?", "back": "Subred sin ruta directa a Internet.", "tags": ["cloud"]}]}'
            }
        },
    ]
    call_idx = {"i": 0}

    def _next_json():
        idx = min(call_idx["i"], len(responses) - 1)
        call_idx["i"] += 1
        return responses[idx]

    fake_response = AsyncMock()
    fake_response.status_code = 200
    fake_response.json = _next_json

    with patch("httpx.AsyncClient.post", return_value=fake_response) as mock_post:
        options = GenerationOptions(
            deck_name="Oracle Cloud",
            target_count=4,
            prerequisites_context="- [ANCLAJE RÁPIDO (1 tarjeta)] Protocolo IP: Direccionamiento lógico",
            selected_themes=["VPC y Redes (~3 tarjetas)"],
        )
        cards = await adapter.generate_from_text("Contenido sobre Cloud", options)
        assert len(cards) == 2
        assert mock_post.call_count == 2

        # Verify prerequisite micro-batch call
        prereq_call = mock_post.call_args_list[0][1]["json"]
        assert prereq_call["options"]["num_ctx"] == 8192
        assert "EXACTAMENTE 1 tarjetas atómicas" in prereq_call["messages"][0]["content"]
        assert "Protocolo IP" in prereq_call["messages"][1]["content"]
        assert "prerrequisito" in cards[0].tags
        assert "fundamentos" in cards[0].tags

        # Verify theme micro-batch call
        theme_call = mock_post.call_args_list[1][1]["json"]
        assert "EXACTAMENTE 3 tarjetas atómicas" in theme_call["messages"][0]["content"]
        assert "VPC y Redes" in theme_call["messages"][1]["content"]


@pytest.mark.asyncio
async def test_ollama_adapter_enrich_prerequisite_returns_blueprint():
    """Verify Ollama enrich_prerequisite returns atomic_blueprint and recommended_deep_cards."""
    adapter = OllamaCardGeneratorAdapter()

    fake_response = AsyncMock()
    fake_response.status_code = 200
    fake_response.json = lambda: {
        "message": {
            "content": (
                '{"summary": "Explicación de ARP.", '
                '"key_takeaway": "ARP mapea IP a MAC.", '
                '"atomic_blueprint": ["1. Propósito de ARP", "2. Broadcast ARP Request", "3. ARP Cache Poisoning"], '
                '"recommended_deep_cards": 3}'
            )
        }
    }

    with patch("httpx.AsyncClient.post", return_value=fake_response):
        res = await adapter.enrich_prerequisite("ARP", "Address Resolution Protocol", "Redes Locales")
        assert res.concept == "ARP"
        assert res.recommended_deep_cards == 3
        assert len(res.atomic_blueprint) == 3
        assert "1. Propósito de ARP" in res.atomic_blueprint


