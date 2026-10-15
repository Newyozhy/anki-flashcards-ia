import pytest
from unittest.mock import MagicMock, patch
from app.adapters.ai.gemini_card_generator_adapter import (
    GeminiCardGeneratorAdapter,
    InspectedStudyPlanSchema,
    InspectedCoreThemeSchema,
    InspectedPrerequisiteSchema,
    EnrichedPrerequisiteSchema,
)
from app.domain.models import GenerationOptions, CardType
from app.services.inspect_material_service import InspectMaterialUseCase, EnrichPrerequisiteUseCase


@pytest.fixture
def adapter():
    return GeminiCardGeneratorAdapter(
        api_key="mock_key",
        model="gemini-3.8-flash",
    )


def test_system_instruction_with_prerequisites_and_themes(adapter):
    options = GenerationOptions(
        deck_name="Sistemas Distribuidos",
        card_type=CardType.BASIC,
        prerequisites_context="RPC (Remote Procedure Call): Protocolo donde un programa ejecuta subrutinas en otro espacio de direcciones.",
        selected_themes=["Elección de Líder en Raft", "Replicación de Log"],
    )
    instruction = adapter._build_system_instruction(options)

    assert "PRERREQUISITOS Y CONCEPTOS BASE ANCLADOS" in instruction
    assert "RPC (Remote Procedure Call)" in instruction
    assert "[Fundamentos > Nombre]" in instruction
    assert "EJES TEMÁTICOS PRIORIZADOS" in instruction
    assert "Elección de Líder en Raft" in instruction
    assert "Replicación de Log" in instruction


@pytest.mark.asyncio
async def test_inspect_material_use_case(adapter):
    mock_plan = InspectedStudyPlanSchema(
        topic_name="Consenso Raft",
        self_sufficiency_score=65,
        self_sufficiency_verdict="El texto asume conocimiento previo de RPC y quórum de mayoría.",
        core_themes=[
            InspectedCoreThemeSchema(
                title="Elección de Líder",
                description="Mecanismo de timers aleatorios y votos",
                recommended_cards=3,
            )
        ],
        prerequisites=[
            InspectedPrerequisiteSchema(
                concept="RPC",
                reason="Raft utiliza RequestVote RPC y AppendEntries RPC",
                is_covered_in_text=False,
                search_query="Remote procedure call basics",
            ),
            InspectedPrerequisiteSchema(
                concept="Heartbeats",
                reason="Señales periódicas del líder",
                is_covered_in_text=True,
                search_query="Distributed systems heartbeats",
            ),
        ],
        suggested_total_cards=4,
    )

    with patch.object(adapter, "_race_hedged_generation", return_value=mock_plan):
        use_case = InspectMaterialUseCase(card_generator=adapter)
        result = await use_case.execute("Texto de Raft...", GenerationOptions())

        assert result.topic_name == "Consenso Raft"
        assert result.self_sufficiency_score == 65
        assert len(result.core_themes) == 1
        assert result.core_themes[0].title == "Elección de Líder"
        assert len(result.prerequisites) == 2
        # Missing prerequisite should be auto-selected for enrichment
        assert result.prerequisites[0].concept == "RPC"
        assert result.prerequisites[0].selected is True
        # Covered prerequisite should not be selected by default
        assert result.prerequisites[1].concept == "Heartbeats"
        assert result.prerequisites[1].selected is False


@pytest.mark.asyncio
async def test_enrich_prerequisite_use_case(adapter):
    mock_enriched = EnrichedPrerequisiteSchema(
        concept="RPC",
        summary="RPC permite que un nodo ejecute procedimientos en otro nodo transparente a la red.",
        key_takeaway="Es la base de comunicación síncrona cliente-servidor en sistemas distribuidos.",
    )

    with patch.object(adapter, "_race_hedged_generation", return_value=mock_enriched):
        use_case = EnrichPrerequisiteUseCase(card_generator=adapter)
        result = await use_case.execute(
            concept="RPC",
            search_query="Remote procedure call basics",
            context_topic="Raft",
        )

        assert result.concept == "RPC"
        assert "procedimientos en otro nodo" in result.summary
        assert "base de comunicación" in result.key_takeaway


@pytest.mark.asyncio
async def test_inspect_material_from_media_use_case(adapter):
    mock_plan = InspectedStudyPlanSchema(
        topic_name="Árboles B y Almacenamiento en Disco",
        self_sufficiency_score=70,
        self_sufficiency_verdict="El diagrama expone la estructura de nodos pero omite el mecanismo de split ante overflow.",
        core_themes=[
            InspectedCoreThemeSchema(
                title="Estructura e Invariantes de Nodos",
                description="Número de claves y punteros por bloque",
                recommended_cards=3,
            )
        ],
        prerequisites=[
            InspectedPrerequisiteSchema(
                concept="I/O de Bloques en Disco",
                reason="Obligatorio para justificar por qué se usan nodos anchos en lugar de árboles binarios",
                is_covered_in_text=False,
                search_query="Disk block I/O B-Tree rationale",
            )
        ],
        suggested_total_cards=3,
    )

    with patch.object(adapter, "_race_hedged_generation", return_value=mock_plan):
        use_case = InspectMaterialUseCase(card_generator=adapter)
        result = await use_case.execute_from_media(
            b"%PDF-1.4 mock content", "application/pdf", GenerationOptions()
        )

        assert result.topic_name == "Árboles B y Almacenamiento en Disco"
        assert result.self_sufficiency_score == 70
        assert len(result.core_themes) == 1
        assert len(result.prerequisites) == 1
        assert result.prerequisites[0].is_covered_in_text is False
        assert result.prerequisites[0].selected is True


@pytest.mark.asyncio
async def test_multimodal_inspection_with_anki_media(adapter):
    from unittest.mock import AsyncMock

    mock_plan = InspectedStudyPlanSchema(
        topic_name="Anatomía del Encéfalo",
        self_sufficiency_score=85,
        self_sufficiency_verdict="El diagrama ilustra con precisión los ventrículos y el tronco.",
        core_themes=[
            InspectedCoreThemeSchema(
                title="Sistema Ventricular",
                description="Circulación de LCR en ventrículos laterales y tercer ventrículo",
                recommended_cards=3,
                associated_diagrams=["paste-brain-ventricles.png"],
            )
        ],
        prerequisites=[],
        suggested_total_cards=3,
    )

    mock_anki_bridge = MagicMock()
    mock_anki_bridge.retrieve_media_base64 = AsyncMock(
        return_value="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )

    with patch.object(adapter, "_race_hedged_generation", return_value=mock_plan):
        use_case = InspectMaterialUseCase(card_generator=adapter, anki_bridge=mock_anki_bridge)
        result = await use_case.execute(
            text="Explicación del sistema ventricular",
            options=GenerationOptions(),
            source_note_id=12345,
            media_files=["paste-brain-ventricles.png"],
        )

        assert result.topic_name == "Anatomía del Encéfalo"
        assert result.source_note_id == 12345
        assert result.inherited_media_files == ["paste-brain-ventricles.png"]
        assert len(result.core_themes) == 1
        assert result.core_themes[0].associated_diagrams == ["paste-brain-ventricles.png"]
        mock_anki_bridge.retrieve_media_base64.assert_called_once_with("paste-brain-ventricles.png")


