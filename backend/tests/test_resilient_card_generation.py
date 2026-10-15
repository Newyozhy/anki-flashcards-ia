import pytest
from unittest.mock import AsyncMock, patch
from app.adapters.ai.resilient_cascade_adapter import ResilientCascadeAdapter
from app.domain.models import Flashcard, CardType, GenerationOptions
from app.services.cognitive_auditor_service import CognitiveAuditorService


@pytest.fixture
def sample_flashcard():
    return Flashcard(
        card_type=CardType.BASIC,
        front="[Biología > Célula] ¿Qué organelo produce ATP?",
        back="La mitocondria mediante fosforilación oxidativa.",
        explanation="⚠️ Trampa frecuente / Error común: Confundir con los ribosomas.",
    )


@pytest.fixture
def sample_nvidia_cards_json():
    return {
        "cards": [
            {
                "archetype": "Arquetipo C: Pregunta Atómica",
                "front": "[Neurociencia > Conducción] ¿Por qué la vaina de mielina acelera el potencial de acción?",
                "back": "Porque permite la conducción saltatoria entre los nódulos de Ranvier.",
                "tags": ["neurociencia", "mielina"],
                "explanation": "<img src='diagrama_ranvier.png' />\n\n⚠️ Trampa frecuente / Error común: Creer que la mielina incrementa la capacitancia de la membrana.",
            },
            {
                "archetype": "Arquetipo A: Cloze Contextualizado",
                "front": "[Neurociencia > Conducción] En los axones mielinizados, el potencial salta en {{c1::los nódulos de Ranvier}}.",
                "back": "los nódulos de Ranvier",
                "tags": ["neurociencia"],
                "explanation": "⚠️ Trampa frecuente / Error común: Creer que ocurre a lo largo de toda la vaina.",
            }
        ]
    }


@pytest.mark.asyncio
async def test_generation_tier1_gemini_success(sample_flashcard):
    mock_primary = AsyncMock()
    mock_primary.generate_from_text.return_value = [sample_flashcard]

    adapter = ResilientCascadeAdapter(
        gemini_api_key="mock-gemini-key",
        primary_adapter=mock_primary,
    )

    cards = await adapter.generate_from_text("Contenido sobre mitocondrias", GenerationOptions())

    assert len(cards) == 1
    assert cards[0].front == sample_flashcard.front
    assert adapter.is_provider_open("gemini") is False
    mock_primary.generate_from_text.assert_called_once()


@pytest.mark.asyncio
async def test_generation_tier1_failure_fallback_to_nvidia(sample_nvidia_cards_json):
    mock_primary = AsyncMock()
    mock_primary.generate_from_text.side_effect = RuntimeError("429 ResourceExhausted: Quota exceeded")

    adapter = ResilientCascadeAdapter(
        gemini_api_key="mock-gemini-key",
        nvidia_api_key="mock-nvidia-key",
        primary_adapter=mock_primary,
    )

    with patch.object(adapter, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = sample_nvidia_cards_json
        cards = await adapter.generate_from_text(
            "Material sobre axones y mielina",
            GenerationOptions(deck_name="Medicina::Neuro")
        )

    assert len(cards) == 2
    assert "nódulos de Ranvier" in cards[0].back
    assert cards[1].card_type == CardType.CLOZE
    assert adapter.is_provider_open("gemini") is True  # Circuit tripped
    mock_call.assert_called_once()


@pytest.mark.asyncio
async def test_generation_streaming_fallback_when_gemini_tripped(sample_nvidia_cards_json):
    mock_primary = AsyncMock()

    adapter = ResilientCascadeAdapter(
        gemini_api_key="mock-gemini-key",
        nvidia_api_key="mock-nvidia-key",
        primary_adapter=mock_primary,
    )

    # Trip Gemini circuit
    adapter.trip_circuit("gemini", cooldown_seconds=60.0)

    with patch.object(adapter, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = sample_nvidia_cards_json
        stream_results = []
        async for item in adapter.generate_from_text_stream("Texto de prueba", GenerationOptions()):
            stream_results.append(item)

    mock_primary.generate_from_text_stream.assert_not_called()
    assert len(stream_results) >= 1
    label, batch_cards, cur, tot = stream_results[0]
    assert "Cascada" in label
    assert len(batch_cards) == 2


def test_generation_instruction_includes_diagram_inheritance_rule():
    adapter = ResilientCascadeAdapter(gemini_api_key="mock")
    options = GenerationOptions(
        selected_themes=[
            "Transmisión Sináptica (~2 tarjetas) | Diagramas a heredar: [vesicula_sinaptica.png]"
        ]
    )

    instruction = adapter._build_generation_instruction(options)

    assert "HERENCIA DE DIAGRAMAS OBLIGATORIA" in instruction
    assert "<img src='nombre_imagen'>" in instruction
    assert "vesicula_sinaptica.png" in instruction
    assert "Arquetipo A: Cloze Contextualizado" in instruction
    assert "Arquetipo B: Matriz de Contraste" in instruction
    assert "Arquetipo C: Pregunta Atómica Elaborativa" in instruction


def test_cognitive_auditor_flags_diagram_inheritance():
    auditor = CognitiveAuditorService()
    card_with_image = Flashcard(
        card_type=CardType.BASIC,
        front="[Fisiología] ¿Qué estructura conecta los axones?",
        back="La hendidura sináptica.",
        explanation="<img src='sinapsis.png' />\n\n⚠️ Trampa frecuente / Error común: Confundir con uniones gap.",
    )

    res_cards, audit_result = auditor.audit_card(card_with_image)

    diagram_finding = next(
        (f for f in audit_result.findings if f.rule == "DIAGRAM_INHERITED"), None
    )
    assert diagram_finding is not None
    assert diagram_finding.severity == "INFO"
    assert "Diagrama visual preservado exitosamente" in diagram_finding.message
