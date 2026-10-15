# AnkiCraft AI - System Index & Agent Knowledge Map

```yaml
---
project: AnkiCraft AI
type: Knowledge Engineering & Spaced Repetition Platform
version: 2.1.0
last_audit_date: 2026-10-14
system_health:
  backend_regression_tests: 119/119 passing (backend/tests/)
  backend_audits_and_fuzzing: 33/33 passing (backend/audits/ Levels 1-6)
  frontend_e2e_tests: 6/6 passing (frontend/e2e/ Playwright)
  total_automated_tests: 158/158 PASS (100% Zero Regressions)
  frontend_quality: 0 tsc errors, 0 oxlint warnings/errors
active_runtime_environment:
  backend: Python 3.14 + FastAPI + Pydantic v2 (port 8000)
  frontend: React 19 + TypeScript 5.8 + Vite 6 + Tailwind CSS v4 (port 5173)
  anki_bridge: AnkiConnect JSON-RPC (port 8765) + Genanki .apkg fallback
  ai_cloud_cascade:
    tier_1: Google Gemini 3.8 Flash (google-genai SDK, Structured Outputs)
    tier_2: NVIDIA NIM (meta/llama-3.2-90b-vision-instruct)
    tier_3: Groq (qwen/qwen3.8-27b)
    tier_4: OpenRouter Free (openrouter/free)
    protection: In-memory circuit breakers with exponential backoff & jitter
  ai_local_gpu: Ollama AMD GPU on 127.0.0.1:11434 (llama3.2:3b, qwen2.5:14b, qwen2.5vl:7b multimodal)
  local_storage: SQLite vector store (backend/data/deck_knowledge.db)
---
```

> **Target Audience**: AI Agents, LLMs, and Human Senior Engineers.  
> **Purpose**: Single Source of Truth (SSOT). This file is the primary entry point to immediately understand what exists, where it is located, and how it is verified—eliminating hallucinations or assumptions about outdated code.

---

## 1. Project Mission & Core Capabilities

AnkiCraft AI is a local production-grade system that converts unstructured educational material (raw text, PDF textbooks, whiteboard/slide diagrams, existing Anki decks) into **atomic, high-retention flashcards** adhering to **FSRS** and **Piotr Wozniak's 20 Rules of Formulating Knowledge**.

### Four Core Workflows
1. **Scaffolded Ingestion & Generation**: Pre-flight inspection $\to$ Prerequisite gap detection $\to$ Dynamic cognitive density calculation $\to$ Deterministic Cloze/LaTeX sanitization $\to$ Direct AnkiConnect injection or `.apkg` download.
2. **Deck Studio (Curriculum Cockpit)**: Full deck analysis, NetworkX concept precedence DAG, cognitive debt table, spherical K-Means semantic clustering, and topological expansion.
3. **Socratic Diagnostic Interview**: Dynamic Q&A evaluating deck purpose, formulating an approved `LearningPlanContract` (Bloom taxonomy depth, negative boundaries, gap strategy).
4. **Surgical Card & Cluster Sanitation**:
   - **Level 1 (In-situ Refactor)**: Rewrites ambiguous/bloated cards in-place via AnkiConnect, strictly preserving `note_id`, review intervals, and FSRS history.
   - **Level 2 (Cluster Sanitation)**: Replaces monolithic notes with 2–4 atomic sister cards transactionally (creates new cards, verifies them, deletes old note with zero-data-loss rollback).

---

## 2. Feature-to-Code Traceability Matrix

Every system capability is mapped directly to its backend service, frontend component, API endpoint, and automated test suite:

