import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from app.core.config import settings
from app.domain.models import Flashcard, LearningPlanContract

logger = logging.getLogger(__name__)


class GEvalScoreDetail(BaseModel):
    """Detailed score and diagnostic for a single G-Eval pedagogical criterion."""
    criterion: str
    name: str
    score: float = Field(ge=0.0, le=1.0, description="Normalized score between 0.0 and 1.0")
    threshold: float = Field(ge=0.0, le=1.0, description="Passing threshold gate")
    passed: bool
    reasoning: str
    flaws: List[str] = Field(default_factory=list)


class PedagogicalJudgeReport(BaseModel):
    """Formal audit certificate and multidimensional pedagogical evaluation of a flashcard."""
    overall_score: float = Field(ge=0.0, le=1.0)
    is_certified: bool
    verdict: str = Field(description="'CERTIFIED', 'NEEDS_REFINEMENT', or 'REJECTED'")
    scores: Dict[str, GEvalScoreDetail]
    critical_flaws: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class PedagogicalJudgeService:
    """
    Pedagogical LLM-as-a-Judge & G-Eval Auditor for Spaced Repetition Flashcards.
    Evaluates cards against 5 neurocognitive and pedagogical pillars:
    1. ATOMICITY: Piotr Wozniak's Rule 4 (Minimum Information Principle).
    2. CONTEXT_INDEPENDENCE: Unambiguous front prompt without cue overfitting or answer leakage.
    3. FAITHFULNESS: Zero hallucinations; all facts grounded in source corpus chunks.
    4. BLOOM_CONTRACT_ALIGNMENT: Adherence to approved LearningPlanContract depth & boundaries.
    5. HYPERCORRECTION_FEEDBACK: High-yield Metcalfe misconception diagnosis in the Extra field.
    """

    RUBRIC_THRESHOLDS = {
        "ATOMICITY": 0.85,
        "CONTEXT_INDEPENDENCE": 0.80,
        "FAITHFULNESS": 0.90,
        "BLOOM_CONTRACT_ALIGNMENT": 0.80,
        "HYPERCORRECTION_FEEDBACK": 0.80,
    }

    RUBRIC_NAMES = {
        "ATOMICITY": "Principio de Información Mínima (Atomicidad)",
        "CONTEXT_INDEPENDENCE": "Independencia de Contexto y Anti-Priming",
        "FAITHFULNESS": "Fidelidad Factual y Anti-Alucinación",
        "BLOOM_CONTRACT_ALIGNMENT": "Alineación de Profundidad Bloom con Contrato",
        "HYPERCORRECTION_FEEDBACK": "Protocolo de Hipercorrección y Trampas Frecuentes",
    }

    def __init__(self, api_key: Optional[str] = None):
        self._api_key = api_key or settings.GEMINI_API_KEY

    def _build_judge_prompt(
        self,
        card: Flashcard,
        source_chunk: Optional[str] = None,
        contract: Optional[LearningPlanContract] = None,
    ) -> str:
        prompt = f"""Eres un Juez y Auditor Pedagógico Senior en Ciencia del Aprendizaje y Sistemas de Repetición Espaciada (Anki).
Evalúa la siguiente tarjeta de estudio según las 5 Rúbricas Formales de G-Eval:

DATOS DE LA TARJETA:
- ANVERSO / PREGUNTA: "{card.front}"
- REVERSO / RESPUESTA: "{card.back}"
- CAMPO EXTRA / EXPLICACIÓN: "{card.explanation or ''}"
- TIPO / ARQUETIPO: "{card.archetype or card.card_type}"
"""
        if source_chunk:
            prompt += f"""
TEXTO FUENTE DE REFERENCIA (GROUND TRUTH):
\"\"\"{source_chunk.strip()}\"\"\"
"""
        if contract:
            prompt += f"""
CONTRATO DE APRENDIZAJE APROBADO:
- Nivel Bloom Exigido: {contract.bloom_level}
- Profundidad Operativa: {contract.operational_depth}
- Límites de Exclusión (Prohibido): {', '.join(contract.exclusion_boundary) if contract.exclusion_boundary else 'Ninguno'}
"""

        prompt += """
RÚBRICAS DE EVALUACIÓN (Puntaje de 0.00 a 1.00 para cada una):

1. ATOMICITY (Umbral >= 0.85):
   - ¿Evalúa exactamente UN hecho mental recuperable o una sola relación atómica?
   - Penaliza severamente (>0.40 de penalización) si contiene listas de múltiples elementos, párrafos enciclopédicos o múltiples conceptos no descompuestos en tarjetas hermanas.

2. CONTEXT_INDEPENDENCE (Umbral >= 0.80):
   - ¿El anverso provee suficiente contexto/taxonomía para no depender de la memoria de corto plazo de la sesión anterior?
   - ¿Evita la fuga trivial de la respuesta (cue overfitting) donde la pregunta regala la respuesta por sintaxis o pistas obvias?

3. FAITHFULNESS (Umbral >= 0.90):
   - Si se proporcionó texto fuente: ¿Todos los hechos, números, parámetros y relaciones afirmados en la tarjeta son 100% respaldados por el texto fuente?
   - Si inventó parámetros, tecnologías o relaciones no demostradas: Penalización severa (<0.40). Si no hay texto fuente, calificar 0.95 si es internamente coherente y no contradictoria.

4. BLOOM_CONTRACT_ALIGNMENT (Umbral >= 0.80):
   - ¿El nivel cognitivo de la tarjeta coincide con el nivel Bloom del contrato (ej. Análisis/Arquitectura vs Memoria de nombres superficiales)?
   - ¿Respeta los límites de exclusión del contrato (no evaluar temas prohibidos)?

5. HYPERCORRECTION_FEEDBACK (Umbral >= 0.80):
   - ¿El campo Extra incluye la sección '⚠️ Trampa frecuente / Error común:' o explica activamente el error conceptual o distractor más habitual (Efecto de Hipercorrección de Metcalfe)?

Devuelve ESTRICTAMENTE un JSON con la siguiente estructura:
{
  "scores": {
    "ATOMICITY": {
      "score": 0.95,
      "reasoning": "La tarjeta evalúa un único hecho atómico...",
      "flaws": []
    },
    "CONTEXT_INDEPENDENCE": {
      "score": 0.90,
      "reasoning": "El anverso tiene breadcrumb claro sin dar pistas...",
      "flaws": []
    },
    "FAITHFULNESS": {
      "score": 1.00,
      "reasoning": "Los datos corresponden exactamente al texto fuente...",
      "flaws": []
    },
    "BLOOM_CONTRACT_ALIGNMENT": {
      "score": 0.85,
      "reasoning": "Coincide con el nivel de diseño arquitectónico...",
      "flaws": []
    },
    "HYPERCORRECTION_FEEDBACK": {
      "score": 0.90,
      "reasoning": "Contiene advertencia explícita sobre el error común...",
      "flaws": []
    }
  },
  "critical_flaws": [],
  "recommendations": []
}
"""
        return prompt

    async def evaluate_card_with_llm(
        self,
        card: Flashcard,
        source_chunk: Optional[str] = None,
        contract: Optional[LearningPlanContract] = None,
        preferred_model: Optional[str] = None,
    ) -> PedagogicalJudgeReport:
        """Evaluate a flashcard using Gemini LLM-as-a-Judge with G-Eval rubrics."""
        if not self._api_key:
            logger.warning("No Gemini API key found, executing high-precision heuristic judge.")
            return self.evaluate_card_heuristic(card, source_chunk, contract)

        client = genai.Client(api_key=self._api_key)
        prompt = self._build_judge_prompt(card, source_chunk, contract)

        candidate_models = [
            preferred_model or "gemini-2.5-flash",
            "gemini-2.0-flash",
            settings.GEMINI_MODEL,
            settings.GEMINI_FALLBACK_MODEL,
            "gemini-1.5-flash",
        ]
        # Deduplicate while preserving order
        candidate_models = list(dict.fromkeys([m for m in candidate_models if m]))

        raw_parsed: Optional[Dict[str, Any]] = None
        for model_name in candidate_models:
            try:
                res = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                )
                text = res.text or "{}"
                text = re.sub(r"^```(?:json)?\s*", "", text.strip())
                text = re.sub(r"\s*```$", "", text.strip())
                raw_parsed = json.loads(text)
                if "scores" in raw_parsed:
                    break
            except Exception as e:
                logger.debug("Judge model '%s' failed: %s. Trying next candidate...", model_name, e)
                continue

        if not raw_parsed or "scores" not in raw_parsed:
            logger.warning("All LLM judge candidates failed. Falling back to heuristic evaluation.")
            return self.evaluate_card_heuristic(card, source_chunk, contract)

        return self._build_report_from_dict(raw_parsed)

    def evaluate_card_heuristic(
        self,
        card: Flashcard,
        source_chunk: Optional[str] = None,
        contract: Optional[LearningPlanContract] = None,
    ) -> PedagogicalJudgeReport:
        """
        High-precision deterministic evaluator enforcing mathematical and syntactic invariants
        for the 5 G-Eval rubrics without requiring active network connectivity.
        """
        front = card.front.strip()
        back = card.back.strip() if card.back else ""
        explanation = card.explanation.strip() if card.explanation else ""

        scores_dict: Dict[str, Dict[str, Any]] = {}
        critical_flaws: List[str] = []
        recommendations: List[str] = []

        # 1. ATOMICITY
        back_words = len(back.split())
        has_bullet_list = bool(re.search(r"(\n\s*[-*•]\s+|\n\s*\d+[\.\)]\s*)", back))
        has_multiple_commas = len(back.split(",")) >= 4
        atomicity_score = 1.0
        atomicity_flaws: List[str] = []

        if back_words > 25:
            atomicity_score -= min(0.6, (back_words - 25) * 0.02)
            atomicity_flaws.append(f"Respuesta excede las 20 palabras atómicas ({back_words} palabras).")
        if has_bullet_list:
            atomicity_score = min(atomicity_score, 0.40)
            atomicity_flaws.append("La respuesta contiene una lista de múltiples elementos no atómica.")
        if has_multiple_commas:
            atomicity_score = min(atomicity_score, 0.50)
            atomicity_flaws.append("La respuesta enumera múltiples ítems separados por comas.")

        scores_dict["ATOMICITY"] = {
            "score": round(max(0.1, atomicity_score), 2),
            "reasoning": "Respuesta breve y concisa." if atomicity_score >= 0.85 else "Violación del principio de información mínima.",
            "flaws": atomicity_flaws,
        }

        # 2. CONTEXT INDEPENDENCE & ANTI-PRIMING
        ci_score = 1.0
        ci_flaws: List[str] = []
        has_breadcrumb = bool(re.match(r"^\[.*?\]", front))
        if not has_breadcrumb and len(front.split()) < 5:
            ci_score -= 0.35
            ci_flaws.append("El anverso carece de taxonomía contextual y es demasiado ambiguo.")

        # Check for answer leak in question
        clean_back_words = set(re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{4,}\b", back.lower()))
        front_words = set(re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ]{4,}\b", front.lower()))
        leaked_keywords = clean_back_words.intersection(front_words)
        # Exclude common stopwords
        stopwords = {"para", "como", "esta", "este", "entre", "sobre", "donde", "tiene", "hace", "modo"}
        leaked_keywords = {w for w in leaked_keywords if w not in stopwords}

        if len(clean_back_words) > 0 and len(leaked_keywords) >= len(clean_back_words) * 0.6:
            ci_score -= 0.45
            ci_flaws.append(f"El anverso regala la respuesta (cue overfitting en: {list(leaked_keywords)[:3]}).")

        scores_dict["CONTEXT_INDEPENDENCE"] = {
            "score": round(max(0.1, ci_score), 2),
            "reasoning": "Anverso con encuadre taxonómico adecuado." if ci_score >= 0.80 else "Falta de contexto o fuga de respuesta en el anverso.",
            "flaws": ci_flaws,
        }

        # 3. FAITHFULNESS
        faith_score = 1.0
        faith_flaws: List[str] = []
        if source_chunk:
            norm_source = source_chunk.lower()
            # Extract key terms in back and check if source contains them
            key_back_terms = [w for w in re.findall(r"\b[a-zA-ZáéíóúÁÉÍÓÚñÑ0-9_-]{4,}\b", back.lower()) if w not in stopwords]
            missing_terms = [w for w in key_back_terms if w not in norm_source]
            if key_back_terms and (len(missing_terms) / len(key_back_terms) > 0.4):
                faith_score = 0.30
                faith_flaws.append(f"Términos no hallados en el texto fuente: {missing_terms[:3]} (posible alucinación).")
        scores_dict["FAITHFULNESS"] = {
            "score": round(faith_score, 2),
            "reasoning": "Afirmaciones respaldadas por el texto fuente." if faith_score >= 0.90 else "Presencia de afirmaciones o términos no demostrados en la fuente.",
            "flaws": faith_flaws,
        }

        # 4. BLOOM & CONTRACT ALIGNMENT
        bloom_score = 1.0
        bloom_flaws: List[str] = []
        if contract:
            # Check exclusion boundaries
            for exc in contract.exclusion_boundary:
                if exc.lower() in front.lower() or exc.lower() in back.lower():
                    bloom_score = 0.20
                    bloom_flaws.append(f"La tarjeta evalúa un concepto explícitamente excluido en el contrato: '{exc}'.")
                    break

            # Check depth alignment if contract specifies high level (Arquitectura / Diseño)
            if "arquitectura" in contract.bloom_level.lower() or "diseño" in contract.bloom_level.lower():
                is_trivial_def = bool(re.match(r"^(\[.*?\]\s*)?¿qué es\b", front.lower()))
                if is_trivial_def and not card.archetype:
                    bloom_score = min(bloom_score, 0.60)
                    bloom_flaws.append("La tarjeta es una definición memorística simple cuando el contrato exige Diseño/Arquitectura.")

        scores_dict["BLOOM_CONTRACT_ALIGNMENT"] = {
            "score": round(bloom_score, 2),
            "reasoning": "Alineada con el contrato pedagógico." if bloom_score >= 0.80 else "Desalineada con el nivel cognitivo o viola límites de exclusión.",
            "flaws": bloom_flaws,
        }

        # 5. HYPERCORRECTION FEEDBACK
        trap_score = 1.0
        trap_flaws: List[str] = []
        has_trap_marker = "⚠️ Trampa frecuente / Error común:" in explanation or "⚠️" in explanation or "Error común:" in explanation
        if not has_trap_marker:
            trap_score = 0.50
            trap_flaws.append("El campo Extra carece de la advertencia de trampa frecuente o error conceptual habitual.")
        elif len(explanation.split()) < 10:
            trap_score = 0.70
            trap_flaws.append("La explicación de la trampa es demasiado escueta (< 10 palabras).")

        scores_dict["HYPERCORRECTION_FEEDBACK"] = {
            "score": round(trap_score, 2),
            "reasoning": "Incluye diagnóstico de error común adecuado." if trap_score >= 0.80 else "Deficiente en diagnóstico de errores frecuentes.",
            "flaws": trap_flaws,
        }

        raw_parsed = {
            "scores": scores_dict,
            "critical_flaws": critical_flaws,
            "recommendations": recommendations,
        }
        return self._build_report_from_dict(raw_parsed)

    def _build_report_from_dict(self, raw: Dict[str, Any]) -> PedagogicalJudgeReport:
        scores: Dict[str, GEvalScoreDetail] = {}
        total_score = 0.0
        critical_flaws = list(raw.get("critical_flaws", []))
        recommendations = list(raw.get("recommendations", []))

        for criterion_key, threshold in self.RUBRIC_THRESHOLDS.items():
            criterion_data = raw.get("scores", {}).get(criterion_key, {})
            score_val = float(criterion_data.get("score", 0.5))
            score_val = max(0.0, min(1.0, score_val))
            reasoning = criterion_data.get("reasoning", "")
            flaws = criterion_data.get("flaws", [])

            passed = score_val >= threshold
            if not passed:
                critical_flaws.extend(flaws)

            detail = GEvalScoreDetail(
                criterion=criterion_key,
                name=self.RUBRIC_NAMES.get(criterion_key, criterion_key),
                score=score_val,
                threshold=threshold,
                passed=passed,
                reasoning=reasoning,
                flaws=flaws,
            )
            scores[criterion_key] = detail
            total_score += score_val

        overall_score = round(total_score / len(self.RUBRIC_THRESHOLDS), 3)
        all_passed = all(detail.passed for detail in scores.values())
        has_severe_failure = any(detail.score < 0.60 for detail in scores.values())

        if all_passed and overall_score >= 0.85:
            verdict = "CERTIFIED"
        elif not has_severe_failure and overall_score >= 0.70:
            verdict = "NEEDS_REFINEMENT"
        else:
            verdict = "REJECTED"

        return PedagogicalJudgeReport(
            overall_score=overall_score,
            is_certified=(verdict == "CERTIFIED"),
            verdict=verdict,
            scores=scores,
            critical_flaws=list(dict.fromkeys(critical_flaws)),
            recommendations=recommendations,
        )
