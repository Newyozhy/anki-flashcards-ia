import pytest
from unittest.mock import AsyncMock, patch
from app.adapters.ai.resilient_cascade_adapter import ResilientCascadeAdapter
from app.domain.models import (
    GenerationOptions,
    StudyPlanInspection,
    CoreTheme,
    PrerequisiteItem,
)


@pytest.fixture
def sample_inspection():
    return StudyPlanInspection(
        topic_name="Sistema Nervioso Central",
        self_sufficiency_score=85,
        self_sufficiency_verdict="El material contiene bases neuroanatómicas sólidas.",
        core_themes=[
            CoreTheme(
                title="Estructura del Encéfalo",
                description="Divisiones anatómicas principales",
                recommended_cards=3,
            )
        ],
        prerequisites=[
            PrerequisiteItem(
                concept="Potencial de Acción",
                reason="Indispensable para comprender la señalización neuronal",
                is_covered_in_text=False,
                search_query="potencial de accion despolarizacion neurona",
                recommended_deep_cards=3,
            )
        ],
        suggested_total_cards=4,
    )


@pytest.fixture
def sample_nvidia_json():
    return {
        "topic_name": "Sistema Nervioso Central (NVIDIA)",
        "self_sufficiency_score": 80,
        "self_sufficiency_verdict": "Veredicto emitido por NVIDIA Llama-3.2 90B.",
        "core_themes": [
            {
                "title": "Mielinización y Conducción",
                "description": "Función de oligodendrocitos y nódulos de Ranvier",
                "recommended_cards": 2,
                "associated_diagrams": [],
            }
        ],
        "prerequisites": [
            {
                "concept": "Sinapsis Química",
                "reason": "Mecanismo de liberación de neurotransmisores",
                "is_covered_in_text": False,
                "search_query": "mecanismo sinapsis quimica vesiculas",
                "recommended_deep_cards": 3,
            }
        ],
        "suggested_total_cards": 3,
    }


@pytest.mark.asyncio
async def test_cascade_tier1_gemini_success(sample_inspection):
    mock_primary = AsyncMock()
    mock_primary.inspect_material.return_value = sample_inspection

    adapter = ResilientCascadeAdapter(
        gemini_api_key="mock-gemini-key",
        primary_adapter=mock_primary,
    )

    result = await adapter.inspect_material("Texto de prueba", GenerationOptions())

    assert result.provider_used == "gemini"
    assert result.fallback_occurred is False
    assert len(result.fallback_chain) == 0
    assert result.topic_name == "Sistema Nervioso Central"
    mock_primary.inspect_material.assert_called_once()


@pytest.mark.asyncio
async def test_cascade_tier1_failure_fallback_to_nvidia(sample_nvidia_json):
    mock_primary = AsyncMock()
    mock_primary.inspect_material.side_effect = RuntimeError("429 ResourceExhausted: Quota exceeded")

    adapter = ResilientCascadeAdapter(
        gemini_api_key="mock-gemini-key",
        nvidia_api_key="mock-nvidia-key",
        primary_adapter=mock_primary,
    )

    with patch.object(adapter, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = sample_nvidia_json
        result = await adapter.inspect_material("Texto sobre neuroanatomía", GenerationOptions())

    assert result.provider_used == "nvidia"
    assert result.fallback_occurred is True
    assert len(result.fallback_chain) > 0
    assert "gemini" in result.fallback_chain[0]
    assert result.topic_name == "Sistema Nervioso Central (NVIDIA)"
    assert adapter.is_provider_open("gemini") is True


@pytest.mark.asyncio
async def test_cascade_circuit_breaker_bypasses_open_provider(sample_nvidia_json):
    mock_primary = AsyncMock()

    adapter = ResilientCascadeAdapter(
        gemini_api_key="mock-gemini-key",
        nvidia_api_key="mock-nvidia-key",
        primary_adapter=mock_primary,
    )

    # Manually trip Gemini circuit
    adapter.trip_circuit("gemini", cooldown_seconds=60.0)
    assert adapter.is_provider_open("gemini") is True

    with patch.object(adapter, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = sample_nvidia_json
        result = await adapter.inspect_material("Texto sobre neuroanatomía", GenerationOptions())

    # Gemini must NOT be called at all
    mock_primary.inspect_material.assert_not_called()
    assert result.provider_used == "nvidia"
    assert "circuit_breaker_open" in result.fallback_chain[0]


@pytest.mark.asyncio
async def test_cascade_multimodal_image_url_conversion():
    adapter = ResilientCascadeAdapter(gemini_api_key="test")
    fake_png = b"\x89PNG\r\n\x1a\nfakeimagebytes"
    messages = adapter._build_openai_messages(
        system_instruction="System prompt",
        user_prompt="User prompt",
        media_parts=[(fake_png, "image/png")],
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    assert user_content[0]["type"] == "text"
    assert user_content[1]["type"] == "image_url"
    assert user_content[1]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.asyncio
async def test_cascade_all_tiers_exhausted_raises_runtime_error():
    mock_primary = AsyncMock()
    mock_primary.inspect_material.side_effect = RuntimeError("503 Service Unavailable")

    adapter = ResilientCascadeAdapter(
        gemini_api_key="mock-gemini-key",
        nvidia_api_key="mock-nvidia-key",
        primary_adapter=mock_primary,
    )

    with patch.object(adapter, "_call_openai_compatible", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = RuntimeError("401 Unauthorized")
        with pytest.raises(RuntimeError) as exc_info:
            await adapter.inspect_material("Texto", GenerationOptions())

    assert "Todos los proveedores de la cascada fallaron" in str(exc_info.value)
