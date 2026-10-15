import pytest
import asyncio
from typing import Dict, Any

from app.domain.models import Flashcard, CardType, LearningPlanContract
from app.services.pedagogical_judge_service import PedagogicalJudgeService, PedagogicalJudgeReport


@pytest.fixture
def judge_service() -> PedagogicalJudgeService:
    """Provides a PedagogicalJudgeService instance."""
    return PedagogicalJudgeService()


def test_audit_l4_wozniak_atomicity_rubric_gate(judge_service: PedagogicalJudgeService):
    """
    AUDIT L4.1: Piotr Wozniak's Rule 4 (Minimum Information Principle).
    Verifies that the judge strictly certifies atomic single-fact cards
    and rejects monolithic cards bundling multiple enumerations or paragraphs.
    """
    # 1. Compliant Atomic Card (< 15 words, single retrievable proposition)
    atomic_card = Flashcard(
        card_type=CardType.BASIC,
        front="[Redes > OCI > VCN] ¿Cuál es el tamaño máximo de MTU para Jumbo Frames en una VCN?",
        back="9000 bytes.",
        explanation=(
            "Las tramas estándar usan 1500 bytes, mientras que Jumbo Frames permiten 9000 bytes dentro de la VCN.\n"
            "⚠️ Trampa frecuente / Error común: Confundir el límite de MTU de Internet (1500 bytes) con el de tráfico interno de VCN."
        ),
    )
    report_atomic = judge_service.evaluate_card_heuristic(atomic_card)
    assert report_atomic.scores["ATOMICITY"].passed is True
    assert report_atomic.scores["ATOMICITY"].score >= 0.85
    assert len(report_atomic.scores["ATOMICITY"].flaws) == 0

    # 2. Monolithic Multi-Item Card (violates Rule 4 with dense list and paragraph)
    monolithic_card = Flashcard(
        card_type=CardType.BASIC,
        front="[Redes > OCI] ¿Cuáles son todos los componentes de una VCN y cómo funcionan?",
        back=(
            "Una VCN se compone de:\n"
            "- Subnets (públicas o privadas)\n"
            "- Route Tables (reglas de enrutamiento por CIDR)\n"
            "- Security Lists e Internet Gateways\n"
            "- NAT Gateways, Service Gateways y Dynamic Routing Gateways (DRG)\n"
            "- Local Peering Gateways para interconectar múltiples redes virtuales."
        ),
        explanation="",
    )
    report_monolithic = judge_service.evaluate_card_heuristic(monolithic_card)
    assert report_monolithic.scores["ATOMICITY"].passed is False
    assert report_monolithic.scores["ATOMICITY"].score <= 0.50
    assert any("lista" in f.lower() or "palabras" in f.lower() for f in report_monolithic.scores["ATOMICITY"].flaws)
    assert report_monolithic.is_certified is False
    assert report_monolithic.verdict == "REJECTED"


def test_audit_l4_context_independence_and_cue_overfitting(judge_service: PedagogicalJudgeService):
    """
    AUDIT L4.2: Context Independence & Anti-Priming (Cue Overfitting).
    Verifies that cards provide sufficient framing without leaking the answer
    through obvious lexical cues, grammatical primes, or trivial keywords.
    """
    # 1. Independent, well-framed card
    well_framed_card = Flashcard(
        card_type=CardType.BASIC,
        front="[Bases de Datos > Replicación > Consistencia] ¿Qué protocolo de consenso utiliza Raft para sincronizar logs?",
        back="Two-Phase Commit (2PC) optimizado mediante log replication conducido por el líder.",
        explanation="⚠️ Trampa frecuente / Error común: Creer que Raft usa Paxos multifase; Raft utiliza un líder fuerte y append entries.",
    )
    report_good = judge_service.evaluate_card_heuristic(well_framed_card)
    assert report_good.scores["CONTEXT_INDEPENDENCE"].passed is True
    assert report_good.scores["CONTEXT_INDEPENDENCE"].score >= 0.80

    # 2. Leaking / Cue Overfitting card (question includes the answer words trivially)
    leaking_card = Flashcard(
        card_type=CardType.BASIC,
        front="¿Qué protocolo de replicación de log de líder fuerte en Raft se llama AppendEntries?",
        back="AppendEntries.",
        explanation="⚠️ Trampa frecuente / Error común: Confundir con RequestVote.",
    )
    report_leaking = judge_service.evaluate_card_heuristic(leaking_card)
    assert report_leaking.scores["CONTEXT_INDEPENDENCE"].passed is False
    assert report_leaking.scores["CONTEXT_INDEPENDENCE"].score <= 0.60
    assert any("regala" in f.lower() or "overfitting" in f.lower() for f in report_leaking.scores["CONTEXT_INDEPENDENCE"].flaws)


