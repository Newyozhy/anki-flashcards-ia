export type CardType = 'basic' | 'cloze' | 'reverse';

export interface Flashcard {
  id: string;
  card_type: CardType;
  archetype?: string;
  front: string;
  back: string;
  tags: string[];
  explanation?: string;
  justification?: string;
  source_image_index?: number;
  source_image?: string;
  source_images?: string[];
}

export interface AnkiStatus {
  is_connected: boolean;
  version?: string;
  available_decks: string[];
  error_message?: string;
}

export interface OllamaStatus {
  is_available: boolean;
  models: string[];
  running_models?: string[];
  active_model: string;
  error_message?: string;
}

export interface GenerationOptions {
  card_type: CardType;
  target_count: number;
  difficulty_level: 'beginner' | 'intermediate' | 'advanced';
  language: string;
  deck_name: string;
  custom_instructions?: string;
  prerequisites_context?: string;
  selected_themes?: string[];
  ai_provider?: 'gemini' | 'ollama';
  local_model?: string;
  neighbor_concepts?: string[];
  source_note_id?: number;
  target_concept?: string;
  media_filenames?: string[];
}

export type PrerequisiteMatchStatus = 'dominated' | 'cognitive_debt' | 'complementary' | 'gap';

export interface PrerequisiteMatch {
  concept: string;
  status: PrerequisiteMatchStatus;
  confidence: number;
  matched_note_id?: number | null;
  matched_note_front?: string | null;
  similarity_score: number;
  verdict_explanation: string;
  suggested_action: 'keep_existing' | 'refactor_existing' | 'study_complementary' | 'create_new';
  media_files?: string[];
  should_replace?: boolean;
  quality_status?: 'unreviewed' | 'bad' | 'preevaluated' | 'optimal';
  quality_score?: number | null;
  quality_feedback?: string | null;
  violation_type?: string | null;
}

export interface CoreTheme {
  id: string;
  title: string;
  theme?: string;
  description: string;
  recommended_cards: number;
  selected: boolean;
  match_info?: PrerequisiteMatch;
  associated_diagrams?: string[];
  diagram_roles?: Record<string, string>;
}

export type CoreThemeItem = CoreTheme;

export interface MatchStudyPlanRequest {
  deck_name: string;
  prerequisites?: PrerequisiteItem[];
  core_themes?: CoreTheme[];
  exclude_note_ids?: number[];
  source_note_id?: number;
}

export interface MatchStudyPlanResponse {
  deck_name: string;
  prerequisite_matches: PrerequisiteMatch[];
  theme_matches: PrerequisiteMatch[];
  total_indexed_notes: number;
}

export interface SyncDeckIndexResponse {
  deck_name: string;
  total_notes: number;
  newly_indexed: number;
  duration_seconds: number;
}

export interface PrerequisiteItem {
  id: string;
  concept: string;
  reason: string;
  is_covered_in_text: boolean;
  search_query: string;
  selected: boolean;
  enriched_summary?: string;
  isEnriching?: boolean;
  mode?: 'anchor' | 'deep_dive';
  deep_card_count?: number;
  recommended_deep_cards?: number;
  atomic_blueprint?: string[];
  match_info?: PrerequisiteMatch;
}

export interface StudyPlanInspection {
  topic_name: string;
  self_sufficiency_score: number;
  self_sufficiency_verdict: string;
  core_themes: CoreTheme[];
  prerequisites: PrerequisiteItem[];
  suggested_total_cards: number;
  obsolete_note_ids?: number[];
  inherited_media_files?: string[];
  source_note_id?: number;
  source_text?: string;
  provider_used?: 'gemini' | 'nvidia' | 'groq' | 'openrouter' | string;
  model_used?: string;
  fallback_occurred?: boolean;
  fallback_chain?: string[];
}

export interface CurationQueueItem {
  id: string;
  note_id: number;
  front: string;
  deck_name: string;
  matched_concept: string;
  added_at: string;
}

