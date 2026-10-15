import logging
import re
from typing import List, Tuple, Optional, Dict
from uuid import uuid4

from app.domain.models import (
    Flashcard,
    CardType,
    CognitiveAuditFinding,
    CardAuditResult,
    DeckAuditReport,
)
from app.core.cloze_sanitizer import ClozeSanitizer
from app.core.formatting import extract_breadcrumb_and_body

logger = logging.getLogger(__name__)


class CognitiveAuditorService:
    """
    Neurocognitive Quality Auditor & Anki Linter.
    Audits generated flashcards against learning science laws:
    - Minimum Information Principle (Piotr Wozniak) via Sister Card decomposition.
    - Anki Cloze Syntax Integrity (eliminates 'No cloze 1' errors and preview leaks).
    - Grammatical Priming Prevention (absorbs leading gender/number articles).
    - Hypercorrection Protocol (Janet Metcalfe) enforcement.
    """

    ARTICLE_PRIMER_RE = re.compile(
        r"\b(el|la|los|las|un|una|unos|unas)\s+(\{\{\s*[cC]\d+::[^}]+?\}\})",
        re.IGNORECASE,
    )

    HYPERCORRECTION_TRIGGER = "⚠️ Trampa frecuente / Error común:"

    def __init__(self, sanitizer: Optional[ClozeSanitizer] = None):
        self._sanitizer = sanitizer or ClozeSanitizer()

    def audit_card(
        self, card: Flashcard, auto_split_sisters: bool = True
    ) -> Tuple[List[Flashcard], CardAuditResult]:
        """
        Audits an individual flashcard, returning a list of compliant/sister flashcards
        and a detailed diagnostic audit result.
        """
        findings: List[CognitiveAuditFinding] = []
        score = 100
        orig_front = card.front

        # 1. Deterministic Syntax Sanitation
        sanitized_front, cloze_indices = self._sanitizer.sanitize_text(card.front)
        if sanitized_front != orig_front:
            findings.append(
                CognitiveAuditFinding(
                    rule="SYNTAX_CLOZE_REPAIRED",
                    severity="WARNING",
                    message="Se corrigió la sintaxis de oclusión defectuosa (ej. {{palabra}} sin ordinal c1::, llaves desbalanceadas o índices no contiguos).",
                    original_snippet=orig_front,
                    corrected_snippet=sanitized_front,
                    auto_fixed=True,
                )
            )
            card.front = sanitized_front

        # 1b. Back Field Cloze Contamination Check (for Basic cards or misplaced cloze in back)
        orig_back = card.back or ""
        if orig_back and ("{{" in orig_back or "{c" in orig_back):
            unwrapped_back = self._sanitizer.unwrap_clozes(orig_back)
            if unwrapped_back != orig_back:
                findings.append(
                    CognitiveAuditFinding(
                        rule="BACK_CLOZE_CONTAMINATION_REPAIRED",
                        severity="WARNING",
                        message="Se desenvolvió la sintaxis cloze {{c1::...}} detectada erróneamente en el reverso de una tarjeta.",
                        original_snippet=orig_back,
                        corrected_snippet=unwrapped_back,
                        auto_fixed=True,
                    )
                )
                card.back = unwrapped_back

        # 1c. Empty or Orphan Breadcrumb Front Check
        has_only_breadcrumb = bool(re.match(r"^\[.*?\]\s*$", card.front.strip()))
        breadcrumb, body = extract_breadcrumb_and_body(card.front)
        if not card.front.strip() or not body.strip() or has_only_breadcrumb:
            score -= 25
            findings.append(
                CognitiveAuditFinding(
                    rule="EMPTY_FRONT_BODY",
                    severity="VIOLATION",
                    message="El frente de la tarjeta no contiene cuerpo textual de pregunta o contexto (solo taxonomía o vacío).",
                    original_snippet=card.front,
                    corrected_snippet=card.front,
                    auto_fixed=False,
                )
            )

        card = self._sanitizer.sanitize_card(card)

        # 2. Grammar Primer Remediation (Article Absorption)
        if card.card_type == CardType.CLOZE:
            def _absorb_article(m: re.Match) -> str:
                article = m.group(1)
                cloze_body = m.group(2)
                # Convert "la {{c1::mitosis}}" -> "{{c1::la mitosis}}"
                return re.sub(r"\{\{[cC](\d+)::(.+?)\}\}", rf"{{{{c\1::{article} \2}}}}", cloze_body)

            if self.ARTICLE_PRIMER_RE.search(card.front):
                before_primer = card.front
                card.front = self.ARTICLE_PRIMER_RE.sub(_absorb_article, card.front)
                findings.append(
                    CognitiveAuditFinding(
                        rule="RETRIEVAL_LEAK_GRAMMAR_PRIMED",
                        severity="WARNING",
                        message="Se absorbió el artículo determinante precedente dentro de la oclusión para evitar dar pistas morfológicas involuntarias de género o número.",
                        original_snippet=before_primer,
                        corrected_snippet=card.front,
                        auto_fixed=True,
                    )
                )

        # 3. Hypercorrection & Common Trap Enforcement
        explanation = card.explanation or ""
        if self.HYPERCORRECTION_TRIGGER.lower() not in explanation.lower():
            score -= 15
            before_expl = card.explanation
            scaffold = (
                f"\n\n{self.HYPERCORRECTION_TRIGGER} Distinguir este concepto de sus análogos inmediatos para evitar interferencia proactiva en el repaso."
            )
            card.explanation = (explanation.strip() + scaffold).strip()
            findings.append(
                CognitiveAuditFinding(
                    rule="HYPERCORRECTION_SECTION_INJECTED",
                    severity="INFO",
                    message="Se inyectó la sección de advertencia de error común para activar el Efecto de Hipercorrección (Janet Metcalfe).",
                    original_snippet=before_expl,
                    corrected_snippet=card.explanation,
                    auto_fixed=True,
                )
            )

        # 4. Word Count Check on Back for Basic Cards (Piotr Wozniak)
        if card.card_type == CardType.BASIC and card.back:
            words = card.back.split()
            if len(words) > 20:
                score -= 10
                findings.append(
                    CognitiveAuditFinding(
                        rule="BACK_WORD_COUNT_HIGH",
                        severity="INFO",
                        message=f"La respuesta dorsal tiene {len(words)} palabras. Se recomienda mantenerla atómica (< 15 palabras) para repaso en menos de 5 segundos.",
                        original_snippet=card.back,
                        corrected_snippet=card.back,
                        auto_fixed=False,
                    )
                )

        # 4b. Cloze Word Count Check (Piotr Wozniak Minimum Information Principle)
        if card.card_type == CardType.CLOZE:
            cloze_targets = self._sanitizer.extract_cloze_targets(card.front)
            for full_cloze, target, word_count in cloze_targets:
                if word_count > 4:
                    score -= 15
                    concise_target = target.strip()
                    cleaned = re.sub(r"^(la descomposición de(l)?|el desglose de(l)?|un estado o)\s+", "", concise_target, flags=re.I)
                    cleaned = re.sub(r"\s+o\s+pasos\s+intermedios", "", cleaned, flags=re.I)

                    # 1. Try trimming trailing circumstantial prepositional clauses (e.g. 'en el mundo real', 'en tiempo real')
                    trimmed_clause = re.sub(r"\s+(?:en|hacia|sobre|para|por)\s+.*$", "", cleaned, flags=re.I).strip()
                    trimmed_words = trimmed_clause.split()

                    cleaned_words = cleaned.split()
                    if 1 <= len(trimmed_words) <= 3:
                        concise_target = trimmed_clause
                    elif len(cleaned_words) <= 3:
                        if cleaned.lower().startswith("razonamiento"):
                            concise_target = f"el {cleaned}"
                        else:
                            concise_target = cleaned
                    else:
                        # 2. Extract syntactic head noun phrase preserving connectors (e.g., 'capacidades de acción')
                        m_prep = re.match(r"^(\w+\s+(?:de|del|para|por)\s+\w+)", cleaned, flags=re.I)
                        if m_prep and len(m_prep.group(1).split()) <= 3:
                            concise_target = m_prep.group(1)
                        else:
                            core_words = [w for w in cleaned.split() if w.lower() not in {"un", "una", "el", "la", "o", "los", "las"}]
                            concise_target = " ".join(core_words[:2]) if len(core_words) >= 2 else target

                    suggested_replacement = full_cloze.replace(target, concise_target, 1)

                    findings.append(
                        CognitiveAuditFinding(
                            rule="CLOZE_WORD_COUNT_HIGH",
                            severity="WARNING",
                            message=(
                                f"La oclusión '{target}' contiene {word_count} palabras. "
                                "Viola el Principio de Información Mínima de Wozniak. "
                                "Las oclusiones deben restringirse a 1-3 palabras clave para garantizar recuerdo activo y evitar memorización textual."
                            ),
                            original_snippet=full_cloze,
                            corrected_snippet=concise_target,
                            suggested_replacement=suggested_replacement,
                            auto_fixed=False,
                        )
                    )

        # 4c. Dual-Coding Theory Diagram Verification (Allan Paivio)
        all_text = f"{card.front} {card.back or ''} {card.explanation or ''}"
        if re.search(r'<img[^>]+src=["\']([^"\']+)["\']', all_text, re.IGNORECASE):
            findings.append(
                CognitiveAuditFinding(
                    rule="DIAGRAM_INHERITED",
                    severity="INFO",
                    message="Diagrama visual preservado exitosamente en la tarjeta atómica para soporte de codificación dual (Paivio).",
                    original_snippet="",
                    corrected_snippet="",
                    auto_fixed=False,
                )
            )

        # 5. Atomicity & Multi-Cloze Sister Card Decomposition
        resulting_cards: List[Flashcard] = []
        if card.card_type == CardType.CLOZE:
            cloze_matches = list(self._sanitizer.STANDARD_CLOZE_RE.finditer(card.front))
            num_clozes = len(cloze_matches)

            if num_clozes > 1:
                findings.append(
                    CognitiveAuditFinding(
                        rule="ATOMICITY_MULTI_CLOZE_SPLIT",
                        severity="VIOLATION",
                        message=(
                            f"Infracción de atomicidad: la tarjeta evaluaba {num_clozes} conceptos simultáneamente. "
                            f"Se desacopló automáticamente en {num_clozes} tarjetas hermanas atómicas (c1 y c2) con un solo esfuerzo mental cada una."
                        ),
                        original_snippet=card.front,
                        corrected_snippet=f"Desacoplada en {num_clozes} tarjetas hermanas",
                        auto_fixed=auto_split_sisters,
                    )
                )

                if auto_split_sisters:
                    resulting_cards = self._split_into_sister_cards(card, cloze_matches)
                else:
                    resulting_cards = [card]
            else:
                resulting_cards = [card]
        else:
            resulting_cards = [card]

        preview = card.front[:70] + "..." if len(card.front) > 70 else card.front
        audit_result = CardAuditResult(
            card_id=card.id,
            card_front_preview=preview,
            passed=score >= 70,
            score=max(0, score),
            findings=findings,
            sister_cards_count=len(resulting_cards),
        )

        return resulting_cards, audit_result

    def _split_into_sister_cards(
        self, original: Flashcard, matches: List[re.Match]
    ) -> List[Flashcard]:
        """
        Decomposes a multi-cloze card into N atomic Sister Cards.
        In Sister Card i:
        - Cloze i remains active as {{c1::target}}
        - All other clozes j != i are revealed as plain unmasked text.
        """
        sister_cards: List[Flashcard] = []
        total_sisters = len(matches)

        for i, active_match in enumerate(matches):
            new_front = original.front
            # Replace in reverse order so string spans remain stable
            for actual_idx, m in reversed(list(enumerate(matches))):
                answer_text = m.group(2).strip()
                if actual_idx == i:
                    # Active cloze: always force ordinal to c1 for strict single-card atomicity
                    hint = m.group(3)
                    replacement = (
                        f"{{{{c1::{answer_text}::{hint.strip()}}}}}"
                        if hint
                        else f"{{{{c1::{answer_text}}}}}"
                    )
                else:
                    # Passive context: reveal as plain text
                    replacement = answer_text

                start, end = m.span()
                new_front = new_front[:start] + replacement + new_front[end:]

            sister_tags = list(
                dict.fromkeys(
                    original.tags + ["tarjeta-hermana", f"hermana-{i+1}-de-{total_sisters}"]
                )
            )
            active_answer = active_match.group(2).strip()

            sister = Flashcard(
                id=str(uuid4()),
                card_type=CardType.CLOZE,
                archetype=(
                    f"{original.archetype} (Hermana {i+1}/{total_sisters})"
                    if original.archetype
                    else None
                ),
                front=new_front,
                back=active_answer,
                tags=sister_tags,
                explanation=original.explanation,
            )
            sister_cards.append(sister)

        return sister_cards

    def audit_deck(
        self, cards: List[Flashcard], auto_split_sisters: bool = True
    ) -> Tuple[List[Flashcard], DeckAuditReport]:
        """
        Audits an entire collection of flashcards, returning the refined, compliant
        flashcards and an aggregated audit report for UI transparency.
        """
        final_cards: List[Flashcard] = []
        card_reports: List[CardAuditResult] = []
        total_repaired = 0
        total_sisters = 0
        scores: List[int] = []

        for card in cards:
            resulting_cards, report = self.audit_card(card, auto_split_sisters=auto_split_sisters)
            card_reports.append(report)
            final_cards.extend(resulting_cards)
            scores.append(report.score)

            if any(f.auto_fixed for f in report.findings):
                total_repaired += 1
            if report.sister_cards_count > 1:
                total_sisters += report.sister_cards_count

        # Batch duplicate and redundancy detection pass
        seen_questions: Dict[str, str] = {}
        for card, report in zip(cards, card_reports):
            breadcrumb, body = extract_breadcrumb_and_body(card.front)
            clean_body = re.sub(r"\{\{[cC]\d+::([^}]+?)(?:::.*?)?\}\}", r"\1", body)
            norm = re.sub(r"[^\w\s]", "", clean_body.lower())
            norm = " ".join(norm.split())
            if norm and len(norm) > 15:
                if norm in seen_questions:
                    report.score = max(0, report.score - 25)
                    report.passed = report.score >= 70
                    report.findings.append(
                        CognitiveAuditFinding(
                            rule="DUPLICATE_CARD_IN_BATCH",
                            severity="VIOLATION",
                            message="Se detectó redundancia léxica directa o pregunta duplicada con otra tarjeta del lote.",
                            original_snippet=card.front,
                            corrected_snippet="Eliminar o fusionar tarjeta redundante",
                            auto_fixed=False,
                        )
                    )
                else:
                    seen_questions[norm] = card.id

        scores = [r.score for r in card_reports]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 100.0

        deck_report = DeckAuditReport(
            total_cards_audited=len(cards),
            total_cards_repaired=total_repaired,
            total_sister_cards_created=total_sisters,
            average_quality_score=avg_score,
            card_reports=card_reports,
        )

        logger.info(
            "Cognitive Auditor completed: %d cards audited, %d repaired, %d sisters created, avg score: %.1f",
            len(cards),
            total_repaired,
            total_sisters,
            avg_score,
        )

        return final_cards, deck_report
