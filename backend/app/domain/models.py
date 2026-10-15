from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4
from pydantic import BaseModel, Field, ConfigDict


class CardType(str, Enum):
    """Supported Anki card note types."""
    BASIC = "basic"
    CLOZE = "cloze"
    REVERSE = "reverse"


class Flashcard(BaseModel):
    """Represents a single flashcard entity."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    card_type: CardType = CardType.BASIC
    archetype: Optional[str] = Field(default=None, description="Cognitive archetype (A, B, C, D)")
    front: str = Field(..., description="Front side content, question, or cloze prompt with breadcrumbs")
    back: str = Field(default="", description="Back side content or answer")
    tags: List[str] = Field(default_factory=list, description="Categorization tags for Anki")
    explanation: Optional[str] = Field(default=None, description="Pedagogical extra field: diagram, contrast table, mnemonic")
    justification: Optional[str] = Field(
        default=None,
        description="Which atomic fact of the source material this card covers and why it is not redundant",
    )
    source_image_index: Optional[int] = Field(
        default=None,
        description="1-based index of the source image this card was derived from (multimodal sanitation)",
    )
    source_image: Optional[str] = Field(
        default=None,
        description="Anki media filename inherited by this card as passive visual support in the Extra field",
    )
    source_images: List[str] = Field(
        default_factory=list,
        description="Anki media filenames inherited by this card as visual support in the Extra field",
    )


class Deck(BaseModel):
    """Represents a collection of flashcards grouped under a deck name."""
    name: str = Field(default="Default", description="Anki deck name, supports subdecks with '::'")
    cards: List[Flashcard] = Field(default_factory=list)


class GenerationSourceType(str, Enum):
    """Type of input educational content."""
    TEXT = "text"
    IMAGE = "image"
    PDF = "pdf"


class GenerationOptions(BaseModel):
    """User preferences for flashcard generation."""
    card_type: CardType = CardType.BASIC
    target_count: int = Field(default=0, ge=0, le=100, description="0 indicates Auto-calculated by AI density")
    difficulty_level: str = Field(default="intermediate")
    language: str = Field(default="es")
    deck_name: str = Field(default="General")
    custom_instructions: Optional[str] = None
    prerequisites_context: Optional[str] = Field(default=None, description="Enriched foundational context to prevent isolated concepts")
    selected_themes: Optional[List[str]] = Field(default=None, description="Specific subtopics approved by the user")
    ai_provider: str = Field(default="gemini", description="'gemini' or 'ollama'")
    local_model: str = Field(default="qwen2.5:14b", description="Model name when using local Ollama")
    neighbor_concepts: Optional[List[str]] = Field(
        default=None,
        description="Sibling or boundary concepts from the DAG that must not be redefined to prevent redundant flashcards",
    )
    source_note_id: Optional[int] = Field(
        default=None,
        description="Original note ID when performing sanitation or scoped refactoring",
    )
    target_concept: Optional[str] = Field(
        default=None,
        description="Core concept name being targeted, used to query the DAG for curriculum precedence and depth",
    )
    media_filenames: Optional[List[str]] = Field(
        default=None,
        description="Filenames of images in source note for dual coding diagram inheritance",
    )


class PrerequisiteMatchStatus(str, Enum):
    """Semantic match verdict status against existing Anki deck."""
    DOMINATED = "dominated"
    COGNITIVE_DEBT = "cognitive_debt"
    COMPLEMENTARY = "complementary"
    GAP = "gap"


class PrerequisiteMatch(BaseModel):
    """Semantic analysis of prerequisite or theme against existing cards in the target Anki deck."""
    concept: str
    status: PrerequisiteMatchStatus
    confidence: float = 0.0
    matched_note_id: Optional[int] = None
    matched_note_front: Optional[str] = None
    similarity_score: float = 0.0
    verdict_explanation: str
    suggested_action: str = Field(
        default="create_new",
        description="'keep_existing', 'refactor_existing', 'study_complementary', or 'create_new'"
    )
    media_files: List[str] = Field(default_factory=list, description="Filenames of images embedded in the matched note")
    should_replace: bool = Field(default=True, description="Whether the user wants to delete this obsolete card from Anki upon export")
    quality_status: Optional[str] = Field(default=None, description="'optimal', 'bad', 'preevaluated', or 'unreviewed'")
    quality_score: Optional[float] = Field(default=None, description="Quality score from 0.0 to 1.0")
    quality_feedback: Optional[str] = Field(default=None, description="Pedagogical diagnosis of quality")
    violation_type: Optional[str] = Field(default=None, description="Hard-gate violation type if bad")


class CoreTheme(BaseModel):
    """A distinct cognitive subtopic identified in the study material."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(..., description="Short name of the subtopic")
    description: str = Field(..., description="Key concept or relationship explored")
    recommended_cards: int = Field(default=2, ge=0, le=15, description="Recommended atomic card count for this subtopic")
    selected: bool = Field(default=True, description="Whether the user approved this theme for generation")
    match_info: Optional[PrerequisiteMatch] = Field(
        default=None,
        description="Semantic deck intelligence verdict comparing this core theme to existing deck notes"
    )
    associated_diagrams: List[str] = Field(
        default_factory=list,
        description="Names of images/diagrams from the source note associated with this subtopic"
    )
    diagram_roles: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of image filename -> brief explanation of what it illustrates for this theme"
    )

    @property
    def theme(self) -> str:
        return self.title


CoreThemeItem = CoreTheme


