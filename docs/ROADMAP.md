# AnkiCraft AI - Project Roadmap

> High-level tracker of completed milestones and upcoming capabilities.

---

## 1. Core Platform & Architecture

- [x] **Hexagonal Architecture Core**: Decoupling between domain use cases, AI generators, and Anki storage.
- [x] **FastAPI Inbound REST Controllers**: 52 endpoints with Pydantic v2 schemas and friendly error formatting.
- [x] **AnkiConnect Bridge**: Local JSON-RPC connection to `127.0.0.1:8765` for instant deck synchronization.
- [x] **Genanki File Adapter**: Independent `.apkg` binary file creation for offline usage and fallback.
- [x] **One-Click Windows Launcher**: `start.bat` automating virtual environment setup, frontend build, and browser launch.

---

## 2. Cognitive Science Engine & Quality Auditing

- [x] **Piotr Wozniak's 20 Rules Integration**: Enforces atomic single-concept testing and hierarchical breadcrumbs `[Topic > Subtopic]`.
- [x] **5 Cognitive Archetypes**:
  - Arquetipo A: Cloze Contextualizado
  - Arquetipo B: Matriz de Contraste (Markdown tables)
  - Arquetipo C: Pregunta Atómica (< 15 palabras)
  - Arquetipo D: Tarjeta Radar (Índice estructural)
  - Arquetipo E: Mini-Escenario / Caso Aplicado
- [x] **Deterministic Cloze Sanitizer (`ClozeSanitizer`)**:
  - Auto-repairs bare clozes (`{{term}}` $\to$ `{{c1::term}}`).
  - Cleans triple braces and normalizes discontinuous cloze indexes.
- [x] **Neurocognitive Auditor (`CognitiveAuditorService`)**:
  - Automatically decouples multi-cloze notes into independent **Sister Cards** (`hermana-1-de-2`).
  - Absorbs leading grammatical articles to avoid morphological priming (`la {{c1::mitosis}}` $\to$ `{{c1::la mitosis}}`).
  - Injects mandatory `⚠️ Trampa frecuente / Error común:` sections for hypercorrection.
- [x] **Interactive Cognitive Audit Modal**: Full UI breakdown with Deck Quality Score (0–100), repair stats, and diff views.

---

## 3. Scaffolding Pipeline & Pre-Flight Cockpit

- [x] **Pre-Flight Diagnostic Inspection**:
  - Evaluates material self-sufficiency score (0–100%) and generates pedagogical verdict.
  - Detects missing foundational prerequisites to prevent cognitive gaps.
- [x] **Asynchronous Prerequisite Enrichment**: Background research and synthesis of prior concepts.
- [x] **Dynamic Cognitive Density (`deep_card_count = 0` / Auto IA)**:
  - Calculates between 3 and 8 atomic cards per prerequisite sub-event based on conceptual complexity.
- [x] **Resilient Scaffolding Banner (`ActiveStudyPlanBanner`)**:
  - Persistent plan state across API demand spikes (`sessionStorage`).
  - Clear state transitions (`✓ En Mazo` and `✓ Plan Generado y en Pantalla`).

---

## 4. Multi-Engine AI Support (Cloud + Local GPU)

- [x] **Google Gemini Cloud Adapter (`google-genai` SDK)**:
  - Primary tier with `gemini-3.8-flash` and Structured Outputs.
  - Exponential backoff with jitter for HTTP 503 and 429 resilience.
- [x] **Resilient Cascade Adapter (`ResilientCascadeAdapter`)**:
  - Multi-provider fallback cascade: Gemini 3.8 Flash $\to$ NVIDIA NIM $\to$ Groq $\to$ OpenRouter Free.
  - In-memory circuit breakers preventing cascade hangs on failing providers.
- [x] **Local Ollama Adapter (AMD GPU)**:
  - Integrated with `http://127.0.0.1:11434` for 100% offline, zero-token generation.
  - Verified models: `llama3.2:3b` and `qwen2.5:14b`.
- [x] **Local Multimodal Vision Support**:
  - Image base64 conversion and visual analysis via `qwen2.5vl:7b` for offline diagram/slide processing.
- [x] **Header Engine Switcher**:
  - Interactive UI toggle `[ ☁️ Cloud (Gemini) | 🖥️ Local (GPU) ]` with live daemon status and model picker.

---

## 5. Deck Studio & Curricular Governance