export interface ExportRequest {
  deck_name: string;
  cards: Flashcard[];
  obsolete_note_ids?: number[];
}

export interface ExportResult {
  success: boolean;
  cards_exported_count: number;
  destination: 'anki_connect' | 'apkg';
  message: string;
  apkg_file_path?: string;
  deleted_notes_count?: number;
  created_note_ids?: number[];
}

export interface CognitiveAuditFinding {
  rule: string;
  severity: 'INFO' | 'WARNING' | 'VIOLATION';
  message: string;
  original_snippet?: string;
  corrected_snippet?: string;
  auto_fixed: boolean;
  suggested_replacement?: string;
}

export interface CardAuditResult {
  card_id: string;
  card_front_preview: string;
  passed: boolean;
  score: number;
  findings: CognitiveAuditFinding[];
  sister_cards_count: number;
}

export interface DeckAuditReport {
  total_cards_audited: number;
  total_cards_repaired: number;
  total_sister_cards_created: number;
  average_quality_score: number;
  card_reports: CardAuditResult[];
}

export interface GenerateCardsResponse {
  cards: Flashcard[];
  audit_report?: DeckAuditReport;
  pedagogical_results?: PedagogicalAuditResult[];
}

export type NoteQualityStatus = 'unreviewed' | 'bad' | 'preevaluated' | 'optimal';

export interface DeckNoteRecord {
  note_id: number;
  deck_name: string;
  model_name: string;
  card_type: CardType;
  front: string;
  back: string;
  explanation?: string;
  clean_text?: string;
  clean_front?: string;
  clean_back?: string;
  clean_explanation?: string;
  tags: string[];
  raw_fields: Record<string, string>;
  media_files: string[];
  card_ids?: number[];
  quality_status?: NoteQualityStatus;
  quality_score?: number;
  quality_feedback?: string;
  audited_at?: string;
}

export interface RefactorNotePreviewRequest {
  note_id: number;
  concept_context?: string;
  deck_name?: string;
  ai_provider?: string;
  local_model?: string;
}

export interface RefactorNotePreviewResponse {
  note_id: number;
  deck_name: string;
  model_name: string;
  original_fields: Record<string, string>;
  refactored_fields: Record<string, string>;
  diff_summary: string;
  cognitive_archetype: string;
}

export interface ApplyRefactorRequest {
  note_id: number;
  deck_name: string;
  fields: Record<string, string>;
}

export interface ApplyRefactorResponse {
  success: boolean;
  note_id: number;
  message: string;
}

export type CoverageGapStatus = 'pending' | 'in_curation' | 'resolved';

export interface CoveredFacet {
  facet: string;
  description: string;
  matched_note_ids: number[];
  quality_score: number;
}

export interface OrphanGap {
  gap_title: string;
  reason: string;
  priority: 'high' | 'medium' | 'low';
  suggested_front?: string;
  status: CoverageGapStatus;
  generated_note_id?: number;
}

export interface TopicCoverageAuditRequest {
  topic: string;
  description?: string;
  top_k?: number;
  save_audit?: boolean;
}

export interface TopicCoverageAuditResponse {
  audit_id?: number;
  deck_name: string;
  topic: string;
  coverage_percentage: number;
  covered_facets: CoveredFacet[];
  orphan_gaps: OrphanGap[];
  summary_assessment: string;
  created_at: string;
}

export interface DeckAuditSummary {
  id: number;
  topic: string;
  coverage_percentage: number;
  total_facets: number;
  total_gaps: number;
  pending_gaps: number;
  created_at: string;
}

export interface ListDeckAuditsResponse {
  deck_name: string;
  audits: DeckAuditSummary[];
}

export interface DeckCoverageMapNode {
  id: string;
  label: string;
  type: 'deck' | 'cluster' | 'note' | 'gap';
  health: 'optimal' | 'preevaluated' | 'bad' | 'gap' | 'unreviewed' | 'debt' | 'broken';
  note_id?: number;
  details?: string;
  quality_score?: number;
  quality_feedback?: string;
}