class PrerequisiteItem(BaseModel):
    """Foundational knowledge required to understand the material without cognitive gaps."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    concept: str = Field(..., description="Name of the prior concept")
    reason: str = Field(..., description="Why this prior concept is necessary to avoid confusion")
    is_covered_in_text: bool = Field(default=False, description="True if already adequately explained in the text, False if missing")
    search_query: str = Field(..., description="Search query to research/synthesize this prerequisite")
    selected: bool = Field(default=True, description="Whether the user wants to enrich and generate base cards for this")
    enriched_summary: Optional[str] = Field(default=None, description="Synthesized foundational summary once researched")
    mode: str = Field(default="anchor", description="'anchor' (1 card) or 'deep_dive' (auto or multi-card)")
    deep_card_count: int = Field(default=0, ge=0, le=12, description="Target card count if mode is deep_dive (0 = Auto por IA según densidad)")
    recommended_deep_cards: int = Field(default=3, ge=2, le=8, description="AI-calculated optimal card count when mode is deep_dive")
    atomic_blueprint: List[str] = Field(default_factory=list, description="Ordered list of irreducible atomic learning objectives for this prerequisite")
    match_info: Optional[PrerequisiteMatch] = Field(
        default=None,
        description="Semantic deck intelligence verdict comparing this prerequisite to existing deck notes"
    )


class StudyPlanInspection(BaseModel):
    """Pedagogical pre-flight diagnostic report before flashcard creation."""
    topic_name: str = Field(..., description="Overall title or subject of the analyzed material")
    self_sufficiency_score: int = Field(..., ge=0, le=100, description="Score 0-100 indicating how self-contained the material is")
    self_sufficiency_verdict: str = Field(..., description="Direct pedagogical explanation of missing foundations or completeness")
    core_themes: List[CoreTheme] = Field(default_factory=list, description="List of detected subtopics")
    prerequisites: List[PrerequisiteItem] = Field(default_factory=list, description="Foundational concepts required")
    suggested_total_cards: int = Field(..., ge=1, description="Recommended total flashcards according to the Minimum Information Principle")
    obsolete_note_ids: List[int] = Field(default_factory=list, description="List of note IDs marked to be superseded and deleted")
    inherited_media_files: List[str] = Field(default_factory=list, description="Media files inherited from superseded debt notes")
    source_note_id: Optional[int] = Field(default=None, description="ID of the original Anki note if inspected from a deck card")
    source_text: Optional[str] = Field(default=None, description="Original raw educational text inspected")
    provider_used: Optional[str] = Field(default="gemini", description="Actual provider that fulfilled the plan ('gemini', 'nvidia', 'groq', 'openrouter')")
    model_used: Optional[str] = Field(default=None, description="Exact model name used for inspection")
    fallback_occurred: bool = Field(default=False, description="True if primary provider failed and fallback was used")
    fallback_chain: List[str] = Field(default_factory=list, description="Log of failed provider attempts if any")


class InspectMaterialRequest(BaseModel):
    """Request payload to diagnose and plan study material."""
    text: str
    options: GenerationOptions = Field(default_factory=GenerationOptions)
    source_note_id: Optional[int] = None
    media_files: List[str] = Field(default_factory=list)


class EnrichPrerequisiteRequest(BaseModel):
    """Request payload to asynchronously enrich a single prerequisite concept."""
    concept: str
    search_query: str
    context_topic: Optional[str] = None
    ai_provider: str = Field(default="gemini")
    local_model: str = Field(default="llama3.2:3b")


class EnrichedConceptResult(BaseModel):
    """Result of asynchronous prerequisite enrichment."""
    concept: str
    summary: str
    key_takeaway: str
    recommended_deep_cards: int = Field(default=3, ge=2, le=8, description="Exact count of atomic cards required to cover the blueprint")
    atomic_blueprint: List[str] = Field(default_factory=list, description="List of 3 to 6 irreducible atomic sub-objectives")


class ExportRequest(BaseModel):
    """Payload to export cards to Anki or generate .apkg."""
    deck_name: str
    cards: List[Flashcard]
    obsolete_note_ids: List[int] = Field(default_factory=list, description="IDs of superseded/debt notes to delete from Anki upon successful export")


class ExportResult(BaseModel):
    """Result of the export operation."""
    success: bool
    cards_exported_count: int
    destination: str  # "anki_connect" or "apkg"
    message: str
    apkg_file_path: Optional[str] = None
    deleted_notes_count: int = Field(default=0, description="Count of obsolete notes successfully deleted from Anki")
    created_note_ids: List[int] = Field(default_factory=list, description="IDs of newly created Anki notes")


class AnkiStatus(BaseModel):
    """Live status of local AnkiConnect instance."""
    is_connected: bool
    version: Optional[str] = None
    available_decks: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class OllamaStatus(BaseModel):
    """Live status of local Ollama instance, downloaded models and active models in VRAM."""
    is_available: bool
    models: List[str] = Field(default_factory=list)
    running_models: List[str] = Field(default_factory=list, description="Models currently active/loaded in GPU VRAM")
    active_model: str = "qwen2.5:14b"
    error_message: Optional[str] = None


class CognitiveAuditFinding(BaseModel):
    """Specific rule violation or repair recorded by the Cognitive Auditor."""
    rule: str = Field(..., description="Rule code (e.g., 'SYNTAX_CLOZE_REPAIRED', 'ATOMICITY_MULTI_CLOZE_SPLIT')")
    severity: str = Field(default="INFO", description="'INFO', 'WARNING', or 'VIOLATION'")
    message: str = Field(..., description="Natural language pedagogical explanation of the issue")
    original_snippet: Optional[str] = None
    corrected_snippet: Optional[str] = None
    auto_fixed: bool = True
    suggested_replacement: Optional[str] = None


class CardAuditResult(BaseModel):
    """Audit evaluation for an individual flashcard."""
    card_id: str
    card_front_preview: str
    passed: bool
    score: int = Field(ge=0, le=100)
    findings: List[CognitiveAuditFinding] = Field(default_factory=list)
    sister_cards_count: int = Field(default=1, description="Number of atomic sister cards created from this note")


class DeckAuditReport(BaseModel):
    """Full cognitive audit report for a generated deck."""
    total_cards_audited: int
    total_cards_repaired: int
    total_sister_cards_created: int
    average_quality_score: float
    card_reports: List[CardAuditResult] = Field(default_factory=list)


class GenerateCardsResponse(BaseModel):
    """Unified response containing generated cards and the complete cognitive audit report."""
    cards: List[Flashcard]
    audit_report: Optional[DeckAuditReport] = None
    pedagogical_results: Optional[List[PedagogicalAuditResult]] = None


class GenerationBatchEvent(BaseModel):
    """Event emitted during progressive micro-batch generation."""
    event_type: str = Field(..., description="'batch', 'done', or 'error'")
    batch_label: str = Field(default="")
    cards: List[Flashcard] = Field(default_factory=list)
    current_batch: int = 0
    total_batches: int = 0
    accumulated_count: int = 0
    audit_report: Optional[DeckAuditReport] = None
    message: Optional[str] = None


class DeckNoteRecord(BaseModel):
    """Raw or normalized note extracted directly from Anki Desktop."""
    note_id: int
    deck_name: str
    model_name: str = "Basic"
    card_type: CardType = CardType.BASIC
    front: str
    back: str = ""
    explanation: Optional[str] = None
    clean_text: Optional[str] = None
    clean_front: Optional[str] = None
    clean_back: Optional[str] = None
    clean_explanation: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    raw_fields: Dict[str, str] = Field(default_factory=dict)
    media_files: List[str] = Field(default_factory=list)
    card_ids: List[int] = Field(default_factory=list, description="IDs of physical cards associated with this note in Anki")
    embedding: Optional[List[float]] = None
    quality_status: str = "unreviewed"
    quality_score: Optional[float] = None
    quality_feedback: Optional[str] = None
    audited_at: Optional[str] = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class MatchPrerequisitesRequest(BaseModel):
    """Request to evaluate prerequisite concepts against an existing Anki deck's indexed knowledge."""
    deck_name: str
    prerequisites: List[PrerequisiteItem]
    exclude_note_ids: List[int] = Field(
        default_factory=list,
        description="Note IDs to exclude from search (e.g. source note currently being analyzed)"
    )


