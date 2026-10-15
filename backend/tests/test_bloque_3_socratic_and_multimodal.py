import os
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    CardType,
    CoreTheme,
    CoreThemeItem,
    Flashcard,
    GenerationOptions,
    PrerequisiteItem,
    PrerequisiteMatchStatus,
    SocraticEvaluateRequest,
)
from app.services.deck_dag_service import DeckDAGService
from app.services.deck_intelligence_service import DeckIntelligenceService
from app.services.inspect_material_service import InspectMaterialUseCase
from app.services.socratic_red_teaming_service import SocraticRedTeamingService


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_bloque3.db")


@pytest.fixture
def store(test_db_path):
    return DeckKnowledgeStore(db_path=test_db_path)


@pytest.fixture
def mock_embedding_port():
    port = MagicMock()
    port.embed_texts = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    return port


@pytest.mark.asyncio
async def test_match_study_plan_with_coverage_ledger(store, mock_embedding_port):
    """Verify that match_study_plan uses ledger entries to mark previously covered sibling themes as DOMINATED."""
    deck_name = "Networking"

    # 1. Record coverage in ledger: Note 101 covered 'Modelo OSI - Capa Red' on behalf of colliding Note 202
    store.record_ledger_coverage(
        deck_name=deck_name,
        source_note_id=101,
        colliding_note_id=202,
        concept_title="Modelo OSI - Capa Red",
        facet_summary="Enrutamiento de paquetes y direccionamiento IP",
        created_atomic_note_ids=[1001, 1002],
    )

    # 2. Setup DeckIntelligenceService
    service = DeckIntelligenceService(
        anki_bridge=MagicMock(),
        embedding_port=mock_embedding_port,
        store=store,
    )

    # 3. Call match_study_plan for note 202
    themes = [
        CoreThemeItem(
            title="Modelo OSI - Capa Red",
            description="Mecanismo de conmutación de paquetes IP",
            recommended_cards=2,
        ),
        CoreThemeItem(
            title="Modelo OSI - Capa Enlace",
            description="Tramas Ethernet y direcciones MAC",
            recommended_cards=2,
        ),
    ]

    response = await service.match_study_plan(
        deck_name=deck_name,
        prerequisites=[],
        themes=themes,
        source_note_id=202,
    )

    assert len(response.theme_matches) == 2

    # Theme 1 must be DOMINATED due to ledger
    t1 = response.theme_matches[0]
    assert t1.concept == "Modelo OSI - Capa Red"
    assert t1.status == PrerequisiteMatchStatus.DOMINATED
    assert t1.suggested_action == "keep_existing"
    assert t1.should_replace is False
    assert t1.matched_note_id == 101
    assert "#1001" in t1.verdict_explanation
    assert "#1002" in t1.verdict_explanation

    # Theme 2 is GAP (not in ledger and no indexed notes)
    t2 = response.theme_matches[1]
    assert t2.concept == "Modelo OSI - Capa Enlace"
    assert t2.status == PrerequisiteMatchStatus.GAP
    assert t2.suggested_action == "create_new"


@pytest.mark.asyncio
async def test_inspect_material_8_image_cap_and_beginner_directive(store):
    """Verify that inspect material caps images at 8 and injects first-principles directive for beginner."""
    mock_generator = MagicMock()
    mock_generator.inspect_material = AsyncMock()

    mock_inspection = MagicMock()
    mock_inspection.prerequisites = []
    mock_generator.inspect_material.return_value = mock_inspection

    mock_anki = MagicMock()
    mock_anki.retrieve_media_base64 = AsyncMock(return_value="aW1hZ2VkYXRh")  # b64 "imagedata"

    use_case = InspectMaterialUseCase(
        card_generator=mock_generator,
        anki_bridge=mock_anki,
        store=store,
    )

    # 10 media files passed
    ten_images = [f"diag_{i}.png" for i in range(1, 11)]

    options = GenerationOptions(
        deck_name="CCNA",
        difficulty_level="beginner",
        card_type=CardType.BASIC,
    )

    result = await use_case.execute(
        text="Concepto de switching multicapa",
        options=options,
        source_note_id=50,
        media_files=ten_images,
    )

    # 1. Check capping at 8 images
    assert len(result.inherited_media_files) == 8
    assert result.inherited_media_files == ten_images[:8]
    assert mock_anki.retrieve_media_base64.call_count == 8

    # 2. Check beginner directive injection
    assert "[Perfil del Aprendiz: PRINCIPIANTE]" in options.custom_instructions
    assert "primeros principios" in options.custom_instructions


