from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from app.domain.models import Flashcard, AnkiStatus, ExportResult, DeckNoteRecord


class IAnkiBridgePort(ABC):
    """Port interface for interacting with Anki (AnkiConnect or .apkg builder)."""

    @abstractmethod
    async def check_status(self) -> AnkiStatus:
        """Check connection status and list available decks."""
        pass

    @abstractmethod
    async def get_deck_names(self) -> List[str]:
        """Fetch list of all existing deck names in Anki."""
        pass

    @abstractmethod
    async def export_cards(self, deck_name: str, cards: List[Flashcard]) -> ExportResult:
        """Export flashcards to the target deck."""
        pass

    async def create_notes(self, deck_name: str, cards: List[Flashcard]) -> List[int]:
        """Create new notes in Anki and return their generated note IDs."""
        res = await self.export_cards(deck_name, cards)
        return res.created_note_ids or []

    @abstractmethod
    async def get_deck_notes(self, deck_name: str) -> List[DeckNoteRecord]:
        """Fetch and normalize all notes within an existing Anki deck."""
        pass

    @abstractmethod
    async def retrieve_media_base64(self, filename: str) -> Optional[str]:
        """Retrieve base64 image data from Anki collection.media."""
        pass

    @abstractmethod
    async def update_note_fields(self, note_id: int, fields: Dict[str, str]) -> bool:
        """Update specific fields of an existing note in-place, preserving FSRS review history."""
        pass

    @abstractmethod
    async def delete_notes(self, note_ids: List[int]) -> bool:
        """Remove obsolete notes from Anki."""
        pass

    async def reposition_cards(
        self,
        card_ids: List[int],
        starting_from: int = 0,
        step: int = 1,
        shift: bool = True,
    ) -> bool:
        """Reposition cards in Anki new queue according to topological curriculum order."""
        return True

    async def get_cards_info(self, card_ids: List[int]) -> List[Dict[str, Any]]:
        """Retrieve detailed card metadata (due, queue, type) from Anki."""
        return []

    async def get_note_cards(self, note_ids: List[int]) -> List[int]:
        """Fetch all physical card IDs belonging to the given note IDs."""
        return []

    async def get_note_by_id(self, note_id: int) -> Optional[DeckNoteRecord]:
        """Fetch a single note by note_id and normalize to DeckNoteRecord."""
        return None