class MatchPrerequisitesResponse(BaseModel):
    """Result of semantic matching for prerequisite concepts against existing deck notes."""
    deck_name: str
    matches: List[PrerequisiteMatch]
    total_indexed_notes: int = 0


class SyncDeckIndexResponse(BaseModel):
    """Summary of vector index synchronization for an Anki deck."""
    deck_name: str
    total_notes: int
    newly_indexed: int
    duration_seconds: float


class MatchThemesRequest(BaseModel):
    """Request to evaluate core themes against an existing Anki deck's indexed knowledge."""
    deck_name: str
    themes: List[CoreTheme]
    exclude_note_ids: List[int] = Field(
        default_factory=list,
        description="Note IDs to exclude from search (e.g. source note currently being analyzed)"
    )


class MatchThemesResponse(BaseModel):
    """Result of semantic matching for core themes against existing deck notes."""
    deck_name: str
    matches: List[PrerequisiteMatch]
    total_indexed_notes: int = 0


class MatchStudyPlanRequest(BaseModel):
    """Request to evaluate both prerequisites and core themes against target deck."""
    deck_name: str
    source_note_id: Optional[int] = Field(
        default=None,
        description="ID of source note being analyzed to look up prior ledger entries"
    )
    prerequisites: List[PrerequisiteItem] = Field(default_factory=list)
    core_themes: List[CoreTheme] = Field(default_factory=list)
    exclude_note_ids: List[int] = Field(
        default_factory=list,
        description="Note IDs to exclude from search (e.g. source note currently being analyzed)"
    )


class MatchStudyPlanResponse(BaseModel):
    """Unified result of semantic matching for both prerequisites and themes."""
    deck_name: str
    prerequisite_matches: List[PrerequisiteMatch] = Field(default_factory=list)
    theme_matches: List[PrerequisiteMatch] = Field(default_factory=list)
    total_indexed_notes: int = 0


class RefactorNotePreviewRequest(BaseModel):
    """Request to preview AI-driven in-place refactoring for a note with cognitive debt."""
    note_id: int
    concept_context: Optional[str] = None
    deck_name: Optional[str] = None
    ai_provider: str = Field(default="gemini")
    local_model: Optional[str] = None


class RefactorNotePreviewResponse(BaseModel):
    """Preview comparing original monolithic note with FSRS-compliant atomic refactoring."""
    note_id: int
    deck_name: str
    model_name: str
    original_fields: Dict[str, str]
    refactored_fields: Dict[str, str]
    diff_summary: str
    cognitive_archetype: str


class ApplyRefactorRequest(BaseModel):
    """Request to write refactored fields directly into Anki Desktop and sync knowledge index."""
    note_id: int
    deck_name: str
    fields: Dict[str, str]


class ApplyRefactorResponse(BaseModel):
    """Result of in-place note update in Anki Desktop."""
    success: bool
    note_id: int
    message: str


class CoverageGapStatus(str, Enum):
    """Status lifecycle of an identified thematic coverage gap."""
    PENDING = "pending"
    IN_CURATION = "in_curation"
    RESOLVED = "resolved"


class CoveredFacet(BaseModel):
    """Specific facet of a topic successfully covered by existing deck notes."""
    facet: str
    description: str
    matched_note_ids: List[int] = Field(default_factory=list)
    quality_score: float = 1.0


