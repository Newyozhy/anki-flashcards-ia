import pytest
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import ExtractedNoteKnowledge, LearningPlanContract
from app.services.deck_dag_service import DeckDAGService
from app.services.deck_interview_service import DeckInterviewService


@pytest.fixture
def interview_setup(tmp_path):
    db_file = tmp_path / "test_interview.db"
    store = DeckKnowledgeStore(db_path=str(db_file))
    dag_service = DeckDAGService(store=store)

    # Ingest sample OCI cards into the DAG
    deck = "Oracle Cloud"
    ext1 = ExtractedNoteKnowledge(
        source_note_id=201,
        raw_front="¿Qué es un Route Table en OCI?",
        raw_back="Reglas virtuales asociadas a subnets.",
        extracted_facts=["Route tables dirigen tráfico fuera de subnets."],
        target_concepts=["OCI Route Table"],
        assumed_prerequisites=["OCI VCN", "CIDR"],
        taxonomy_path="oci::networking",
    )
    dag_service.ingest_note_extractions(deck, [ext1])

    service = DeckInterviewService(
        store=store,
        dag_service=dag_service,
        gemini_api_key=None,
        groq_api_key=None,
    )
    return store, dag_service, service, deck


@pytest.mark.asyncio
async def test_generate_interview_form_has_4_slots(interview_setup):
    store, dag_service, service, deck = interview_setup

    form = await service.generate_interview_form(deck)
    assert form.deck_name == deck
    assert form.detected_concepts_count >= 1
    assert len(form.orphan_concepts) >= 1  # VCN and CIDR are orphans
    assert len(form.questions) == 4

    slot_keys = [q.slot_key for q in form.questions]
    assert "bloom_level" in slot_keys
    assert "exclusion_boundary" in slot_keys
    assert "gap_strategy" in slot_keys
    assert "operational_depth" in slot_keys


@pytest.mark.asyncio
async def test_synthesize_refine_and_approve_contract(interview_setup):
    store, dag_service, service, deck = interview_setup

    # 1. Synthesize from answers
    answers = {
        "bloom_level": "Diseño y Análisis Arquitectónico",
        "exclusion_boundary": "Excluir arquitecturas híbridas y FastConnect",
        "gap_strategy": "fill_all_anchors",
        "operational_depth": "Lógica y Arquitectura Conceptual (Sin comandos)",
    }

    contract = await service.synthesize_contract(deck, answers)
    assert contract.deck_name == deck
    assert contract.status == "draft"
    assert contract.version == 1
    assert "Diseño" in contract.bloom_level
    assert contract.gap_strategy == "fill_all_anchors"

    # 2. Refine via natural language
    refined = await service.refine_contract(
        deck_name=deck,
        current_contract=contract,
        user_feedback="Agregar exclusión de políticas IAM avanzadas",
    )
    assert refined.version == 2
    assert refined.status == "draft"
    assert "IAM" in refined.raw_summary

    # 3. Approve and Lock
    approved = service.approve_contract(deck, refined)
    assert approved.status == "approved"
    assert approved.approved_at is not None

    # 4. Verify persistence
    saved = service.get_learning_contract(deck)
    assert saved is not None
    assert saved.status == "approved"
    assert saved.version == 2
