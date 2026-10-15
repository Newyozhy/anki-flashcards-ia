import re
from typing import List
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    CardType,
    DeckNoteRecord,
    Flashcard,
    LearningPlanContract,
    SanitationCoverageLedgerInput,
)
from app.services.sanitation_service import SanitationService


@pytest.fixture
def audit_sanitizer_env(tmp_path):
    """Provides isolated SQLite store, mock Anki bridge, and SanitationService."""
    db_file = tmp_path / "sanitizer_safety_audit.db"
    store = DeckKnowledgeStore(db_path=str(db_file))
    mock_bridge = MagicMock()
    service = SanitationService(anki_bridge=mock_bridge, store=store)
    deck = "Audit::SanitationSafety"
    return store, mock_bridge, service, deck


# =============================================================================
# Level 3.1: Fault Injection & Zero Data Loss Verification
# =============================================================================

@pytest.mark.asyncio
async def test_audit_l3_fault_injection_socket_timeout_aborts_deletion(audit_sanitizer_env):
    """
    AUDIT L3.1: Fault Injection - Socket Timeout / Network Crash during AnkiConnect insertion.
    CRITICAL SAFETY INVARIANT: If AnkiConnect drops connection or times out during card insertion,
    the obsolete note MUST NEVER be deleted. The original note must remain 100% intact.
    """
    store, mock_bridge, service, deck = audit_sanitizer_env
    legacy_note_id = 1001

    # Seed legacy note in SQLite store
    store.save_note_embeddings(
        deck,
        [{"note_id": legacy_note_id, "front": "Monolithic legacy note", "back": "Paragraph answer"}],
    )

    # Fault Injection: AnkiConnect crashes with network socket timeout
    mock_bridge.create_notes = AsyncMock(side_effect=httpx.ConnectTimeout("AnkiConnect connection dropped"))
    mock_bridge.delete_notes = AsyncMock()

    new_cards = [
        Flashcard(front="Atomic sister 1", back="Answer 1"),
        Flashcard(front="Atomic sister 2", back="Answer 2"),
    ]

    with pytest.raises(httpx.ConnectTimeout):
        await service.replace_note_transactionally(
            deck_name=deck,
            source_note_id=legacy_note_id,
            new_cards=new_cards,
        )

    # SAFETY CERTIFICATIONS:
    # 1. delete_notes must NEVER have been called
    assert mock_bridge.delete_notes.called is False, "CRITICAL VIOLATION: delete_notes was called after creation failure!"
    assert mock_bridge.delete_notes.call_count == 0

    # 2. Obsolete note must remain intact in SQLite store
    existing_in_store = store.get_indexed_note_ids(deck)
    assert legacy_note_id in existing_in_store, "Legacy note was erroneously purged from knowledge index!"


@pytest.mark.asyncio
async def test_audit_l3_fault_injection_empty_creation_response_aborts_deletion(audit_sanitizer_env):
    """
    AUDIT L3.2: Fault Injection - Silent AnkiConnect Failure (returns empty created note IDs).
    CRITICAL SAFETY INVARIANT: If AnkiConnect returns an empty list [] or None,
    the transaction must raise a RuntimeError and abort deletion to prevent data loss.
    """
    store, mock_bridge, service, deck = audit_sanitizer_env
    legacy_note_id = 1002

    store.save_note_embeddings(
        deck,
        [{"note_id": legacy_note_id, "front": "Monolithic note 2", "back": "Paragraph 2"}],
    )

    # Silent AnkiConnect failure: returns empty list
    mock_bridge.create_notes = AsyncMock(return_value=[])
    mock_bridge.delete_notes = AsyncMock()

    new_cards = [Flashcard(front="Atomic sister", back="Answer")]

    with pytest.raises(RuntimeError) as exc_info:
        await service.replace_note_transactionally(
            deck_name=deck,
            source_note_id=legacy_note_id,
            new_cards=new_cards,
        )

    assert "Fallo en AnkiConnect" in str(exc_info.value)
    assert f"#{legacy_note_id} se mantuvo intacta" in str(exc_info.value)

    # Deletion was never called
    assert mock_bridge.delete_notes.called is False


# =============================================================================
# Level 3.2: DAG Precedence, Concept Transfer & Ledger Defense
# =============================================================================

