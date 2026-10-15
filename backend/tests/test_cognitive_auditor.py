import pytest
from app.core.cloze_sanitizer import ClozeSanitizer
from app.domain.models import Flashcard, CardType
from app.services.cognitive_auditor_service import CognitiveAuditorService


def test_cloze_sanitizer_bare_cloze_repair():
    """Verify bare clozes {{word}} are automatically repaired to {{c1::word}}."""
    text = "El protocolo TCP encapsula los datos en {{segmento}} antes de pasarlos a IP."
    sanitized, indices = ClozeSanitizer.sanitize_text(text)
    assert "{{c1::segmento}}" in sanitized
    assert indices == [1]


def test_cloze_sanitizer_triple_braces_and_missing_c():
    """Verify {{{word}}} and {{1::word}} are correctly normalized."""
    text = "La capa {{{c1::Enlace}}} transmite tramas y la capa {{2::Red}} paquetes."
    sanitized, indices = ClozeSanitizer.sanitize_text(text)
    assert "{{c1::Enlace}}" in sanitized
    assert "{{c2::Red}}" in sanitized
    assert indices == [1, 2]


def test_cloze_sanitizer_non_contiguous_reindexing():
    """Verify non-contiguous cloze ordinals (c2, c5) are normalized to (c1, c2)."""
    text = "Concepto A: {{c3::primero}} y Concepto B: {{c7::segundo}}."
    sanitized, indices = ClozeSanitizer.sanitize_text(text)
    assert "{{c1::primero}}" in sanitized
    assert "{{c2::segundo}}" in sanitized
    assert indices == [1, 2]


def test_cloze_sanitizer_card_type_sync():
    """Verify Flashcard entity card_type is synchronized with cloze presence."""
    card = Flashcard(
        card_type=CardType.BASIC,
        front="La fotosíntesis ocurre en el {{cloroplasto}}.",
        back="Detalle",
        tags=["biologia"],
    )
    sanitized_card = ClozeSanitizer.sanitize_card(card)
    assert sanitized_card.card_type == CardType.CLOZE
    assert "{{c1::cloroplasto}}" in sanitized_card.front


def test_cognitive_auditor_sister_card_split():
    """
    Verify that multi-cloze cards violate atomicity and are decomposed into
    two atomic Sister Cards, each exercising a single mental effort.
    """
    auditor = CognitiveAuditorService()
    multi_cloze_card = Flashcard(
        card_type=CardType.CLOZE,
        archetype="Arquetipo A: Cloze Contextualizado Causal",
        front="[Redes > Capas] En la capa de transporte la PDU es el {{c1::segmento}}, mientras que en red es el {{c2::paquete}}.",
        back="",
        tags=["redes", "protocolos"],
        explanation="Cada capa tiene su PDU propia.\n\n⚠️ Trampa frecuente / Error común: Confundir trama con paquete.",
    )

    resulting_cards, audit_result = auditor.audit_card(multi_cloze_card, auto_split_sisters=True)

    assert len(resulting_cards) == 2
    assert audit_result.sister_cards_count == 2
    assert any(f.rule == "ATOMICITY_MULTI_CLOZE_SPLIT" for f in audit_result.findings)

    # Sister Card 1: Active c1 is "el segmento" (article absorbed), "paquete" is plain text
    sister_1 = resulting_cards[0]
    assert "{{c1::el segmento}}" in sister_1.front
    assert "{{c" not in sister_1.front.replace("{{c1::el segmento}}", "")
    assert "paquete" in sister_1.front
    assert sister_1.back == "el segmento"
    assert "tarjeta-hermana" in sister_1.tags
    assert "hermana-1-de-2" in sister_1.tags

    # Sister Card 2: Active c1 is "el paquete" (article absorbed), "el segmento" is plain text
    sister_2 = resulting_cards[1]
    assert "{{c1::el paquete}}" in sister_2.front
    assert "{{c" not in sister_2.front.replace("{{c1::el paquete}}", "")
    assert "el segmento" in sister_2.front
    assert sister_2.back == "el paquete"
    assert "tarjeta-hermana" in sister_2.tags
    assert "hermana-2-de-2" in sister_2.tags


def test_cognitive_auditor_grammatical_article_absorption():
    """Verify that preceding articles ('la', 'el') are absorbed inside the cloze to prevent gender leaks."""
    auditor = CognitiveAuditorService()
    primed_card = Flashcard(
        card_type=CardType.CLOZE,
        front="[Biología] La división nuclear de células somáticas se denomina la {{c1::mitosis}}.",
        back="",
        tags=["biologia"],
        explanation="Ocurre en células somáticas.\n\n⚠️ Trampa frecuente / Error común: Confundir con meiosis.",
    )

    resulting_cards, audit_result = auditor.audit_card(primed_card)
    card = resulting_cards[0]
    assert "{{c1::la mitosis}}" in card.front
    assert "la {{c1::" not in card.front
    assert any(f.rule == "RETRIEVAL_LEAK_GRAMMAR_PRIMED" for f in audit_result.findings)


def test_cognitive_auditor_hypercorrection_injection():
    """Verify hypercorrection section is injected if missing from explanation."""
    auditor = CognitiveAuditorService()
    bare_explanation_card = Flashcard(
        card_type=CardType.BASIC,
        front="[Física > Dinámica] ¿Qué establece la primera ley de Newton?",
        back="Inercia de los cuerpos en reposo o MRU.",
        tags=["fisica"],
        explanation="Formulada por Isaac Newton en 1687.",
    )

    resulting_cards, audit_result = auditor.audit_card(bare_explanation_card)
    card = resulting_cards[0]
    assert "⚠️ Trampa frecuente / Error común:" in card.explanation
    assert any(f.rule == "HYPERCORRECTION_SECTION_INJECTED" for f in audit_result.findings)


