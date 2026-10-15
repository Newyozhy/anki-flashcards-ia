from unittest.mock import AsyncMock, MagicMock
import pytest
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import CardType, DeckNoteRecord, Flashcard, GenerationOptions, LearningPlanContract
from app.services.sanitation_service import SanitationService


@pytest.fixture
def sanitation_setup(tmp_path):
    db_file = tmp_path / "test_sanitation.db"
    store = DeckKnowledgeStore(db_path=str(db_file))
    mock_bridge = MagicMock()
    service = SanitationService(anki_bridge=mock_bridge, store=store)
    deck = "Oracle Cloud"
    return store, mock_bridge, service, deck


@pytest.mark.asyncio
async def test_get_sanitation_queue_prioritizes_bad_notes(sanitation_setup):
    store, mock_bridge, service, deck = sanitation_setup

    # Mock Anki returning 3 notes
    mock_bridge.get_deck_notes = AsyncMock(
        return_value=[
            DeckNoteRecord(note_id=101, deck_name=deck, model_name="Basic", front="What is VCN?", back="Virtual Cloud Network"),
            DeckNoteRecord(note_id=102, deck_name=deck, model_name="Basic", front="Complex OCI rules", back="A massive wall of text"),
            DeckNoteRecord(note_id=103, deck_name=deck, model_name="Basic", front="What is CIDR?", back="Classless Inter-Domain Routing"),
        ]
    )

    # In SQLite, mark 102 as 'bad', 103 as 'optimal', 101 as unreviewed
    store.save_note_embeddings(
        deck,
        [
            {"note_id": 101, "front": "What is VCN?", "back": "Virtual Cloud Network"},
            {"note_id": 102, "front": "Complex OCI rules", "back": "A massive wall of text"},
            {"note_id": 103, "front": "What is CIDR?", "back": "Classless Inter-Domain Routing"},
        ],
    )
    store.update_note_quality(deck, 102, "bad", 0.2, "Cognitive overload")
    store.update_note_quality(deck, 103, "optimal", 0.95, "Clean atomic note")

    # Contract approved
    contract = LearningPlanContract(
        deck_name=deck,
        version=1,
        status="approved",
        bloom_level="Application",
        exclusion_boundary=["FastConnect"],
        gap_strategy="fill_critical_only",
        operational_depth="Standard",
        raw_summary="Test contract summary",
    )
    store.save_learning_contract(deck, contract.model_dump())

    res = await service.get_sanitation_queue(deck)
    assert res.deck_name == deck
    assert res.total_notes == 3
    assert res.sanitized_count == 1  # Note 103 is optimal
    assert res.pending_count == 2  # Notes 102 and 101
    assert res.contract_approved is True

    # Note 102 (bad) must be sorted BEFORE Note 101 (unreviewed)
    assert res.notes[0].note_id == 102
    assert res.notes[0].quality_status == "bad"
    assert res.notes[1].note_id == 101
    assert res.notes[1].quality_status == "unreviewed"


@pytest.mark.asyncio
async def test_replace_note_transactionally_success(sanitation_setup):
    store, mock_bridge, service, deck = sanitation_setup

    # Setup initial note in store
    store.save_note_embeddings(deck, [{"note_id": 500, "front": "Old dense card", "back": "Too much content"}])

    # Configure mock bridge
    mock_bridge.create_notes = AsyncMock(return_value=[501, 502, 503])
    mock_bridge.delete_notes = AsyncMock(return_value=1)
    mock_bridge.get_deck_notes = AsyncMock(return_value=[])

    new_cards = [
        Flashcard(
            id="c1",
            card_type=CardType.BASIC,
            front="Atomic question 1",
            back="Short answer 1",
        ),
        Flashcard(
            id="c2",
            card_type=CardType.CLOZE,
            front="Atomic cloze {{c1::fact}}",
            back="Extra notes",
        ),
        Flashcard(
            id="c3",
            card_type=CardType.BASIC,
            front="Atomic question 3",
            back="Short answer 3",
        ),
    ]

    res = await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=500,
        new_cards=new_cards,
    )

    assert res.success is True
    assert res.deleted_note_id == 500
    assert res.created_note_ids == [501, 502, 503]
    assert res.created_cards_count == 3

    # Verify bridge was called in proper transactional order
    mock_bridge.create_notes.assert_awaited_once_with(deck_name=deck, cards=new_cards)
    mock_bridge.delete_notes.assert_awaited_once_with([500])

    # Verify new cards were registered as optimal in store
    indexed = store.get_all_indexed_notes(deck)
    indexed_map = {n["note_id"]: n for n in indexed}
    assert 500 not in indexed_map
    assert 501 in indexed_map
    assert indexed_map[501]["quality_status"] == "optimal"


