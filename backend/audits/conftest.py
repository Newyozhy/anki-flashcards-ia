import json
from pathlib import Path
from typing import Any, Dict, List
import pytest

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.services.deck_dag_service import DeckDAGService


@pytest.fixture
def tmp_audit_db(tmp_path) -> DeckKnowledgeStore:
    """Provides a fresh isolated SQLite store for each audit test run."""
    db_file = tmp_path / "audit_knowledge.db"
    return DeckKnowledgeStore(db_path=str(db_file))


@pytest.fixture
def audit_dag_service(tmp_audit_db) -> DeckDAGService:
    """Provides a DeckDAGService bound to the isolated audit store."""
    return DeckDAGService(store=tmp_audit_db)


@pytest.fixture
def sample_audit_cards() -> List[Dict[str, Any]]:
    """Loads realistic audit cards from root audit_cards.json if present."""
    root_path = Path(__file__).resolve().parent.parent.parent
    audit_file = root_path / "audit_cards.json"
    if audit_file.exists():
        with open(audit_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return []
