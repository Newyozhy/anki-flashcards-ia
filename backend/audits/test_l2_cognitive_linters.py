import time
from typing import List
import pytest

from app.core.cloze_sanitizer import ClozeSanitizer
from app.domain.models import (
    CardType,
    FacetDiscriminationVerdict,
    FacetType,
    Flashcard,
)
from app.services.cognitive_auditor_service import CognitiveAuditorService
from app.services.pedagogical_discriminator_service import (
    PedagogicalDiscriminatorService,
    _tokenize_core_words,
)


# =============================================================================
# Level 2.1: Deterministic Syntax Linter & Anti-Priming (Layer 1)
# =============================================================================

def test_audit_l2_deterministic_cloze_syntax_repairs():
    """
    AUDIT L2.1: Deterministic Cloze Syntax Linter & Edge Cases.
    Validates auto-repair of malformed cloze tags produced by LLMs:
    (a) Bare {{palabra}} -> {{c1::palabra}}
    (b) Triple braces {{{c1::palabra}}} -> {{c1::palabra}}
    (c) Single colon typo {{c1:palabra}} -> {{c1::palabra}}
    (d) Non-contiguous ordinals {{c5::a}} {{c12::b}} -> {{c1::a}} {{c2::b}}
    (e) Misplaced clozes in back field unwrapped to clean text.
    """
    sanitizer = ClozeSanitizer()
    auditor = CognitiveAuditorService(sanitizer=sanitizer)

    card = Flashcard(
        card_type=CardType.BASIC,
        front="El protocolo BGP usa {{{c1::TCP}}} en puerto {{179}} y no {{c8::UDP}}.",
        back="Respuesta errónea con {{c1::cloze en reverso}}.",
        tags=["redes"],
        explanation="⚠️ Trampa frecuente / Error común: Confundir BGP con OSPF.",
    )

    resulting_cards, audit_report = auditor.audit_card(card, auto_split_sisters=False)
    audited = resulting_cards[0]

    # Front assertions
    assert "{{c1::TCP}}" in audited.front
    assert "{{c2::179}}" in audited.front
    assert "{{c3::UDP}}" in audited.front
    assert "{{{" not in audited.front
    assert audited.card_type == CardType.CLOZE

    # Back assertion: Clozes in back field must be stripped/unwrapped
    assert "{{c1::" not in audited.back
    assert "cloze en reverso" in audited.back

    # Findings log
    rule_names = {f.rule for f in audit_report.findings}
    assert "SYNTAX_CLOZE_REPAIRED" in rule_names
    assert "BACK_CLOZE_CONTAMINATION_REPAIRED" in rule_names


def test_audit_l2_exhaustive_grammatical_article_absorption():
    """
    AUDIT L2.2: Grammatical Priming Prevention (Article Absorption).
    Validates that preceding Spanish determinants ('el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas')
    are absorbed inside the cloze to prevent morphological retrieval leaks (gender/number priming).
    """
    auditor = CognitiveAuditorService()

    test_cases = [
        ("La división nuclear es la {{c1::mitosis}}.", "{{c1::la mitosis}}"),
        ("El consenso requiere el {{c1::quórum}}.", "{{c1::el quórum}}"),
        ("Se analizan los {{c1::algoritmos}}.", "{{c1::los algoritmos}}"),
        ("Se toleran las {{c1::particiones}}.", "{{c1::las particiones}}"),
        ("Se ajusta un {{c1::hiperparámetro}}.", "{{c1::un hiperparámetro}}"),
        ("Se introduce una {{c1::heurística}}.", "{{c1::una heurística}}"),
        ("Se actualizan unos {{c1::pesos}}.", "{{c1::unos pesos}}"),
        ("Se inicializan unas {{c1::variables}}.", "{{c1::unas variables}}"),
        ("Sensibilidad a mayúsculas: LA {{c1::mitosis}}.", "{{c1::LA mitosis}}"),
    ]

    for raw_prompt, expected_cloze in test_cases:
        card = Flashcard(
            card_type=CardType.CLOZE,
            front=f"[Test] {raw_prompt}",
            back="",
            explanation="⚠️ Trampa frecuente / Error común: Error de concepto.",
        )
        resulting_cards, audit_report = auditor.audit_card(card)
        assert expected_cloze in resulting_cards[0].front, (
            f"Failed anti-priming on: '{raw_prompt}'. Expected '{expected_cloze}' in '{resulting_cards[0].front}'"
        )
        assert any(f.rule == "RETRIEVAL_LEAK_GRAMMAR_PRIMED" for f in audit_report.findings)


