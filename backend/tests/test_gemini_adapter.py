import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.adapters.ai.gemini_card_generator_adapter import (
    GeminiCardGeneratorAdapter,
    EnrichedPrerequisiteSchema,
)
from app.domain.models import Flashcard, GenerationOptions, CardType


@pytest.fixture
def gemini_adapter():
    return GeminiCardGeneratorAdapter(
        api_key="mock_gemini_key",
        model="gemini-3.8-flash",
    )


@pytest.mark.asyncio
async def test_gemini_enrich_prerequisite_returns_blueprint_and_count(gemini_adapter):
    """Verify enrich_prerequisite returns atomic_blueprint and sets recommended_deep_cards to len(atomic_blueprint)."""
    mock_schema = EnrichedPrerequisiteSchema(
        concept="TCP Three-Way Handshake",
        summary="El handshake de tres vías sincroniza números de secuencia iniciales (ISN) entre cliente y servidor.",
        key_takeaway="Garantiza que ambos extremos pueden transmitir y recibir antes de transferir datos.",
        atomic_blueprint=[
            "1. Propósito de sincronización de ISN en SYN",
            "2. Confirmación dual en el segmento SYN-ACK",
            "3. Establecimiento de estado ESTABLISHED tras ACK",
            "4. Vulnerabilidad SYN Flood y mitigación con SYN Cookies",
        ],
        recommended_deep_cards=4,
    )

    with patch.object(gemini_adapter, "_race_hedged_generation", new=AsyncMock(return_value=mock_schema)):
        result = await gemini_adapter.enrich_prerequisite(
            concept="TCP Three-Way Handshake",
            search_query="TCP 3-way handshake ISN synchronization",
            context_topic="Redes de Computadoras",
        )

        assert result.concept == "TCP Three-Way Handshake"
        assert result.recommended_deep_cards == 4
        assert len(result.atomic_blueprint) == 4
        assert "1. Propósito de sincronización de ISN en SYN" in result.atomic_blueprint


@pytest.mark.asyncio
async def test_gemini_generate_prerequisites_batch_isolates_deep_dive_and_enforces_exact_count(
    gemini_adapter,
):
    """Verify _generate_prerequisites_batch isolates Deep Dive items and passes exact_target_count into system_instruction."""
    prereq_context = "\n".join(
        [
            "- [SUB-EVENTO DE ANÁLISIS PROFUNDO (4 tarjetas)] Modelo OSI: Fundamento: Capas de red | Blueprint Atómico Obligatorio (1 tarjeta por ítem): 1) Capa física ; 2) Enlace ; 3) Red ; 4) Transporte",
            "- [SUB-EVENTO DE ANÁLISIS PROFUNDO (3 tarjetas)] Protocolo ARP: Fundamento: Resolución MAC | Blueprint Atómico Obligatorio (1 tarjeta por ítem): 1) ARP Request ; 2) ARP Reply ; 3) ARP Cache",
            "- [ANCLAJE RÁPIDO (1 tarjeta)] Dirección MAC: Identificador físico de 48 bits",
            "- [ANCLAJE RÁPIDO (1 tarjeta)] Dirección IPv4: Identificador lógico de 32 bits",
        ]
    )
    options = GenerationOptions(
        deck_name="Redes",
        prerequisites_context=prereq_context,
    )

    captured_calls = []

    async def _mock_micro_batch(client, contents, system_instruction, options, batch_label, retries=1):
        captured_calls.append(
            {
                "batch_label": batch_label,
                "system_instruction": system_instruction,
                "user_prompt": contents[0],
            }
        )
        return [
            Flashcard(
                card_type=CardType.BASIC,
                front=f"[Fundamentos > {batch_label}] ¿Pregunta?",
                back="Respuesta atómica.",
                tags=["redes"],
            )
        ]

    with patch.object(gemini_adapter, "_execute_single_micro_batch", side_effect=_mock_micro_batch):
        cards = await gemini_adapter._generate_prerequisites_batch(client=MagicMock(), options=options)

        # 2 isolated Deep Dive calls + 1 grouped Anchor call (2 anchors <= 3) = 3 total micro-batch calls
        assert len(captured_calls) == 3
        assert len(cards) == 3

        # Call 1: Deep Dive #1 (4 tarjetas)
        assert "CANTIDAD OBJETIVO OBLIGATORIA DE ESTE MICRO-LOTE: Genera EXACTAMENTE 4 tarjetas atómicas." in captured_calls[0]["system_instruction"]
        assert "Modelo OSI" in captured_calls[0]["user_prompt"]

        # Call 2: Deep Dive #2 (3 tarjetas)
        assert "CANTIDAD OBJETIVO OBLIGATORIA DE ESTE MICRO-LOTE: Genera EXACTAMENTE 3 tarjetas atómicas." in captured_calls[1]["system_instruction"]
        assert "Protocolo ARP" in captured_calls[1]["user_prompt"]

        # Call 3: Anchor group (2 tarjetas)
        assert "CANTIDAD OBJETIVO OBLIGATORIA DE ESTE MICRO-LOTE: Genera EXACTAMENTE 2 tarjetas atómicas." in captured_calls[2]["system_instruction"]
        assert "Dirección MAC" in captured_calls[2]["user_prompt"]
        assert "Dirección IPv4" in captured_calls[2]["user_prompt"]

        # All returned cards must have 'prerrequisito' and 'fundamentos' tags
        for card in cards:
            assert "prerrequisito" in card.tags
            assert "fundamentos" in card.tags