| Capability / Feature | Backend Service / Module | Frontend Component | API Route / Contract | Test Suite |
| :--- | :--- | :--- | :--- | :--- |
| **Card Generation (Cloud)** | `generate_cards_service.py`<br>`gemini_card_generator_adapter.py` | `App.tsx`<br>`GenerationConfigBar.tsx` | `POST /api/generate` | `tests/test_generate_cards_service.py`<br>`tests/test_gemini_card_generator.py` |
| **Resilient AI Cascade** | `resilient_cascade_adapter.py` | `Header.tsx` (Status pill) | Inbound adapter fallback | `tests/test_resilient_cascade_adapter.py` |
| **Local GPU (Ollama)** | `ollama_adapter.py` | `Header.tsx`<br>`OllamaModelPicker.tsx` | `GET /api/ollama/status`<br>`POST /api/generate` | `tests/test_ollama_adapter.py` |
| **Pre-Flight Cockpit** | `inspect_material_service.py` | `MaterialInspectionCockpit.tsx`<br>`ActiveStudyPlanBanner.tsx` | `POST /api/inspect`<br>`POST /api/enrich-prerequisite` | `tests/test_inspect_material_service.py` |
| **Deterministic Cloze Sanitizer** | `cloze_sanitizer.py` | `CardContentRenderer.tsx` | Deterministic pipeline filter | `tests/test_cloze_sanitizer.py`<br>`audits/test_l2_cognitive_linters.py` |
| **Cognitive Auditor & Decoupler** | `cognitive_auditor_service.py`<br>`semantic_auditor_agent.py` | `CognitiveAuditModal.tsx`<br>`SisterCardBadge.tsx` | `POST /api/audit-deck` | `tests/test_cognitive_auditor_service.py`<br>`audits/test_l2_cognitive_linters.py` |
| **Anki Bridge & .apkg Export** | `anki_connect_adapter.py`<br>`genanki_file_adapter.py` | `App.tsx`<br>`SyncButton.tsx` | `POST /api/export`<br>`GET /api/anki/status` | `tests/test_anki_connect_adapter.py`<br>`tests/test_export_deck_service.py` |
| **Deck Studio Hub** | `deck_intelligence_service.py` | `DeckStudioModal.tsx`<br>`DeckPickerModal.tsx` | `GET /api/anki/decks`<br>`GET /api/anki/decks/{name}/stats` | `tests/test_deck_intelligence_service.py`<br>`frontend/e2e/flow_c_deck_studio_dag.spec.ts` |
| **Vector Store & Indexing** | `deck_knowledge_store.py`<br>`gemini_embedding_adapter.py` | `DeckStudioModal.tsx` (Index button) | `POST /api/anki/decks/{name}/sync-index` | `tests/test_deck_knowledge_store.py`<br>`tests/test_gemini_embedding_adapter.py` |
| **Concept Precedence DAG** | `deck_dag_service.py` (NetworkX) | `CognitivePrecedenceDAG.tsx` | `GET /api/anki/decks/{name}/dag` | `tests/test_deck_dag_service.py`<br>`audits/test_l1_topological_dag.py` |
| **Semantic Clustering** | `clustering.py` (Spherical K-Means) | `DeckStudioModal.tsx` (Checklist tab) | `GET /api/anki/decks/{name}/semantic-clusters` | `tests/test_spherical_kmeans.py`<br>`audits/test_l1_topological_dag.py` |
| **Socratic Interview & Contract** | `deck_interview_service.py` | `DeckInterviewModal.tsx` | `POST /api/anki/decks/{name}/interview/synthesize` | `tests/test_deck_interview_service.py`<br>`audits/test_l4_pedagogical_judge.py` |
| **In-Situ Note Refactor (FSRS)** | `sanitation_service.py`<br>`anki_connect_adapter.py` | `RefactorNoteModal.tsx` | `POST /api/anki/decks/{name}/notes/{id}/refactor/apply` | `tests/test_sanitation_service.py`<br>`audits/test_l3_sanitizer_safety.py` |
| **Cluster Sanitation (Cockpit/Batch)** | `sanitation_service.py` | `ClusterSanitationModal.tsx` | `POST /api/anki/decks/{name}/clusters/{id}/sanitize` | `tests/test_sanitation_service.py`<br>`audits/test_l3_sanitizer_safety.py` |
| **Topological Deck Expansion** | `deck_expansion_service.py` | `DeckStudioModal.tsx` (Expansion tab) | `GET /api/anki/decks/{name}/expansion/orphan-queue` | `tests/test_deck_expansion_service.py`<br>`audits/test_l1_topological_dag.py` |
| **Exam Blueprint Alignment** | `exam_blueprint_service.py` (pypdf) | `DeckStudioModal.tsx` (Blueprint tab) | `POST /api/anki/decks/{name}/blueprint/align` | `tests/test_exam_blueprint_service.py` |
| **Pedagogical LLM-as-a-Judge** | `pedagogical_judge_service.py` | Quality audit reports | Heuristic & LLM Judge | `audits/test_l4_pedagogical_judge.py` |
| **Adversarial Red Teaming** | `socratic_red_teaming_service.py` | Quality verification harness | Critic-Defender-Arbiter | `audits/test_l5_socratic_red_teaming.py` |
| **Property-Based API Fuzzing** | Schemathesis 4.31 harness | Automated harness | 52 FastAPI endpoints | `audits/test_l6_schemathesis_fuzzing.py` |

---

## 3. Directory Layout & Module Responsibilities

