import tempfile
from pathlib import Path
from typing import List, Optional
import pytest

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.domain.models import (
    CoreTheme,
    PrerequisiteItem,
    PrerequisiteMatchStatus,
)
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.ports.embedding_port import IEmbeddingPort
from app.services.deck_intelligence_service import DeckIntelligenceService


class MockAnkiBridge(IAnkiBridgePort):
    def __init__(self, notes: List[dict]):
        self.notes = notes
        self.updated_fields = {}

    async def check_status(self):
        return None

    async def get_deck_names(self):
        return ["Medicina::Farmacología"]

    async def export_cards(self, deck_name: str, cards):
        return None

    async def get_deck_notes(self, deck_name: str) -> List[dict]:
        return self.notes

    async def get_notes_info(self, note_ids: List[int]) -> List[dict]:
        infos = []
        for nid in note_ids:
            found = next(
                (n for n in self.notes if (n.get("note_id") if isinstance(n, dict) else n.note_id) == nid),
                None
            )
            if found:
                if isinstance(found, dict):
                    front = found.get("front", "")
                    back = found.get("back", "")
                    exp = found.get("explanation", "")
                    model = found.get("model_name", "Basic")
                    deck = found.get("deck_name", "General")
                    raw = found.get("raw_fields")
                else:
                    front = found.front
                    back = found.back
                    exp = found.explanation or ""
                    model = getattr(found, "model_name", "Basic")
                    deck = found.deck_name
                    raw = getattr(found, "raw_fields", None)

                if raw:
                    fields_dict = {k: {"value": v, "order": idx} for idx, (k, v) in enumerate(raw.items())}
                elif model == "AnkiCraft Pro (Basic)":
                    fields_dict = {
                        "Breadcrumb": {"value": "", "order": 0},
                        "Front": {"value": front, "order": 1},
                        "Back": {"value": back, "order": 2},
                        "Extra": {"value": exp, "order": 3},
                    }
                else:
                    fields_dict = {
                        "Front": {"value": front, "order": 0},
                        "Back": {"value": back, "order": 1},
                    }

                infos.append({
                    "noteId": nid,
                    "modelName": model,
                    "deckName": deck,
                    "fields": fields_dict,
                })
        return infos

    async def retrieve_media_base64(self, filename: str):
        return None

    async def update_note_fields(self, note_id: int, fields):
        self.updated_fields[note_id] = fields
        return True

    async def delete_notes(self, note_ids):
        return True


class MockEmbeddingPort(IEmbeddingPort):
    def __init__(self, vector_map: Optional[dict] = None):
        self.vector_map = vector_map or {}
        self.default_vector = [1.0, 0.0, 0.0]

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        results = []
        for t in texts:
            matched = False
            for k, vec in self.vector_map.items():
                if k.lower() in t.lower():
                    results.append(vec)
                    matched = True
                    break
            if not matched:
                results.append(self.default_vector)
        return results

    async def embed_single(self, text: str) -> List[float]:
        res = await self.embed_texts([text])
        return res[0]