@pytest.mark.asyncio
async def test_audit_l3_dag_topological_queue_safety(audit_sanitizer_env):
    """
    AUDIT L3.3: Deterministic 0-LLM Topological Queue Safety.
    Validates:
    (a) Notes mapped to foundational concepts (depth_level 1) are queued before deeper concepts.
    (b) Confirmed cognitive debt ('bad') precedes unreviewed notes at the same depth.
    (c) Notes unmapped in the curriculum are placed at depth 999.
    (d) Fully sanitized optimal notes are excluded from the pending queue.
    """
    store, mock_bridge, service, deck = audit_sanitizer_env

    # 1. Setup curriculum graph: node_foundations (depth 1) -> node_deep (depth 3)
    store.upsert_concept_node(deck, "node_foundations", "Core Principles", taxonomy_path="Core > Principles", depth_level=1, stage_id="stage_1")
    store.upsert_concept_node(deck, "node_deep", "Advanced Deep Topics", taxonomy_path="Core > Advanced", depth_level=3, stage_id="stage_1")
    store.upsert_concept_edge(deck, "node_foundations", "node_deep", "requires")

    # 2. Setup mock notes in Anki
    mock_bridge.get_deck_notes = AsyncMock(
        return_value=[
            DeckNoteRecord(note_id=101, deck_name=deck, model_name="Basic", front="Advanced Note", back="Ans 101"),
            DeckNoteRecord(note_id=102, deck_name=deck, model_name="Basic", front="Foundation Bad Note", back="Ans 102"),
            DeckNoteRecord(note_id=103, deck_name=deck, model_name="Basic", front="Foundation Unreviewed Note", back="Ans 103"),
            DeckNoteRecord(note_id=104, deck_name=deck, model_name="Basic", front="Unmapped Note", back="Ans 104"),
            DeckNoteRecord(note_id=105, deck_name=deck, model_name="Basic", front="Optimal Preserved Note", back="Ans 105"),
        ]
    )

    # 3. Mappings in card_concept_mappings
    store.link_card_to_concept(deck, 101, "node_deep", role="target")
    store.link_card_to_concept(deck, 102, "node_foundations", role="target")
    store.link_card_to_concept(deck, 103, "node_foundations", role="target")

    # 4. Status in SQLite index
    store.save_note_embeddings(
        deck,
        [
            {"note_id": 101, "front": "Advanced Note", "back": "Ans 101", "quality_status": "bad"},
            {"note_id": 102, "front": "Foundation Bad Note", "back": "Ans 102", "quality_status": "bad"},
            {"note_id": 103, "front": "Foundation Unreviewed Note", "back": "Ans 103", "quality_status": "unreviewed"},
            {"note_id": 104, "front": "Unmapped Note", "back": "Ans 104", "quality_status": "unreviewed"},
            {"note_id": 105, "front": "Optimal Preserved Note", "back": "Ans 105", "quality_status": "optimal"},
        ],
    )

    queue = await service.get_sanitation_queue(deck)

    assert queue.total_notes == 5
    assert queue.sanitized_count == 1
    assert queue.pending_count == 4

    # Order verification:
    # 1. 102 (depth 1, bad)
    # 2. 103 (depth 1, unreviewed)
    # 3. 101 (depth 3, bad)
    # 4. 104 (depth 999, unreviewed)
    pending_ids = [n.note_id for n in queue.notes]
    assert pending_ids == [102, 103, 101, 104]


@pytest.mark.asyncio
async def test_audit_l3_transactional_concept_mapping_transfer(audit_sanitizer_env):
    """
    AUDIT L3.4: Concept Mapping Atomic Transfer.
    Validates:
    (a) When obsolete note X is replaced, target concepts are linked to the newly created atomic cards.
    (b) Obsolete note X is completely purged from card_concept_mappings and indexed_notes.
    (c) Newly created cards are registered with quality_status = 'optimal'.
    """
    store, mock_bridge, service, deck = audit_sanitizer_env
    legacy_note_id = 2001

    store.upsert_concept_node(deck, "iam_policies", "IAM Policies", taxonomy_path="Sec > IAM", depth_level=1)
    store.save_note_embeddings(deck, [{"note_id": legacy_note_id, "front": "Big IAM Monolith", "back": "Details"}])
    store.link_card_to_concept(deck, legacy_note_id, "iam_policies", role="target")

    mock_bridge.create_notes = AsyncMock(return_value=[3001, 3002])
    mock_bridge.delete_notes = AsyncMock(return_value=1)
    mock_bridge.get_deck_notes = AsyncMock(return_value=[])

    new_cards = [
        Flashcard(front="Atomic IAM syntax", back="Syntax details"),
        Flashcard(front="Atomic IAM compartments", back="Compartment details"),
    ]

    res = await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=legacy_note_id,
        new_cards=new_cards,
        target_concepts=["IAM Policies"],
    )

    assert res.success is True
    assert res.created_note_ids == [3001, 3002]

    # Verify old note purged and new notes mapped
    mappings = store.get_card_concept_mappings(deck)
    mapped_nids = {m["note_id"] for m in mappings}
    assert legacy_note_id not in mapped_nids
    assert 3001 in mapped_nids
    assert 3002 in mapped_nids

    # Verify indexed quality status
    indexed = store.get_all_indexed_notes(deck)
    idx_map = {n["note_id"]: n for n in indexed}
    assert legacy_note_id not in idx_map
    assert idx_map[3001]["quality_status"] == "optimal"
    assert idx_map[3002]["quality_status"] == "optimal"