export interface DeckCoverageMapEdge {
  source: string;
  target: string;
}

export interface DeckCoverageMapResponse {
  deck_name: string;
  total_nodes: number;
  nodes: DeckCoverageMapNode[];
  edges: DeckCoverageMapEdge[];
  optimal_count: number;
  preevaluated_count?: number;
  bad_count?: number;
  debt_count: number;
  gap_count: number;
  unreviewed_count?: number;
  broken_count?: number;
  audited_count?: number;
  deck_health_percentage?: number | null;
}

export interface NoteQualityAuditItem {
  note_id: number;
  front: string;
  back: string;
  quality_status: 'optimal' | 'bad' | 'preevaluated' | 'unreviewed' | 'debt' | 'broken';
  quality_score: number;
  violation_type?: string;
  quality_feedback: string;
  atomic_sister_cards_recommended: string[];
  audited_at: string;
}

export interface AuditQualityBatchRequest {
  batch_size?: number;
  note_ids?: number[];
  ai_provider?: string;
  local_model?: string;
}

export interface AuditQualityBatchResponse {
  deck_name: string;
  batch_size: number;
  audited_count: number;
  items: NoteQualityAuditItem[];
  deck_stats: Record<string, any>;
}

export interface SemanticClusterItem {
  cluster_index: number;
  title: string;
  scope: string;
  note_ids: number[];
  centroid_note_ids: number[];
}

export interface DeckClustersResponse {
  deck_name: string;
  clusters: SemanticClusterItem[];
}

export interface DuplicateNotePair {
  note_id_1: number;
  note_id_2: number;
  front_1: string;
  front_2: string;
  similarity: number;
  cluster_1?: string;
  cluster_2?: string;
}

export interface DeckDuplicatesResponse {
  deck_name: string;
  min_similarity: number;
  total_pairs: number;
  pairs: DuplicateNotePair[];
}

// -----------------------------------------------------------------------------
// Phase 1 & 2: Concept DAG & Learning Plan Contract Types
// -----------------------------------------------------------------------------

export interface ConceptNode {
  id: string;
  name: string;
  deck_name: string;
  taxonomy_path: string;
  description?: string | null;
  depth_level: number;
  cards_mapped: number[];
  card_count: number;
  is_orphan: boolean;
  status?: string;
  is_in_scope?: boolean;
  in_degree?: number;
  out_degree?: number;
  is_overloaded?: boolean;
}

export interface ConceptEdge {
  source: string;
  target: string;
  relation_type: string;
}

export interface DeckConceptDAG {
  deck_name: string;
  nodes: ConceptNode[];
  edges: ConceptEdge[];
  topological_order: string[];
  orphan_concepts: string[];
  has_cycles: boolean;
  total_concepts: number;
  total_edges: number;
  transitive_reduction_applied?: boolean;
  pruned_edges_count?: number;
  out_of_scope_concepts?: string[];
}

export interface ExtractedNoteKnowledge {
  source_note_id: number;
  raw_front?: string;
  raw_back?: string;
  extracted_facts: string[];
  target_concepts: string[];
  assumed_prerequisites: string[];
  taxonomy_path?: string | null;
}

export interface ExtractOntologyBatchRequest {
  note_ids?: number[];
  batch_size?: number;
  ai_provider?: string;
  local_model?: string;
  force_reextract?: boolean;
}

export interface ExtractOntologyBatchResponse {
  deck_name: string;
  processed_notes_count: number;
  remaining_unextracted_count: number;
  extracted_knowledge?: ExtractedNoteKnowledge[];
  dag_summary?: DeckConceptDAG;
}

export interface SlotQuestionOption {
  id: string;
  label: string;
  description: string;
  is_recommended: boolean;
}