@pytest.mark.asyncio
async def test_deck_intelligence_sync_and_prerequisite_matching():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_deck_intel.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        # Sample Notes:
        # Note 1: Atomic, has trap, concise back -> Will test DOMINATED
        # Note 2: Cognitive debt, >25 words, no trap -> Will test COGNITIVE_DEBT
        mock_notes = [
            {
                "note_id": 201,
                "deck_name": "Farmacología",
                "front": "[Farmaco > Bloqueadores] ¿Cuál es el mecanismo del propanolol?",
                "back": "Antagonista competitivo no selectivo de los receptores beta-1 y beta-2 adrenérgicos.",
                "explanation": "⚠️ Trampa frecuente / Error común: no usar en pacientes asmáticos por broncoconstricción.",
                "tags": ["beta-bloqueantes", "cardio"],
            },
            {
                "note_id": 202,
                "deck_name": "Farmacología",
                "front": "¿Qué es la farmacocinética del paracetamol?",
                "back": (
                    "Se absorbe de manera rápida y casi completa en el tubo digestivo, alcanzando concentraciones "
                    "plasmáticas máximas en 30 a 60 minutos, con una biodisponibilidad que oscila entre el 60 y 70 por ciento "
                    "debido al metabolismo de primer paso hepático mediado principalmente por glucuronidación y sulfatación "
                    "generando una fracción tóxica menor de NAPQI que se neutraliza con glutatión."
                ),
                "explanation": "Ver tabla de toxicidad en Harrison.",
                "tags": ["analgésicos"],
            },
        ]

        # Vectors:
        # Note 201: [1.0, 0.0, 0.0] (Propanolol)
        # Note 202: [0.0, 1.0, 0.0] (Paracetamol)
        # Gap concept: [0.0, 0.0, 1.0] (Antibióticos)
        vector_map = {
            "propanolol": [1.0, 0.0, 0.0],
            "paracetamol": [0.0, 1.0, 0.0],
            "amoxicilina": [0.0, 0.0, 1.0],
        }

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort(vector_map)

        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        deck_name = "Medicina::Farmacología"

        # 1. Sync Index
        sync_res1 = await service.sync_deck_index(deck_name)
        assert sync_res1.total_notes == 2
        assert sync_res1.newly_indexed == 2

        # Second sync should index 0 new notes
        sync_res2 = await service.sync_deck_index(deck_name)
        assert sync_res2.total_notes == 2
        assert sync_res2.newly_indexed == 0

        # 2. Prerequisite Matching
        prereqs = [
            PrerequisiteItem(
                concept="Propanolol y receptores adrenérgicos",
                reason="Base para entender antiarrítmicos",
                search_query="propanolol mecanismo beta",
            ),
            PrerequisiteItem(
                concept="Metabolismo de Paracetamol y NAPQI",
                reason="Base para toxicología hepática",
                search_query="paracetamol farmacocinética",
            ),
            PrerequisiteItem(
                concept="Mecanismo de acción de Amoxicilina",
                reason="Inhibición de pared bacteriana",
                search_query="amoxicilina betalactamico",
            ),
        ]

        match_res = await service.match_prerequisites(deck_name, prereqs)
        assert match_res.total_indexed_notes == 2
        assert len(match_res.matches) == 3

        # Match 1: Propanolol -> Dominado (alta calidad, con trampa)
        m1 = match_res.matches[0]
        assert m1.concept == "Propanolol y receptores adrenérgicos"
        assert m1.status == PrerequisiteMatchStatus.DOMINATED
        assert m1.matched_note_id == 201
        assert m1.suggested_action == "keep_existing"

        # Match 2: Paracetamol -> Deuda Cognitiva (respuesta larga, sin trampa)
        m2 = match_res.matches[1]
        assert m2.concept == "Metabolismo de Paracetamol y NAPQI"
        assert m2.status == PrerequisiteMatchStatus.COGNITIVE_DEBT
        assert m2.matched_note_id == 202
        assert m2.suggested_action in ("create_new", "refactor_existing")

        # Match 3: Amoxicilina -> Gap (orthogonal vector [0, 0, 1], similarity 0.0)
        m3 = match_res.matches[2]
        assert m3.concept == "Mecanismo de acción de Amoxicilina"
        assert m3.status == PrerequisiteMatchStatus.GAP
        assert m3.matched_note_id is None
        assert m3.suggested_action == "create_new"