@pytest.mark.asyncio
async def test_socratic_challenge_and_evaluate_mastered(store):
    """Verify interactive Socratic Red-Teaming challenge generation and evaluation passing to MASTERED."""
    deck_name = "CCNA"
    concept_id = "osi_layer_3"

    # Setup concept node and cards
    store.upsert_concept_node(
        deck_name=deck_name,
        concept_id=concept_id,
        name="Capa 3 de Red",
        status="SUFFICIENT",
    )
    store.save_note_embeddings(
        deck_name=deck_name,
        notes=[
            {
                "note_id": 301,
                "front": "Capa 3: ¿Cuál es su PDU?",
                "back": "Paquete",
                "explanation": "⚠️ Trampa frecuente: No confundir con trama (capa 2) ni segmento (capa 4).",
                "clean_text": "Capa 3 PDU Paquete",
                "embedding": [0.1, 0.2],
            }
        ],
    )
    store.link_card_to_concept(deck_name, 301, concept_id, role="target")

    socratic_service = SocraticRedTeamingService(store=store, api_key=None)

    # 1. Generate challenge
    challenge_resp = await socratic_service.generate_challenge(deck_name, concept_id)
    assert challenge_resp.deck_name == deck_name
    assert challenge_resp.concept_id == concept_id
    assert challenge_resp.challenge.challenge_question is not None
    assert challenge_resp.eligible_for_mastery is True

    # 2. Evaluate with a high-substance answer (simulating deep causal model)
    good_answer = (
        "La capa de red se encarga del enrutamiento lógico de paquetes entre redes dispares mediante direcciones IP. "
        "Si falla, las capas 1 y 2 pueden estar operativas con link físico pero el tráfico inter-red es imposible."
    )
    eval_req = SocraticEvaluateRequest(
        concept_id=concept_id,
        challenge_question=challenge_resp.challenge.challenge_question,
        user_answer=good_answer,
    )

    eval_resp = await socratic_service.evaluate_response(deck_name, eval_req)

    assert eval_resp.passed is True
    assert eval_resp.score >= 0.75
    assert eval_resp.new_node_status == "MASTERED"

    # Verify node in SQLite store is updated to MASTERED
    node_in_db = store.get_concept_node(deck_name, concept_id)
    assert node_in_db is not None
    assert node_in_db["status"] == "MASTERED"

    # Verify DeckDAGService preserves MASTERED status
    dag_service = DeckDAGService(store=store)
    dag = dag_service.get_deck_dag(deck_name)
    dag_node = next(n for n in dag.nodes if n.id == concept_id)
    assert dag_node.status == "MASTERED"


@pytest.mark.asyncio
async def test_socratic_evaluate_failure_deck_gap_and_user_recall(store):
    """Verify that failing Socratic evaluations correctly branch into user_recall or deck_gap."""
    deck_name = "Cloud"
    concept_id = "vpc_peering"

    store.upsert_concept_node(
        deck_name=deck_name,
        concept_id=concept_id,
        name="VPC Peering",
        status="SUFFICIENT",
    )
    store.save_note_embeddings(
        deck_name=deck_name,
        notes=[
            {
                "note_id": 401,
                "front": "¿VPC Peering soporta enrutamiento transitivo?",
                "back": "No, es no-transitivo.",
                "explanation": "⚠️ Trampa frecuente / Error común: Creer que si A se conecta con B y B con C, A puede hablar con C. No existe enrutamiento transitivo.",
                "clean_text": "VPC Peering no transitivo",
                "embedding": [0.1, 0.2],
            }
        ],
    )
    store.link_card_to_concept(deck_name, 401, concept_id, role="target")

    socratic_service = SocraticRedTeamingService(store=store, api_key=None)

    # 1. Test user_recall failure (short / inadequate answer)
    bad_req = SocraticEvaluateRequest(
        concept_id=concept_id,
        challenge_question="¿Por qué VPC Peering no conecta A y C?",
        user_answer="No sé bien.",
    )
    bad_resp = await socratic_service.evaluate_response(deck_name, bad_req)

    assert bad_resp.passed is False
    assert bad_resp.score < 0.75
    assert bad_resp.failure_cause == "user_recall"
    assert bad_resp.relevant_card_id == 401
    assert bad_resp.relevant_card_front == "¿VPC Peering soporta enrutamiento transitivo?"
    assert "No existe enrutamiento transitivo" in bad_resp.relevant_card_trap

    # 2. Test deck_gap failure (mocked LLM outcome emitting deck_gap)
    # Simulate LLM response identifying a foundational gap
    socratic_service._api_key = "fake_key_for_mock"
    import unittest.mock as mock

    fake_eval_data = {
        "score": 0.40,
        "passed": False,
        "feedback": "El estudiante no comprende el concepto previo de CIDR overlapping.",
        "failure_cause": "deck_gap",
        "remedy_gap_title": "Solapamiento de Bloques CIDR",
    }

    with mock.patch("asyncio.to_thread") as mock_thread:
        mock_res = MagicMock()
        mock_res.text = str(fake_eval_data).replace("'", '"').replace("False", "false")
        mock_thread.return_value = mock_res

        gap_req = SocraticEvaluateRequest(
            concept_id=concept_id,
            challenge_question="¿Qué restricción de direccionamiento impide crear un peering?",
            user_answer="Creo que las IPs tienen que ser diferentes pero no recuerdo el concepto.",
        )
        gap_resp = await socratic_service.evaluate_response(deck_name, gap_req)

        assert gap_resp.passed is False
        assert gap_resp.failure_cause == "deck_gap"
        assert gap_resp.remedy_gap_title == "Solapamiento de Bloques CIDR"

        # Check orphan gap node was inserted in DAG
        gap_node = store.get_concept_node(deck_name, "solapamiento_de_bloques_cidr")
        assert gap_node is not None
        assert gap_node["name"] == "Solapamiento de Bloques CIDR"
        assert gap_node["status"] == "UNMAPPED"