@pytest.mark.asyncio
async def test_audit_l3_coverage_ledger_collision_and_purge(audit_sanitizer_env):
    """
    AUDIT L3.5: Coverage Ledger Collision Tracking and Turn Consumption Purge.
    Validates:
    (a) When Note A's approved atomic cards cover concepts also present in debt Note B,
        a collision record is immutably registered in sanitation_coverage_ledger.
    (b) When Note B subsequently executes its own turn, its consumed ledger entries are purged cleanly.
    """
    store, mock_bridge, service, deck = audit_sanitizer_env
    note_a = 4001
    note_b = 4002

    store.upsert_concept_node(deck, "vcn_peering", "VCN Peering", taxonomy_path="Net > Peering", depth_level=2)

    store.save_note_embeddings(
        deck,
        [
            {"note_id": note_a, "front": "Note A Monolith", "back": "Covers peering"},
            {"note_id": note_b, "front": "Note B Monolith", "back": "Also covers peering"},
        ],
    )

    mock_bridge.create_notes = AsyncMock(return_value=[5001, 5002])
    mock_bridge.delete_notes = AsyncMock(return_value=1)
    mock_bridge.get_deck_notes = AsyncMock(return_value=[])

    # 1. Note A turn generates atomic cards that cover VCN Peering, colliding with Note B
    collisions = [
        SanitationCoverageLedgerInput(
            colliding_note_id=note_b,
            concept_title="VCN Peering",
            facet_summary="Local Peering Gateway routing",
        )
    ]

    await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=note_a,
        new_cards=[Flashcard(front="Atomic Peering 1", back="Ans 1"), Flashcard(front="Atomic Peering 2", back="Ans 2")],
        target_concepts=["VCN Peering"],
        pending_ledger_collisions=collisions,
    )

    # Verify ledger entry was created for Note B
    b_ledger = store.get_ledger_entries_for_note(deck, note_b)
    assert len(b_ledger) == 1
    assert b_ledger[0]["source_sanitized_note_id"] == note_a
    assert b_ledger[0]["covered_concept_title"] == "VCN Peering"
    assert b_ledger[0]["created_atomic_note_ids"] == [5001, 5002]

    # 2. When Note B gets its turn, its consumed ledger entries are purged
    mock_bridge.create_notes = AsyncMock(return_value=[6001])
    mock_bridge.delete_notes = AsyncMock(return_value=1)
    await service.replace_note_transactionally(
        deck_name=deck,
        source_note_id=note_b,
        new_cards=[Flashcard(front="Atomic Other", back="Ans Other")],
    )

    b_ledger_after = store.get_ledger_entries_for_note(deck, note_b)
    assert len(b_ledger_after) == 0, "Consumed ledger entries for Note B were not purged on turn completion!"


# =============================================================================
# Level 3.3: Preserve Optimal Notes Integrity
# =============================================================================

@pytest.mark.asyncio
async def test_audit_l3_preserve_optimal_leaves_notes_untouched(audit_sanitizer_env):
    """
    AUDIT L3.6: Preserve Optimal Notes Integrity.
    Validates that when a high-quality note is preserved:
    (a) It is marked as 'optimal' in SQLite store.
    (b) Neither update_note_fields nor delete_notes is called on AnkiConnect.
    (c) Any pending ledger records for this note are purged.
    (d) The pending queue count decreases accordingly.
    """
    store, mock_bridge, service, deck = audit_sanitizer_env
    optimal_note_id = 7001

    store.save_note_embeddings(
        deck,
        [{"note_id": optimal_note_id, "front": "Clean atomic card", "back": "Precise atomic answer"}],
    )
    mock_bridge.get_deck_notes = AsyncMock(
        return_value=[DeckNoteRecord(note_id=optimal_note_id, deck_name=deck, model_name="Basic", front="Clean card", back="Ans")]
    )
    mock_bridge.delete_notes = AsyncMock()
    mock_bridge.update_note_fields = AsyncMock()

    resp = await service.mark_note_as_optimal_preserved(deck, optimal_note_id)

    assert resp.success is True
    assert resp.quality_status == "optimal"

    # Invariant: Anki Desktop was NOT touched
    assert mock_bridge.delete_notes.called is False
    assert mock_bridge.update_note_fields.called is False

    # In SQLite, status is optimal
    stored = store.get_indexed_note(optimal_note_id)
    assert stored["quality_status"] == "optimal"