def test_audit_l4_faithfulness_and_hallucination_injection(judge_service: PedagogicalJudgeService):
    """
    AUDIT L4.3: Faithfulness & Anti-Hallucination Gate against Source Text.
    Verifies that claims must be grounded in the source text chunk,
    flagging hallucinations and fabricated technical specifications.
    """
    source_corpus_chunk = """
    Oracle Cloud Infrastructure (OCI) Virtual Cloud Network (VCN) supports Maximum Transmission Unit (MTU)
    sizes of 1500 bytes (standard) and 9000 bytes (jumbo frames). Jumbo frames are only supported for
    traffic within the same VCN or across peered VCNs via Local Peering Gateway (LPG). Traffic destined
    to the Internet is strictly clamped to 1500 bytes. FastConnect supports both 1500 and 9000 MTU.
    """

    # 1. Faithful Card grounded in source
    faithful_card = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > VCN > MTU] ¿Qué tamaño de MTU se admite para tráfico interno de VCN usando Jumbo Frames?",
        back="9000 bytes.",
        explanation="⚠️ Trampa frecuente / Error común: Tráfico hacia Internet solo admite 1500 bytes.",
    )
    report_faithful = judge_service.evaluate_card_heuristic(faithful_card, source_chunk=source_corpus_chunk)
    assert report_faithful.scores["FAITHFULNESS"].passed is True
    assert report_faithful.scores["FAITHFULNESS"].score >= 0.90

    # 2. Hallucinatory Card (Fabricating non-existent 64000 MTU and UltraFast Turbo mode)
    hallucinated_card = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > VCN > MTU] ¿Qué tamaño de MTU admite el modo UltraFast Turbo?",
        back="64000 bytes usando compresión cuántica acelerada.",
        explanation="⚠️ Trampa frecuente / Error común: Confundir con 9000 bytes.",
    )
    report_hallucinated = judge_service.evaluate_card_heuristic(hallucinated_card, source_chunk=source_corpus_chunk)
    assert report_hallucinated.scores["FAITHFULNESS"].passed is False
    assert report_hallucinated.scores["FAITHFULNESS"].score <= 0.40
    assert any("alucinación" in f.lower() or "no hallados" in f.lower() for f in report_hallucinated.scores["FAITHFULNESS"].flaws)
    assert report_hallucinated.is_certified is False


def test_audit_l4_bloom_and_learning_contract_alignment(judge_service: PedagogicalJudgeService):
    """
    AUDIT L4.4: Bloom Depth & LearningPlanContract Boundary Enforcement.
    Verifies that cards strictly adhere to the contract's cognitive depth
    and respect explicit exclusion boundaries (e.g., prohibited topics).
    """
    approved_contract = LearningPlanContract(
        deck_name="Oracle::Cloud::Architecture",
        bloom_level="Diseño y Arquitectura",
        exclusion_boundary=["CLI sintaxis", "SDK deprecado", "Precios y facturación"],
        gap_strategy="fill_critical_only",
        operational_depth="Conceptos y patrones de alta disponibilidad sin comandos de terminal",
        status="approved",
    )

    # 1. Compliant Architectural Card
    architectural_card = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > Arquitectura > Subnets] Para una base de datos de producción con alta disponibilidad, ¿qué tipo de subnet se debe diseñar?",
        back="Subnet privada regional distribuida en múltiples Availability Domains o Fault Domains.",
        explanation="⚠️ Trampa frecuente / Error común: Usar subnets públicas exponiendo el listener de BD a Internet.",
    )
    report_arch = judge_service.evaluate_card_heuristic(architectural_card, contract=approved_contract)
    assert report_arch.scores["BLOOM_CONTRACT_ALIGNMENT"].passed is True
    assert report_arch.scores["BLOOM_CONTRACT_ALIGNMENT"].score >= 0.80

    # 2. Boundary Violation Card (Evaluating explicitly prohibited CLI syntax)
    cli_violation_card = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > CLI sintaxis] ¿Qué comando se usa para listar subnets en OCI?",
        back="oci network subnet list --compartment-id ocid1...",
        explanation="⚠️ Trampa frecuente / Error común: Olvidar el parámetro compartment-id.",
    )
    report_cli = judge_service.evaluate_card_heuristic(cli_violation_card, contract=approved_contract)
    assert report_cli.scores["BLOOM_CONTRACT_ALIGNMENT"].passed is False
    assert report_cli.scores["BLOOM_CONTRACT_ALIGNMENT"].score <= 0.30
    assert any("excluido" in f.lower() for f in report_cli.scores["BLOOM_CONTRACT_ALIGNMENT"].flaws)
    assert report_cli.is_certified is False


