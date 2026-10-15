# AnkiCraft AI - Architecture Guide

> High-level architecture, design patterns, domain boundaries, and technical specifications for AnkiCraft AI.

---

## 1. Architectural Philosophy: Hexagonal (Ports & Adapters)

AnkiCraft AI strictly adheres to **Hexagonal Architecture (Ports and Adapters)** and **Clean Code Principles**.
The core pedagogical, cognitive, and curricular domain logic is decoupled from external infrastructure (such as LLM cloud providers, local GPU daemons, vector databases, and Anki Desktop protocols).

```
                      ┌──────────────────────────────────────────────┐
                      │          Frontend Layer (React 19)           │
                      │   - Vite 6 + Tailwind CSS v4                 │
                      │   - Dual Engine UI (Cloud / Local GPU)       │
                      │   - Pre-flight Cockpit + Cognitive Audit     │
                      │   - Deck Studio Hub (DAG, Debt, Expansion)   │
                      └──────────────────────┬───────────────────────┘
                                             │ HTTP / REST (52 Endpoints)
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │          FastAPI Controllers (Inbound)       │
                      │   - Dependency Injection (deps.py)           │
                      │   - Request validation with Pydantic v2      │
                      └──────────────────────┬───────────────────────┘
                                             │
                                             ▼
                      ┌──────────────────────────────────────────────┐
                      │              Domain & Services               │
                      │   - Card Generation & Inspection Services    │
                      │   - Cognitive Auditor & Cloze Sanitizer      │
                      │   - Deck Intelligence & Precedence DAG       │
                      │   - Socratic Interview & Learning Contract   │
                      │   - Surgical Sanitation & Cluster Remediation│
                      │   - Exam Blueprint & Topological Expansion   │
                      └──────┬───────────────┬───────────────┬───────┘
                             │               │               │
                 Port (Call) │   Port (Call) │   Port (Call) │ Internal DB
                             ▼               ▼               ▼
             ┌──────────────────────┐ ┌──────────────┐ ┌──────────────────┐
             │  ICardGeneratorPort  │ │IAnkiBridgePort│ │ IEmbeddingPort   │
             └──────────┬───────────┘ └──────┬───────┘ └────────┬─────────┘
                        │ Adapters           │ Adapters         │ Adapters
         ┌──────────────┴──────────────┐     │                  │
         ▼                             ▼     ▼                  ▼
┌─────────────────────────┐ ┌──────────────┐ ┌─────────────┐ ┌────────────┐
│ ResilientCascadeAdapter │ │ Ollama Local │ │ AnkiConnect │ │ Gemini     │
│ - Tier 1: Gemini 3.8 Fl │ │ - AMD GPU    │ │ - JSON-RPC  │ │ Embedding  │
│ - Tier 2: NVIDIA NIM    │ │   port 11434 │ │   port 8765 │ │ Adapter    │
│ - Tier 3: Groq          │ │ - Multimodal │ │ - Sync / FSRS││ - text-     │
│ - Tier 4: OpenRouter    │ │   qwen2.5vl  │ │Genanki File │ │   embed-   │
│ - Circuit Breakers      │ │ - llama3.2   │ │ - .apkg pkg │ │   ding-004 │
└─────────────────────────┘ └──────────────┘ └─────────────┘ └────────────┘
                                                            ▲
                                                            │ SQLite
                                             ┌──────────────┴─────────────┐
                                             │ DeckKnowledgeStore (DB)    │
                                             │ - SQLite Vector Storage    │
                                             │ - Cosine Similarity Search │
                                             │ - DAG Concept Graph Tables │
                                             └────────────────────────────┘
```

---

## 2. Directory Structure and Boundaries