@pytest.mark.asyncio
async def test_deck_intelligence_sync_with_deck_note_records():
    """Verify that sync_deck_index seamlessly handles DeckNoteRecord model objects without item assignment errors."""
    from app.domain.models import DeckNoteRecord, CardType

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_records.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        record_notes = [
            DeckNoteRecord(
                note_id=501,
                deck_name="Oracle Cloud",
                model_name="AnkiCraft Basic",
                card_type=CardType.BASIC,
                front="¿Qué es OCI IAM?",
                back="Servicio de gestión de identidades y accesos.",
                explanation="⚠️ Trampa frecuente: las políticas se heredan por compartimentos.",
                tags=["oci", "iam"],
            ),
            DeckNoteRecord(
                note_id=502,
                deck_name="Oracle Cloud",
                model_name="AnkiCraft Basic",
                card_type=CardType.BASIC,
                front="¿Qué es VCN en OCI?",
                back="Red virtual en la nube definida por software.",
                explanation="⚠️ Trampa frecuente: requiere subredes para desplegar cómputo.",
                tags=["oci", "redes"],
            ),
        ]

        anki_bridge = MockAnkiBridge(record_notes)
        embedding_port = MockEmbeddingPort()
        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        res = await service.sync_deck_index("Oracle Cloud")
        assert res.total_notes == 2
        assert res.newly_indexed == 2
        assert store.get_indexed_note_ids("Oracle Cloud") == {501, 502}


@pytest.mark.asyncio
async def test_deck_intelligence_theme_matching():
    """Verify that match_themes correctly audits core themes against indexed notes."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_themes.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        mock_notes = [
            {
                "note_id": 301,
                "deck_name": "Medicina::Farmacología",
                "front": "¿Cuál es el mecanismo del propanolol?",
                "back": "Antagonista competitivo no selectivo de receptores beta adrenérgicos.",
                "explanation": "⚠️ Trampa frecuente: no usar en asma.",
                "tags": ["beta-bloqueantes"],
            },
            {
                "note_id": 302,
                "deck_name": "Medicina::Farmacología",
                "front": "¿Farmacocinética del paracetamol?",
                "back": (
                    "Se absorbe rápidamente y alcanza concentraciones plasmáticas máximas en 30 minutos "
                    "sufriendo metabolismo de primer paso con conjugación con ácido glucurónico y sulfato "
                    "produciendo el metabolito reactivo NAPQI el cual es detoxificado por el glutatión celular."
                ),
                "explanation": "Toxicidad hepática.",
                "tags": ["analgésicos"],
            },
        ]

        vector_map = {
            "propanolol": [1.0, 0.0, 0.0],
            "paracetamol": [0.0, 1.0, 0.0],
            "amoxicilina": [0.0, 0.0, 1.0],
        }

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort(vector_map)
        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        deck_name = "Medicina::Farmacología"
        await service.sync_deck_index(deck_name)

        themes = [
            CoreTheme(
                id="t1",
                title="Mecanismo de Propanolol",
                description="Bloqueo de receptores beta adrenérgicos",
                recommended_cards=3,
            ),
            CoreTheme(
                id="t2",
                title="Farmacocinética de Paracetamol",
                description="Absorción y metabolismo de primer paso hepático",
                recommended_cards=4,
            ),
            CoreTheme(
                id="t3",
                title="Tratamiento con Amoxicilina",
                description="Antibiótico de amplio espectro bacteriano",
                recommended_cards=2,
            ),
        ]

        res = await service.match_themes(deck_name, themes)
        assert res.deck_name == deck_name
        assert res.total_indexed_notes == 2
        assert len(res.matches) == 3

        # Match 1: Propanolol -> Dominado (alta calidad, con trampa)
        m1 = res.matches[0]
        assert m1.status == PrerequisiteMatchStatus.DOMINATED
        assert m1.matched_note_id == 301
        assert m1.suggested_action == "keep_existing"

        # Match 2: Paracetamol -> Deuda Cognitiva (largo, sin trampa)
        m2 = res.matches[1]
        assert m2.status == PrerequisiteMatchStatus.COGNITIVE_DEBT
        assert m2.matched_note_id == 302
        assert m2.suggested_action in ("create_new", "refactor_existing")

        # Match 3: Amoxicilina -> Brecha / Gap
        m3 = res.matches[2]
        assert m3.status == PrerequisiteMatchStatus.GAP
        assert m3.matched_note_id is None
        assert m3.suggested_action == "create_new"


@pytest.mark.asyncio
async def test_deck_intelligence_match_study_plan_combined_and_auto_sync():
    """Verify that match_study_plan handles prerequisites and themes together with auto-sync."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_study_plan.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        mock_notes = [
            {
                "note_id": 401,
                "deck_name": "Medicina::Farmacología",
                "front": "¿Cuál es el mecanismo del propanolol?",
                "back": "Antagonista competitivo de receptores beta adrenérgicos.",
                "explanation": "⚠️ Trampa frecuente: contraindicado en asma.",
                "tags": ["beta-bloqueantes"],
            },
        ]

        vector_map = {
            "propanolol": [1.0, 0.0, 0.0],
            "amoxicilina": [0.0, 0.0, 1.0],
        }

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort(vector_map)
        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        deck_name = "Medicina::Farmacología"
        # Notice: we do NOT call sync_deck_index manually.
        # match_study_plan must auto-sync via _ensure_deck_indexed!

        prereqs = [
            PrerequisiteItem(
                concept="Propanolol y receptores adrenérgicos",
                reason="Concepto previo esencial",
                search_query="propanolol mecanismo",
            ),
        ]
        themes = [
            CoreTheme(
                id="th1",
                title="Terapia con Amoxicilina",
                description="Antibiótico bactericida beta-lactámico",
                recommended_cards=2,
            ),
        ]

        plan_res = await service.match_study_plan(
            deck_name=deck_name,
            prerequisites=prereqs,
            themes=themes,
        )

        assert plan_res.deck_name == deck_name
        assert plan_res.total_indexed_notes == 1
        assert len(plan_res.prerequisite_matches) == 1
        assert len(plan_res.theme_matches) == 1

        # Prereq matched Note 401 (Propanolol) -> DOMINATED
        p_match = plan_res.prerequisite_matches[0]
        assert p_match.status == PrerequisiteMatchStatus.DOMINATED
        assert p_match.matched_note_id == 401

        # Theme Amoxicilina -> GAP
        t_match = plan_res.theme_matches[0]
        assert t_match.status == PrerequisiteMatchStatus.GAP
        assert t_match.matched_note_id is None