def test_audit_l4_metcalfe_hypercorrection_quality(judge_service: PedagogicalJudgeService):
    """
    AUDIT L4.5: Metcalfe Hypercorrection Misconception Diagnostic Gate.
    Verifies that cards must include an actionable diagnostic trap in the Extra field,
    penalizing cards with empty or trivial explanations.
    """
    # 1. Compliant Hypercorrection Explanation
    good_trap_card = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > Seguridad] ¿A qué nivel se aplican las reglas de un Network Security Group (NSG)?",
        back="A nivel de VNIC individual (interfaz de red).",
        explanation=(
            "Los NSG se asocian directamente a las VNIC de instancias específicas.\n"
            "⚠️ Trampa frecuente / Error común: Confundir NSG con Security Lists, las cuales se aplican a nivel de toda la subnet."
        ),
    )
    report_good_trap = judge_service.evaluate_card_heuristic(good_trap_card)
    assert report_good_trap.scores["HYPERCORRECTION_FEEDBACK"].passed is True
    assert report_good_trap.scores["HYPERCORRECTION_FEEDBACK"].score >= 0.80

    # 2. Missing Hypercorrection Explanation
    no_trap_card = Flashcard(
        card_type=CardType.BASIC,
        front="[OCI > Seguridad] ¿A qué nivel se aplican las reglas de un Network Security Group (NSG)?",
        back="A nivel de VNIC individual.",
        explanation="Es un concepto importante de seguridad.",
    )
    report_no_trap = judge_service.evaluate_card_heuristic(no_trap_card)
    assert report_no_trap.scores["HYPERCORRECTION_FEEDBACK"].passed is False
    assert report_no_trap.scores["HYPERCORRECTION_FEEDBACK"].score <= 0.50
    assert any("trampa frecuente" in f.lower() for f in report_no_trap.scores["HYPERCORRECTION_FEEDBACK"].flaws)


@pytest.mark.asyncio
async def test_audit_l4_end_to_end_gemini_llm_judge(judge_service: PedagogicalJudgeService):
    """
    AUDIT L4.6: End-to-End LLM-as-a-Judge Evaluation Pipeline.
    Verifies that the LLM evaluator (or resilient heuristic fallback if quota constrained)
    generates a multi-dimensional report with normalized scores and certification verdict.
    """
    candidate_card = Flashcard(
        card_type=CardType.BASIC,
        archetype="Arquetipo C: Pregunta Atómica",
        front="[Cloud Architecture > Storage > Object Storage] ¿Qué clase de almacenamiento se recomienda para datos con acceso inferior a una vez al mes pero recuperación inmediata?",
        back="Infrequent Access (o Cool tier).",
        explanation=(
            "Infrequent Access ofrece menor costo de almacenamiento con retención mínima de 31 días y acceso inmediato.\n"
            "⚠️ Trampa frecuente / Error común: Confundir con Archive Storage, el cual requiere desarchivar durante horas antes de poder leer los datos."
        ),
    )
    source_chunk = """
    Object Storage offers multiple storage tiers: Standard (hot data, immediate access, no minimum retention),
    Infrequent Access (cool data, accessed less than once a month, immediate millisecond retrieval, 31-day minimum retention),
    and Archive Storage (cold data, rare access, retrieval time of 1-4 hours, 90-day minimum retention).
    """
    contract = LearningPlanContract(
        deck_name="Cloud::Storage",
        bloom_level="Diseño y Selección Tecnológica",
        exclusion_boundary=["Pricing tables exactos"],
        gap_strategy="fill_all_anchors",
        operational_depth="Comprensión de SLAs y trade-offs de arquitectura",
        status="approved",
    )

    report = await judge_service.evaluate_card_with_llm(
        card=candidate_card,
        source_chunk=source_chunk,
        contract=contract,
    )

    # Validate schema integrity and invariants
    assert isinstance(report, PedagogicalJudgeReport)
    assert 0.0 <= report.overall_score <= 1.0
    assert len(report.scores) == 5
    for criterion in ["ATOMICITY", "CONTEXT_INDEPENDENCE", "FAITHFULNESS", "BLOOM_CONTRACT_ALIGNMENT", "HYPERCORRECTION_FEEDBACK"]:
        assert criterion in report.scores
        score_detail = report.scores[criterion]
        assert 0.0 <= score_detail.score <= 1.0
        assert isinstance(score_detail.passed, bool)
        assert len(score_detail.reasoning) > 0

    # For this well-constructed card, it should achieve certification
    assert report.is_certified is True
    assert report.verdict == "CERTIFIED"
    assert report.overall_score >= 0.85