export interface SlotQuestion {
  slot_key: 'bloom_level' | 'exclusion_boundary' | 'gap_strategy' | 'operational_depth' | string;
  title: string;
  contextual_explanation: string;
  options: SlotQuestionOption[];
  custom_input_allowed?: boolean;
  selected_option_id?: string | null;
  custom_value?: string | null;
}

export interface DeckInterviewForm {
  deck_name: string;
  topic_overview: string;
  detected_concepts_count: number;
  detected_orphans_count: number;
  sample_concepts: string[];
  orphan_concepts: string[];
  questions: SlotQuestion[];
}

export interface LearningPlanContract {
  deck_name: string;
  bloom_level: string;
  exclusion_boundary: string[];
  gap_strategy: string;
  operational_depth: string;
  raw_summary: string;
  version: number;
  status: 'draft' | 'approved';
  approved_at?: string | null;
  blueprint_exam_name?: string | null;
  blueprint_coverage_pct?: number | null;
}

export interface BlueprintObjective {
  objective_id: string;
  title: string;
  description?: string | null;
  cognitive_level: string;
  weight_pct?: number | null;
  coverage_status: 'covered' | 'partial' | 'gap' | 'unaligned';
  matched_note_ids: number[];
  similarity_score?: number | null;
}

export interface BlueprintDomain {
  domain_id: string;
  name: string;
  weight_pct?: number | null;
  objectives: BlueprintObjective[];
}

export interface ExamBlueprint {
  exam_name: string;
  provider?: string | null;
  source_type: string;
  raw_snippet?: string | null;
  domains: BlueprintDomain[];
  total_objectives: number;
}

export interface BlueprintAlignmentSummary {
  deck_name: string;
  exam_name: string;
  total_objectives: number;
  covered_count: number;
  partial_count: number;
  gap_count: number;
  coverage_percentage: number;
  created_gaps_count: number;
  blueprint: ExamBlueprint;
}

export interface SanitationQueueResponse {
  deck_name: string;
  total_notes: number;
  pending_count: number;
  sanitized_count: number;
  contract_approved: boolean;
  contract_version?: number | null;
  notes: DeckNoteRecord[];
}

export interface SanitationCoverageLedgerInput {
  colliding_note_id: number;
  concept_title: string;
  facet_summary?: string;
}

export interface TransactionalReplaceRequest {
  source_note_id: number;
  new_cards: Flashcard[];
  target_concepts?: string[];
  pending_ledger_collisions?: SanitationCoverageLedgerInput[];
}

export interface TransactionalReplaceResponse {
  success: boolean;
  deck_name: string;
  deleted_note_id: number;
  created_note_ids: number[];
  created_cards_count: number;
  message: string;
  remaining_in_queue: number;
}

export interface SocraticChallengeQuestion {
  concept_id: string;
  concept_name: string;
  challenge_question: string;
  scenario_context?: string;
  evaluation_criteria: string[];
}

export interface SocraticChallengeResponse {
  deck_name: string;
  concept_id: string;
  concept_name: string;
  challenge: SocraticChallengeQuestion;
  eligible_for_mastery: boolean;
}

export interface SocraticEvaluateRequest {
  concept_id: string;
  challenge_question: string;
  user_answer: string;
  ai_provider?: string;
}

export interface SocraticEvaluateResponse {
  deck_name: string;
  concept_id: string;
  passed: boolean;
  score: number;
  feedback: string;
  new_node_status: string;
  failure_cause?: 'deck_gap' | 'user_recall' | null;
  remedy_gap_title?: string | null;
  relevant_card_id?: number | null;
  relevant_card_front?: string | null;
  relevant_card_trap?: string | null;
}

export interface ClusterSanitationPreviewItem {
  note_id: number;
  front: string;
  back: string;
  clean_front: string;
  quality_status: NoteQualityStatus;
  subtopic_descriptor: string;
  negative_boundaries: string[];
  media_files?: string[];
  topological_rank?: number;
  sibling_quality_badges?: Record<string, string>;
}