# =============================================================================
# Level 2.2: Wozniak Minimum Information Principle & Hypercorrection (Layer 1)
# =============================================================================

def test_audit_l2_wozniak_atomicity_and_3_sister_card_split():
    """
    AUDIT L2.3: Piotr Wozniak Rule 4 (Minimum Information Principle).
    Validates that a 3-cloze compound card is decomposed into exactly 3 atomic Sister Cards.
    In each sister card:
    - Exactly one cloze is occluded as c1.
    - Sibling clozes appear as visible plain text context.
    - Sister tags ('tarjeta-hermana', 'hermana-X-de-3') are injected.
    - Zero data loss across the decomposition.
    """
    auditor = CognitiveAuditorService()

    compound_card = Flashcard(
        card_type=CardType.CLOZE,
        front="[Sistemas Distribuidos > Raft] En Raft, un nodo reside en uno de tres estados: {{c1::Follower}}, {{c2::Candidate}} o {{c3::Leader}}.",
        back="",
        tags=["sistemas_distribuidos", "raft"],
        explanation="Tres estados posibles del ciclo de vida.\n\n⚠️ Trampa frecuente / Error común: Confundir Candidate con Learner.",
    )

    start_time = time.perf_counter()
    sisters, audit_report = auditor.audit_card(compound_card, auto_split_sisters=True)
    duration_ms = (time.perf_counter() - start_time) * 1000

    # Invariants
    assert len(sisters) == 3, f"Expected 3 sister cards, got {len(sisters)}"
    assert audit_report.sister_cards_count == 3
    assert duration_ms < 10, f"Decomposition too slow: {duration_ms:.2f}ms"

    # Sister 1: Follower is hidden (c1), Candidate and Leader are visible text
    assert "{{c1::Follower}}" in sisters[0].front
    assert "{{c2" not in sisters[0].front and "{{c3" not in sisters[0].front
    assert "Candidate" in sisters[0].front and "Leader" in sisters[0].front
    assert "hermana-1-de-3" in sisters[0].tags
    assert sisters[0].back == "Follower"

    # Sister 2: Candidate is hidden (c1), Follower and Leader are visible text
    assert "{{c1::Candidate}}" in sisters[1].front
    assert "{{c2" not in sisters[1].front and "{{c3" not in sisters[1].front
    assert "Follower" in sisters[1].front and "Leader" in sisters[1].front
    assert "hermana-2-de-3" in sisters[1].tags
    assert sisters[1].back == "Candidate"

    # Sister 3: Leader is hidden (c1), Follower and Candidate are visible text
    assert "{{c1::Leader}}" in sisters[2].front
    assert "{{c2" not in sisters[2].front and "{{c3" not in sisters[2].front
    assert "Follower" in sisters[2].front and "Candidate" in sisters[2].front
    assert "hermana-3-de-3" in sisters[2].tags
    assert sisters[2].back == "Leader"


def test_audit_l2_metcalfe_hypercorrection_and_bloat_penalties():
    """
    AUDIT L2.4: Metcalfe Hypercorrection Effect & Paragraph Memorization Penalties.
    Validates:
    (a) Cards lacking the hypercorrection section receive a penalty and automatic scaffolding injection.
    (b) Basic cards with answer words > 20 are penalized for rote paragraph bloat.
    (c) Cards with empty front body (only taxonomy breadcrumbs) receive a critical penalty.
    """
    auditor = CognitiveAuditorService()

    # Case A: Missing hypercorrection
    card_no_trap = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > IAM] ¿Qué es un Compartment?",
        back="Una colección lógica de recursos relacionados.",
        explanation="Permite aislar recursos.",
    )
    res_a, report_a = auditor.audit_card(card_no_trap)
    assert any(f.rule == "HYPERCORRECTION_SECTION_INJECTED" for f in report_a.findings)
    assert auditor.HYPERCORRECTION_TRIGGER in res_a[0].explanation
    assert report_a.score <= 85

    # Case B: Answer word count > 20
    long_answer = " ".join(["palabra"] * 25)
    card_bloated = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > Networking] Explique el funcionamiento de VCN.",
        back=long_answer,
        explanation=f"Explicación técnica.\n\n{auditor.HYPERCORRECTION_TRIGGER} Error.",
    )
    res_b, report_b = auditor.audit_card(card_bloated)
    assert any(f.rule == "BACK_WORD_COUNT_HIGH" for f in report_b.findings)

    # Case C: Empty front body (only breadcrumbs)
    card_empty_body = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > Compute > Instances]",
        back="Detalle de instancia",
        explanation=f"{auditor.HYPERCORRECTION_TRIGGER} Error.",
    )
    res_c, report_c = auditor.audit_card(card_empty_body)
    assert any(f.rule == "EMPTY_FRONT_BODY" for f in report_c.findings)