class OrphanGap(BaseModel):
    """A missing foundational or critical subconcept that leaves an orphan cognitive gap."""
    gap_title: str
    reason: str
    priority: str = "high"
    suggested_front: Optional[str] = None
    status: CoverageGapStatus = CoverageGapStatus.PENDING
    generated_note_id: Optional[int] = None


class TopicCoverageAuditRequest(BaseModel):
    """Request payload to perform a thematic coverage audit over an Anki deck."""
    topic: str
    description: Optional[str] = None
    top_k: int = 10
    save_audit: bool = True


class TopicCoverageAuditResponse(BaseModel):
    """Comprehensive thematic audit report with covered facets and orphan gap checklist."""
    audit_id: Optional[int] = None
    deck_name: str
    topic: str
    coverage_percentage: int = 0
    covered_facets: List[CoveredFacet] = Field(default_factory=list)
    orphan_gaps: List[OrphanGap] = Field(default_factory=list)
    summary_assessment: str = ""
    created_at: str = ""


class UpdateGapStatusRequest(BaseModel):
    """Request to update the resolution status of an orphan gap in a coverage audit."""
    status: CoverageGapStatus
    generated_note_id: Optional[int] = None


class DeckCoverageMapNode(BaseModel):
    """Node in the deck hierarchical coverage DAG."""
    id: str
    label: str
    type: str  # "deck" | "cluster" | "note" | "gap"
    health: str  # "unreviewed" | "bad" | "preevaluated" | "optimal" | "gap"
    note_id: Optional[int] = None
    details: Optional[str] = None
    quality_score: Optional[float] = None
    quality_feedback: Optional[str] = None


class DeckCoverageMapEdge(BaseModel):
    """Directed edge in the deck hierarchical coverage DAG."""
    source: str
    target: str


class DeckCoverageMapResponse(BaseModel):
    """DAG graph representation of deck coverage hierarchy and health metrics."""
    deck_name: str
    total_nodes: int = 0
    nodes: List[DeckCoverageMapNode] = Field(default_factory=list)
    edges: List[DeckCoverageMapEdge] = Field(default_factory=list)
    optimal_count: int = 0
    preevaluated_count: int = 0
    bad_count: int = 0
    debt_count: int = 0
    gap_count: int = 0
    unreviewed_count: int = 0
    broken_count: int = 0
    audited_count: int = 0
    deck_health_percentage: Optional[float] = None


class DeckAuditSummary(BaseModel):
    """Brief metadata summary of a past thematic coverage audit."""
    id: int
    topic: str
    coverage_percentage: int
    total_facets: int
    total_gaps: int
    pending_gaps: int
    created_at: str


class ListDeckAuditsResponse(BaseModel):
    """Collection of past thematic coverage audits for a deck."""
    deck_name: str
    audits: List[DeckAuditSummary] = Field(default_factory=list)


class SemanticClusterItem(BaseModel):
    """Thematic conceptual cluster extracted from vector embeddings."""
    cluster_index: int
    title: str
    scope: str
    note_ids: List[int] = Field(default_factory=list)
    centroid_note_ids: List[int] = Field(default_factory=list)


class DeckClustersResponse(BaseModel):
    """Discovered semantic clusters for an Anki deck."""
    deck_name: str
    clusters: List[SemanticClusterItem] = Field(default_factory=list)


class DiscoverClustersRequest(BaseModel):
    """Options for triggering semantic clustering discovery."""
    model_config = ConfigDict(populate_by_name=True)

    force_refresh: bool = Field(default=False, alias="forceRefresh")
    ai_provider: Optional[str] = Field(default=None, alias="aiProvider")
    local_model: Optional[str] = Field(default=None, alias="localModel")
    k: Optional[int] = None


class AuditQualityBatchRequest(BaseModel):
    """Options for auditing a micro-batch of notes."""
    model_config = ConfigDict(populate_by_name=True)

    batch_size: int = Field(default=5, ge=1, le=25, alias="batchSize")
    note_ids: Optional[List[int]] = Field(default=None, alias="noteIds")
    ai_provider: Optional[str] = Field(default=None, alias="aiProvider")
    local_model: Optional[str] = Field(default=None, alias="localModel")


class NoteQualityAuditItem(BaseModel):
    """Audit result for an individual flashcard."""
    note_id: int
    front: str
    back: str
    quality_status: str
    quality_score: float
    violation_type: Optional[str] = None
    quality_feedback: str
    atomic_sister_cards_recommended: List[str] = Field(default_factory=list)
    audited_at: str


class AuditQualityBatchResponse(BaseModel):
    """Batch audit execution summary and updated deck statistics."""
    deck_name: str
    batch_size: int
    audited_count: int
    items: List[NoteQualityAuditItem] = Field(default_factory=list)
    deck_stats: Dict[str, Any] = Field(default_factory=dict)


class DuplicateNotePair(BaseModel):
    """Pair of notes with high semantic vector similarity indicating redundancy or duplication."""
    note_id_1: int
    note_id_2: int
    front_1: str
    front_2: str
    similarity: float
    cluster_1: Optional[str] = None
    cluster_2: Optional[str] = None


class DeckDuplicatesResponse(BaseModel):
    """Detected redundant and duplicate note pairs in a deck."""
    deck_name: str
    min_similarity: float
    total_pairs: int
    pairs: List[DuplicateNotePair] = Field(default_factory=list)