@pytest.mark.asyncio
async def test_replace_note_transactionally_rolls_back_if_creation_fails(sanitation_setup):
    store, mock_bridge, service, deck = sanitation_setup

    store.save_note_embeddings(deck, [{"note_id": 999, "front": "Crucial note", "back": "Must not be lost"}])

    # AnkiConnect returns empty list or fails
    mock_bridge.create_notes = AsyncMock(return_value=[])
    mock_bridge.delete_notes = AsyncMock()

    new_cards = [
        Flashcard(
            id="c1",
            card_type=CardType.BASIC,
            front="Atomic question 1",
            back="Short answer 1",
        )
    ]

    with pytest.raises(RuntimeError, match="Fallo en AnkiConnect"):
        await service.replace_note_transactionally(
            deck_name=deck,
            source_note_id=999,
            new_cards=new_cards,
        )

    # CRITICAL: delete_notes must NEVER be called if create_notes failed
    mock_bridge.delete_notes.assert_not_called()

    # Note 999 must still exist in SQLite index
    indexed = store.get_all_indexed_notes(deck)
    assert any(n["note_id"] == 999 for n in indexed)


@pytest.mark.asyncio
async def test_generate_cards_injects_cluster_mutual_negative_boundaries(tmp_path):
    """Verify that GenerateCardsUseCase dynamically extracts sibling boundaries from cluster."""
    from app.services.generate_cards_service import GenerateCardsUseCase
    from app.ports.card_generator_port import ICardGeneratorPort

    db_file = tmp_path / "test_gen_boundaries.db"
    store = DeckKnowledgeStore(db_path=str(db_file))
    deck = "AI Deck"

    # Insert sibling notes in same cluster
    notes = [
        {"note_id": 201, "front": "[Agent > Loop > Cycle] Cycle", "back": "T-A-O", "embedding": [1.0, 0.0]},
        {"note_id": 202, "front": "[Agent > Tools > Schemas] Schemas", "back": "JSON", "embedding": [0.9, 0.1]},
        {"note_id": 203, "front": "[Agent > ReAct > Rationale] Rationale", "back": "Grounding", "embedding": [0.8, 0.2]},
    ]
    store.save_note_embeddings(deck, notes)
    store.save_deck_clusters(
        deck,
        [{"cluster_index": 0, "title": "Agents", "scope": "Agent architecture", "note_ids": [201, 202, 203]}],
    )

    captured_options = None

    class MockGenerator(ICardGeneratorPort):
        async def generate_from_text(self, text, options):
            nonlocal captured_options
            captured_options = options
            return [Flashcard(front="Generated Front", back="Generated Back")]

        async def generate_from_text_stream(self, text, options):
            yield ("batch", [Flashcard(front="Generated Front", back="Generated Back")], 1, 1)

        async def generate_from_media(self, file_bytes, mime_type, options, text=None):
            return [Flashcard(front="Generated Front", back="Generated Back")]

        async def inspect_material(self, text, options, media_parts=None):
            pass

        async def inspect_material_from_media(self, file_bytes, mime_type, options, text=None):
            pass

        async def enrich_prerequisite(self, concept, search_query="", context_topic=""):
            pass

    use_case = GenerateCardsUseCase(card_generator=MockGenerator(), store=store)

    # Call with source_note_id=201 (Agent Loop) and neighbor_concepts=None
    options = GenerationOptions(deck_name=deck, source_note_id=201)
    await use_case.execute_from_text("Agent loop text", options)

    assert captured_options is not None
    assert captured_options.neighbor_concepts is not None
    assert "Schemas" in captured_options.neighbor_concepts
    assert "Rationale" in captured_options.neighbor_concepts
    assert "Cycle" not in captured_options.neighbor_concepts