```
backend/
├── app/
│   ├── adapters/
│   │   ├── ai/
│   │   │   ├── gemini_card_generator_adapter.py   # Primary Google GenAI adapter (Gemini 3.8 Flash)
│   │   │   ├── gemini_embedding_adapter.py        # Vector embedding adapter with 429 quota backoff
│   │   │   ├── ollama_adapter.py                  # Local LLM adapter (Ollama on AMD GPU, multimodal)
│   │   │   └── resilient_cascade_adapter.py       # 4-tier provider cascade with circuit breakers
│   │   ├── anki/
│   │   │   ├── anki_connect_adapter.py            # JSON-RPC bridge to Anki Desktop (port 8765)
│   │   │   └── genanki_file_adapter.py            # Independent .apkg binary package creator
│   │   └── db/
│   │       └── deck_knowledge_store.py            # SQLite vector repository, cosine search, DAG tables
│   ├── api/
│   │   ├── deps.py                                # Dependency injection factories
│   │   └── routes.py                              # 52 REST API endpoints across all workflows
│   ├── core/
│   │   ├── cloze_sanitizer.py                     # Deterministic Cloze syntax linter and repairer
│   │   ├── clustering.py                          # Spherical K-Means & optimal K determination
│   │   ├── config.py                              # Settings & model constants from environment
│   │   ├── formatting.py                          # Anki HTML, KaTeX markup, and math formatting
│   │   └── logging_config.py                      # In-memory circular log buffer for UI inspection
│   ├── domain/
│   │   └── models.py                              # Core Pydantic v2 schemas and domain models
│   ├── ports/
│   │   ├── anki_bridge_port.py                    # Protocol interface for Anki operations
│   │   ├── card_generator_port.py                 # Protocol interface for AI card generation
│   │   └── embedding_port.py                      # Protocol interface for vector embeddings
│   ├── services/
│   │   ├── cognitive_auditor_service.py           # Neurocognitive quality auditor & sister card decoupler
│   │   ├── deck_dag_service.py                    # NetworkX concept precedence DAG & topological sort
│   │   ├── deck_expansion_service.py              # Phase 4 topological expansion on orphan gaps
│   │   ├── deck_intelligence_service.py           # Deck indexing, thematic coverage, duplicate detector
│   │   ├── deck_interview_service.py              # Socratic interview & LearningPlanContract synthesizer
│   │   ├── exam_blueprint_service.py              # Syllabus PDF parsing & exam alignment engine
│   │   ├── export_deck_service.py                 # Deck export orchestration with fallback
│   │   ├── generate_cards_service.py              # Card generation pipeline with anti-redundancy
│   │   ├── inspect_material_service.py            # Pre-flight diagnostic & prerequisite enrichment
│   │   ├── ontology_extractor_service.py          # Bottom-up proposition & concept extraction
│   │   ├── pedagogical_discriminator_service.py   # Multi-level anti-redundancy & facet discrimination
│   │   ├── pedagogical_judge_service.py           # G-Eval LLM-as-a-Judge evaluation engine
│   │   ├── sanitation_service.py                  # In-situ refactor & transactional cluster sanitation
│   │   ├── semantic_auditor_agent.py              # Quality linter enforcing Wozniak & Metcalfe rules
│   │   └── socratic_red_teaming_service.py        # Multi-turn adversarial red teaming engine
│   └── main.py                                    # FastAPI entrypoint, lifespan, CORS, and middleware
├── audits/                                        # 33 Quality & Fuzzing audit tests (Levels 1 to 6)
└── tests/                                         # 119 Unit and integration regression tests
```

---

## 3. Key Subsystems and Patterns

### A. Dual Engine AI Infrastructure & Resilient Cascade
1. **Google Gemini Cloud (`GeminiCardGeneratorAdapter`)**:
   - Primary tier: `gemini-3.8-flash` utilizing the `google-genai` SDK with Structured Outputs (`response_schema`).
   - Fallback tier: `gemini-3.5-flash-lite` for lower quota consumption under burst traffic.
   - Jittered exponential backoff handles transient HTTP 503 or 429 quota spikes.