- [x] **Deck Studio Hub (`DeckStudioModal.tsx`)**: Centralized multi-tab curricular workspace for deck auditing and expansion.
- [x] **Concept Precedence DAG (`deck_dag_service.py` + `CognitivePrecedenceDAG.tsx`)**:
  - Interactive SVG rendering with NetworkX cycle resolution, Hasse transitive reduction, and orphan recall.
- [x] **Cognitive Debt Matrix**: Batch quality auditing and bad card inspection.
- [x] **Spherical K-Means Clustering (`clustering.py`)**: Unsupervised cosine vector clustering for deck partitioning and thematic clusters.
- [x] **Socratic Diagnostic Interview (`deck_interview_service.py`)**:
  - Multi-turn diagnostic Q&A synthesizing an immutable `LearningPlanContract` (Bloom depth, exclusion boundaries, gap strategy).
- [x] **In-Situ FSRS Note Refactor (`RefactorNoteModal.tsx`)**:
  - Updates note fields in-place via AnkiConnect, strictly preserving `note_id`, review intervals, and FSRS memory state.
- [x] **Surgical Cluster Sanitation (`ClusterSanitationModal.tsx`)**:
  - Supervised turn-by-turn cockpit (`replaceNoteTransactionally`) and batch mode with zero-data-loss rollback.
  - Mutual negative boundaries injection to prevent cross-concept contamination.
- [x] **Topological Deck Expansion (`deck_expansion_service.py`)**:
  - Identifies orphan prerequisite gaps and suggests targeted atomic anchor cards.
- [x] **Exam Blueprint Alignment (`exam_blueprint_service.py`)**:
  - Extracts official certification guide PDFs (`pypdf`) and semantically aligns them with deck contents.

---

## 6. Certified Quality Audits (100% Passing)

- [x] **Backend Level 1 (Topological DAG)**: 6/6 tests passing (cycle breaking, transitive reduction, orphan recall).
- [x] **Backend Level 2 (Cognitive Linters)**: 7/7 tests passing (cloze auto-repair, article absorption, Wozniak Rule 4 sister cards).
- [x] **Backend Level 3 (Sanitizer Safety & Fault Injection)**: 6/6 tests passing (zero deletion on timeout, transactional rollback).
- [x] **Backend Level 4 (Pedagogical LLM-as-a-Judge / G-Eval)**: 6/6 tests passing (atomicity gate, context independence, faithfulness).
- [x] **Backend Level 5 (Socratic Adversarial Red Teaming)**: 5/5 tests passing (sycophancy resistance, concept bleed defense).
- [x] **Backend Level 6 (Schemathesis Property-Based API Fuzzing)**: 3/3 tests passing (~160+ randomized input runs, 0 HTTP 500 errors).
- [x] **Frontend Levels F1 to F6**:
  - F1 Type Integrity & DTO Parity
  - F2 Performance & Bundle Optimization (code-split chunks)
  - F3 Cognitive Ergonomics & WCAG AA Contrast / ARIA
  - F4 Specialized Rendering (KaTeX math, dynamic Cloze, multimedia)
  - F5 Resilience & Error Boundaries
  - F6 Playwright E2E Integration Suite (Flows A, B, C, D)

---

## 7. Active Backlog (Upcoming Capabilities)

- [ ] **Unified Sanitation Workflow Purge**:
  - Remove orphan `isSanitationMode` and `sanitationQueue` in `App.tsx`.
  - Deprecate legacy "Tarjeta de Anki" tab in `ContentDropzone.tsx`, funneling note curation into Deck Studio.
  - Refactor `flow_b_surgical_sanitation.spec.ts` to navigate via UI instead of synthetic `sessionStorage` (see [`docs/SANITATION_WORKFLOW_AUDIT.md`](file:///c:/Users/Manolo/Desktop/Antigravity%20Proyects/Anki%20Flashcards%20IA/docs/SANITATION_WORKFLOW_AUDIT.md)).
- [ ] **Direct Deck Stats Dashboard**:
  - Retrieve real-time learning retention curves and due cards directly from Anki via AnkiConnect.
- [ ] **CSV / TSV Export**:
  - Secondary export format for users with older mobile Anki versions or alternative flashcard apps.
- [ ] **Batch PDF Chapter Splitter**:
  - Automatic partitioning of long textbook chapters into discrete study sessions.
- [ ] **Custom FSRS Retention Target**:
  - UI setting to calibrate card density for specific retention targets (e.g., 85% vs 90%).