class MockCardGenerator:
    def __init__(self, ai_response: Optional[dict] = None):
        self.ai_response = ai_response or {
            "breadcrumb": "Farmaco > Toxicología",
            "front": "¿Cuál es el metabolito reactivo hepatotóxico del paracetamol?",
            "back": "NAPQI (N-acetil-p-benzoquinoneimina).",
            "explanation": "⚠️ Trampa frecuente: solo produce necrosis centrolobulillar al depletarse el glutatión.",
            "diff_summary": "Eliminada sobrecarga enciclopédica; enfocada en mecanismo de toxicidad agudo.",
            "archetype": "Arquetipo C: Pregunta Atómica",
        }

    async def refactor_card(self, system_instruction: str, user_prompt: str) -> dict:
        return self.ai_response


@pytest.mark.asyncio
async def test_preview_refactor_note_with_image_preservation_and_mapping():
    """Verify that preview_refactor_note preserves embedded images and maps fields accurately."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_refactor_preview.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        # Note 701: Basic model with an embedded diagram image
        mock_notes = [
            {
                "note_id": 701,
                "deck_name": "Medicina::Farmacología",
                "model_name": "Basic",
                "front": "¿Farmacocinética y toxicidad del paracetamol?",
                "back": (
                    "Se metaboliza por glucuronidación y genera NAPQI. "
                    'Ver esquema anexo: <img src="paracetamol_toxicity_pathway.png">.'
                ),
                "explanation": "",
            },
            # Note 702: AnkiCraft Pro model with Breadcrumb, Front, Back, Extra
            {
                "note_id": 702,
                "deck_name": "Medicina::Farmacología",
                "model_name": "AnkiCraft Pro (Basic)",
                "front": "¿Toxicidad de paracetamol?",
                "back": "Produce falla hepática fulminante por sobredosis.",
                "explanation": "",
            },
        ]

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort()
        card_generator = MockCardGenerator()

        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
            card_generator=card_generator,
        )

        # 1. Preview Note 701 (Basic model)
        preview_basic = await service.preview_refactor_note(
            note_id=701,
            concept_context="Metabolismo tóxico de Paracetamol",
            deck_name="Medicina::Farmacología",
        )

        assert preview_basic.note_id == 701
        assert preview_basic.deck_name == "Medicina::Farmacología"
        assert preview_basic.model_name == "Basic"
        assert preview_basic.cognitive_archetype == "Arquetipo C: Pregunta Atómica"
        assert preview_basic.diff_summary == "Eliminada sobrecarga enciclopédica; enfocada en mecanismo de toxicidad agudo."
        assert "paracetamol_toxicity_pathway.png" in preview_basic.refactored_fields["Back"]
        assert "⚠️ Trampa frecuente" in preview_basic.refactored_fields["Back"]
        assert "NAPQI" in preview_basic.refactored_fields["Back"]
        # Basic model front includes breadcrumb in brackets
        assert "[Farmaco > Toxicología]" in preview_basic.refactored_fields["Front"]

        # 2. Preview Note 702 (AnkiCraft Pro model)
        preview_pro = await service.preview_refactor_note(
            note_id=702,
            concept_context="Metabolismo tóxico de Paracetamol",
            deck_name="Medicina::Farmacología",
        )

        assert preview_pro.note_id == 702
        assert preview_pro.model_name == "AnkiCraft Pro (Basic)"
        assert preview_pro.refactored_fields["Breadcrumb"] == "Farmaco > Toxicología"
        assert not preview_pro.refactored_fields["Front"].startswith("[")
        assert preview_pro.refactored_fields["Back"] == "NAPQI (N-acetil-p-benzoquinoneimina)."
        assert "⚠️ Trampa frecuente" in preview_pro.refactored_fields["Extra"]


@pytest.mark.asyncio
async def test_apply_refactor_note_in_place_and_reindex():
    """Verify that apply_refactor_note updates Anki fields in-place and re-indexes the SQLite store."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_refactor_apply.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        mock_notes = [
            {
                "note_id": 801,
                "deck_name": "Medicina::Farmacología",
                "model_name": "Basic",
                "front": "¿Farmacocinética del paracetamol?",
                "back": "Texto viejo con deuda cognitiva.",
                "explanation": "",
            },
        ]

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort({
            "metabolito reactivo": [0.9, 0.1, 0.0],
        })

        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        # Pre-index note in store
        await service.sync_deck_index("Medicina::Farmacología")

        # Apply refactor
        new_fields = {
            "Front": "¿Cuál es el metabolito reactivo de paracetamol?",
            "Back": "NAPQI.<br><br><small>⚠️ Trampa frecuente: se neutraliza con glutatión.</small>",
        }

        apply_res = await service.apply_refactor_note(
            note_id=801,
            deck_name="Medicina::Farmacología",
            fields=new_fields,
        )

        assert apply_res.success is True
        assert apply_res.note_id == 801
        assert "FSRS" in apply_res.message
        assert anki_bridge.updated_fields[801] == new_fields

        # Check that SQLite store has updated front/back
        indexed = store.semantic_search("Medicina::Farmacología", [0.9, 0.1, 0.0], top_k=1, min_similarity=0.0)
        assert len(indexed) == 1
        assert indexed[0]["note_id"] == 801
        assert "NAPQI" in indexed[0]["back"]