class ConceptNode(BaseModel):
    """Atomic concept node in the deck curriculum DAG."""
    id: str = Field(..., description="Unique slug or normalized identifier for the concept")
    name: str = Field(..., description="Human-readable concept name")
    deck_name: str
    taxonomy_path: str = Field(default="general", description="Hierarchical taxonomy path e.g. 'oci::networking::security'")
    description: Optional[str] = None
    depth_level: int = Field(default=1, description="Topological depth level in the learning graph")
    stage_id: str = Field(default="stage_1", description="Curriculum stage identifier (e.g. 'stage_1', 'stage_2')")
    cards_mapped: List[int] = Field(default_factory=list, description="Anki note IDs currently mapped to this concept")
    card_count: int = Field(default=0, description="Total cards mapped to this node")
    is_orphan: bool = Field(default=False, description="True if this concept is required by others but has 0 cards mapped")
    status: str = Field(default="RAW", description="'UNMAPPED', 'RAW', 'SANITIZED', or 'EXPANDED'")
    is_in_scope: bool = Field(default=True, description="False if excluded by learning contract")
    in_degree: int = Field(default=0, description="Direct prerequisite count")
    out_degree: int = Field(default=0, description="Direct dependent count")
    is_overloaded: bool = Field(default=False, description="True if in_degree > 4, indicating node is cognitively overloaded")


class ConceptEdge(BaseModel):
    """Directed edge in the concept DAG representing dependencies or containment."""
    source: str = Field(..., description="Source concept ID (e.g. prerequisite concept)")
    target: str = Field(..., description="Target concept ID (e.g. dependent concept)")
    relation_type: str = Field(default="requires", description="'requires' (precedence: source required by target) or 'contains' (taxonomy)")


class DeckConceptDAG(BaseModel):
    """Full Directed Acyclic Graph (DAG) representing the deck curriculum ontology."""
    deck_name: str
    nodes: List[ConceptNode] = Field(default_factory=list)
    edges: List[ConceptEdge] = Field(default_factory=list)
    topological_order: List[str] = Field(default_factory=list, description="Ordered concept IDs from fundamentals to advanced")
    orphan_concepts: List[str] = Field(default_factory=list, description="Concept IDs required by notes but missing direct coverage")
    has_cycles: bool = False
    total_concepts: int = 0
    total_edges: int = 0
    transitive_reduction_applied: bool = True
    pruned_edges_count: int = 0
    out_of_scope_concepts: List[str] = Field(default_factory=list, description="Concepts excluded by learning contract")


class DAGPedagogicalContext(BaseModel):
    """Context extracted from the deck's pedagogical DAG to guide flashcard generation."""
    concept_id: str
    concept_name: str
    depth_level: int
    ancestors: List[str] = Field(default_factory=list, description="Foundational prerequisites assumed already mastered")
    descendants: List[str] = Field(default_factory=list, description="Downstream advanced concepts out of current scope")
    siblings: List[str] = Field(default_factory=list, description="Peer concepts in the same taxonomy branch")
    negative_boundaries: List[str] = Field(default_factory=list, description="Concepts forbidden from being defined in this batch")
    prompt_directive: str = Field(..., description="Pre-formatted prompt instruction block for the AI generator")


class ExtractedNoteKnowledge(BaseModel):
    """Semantic micro-extraction result from a single flashcard note."""
    source_note_id: int
    raw_front: str = ""
    raw_back: str = ""
    extracted_facts: List[str] = Field(default_factory=list, description="Atomic educational facts extracted from the note")
    target_concepts: List[str] = Field(default_factory=list, description="Core concepts explained or tested by this note")
    assumed_prerequisites: List[str] = Field(default_factory=list, description="Foundational concepts assumed by this note")
    taxonomy_path: Optional[str] = Field(default=None, description="Inferred hierarchical category e.g. 'domain::subdomain'")


class ExtractOntologyBatchRequest(BaseModel):
    """Request payload to extract ontology from notes of a deck."""
    note_ids: Optional[List[int]] = Field(default=None, description="Specific note IDs to extract; if omitted, extracts unindexed notes")
    batch_size: int = Field(default=5, ge=1, le=20)
    ai_provider: Optional[str] = Field(default="gemini")
    local_model: Optional[str] = None
    force_reextract: bool = Field(default=False, description="Whether to re-extract notes that have already been extracted")


class ExtractOntologyBatchResponse(BaseModel):
    """Execution report of ontology extraction."""
    deck_name: str
    processed_notes_count: int
    remaining_unextracted_count: int = 0
    extracted_knowledge: List[ExtractedNoteKnowledge] = Field(default_factory=list)
    dag_summary: Optional[DeckConceptDAG] = None


# -----------------------------------------------------------------------------
# Phase 2: Structured Interview & Learning Plan Contract Models
# -----------------------------------------------------------------------------

class SlotQuestionOption(BaseModel):
    """Option for a slot question in the contextual interview form."""
    id: str = Field(..., description="Unique slug for option e.g. 'bloom_design'")
    label: str = Field(..., description="Short title of the option")
    description: str = Field(..., description="Contextual explanation tailored to the deck")
    is_recommended: bool = Field(default=False, description="True if recommended by AI based on deck ontology")


class SlotQuestion(BaseModel):
    """One of the 4 mandatory slot-filling questions for establishing the learning contract."""
    slot_key: str = Field(..., description="'bloom_level', 'exclusion_boundary', 'gap_strategy', or 'operational_depth'")
    title: str = Field(..., description="Concise question title")
    contextual_explanation: str = Field(..., description="Explanation citing specific concepts found in the deck DAG")
    options: List[SlotQuestionOption] = Field(default_factory=list)
    custom_input_allowed: bool = True
    selected_option_id: Optional[str] = None
    custom_value: Optional[str] = None


