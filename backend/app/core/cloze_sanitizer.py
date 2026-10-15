import re
from typing import List, Tuple, Dict
from app.domain.models import Flashcard, CardType


class ClozeSanitizer:
    """
    Deterministic Cloze & Anki Syntax Sanitizer.
    Guarantees that all Cloze cards satisfy Anki's compiler invariants,
    eliminating the 'No cloze 1 found on card' error and preventing
    front-side retrieval leaks in previews.
    """

    # Matches malformed triple braces: {{{...}}} -> {{...}}
    TRIPLE_BRACE_RE = re.compile(r"\{\{\{\s*(.*?)\s*\}\}\}")

    # Matches single-brace cloze attempts: {c1::word} -> {{c1::word}}
    SINGLE_BRACE_CLOZE_RE = re.compile(r"(?<!\{)\{\s*([cC]\d+\s*::[^{}]+?)\}(?!\})")

    # Matches standard Anki clozes: {{c1::answer}} or {{c1::answer::hint}}
    STANDARD_CLOZE_RE = re.compile(
        r"\{\{\s*[cC](\d+)\s*::\s*([^}]+?)(?:\s*::\s*([^}]+?))?\s*\}\}",
        re.DOTALL,
    )

    # Matches clozes with digit only (missing 'c'): {{1::answer}}
    MISSING_C_CLOZE_RE = re.compile(
        r"\{\{\s*(\d+)\s*::\s*([^}]+?)(?:\s*::\s*([^}]+?))?\s*\}\}",
        re.DOTALL,
    )

    # Matches bare unindexed clozes: {{word}} or {{word::hint}} where inside has no c\d+::
    BARE_CLOZE_RE = re.compile(
        r"\{\{\s*(?![cC]?\d+\s*::)([^}]+?)\s*\}\}",
        re.DOTALL,
    )

    @classmethod
    def sanitize_text(cls, text: str, ensure_c1: bool = True) -> Tuple[str, List[int]]:
        """
        Sanitize any cloze deletions in the given string.
        Returns:
            (sanitized_text, list_of_cloze_indices_found)
        """
        if not text:
            return "", []

        result = text

        # 1. Normalize triple braces {{{foo}}} -> {{foo}}
        result = cls.TRIPLE_BRACE_RE.sub(r"{{\1}}", result)

        # 2. Normalize single-brace cloze {c1::foo} -> {{c1::foo}}
        result = cls.SINGLE_BRACE_CLOZE_RE.sub(r"{{\1}}", result)

        # 3. Normalize missing 'c': {{1::foo}} -> {{c1::foo}}
        result = cls.MISSING_C_CLOZE_RE.sub(r"{{c\1::\2}}", result)

        # 4. Repair bare unindexed clozes: {{word}} -> {{c{idx}::word}}
        existing_indices = [int(m.group(1)) for m in cls.STANDARD_CLOZE_RE.finditer(result)]
        next_idx = max(existing_indices) + 1 if existing_indices else 1

        def _bare_replacer(match: re.Match) -> str:
            nonlocal next_idx
            inner = match.group(1).strip()
            parts = inner.split("::", 1)
            cloze_idx = next_idx
            next_idx += 1
            if len(parts) == 2:
                word, hint = parts[0].strip(), parts[1].strip()
                return f"{{{{c{cloze_idx}::{word}::{hint}}}}}"
            return f"{{{{c{cloze_idx}::{inner}}}}}"

        result = cls.BARE_CLOZE_RE.sub(_bare_replacer, result)

        # 5. Index Re-sequencing Pass: Guarantee c1 and contiguity (c1, c2, c3...)
        all_matches = list(cls.STANDARD_CLOZE_RE.finditer(result))
        if not all_matches:
            return result, []

        if ensure_c1:
            index_mapping: Dict[str, int] = {}
            for m in all_matches:
                orig_idx = m.group(1)
                if orig_idx not in index_mapping:
                    index_mapping[orig_idx] = len(index_mapping) + 1

            def _canonical_reindex(match: re.Match) -> str:
                orig_idx = match.group(1)
                new_idx = index_mapping[orig_idx]
                content = match.group(2).strip()
                hint = match.group(3)
                if hint and hint.strip():
                    return f"{{{{c{new_idx}::{content}::{hint.strip()}}}}}"
                return f"{{{{c{new_idx}::{content}}}}}"

            result = cls.STANDARD_CLOZE_RE.sub(_canonical_reindex, result)

        final_indices = [int(m.group(1)) for m in cls.STANDARD_CLOZE_RE.finditer(result)]
        return result, final_indices

    @classmethod
    def unwrap_clozes(cls, text: str) -> str:
        """Strip cloze markers and reveal inner target text, e.g. {{c1::target}} -> target."""
        if not text:
            return ""
        # 1. Clean triple/single braces first
        res = cls.TRIPLE_BRACE_RE.sub(r"{{\1}}", text)
        res = cls.SINGLE_BRACE_CLOZE_RE.sub(r"{{\1}}", res)
        res = cls.MISSING_C_CLOZE_RE.sub(r"{{c\1::\2}}", res)
        # 2. Replace standard {{cN::target::hint}} or {{cN::target}} -> target
        res = cls.STANDARD_CLOZE_RE.sub(r"\2", res)
        # 3. Replace bare {{target}} -> target
        res = cls.BARE_CLOZE_RE.sub(r"\1", res)
        return res

    @classmethod
    def extract_cloze_targets(cls, text: str) -> List[Tuple[str, str, int]]:
        """
        Extract all cloze deletions from text.
        Returns a list of tuples: (full_cloze_string, inner_target_text, word_count)
        """
        if not text:
            return []
        matches = cls.STANDARD_CLOZE_RE.finditer(text)
        targets = []
        for m in matches:
            full = m.group(0)
            target = m.group(2).strip()
            word_count = len(target.split())
            targets.append((full, target, word_count))
        return targets

    @classmethod
    def sanitize_card(cls, card: Flashcard) -> Flashcard:
        """
        Sanitizes a Flashcard entity in-place and guarantees domain invariant alignment:
        - Repairs malformed front cloze deletions.
        - Unwraps accidental cloze syntax in back field for Basic cards.
        - Synchronizes card_type between BASIC and CLOZE.
        """
        sanitized_front, indices = cls.sanitize_text(card.front)
        card.front = sanitized_front
        has_front_clozes = len(indices) > 0

        # Check and remediate back field contamination
        if card.back and ("{{" in card.back or "{c" in card.back):
            if card.card_type == CardType.BASIC or not has_front_clozes:
                card.back = cls.unwrap_clozes(card.back)

        # Sync card_type
        if card.card_type == CardType.CLOZE:
            if not has_front_clozes:
                if card.back and card.back.strip():
                    card.card_type = CardType.BASIC
                else:
                    bold_match = re.search(r"\*\*(.+?)\*\*", card.front)
                    if bold_match:
                        target = bold_match.group(1)
                        card.front = card.front.replace(f"**{target}**", f"{{{{c1::{target}}}}}")
                        card.card_type = CardType.CLOZE
                    else:
                        card.card_type = CardType.BASIC
        elif card.card_type == CardType.BASIC and has_front_clozes:
            card.card_type = CardType.CLOZE

        return card