# =============================================================================
# Level 2.3: Multi-Level Pedagogical Facet Discrimination (Layer 2)
# =============================================================================

def test_audit_l2_facet_extraction_and_categorization():
    """
    AUDIT L2.5: Cognitive Facet Extraction & Intent Categorization.
    Validates that candidate cards across diverse pedagogical objectives are accurately
    mapped to their canonical FacetType and atomic retrieval fact.
    """
    discriminator = PedagogicalDiscriminatorService()

    cards = [
        (
            Flashcard(
                card_type=CardType.BASIC,
                front="[Arquitectura > Microservicios] ¿Cuál es la condición de salida o parada del circuito (Circuit Breaker)?",
                back="Cuando la tasa de errores de petición supera el umbral configurado.",
            ),
            FacetType.STOP_CONDITION,
        ),
        (
            Flashcard(
                card_type=CardType.BASIC,
                front="[Bases de Datos > Réplicas] En el patrón CQRS, ¿de dónde proviene la información de la base de lectura?",
                back="De los eventos proyectados generados por la base de escritura.",
            ),
            FacetType.DATA_SOURCE_ORIGIN,
        ),
        (
            Flashcard(
                card_type=CardType.BASIC,
                front="[Sistemas Operativos > Procesos] ¿Cuál es la diferencia principal entre un proceso y un hilo?",
                back="Los procesos tienen espacio de memoria aislado; los hilos comparten memoria.",
            ),
            FacetType.DIFFERENTIATION_CONTRAST,
        ),
        (
            Flashcard(
                card_type=CardType.BASIC,
                front="[Redes > TCP] ¿Por qué ocurre la congestión de red y cuál es su causa raíz?",
                back="Sobrecarga en buffers de routers intermedios que excede la tasa de absorción.",
            ),
            FacetType.MECHANISM_CYCLE,
        ),
        (
            Flashcard(
                card_type=CardType.BASIC,
                front="[Seguridad > Criptografía] ¿Cuál es la trampa o error común al usar ECB en cifrado AES?",
                back="Fuga de patrones visuales porque bloques idénticos producen cifrados idénticos.",
            ),
            FacetType.FAILURE_TRAP,
        ),
        (
            Flashcard(
                card_type=CardType.BASIC,
                front="[Algoritmos > Grafos] ¿Qué es el algoritmo de Dijkstra?",
                back="Un algoritmo codicioso para calcular caminos más cortos desde un nodo origen.",
            ),
            FacetType.DEFINITION_FUNCTION,
        ),
    ]

    for card, expected_facet in cards:
        extracted = discriminator.extract_facet(card)
        assert extracted.facet_type == expected_facet, (
            f"Expected {expected_facet} for '{card.front}', got {extracted.facet_type}"
        )


