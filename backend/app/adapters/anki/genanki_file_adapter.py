import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, List, Optional
import genanki

from app.core.formatting import (
    ANKICRAFT_BASIC_MODEL_NAME,
    ANKICRAFT_CLOZE_MODEL_NAME,
    BASIC_CARD_FRONT,
    BASIC_CARD_BACK,
    CLOZE_CARD_FRONT,
    CLOZE_CARD_BACK,
    ANKICRAFT_CARD_CSS,
    format_anki_field,
    extract_breadcrumb_and_body,
)
from app.core.cloze_sanitizer import ClozeSanitizer
from app.domain.models import Flashcard, CardType, AnkiStatus, ExportResult
from app.ports.anki_bridge_port import IAnkiBridgePort


# Deterministic IDs for Genanki Models
BASIC_MODEL_ID = 1607392319
CLOZE_MODEL_ID = 1607392320

BASIC_MODEL = genanki.Model(
    BASIC_MODEL_ID,
    ANKICRAFT_BASIC_MODEL_NAME,
    fields=[
        {"name": "Breadcrumb"},
        {"name": "Front"},
        {"name": "Back"},
        {"name": "Extra"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": BASIC_CARD_FRONT,
            "afmt": BASIC_CARD_BACK,
        },
    ],
    css=ANKICRAFT_CARD_CSS,
)

CLOZE_MODEL = genanki.Model(
    CLOZE_MODEL_ID,
    ANKICRAFT_CLOZE_MODEL_NAME,
    model_type=genanki.Model.CLOZE,
    fields=[
        {"name": "Breadcrumb"},
        {"name": "Text"},
        {"name": "Back Extra"},
        {"name": "Extra"},
    ],
    templates=[
        {
            "name": "Cloze Card",
            "qfmt": CLOZE_CARD_FRONT,
            "afmt": CLOZE_CARD_BACK,
        },
    ],
    css=ANKICRAFT_CARD_CSS,
)


class GenankiFileAdapter(IAnkiBridgePort):
    """Adapter for generating standalone .apkg package files via genanki."""

    def __init__(self, export_dir: str = "exports"):
        self._export_dir = Path(export_dir)
        self._export_dir.mkdir(parents=True, exist_ok=True)

    def _generate_deck_id(self, deck_name: str) -> int:
        """Create a stable, positive 31-bit integer ID from the deck name."""
        hash_digest = hashlib.sha256(deck_name.encode("utf-8")).hexdigest()
        return int(hash_digest[:8], 16) & 0x7FFFFFFF

    async def check_status(self) -> AnkiStatus:
        """File adapter is always available offline."""
        return AnkiStatus(
            is_connected=True,
            version="genanki-0.13.1",
            available_decks=[],
        )

    async def get_deck_names(self) -> List[str]:
        return []

    async def export_cards(self, deck_name: str, cards: List[Flashcard]) -> ExportResult:
        """Package flashcards into an .apkg file on disk."""
        try:
            deck_id = self._generate_deck_id(deck_name)
            deck = genanki.Deck(deck_id, deck_name)

            for card in cards:
                card = ClozeSanitizer.sanitize_card(card)
                breadcrumb, body = extract_breadcrumb_and_body(card.front)
                formatted_breadcrumb = breadcrumb
                formatted_body = format_anki_field(body)
                formatted_back = format_anki_field(card.back or "")
                formatted_extra = format_anki_field(card.explanation or "")

                clean_tags = [
                    t.replace(" ", "_").strip()
                    for t in (card.tags or [])
                    if t and t.replace(" ", "_").strip()
                ]

                if card.card_type == CardType.CLOZE:
                    note = genanki.Note(
                        model=CLOZE_MODEL,
                        fields=[
                            formatted_breadcrumb,
                            formatted_body,
                            formatted_back,
                            formatted_extra,
                        ],
                        tags=clean_tags,
                    )
                else:
                    if "{{c" in formatted_body:
                        formatted_body = ClozeSanitizer.unwrap_clozes(formatted_body)
                    if "{{c" in formatted_back:
                        formatted_back = ClozeSanitizer.unwrap_clozes(formatted_back)

                    note = genanki.Note(
                        model=BASIC_MODEL,
                        fields=[
                            formatted_breadcrumb,
                            formatted_body,
                            formatted_back,
                            formatted_extra,
                        ],
                        tags=clean_tags,
                    )
                deck.add_note(note)

            # Generate filename
            safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in deck_name)
            filename = f"{safe_name}.apkg"
            output_path = self._export_dir / filename

            package = genanki.Package(deck)
            package.write_to_file(str(output_path))

            return ExportResult(
                success=True,
                cards_exported_count=len(cards),
                destination="apkg",
                message=f"Generated '{filename}' with {len(cards)} cards.",
                apkg_file_path=str(output_path),
            )
        except Exception as e:
            return ExportResult(
                success=False,
                cards_exported_count=0,
                destination="apkg",
                message=f"Failed to create .apkg: {str(e)}",
            )

    async def create_notes(self, deck_name: str, cards: List[Flashcard]) -> List[int]:
        res = await self.export_cards(deck_name, cards)
        return res.created_note_ids or []

    async def get_deck_notes(self, deck_name: str) -> List[Any]:
        return []

    async def retrieve_media_base64(self, filename: str) -> Optional[str]:
        return None

    async def update_note_fields(self, note_id: int, fields: Any) -> bool:
        return False

    async def delete_notes(self, note_ids: List[int]) -> bool:
        return False

    async def reposition_cards(
        self,
        card_ids: List[int],
        starting_from: int = 0,
        step: int = 1,
        shift: bool = True,
    ) -> bool:
        return True

    async def get_cards_info(self, card_ids: List[int]) -> List[Any]:
        return []

    async def get_note_cards(self, note_ids: List[int]) -> List[int]:
        return []



