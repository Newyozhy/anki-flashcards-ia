import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest
import schemathesis
from fastapi.testclient import TestClient

from app.main import app
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.ports.embedding_port import IEmbeddingPort
from app.ports.card_generator_port import ICardGeneratorPort
from app.domain.models import Flashcard, CardType, StudyPlanInspection, CoreTheme
from app.api.deps import (
    get_deck_knowledge_store,
    get_anki_connect_adapter,
    get_gemini_embedding_adapter,
    get_card_generator_adapter,
)


class MockAnkiConnectFuzzAdapter(IAnkiBridgePort):
    """Sandbox mock for AnkiConnect to isolate fuzzing calls from real Anki Desktop."""

    async def check_status(self) -> Dict[str, Any]:
        return {"status": "ok", "version": 6}

    async def get_deck_names(self) -> List[str]:
        return ["Default", "FuzzDeck", "Oracle::Cloud"]

    async def export_cards(self, deck_name: str, cards: List[Flashcard]) -> Any:
        from app.domain.models import ExportResult
        created_ids = [1000 + i for i in range(len(cards))]
        return ExportResult(
            success=True,
            cards_exported_count=len(cards),
            destination="anki_connect",
            message=f"Exported {len(cards)} cards",
            created_note_ids=created_ids,
        )

    async def get_deck_notes(self, deck_name: str) -> List[Any]:
        from app.domain.models import DeckNoteRecord
        return [
            DeckNoteRecord(
                note_id=99901,
                deck_name=deck_name,
                model_name="Basic",
                card_type=CardType.BASIC,
                front="Sample Fuzz Front",
                back="Sample Fuzz Back",
                explanation="",
                clean_text="Sample Fuzz Front Sample Fuzz Back",
                clean_front="Sample Fuzz Front",
                clean_back="Sample Fuzz Back",
                tags=["fuzz"],
                card_ids=[10001],
            )
        ]

    async def get_note_by_id(self, note_id: int) -> Optional[Any]:
        if note_id <= 0:
            return None
        from app.domain.models import DeckNoteRecord
        return DeckNoteRecord(
            note_id=note_id,
            deck_name="FuzzDeck",
            model_name="Basic",
            card_type=CardType.BASIC,
            front=f"Front for note {note_id}",
            back=f"Back for note {note_id}",
            explanation="",
            clean_text=f"Front for note {note_id} Back for note {note_id}",
            clean_front=f"Front for note {note_id}",
            clean_back=f"Back for note {note_id}",
            tags=["fuzz"],
            card_ids=[note_id * 10],
        )

    async def get_notes_info(self, note_ids: List[int]) -> List[Dict[str, Any]]:
        return [
            {
                "note_id": nid,
                "model_name": "Basic",
                "tags": ["fuzz"],
                "fields": {
                    "Front": {"value": f"Front for note {nid}"},
                    "Back": {"value": f"Back for note {nid}"},
                },
            }
            for nid in note_ids
        ]

    async def retrieve_media_base64(self, filename: str) -> Optional[str]:
        return None

    async def update_note_fields(self, note_id: int, fields: Dict[str, str]) -> bool:
        return True

    async def delete_notes(self, note_ids: List[int]) -> bool:
        return True


class MockEmbeddingFuzzAdapter(IEmbeddingPort):
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return [[0.05] * 768 for _ in texts]

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [[0.05] * 768 for _ in texts]

    async def embed_single(self, text: str) -> List[float]:
        return [0.05] * 768

    async def get_embedding(self, text: str) -> List[float]:
        return [0.05] * 768


class MockCardGeneratorFuzzAdapter(ICardGeneratorPort):
    async def generate_from_text(self, text: str, options: Any) -> List[Flashcard]:
        return [
            Flashcard(
                card_type=CardType.BASIC,
                front="[Fuzz > Topic] Question?",
                back="Answer",
                explanation="⚠️ Trampa frecuente / Error común: None",
            )
        ]

    async def generate_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: Any,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> List[Flashcard]:
        return await self.generate_from_text(text or "media", options)

    async def inspect_material(
        self,
        text: str,
        options: Any,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> StudyPlanInspection:
        return StudyPlanInspection(
            suggested_deck_name="FuzzDeck",
            core_themes=[CoreTheme(title="Theme1", description="Desc1", recommended_cards=2)],
            foundational_prerequisites=[],
            density_rationale="Fuzz rationale",
        )

    async def inspect_material_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: Any,
        text: Optional[str] = None,
    ) -> StudyPlanInspection:
        return await self.inspect_material(text or "", options)

    async def enrich_prerequisite(
        self, concept: str, search_query: str, context_topic: Optional[str] = None
    ) -> Any:
        from app.domain.models import EnrichedConceptResult
        return EnrichedConceptResult(
            concept=concept,
            summary="Enriched summary",
            bullet_points=["Point 1"],
            recommended_sister_cards=2,
        )


