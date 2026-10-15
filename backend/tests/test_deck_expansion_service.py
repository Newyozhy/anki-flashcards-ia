from unittest.mock import AsyncMock, MagicMock
import pytest
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import DeckNoteRecord, ExtractedNoteKnowledge, LearningPlanContract
from app.services.deck_dag_service import DeckDAGService
from app.services.deck_expansion_service import DeckExpansionService


@pytest.fixture
def expansion_setup(tmp_path):
    db_file = tmp_path / "test_expansion.db"
    store = DeckKnowledgeStore(db_path=str(db_file))
    dag_service = DeckDAGService(store=store)
    mock_bridge = MagicMock()
    service = DeckExpansionService(
        store=store,
        dag_service=dag_service,
        anki_bridge=mock_bridge,
    )
    deck = "Oracle Cloud"
    return store, dag_service, mock_bridge, service, deck


@pytest.mark.asyncio
async def test_expansion_queue_topological_ordering(expansion_setup):
    store, dag_service, mock_bridge, service, deck = expansion_setup

    # Mock Anki: 1 optimal note
    mock_bridge.get_deck_notes = AsyncMock(
        return_value=[
            DeckNoteRecord(
                note_id=101,
                deck_name=deck,
                model_name="Basic",
                front="What is VCN Peering?",
                back="Connecting two VCNs",
            )
        ]
    )
    store.save_note_embeddings(
        deck,
        [
            {
                "note_id": 101,
                "front": "What is VCN Peering?",
                "back": "Connecting two VCNs",
                "quality_status": "optimal",
            }
        ],
    )

    # Ingest extractions:
    # Note 101 teaches "OCI VCN Peering", but assumes prerequisites "OCI VCN" and "Networking Fundamentals"
    ext1 = ExtractedNoteKnowledge(
        source_note_id=101,
        raw_front="What is VCN Peering?",
        raw_back="Connecting two VCNs",
        extracted_facts=["VCN Peering connects two VCNs."],
        target_concepts=["OCI VCN Peering"],
        assumed_prerequisites=["OCI VCN"],
        taxonomy_path="oci::networking",
    )
    # Also another note or extraction: "OCI VCN" assumes "CIDR"
    ext2 = ExtractedNoteKnowledge(
        source_note_id=999,  # synthetic extraction
        raw_front="Dummy",
        raw_back="Dummy",
        extracted_facts=["VCN needs CIDR"],
        target_concepts=["OCI VCN"],
        assumed_prerequisites=["CIDR"],
        taxonomy_path="oci::networking",
    )
    dag_service.ingest_note_extractions(deck, [ext1, ext2])

    # Note 999 was synthetic, let's remove its mapping so OCI VCN and CIDR are orphans
    # (OCI VCN has 0 target notes, CIDR has 0 target notes)
    with store._get_connection() as conn:
        conn.cursor().execute("DELETE FROM card_concept_mappings WHERE note_id = 999")
        conn.commit()

    # Save approved contract
    contract = LearningPlanContract(
        deck_name=deck,
        version=1,
        status="approved",
        bloom_level="Application",
        exclusion_boundary=["FastConnect"],
        gap_strategy="fill_critical_only",
        operational_depth="Standard",
        raw_summary="Approved contract",
    )
    store.save_learning_contract(deck, contract.model_dump())

    res = await service.get_expansion_queue(deck)

    assert res.deck_name == deck
    assert res.contract_approved is True
    assert res.sanitation_completed is True
    assert res.pending_sanitation_count == 0
    assert res.total_orphans >= 2

    # CIDR -> OCI VCN -> OCI VCN Peering
    # In expansion_queue (which only includes orphans):
    # CIDR MUST come before OCI VCN!
    slugs = [item.concept_id for item in res.expansion_queue]
    assert "cidr" in slugs
    assert "oci_vcn" in slugs
    cidr_idx = slugs.index("cidr")
    vcn_idx = slugs.index("oci_vcn")
    assert cidr_idx < vcn_idx

    # Check dependents
    cidr_item = res.expansion_queue[cidr_idx]
    assert any("VCN" in d for d in cidr_item.dependents)


@pytest.mark.asyncio
async def test_link_cards_resolves_orphan_status(expansion_setup):
    store, dag_service, mock_bridge, service, deck = expansion_setup

    mock_bridge.get_deck_notes = AsyncMock(return_value=[])

    # Create an orphan concept
    store.upsert_concept_node(deck, "oci_iam", "OCI IAM")

    # Queue should have oci_iam as orphan
    q1 = await service.get_expansion_queue(deck)
    assert any(item.concept_id == "oci_iam" for item in q1.expansion_queue)
    assert q1.total_orphans == 1

    # Link new cards to oci_iam
    success = service.link_cards_to_concept(deck, "oci_iam", [701, 702])
    assert success is True

    # Queue should now have 0 orphans!
    q2 = await service.get_expansion_queue(deck)
    assert not any(item.concept_id == "oci_iam" for item in q2.expansion_queue)
    assert q2.total_orphans == 0