class DeckInterviewForm(BaseModel):
    """Dynamically generated contextual interview form for a deck."""
    deck_name: str
    topic_overview: str
    detected_concepts_count: int
    detected_orphans_count: int
    sample_concepts: List[str] = Field(default_factory=list)
    orphan_concepts: List[str] = Field(default_factory=list)
    questions: List[SlotQuestion] = Field(default_factory=list)


class LearnerExpertiseLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class CurriculumStage(BaseModel):
    """A modular sequential milestone or track in the deck learning plan."""
    stage_id: str = Field(..., description="Unique ID, e.g. 'stage_1_foundations', 'stage_2_cloud'")
    order_index: int = Field(default=1, ge=1)
    title: str = Field(..., description="E.g. 'Etapa 1: Fundamentos de Redes (0 a 100)'")
    target_learner_level: LearnerExpertiseLevel = LearnerExpertiseLevel.BEGINNER
    bloom_level: str = Field(default="Comprensión y Mecanismos Causales")
    core_domains: List[str] = Field(default_factory=list, description="Core topics of this stage")
    exclusion_boundary: List[str] = Field(default_factory=list)
    blueprint_exam_name: Optional[str] = None
    status: str = Field(default="active", description="'active' | 'queued' | 'completed'")
    sanitation_progress_pct: float = 0.0
    sufficiency_coverage_pct: float = 0.0


class LearningPlanContract(BaseModel):
    """Formal pedagogical contract governing deck sanitization and expansion."""
    deck_name: str
    bloom_level: str = Field(..., description="Cognitive depth standard (e.g. 'Diseño y Arquitectura')")
    exclusion_boundary: List[str] = Field(default_factory=list, description="Explicit list of out-of-scope concepts or services")
    gap_strategy: str = Field(..., description="'fill_all_anchors', 'fill_critical_only', or 'assume_prerequisites'")
    operational_depth: str = Field(..., description="E.g. 'Conceptos y Arquitectura sin sintaxis CLI/código'")
    raw_summary: str = Field(default="", description="Executive pedagogical summary of the agreement")
    version: int = 1
    status: str = Field(default="draft", description="'draft' or 'approved'")
    approved_at: Optional[str] = None
    blueprint_exam_name: Optional[str] = None
    blueprint_coverage_pct: Optional[int] = None
    stages: List[CurriculumStage] = Field(default_factory=list, description="Modular sequential curriculum stages")


class SynthesizeContractRequest(BaseModel):
    """Payload to synthesize contract preview from interview form answers."""
    answers: Dict[str, str] = Field(..., description="Mapping of slot_key to user selected option or custom text")
    ai_provider: Optional[str] = "gemini"


class RefineContractRequest(BaseModel):
    """Payload to refine an existing contract preview using natural language feedback."""
    current_contract: LearningPlanContract
    user_feedback: str
    ai_provider: Optional[str] = "gemini"


class ApproveContractRequest(BaseModel):
    """Payload to finalize and lock the learning plan contract."""
    contract: LearningPlanContract


# -----------------------------------------------------------------------------
# Optional Exam Blueprint & Syllabus Models
# -----------------------------------------------------------------------------

class BlueprintObjective(BaseModel):
    """An atomic testable objective from an official syllabus/blueprint."""
    objective_id: str = Field(..., description="Unique or sequential ID (e.g. '1.1', 'OBJ-02')")
    title: str = Field(..., description="Short objective statement (e.g. 'Identify core OCI identity components')")
    description: Optional[str] = Field(default=None, description="Detailed scope or sub-topics")
    cognitive_level: str = Field(default="Understand", description="Bloom taxonomy depth")
    weight_pct: Optional[float] = Field(default=None, description="Estimated exam weight percentage")
    coverage_status: str = Field(default="unaligned", description="'covered' | 'partial' | 'gap' | 'unaligned'")
    matched_note_ids: List[int] = Field(default_factory=list, description="IDs of notes satisfying this objective")
    similarity_score: Optional[float] = Field(default=None, description="Best cosine similarity with deck knowledge")


class BlueprintDomain(BaseModel):
    """A major knowledge area or module in the syllabus."""
    domain_id: str = Field(..., description="E.g. 'D1', 'domain:iam'")
    name: str = Field(..., description="Domain name (e.g. 'OCI Networking and Connectivity')")
    weight_pct: Optional[float] = Field(default=None, description="Domain weight in the syllabus/exam (e.g. 25.0)")
    objectives: List[BlueprintObjective] = Field(default_factory=list)


class ExamBlueprint(BaseModel):
    """Formal structured blueprint representing an official syllabus or exam outline."""
    exam_name: str = Field(..., description="Official name of the exam or course")
    provider: Optional[str] = Field(default=None, description="Issuing body (e.g. 'Oracle', 'AWS', 'University')")
    source_type: str = Field(default="pasted_text", description="'upload_pdf' | 'pasted_text' | 'web_search'")
    raw_snippet: Optional[str] = Field(default=None, description="Original source excerpt or reference URL")
    domains: List[BlueprintDomain] = Field(default_factory=list)
    total_objectives: int = 0


class ParseBlueprintRequest(BaseModel):
    """Payload to parse and structure raw syllabus text or trigger search."""
    raw_text: Optional[str] = None
    exam_name: Optional[str] = None
    search_web: bool = False
    ai_provider: Optional[str] = "gemini"


class BlueprintAlignmentSummary(BaseModel):
    """Result of cross-referencing an ExamBlueprint against indexed deck knowledge."""
    deck_name: str
    exam_name: str
    total_objectives: int
    covered_count: int
    partial_count: int
    gap_count: int
    coverage_percentage: int
    created_gaps_count: int
    blueprint: ExamBlueprint


# -----------------------------------------------------------------------------
# Phase 3: Surgical Sanitation & Transactional Replacement Models
# -----------------------------------------------------------------------------

