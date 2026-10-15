import logging
from typing import List, Optional
from app.domain.models import Flashcard, ExportResult, AnkiStatus
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.core.cloze_sanitizer import ClozeSanitizer
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore

logger = logging.getLogger(__name__)


class ExportDeckUseCase:
    """Use case to orchestrate exporting cards either directly to AnkiConnect or to .apkg."""

    def __init__(
        self,
        anki_connect_bridge: IAnkiBridgePort,
        apkg_bridge: IAnkiBridgePort,
        sanitizer: Optional[ClozeSanitizer] = None,
        store: Optional[DeckKnowledgeStore] = None,
    ):
        self._anki_connect = anki_connect_bridge
        self._apkg_bridge = apkg_bridge
        self._sanitizer = sanitizer or ClozeSanitizer()
        self._store = store

    async def get_anki_status(self) -> AnkiStatus:
        """Check live connection to AnkiConnect and get existing decks."""
        return await self._anki_connect.check_status()

    async def export_to_anki(
        self,
        deck_name: str,
        cards: List[Flashcard],
    ) -> ExportResult:
        """Direct export into running Anki Desktop via AnkiConnect for newly created cards."""
        if not cards:
            return ExportResult(
                success=False,
                cards_exported_count=0,
                destination="anki_connect",
                message="No cards provided to export.",
            )
        status = await self._anki_connect.check_status()
        if not status.is_connected:
            return ExportResult(
                success=False,
                cards_exported_count=0,
                destination="anki_connect",
                message=f"Anki Desktop is not running or AnkiConnect is unreachable ({status.error_message}).",
            )
        # Defense-in-depth: Sanitize every card before pushing to Anki compiler
        sanitized_cards = [self._sanitizer.sanitize_card(c) for c in cards]
        res = await self._anki_connect.export_cards(deck_name, sanitized_cards)

        if res.success and self._store and res.created_note_ids:
            try:
                self._store.mark_notes_optimal(deck_name, res.created_note_ids)
            except Exception as store_err:
                logger.warning("Failed to mark newly exported notes as optimal in store: %s", store_err)

        return res

    async def export_to_apkg(
        self, deck_name: str, cards: List[Flashcard]
    ) -> ExportResult:
        """Export cards as a standalone downloadable .apkg file."""
        if not cards:
            return ExportResult(
                success=False,
                cards_exported_count=0,
                destination="apkg",
                message="No cards provided to generate .apkg package.",
            )
        # Defense-in-depth: Sanitize every card before packaging
        sanitized_cards = [self._sanitizer.sanitize_card(c) for c in cards]
        return await self._apkg_bridge.export_cards(deck_name, sanitized_cards)