export interface ClusterSanitationPreviewResponse {
  deck_name: string;
  cluster_index: number;
  cluster_title: string;
  cluster_scope: string;
  suggested_mode: 'cross_partition' | 'fusion';
  total_notes: number;
  notes: ClusterSanitationPreviewItem[];
  cluster_negative_boundaries: string[];
}

export interface ClusterSanitationRequest {
  mode?: 'cross_partition' | 'fusion';
  cards_per_note?: number;
  fusion_target_count?: number;
  note_ids?: number[];
  custom_instructions?: string;
  ai_provider?: string;
  local_model?: string;
}

export interface ClusterSanitationResponse {
  success: boolean;
  deck_name: string;
  cluster_index: number;
  cluster_title: string;
  mode: string;
  deleted_note_ids: number[];
  created_note_ids: number[];
  created_cards: Flashcard[];
  created_cards_count: number;
  remaining_in_queue: number;
  message: string;
}

export interface PreserveOptimalResponse {
  success: boolean;
  deck_name: string;
  note_id: number;
  message: string;
  quality_status: string;
  remaining_in_queue: number;
}

export interface GenerateNoteCandidatesResponse {
  success: boolean;
  deck_name: string;
  note_id: number;
  cluster_index?: number;
  cards: Flashcard[];
  media_files: string[];
  subtopic_descriptor: string;
  negative_boundaries: string[];
}

export interface ExpansionQueueItem {
  concept_id: string;
  concept_name: string;
  taxonomy_path: string;
  depth_level: number;
  prerequisites: string[];
  dependents: string[];
  is_orphan: boolean;
  cards_count: number;
  suggested_prompt?: string;
  neighbor_concepts?: string[];
}

export interface DeckExpansionQueueResponse {
  deck_name: string;
  contract_approved: boolean;
  sanitation_completed: boolean;
  pending_sanitation_count: number;
  total_orphans: number;
  total_concepts: number;
  expansion_queue: ExpansionQueueItem[];
}

export interface FulfillConceptRequest {
  concept_id: string;
  note_ids: number[];
}

// -----------------------------------------------------------------------------
// Layer 2: Pedagogical Facet Discrimination & Multi-Level Anti-Redundancy
// -----------------------------------------------------------------------------

export type FacetType =
  | 'definition_function'
  | 'mechanism_cycle'
  | 'stop_condition'
  | 'differentiation_contrast'
  | 'data_source_origin'
  | 'failure_trap'
  | 'attribute_specification'
  | 'other';

export interface ExtractedFacet {
  entity: string;
  facet_type: FacetType;
  facet_label: string;
  target_retrieval_fact: string;
}

export type FacetDiscriminationVerdict = 'faceted_complement' | 'redundant_collision';

export interface FacetComparisonResult {
  verdict: FacetDiscriminationVerdict;
  candidate_entity: string;
  candidate_facet: string;
  colliding_note_id?: number | null;
  colliding_card_id?: string | null;
  colliding_snippet?: string | null;
  reasoning: string;
  confidence_score: number;
}

export interface PedagogicalAuditResult {
  card_id: string;
  card_front: string;
  extracted_facet: ExtractedFacet;
  intra_batch_collision?: FacetComparisonResult | null;
  global_deck_collision?: FacetComparisonResult | null;
  is_approved: boolean;
  audit_feedback: string;
}

export interface PedagogicalOrderViolation {
  higher_depth_note_id: number;
  lower_depth_note_id: number;
  higher_concept: string;
  lower_concept: string;
  higher_depth: number;
  lower_depth: number;
  higher_due: number;
  lower_due: number;
  reason: string;
}

export interface PedagogicalDeckAuditResult {
  deck_name: string;
  total_cards: number;
  sanitized_cards: number;
  inversions_count: number;
  is_pedagogically_sound: boolean;
  violations: PedagogicalOrderViolation[];
  recommendation: string;
}