class SanitationQueueResponse(BaseModel):
    """Current state of deck notes pending surgical sanitation."""
    deck_name: str
    total_notes: int
    pending_count: int
    sanitized_count: int
    contract_approved: bool = False
    contract_version: Optional[int] = None
    notes: List[DeckNoteRecord] = Field(default_factory=list, description="Ordered list of notes pending sanitation")


class SanitationCoverageLedgerInput(BaseModel):
    """Input payload to record a collision with an existing debt/unreviewed note in the coverage ledger."""
    colliding_note_id: int = Field(..., description="ID of the colliding unreviewed/bad note")
    concept_title: str = Field(..., description="Title of the concept covered by new cards")
    facet_summary: Optional[str] = Field(default=None, description="Summary of covered cognitive facet")


class TransactionalReplaceRequest(BaseModel):
    """Request payload to atomically replace an obsolete note with new atomic flashcards."""
    source_note_id: int = Field(..., description="ID of the obsolete monolithic note to delete")
    new_cards: List[Flashcard] = Field(..., description="List of atomic sister flashcards to create")
    target_concepts: List[str] = Field(default_factory=list, description="Titles of approved CoreThemes to link to DAG concept nodes")
    pending_ledger_collisions: List[SanitationCoverageLedgerInput] = Field(
        default_factory=list,
        description="Collision notes with cognitive debt to record in coverage ledger"
    )


class TransactionalReplaceResponse(BaseModel):
    """Result of transactional note replacement via AnkiConnect."""
    success: bool
    deck_name: str
    deleted_note_id: int
    created_note_ids: List[int] = Field(default_factory=list)
    created_cards_count: int
    message: str
    remaining_in_queue: int


class SanitationCoverageLedgerEntry(BaseModel):
    """A record in the sanitation coverage ledger tracking concepts covered by prior turns."""
    id: int
    deck_name: str
    source_sanitized_note_id: int
    colliding_pending_note_id: int
    covered_concept_title: str
    covered_facet_summary: Optional[str] = None
    created_atomic_note_ids: List[int] = Field(default_factory=list)
    created_at: str


class ClusterSanitationPreviewItem(BaseModel):
    """Inspection data for an individual note within a thematic cluster."""
    note_id: int
    front: str
    back: str
    clean_front: str
    quality_status: str
    subtopic_descriptor: str
    negative_boundaries: List[str] = Field(default_factory=list)
    media_files: List[str] = Field(default_factory=list, description="Attached image filenames in this note")
    topological_rank: Optional[int] = Field(default=None, description="Precedence rank in DAG topological curriculum")
    sibling_quality_badges: Dict[str, str] = Field(default_factory=dict, description="Sibling quality status badges")


class ClusterSanitationPreviewResponse(BaseModel):
    """Thematic scope, sibling sub-topics, and mutual negative boundaries for a cluster."""
    deck_name: str
    cluster_index: int
    cluster_title: str
    cluster_scope: str
    suggested_mode: str = "cross_partition"  # "cross_partition" | "fusion"
    total_notes: int
    notes: List[ClusterSanitationPreviewItem] = Field(default_factory=list)
    cluster_negative_boundaries: List[str] = Field(default_factory=list)


class ClusterSanitationRequest(BaseModel):
    """Options for executing cluster-based thematic sanitation."""
    mode: str = Field(default="cross_partition", description="'cross_partition' (preserve depth) or 'fusion' (deduplicate)")
    cards_per_note: int = Field(default=3, ge=1, le=8, description="Target cards per note in cross-partition mode")
    fusion_target_count: int = Field(default=6, ge=2, le=16, description="Target cards if running in fusion mode")
    note_ids: Optional[List[int]] = Field(default=None, description="Optional subset of cluster note IDs to sanitize")
    custom_instructions: Optional[str] = None
    ai_provider: Optional[str] = "gemini"
    local_model: Optional[str] = "llama3.2:3b"


class ClusterSanitationResponse(BaseModel):
    """Summary of cluster-based sanitation and transactional substitution in Anki."""
    success: bool
    deck_name: str
    cluster_index: int
    cluster_title: str
    mode: str
    deleted_note_ids: List[int] = Field(default_factory=list)
    created_note_ids: List[int] = Field(default_factory=list)
    created_cards: List[Flashcard] = Field(default_factory=list)
    created_cards_count: int = 0
    remaining_in_queue: int = 0
    message: str


class PreserveOptimalResponse(BaseModel):
    """Result of preserving an original note as optimal without rewriting or deleting."""
    success: bool
    deck_name: str
    note_id: int
    message: str
    quality_status: str = "optimal"
    remaining_in_queue: int = 0


class GenerateNoteCandidatesRequest(BaseModel):
    """Request to generate candidate atomic flashcards for a single turn in a cluster."""
    cluster_index: Optional[int] = None
    custom_instructions: Optional[str] = None
    target_count: int = Field(default=0, ge=0, le=10)
    ai_provider: Optional[str] = "gemini"
    local_model: Optional[str] = "llama3.2:3b"


class GenerateNoteCandidatesResponse(BaseModel):
    """Candidate flashcards generated for an individual turn in a cluster."""
    success: bool
    deck_name: str
    note_id: int
    cluster_index: Optional[int] = None
    cards: List[Flashcard] = Field(default_factory=list)
    media_files: List[str] = Field(default_factory=list)
    subtopic_descriptor: str = ""
    negative_boundaries: List[str] = Field(default_factory=list)



# -----------------------------------------------------------------------------
# Phase 4: Topological Expansion Models
# -----------------------------------------------------------------------------