@pytest.mark.asyncio
async def test_audit_l2_intra_batch_collision_filter():
    """
    AUDIT L2.6: Intra-Batch Redundancy Filter & Complement Approval.
    Validates that when a micro-batch of candidate cards contains:
    - 2 redundant cards asking the exact same question in different phrasing.
    - 3 complementary cards targeting different facets of the same entity.
    The Layer 2 discriminator prunes exactly the redundant card and approves all complements.
    """
    discriminator = PedagogicalDiscriminatorService()

    # Redundant Pair: Card A and Card B both ask what Raft consensus is
    card_a = Flashcard(
        id="card-a",
        card_type=CardType.BASIC,
        front="[Sistemas Distribuidos > Raft] ¿Qué es el algoritmo de consenso Raft?",
        back="Un algoritmo para consenso en máquinas de estados replicadas descompuesto en subproblemas.",
    )
    card_b_redundant = Flashcard(
        id="card-b",
        card_type=CardType.BASIC,
        front="[Raft > Algoritmo] ¿Cuál es la definición del protocolo Raft?",
        back="Algoritmo de consenso para gestionar máquinas de estados replicadas.",
    )

    # Complement 1: Mechanism / Election Cycle
    card_c_mechanism = Flashcard(
        id="card-c",
        card_type=CardType.BASIC,
        front="[Raft > Elección] ¿Cómo intercala Raft los temporizadores de heartbeat para evitar split votes?",
        back="Aleatorizando los tiempos de espera entre 150ms y 300ms.",
    )

    # Complement 2: Stop condition / Election win
    card_d_stop = Flashcard(
        id="card-d",
        card_type=CardType.BASIC,
        front="[Raft > Quórum] ¿Cuál es la condición de parada o triunfo en una elección de líder?",
        back="Alcanzar votos de una mayoría estricta de nodos: Q = floor(N/2) + 1.",
    )

    # Complement 3: Failure trap / Figure 8 anomaly
    card_e_trap = Flashcard(
        id="card-e",
        card_type=CardType.BASIC,
        front="[Raft > Seguridad] ¿Cuál es el riesgo o trampa al comprometer entradas de términos anteriores?",
        back="Sobrescritura de entradas replicadas (anomalía de la Figura 8).",
    )

    batch = [card_a, card_b_redundant, card_c_mechanism, card_d_stop, card_e_trap]

    results = await discriminator.audit_batch(batch)

    # Invariants
    approved_cards = [r for r in results if r.is_approved]
    rejected_cards = [r for r in results if not r.is_approved]

    # Exactly 1 card rejected (the redundant duplicate)
    assert len(rejected_cards) == 1, f"Expected 1 rejected card, got {len(rejected_cards)}"
    assert rejected_cards[0].card_id == "card-b", "Card B must be rejected as redundant collision."
    assert rejected_cards[0].intra_batch_collision.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION

    # Exactly 4 cards approved (Card A + 3 complementary facets)
    assert len(approved_cards) == 4, f"Expected 4 approved cards, got {len(approved_cards)}"
    approved_ids = {r.card_id for r in approved_cards}
    assert approved_ids == {"card-a", "card-c", "card-d", "card-e"}


def test_audit_l2_global_deck_collision_detection(tmp_audit_db):
    """
    AUDIT L2.7: Global Deck Semantic Collision Detection.
    Validates that a candidate card is checked against existing deck notes in SQLite store:
    (a) Candidate card testing an already-covered atomic fact is flagged as global collision.
    (b) Candidate card introducing a complementary facet for an existing note is approved.
    """
    deck = "Audit::GlobalDeckCollisions"

    # Seed existing deck note in SQLite store
    existing_front = "[OCI > Redes > VCN] ¿Qué es una Virtual Cloud Network (VCN)?"
    existing_back = "Una red virtual definida por software en una región de Oracle Cloud."
    tmp_audit_db.save_note_embeddings(
        deck_name=deck,
        notes=[
            {
                "note_id": 901,
                "front": existing_front,
                "back": existing_back,
                "tags": ["oci", "networking"],
                "clean_text": f"{existing_front} {existing_back}",
                "embedding": [0.95, 0.1, 0.0, 0.0],
            }
        ],
    )

    discriminator = PedagogicalDiscriminatorService(store=tmp_audit_db)

    # 1. Candidate Colliding Card: repeats the definition of VCN
    candidate_colliding = Flashcard(
        id="candidate-dup",
        card_type=CardType.BASIC,
        front="[OCI > Networking] ¿Cuál es la definición de una VCN en Oracle Cloud?",
        back="Es una red privada virtual definida por software en una región de OCI.",
    )

    verdict_colliding = discriminator.discriminate_pair(
        candidate_card=candidate_colliding,
        existing_text=f"{existing_front} {existing_back}",
        existing_note_id=901,
    )
    assert verdict_colliding.verdict == FacetDiscriminationVerdict.REDUNDANT_COLLISION
    assert verdict_colliding.colliding_note_id == 901

    # 2. Candidate Complementary Card: tests stop condition or CIDR specification of VCN
    candidate_complement = Flashcard(
        id="candidate-comp",
        card_type=CardType.BASIC,
        front="[OCI > Redes > VCN] ¿Cuál es el tamaño máximo de bloque CIDR permitido para una VCN?",
        back="El rango de tamaño CIDR va desde /16 hasta /30.",
    )

    verdict_complement = discriminator.discriminate_pair(
        candidate_card=candidate_complement,
        existing_text=f"{existing_front} {existing_back}",
        existing_note_id=901,
    )
    assert verdict_complement.verdict == FacetDiscriminationVerdict.FACETED_COMPLEMENT