2. **Resilient Cascade Adapter (`ResilientCascadeAdapter`)**:
   - Implements a resilient 4-tier provider cascade with in-memory circuit breakers:
     - **Tier 1**: Google Gemini 3.8 Flash (Cloud)
     - **Tier 2**: NVIDIA NIM (`meta/llama-3.2-90b-vision-instruct`)
     - **Tier 3**: Groq (`qwen/qwen3.8-27b`)
     - **Tier 4**: OpenRouter Free (`openrouter/free`)
   - Automatically trips and skips failing providers after consecutive failures.
3. **Local Ollama on AMD GPU (`OllamaCardGeneratorAdapter`)**:
   - Connects to `http://127.0.0.1:11434` for 100% offline, zero-token local generation.
   - Multimodal support: extracts and encodes image data into base64 for vision models like `qwen2.5vl:7b`.
   - Text models: `llama3.2:3b` and `qwen2.5:14b`.

### B. Cognitive Science Engine & Neurocognitive Linters
- **Minimum Information Principle (Piotr Wozniak's Rule 4)**:
  Every flashcard tests strictly one atomic cognitive proposition.
- **Sister Card Decoupling (`CognitiveAuditorService`)**:
  When an LLM generates a card with multiple clozes, the auditor automatically duplicates the card into independent sister cards (`hermana-1-de-2`, `hermana-2-de-2`). Each sister card isolates one term while rendering sibling terms as plain structural context.
- **Grammatical Anti-Priming (Article Absorption)**:
  Eliminates morphological hints by absorbing articles into cloze brackets (`la {{c1::mitosis}}` $\to$ `{{c1::la mitosis}}`).
- **Hypercorrection Effect (Metcalfe)**:
  Enforces mandatory `⚠️ Trampa frecuente / Error común:` sections in card explanations.
- **Deterministic Cloze Sanitizer (`ClozeSanitizer`)**:
  Deterministically fixes bare clozes (`{{term}}` $\to$ `{{c1::term}}`), strips malformed triple braces, and normalizes non-contiguous cloze indices.

### C. Curriculum Graph & Precedence DAG (`DeckDAGService`)
- Uses **NetworkX** to construct a directed acyclic graph (DAG) of all concepts within a deck.
- **Cycle Breaking**: Automatically breaks multi-cycle feedback loops using greedy feedback arc set heuristics in $< 3$ ms while preserving 100% of concept nodes.
- **Hasse Transitive Reduction**: Removes redundant bypass edges on dense graphs while maintaining reachability.
- **Orphan Recall**: Identifies ungrounded foundational concepts and surfaces them as prerequisite gaps sorted by topological depth.

### D. Surgical Deck Sanitizer & Transactional Rollback (`SanitationService`)
- **Level 1 (In-situ Refactor)**: Modifies note fields directly via AnkiConnect's `update_note_fields`, strictly preserving `note_id`, review intervals, and FSRS memory state.
- **Level 2 (Cluster Sanitation)**:
  - Supports supervised turn-by-turn cockpit and batch cluster remediation.
  - **Zero Data Loss Guarantee**: Deletes obsolete monolithic notes only after verifying successful creation of replacement atomic cards. Reverts state immediately upon API failure.
  - **Negative Boundaries Injection**: Automatically injects sibling note descriptors into `neighbor_concepts` and negative prompt directives (`PROHIBIDO evaluar conceptos vecinos: ...`) to eliminate concept bleed.

### E. Diagnostic Interview & Learning Contract (`DeckInterviewService`)
- Conducts an interactive Socratic interview analyzing deck scope, learner background, and target exam.
- Synthesizes an immutable `LearningPlanContract` defining Bloom taxonomy depth, explicit exclusion boundaries, and prerequisite gap strategies.

---

## 4. Verification Baseline

The architecture is continuously verified across three testing tiers:
* **Backend Regression**: 119 tests in `backend/tests/` (100% pass).
* **Backend Quality & Audits**: 33 tests in `backend/audits/` (Levels 1–6, 100% pass).
* **Frontend E2E**: 6 Playwright tests in `frontend/e2e/` (Flows A, B, C, D, 100% pass).