@pytest.mark.asyncio
async def test_get_sanitation_queue_topological_dag_order(sanitation_setup):
    """Verify that get_sanitation_queue sorts notes by active stage, depth_level ASC, quality_rank, and topological index."""
    store, mock_bridge, service, deck = sanitation_setup

    # Setup DAG concepts: A (depth 1) -> B (depth 2) -> C (depth 3)
    store.upsert_concept_node(deck, "node_a", "Foundations", taxonomy_path="Core > Foundations", depth_level=1, stage_id="stage_1")
    store.upsert_concept_node(deck, "node_b", "Intermediate", taxonomy_path="Core > Intermediate", depth_level=2, stage_id="stage_1")
    store.upsert_concept_node(deck, "node_c", "Advanced", taxonomy_path="Core > Advanced", depth_level=3, stage_id="stage_1")
    store.upsert_concept_edge(deck, "node_a", "node_b", "requires")
    store.upsert_concept_edge(deck, "node_b", "node_c", "requires")

    # Mock notes in Anki
    mock_bridge.get_deck_notes = AsyncMock(
        return_value=[
            DeckNoteRecord(note_id=101, deck_name=deck, model_name="Basic", front="Advanced note", back="Ans C"),
            DeckNoteRecord(note_id=102, deck_name=deck, model_name="Basic", front="Foundational note", back="Ans A"),
            DeckNoteRecord(note_id=103, deck_name=deck, model_name="Basic", front="Intermediate note", back="Ans B"),
            DeckNoteRecord(note_id=104, deck_name=deck, model_name="Basic", front="Unmapped note", back="Ans Unmapped"),
            DeckNoteRecord(note_id=105, deck_name=deck, model_name="Basic", front="Already optimal note", back="Ans Optimal"),
        ]
    )

    # Link mappings
    store.link_card_to_concept(deck, 101, "node_c", role="target")
    store.link_card_to_concept(deck, 102, "node_a", role="target")
    store.link_card_to_concept(deck, 103, "node_b", role="target")

    # In SQLite index
    store.save_note_embeddings(
        deck,
        [
            {"note_id": 101, "front": "Advanced note", "back": "Ans C", "quality_status": "bad"},
            {"note_id": 102, "front": "Foundational note", "back": "Ans A", "quality_status": "unreviewed"},
            {"note_id": 103, "front": "Intermediate note", "back": "Ans B", "quality_status": "bad"},
            {"note_id": 104, "front": "Unmapped note", "back": "Ans Unmapped", "quality_status": "unreviewed"},
            {"note_id": 105, "front": "Already optimal note", "back": "Ans Optimal", "quality_status": "optimal"},
        ],
    )

    res = await service.get_sanitation_queue(deck)
    assert res.total_notes == 5
    assert res.sanitized_count == 1
    assert res.pending_count == 4

    # Order must be:
    # 1. Note 102 (depth 1)
    # 2. Note 103 (depth 2)
    # 3. Note 101 (depth 3)
    # 4. Note 104 (unmapped, depth 999)
    order_nids = [n.note_id for n in res.notes]
    assert order_nids == [102, 103, 101, 104]


@pytest.mark.asyncio
async def test_replace_note_transactionally_links_mappings_and_ledger(sanitation_setup):
    """Verify that replace_note_transactionally links target concepts and records ledger collisions."""
    store, mock_bridge, service, deck = sanitation_setup
    from app.domain.models import SanitationCoverageLedgerInput

    # Setup concepts
    store.upsert_concept_node(deck, "vcn_id", "VCN Architecture", taxonomy_path="Net > VCN", depth_level=1)
    store.upsert_concept_node(deck, "subnet_id", "Subnets", taxonomy_path="Net > Subnets", depth_level=2)

    # Note 500 being replaced
    store.save_note_embeddings(deck, [{"note_id": 500, "front": "Monolith VCN", "back": "All about VCN and Subnets"}])
    store.link_card_to_concept(deck, 500, "vcn_id", role="target")

    mock_bridge.create_notes = AsyncMock(return_value=[501, 502])
    mock_bridge.delete_notes = AsyncMock(return_value=1)
    mock_bridge.get_deck_notes = AsyncMock(return_value=[])

    new_cards = [
        Flashcard(id="c1", front="Atomic VCN Question", back="VCN Ans"),
        Flashcard(id="c2", front="Atomic Subnet Question", back="Subnet Ans"),
    ]

    collisions = [
        SanitationCoverageLedgerInput(
            colliding_note_id=600,
            concept_title="Subnets",
            facet_summary="Subnet CIDR division",
        )
    ]

    res = await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=500,
        new_cards=new_cards,
        target_concepts=["VCN Architecture", "Subnets"],
        pending_ledger_collisions=collisions,
    )

    assert res.success is True
    assert res.created_note_ids == [501, 502]

    # Verify concept mappings: notes 501 and 502 linked to vcn_id and subnet_id
    mappings = store.get_card_concept_mappings(deck)
    mapped_nids = {m["note_id"] for m in mappings}
    assert 500 not in mapped_nids
    assert 501 in mapped_nids
    assert 502 in mapped_nids

    # Verify coverage ledger: note 600 recorded
    ledger = store.get_ledger_entries_for_note(deck, 600)
    assert len(ledger) == 1
    assert ledger[0]["source_sanitized_note_id"] == 500
    assert ledger[0]["covered_concept_title"] == "Subnets"
    assert ledger[0]["created_atomic_note_ids"] == [501, 502]

    # Clean up ledger when note 600 gets its turn
    mock_bridge.create_notes = AsyncMock(return_value=[601])
    mock_bridge.delete_notes = AsyncMock(return_value=1)
    await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=600,
        new_cards=[Flashcard(id="c3", front="Q", back="A")],
    )
    ledger_after = store.get_ledger_entries_for_note(deck, 600)
    assert len(ledger_after) == 0