@pytest.mark.asyncio
async def test_deck_intelligence_match_study_plan_with_exclude_note_ids():
    """Verify that match_study_plan excludes specified note IDs (e.g. source note in analysis)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_match_exclude.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        mock_notes = [
            {
                "note_id": 901,
                "deck_name": "Medicina::Farmacología",
                "front": "¿Farmacocinética y toxicidad del paracetamol?",
                "back": "Produce NAPQI hepatotóxico.",
                "explanation": "⚠️ Trampa frecuente: daño con glutatión bajo.",
            },
            {
                "note_id": 902,
                "deck_name": "Medicina::Farmacología",
                "front": "¿Mecanismo del propanolol?",
                "back": "Beta bloqueante no selectivo.",
                "explanation": "⚠️ Trampa frecuente: evitar en asma.",
            },
        ]

        vector_map = {
            "paracetamol": [1.0, 0.0, 0.0],
            "propanolol": [0.0, 1.0, 0.0],
        }

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort(vector_map)
        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        deck_name = "Medicina::Farmacología"
        await service.sync_deck_index(deck_name)

        prereqs = [
            PrerequisiteItem(
                concept="Paracetamol y NAPQI",
                reason="Concepto fundamental",
                search_query="paracetamol metabolismo",
            )
        ]
        themes = [
            CoreTheme(
                id="th_paracetamol",
                title="Toxicidad de Paracetamol",
                description="Hepatotoxicidad por metabolito reactivo",
                recommended_cards=3,
            )
        ]

        # 1. Without exclusion: Note 901 matches both
        res_no_exclude = await service.match_study_plan(
            deck_name=deck_name,
            prerequisites=prereqs,
            themes=themes,
        )
        assert res_no_exclude.prerequisite_matches[0].matched_note_id == 901
        assert res_no_exclude.theme_matches[0].matched_note_id == 901

        # 2. With exclude_note_ids=[901]: Note 901 is ignored, resulting in GAP (new topic)
        res_with_exclude = await service.match_study_plan(
            deck_name=deck_name,
            prerequisites=prereqs,
            themes=themes,
            exclude_note_ids=[901],
        )
        assert res_with_exclude.prerequisite_matches[0].status == PrerequisiteMatchStatus.GAP
        assert res_with_exclude.prerequisite_matches[0].matched_note_id is None

        assert res_with_exclude.theme_matches[0].status == PrerequisiteMatchStatus.GAP
        assert res_with_exclude.theme_matches[0].matched_note_id is None


@pytest.mark.asyncio
async def test_deck_intelligence_find_duplicates():
    """Verify that find_deck_duplicates detects near-identical and duplicate notes above similarity threshold."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_dup.db"
        store = DeckKnowledgeStore(db_path=str(db_path))

        mock_notes = [
            {
                "note_id": 1001,
                "deck_name": "TestDeck",
                "front": "OCI Responses API",
                "back": "API for responses in OCI",
                "explanation": "",
                "tags": ["oci"],
            },
            {
                "note_id": 1002,
                "deck_name": "TestDeck",
                "front": "OCI Responses API",
                "back": "API for responses in OCI (Duplicate)",
                "explanation": "",
                "tags": ["oci"],
            },
            {
                "note_id": 1003,
                "deck_name": "TestDeck",
                "front": "Unrelated Networking Concept",
                "back": "Virtual Cloud Network VCN",
                "explanation": "",
                "tags": ["network"],
            },
        ]

        vector_map = {
            "responses api": [1.0, 0.0, 0.0],
            "networking": [0.0, 1.0, 0.0],
        }

        anki_bridge = MockAnkiBridge(mock_notes)
        embedding_port = MockEmbeddingPort(vector_map)
        service = DeckIntelligenceService(
            anki_bridge=anki_bridge,
            embedding_port=embedding_port,
            store=store,
        )

        # Index the notes
        await service.sync_deck_index("TestDeck")

        # Find duplicates with min_similarity=0.88
        dup_res = await service.find_deck_duplicates("TestDeck", min_similarity=0.88)
        assert dup_res.deck_name == "TestDeck"
        assert dup_res.total_pairs == 1
        assert dup_res.pairs[0].note_id_1 == 1001
        assert dup_res.pairs[0].note_id_2 == 1002
        assert dup_res.pairs[0].similarity == 1.0