class ExpansionQueueItem(BaseModel):
    """An uncovered concept or orphan gap ordered topographically for curriculum expansion."""
    concept_id: str
    concept_name: str
    taxonomy_path: str = "general"
    depth_level: int = 0
    prerequisites: List[str] = Field(default_factory=list, description="Names of concepts that must be learned before this one")
    dependents: List[str] = Field(default_factory=list, description="Names of concepts in the deck that rely on this one")
    is_orphan: bool = True
    cards_count: int = 0
    suggested_prompt: Optional[str] = None
    neighbor_concepts: List[str] = Field(default_factory=list, description="Sibling or boundary concepts in DAG to avoid overlap")


class DeckExpansionQueueResponse(BaseModel):
    """Ordered queue of curriculum gaps ready for topological expansion."""
    deck_name: str
    contract_approved: bool
    sanitation_completed: bool
    pending_sanitation_count: int
    total_orphans: int
    total_concepts: int
    expansion_queue: List[ExpansionQueueItem] = Field(default_factory=list)


class FulfillConceptRequest(BaseModel):
    """Link newly created flashcards to a concept node, resolving its orphan gap status."""
    concept_id: str
    note_ids: List[int] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Layer 2: Pedagogical Facet Discrimination & Multi-Level Anti-Redundancy
# -----------------------------------------------------------------------------

class FacetType(str, Enum):
    """Categorization of the distinct cognitive facet tested by a flashcard."""
    DEFINITION_FUNCTION = "definition_function"
    MECHANISM_CYCLE = "mechanism_cycle"
    STOP_CONDITION = "stop_condition"
    DIFFERENTIATION_CONTRAST = "differentiation_contrast"
    DATA_SOURCE_ORIGIN = "data_source_origin"
    FAILURE_TRAP = "failure_trap"
    ATTRIBUTE_SPECIFICATION = "attribute_specification"
    OTHER = "other"


class ExtractedFacet(BaseModel):
    """Structured ontological facet extracted from a flashcard."""
    entity: str = Field(..., description="Target subject or entity (e.g. 'Patrón ReAct')")
    facet_type: FacetType = Field(default=FacetType.OTHER, description="The cognitive facet dimension")
    facet_label: str = Field(..., description="Human-readable description of the facet")
    target_retrieval_fact: str = Field(..., description="The precise atomic mental fact to recall")


class FacetDiscriminationVerdict(str, Enum):
    """Verdict of comparing a candidate flashcard against existing deck notes or sibling batch cards."""
    FACETED_COMPLEMENT = "faceted_complement"
    REDUNDANT_COLLISION = "redundant_collision"


class FacetComparisonResult(BaseModel):
    """Result of pedagogical facet discrimination."""
    verdict: FacetDiscriminationVerdict
    candidate_entity: str
    candidate_facet: str
    colliding_note_id: Optional[int] = Field(default=None, description="Note ID in Anki/DB that collides")
    colliding_card_id: Optional[str] = Field(default=None, description="Card ID in current batch that collides")
    colliding_snippet: Optional[str] = Field(default=None, description="Front snippet of colliding note")
    reasoning: str = Field(..., description="Pedagogical explanation of why it is complementary or redundant")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)


class PedagogicalAuditResult(BaseModel):
    """Composite Layer 2 audit result for a candidate flashcard."""
    card_id: str
    card_front: str
    extracted_facet: ExtractedFacet
    intra_batch_collision: Optional[FacetComparisonResult] = None
    global_deck_collision: Optional[FacetComparisonResult] = None
    is_approved: bool = True
    audit_feedback: str = ""


# -----------------------------------------------------------------------------
# Phase 4/5: Socratic Node Mastery & Challenge Models
# -----------------------------------------------------------------------------

class SocraticChallengeQuestion(BaseModel):
    """An interactive Socratic integration or counterfactual question for a DAG node."""
    concept_id: str
    concept_name: str
    challenge_question: str
    scenario_context: Optional[str] = None
    evaluation_criteria: List[str] = Field(default_factory=list)


class SocraticChallengeResponse(BaseModel):
    """Response payload containing the Socratic challenge for a node."""
    deck_name: str
    concept_id: str
    concept_name: str
    challenge: SocraticChallengeQuestion
    eligible_for_mastery: bool = True


class SocraticEvaluateRequest(BaseModel):
    """Request payload evaluating user response to a Socratic node challenge."""
    concept_id: str
    challenge_question: str
    user_answer: str
    ai_provider: Optional[str] = "gemini"


class SocraticEvaluateResponse(BaseModel):
    """Result of Socratic challenge evaluation."""
    deck_name: str
    concept_id: str
    passed: bool
    score: float = Field(..., ge=0.0, le=1.0)
    feedback: str
    new_node_status: str = "SUFFICIENT"  # "MASTERED" | "SANITIZED" | "SUFFICIENT"
    failure_cause: Optional[str] = None  # "deck_gap" | "user_recall"
    remedy_gap_title: Optional[str] = None
    relevant_card_id: Optional[int] = None
    relevant_card_front: Optional[str] = None
    relevant_card_trap: Optional[str] = None


class PedagogicalOrderViolation(BaseModel):
    """An anomaly where a card violates prerequisite sequence or depth tiering in Anki."""
    higher_depth_note_id: int
    lower_depth_note_id: int
    higher_concept: str
    lower_concept: str
    higher_depth: int
    lower_depth: int
    higher_due: int
    lower_due: int
    reason: str


class PedagogicalDeckAuditResult(BaseModel):
    """Comprehensive pedagogical audit report comparing Anki's new queue against the curriculum DAG."""
    deck_name: str
    total_cards: int
    sanitized_cards: int
    inversions_count: int
    is_pedagogically_sound: bool
    violations: List[PedagogicalOrderViolation] = Field(default_factory=list)
    recommendation: str

