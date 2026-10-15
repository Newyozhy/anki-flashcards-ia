import asyncio
import time
from unittest.mock import MagicMock, patch
import pytest
from google.genai import types

from app.adapters.ai.gemini_card_generator_adapter import (
    GeminiCardGeneratorAdapter,
    GeneratedCardSchema,
    GeneratedDeckSchema,
)


@pytest.fixture
def adapter():
    return GeminiCardGeneratorAdapter(
        api_key="mock_api_key",
        model="gemini-3.8-flash",
        tier_models=["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"],
        hedge_delay=0.15,
    )


def test_build_config_gemini_3(adapter):
    cfg_38 = adapter._build_config_for_model("gemini-3.8-flash", "test instruction")
    assert cfg_38.thinking_config is not None
    assert cfg_38.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert cfg_38.response_mime_type == "application/json"

    cfg_36 = adapter._build_config_for_model("gemini-3.6-flash", "test instruction")
    assert cfg_36.thinking_config.thinking_level == types.ThinkingLevel.LOW

    cfg_35 = adapter._build_config_for_model("gemini-3.5-flash", "test instruction")
    assert cfg_35.thinking_config.thinking_level == types.ThinkingLevel.LOW


@pytest.mark.asyncio
async def test_hedged_race_primary_fast_wins(adapter):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = GeneratedDeckSchema(
        cards=[
            GeneratedCardSchema(
                archetype="Arquetipo C: Pregunta Atómica",
                front="[Tema > Sub] Pregunta 1",
                back="Respuesta 1",
                tags=["redes"],
                explanation="Diagrama 1",
            )
        ]
    )

    async def mock_execute_single_tier(client, model_name, contents, instruction):
        await asyncio.sleep(0.05)
        return mock_response.parsed

    with patch.object(adapter, "_execute_single_tier", side_effect=mock_execute_single_tier):
        t0 = time.perf_counter()
        result = await adapter._race_hedged_generation(mock_client, ["content"], "instruction")
        elapsed = time.perf_counter() - t0

        assert len(result.cards) == 1
        assert result.cards[0].front == "[Tema > Sub] Pregunta 1"
        assert elapsed < 0.12


@pytest.mark.asyncio
async def test_hedged_race_speculative_secondary_wins(adapter):
    mock_client = MagicMock()

    async def mock_execute_single_tier(client, model_name, contents, instruction):
        if model_name == "gemini-3.8-flash":
            await asyncio.sleep(0.8)
            return GeneratedDeckSchema(cards=[GeneratedCardSchema(archetype="A", front="P1", back="R1")])
        elif model_name == "gemini-3.6-flash":
            await asyncio.sleep(0.05)
            return GeneratedDeckSchema(cards=[GeneratedCardSchema(archetype="B", front="P2_Secondary", back="R2")])
        else:
            await asyncio.sleep(0.5)
            return GeneratedDeckSchema(cards=[])

    with patch.object(adapter, "_execute_single_tier", side_effect=mock_execute_single_tier):
        t0 = time.perf_counter()
        result = await adapter._race_hedged_generation(mock_client, ["content"], "instruction")
        elapsed = time.perf_counter() - t0

        assert len(result.cards) == 1
        assert result.cards[0].front == "P2_Secondary"
        assert elapsed < 0.35


@pytest.mark.asyncio
async def test_hedged_race_fast_failover_succeeds(adapter):
    mock_client = MagicMock()

    async def mock_execute_single_tier(client, model_name, contents, instruction):
        if model_name == "gemini-3.8-flash":
            await asyncio.sleep(0.02)
            raise RuntimeError("503 Service Unavailable")
        elif model_name == "gemini-3.6-flash":
            await asyncio.sleep(0.04)
            return GeneratedDeckSchema(cards=[GeneratedCardSchema(archetype="C", front="P_Failover", back="R")])
        raise RuntimeError("should not be reached")

    with patch.object(adapter, "_execute_single_tier", side_effect=mock_execute_single_tier):
        t0 = time.perf_counter()
        result = await adapter._race_hedged_generation(mock_client, ["content"], "instruction")
        elapsed = time.perf_counter() - t0

        assert len(result.cards) == 1
        assert result.cards[0].front == "P_Failover"
        assert elapsed < 0.15


@pytest.mark.asyncio
async def test_hedged_race_all_fail_raises_runtime_error(adapter):
    mock_client = MagicMock()

    async def mock_execute_single_tier(client, model_name, contents, instruction):
        await asyncio.sleep(0.02)
        raise RuntimeError(f"Model {model_name} failed")

    with patch.object(adapter, "_execute_single_tier", side_effect=mock_execute_single_tier):
        with pytest.raises(RuntimeError) as exc_info:
            await adapter._race_hedged_generation(mock_client, ["content"], "instruction")
        assert "All Gemini tier models failed in hedged race" in str(exc_info.value)
