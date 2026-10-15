import asyncio
import base64
import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from app.adapters.ai.gemini_card_generator_adapter import (
    GeminiCardGeneratorAdapter,
    InspectedStudyPlanSchema,
    GeneratedDeckSchema,
    GeneratedCardSchema,
)
from app.core.config import settings
from app.domain.models import (
    CardType,
    CoreTheme,
    EnrichedConceptResult,
    Flashcard,
    GenerationOptions,
    PrerequisiteItem,
    StudyPlanInspection,
)
from app.ports.card_generator_port import ICardGeneratorPort

logger = logging.getLogger(__name__)


class ResilientCascadeAdapter(ICardGeneratorPort):
    """
    Motor Resiliente Multimodal Multi-Proveedor (Cascade Fallback 2026).
    Orchestrates a robust waterfall sequence:
      Tier 1: Google Gemini (Primary high-context multimodal reasoning)
      Tier 2: NVIDIA NIM (Enterprise-grade Llama-3.2 90B/11B vision models)
      Tier 3: Groq Cloud (Ultra-low latency LPU inference with Qwen 27B / Llama 70B)
      Tier 4: OpenRouter Free (Global safety net router)
    Features in-memory adaptive circuit breakers to bypass rate-limited providers immediately.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        nvidia_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        primary_adapter: Optional[ICardGeneratorPort] = None,
    ):
        self._gemini_api_key = gemini_api_key or settings.GEMINI_API_KEY
        self._nvidia_api_key = nvidia_api_key or settings.NVIDIA_API_KEY
        self._groq_api_key = groq_api_key or settings.GROQ_API_KEY
        self._openrouter_api_key = openrouter_api_key or settings.OPENROUTER_API_KEY

        self._primary_adapter = primary_adapter or GeminiCardGeneratorAdapter(
            api_key=self._gemini_api_key
        )
        # Provider circuit breakers: {provider_name: cooldown_until_timestamp}
        self._circuit_breakers: Dict[str, float] = {}

    def is_provider_open(self, provider: str) -> bool:
        """Check if provider circuit breaker is currently open (in cooldown)."""
        cooldown_until = self._circuit_breakers.get(provider, 0.0)
        return time.time() < cooldown_until

    def trip_circuit(self, provider: str, cooldown_seconds: float = 60.0) -> None:
        """Trip circuit breaker for a provider after rate limit (429) or outage (503)."""
        until = time.time() + cooldown_seconds
        self._circuit_breakers[provider] = until
        logger.warning(
            "Circuit breaker TRIPPED for provider '%s' until %.1f (cooldown: %.0fs)",
            provider,
            until,
            cooldown_seconds,
        )

    def reset_circuit(self, provider: str) -> None:
        """Reset circuit breaker for provider upon confirmed success."""
        if provider in self._circuit_breakers:
            del self._circuit_breakers[provider]

    def _build_inspection_instruction(self) -> str:
        """Detailed neurocognitive system instruction for study plan diagnostic."""
        return (
            "# SYSTEM PROMPT: DIAGNOSTICADOR COGNITIVO Y ARQUITECTO DE APRENDIZAJE (CTA)\n\n"
            "Eres un Arquitecto de Aprendizaje experto en Psicología Educativa, Epistemología y Repetición Espaciada (Ausubel, Wozniak).\n"
            "Tu objetivo es AUDITAR A FONDO el material de estudio antes de crear las flashcards:\n\n"
            "1. ESCRUTINIO DEL CONCEPTO PROPIO Y RIGOR DEL CONTENIDO:\n"
            "   - Identifica con precisión qué concepto, mecanismo o teoría específica expone el contenido entregado.\n"
            "   - Verifica críticamente si la explicación provista en el material es completa y profunda o si es superficial, incompleta o confusa.\n"
            "   - Si se proporcionan imágenes, esquemas o diagramas visuales, OBSÉRVALOS Y AUDÍTALOS EN DETALLE: analiza su contenido visual, qué estructuras o procesos revelan y si el texto los explica adecuadamente.\n"
            "   - Califica la autosuficiencia de 0 a 100 y emite un veredicto pedagógico que evalúe si el contenido actual basta para dominar el concepto.\n\n"
            "2. DESGLOSE OBLIGATORIO DE SUBTEMAS Y ASOCIACIÓN DE DIAGRAMAS:\n"
            "   - Para dominar dicho concepto 'a profundidad' (y no de forma anecdótica o de memoria mecánica), determina qué subtemas o dimensiones estructurales son OBLIGATORIOS.\n"
            "   - Descompón el tema en esos 2 a 5 ejes temáticos indispensables.\n"
            "   - Asigna a cada subtema la cantidad exacta de tarjetas necesarias según el Principio de Información Mínima (1 hecho/relación por tarjeta).\n"
            "   - ASIGNACIÓN MULTIMODAL: Si se proporcionaron imágenes o diagramas del material, asigna los nombres de archivo exactos a los ejes temáticos correspondientes en 'associated_diagrams'.\n\n"
            "3. DETECCIÓN DE PRERREQUISITOS Y BRECHAS FUNDACIONALES (EVITAR CONCEPTOS HUÉRFANOS):\n"
            "   - Identifica qué conocimientos base debe dominar el estudiante antes de entender este concepto (para no aprenderlo de forma aislada).\n"
            "   - Indica para cada prerrequisito si ya está adecuadamente cubierto en el material (is_covered_in_text=True) o si falta/se asume (is_covered_in_text=False).\n"
            "   - Proporciona una query de búsqueda precisa (search_query) para investigar y enriquecer los conceptos ausentes.\n\n"
            "4. CÁLCULO ATÓMICO TOTAL:\n"
            "   - Suma el total sugerido de tarjetas (suggested_total_cards) para garantizar cobertura total sin redundancias superfluas.\n\n"
            "Responde ESTRICTAMENTE con un objeto JSON válido con la siguiente estructura exacta:\n"
            "{\n"
            '  "topic_name": "Nombre conciso del tema principal",\n'
            '  "self_sufficiency_score": 85,\n'
            '  "self_sufficiency_verdict": "Veredicto pedagógico claro y directo",\n'
            '  "core_themes": [\n'
            '    {\n'
            '      "title": "Nombre del subtema",\n'
            '      "description": "Concepto o mecanismo evaluado",\n'
            '      "recommended_cards": 2,\n'
            '      "associated_diagrams": []\n'
            '    }\n'
            '  ],\n'
            '  "prerequisites": [\n'
            '    {\n'
            '      "concept": "Concepto previo indispensable",\n'
            '      "reason": "Por qué es necesario para evitar confusiones",\n'
            '      "is_covered_in_text": false,\n'
            '      "search_query": "Consulta de búsqueda recomendada",\n'
            '      "recommended_deep_cards": 3\n'
            '    }\n'
            '  ],\n'
            '  "suggested_total_cards": 6\n'
            "}"
        )

    def _build_openai_messages(
        self,
        system_instruction: str,
        user_prompt: str,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> List[Dict[str, Any]]:
        """Construct standard OpenAI-compatible messages payload with multimodal image_url support."""
        if media_parts and len(media_parts) > 0:
            user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            for file_bytes, mime_type in media_parts:
                b64 = base64.b64encode(file_bytes).decode("utf-8")
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                })
            return [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ]

        return [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_prompt},
        ]

    async def _call_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model: str,
        messages: List[Dict[str, Any]],
        response_format: Optional[Dict[str, Any]] = None,
        timeout: float = 35.0,
    ) -> Dict[str, Any]:
        """Execute an asynchronous request against an OpenAI-compatible endpoint."""
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        }
        if response_format:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                err_text = resp.text
                resp.raise_for_status()

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise ValueError(f"No choices returned from model '{model}': {data}")

            raw_content = choices[0].get("message", {}).get("content", "")
            if not raw_content:
                raise ValueError(f"Empty content from model '{model}'")

            # Clean markdown code fences if model returned ```json ... ```
            cleaned = raw_content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:].strip()
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:].strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(cleaned[start : end + 1])
                raise

    def _map_schema_to_domain(
        self,
        parsed: InspectedStudyPlanSchema,
        provider_used: str,
        model_used: Optional[str] = None,
        fallback_occurred: bool = False,
        fallback_chain: Optional[List[str]] = None,
    ) -> StudyPlanInspection:
        """Map validated Pydantic schema to domain model with execution telemetry."""
        return StudyPlanInspection(
            topic_name=parsed.topic_name,
            self_sufficiency_score=parsed.self_sufficiency_score,
            self_sufficiency_verdict=parsed.self_sufficiency_verdict,
            core_themes=[
                CoreTheme(
                    title=t.title,
                    description=t.description,
                    recommended_cards=t.recommended_cards,
                    selected=True,
                    associated_diagrams=getattr(t, "associated_diagrams", []) or [],
                )
                for t in parsed.core_themes
            ],
            prerequisites=[
                PrerequisiteItem(
                    concept=p.concept,
                    reason=p.reason,
                    is_covered_in_text=p.is_covered_in_text,
                    search_query=p.search_query,
                    selected=not p.is_covered_in_text,
                    recommended_deep_cards=getattr(p, "recommended_deep_cards", 3),
                )
                for p in parsed.prerequisites
            ],
            suggested_total_cards=parsed.suggested_total_cards,
            provider_used=provider_used,
            model_used=model_used,
            fallback_occurred=fallback_occurred,
            fallback_chain=fallback_chain or [],
        )

    def _is_rate_limit_or_overload(self, exc: Exception) -> bool:
        """Detect 429 quota exhaustion, 503 high demand or resource exhaustion in exception."""
        msg = str(exc).lower()
        sigs = [
            "429",
            "503",
            "quota",
            "rate limit",
            "rate_limit",
            "resource_exhausted",
            "high demand",
            "overloaded",
            "capacity",
        ]
        return any(sig in msg for sig in sigs)

    async def inspect_material(
        self,
        text: str,
        options: GenerationOptions,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> StudyPlanInspection:
        """
        Execute material inspection with Resilient Waterfall Cascade:
        Tier 1: Gemini -> Tier 2: NVIDIA NIM -> Tier 3: Groq -> Tier 4: OpenRouter.
        """
        fallback_chain: List[str] = []
        system_instruction = self._build_inspection_instruction()
        has_media = media_parts is not None and len(media_parts) > 0

        user_prompt = (
            f"Audita críticamente el material educativo provisto (incluyendo las imágenes/diagramas adjuntos), "
            f"escudriña el concepto propio expuesto, analiza detalladamente el contenido visual y su relación con el texto, "
            f"verifica la suficiencia del contenido y determina los subtemas obligatorios asignando los diagramas pertinentes a cada eje:\n\n"
            f"---\n{text}\n---"
            if has_media
            else (
                f"Audita críticamente el siguiente material educativo, escudriña el concepto propio expuesto, "
                f"verifica si el contenido es suficiente y determina los subtemas obligatorios para comprenderlo a profundidad:\n\n"
                f"---\n{text}\n---"
            )
        )

        openai_messages = self._build_openai_messages(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            media_parts=media_parts,
        )

        # -------------------------------------------------------------
        # TIER 1: Google Gemini (Official SDK)
        # -------------------------------------------------------------
        if self._gemini_api_key and not self.is_provider_open("gemini"):
            try:
                logger.info("Executing Cascade Tier 1: Google Gemini...")
                res = await self._primary_adapter.inspect_material(
                    text=text, options=options, media_parts=media_parts
                )
                res.provider_used = "gemini"
                res.model_used = settings.GEMINI_MODEL
                res.fallback_occurred = False
                res.fallback_chain = []
                self.reset_circuit("gemini")
                return res
            except Exception as e:
                logger.warning("Cascade Tier 1 (Gemini) failed: %s", e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("gemini", cooldown_seconds=45.0)
                fallback_chain.append(f"gemini ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("gemini"):
            logger.info("Cascade Tier 1 (Gemini) circuit is OPEN. Bypassing...")
            fallback_chain.append("gemini (circuit_breaker_open)")
        else:
            fallback_chain.append("gemini (no_api_key)")

        # -------------------------------------------------------------
        # TIER 2: NVIDIA NIM (Llama-3.2 90B/11B Vision Instruct)
        # -------------------------------------------------------------
        if self._nvidia_api_key and not self.is_provider_open("nvidia"):
            models_to_try = [
                "deepseek-ai/deepseek-v4.1-flash",
                settings.NVIDIA_MODEL,
                settings.NVIDIA_FALLBACK_MODEL,
            ]
            for nvidia_model in models_to_try:
                try:
                    logger.info("Executing Cascade Tier 2: NVIDIA NIM (model=%s)...", nvidia_model)
                    json_dict = await self._call_openai_compatible(
                        base_url=settings.NVIDIA_BASE_URL,
                        api_key=self._nvidia_api_key,
                        model=nvidia_model,
                        messages=openai_messages,
                        response_format={"type": "json_object"},
                        timeout=12.0,
                    )
                    parsed = InspectedStudyPlanSchema.model_validate(json_dict)
                    self.reset_circuit("nvidia")
                    return self._map_schema_to_domain(
                        parsed=parsed,
                        provider_used="nvidia",
                        model_used=nvidia_model,
                        fallback_occurred=True,
                        fallback_chain=fallback_chain,
                    )
                except Exception as e:
                    logger.warning("Cascade Tier 2 (NVIDIA NIM %s) failed: %s", nvidia_model, e)
                    if self._is_rate_limit_or_overload(e):
                        self.trip_circuit("nvidia", cooldown_seconds=45.0)
                        fallback_chain.append(f"nvidia:{nvidia_model} ({type(e).__name__}: {str(e)[:80]})")
                        break
                    fallback_chain.append(f"nvidia:{nvidia_model} ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("nvidia"):
            logger.info("Cascade Tier 2 (NVIDIA NIM) circuit is OPEN. Bypassing...")
            fallback_chain.append("nvidia (circuit_breaker_open)")
        else:
            fallback_chain.append("nvidia (no_api_key)")

        # -------------------------------------------------------------
        # TIER 3: Groq Cloud (Qwen 3.8 27B / Llama 3.3 70B)
        # -------------------------------------------------------------
        if self._groq_api_key and not self.is_provider_open("groq"):
            groq_model = (
                settings.GROQ_VISION_MODEL if has_media else settings.GROQ_TEXT_MODEL
            )
            try:
                logger.info("Executing Cascade Tier 3: Groq Cloud (model=%s)...", groq_model)
                json_dict = await self._call_openai_compatible(
                    base_url=settings.GROQ_BASE_URL,
                    api_key=self._groq_api_key,
                    model=groq_model,
                    messages=openai_messages,
                    response_format={"type": "json_object"},
                )
                parsed = InspectedStudyPlanSchema.model_validate(json_dict)
                self.reset_circuit("groq")
                return self._map_schema_to_domain(
                    parsed=parsed,
                    provider_used="groq",
                    model_used=groq_model,
                    fallback_occurred=True,
                    fallback_chain=fallback_chain,
                )
            except Exception as e:
                logger.warning("Cascade Tier 3 (Groq %s) failed: %s", groq_model, e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("groq", cooldown_seconds=45.0)
                fallback_chain.append(f"groq:{groq_model} ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("groq"):
            logger.info("Cascade Tier 3 (Groq) circuit is OPEN. Bypassing...")
            fallback_chain.append("groq (circuit_breaker_open)")
        else:
            fallback_chain.append("groq (no_api_key)")

        # -------------------------------------------------------------
        # TIER 4: OpenRouter Free (Global Safety Net)
        # -------------------------------------------------------------
        if self._openrouter_api_key and not self.is_provider_open("openrouter"):
            openrouter_model = settings.OPENROUTER_MODEL
            try:
                logger.info("Executing Cascade Tier 4: OpenRouter (model=%s)...", openrouter_model)
                json_dict = await self._call_openai_compatible(
                    base_url=settings.OPENROUTER_BASE_URL,
                    api_key=self._openrouter_api_key,
                    model=openrouter_model,
                    messages=openai_messages,
                    response_format={"type": "json_object"},
                )
                parsed = InspectedStudyPlanSchema.model_validate(json_dict)
                self.reset_circuit("openrouter")
                return self._map_schema_to_domain(
                    parsed=parsed,
                    provider_used="openrouter",
                    model_used=openrouter_model,
                    fallback_occurred=True,
                    fallback_chain=fallback_chain,
                )
            except Exception as e:
                logger.warning("Cascade Tier 4 (OpenRouter) failed: %s", e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("openrouter", cooldown_seconds=45.0)
                fallback_chain.append(f"openrouter ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("openrouter"):
            logger.info("Cascade Tier 4 (OpenRouter) circuit is OPEN. Bypassing...")
            fallback_chain.append("openrouter (circuit_breaker_open)")
        else:
            fallback_chain.append("openrouter (no_api_key)")

        # -------------------------------------------------------------
        # ALL TIERS EXHAUSTED
        # -------------------------------------------------------------
        chain_str = " -> ".join(fallback_chain)
        logger.error("All Cascade tiers exhausted. Chain of failure: %s", chain_str)
        raise RuntimeError(
            f"Todos los proveedores de la cascada fallaron al diagnosticar el material: {chain_str}"
        )

    async def inspect_material_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> StudyPlanInspection:
        """Multimodal inspection of file bytes (PDF / image) with optional accompanying notes."""
        return await self.inspect_material(
            text=text or "",
            options=options,
            media_parts=[(file_bytes, mime_type)],
        )

    # -----------------------------------------------------------------
    # Card Generation Cascade Waterfall (Tier 1: Gemini -> Tier 2: NVIDIA -> Tier 3: Groq -> Tier 4: OpenRouter)
    # -----------------------------------------------------------------
    def _build_generation_instruction(self, options: GenerationOptions) -> str:
        """
        Cognitive system instruction for atomic card generation across cascade providers.
        Strictly enforces the 5 learning archetypes, Minimum Information Principle, and Dual-Coding Diagram Inheritance.
        """
        count_desc = (
            f"Genera exactamente {options.target_count} tarjetas atómicas."
            if options.target_count > 0
            else "Evalúa la densidad conceptual del material y genera la cantidad exacta de tarjetas atómicas necesarias para cubrirlo al 100% sin redundancia ni sobrecarga."
        )

        themes_prompt = ""
        if options.selected_themes:
            formatted_themes = "\n".join(f"- {t}" for t in options.selected_themes)
            themes_prompt = (
                f"\n\n## EJES TEMÁTICOS OBLIGATORIOS (COBERTURA REQUERIDA):\n"
                f"Debes generar tarjetas que cubran específicamente los siguientes ejes temáticos aprobados:\n"
                f"{formatted_themes}\n"
            )

        prerequisites_prompt = ""
        if options.prerequisites_context:
            prerequisites_prompt = (
                f"\n\n## CONTEXTO DE PRERREQUISITOS Y ANDAMIAJE FUNDACIONAL:\n"
                f"Incorpora o ancla los siguientes conceptos fundacionales:\n"
                f"{options.prerequisites_context}\n"
            )

        neighbors_prompt = ""
        if options.neighbor_concepts:
            neighbors_str = ", ".join(f"'{c}'" for c in options.neighbor_concepts[:10])
            neighbors_prompt = (
                f"\n\n## FRONTERA DE ALCANCE NEGATIVA (NO-DUPLICIDAD):\n"
                f"Los siguientes conceptos vecinos ya están cubiertos de forma independiente en el grafo de conocimiento: {neighbors_str}.\n"
                f"PROHIBIDO generar tarjetas cuya pregunta central defina o evalúe directamente estos conceptos vecinos; mantén el foco en los temas aprobados.\n"
            )

        custom_prompt = (
            f"\n\n## INSTRUCCIONES ESPECÍFICAS ADICIONALES:\n{options.custom_instructions}"
            if options.custom_instructions
            else ""
        )

        return (
            "# SYSTEM PROMPT: ARQUITECTO COGNITIVO Y GENERADOR DE FLASHCARDS DE ALTO RENDIMIENTO\n\n"
            "## ROL Y OBJETIVO\n"
            "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva, diseño instruccional y repetición espaciada (FSRS / SM-2). "
            "Tu misión es procesar material educativo y transformarlo en tarjetas de Anki de máxima calidad, optimizadas para eliminar la fatiga mental y garantizar la retención relacional profunda.\n\n"
            "## 1. LEYES COGNITIVAS DE OBLIGATORIO CUMPLIMIENTO\n\n"
            "1. Principio de Información Mínima (Piotr Wozniak):\n"
            "   - Cada tarjeta debe responderse mentalmente en MENOS DE 5 A 8 SEGUNDOS.\n"
            "   - Evalúa únicamente UN SOLO HECHO O RELACIÓN LÓGICA por tarjeta.\n"
            "   - La respuesta en el dorso ('back') debe ser directa, atómica, MÁXIMO 15 PALABRAS.\n\n"
            "2. Anclaje Jerárquico Obligatorio (Breadcrumbs):\n"
            "   - Toda tarjeta DEBE iniciar obligatoriamente en el campo 'front' con la ruta de su esquema mental entre corchetes: `[Macro-tema > Sub-tema > Categoría]`.\n\n"
            "3. Oclusión Causal Inversa y Especificación Estricta Cloze:\n"
            "   - En tarjetas Cloze, ocluye el mecanismo de impacto, la dirección del cambio o la relación causal (ej. {{c1::aumenta}}, {{c1::se descarta}}).\n"
            "   - ESTRICTAMENTE OBLIGATORIO: Toda oclusión DEBE usar el prefijo ordinal 'c1::', ej. `{{c1::palabra}}` o `{{c1::palabra::pista}}`. NUNCA emitas `{{palabra}}` sin 'c1::'.\n"
            "   - NUNCA incluyas dos conceptos independientes en la misma oclusión (`{{c1::A y B}}`). Usa `{{c1::A}}` y `{{c2::B}}`.\n"
            "   - ESTRICTAMENTE OBLIGATORIO: Oclusiones atómicas de 1 a 3 palabras clave (Principio de Wozniak). PROHIBIDO ocluir frases o cláusulas de 4 o más palabras; si el concepto requiere una frase larga, DEBE usarse Arquetipo C (Básica Elaborativa), NUNCA un Cloze.\n\n"
            "4. Efecto de Hipercorrección en Campo Extra (Janet Metcalfe):\n"
            "   - El campo 'explanation' (Extra de Anki) DEBE incluir síntesis visual pasiva (diagrama ASCII/tabla Markdown) y OBLIGATORIAMENTE la sección '⚠️ Trampa frecuente / Error común:' desarticulando explícitamente la confusión típica o falsa creencia sobre ese concepto.\n\n"
            "5. HERENCIA DE DIAGRAMAS OBLIGATORIA (Codificación Dual de Paivio):\n"
            "   - Si un eje temático incluye 'Diagramas a heredar: [nombre_imagen]', DEBES incluir exactamente la etiqueta <img src='nombre_imagen'> en el campo 'explanation' de la tarjeta atómica correspondiente que evalúe dicho concepto visual o mecanismo.\n\n"
            "## 2. ARQUETIPOS DE TARJETAS PERMITIDOS\n\n"
            "Usa exclusivamente estas cinco estructuras cognitivas:\n"
            "- Arquetipo A: Cloze Contextualizado Causal (Párrafo cohesivo donde se ocluye la relación causal o métrica crítica con {{c1::...}}).\n"
            "- Arquetipo B: Matriz de Contraste (Tabla Markdown donde se ocluye el atributo diferencial clave entre conceptos competidores con {{c1::...}}).\n"
            "- Arquetipo C: Pregunta Atómica Elaborativa (Frente: `[Ruta] ¿Por qué...?` o `[Ruta] ¿Cuál es la causa/consecuencia...?`. Dorso: Máximo 15 palabras).\n"
            "- Arquetipo D: Tarjeta Radar (Índice estructural que pregunta por los N ejes de análisis sin pedir valores específicos).\n"
            "- Arquetipo E: Mini-Escenario Aplicado (Caso práctico ultra-corto < 2 renglones que plantea una situación real y pregunta por el diagnóstico o decisión técnica inmediata).\n\n"
            f"## 3. CONFIGURACIÓN DE GENERACIÓN:\n"
            f"- {count_desc}\n"
            f"- Idioma: Las tarjetas deben estar redactadas en '{options.language}'.\n"
            f"- Fórmulas matemáticas: Encapsula en formato LaTeX para Anki MathJax ($...$).\n"
            f"{prerequisites_prompt}"
            f"{themes_prompt}"
            f"{neighbors_prompt}"
            f"{custom_prompt}\n\n"
            "Responde ESTRICTAMENTE con un objeto JSON válido con la siguiente estructura:\n"
            "{\n"
            '  "cards": [\n'
            '    {\n'
            '      "archetype": "Arquetipo A: Cloze Contextualizado",\n'
            '      "front": "[Macro > Sub] Texto con {{c1::oclusión estricta}}",\n'
            '      "back": "Respuesta directa menor a 15 palabras",\n'
            '      "tags": ["etiqueta1", "etiqueta2"],\n'
            '      "explanation": "Síntesis visual y ⚠️ Trampa frecuente / Error común: ..."\n'
            '    }\n'
            '  ]\n'
            "}"
        )

    def _map_generated_cards(
        self, parsed: GeneratedDeckSchema, options: GenerationOptions
    ) -> List[Flashcard]:
        """Convert parsed GeneratedDeckSchema into Domain Flashcard models."""
        cards: List[Flashcard] = []
        for c in parsed.cards:
            card_type = options.card_type
            if "{{c" in c.front or "Cloze" in c.archetype or "Matriz" in c.archetype:
                card_type = CardType.CLOZE

            source_img = None
            img_idx = getattr(c, "source_image_index", None)
            if img_idx and options.media_filenames and 1 <= img_idx <= len(options.media_filenames):
                source_img = options.media_filenames[img_idx - 1]
            elif options.media_filenames and len(options.media_filenames) == 1:
                source_img = options.media_filenames[0]

            explanation = c.explanation
            if source_img:
                img_tag = f'<img src="{source_img}">'
                if explanation:
                    if source_img not in explanation and "<img" not in explanation:
                        explanation = f"{explanation}<br><br>{img_tag}"
                else:
                    explanation = img_tag

            cards.append(
                Flashcard(
                    card_type=card_type,
                    archetype=c.archetype,
                    front=c.front,
                    back=c.back,
                    tags=c.tags or [options.deck_name.lower().replace("::", "-")],
                    explanation=explanation,
                    justification=getattr(c, "justification", None),
                    source_image_index=getattr(c, "source_image_index", None),
                    source_image=source_img,
                )
            )
        return cards

    async def generate_from_text(
        self, text: str, options: GenerationOptions
    ) -> List[Flashcard]:
        """
        Generate flashcards using Resilient Waterfall Cascade:
        Tier 1: Gemini -> Tier 2: NVIDIA NIM -> Tier 3: Groq Cloud -> Tier 4: OpenRouter Free.
        """
        fallback_chain: List[str] = []

        # -------------------------------------------------------------
        # TIER 1: Google Gemini (Primary high-context adapter)
        # -------------------------------------------------------------
        if self._gemini_api_key and not self.is_provider_open("gemini"):
            try:
                logger.info("Executing Generation Cascade Tier 1: Google Gemini...")
                cards = await self._primary_adapter.generate_from_text(text, options)
                if cards:
                    self.reset_circuit("gemini")
                    return cards
                logger.warning("Gemini returned 0 cards, continuing to Tier 2...")
                fallback_chain.append("gemini (returned 0 cards)")
            except Exception as e:
                logger.warning("Generation Cascade Tier 1 (Gemini) failed: %s", e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("gemini", cooldown_seconds=60.0)
                fallback_chain.append(f"gemini ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("gemini"):
            logger.info("Generation Cascade Tier 1 (Gemini) circuit is OPEN. Bypassing...")
            fallback_chain.append("gemini (circuit_breaker_open)")
        else:
            fallback_chain.append("gemini (no_api_key)")

        # Prepare payload for OpenAI-compatible tiers
        system_instruction = self._build_generation_instruction(options)
        user_prompt = (
            f"Analiza minuciosamente el siguiente contenido educativo y genera las tarjetas de estudio atómicas solicitadas siguiendo todas las leyes cognitivas y el esquema JSON especificado:\n\n"
            f"---\n{text}\n---"
        )
        openai_messages = self._build_openai_messages(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
        )

        # -------------------------------------------------------------
        # TIER 2: NVIDIA NIM (meta/llama-3.2-90b-vision-instruct / 11b)
        # -------------------------------------------------------------
        if self._nvidia_api_key and not self.is_provider_open("nvidia"):
            models_to_try = [
                settings.NVIDIA_MODEL,
                settings.NVIDIA_FALLBACK_MODEL,
            ]
            for nvidia_model in models_to_try:
                try:
                    logger.info("Executing Generation Cascade Tier 2: NVIDIA NIM (model=%s)...", nvidia_model)
                    json_dict = await self._call_openai_compatible(
                        base_url=settings.NVIDIA_BASE_URL,
                        api_key=self._nvidia_api_key,
                        model=nvidia_model,
                        messages=openai_messages,
                        response_format={"type": "json_object"},
                    )
                    parsed = GeneratedDeckSchema.model_validate(json_dict)
                    cards = self._map_generated_cards(parsed, options)
                    if cards:
                        self.reset_circuit("nvidia")
                        return cards
                except Exception as e:
                    logger.warning("Generation Cascade Tier 2 (NVIDIA NIM %s) failed: %s", nvidia_model, e)
                    if self._is_rate_limit_or_overload(e):
                        self.trip_circuit("nvidia", cooldown_seconds=60.0)
                        fallback_chain.append(f"nvidia:{nvidia_model} ({type(e).__name__}: {str(e)[:80]})")
                        break
                    fallback_chain.append(f"nvidia:{nvidia_model} ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("nvidia"):
            logger.info("Generation Cascade Tier 2 (NVIDIA NIM) circuit is OPEN. Bypassing...")
            fallback_chain.append("nvidia (circuit_breaker_open)")
        else:
            fallback_chain.append("nvidia (no_api_key)")

        # -------------------------------------------------------------
        # TIER 3: Groq Cloud (llama-3.3-70b-versatile)
        # -------------------------------------------------------------
        if self._groq_api_key and not self.is_provider_open("groq"):
            groq_model = settings.GROQ_TEXT_MODEL
            try:
                logger.info("Executing Generation Cascade Tier 3: Groq Cloud (model=%s)...", groq_model)
                json_dict = await self._call_openai_compatible(
                    base_url=settings.GROQ_BASE_URL,
                    api_key=self._groq_api_key,
                    model=groq_model,
                    messages=openai_messages,
                    response_format={"type": "json_object"},
                )
                parsed = GeneratedDeckSchema.model_validate(json_dict)
                cards = self._map_generated_cards(parsed, options)
                if cards:
                    self.reset_circuit("groq")
                    return cards
            except Exception as e:
                logger.warning("Generation Cascade Tier 3 (Groq %s) failed: %s", groq_model, e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("groq", cooldown_seconds=60.0)
                fallback_chain.append(f"groq:{groq_model} ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("groq"):
            logger.info("Generation Cascade Tier 3 (Groq) circuit is OPEN. Bypassing...")
            fallback_chain.append("groq (circuit_breaker_open)")
        else:
            fallback_chain.append("groq (no_api_key)")

        # -------------------------------------------------------------
        # TIER 4: OpenRouter Free (Global Safety Net)
        # -------------------------------------------------------------
        if self._openrouter_api_key and not self.is_provider_open("openrouter"):
            openrouter_model = settings.OPENROUTER_MODEL
            try:
                logger.info("Executing Generation Cascade Tier 4: OpenRouter (model=%s)...", openrouter_model)
                json_dict = await self._call_openai_compatible(
                    base_url=settings.OPENROUTER_BASE_URL,
                    api_key=self._openrouter_api_key,
                    model=openrouter_model,
                    messages=openai_messages,
                    response_format={"type": "json_object"},
                )
                parsed = GeneratedDeckSchema.model_validate(json_dict)
                cards = self._map_generated_cards(parsed, options)
                if cards:
                    self.reset_circuit("openrouter")
                    return cards
            except Exception as e:
                logger.warning("Generation Cascade Tier 4 (OpenRouter) failed: %s", e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("openrouter", cooldown_seconds=60.0)
                fallback_chain.append(f"openrouter ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("openrouter"):
            logger.info("Generation Cascade Tier 4 (OpenRouter) circuit is OPEN. Bypassing...")
            fallback_chain.append("openrouter (circuit_breaker_open)")
        else:
            fallback_chain.append("openrouter (no_api_key)")

        # -------------------------------------------------------------
        # ALL TIERS EXHAUSTED
        # -------------------------------------------------------------
        chain_str = " -> ".join(fallback_chain)
        logger.error("All Generation Cascade tiers exhausted. Chain of failure: %s", chain_str)
        raise RuntimeError(
            f"Todos los proveedores de la cascada fallaron al generar tarjetas: {chain_str}"
        )

    async def generate_from_text_stream(
        self, text: str, options: GenerationOptions
    ) -> AsyncGenerator[Tuple[str, List[Flashcard], int, int], None]:
        """
        Stream cards batch by batch with Resilient Cascade fallback.
        If Gemini primary stream fails or circuit is open, trips circuit and falls back to
        generate_from_text (NVIDIA/Groq/OpenRouter), chunking the cards into 2-3 card batches
        so the frontend receives real-time progress.
        """
        if not self.is_provider_open("gemini") and self._gemini_api_key:
            yielded_any = False
            try:
                async for item in self._primary_adapter.generate_from_text_stream(text, options):
                    yielded_any = True
                    yield item
                self.reset_circuit("gemini")
                return
            except Exception as exc:
                logger.warning("Gemini streaming failed (yielded_any=%s): %s", yielded_any, exc)
                if self._is_rate_limit_or_overload(exc):
                    self.trip_circuit("gemini", cooldown_seconds=60.0)

        # Fallback to waterfall generate_from_text
        logger.info("Streaming falling back to waterfall cascade generate_from_text...")
        all_cards = await self.generate_from_text(text, options)

        # Chunk cards into batches of 2 or 3 cards
        chunk_size = 3
        chunks = [all_cards[i:i + chunk_size] for i in range(0, len(all_cards), chunk_size)]
        total_chunks = max(1, len(chunks))

        for idx, chunk in enumerate(chunks):
            label = f"Lote Cascada {idx + 1}"
            yield (label, chunk, idx + 1, total_chunks)
            await asyncio.sleep(0.1)

    async def generate_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> List[Flashcard]:
        """Generate cards from multimodal file bytes (image, diagram, PDF) with cascade fallback and multi-image support."""
        fallback_chain: List[str] = []

        # Tier 1: Gemini
        if self._gemini_api_key and not self.is_provider_open("gemini"):
            try:
                cards = await self._primary_adapter.generate_from_media(
                    file_bytes=file_bytes, mime_type=mime_type, options=options, text=text, media_parts=media_parts
                )
                if cards:
                    self.reset_circuit("gemini")
                    return cards
                fallback_chain.append("gemini (returned 0 cards)")
            except Exception as e:
                logger.warning("Generation Cascade Tier 1 (Gemini media) failed: %s", e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("gemini", cooldown_seconds=60.0)
                fallback_chain.append(f"gemini ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("gemini"):
            logger.info("Generation Cascade Tier 1 (Gemini) circuit is OPEN. Bypassing...")
            fallback_chain.append("gemini (circuit_breaker_open)")
        else:
            fallback_chain.append("gemini (no_api_key)")

        # Prepare multimodal OpenAI messages
        system_instruction = self._build_generation_instruction(options)
        count_desc = (
            f"Genera {options.target_count} tarjetas atómicas."
            if options.target_count > 0
            else "Genera las tarjetas atómicas necesarias según la densidad del material."
        )
        text_context = f"\n\nTexto adicional:\n{text.strip()}" if text and text.strip() else ""
        user_prompt = (
            f"Analiza minuciosamente el archivo multimodal ({mime_type}) adjunto y el texto de apoyo para generar tarjetas de estudio atómicas siguiendo las leyes cognitivas y el esquema JSON especificado. {count_desc}{text_context}"
        )
        openai_messages = self._build_openai_messages(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            media_parts=media_parts or [(file_bytes, mime_type)],
        )

        # Tier 2: NVIDIA NIM (meta/llama-3.2-90b-vision-instruct / 11b)
        if self._nvidia_api_key and not self.is_provider_open("nvidia"):
            for nvidia_model in [settings.NVIDIA_MODEL, settings.NVIDIA_FALLBACK_MODEL]:
                try:
                    logger.info("Executing Generation Cascade Tier 2: NVIDIA NIM Vision (model=%s)...", nvidia_model)
                    json_dict = await self._call_openai_compatible(
                        base_url=settings.NVIDIA_BASE_URL,
                        api_key=self._nvidia_api_key,
                        model=nvidia_model,
                        messages=openai_messages,
                        response_format={"type": "json_object"},
                    )
                    parsed = GeneratedDeckSchema.model_validate(json_dict)
                    cards = self._map_generated_cards(parsed, options)
                    if cards:
                        self.reset_circuit("nvidia")
                        return cards
                except Exception as e:
                    logger.warning("Generation Cascade Tier 2 (NVIDIA NIM %s) failed: %s", nvidia_model, e)
                    if self._is_rate_limit_or_overload(e):
                        self.trip_circuit("nvidia", cooldown_seconds=60.0)
                        fallback_chain.append(f"nvidia:{nvidia_model} ({type(e).__name__}: {str(e)[:80]})")
                        break
                    fallback_chain.append(f"nvidia:{nvidia_model} ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("nvidia"):
            fallback_chain.append("nvidia (circuit_breaker_open)")
        else:
            fallback_chain.append("nvidia (no_api_key)")

        # Tier 3: Groq Cloud (Vision)
        if self._groq_api_key and not self.is_provider_open("groq"):
            groq_model = settings.GROQ_VISION_MODEL
            try:
                logger.info("Executing Generation Cascade Tier 3: Groq Cloud Vision (model=%s)...", groq_model)
                json_dict = await self._call_openai_compatible(
                    base_url=settings.GROQ_BASE_URL,
                    api_key=self._groq_api_key,
                    model=groq_model,
                    messages=openai_messages,
                    response_format={"type": "json_object"},
                )
                parsed = GeneratedDeckSchema.model_validate(json_dict)
                cards = self._map_generated_cards(parsed, options)
                if cards:
                    self.reset_circuit("groq")
                    return cards
            except Exception as e:
                logger.warning("Generation Cascade Tier 3 (Groq %s) failed: %s", groq_model, e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("groq", cooldown_seconds=60.0)
                fallback_chain.append(f"groq:{groq_model} ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("groq"):
            fallback_chain.append("groq (circuit_breaker_open)")
        else:
            fallback_chain.append("groq (no_api_key)")

        # Tier 4: OpenRouter Free
        if self._openrouter_api_key and not self.is_provider_open("openrouter"):
            openrouter_model = settings.OPENROUTER_MODEL
            try:
                logger.info("Executing Generation Cascade Tier 4: OpenRouter (model=%s)...", openrouter_model)
                json_dict = await self._call_openai_compatible(
                    base_url=settings.OPENROUTER_BASE_URL,
                    api_key=self._openrouter_api_key,
                    model=openrouter_model,
                    messages=openai_messages,
                    response_format={"type": "json_object"},
                )
                parsed = GeneratedDeckSchema.model_validate(json_dict)
                cards = self._map_generated_cards(parsed, options)
                if cards:
                    self.reset_circuit("openrouter")
                    return cards
            except Exception as e:
                logger.warning("Generation Cascade Tier 4 (OpenRouter) failed: %s", e)
                if self._is_rate_limit_or_overload(e):
                    self.trip_circuit("openrouter", cooldown_seconds=60.0)
                fallback_chain.append(f"openrouter ({type(e).__name__}: {str(e)[:80]})")
        elif self.is_provider_open("openrouter"):
            fallback_chain.append("openrouter (circuit_breaker_open)")
        else:
            fallback_chain.append("openrouter (no_api_key)")

        chain_str = " -> ".join(fallback_chain)
        logger.error("All Cascade tiers exhausted for media generation. Chain: %s", chain_str)
        raise RuntimeError(
            f"Todos los proveedores de la cascada fallaron al generar tarjetas desde archivo multimodal: {chain_str}"
        )

    async def generate_from_media_stream(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> AsyncGenerator[Tuple[str, List[Flashcard], int, int], None]:
        """Stream cards from media with Resilient Cascade fallback."""
        if not self.is_provider_open("gemini") and self._gemini_api_key:
            yielded_any = False
            try:
                async for item in self._primary_adapter.generate_from_media_stream(
                    file_bytes=file_bytes, mime_type=mime_type, options=options, text=text
                ):
                    yielded_any = True
                    yield item
                self.reset_circuit("gemini")
                return
            except Exception as exc:
                logger.warning("Gemini media streaming failed (yielded_any=%s): %s", yielded_any, exc)
                if self._is_rate_limit_or_overload(exc):
                    self.trip_circuit("gemini", cooldown_seconds=60.0)

        logger.info("Media streaming falling back to waterfall cascade generate_from_media...")
        all_cards = await self.generate_from_media(
            file_bytes=file_bytes, mime_type=mime_type, options=options, text=text
        )

        chunk_size = 3
        chunks = [all_cards[i:i + chunk_size] for i in range(0, len(all_cards), chunk_size)]
        total_chunks = max(1, len(chunks))

        for idx, chunk in enumerate(chunks):
            label = f"Lote Cascada {idx + 1}"
            yield (label, chunk, idx + 1, total_chunks)
            await asyncio.sleep(0.1)

    async def enrich_prerequisite(
        self, concept: str, search_query: str, context_topic: Optional[str] = None
    ) -> EnrichedConceptResult:
        return await self._primary_adapter.enrich_prerequisite(
            concept=concept, search_query=search_query, context_topic=context_topic
        )