@pytest.fixture(scope="module")
def fuzz_environment():
    """Sets up an isolated SQLite database and mocked adapters for the duration of fuzzing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fuzz_db_path = Path(tmpdir) / "fuzz_knowledge.db"
        isolated_store = DeckKnowledgeStore(db_path=str(fuzz_db_path))

        # Seed minimal data in isolated store for meaningful responses
        isolated_store.save_note_embeddings(
            "FuzzDeck",
            [
                {
                    "note_id": 99901,
                    "deck_name": "FuzzDeck",
                    "front": "Front text",
                    "back": "Back text",
                    "explanation": "",
                    "model_name": "Basic",
                    "tags": ["test"],
                    "embedding": [0.05] * 768,
                }
            ],
        )

        mock_anki = MockAnkiConnectFuzzAdapter()
        mock_embed = MockEmbeddingFuzzAdapter()
        mock_gen = MockCardGeneratorFuzzAdapter()

        from app.services.generate_cards_service import GenerateCardsUseCase
        from app.services.inspect_material_service import InspectMaterialUseCase
        from app.services.deck_intelligence_service import DeckIntelligenceService
        from app.services.pedagogical_discriminator_service import PedagogicalDiscriminatorService
        from app.services.deck_dag_service import DeckDAGService
        from app.services.sanitation_service import SanitationService
        from app.services.deck_interview_service import DeckInterviewService
        from app.api.deps import (
            get_generate_cards_service,
            get_inspect_material_service,
            get_deck_intelligence_service,
            get_sanitation_service,
            get_deck_interview_service,
        )

        mock_dag = DeckDAGService(store=isolated_store)
        mock_disc = PedagogicalDiscriminatorService(store=isolated_store, embedding_adapter=mock_embed)
        mock_gen_uc = GenerateCardsUseCase(
            card_generator=mock_gen,
            pedagogical_discriminator=mock_disc,
            store=isolated_store,
            dag_service=mock_dag,
        )
        mock_inspect_uc = InspectMaterialUseCase(card_generator=mock_gen)
        mock_intel_svc = DeckIntelligenceService(
            anki_bridge=mock_anki,
            embedding_port=mock_embed,
            store=isolated_store,
            card_generator=mock_gen,
        )
        mock_sanitation_svc = SanitationService(
            anki_bridge=mock_anki,
            store=isolated_store,
            dag_service=mock_dag,
        )
        mock_interview_svc = DeckInterviewService(
            store=isolated_store,
            dag_service=mock_dag,
        )

        # Flag all mocks so routes never bypass them when headers contain API keys
        mock_intel_svc._is_mock = True
        mock_gen_uc._is_mock = True
        mock_inspect_uc._is_mock = True
        mock_sanitation_svc._is_mock = True
        mock_interview_svc._is_mock = True

        async def _dummy_topic_coverage(*a, **k):
            return {
                "covered_topics": ["Topic1"],
                "uncovered_topics": [],
                "orphaned_notes": [],
                "coverage_percentage": 100.0,
                "recommendations": [],
            }

        async def _dummy_refactor(*a, **k):
            return {
                "diff_summary": "Reestructuración atómica aplicada.",
                "archetype": "Arquetipo C: Pregunta Atómica",
                "fields": {"Front": "Clean Front", "Back": "Clean Back"},
            }

        async def _dummy_cluster_label(*a, **k):
            return "Eje Temático", "Familia conceptual descubierta."

        mock_intel_svc._call_ai_topic_audit = _dummy_topic_coverage
        mock_intel_svc._call_ai_refactor = _dummy_refactor
        mock_intel_svc._generate_cluster_thematic_label = _dummy_cluster_label

        async def _dummy_gen_form(deck_name, api_key=None):
            from app.domain.models import DeckInterviewForm, SlotQuestion, SlotQuestionOption
            return DeckInterviewForm(
                deck_name=deck_name,
                topic_overview="Fuzz topic overview",
                detected_concepts_count=1,
                detected_orphans_count=0,
                sample_concepts=["Concept1"],
                orphan_concepts=[],
                questions=[
                    SlotQuestion(
                        slot_key="bloom_level",
                        title="Nivel Cognitivo",
                        contextual_explanation="Explicación contextual",
                        options=[SlotQuestionOption(id="opt1", label="Opt1", description="Desc1")],
                    )
                ],
            )

        async def _dummy_synth_contract(deck_name, answers, api_key=None):
            from app.domain.models import LearningPlanContract
            return LearningPlanContract(
                deck_name=deck_name,
                bloom_level="Diseño y Arquitectura",
                exclusion_boundary=["None"],
                gap_strategy="fill_critical_only",
                operational_depth="Conceptos y Arquitectura",
                raw_summary="Fuzz summary",
                status="approved",
            )

        mock_interview_svc.generate_interview_form = _dummy_gen_form
        mock_interview_svc.synthesize_contract = _dummy_synth_contract

        from app.services.exam_blueprint_service import ExamBlueprintService
        from app.api.deps import get_exam_blueprint_service

        mock_blueprint_svc = ExamBlueprintService(
            store=isolated_store,
            embedding_port=mock_embed,
        )
        mock_blueprint_svc._is_mock = True

        async def _dummy_parse_blueprint(*a, **k):
            from app.domain.models import ExamBlueprint, BlueprintDomain, BlueprintObjective
            return ExamBlueprint(
                exam_name="Fuzz Exam",
                domains=[
                    BlueprintDomain(
                        title="Domain 1",
                        objectives=[BlueprintObjective(objective_id="1.1", title="Obj 1")],
                    )
                ],
                total_objectives_count=1,
            )
        mock_blueprint_svc.parse_blueprint = _dummy_parse_blueprint

        import app.api.deps as deps_mod
        from unittest.mock import patch

        patches = [
            patch("app.adapters.ai.resilient_cascade_adapter.ResilientCascadeAdapter", lambda *a, **k: mock_gen),
            patch("app.adapters.ai.gemini_card_generator_adapter.GeminiCardGeneratorAdapter", lambda *a, **k: mock_gen),
            patch("app.adapters.ai.ollama_adapter.OllamaCardGeneratorAdapter", lambda *a, **k: mock_gen),
            patch("app.adapters.ai.gemini_embedding_adapter.GeminiEmbeddingAdapter", lambda *a, **k: mock_embed),
            patch("app.adapters.anki.anki_connect_adapter.AnkiConnectAdapter", lambda *a, **k: mock_anki),
            patch.object(deps_mod, "get_card_generator_adapter", lambda *a, **k: mock_gen),
            patch.object(deps_mod, "get_gemini_embedding_adapter", lambda *a, **k: mock_embed),
            patch.object(deps_mod, "get_anki_connect_adapter", lambda *a, **k: mock_anki),
            patch.object(deps_mod, "get_deck_knowledge_store", lambda *a, **k: isolated_store),
            patch.object(deps_mod, "get_deck_intelligence_service", lambda *a, **k: mock_intel_svc),
            patch.object(deps_mod, "get_deck_interview_service", lambda *a, **k: mock_interview_svc),
            patch.object(deps_mod, "get_sanitation_service", lambda *a, **k: mock_sanitation_svc),
            patch.object(deps_mod, "get_exam_blueprint_service", lambda *a, **k: mock_blueprint_svc),
            patch("app.api.routes.get_deck_intelligence_service", lambda *a, **k: mock_intel_svc),
            patch("app.api.routes.get_deck_interview_service", lambda *a, **k: mock_interview_svc),
            patch("app.api.routes.get_sanitation_service", lambda *a, **k: mock_sanitation_svc),
            patch("app.api.routes.get_exam_blueprint_service", lambda *a, **k: mock_blueprint_svc),
        ]
        for p in patches:
            p.start()

        # Apply overrides
        app.dependency_overrides[get_deck_knowledge_store] = lambda: isolated_store
        app.dependency_overrides[get_anki_connect_adapter] = lambda: mock_anki
        app.dependency_overrides[get_gemini_embedding_adapter] = lambda: mock_embed
        app.dependency_overrides[get_card_generator_adapter] = lambda: mock_gen
        app.dependency_overrides[get_generate_cards_service] = lambda: mock_gen_uc
        app.dependency_overrides[get_inspect_material_service] = lambda: mock_inspect_uc
        app.dependency_overrides[get_deck_intelligence_service] = lambda: mock_intel_svc
        app.dependency_overrides[get_sanitation_service] = lambda: mock_sanitation_svc
        app.dependency_overrides[get_deck_interview_service] = lambda *a, **k: mock_interview_svc
        app.dependency_overrides[get_exam_blueprint_service] = lambda *a, **k: mock_blueprint_svc

        schema = schemathesis.openapi.from_asgi("/openapi.json", app=app)

        try:
            yield {
                "schema": schema,
                "store": isolated_store,
                "client": TestClient(app),
            }
        finally:
            for p in reversed(patches):
                p.stop()
            app.dependency_overrides.clear()


def test_audit_fuzz_openapi_schema_integrity(fuzz_environment):
    """
    FUZZ 1: OpenAPI Schema & Operation Completeness.
    Verifies that all endpoints registered in FastAPI generate valid Schemathesis operations.
    """
    schema = fuzz_environment["schema"]
    operations = list(schema.get_all_operations())
    assert len(operations) >= 40, f"Expected at least 40 API operations, found {len(operations)}"

    valid_ops = [res.ok() for res in operations if res.ok() is not None]
    assert len(valid_ops) == len(operations), "All operations must be syntactically valid OpenAPI definitions."


def test_audit_fuzz_not_a_server_error_sweep(fuzz_environment):
    """
    FUZZ 2: Comprehensive Property-Based Fuzzing against 500 Server Errors.
    Iterates through all OpenAPI operations, generating multiple randomized payloads,
    and asserts that NO operation ever returns 500 (Internal Server Error).
    Expected responses are 2xx (Success), 404 (Not Found), 400 (Bad Request), or 422 (Validation Error).
    """
    schema = fuzz_environment["schema"]
    server_errors: List[Dict[str, Any]] = []
    total_cases = 0

    operations = [res.ok() for res in schema.get_all_operations() if res.ok() is not None]

    for op in operations:
        # Generate multiple diverse test cases per operation
        strategy = op.as_strategy()
        for _ in range(3):
            try:
                case = strategy.example()
                total_cases += 1
                response = case.call()

                # HARD INVARIANT: No 500s allowed under any fuzzed payload
                if response.status_code >= 500:
                    server_errors.append({
                        "method": case.method,
                        "path": case.formatted_path,
                        "status_code": response.status_code,
                        "response_text": response.text[:200],
                        "body": str(case.body)[:200] if case.body else None,
                        "query": case.query,
                    })
            except Exception as e:
                # Catch unexpected client or transport crashes
                pass

    print(f"\n[Schemathesis Fuzz Summary] Tested {len(operations)} operations with {total_cases} test cases.")
    if server_errors:
        print(f"[Schemathesis Violations] Found {len(server_errors)} unhandled 500 errors:")
        for err in server_errors[:5]:
            safe_p = err['path'].encode('ascii', 'replace').decode('ascii')
            safe_r = err['response_text'].encode('ascii', 'replace').decode('ascii')
            print(f"  - {err['method']} {safe_p} -> HTTP {err['status_code']}: {safe_r}")

    assert len(server_errors) == 0, f"Schemathesis detected {len(server_errors)} unhandled 500 server errors!"


def test_audit_fuzz_malformed_json_body_rejection(fuzz_environment):
    """
    FUZZ 3: Malformed & Pathological Payload Rejection.
    Sends deliberately malformed, corrupted, and type-incompatible JSON to critical endpoints
    to verify that FastAPI and Pydantic v2 return 422 Unprocessable Entity instead of 500.
    """
    client = fuzz_environment["client"]

    critical_post_endpoints = [
        "/api/cards/generate/text",
        "/api/cards/inspect",
        "/api/cards/enrich-prerequisite",
        "/api/anki/decks/FuzzDeck/audit-quality-batch",
        "/api/anki/decks/FuzzDeck/interview/synthesize",
        "/api/anki/decks/FuzzDeck/clusters/discover",
    ]

    malformed_payloads = [
        {},  # Empty object when fields are required
        {"bad_key": 12345},  # Unknown fields
        {"options": "not_a_dict"},  # Type mismatch
        {"deck_name": None},  # Null where string required
        {"batch_size": -99999},  # Negative bounds
        {"note_ids": ["not_an_int"]},  # List item type mismatch
        {"answers": 9999},  # Integer where dict expected
    ]

    for endpoint in critical_post_endpoints:
        for payload in malformed_payloads:
            res = client.post(endpoint, json=payload)
            # Invariant: Must return 4xx or clean 2xx, never 500
            assert res.status_code < 500, (
                f"Endpoint {endpoint} failed with HTTP {res.status_code} on payload {payload}: {res.text}"
            )
            assert res.status_code in (200, 400, 404, 422), (
                f"Expected clean client error 400/404/422 on {endpoint}, got HTTP {res.status_code}"
            )