```
Anki Flashcards IA/
├── backend/
│   ├── app/
│   │   ├── adapters/
│   │   │   ├── ai/
│   │   │   │   ├── gemini_card_generator_adapter.py  # Primary Cloud LLM (Gemini 3.8 Flash, Structured Outputs)
│   │   │   │   ├── gemini_embedding_adapter.py       # Google GenAI vector embeddings (text-embedding-004)
│   │   │   │   ├── ollama_adapter.py                 # Local LLM adapter (AMD GPU via Ollama, vision support)
│   │   │   │   └── resilient_cascade_adapter.py      # 4-tier provider cascade with circuit breakers
│   │   │   ├── anki/
│   │   │   │   ├── anki_connect_adapter.py           # Anki Desktop JSON-RPC bridge (port 8765)
│   │   │   │   └── genanki_file_adapter.py           # Standalone .apkg binary package builder
│   │   │   └── db/
│   │   │       └── deck_knowledge_store.py           # SQLite vector repository, cosine search, DAG tables
│   │   ├── api/
│   │   │   ├── deps.py                               # FastAPI dependency injection factories
│   │   │   └── routes.py                             # 52 REST API endpoints across all workflows
│   │   ├── core/
│   │   │   ├── cloze_sanitizer.py                    # Deterministic Cloze syntax sanitizer & repairer
│   │   │   ├── clustering.py                         # Spherical K-Means & cosine clustering
│   │   │   ├── config.py                             # App settings & model constants
│   │   │   ├── formatting.py                         # Anki HTML, math syntax, KaTeX formatting
│   │   │   └── logging_config.py                     # Rotating log buffer for /api/logs/recent
│   │   ├── domain/
│   │   │   └── models.py                             # Pydantic v2 schemas, domain entities & DTOs
│   │   ├── ports/
│   │   │   ├── anki_bridge_port.py                   # Protocol interface for Anki Desktop / .apkg
│   │   │   ├── card_generator_port.py                # Protocol interface for card generation
│   │   │   └── embedding_port.py                     # Protocol interface for vector embeddings
│   │   ├── services/                                 # 15 domain & application services (see matrix)
│   │   └── main.py                                   # FastAPI entrypoint, lifespan, CORS, middleware
│   ├── audits/                                       # 33 Quality, Topological & Fuzzing audit tests (L1-L6)
│   └── tests/                                        # 119 Unit and service integration tests
├── frontend/
│   ├── src/
│   │   ├── components/                               # Modular React 19 UI components (see matrix)
│   │   ├── services/
│   │   │   └── api.ts                                # Axios / Fetch API client & endpoint contracts
│   │   ├── types/
│   │   │   └── index.ts                              # TypeScript models matching backend DTOs
│   │   ├── App.tsx                                   # Main view container & state orchestration
│   │   └── main.tsx                                  # React DOM bootstrap
│   ├── e2e/                                          # 6 Playwright E2E browser tests (Flows A, B, C, D)
│   ├── index.html                                    # HTML shell with KaTeX and dark theme styles
│   └── vite.config.ts                                # Vite configuration with chunk splitting
├── docs/                                             # System documentation (see Documentation Guide below)
├── start.bat                                         # One-click Windows launcher (starts backend + frontend)
└── README.md                                         # Main public repository overview
```

---

## 4. Verification & Testing Commands

To verify system integrity, run the corresponding command suites:

```powershell
# 1. Run Backend Regression Suite (119 tests ~ 113s)
cd backend
.\.venv\Scripts\python -m pytest tests -q

# 2. Run Backend Pedagogical Audits & Schemathesis Fuzzing (33 tests ~ 158s)
cd backend
.\.venv\Scripts\python -m pytest audits -v

# 3. Run Full Backend Verification (152 tests ~ 270s)
cd backend
.\.venv\Scripts\python -m pytest tests audits -q

# 4. Run Frontend Quality Checks (Types & Oxlint)
cd frontend
npx tsc -b
npm run lint

# 5. Run Frontend Production Build (Validates Vite bundles & code splitting)
cd frontend
npm run build

# 6. Run Playwright E2E Integration Suite (6 tests ~ 11s)
cd frontend
npm run test:e2e
```

---

## 5. Documentation Directory Guide

* [`docs/INDEX.md`](file:///c:/Users/Manolo/Desktop/Antigravity%20Proyects/Anki%20Flashcards%20IA/docs/INDEX.md) (This file): Master navigation index, YAML frontmatter, traceability matrix, and verification commands.
* [`docs/ARCHITECTURE.md`](file:///c:/Users/Manolo/Desktop/Antigravity%20Proyects/Anki%20Flashcards%20IA/docs/ARCHITECTURE.md): Comprehensive hexagonal architecture, AI cascade tiers, and database persistence layers.
* [`docs/CONVENTIONS.md`](file:///c:/Users/Manolo/Desktop/Antigravity%20Proyects/Anki%20Flashcards%20IA/docs/CONVENTIONS.md): Coding rules, strict typing, error handling protocols, and cognitive science standards.
* [`docs/ROADMAP.md`](file:///c:/Users/Manolo/Desktop/Antigravity%20Proyects/Anki%20Flashcards%20IA/docs/ROADMAP.md): Real-time project roadmap (completed milestones vs active backlog).
* [`docs/AUDIT_FINDINGS.md`](file:///c:/Users/Manolo/Desktop/Antigravity%20Proyects/Anki%20Flashcards%20IA/docs/AUDIT_FINDINGS.md): Full certified quality ledger for Backend Levels 1–6 and Frontend Levels F1–F6.
* [`docs/SANITATION_WORKFLOW_AUDIT.md`](file:///c:/Users/Manolo/Desktop/Antigravity%20Proyects/Anki%20Flashcards%20IA/docs/SANITATION_WORKFLOW_AUDIT.md): Diagnostic and unification roadmap for Deck Studio card/cluster sanitation.
