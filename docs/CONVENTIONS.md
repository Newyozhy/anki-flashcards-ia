# AnkiCraft AI - Conventions & Rules

> Coding standards, architectural guardrails, allowed libraries, testing conventions, and cognitive science specifications.

---

## 1. Architectural Guardrails (Non-Negotiable)

1. **Strict Hexagonal Isolation**:
   - The **Domain** (`backend/app/domain/`) and **Services** (`backend/app/services/`) must depend on abstract **Ports** (`backend/app/ports/`) via Python's `Protocol` or abstract base classes.
   - Controllers/Routes (`backend/app/api/`) only interact with use cases and services via Dependency Injection (`backend/app/api/deps.py`).
   - *Technical Debt Note*: Services currently interact with `DeckKnowledgeStore` in `adapters/db/`. New service integrations should prioritize extracting an `IDeckKnowledgeStorePort` to maintain full hexagonal decoupling.
2. **Deterministic Fallbacks & Graceful Degradation**:
   - Any external integration (AnkiConnect, Gemini API, Ollama) must include a fallback or circuit breaker mechanism:
     - AnkiConnect unavailable $\to$ Fall back to standalone `.apkg` download.
     - Gemini API 503 / 429 quota $\to$ Resilient multi-tier cascade (Tier 1 Gemini $\to$ Tier 2 NVIDIA NIM $\to$ Tier 3 Groq $\to$ Tier 4 OpenRouter) with circuit breakers.
     - Ollama daemon offline $\to$ Report clean status via `OllamaStatus` without crashing the application.
3. **Data Loss Prevention Invariant**:
   - In all note replacement, refactoring, and cluster sanitation operations: never delete or mutate original notes before verifying that the replacement notes have been successfully created and validated in Anki Desktop.

---

## 2. Backend Conventions (Python 3.14 + FastAPI + Pydantic v2)

- **Type Annotations**: 100% type coverage required for all function arguments, return types, and class attributes.
- **Pydantic v2**:
  - Use `model_config = ConfigDict(...)` instead of Pydantic v1 `class Config:`.
  - Use `Field(..., description="...")` for clear API schema generation.
- **Error Handling**:
  - Never allow raw tracebacks to reach the user. Map internal errors to descriptive, pedagogically helpful messages in `_format_friendly_error()`.
  - Handle transient HTTP errors with retry loops before returning 500.
- **Code Language**:
  - All source code, docstrings, identifiers, comments, and unit tests must be written in **English**.
  - Generated learning flashcards default to Spanish (`es`) or the user's selected language.
- **Approved Domain Libraries**:
  - `NetworkX` for concept precedence DAGs, topological sorting, and cycle resolution.
  - `pypdf` for syllabus / exam blueprint PDF extraction.
  - `google-genai` SDK for Gemini 3.8 Flash and embeddings (`text-embedding-004`).

---

## 3. Frontend Conventions (React 19 + TypeScript + Vite + Tailwind)

- **Language & Naming**:
  - All React components, variables, functions, and interfaces must be written in **English** (e.g., `DeckStudioModal`, `handleGenerateApproved`).
  - User-facing UI copy, alerts, and tooltips follow clear, professional Spanish.
- **Component Pattern**:
  - Container-Presentational separation: State orchestration in `App.tsx` or modal containers; presentational components receive typed props.
  - Sub-sections of large interfaces must be broken down into dedicated modular components (e.g. `CognitivePrecedenceDAG.tsx`, `RefactorNoteModal.tsx`, `ClusterSanitationModal.tsx`).
- **Styling & Accessibility**:
  - Tailwind CSS exclusively (no inline CSS styles or `.css` module files unless strictly required for third-party widgets like KaTeX).
  - Dark obsidian / slate theme (`#080c14`), glassmorphism with `backdrop-blur-md`.
  - Strictly enforce WCAG AA contrast ratios ($\ge 4.5:1$) and keyboard navigation (ARIA dialog semantics and Escape key dismissals).
- **State Integrity**:
  - Critical transient plans (such as the pre-flight diagnostic report) must be mirrored to `sessionStorage` so API hiccups or network drops never erase user work.

---

## 4. Cognitive Science & Anki Standards

All generated flashcards must strictly satisfy the following rules:

1. **Hierarchical Breadcrumbs**: Every question/front must begin with bracketed structural context: `[Topic > Subtopic]`.
2. **Atomicity (Minimum Information Principle - Piotr Wozniak's Rule 4)**:
   - A single flashcard must test exactly **one** atomic concept, relationship, or blank.
   - If a source sentence contains multiple items to memorize, they must be converted into independent sister cards (`hermana-1-de-2`, `hermana-2-de-2`).
3. **Cloze Syntax Strictness**:
   - Always use `{{c1::answer}}`. Never omit the ordinal prefix.
   - Articles must be absorbed into the cloze (`{{c1::la mitosis}}`, NOT `la {{c1::mitosis}}`) to avoid grammatical priming.
4. **Hypercorrection Cue (Metcalfe Effect)**:
   - The `explanation` field must include `⚠️ Trampa frecuente / Error común:` highlighting common student misconceptions.
5. **Length Constraints**:
   - Basic questions should be $< 15$ words. Back answers should be atomic phrases or concise definitions, avoiding multi-paragraph blocks.

---

## 5. Testing & Verification Standards

Before completing any task, ensure zero regressions across the three test suites:

1. **Backend Verification (152 tests total)**:
   ```powershell
   cd backend
   # Regression suite (119 tests)
   .\.venv\Scripts\python -m pytest tests -q

   # Audits and Fuzzing suite (33 tests)
   .\.venv\Scripts\python -m pytest audits -v

   # Full backend test suite (152 tests)
   .\.venv\Scripts\python -m pytest tests audits -q
   ```
   All 152 tests must pass with zero failures.

2. **Frontend Quality & Build**:
   ```powershell
   cd frontend
   # Strict TypeScript type check
   npx tsc -b

   # Oxlint static analysis (116 rules)
   npm run lint

   # Production build verification
   npm run build
   ```
   Must pass with 0 errors and 0 warnings.

3. **Frontend Playwright E2E Integration**:
   ```powershell
   cd frontend
   npm run test:e2e
   ```
   All 6 integration flows must pass green.
