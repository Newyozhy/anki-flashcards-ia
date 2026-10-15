import pytest
from unittest.mock import AsyncMock, MagicMock
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import CardType, DeckNoteRecord, Flashcard
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.services.deck_dag_service import DeckDAGService
from app.services.sanitation_service import SanitationService


@pytest.fixture
def test_store(tmp_path):
    db_path = tmp_path / "test_ordering.db"
    return DeckKnowledgeStore(db_path=str(db_path))


@pytest.fixture
def mock_anki_bridge():
    bridge = MagicMock(spec=IAnkiBridgePort)
    bridge.check_status = AsyncMock()
    bridge.get_deck_names = AsyncMock(return_value=["Test Deck"])
    bridge.create_notes = AsyncMock(return_value=[201, 202])
    bridge.delete_notes = AsyncMock(return_value=1)
    bridge.reposition_cards = AsyncMock(return_value=True)
    bridge.get_cards_info = AsyncMock()
    bridge.get_note_cards = AsyncMock()
    bridge.get_deck_notes = AsyncMock()
    return bridge


@pytest.mark.asyncio
async def test_replace_note_transactionally_local_splicing(test_store, mock_anki_bridge):
    deck = "Oracle Cloud"
    source_note_id = 100

    # Mock original card located at slot due=42
    mock_anki_bridge.get_note_cards.side_effect = [
        [1001],  # original card IDs for source_note_id 100
        [2001, 2002],  # newly created card IDs for notes 201, 202
    ]
    mock_anki_bridge.get_cards_info.return_value = [
        {"cardId": 1001, "queue": 0, "due": 42}
    ]

    service = SanitationService(
        anki_bridge=mock_anki_bridge,
        store=test_store,
    )

    new_cards = [
        Flashcard(archetype="B", front="[OCI] Matriz", back="Diff", explanation="⚠️ Trampa"),
        Flashcard(front="[Fundamentos] Prerrequisito", back="Base", tags=["prerrequisito"]),
    ]

    response = await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=source_note_id,
        new_cards=new_cards,
    )

    assert response.success is True
    assert response.deleted_note_id == source_note_id

    # Verify reposition_cards was called with original_due=42 and shift=True
    mock_anki_bridge.reposition_cards.assert_called_once_with(
        card_ids=[2001, 2002],
        starting_from=42,
        step=1,
        shift=True,
    )


@pytest.mark.asyncio
async def test_audit_pedagogical_deck_order_inversion_detection(test_store, mock_anki_bridge):
    deck = "Oracle Cloud"

    # 1. Setup DAG concepts in SQLite: Level 0 (VCN) and Level 1 (Route Table)
    test_store.upsert_concept_node(
        deck_name=deck,
        concept_id="vcn",
        name="Virtual Cloud Network",
        taxonomy_path="oci::net",
        depth_level=0,
    )
    test_store.upsert_concept_node(
        deck_name=deck,
        concept_id="route_table",
        name="Route Table",
        taxonomy_path="oci::net::rt",
        depth_level=1,
    )
    test_store.upsert_concept_edge(
        deck_name=deck,
        source_id="vcn",
        target_id="route_table",
        relation_type="requires",
    )

    # Link notes: Note 101 -> Level 1 (Route Table), Note 102 -> Level 0 (VCN)
    test_store.link_card_to_concept(deck, 101, "route_table", role="target")
    test_store.link_card_to_concept(deck, 102, "vcn", role="target")

    # Mark both as optimal (sanitized)
    test_store.save_note_embeddings(deck, [
        {"note_id": 101, "front": "RT", "back": "A", "quality_status": "optimal"},
        {"note_id": 102, "front": "VCN", "back": "B", "quality_status": "optimal"},
    ])

    # 2. Simulate inverted order in Anki: Note 101 (Level 1) is at due=5, while Note 102 (Level 0) is at due=20
    mock_anki_bridge.get_deck_notes.return_value = [
        DeckNoteRecord(
            note_id=101,
            deck_name=deck,
            model_name="Basic",
            card_type=CardType.BASIC,
            front="RT",
            back="A",
            card_ids=[1011],
        ),
        DeckNoteRecord(
            note_id=102,
            deck_name=deck,
            model_name="Basic",
            card_type=CardType.BASIC,
            front="VCN",
            back="B",
            card_ids=[1021],
        ),
    ]

    mock_anki_bridge.get_cards_info.return_value = [
        {"cardId": 1011, "queue": 0, "due": 5},
        {"cardId": 1021, "queue": 0, "due": 20},
    ]

    dag_service = DeckDAGService(test_store)
    service = SanitationService(
        anki_bridge=mock_anki_bridge,
        store=test_store,
        dag_service=dag_service,
    )

    audit = await service.audit_pedagogical_deck_order(deck)

    assert audit.is_pedagogically_sound is False
    assert audit.inversions_count >= 1
    assert any("Nivel 1" in v.reason and "Nivel 0" in v.reason for v in audit.violations)

    # 3. Now align deck topologically
    realign_res = await service.reposition_deck_topologically(deck)
    assert realign_res["success"] is True

    # Check reposition was invoked with Level 0 note card (1021) BEFORE Level 1 note card (1011)
    call_args = mock_anki_bridge.reposition_cards.call_args[0]
    ordered_ids = call_args[0]
    assert ordered_ids == [1021, 1011]

    # Verify that once cards are in aligned order in Anki, audit reports 0 inversions and sound
    mock_anki_bridge.get_cards_info.return_value = [
        {"cardId": 1021, "queue": 0, "due": 0},
        {"cardId": 1011, "queue": 0, "due": 1},
    ]
    audit_after = await service.audit_pedagogical_deck_order(deck)
    assert audit_after.inversions_count == 0
    assert audit_after.is_pedagogically_sound is True


@pytest.mark.asyncio
async def test_replace_note_transactionally_skips_splicing_when_queue_not_zero(test_store, mock_anki_bridge):
    """Q4 regression: If original note was in review (queue == 2) rather than new (queue == 0), skip local reposition."""
    deck = "Oracle Cloud"
    source_note_id = 500

    # Original card is in review queue (queue == 2)
    mock_anki_bridge.get_note_cards.side_effect = [
        [5001],
        [6001],
    ]
    mock_anki_bridge.get_cards_info.return_value = [
        {"cardId": 5001, "queue": 2, "due": 180}
    ]
    mock_anki_bridge.reposition_cards.reset_mock()

    service = SanitationService(
        anki_bridge=mock_anki_bridge,
        store=test_store,
    )

    new_cards = [
        Flashcard(front="Front atomic", back="Back atomic"),
    ]

    response = await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=source_note_id,
        new_cards=new_cards,
    )

    assert response.success is True
    # reposition_cards MUST NOT be called because queue != 0!
    mock_anki_bridge.reposition_cards.assert_not_called()
