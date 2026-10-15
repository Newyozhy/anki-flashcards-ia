import pytest
from app.core.card_sorter import sort_flashcards_pedagogically, get_card_pedagogical_rank
from app.domain.models import Flashcard, CardType


def test_get_card_pedagogical_rank():
    # Tier 0: Prerequisite / Anchor
    card_prereq = Flashcard(
        front="[Fundamentos > Redes] ¿Qué es una máscara CIDR?",
        back="/24 equivale a 256 IPs",
        tags=["prerrequisito"],
    )
    assert get_card_pedagogical_rank(card_prereq) == 0

    # Tier 1: Definition / Core Purpose
    card_def = Flashcard(
        archetype="C",
        front="[OCI > Networking] ¿Qué problema resuelve una VCN en la nube?",
        back="Aislamiento lógico de red para cargas de trabajo.",
    )
    assert get_card_pedagogical_rank(card_def) == 1

    # Tier 2: Causal Mechanism
    card_causal = Flashcard(
        archetype="A",
        card_type=CardType.CLOZE,
        front="[OCI > Networking] Una subnet privada {{c1::bloquea}} el tráfico directo hacia Internet.",
        back="",
    )
    assert get_card_pedagogical_rank(card_causal) == 2

    # Tier 3: Matrix / Trap
    card_trap = Flashcard(
        archetype="B",
        front="[OCI > Networking] Tabla comparativa entre NAT Gateway y Service Gateway",
        back="",
        explanation="⚠️ Trampa frecuente: Confundir NAT Gateway (Internet saliente) con Service Gateway (servicios internos OCI).",
    )
    assert get_card_pedagogical_rank(card_trap) == 3


def test_sort_flashcards_pedagogically():
    c_trap = Flashcard(
        id="c_trap",
        archetype="B",
        front="[OCI] Diferencia clave entre Security List y NSG",
        back="SL a nivel de subnet, NSG a nivel de VNIC",
        explanation="⚠️ Trampa frecuente: Creer que NSG reemplaza el enrutamiento de la Route Table.",
    )
    c_causal = Flashcard(
        id="c_causal",
        archetype="C",
        front="[OCI] ¿Por qué un Route Table requiere una regla hacia el Internet Gateway?",
        back="Para habilitar la salida y entrada pública en subnets públicas.",
    )
    c_def = Flashcard(
        id="c_def",
        archetype="C",
        front="[OCI] ¿Qué es una Virtual Cloud Network (VCN)?",
        back="Una red privada virtual definida por software en OCI.",
    )
    c_prereq = Flashcard(
        id="c_prereq",
        front="[Fundamentos > Redes] ¿Qué define el bloque CIDR IPv4?",
        back="El rango contiguo de direcciones IP asignadas a una red.",
        tags=["prerrequisito"],
    )

    unordered = [c_trap, c_causal, c_def, c_prereq]
    ordered = sort_flashcards_pedagogically(unordered)

    # Ascending cognitive scaffold: Prerequisite -> Definition -> Mechanism -> Trap
    assert [c.id for c in ordered] == ["c_prereq", "c_def", "c_causal", "c_trap"]


def test_metcalfe_hypercorrection_in_explanation_does_not_corrupt_tier():
    """G-01 regression: Ensure definition card with 'trampa frecuente' in explanation is Tier 1, not Tier 3."""
    c_def = Flashcard(
        archetype="C",
        front="¿Qué es una Virtual Cloud Network (VCN)?",
        back="Red privada definida por software.",
        explanation="⚠️ Trampa frecuente / Error común: Confundir VCN con una subred física.",
    )
    assert get_card_pedagogical_rank(c_def) == 1

    c_cloze = Flashcard(
        archetype="A",
        card_type=CardType.CLOZE,
        front="{{c1::OSPF}} calcula rutas dinámicamente mediante Dijkstra.",
        back="",
        explanation="⚠️ Trampa frecuente / Error común: Confundir OSPF con RIP o BGP.",
    )
    assert get_card_pedagogical_rank(c_cloze) == 2