def test_cognitive_auditor_deck_audit():
    """Verify whole-deck audit report aggregation and scoring."""
    auditor = CognitiveAuditorService()
    cards = [
        Flashcard(
            card_type=CardType.BASIC,
            front="[Química] ¿Cuál es el número atómico del Carbono?",
            back="6",
            tags=["quimica"],
            explanation="Posee 6 protones.\n\n⚠️ Trampa frecuente / Error común: Confundir con masa atómica (12).",
        ),
        Flashcard(
            card_type=CardType.CLOZE,
            front="[Redes] El protocolo HTTP utiliza el puerto {{80}} y HTTPS el {{443}}.",
            back="",
            tags=["redes"],
            explanation="Puertos estándar.\n\n⚠️ Trampa frecuente / Error común: Confundir con DNS (53).",
        ),
    ]

    final_cards, deck_report = auditor.audit_deck(cards)

    # 1 basic card + 2 sister cards from the multi-cloze
    assert len(final_cards) == 3
    assert deck_report.total_cards_audited == 2
    assert deck_report.total_cards_repaired >= 1
    assert deck_report.total_sister_cards_created == 2
    assert deck_report.average_quality_score > 0
    assert len(deck_report.card_reports) == 2


def test_cognitive_auditor_back_cloze_contamination_repair():
    """Verify cloze tags in Back field of Basic cards are cleanly unwrapped."""
    auditor = CognitiveAuditorService()
    card = Flashcard(
        card_type=CardType.BASIC,
        front="[Oracle Cloud > ReAct] ¿Qué mecanismo de ReAct reduce drásticamente la tasa de alucinaciones?",
        back="{{c1::El grounding de datos externos mediante acciones en el entorno}}.",
        tags=["ia", "react"],
        explanation="⚠️ Trampa frecuente / Error común: Asumir que CoT-only hace grounding.",
    )

    resulting_cards, result = auditor.audit_card(card)
    assert len(resulting_cards) == 1
    repaired_card = resulting_cards[0]
    assert repaired_card.card_type == CardType.BASIC
    assert "{{c1::" not in repaired_card.back
    assert "El grounding de datos externos mediante acciones en el entorno." in repaired_card.back
    assert any(f.rule == "BACK_CLOZE_CONTAMINATION_REPAIRED" for f in result.findings)


def test_cognitive_auditor_cloze_word_count_high_warning():
    """Verify clozes exceeding Wozniak's minimum information principle (>4 words) are penalized."""
    auditor = CognitiveAuditorService()
    card = Flashcard(
        card_type=CardType.CLOZE,
        front="[AI] ReAct permite a un LLM resolver tareas complejas mediante {{c1::la intercalación de razonamiento y acciones con observaciones}}.",
        back="",
        tags=["ai"],
        explanation="⚠️ Trampa frecuente / Error común: Creer que la observación la genera el LLM.",
    )

    resulting_cards, result = auditor.audit_card(card)
    assert any(f.rule == "CLOZE_WORD_COUNT_HIGH" for f in result.findings)
    assert result.score < 100


def test_cognitive_auditor_batch_duplicate_detection():
    """Verify lexical duplicate questions in the same batch are detected."""
    auditor = CognitiveAuditorService()
    cards = [
        Flashcard(
            card_type=CardType.BASIC,
            front="[AI] ¿Qué es el patrón ReAct en inteligencia artificial?",
            back="Un patrón que intercala razonamiento y acciones.",
            tags=["ai"],
            explanation="⚠️ Trampa frecuente / Error común: Confundir con CoT.",
        ),
        Flashcard(
            card_type=CardType.BASIC,
            front="[AI] ¿Qué es el patrón ReAct en inteligencia artificial?",
            back="Es un enfoque iterativo de thought y action.",
            tags=["ai"],
            explanation="⚠️ Trampa frecuente / Error común: Confundir con CoT.",
        ),
    ]

    final_cards, deck_report = auditor.audit_deck(cards)
    assert any(f.rule == "DUPLICATE_CARD_IN_BATCH" for r in deck_report.card_reports for f in r.findings)


def test_cognitive_auditor_cloze_phrase_preserves_natural_preposition():
    """
    Verify that long cloze phrases with prepositions like 'capacidades de acción en el mundo real'
    are contracted to grammatically natural 2-3 word phrases like 'capacidades de acción'
    instead of stripping prepositions into unnatural fragments like 'capacidades acción'.
    """
    auditor = CognitiveAuditorService()
    card = Flashcard(
        card_type=CardType.CLOZE,
        front="[Limitations of Standalone CoT > Agency > Action Capability] La incapacidad fundamental del CoT puro es su falta de {{c1::capacidades de acción en el mundo real}}.",
        back="capacidades de acción en el mundo real",
        tags=["cot", "agents"],
    )

    resulting_cards, result = auditor.audit_card(card)
    finding = next((f for f in result.findings if f.rule == "CLOZE_WORD_COUNT_HIGH"), None)
    assert finding is not None
    assert finding.corrected_snippet == "capacidades de acción"
    assert finding.suggested_replacement == "{{c1::capacidades de acción}}"

