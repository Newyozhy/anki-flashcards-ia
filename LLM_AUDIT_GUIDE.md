# LLM Audit Guide for Gemini Web

> **Welcome Auditor**: This repository is **AnkiCraft AI** (v2.1.0), an advanced knowledge engineering, spaced repetition (SRS), and curriculum optimization platform.

---

## 1. Quick Orientation & Map

* **Master Index & Traceability Matrix**: [`docs/INDEX.md`](docs/INDEX.md)  
  *Contains structured YAML frontmatter, verified test metrics, and a feature-to-code mapping matrix connecting every business capability to its backend service, frontend component, API endpoint, and test suite.*
* **Architecture Guide**: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)  
  *Hexagonal architecture (Ports & Adapters), 4-tier AI cascade, SQLite vector knowledge store, and NetworkX concept DAG.*
* **Coding Standards & Guardrails**: [`docs/CONVENTIONS.md`](docs/CONVENTIONS.md)  
  *Python 3.14 + Pydantic v2 conventions, React 19 + TypeScript rules, and Piotr Wozniak's 20 Rules of Knowledge Formulation.*
* **Quality & Verification Ledger**: [`docs/AUDIT_FINDINGS.md`](docs/AUDIT_FINDINGS.md)  
  *Certified findings across 158 tests: Backend Levels 1–6 (Topological DAG, Linters, Fault Injection, LLM-as-a-Judge, Socratic Red Teaming, Schemathesis API Fuzzing) and Frontend Levels F1–F6.*
* **Current Roadmap**: [`docs/ROADMAP.md`](docs/ROADMAP.md)  
  *Completed capabilities vs active backlog items.*
* **Active Working Topic**: [`docs/SANITATION_WORKFLOW_AUDIT.md`](docs/SANITATION_WORKFLOW_AUDIT.md)  
  *Diagnosis and plan for unifying card/cluster sanitation into Deck Studio and retiring legacy orphan state.*

---

## 2. Key Codebase Entrypoints

* **Backend Main**: `backend/app/main.py`
* **API Endpoints (52 Routes)**: `backend/app/api/routes.py`
* **Domain Models & DTOs**: `backend/app/domain/models.py`
* **Core Services (15 Services)**: `backend/app/services/`
  - `deck_intelligence_service.py`: Vector search, clustering, thematic coverage, duplicate detector.
  - `deck_dag_service.py`: NetworkX concept precedence graph, cycle breaking, transitive reduction.
  - `sanitation_service.py`: In-situ FSRS refactoring, transactional substitution, and cluster sanitation.
  - `deck_interview_service.py`: Socratic diagnostic interview & `LearningPlanContract` synthesizer.
  - `exam_blueprint_service.py`: PDF syllabus alignment.
* **AI Adapters**: `backend/app/adapters/ai/`
  - `gemini_card_generator_adapter.py`: Cloud adapter (Gemini 3.8 Flash, Structured Outputs).
  - `resilient_cascade_adapter.py`: 4-tier provider cascade with circuit breakers.
  - `ollama_adapter.py`: Local AMD GPU adapter (text and multimodal vision with `qwen2.5vl:7b`).
* **Frontend Main**: `frontend/src/App.tsx`
* **Deck Studio Modal**: `frontend/src/components/DeckStudioModal.tsx`
* **Test Suites**:
  - `backend/tests/`: 119 Unit and integration regression tests.
  - `backend/audits/`: 33 Quality, Topological, LLM-as-a-Judge, and Schemathesis fuzzing tests.
  - `frontend/e2e/`: 6 Playwright integration tests (Flows A, B, C, D).

---

## 3. Recommended Audit Prompts for Gemini Web

When uploading this zip to Gemini Web, you can prompt it with:

1. **System Health & Architecture Review**:
   > *"I have uploaded the source code of AnkiCraft AI. Please review `docs/INDEX.md` and `docs/ARCHITECTURE.md`. Evaluate the hexagonal decoupling between the domain services and external adapters, and verify if the data loss prevention invariants in `sanitation_service.py` are sound."*

2. **Neurocognitive & Pedagogical Integrity**:
   > *"Analyze the implementation of Piotr Wozniak's Minimum Information Principle across `backend/app/core/cloze_sanitizer.py`, `backend/app/services/cognitive_auditor_service.py`, and `backend/audits/test_l2_cognitive_linters.py`. Are edge cases such as nested LaTeX clozes and grammatical priming properly handled?"*

3. **Curricular DAG & Topological Optimization**:
   > *"Inspect `backend/app/services/deck_dag_service.py` and `frontend/src/components/CognitivePrecedenceDAG.tsx`. How does the system handle multi-cycle feedback loops and transitive reduction on concept graphs? Suggest any mathematical or performance optimizations."*

4. **Frontend Architecture & Accessibility**:
   > *"Review `frontend/src/App.tsx` and `frontend/src/components/DeckStudioModal.tsx`. Assess component decomposition, performance optimization (lazy-loaded chunks), and WCAG AA accessibility compliance."*
