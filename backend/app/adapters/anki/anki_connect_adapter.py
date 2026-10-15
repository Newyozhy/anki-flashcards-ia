import logging
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.core.formatting import (
    ANKICRAFT_BASIC_MODEL_NAME,
    ANKICRAFT_CLOZE_MODEL_NAME,
    BASIC_MODEL_FIELDS,
    CLOZE_MODEL_FIELDS,
    BASIC_CARD_FRONT,
    BASIC_CARD_BACK,
    CLOZE_CARD_FRONT,
    CLOZE_CARD_BACK,
    ANKICRAFT_CARD_CSS,
    format_anki_field,
    extract_breadcrumb_and_body,
)
from app.core.cloze_sanitizer import ClozeSanitizer
import re
from app.domain.models import Flashcard, CardType, AnkiStatus, ExportResult, DeckNoteRecord
from app.ports.anki_bridge_port import IAnkiBridgePort

logger = logging.getLogger(__name__)


class AnkiConnectAdapter(IAnkiBridgePort):
    """Adapter for AnkiConnect plugin (JSON-RPC over HTTP on localhost:8765)."""

    def __init__(self, base_url: Optional[str] = None):
        self._base_url = base_url or settings.ANKI_CONNECT_URL
        self._timeout = settings.ANKI_CONNECT_TIMEOUT_SECONDS

    async def _invoke(self, action: str, **params) -> Any:
        """Send JSON-RPC request to AnkiConnect."""
        payload = {
            "action": action,
            "version": 6,
            "params": params,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._base_url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError:
            raise ConnectionError(
                "Cannot connect to AnkiConnect. Ensure Anki Desktop is running and AnkiConnect add-on is installed."
            )
        except Exception as e:
            raise RuntimeError(f"AnkiConnect request failed: {str(e)}")

        if data.get("error"):
            raise RuntimeError(f"AnkiConnect error on action '{action}': {data['error']}")

        return data.get("result")

    async def check_status(self) -> AnkiStatus:
        """Check whether Anki Desktop is running with AnkiConnect enabled."""
        try:
            version = await self._invoke("version")
            decks = await self._invoke("deckNames")
            return AnkiStatus(
                is_connected=True,
                version=f"v{version}",
                available_decks=decks or [],
            )
        except Exception as e:
            return AnkiStatus(
                is_connected=False,
                error_message=str(e),
                available_decks=[],
            )

    async def get_deck_names(self) -> List[str]:
        """Retrieve list of all decks in local Anki."""
        status = await self.check_status()
        return status.available_decks if status.is_connected else []

    async def create_deck_if_not_exists(self, deck_name: str) -> None:
        """Ensure the target deck exists, creating it if needed."""
        await self._invoke("createDeck", deck=deck_name)

    async def _ensure_models_exist(self) -> None:
        """Ensure custom ergonomic AnkiCraft Pro note types are registered in Anki."""
        try:
            existing_models = set(await self._invoke("modelNames"))
            if ANKICRAFT_BASIC_MODEL_NAME not in existing_models:
                logger.info("Creating custom note type '%s' in Anki Desktop", ANKICRAFT_BASIC_MODEL_NAME)
                await self._invoke(
                    "createModel",
                    modelName=ANKICRAFT_BASIC_MODEL_NAME,
                    inOrderFields=BASIC_MODEL_FIELDS,
                    css=ANKICRAFT_CARD_CSS,
                    cardTemplates=[{
                        "Name": "Card 1",
                        "Front": BASIC_CARD_FRONT,
                        "Back": BASIC_CARD_BACK,
                    }],
                )

            if ANKICRAFT_CLOZE_MODEL_NAME not in existing_models:
                logger.info("Creating custom note type '%s' in Anki Desktop", ANKICRAFT_CLOZE_MODEL_NAME)
                await self._invoke(
                    "createModel",
                    modelName=ANKICRAFT_CLOZE_MODEL_NAME,
                    inOrderFields=CLOZE_MODEL_FIELDS,
                    css=ANKICRAFT_CARD_CSS,
                    isCloze=True,
                    cardTemplates=[{
                        "Name": "Cloze",
                        "Front": CLOZE_CARD_FRONT,
                        "Back": CLOZE_CARD_BACK,
                    }],
                )
        except Exception as err:
            logger.warning("Could not verify/create AnkiCraft models: %s", err)

    async def export_cards(self, deck_name: str, cards: List[Flashcard]) -> ExportResult:
        """Batch export cards into the designated Anki deck."""
        try:
            # 1. Ensure deck exists
            await self.create_deck_if_not_exists(deck_name)

            # 2. Ensure custom ergonomic models exist
            await self._ensure_models_exist()

            # 3. Format notes
            notes: List[Dict[str, Any]] = []
            for card in cards:
                note_payload = self._build_note_payload(deck_name, card)
                notes.append(note_payload)

            # 4. Invoke addNotes
            results = await self._invoke("addNotes", notes=notes)

            # AnkiConnect returns an array of note IDs or null for duplicates/failures
            successful_count = sum(1 for item in results if item is not None)
            created_ids = [int(item) for item in results if item is not None]

            return ExportResult(
                success=True,
                cards_exported_count=successful_count,
                destination="anki_connect",
                message=f"Successfully imported {successful_count}/{len(cards)} cards directly into Anki deck '{deck_name}'.",
                created_note_ids=created_ids,
            )
        except Exception as e:
            logger.error("Failed to export cards to AnkiConnect: %s", e)
            return ExportResult(
                success=False,
                cards_exported_count=0,
                destination="anki_connect",
                message=f"Export failed: {str(e)}",
            )

    async def create_notes(self, deck_name: str, cards: List[Flashcard]) -> List[int]:
        """Create new flashcards in Anki and return their generated note IDs."""
        result = await self.export_cards(deck_name, cards)
        if not result.success:
            logger.error("Failed to create notes via AnkiConnect: %s", result.message)
            return []
        return result.created_note_ids or []

    def _build_note_payload(self, deck_name: str, card: Flashcard) -> Dict[str, Any]:
        """Construct AnkiConnect note schema based on card type with HTML formatting."""
        card = ClozeSanitizer.sanitize_card(card)
        breadcrumb, body = extract_breadcrumb_and_body(card.front)
        formatted_breadcrumb = breadcrumb
        formatted_body = format_anki_field(body)
        formatted_back = format_anki_field(card.back or "")
        formatted_extra = format_anki_field(card.explanation or "")

        if card.card_type == CardType.CLOZE:
            return {
                "deckName": deck_name,
                "modelName": ANKICRAFT_CLOZE_MODEL_NAME,
                "fields": {
                    "Breadcrumb": formatted_breadcrumb,
                    "Text": formatted_body,
                    "Back Extra": formatted_back,
                    "Extra": formatted_extra,
                },
                "tags": card.tags,
                "options": {
                    "allowDuplicate": True,
                    "duplicateScope": "deck",
                },
            }
        else:
            # Defensive gate: If basic card, ensure no raw cloze markers exist in Front or Back
            if "{{c" in formatted_body:
                formatted_body = ClozeSanitizer.unwrap_clozes(formatted_body)
            if "{{c" in formatted_back:
                formatted_back = ClozeSanitizer.unwrap_clozes(formatted_back)

            return {
                "deckName": deck_name,
                "modelName": ANKICRAFT_BASIC_MODEL_NAME,
                "fields": {
                    "Breadcrumb": formatted_breadcrumb,
                    "Front": formatted_body,
                    "Back": formatted_back,
                    "Extra": formatted_extra,
                },
                "tags": card.tags,
                "options": {
                    "allowDuplicate": True,
                    "duplicateScope": "deck",
                },
            }

    async def get_deck_notes(self, deck_name: str) -> List[DeckNoteRecord]:
        """Fetch all notes from Anki for a given deck in batches of 100, tolerantly normalizing fields and cleaning HTML."""
        try:
            note_ids = await self._invoke("findNotes", query=f'deck:"{deck_name}"')
            if not note_ids:
                return []

            notes_info: List[Dict[str, Any]] = []
            batch_size = 100
            for i in range(0, len(note_ids), batch_size):
                batch = note_ids[i : i + batch_size]
                batch_res = await self._invoke("notesInfo", notes=batch)
                if batch_res:
                    notes_info.extend(batch_res)

            normalized_records: List[DeckNoteRecord] = []
            for n in notes_info:
                normalized_records.append(self._normalize_single_note(n, deck_name))
            return normalized_records
        except Exception as e:
            logger.warning("Failed to fetch deck notes from AnkiConnect for deck '%s': %s", deck_name, e)
            return []

    def _normalize_single_note(self, n: Dict[str, Any], deck_name: str) -> DeckNoteRecord:
        def _clean_html(text: str) -> str:
            if not text:
                return ""
            cleaned = re.sub(r"<[^>]+>", " ", text)
            cleaned = (
                cleaned.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
            )
            return " ".join(cleaned.split()).strip()

        nid = n["noteId"]
        m_name = n.get("modelName", "")
        tags = n.get("tags", [])
        raw_fields = {k: v.get("value", "") for k, v in n.get("fields", {}).items()}

        all_text = " ".join(raw_fields.values())
        media_files = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', all_text)

        if m_name == "Gramatica":
            front = f"{raw_fields.get('Titulo', '')}\n\n{raw_fields.get('preguntas', '')}".strip()
            back = raw_fields.get("respuestas", "")
            explanation = raw_fields.get("imagen", "")
        elif m_name == "Input":
            front = raw_fields.get("Front", "")
            back = raw_fields.get("Explanation", "")
            sentence_ctx = raw_fields.get("Sentence", "")
            trans_ctx = raw_fields.get("Translation", "")
            explanation = f"Sentence: {sentence_ctx}\nTranslation: {trans_ctx}".strip()
        elif m_name == "Output":
            front = raw_fields.get("Front", "")
            back = raw_fields.get("Back", "")
            tip_ctx = raw_fields.get("Tip", "")
            extra_ctx = raw_fields.get("Extra", "")
            explanation = f"{tip_ctx}\n\n{extra_ctx}".strip()
        elif m_name == "JP":
            front = raw_fields.get("Expression", "")
            pron_ctx = raw_fields.get("Pronunciation", "")
            mean_ctx = raw_fields.get("Meaning", "")
            back = f"Pronunciation: {pron_ctx}\nMeaning: {mean_ctx}".strip()
            explanation = mean_ctx
        elif "Text" in raw_fields:
            front = raw_fields.get("Text", "")
            back = raw_fields.get("Back Extra", "")
            explanation = raw_fields.get("Extra", "")
        else:
            field_vals = list(raw_fields.values())
            front = raw_fields.get("Front", "") or (field_vals[0] if field_vals else "")
            back = raw_fields.get("Back", "") or (field_vals[1] if len(field_vals) > 1 else "")
            explanation = raw_fields.get("Extra", "") or raw_fields.get("Tip", "")

        card_type = (
            CardType.CLOZE
            if "{{c" in front or "cloze" in m_name.lower()
            else CardType.BASIC
        )

        clean_front = _clean_html(front)
        clean_back = _clean_html(back)
        clean_exp = _clean_html(explanation)
        clean_text = f"{clean_front} | {clean_back}".strip()

        return DeckNoteRecord(
            note_id=nid,
            deck_name=deck_name,
            model_name=m_name,
            card_type=card_type,
            front=front,
            back=back,
            explanation=explanation if explanation else None,
            clean_text=clean_text,
            clean_front=clean_front,
            clean_back=clean_back,
            clean_explanation=clean_exp,
            tags=tags,
            raw_fields=raw_fields,
            media_files=media_files,
            card_ids=n.get("cards") or [],
        )

    async def get_note_by_id(self, note_id: int) -> Optional[DeckNoteRecord]:
        """Fetch a single note by note_id and normalize to DeckNoteRecord."""
        try:
            res = await self._invoke("notesInfo", notes=[note_id])
            if not res or len(res) == 0:
                return None
            n = res[0]
            deck_name = n.get("deckName", "")
            if not deck_name and n.get("cards"):
                try:
                    card_infos = await self._invoke("cardsInfo", cards=[n["cards"][0]])
                    if card_infos and len(card_infos) > 0:
                        deck_name = card_infos[0].get("deckName", "")
                except Exception:
                    pass
            return self._normalize_single_note(n, deck_name)
        except Exception as e:
            logger.warning("Failed to fetch note %d from AnkiConnect: %s", note_id, e)
            return None

    async def retrieve_media_base64(self, filename: str) -> Optional[str]:
        """Fetch base64 image data from Anki Desktop collection.media."""
        try:
            res = await self._invoke("retrieveMediaFile", filename=filename)
            if res and isinstance(res, str):
                return res
            return None
        except Exception as e:
            logger.warning("Could not retrieve media file '%s' from Anki: %s", filename, e)
            return None

    async def update_note_fields(self, note_id: int, fields: Dict[str, str]) -> bool:
        """Update existing note fields in Anki without resetting FSRS intervals."""
        try:
            await self._invoke("updateNoteFields", note={"id": note_id, "fields": fields})
            return True
        except Exception as e:
            logger.error("Failed to update note fields in Anki for note %d: %s", note_id, e)
            return False

    async def delete_notes(self, note_ids: List[int]) -> bool:
        """Delete specific notes by ID from Anki."""
        try:
            await self._invoke("deleteNotes", notes=note_ids)
            return True
        except Exception as e:
            logger.error("Failed to delete notes in Anki: %s", e)
            return False

    async def reposition_cards(
        self,
        card_ids: List[int],
        starting_from: int = 0,
        step: int = 1,
        shift: bool = True,
    ) -> bool:
        """Reposition cards in Anki's new queue with optional shifting of existing cards."""
        if not card_ids:
            return True
        try:
            await self._invoke(
                "reposition",
                cards=card_ids,
                startingFrom=starting_from,
                step=step,
                random=False,
                shift=shift,
            )
            return True
        except Exception as e:
            logger.error("Failed to reposition cards in Anki: %s", e)
            return False

    async def get_cards_info(self, card_ids: List[int]) -> List[Dict[str, Any]]:
        """Fetch detailed card metadata (due, queue, reps, lapses) from AnkiConnect."""
        if not card_ids:
            return []
        try:
            res = await self._invoke("cardsInfo", cards=card_ids)
            return res if isinstance(res, list) else []
        except Exception as e:
            logger.warning("Failed to fetch cardsInfo from AnkiConnect: %s", e)
            return []

    async def get_note_cards(self, note_ids: List[int]) -> List[int]:
        """Fetch all physical card IDs belonging to the given note IDs."""
        if not note_ids:
            return []
        try:
            notes_info = await self._invoke("notesInfo", notes=note_ids)
            card_ids: List[int] = []
            for n in notes_info or []:
                card_ids.extend(n.get("cards") or [])
            return card_ids
        except Exception as e:
            logger.warning("Failed to fetch card IDs for notes %s: %s", note_ids, e)
            return []



