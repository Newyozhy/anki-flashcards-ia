"""Deterministic pedagogical card sorter enforcing Bloom cognitive scaffolding (0-LLM)."""

from typing import List
from app.domain.models import Flashcard, CardType


def get_card_pedagogical_rank(card: Flashcard) -> int:
    """Calculate the integer cognitive tier (0 to 3) for a flashcard.
    
    Tier 0: Anchors & Prerequisite concepts (Scaffolding foundation).
    Tier 1: Functional definition, identity, and problem solved.
    Tier 2: Causal mechanics, inner workings, and 'why' relationships.
    Tier 3: Contrast matrices, edge cases, discrimination, and traps.
    """
    front = (card.front or "").lower()
    tags = [t.lower() for t in (card.tags or [])]
    arch = (card.archetype or "").upper()
    explanation = (card.explanation or "").lower()

    # Tier 0: Explicit prerequisites or mental model anchors
    if "prerrequisito" in tags or "prerequisite" in tags or "[fundamentos" in front or "[prerrequisito" in front:
        return 0

    # Tier 1: Functional definition / core purpose ("¿Qué es?", "¿Para qué sirve?", "¿Qué problema resuelve?")
    definition_signals = ("qué es", "que es", "definición", "definicion", "propósito", "proposito", "qué problema resuelve")
    if (arch in ("C", "BASIC", "D") and any(sig in front for sig in definition_signals)) or (
        arch in ("C", "BASIC", "D") and not any(sig in front for sig in ("por qué", "por que", "causa", "cómo funciona"))
    ):
        return 1

    # Tier 2: Causal mechanics and Cloze dynamics ("¿Por qué...?", "¿Cuál es la causa...?", Cloze reversals)
    causal_signals = ("por qué", "por que", "causa", "mecanismo", "cómo funciona", "como funciona", "consecuencia")
    if arch in ("A", "CLOZE") or card.card_type == CardType.CLOZE or any(sig in front for sig in causal_signals):
        return 2

    # Tier 3: Contrast matrices, applied mini-scenarios, and explicit error inquiries in prompt
    trap_front_signals = ("trampa frecuente", "error común", "error comun", "distinción", "distincion", "diferencia")
    if arch in ("B", "E") or "matriz" in tags or any(sig in front for sig in trap_front_signals):
        return 3

    # Fallback: Tier 1 if definition signal present, otherwise Tier 2
    if any(sig in front for sig in definition_signals):
        return 1
    return 2


def sort_flashcards_pedagogically(cards: List[Flashcard]) -> List[Flashcard]:
    """Sort a batch of atomized cards in ascending cognitive complexity (0-LLM, stable sort)."""
    if not cards or len(cards) <= 1:
        return list(cards)

    return sorted(cards, key=get_card_pedagogical_rank)
