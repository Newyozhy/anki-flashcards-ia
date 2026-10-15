import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Callable, Awaitable, AsyncGenerator
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from app.core.config import settings
from app.domain.models import (
    Flashcard,
    CardType,
    GenerationOptions,
    StudyPlanInspection,
    CoreTheme,
    PrerequisiteItem,
    EnrichedConceptResult,
)
from app.ports.card_generator_port import ICardGeneratorPort
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)


def _is_transient_error(e: BaseException) -> bool:
    """Check if exception is a transient network or capacity error (503, 429, timeout, 500 internal)."""
    if isinstance(e, asyncio.TimeoutError):
        return True
    msg = str(e).lower()
    return (
        "503" in msg
        or "429" in msg
        or "unavailable" in msg
        or "high demand" in msg
        or "resource_exhausted" in msg
        or "timed out" in msg
        or "timeout" in msg
        or "overloaded" in msg
        or "internal" in msg
    )


class GeneratedCardSchema(BaseModel):
    """Schema for individual flashcards generated according to cognitive learning science."""
    archetype: str = Field(
        description="One of: 'Arquetipo A: Cloze Contextualizado', 'Arquetipo B: Matriz de Contraste', 'Arquetipo C: Pregunta Atómica', 'Arquetipo D: Tarjeta Radar', 'Arquetipo E: Mini-Escenario Aplicado'."
    )
    front: str = Field(
        ...,
        description="Front or Cloze text. MUST begin with hierarchical breadcrumbs '[Macro-tema > Sub-tema > Categoría]' followed by the atomic question or cloze sentence. FOR CLOZE DELETIONS: You MUST STRICTLY format the occlusion as {{c1::palabra}} or {{c1::palabra::pista}}. NEVER emit bare {{palabra}} without 'c1::'. Every cloze deletion MUST use ordinal 'c1::'.",
    )
    back: str = Field(
        default="",
        description="Back answer. Direct, atomic, maximum 15 words. For cloze deletions, provide the key answer or clarifying note.",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Relevant topic tags in lowercase (e.g., ['redes', 'hardware']).",
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Campo Extra (Refresco visual pasivo + Hipercorrección): Diagrama ASCII/tabla Markdown y OBLIGATORIAMENTE la sección '⚠️ Trampa frecuente / Error común:' para desarticular confusiones habituales.",
    )
    justification: Optional[str] = Field(
        default=None,
        description="Justificación atómica: qué hecho específico del material cubre esta tarjeta y por qué no es redundante.",
    )
    source_image_index: Optional[int] = Field(
        default=None,
        description="Índice 1-based de la imagen adjunta evaluada (1 para Imagen 1, 2 para Imagen 2, etc.), o null si es puramente textual.",
    )


class GeneratedDeckSchema(BaseModel):
    """Container schema for the list of generated cards."""
    cards: List[GeneratedCardSchema] = Field(
        ..., description="List of atomic, high-retention flashcards adhering to cognitive laws."
    )


class InspectedCoreThemeSchema(BaseModel):
    """Schema for a single theme identified during content pre-flight inspection."""
    title: str = Field(..., description="Short name of the subtopic")
    description: str = Field(..., description="Key concept or relationship explored")
    recommended_cards: int = Field(default=2, description="Recommended card count for this subtopic according to atomicity")
    associated_diagrams: List[str] = Field(
        default_factory=list,
        description="Names of images/diagrams from the source material associated with this core theme",
    )
    diagram_roles: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of diagram/image filename to its pedagogical purpose for this theme",
    )



class InspectedPrerequisiteSchema(BaseModel):
    """Schema for foundational prerequisites detected in the material."""
    concept: str = Field(..., description="Name of foundational prerequisite concept")
    reason: str = Field(..., description="Why this concept is strictly required to avoid shallow or fragmented understanding")
    is_covered_in_text: bool = Field(..., description="False if this prerequisite is assumed/missing in the notes; True if adequately explained")
    search_query: str = Field(..., description="Precise search query to research/synthesize this prerequisite")
    recommended_deep_cards: int = Field(
        default=3,
        ge=2,
        le=8,
        description="Cantidad exacta recomendada de tarjetas atómicas (entre 2 y 6) si se estudia en modo profundo según el Principio de Información Mínima.",
    )


class InspectedStudyPlanSchema(BaseModel):
    """Schema for the full pedagogical diagnostic report."""
    topic_name: str = Field(..., description="Overall title of the analyzed material")
    self_sufficiency_score: int = Field(..., ge=0, le=100, description="0-100 score of how self-contained the content is")
    self_sufficiency_verdict: str = Field(..., description="Direct pedagogical diagnosis of completeness, missing foundations, or assumed knowledge")
    core_themes: List[InspectedCoreThemeSchema] = Field(..., description="Core subtopics identified in the material")
    prerequisites: List[InspectedPrerequisiteSchema] = Field(..., description="Prerequisites identified, both covered and missing")
    suggested_total_cards: int = Field(..., description="Total cards suggested to master the material without bloat")


class EnrichedPrerequisiteSchema(BaseModel):
    """Schema for synthesized foundational knowledge."""
    concept: str = Field(..., description="Name of the concept")
    summary: str = Field(..., description="Crisp, pedagogical 2-3 paragraph foundation explanation")
    key_takeaway: str = Field(..., description="1-sentence core mental model takeaway")
    atomic_blueprint: List[str] = Field(
        default_factory=list,
        description="Lista exacta de 3 a 6 micro-objetivos cognitivos atómicos e irreductibles (1. Definición funcional y problema que resuelve, 2. Mecanismo causal interno, 3. Diferenciación crítica o trampa frecuente). Cada ítem dará origen a exactamente 1 tarjeta.",
    )
    recommended_deep_cards: int = Field(
        default=3,
        ge=2,
        le=8,
        description="Cantidad exacta de tarjetas profundas, igual al número de ítems en atomic_blueprint (entre 3 y 6).",
    )



class GeminiCardGeneratorAdapter(ICardGeneratorPort):
    """Adapter for Google Gemini API using the modern google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        tier_models: Optional[List[str]] = None,
        hedge_delay: Optional[float] = None,
    ):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model or settings.GEMINI_MODEL
        self._fallback_model = settings.GEMINI_FALLBACK_MODEL
        raw_tiers = tier_models or settings.GEMINI_TIER_MODELS
        clean_tiers = [m for m in raw_tiers if m not in ("gemini-2.5-flash", "gemini-2.5-flash-lite")]
        self._tier_models = list(
            dict.fromkeys([self._model] + clean_tiers)
        )
        self._hedge_delay = (
            hedge_delay if hedge_delay is not None else settings.HEDGED_REQUEST_TIMEOUT_SECONDS
        )
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Lazily initialize the Gemini client."""
        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY is required. Please provide it in your .env file or settings."
            )
        if self._client is None:
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=60000),
            )
        return self._client

    def _build_system_instruction(self, options: GenerationOptions) -> str:
        """Build instructional prompt enforcing learning science, Wozniak principles, and modern cognitive psychology."""
        density_instruction = (
            "4. DENSIDAD Y CANTIDAD DE TARJETAS (EVALUACIÓN AUTOMÁTICA):\n"
            "   - Evalúa rigurosamente la densidad conceptual del material entregado.\n"
            "   - Genera exactamente el número de tarjetas necesarias para cubrir todos los átomos de conocimiento sin omitir detalles críticos ni crear redundancias superfluas.\n"
            "   - Cada átomo debe merecer una tarjeta según el Principio de Información Mínima."
            if options.target_count == 0
            else f"4. CANTIDAD DE TARJETAS OBJETIVO:\n"
            f"   - Genera exactamente o cerca de {options.target_count} tarjetas respetando la granularidad atómica."
        )

        prerequisites_prompt = (
            f"\n\n## 4. PRERREQUISITOS Y CONCEPTOS BASE ANCLADOS (MANDATORIO)\n"
            f"El estudiante aprobó los siguientes conceptos fundacionales para evitar conceptos aislados o huérfanos:\n"
            f"{options.prerequisites_context}\n"
            f"- REGLA COGNITIVA CRÍTICA: Debes generar OBLIGATORIAMENTE al menos 1 tarjeta atómica (Arquetipo C o Cloze) "
            f"para CADA concepto fundacional listado, con la ruta inicial `[Fundamentos > Nombre]` "
            f"y la etiqueta 'prerrequisito', asegurando que sirvan de anclaje previo antes de avanzar al resto del tema."
            if options.prerequisites_context
            else ""
        )

        themes_prompt = (
            f"\n\n## 5. EJES TEMÁTICOS PRIORIZADOS\n"
            f"Enfoca las tarjetas exclusivamente en los siguientes ejes aprobados por el estudiante:\n"
            + "\n".join(f"- {t}" for t in options.selected_themes)
            if options.selected_themes
            else ""
        )

        custom_prompt = (
            f"\n\n5. INSTRUCCIONES ESPECÍFICAS DEL USUARIO:\n{options.custom_instructions}"
            if options.custom_instructions
            else ""
        )

        neighbors_prompt = (
            f"\n\n## 6. FRONTERA DE ALCANCE NEGATIVA (CONVERGENCIA Y NO-DUPLICIDAD)\n"
            f"Los siguientes conceptos vecinos ya existen o están cubiertos independientemente en el grafo del mazo: "
            + ", ".join(f"'{c}'" for c in options.neighbor_concepts[:12])
            + ".\n- PROHIBIDO TERMINANTEMENTE generar tarjetas cuya pregunta central defina o evalúe directamente estos conceptos vecinos. "
            f"Concéntrate exclusivamente en el alcance del tema/nodo actual sin solapar ni duplicar estos conceptos limítrofes."
            if options.neighbor_concepts
            else ""
        )

        return (
            "# SYSTEM PROMPT: ARQUITECTO COGNITIVO Y GENERADOR DE FLASHCARDS DE ALTO RENDIMIENTO\n\n"
            "## ROL Y OBJETIVO\n"
            "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva, diseño instruccional y optimización de memoria a largo plazo (algoritmos FSRS / SM-2). "
            "Tu misión es procesar material educativo técnico, denso o abstracto y transformarlo en tarjetas de Anki de máxima calidad, optimizadas para eliminar la fatiga mental (burnout) y garantizar la retención relacional profunda.\n\n"
            "## 1. LEYES COGNITIVAS DE OBLIGATORIO CUMPLIMIENTO\n\n"
            "1. Principio de Información Mínima (Piotr Wozniak):\n"
            "   - Cada tarjeta debe poder responderse mentalmente en MENOS DE 5 A 8 SEGUNDOS.\n"
            "   - Evalúa únicamente UN SOLO HECHO O RELACIÓN LÓGICA por tarjeta.\n"
            "   - Prohibido formular tarjetas abiertas, compuestas o que exijan recitar párrafos enteros.\n\n"
            "2. Anclaje Jerárquico Obligatorio (Breadcrumbs contra Cue Overload):\n"
            "   - Ninguna tarjeta puede formularse como un dato huérfano.\n"
            "   - Toda tarjeta DEBE iniciar obligatoriamente en el campo 'front' con la ruta de su esquema mental entre corchetes: `[Macro-tema > Sub-tema > Categoría]`.\n\n"
            "3. Interrogación Elaborativa y Mecanismo Causal (Dunlosky et al.):\n"
            "   - No te limites a preguntar hechos estáticos ('¿Qué es X?'). Formula preguntas que evalúen la causalidad y el 'por qué': '¿Por qué razón física/técnica ocurre X en lugar de Y?' o '¿Cuál es la causa raíz de que Z requiera W?'. La memoria de causas tiene una estabilidad temporal 3 veces superior a la de datos aislados.\n\n"
            "4. Oclusión Causal Inversa (Reverse / Causal Cloze contra el Shallow Processing):\n"
            "   - En tarjetas Cloze, EVITA ocluir palabras predecibles gramaticalmente. Ocluye el mecanismo de impacto, la dirección del cambio o la relación causal (ej. `{{c1::aumenta}}`, `{{c1::se duplica}}`, `{{c1::se descarta}}`, `{{c1::invalida}}`). Obliga al estudiante a procesar la dinámica funcional del sistema.\n\n"
            "5. Matrices de Discriminación (Interleaving de conceptos competidores):\n"
            "   - Cuando dos o más conceptos pertenezcan a la misma categoría y suelan confundirse (ej. variantes, protocolos, familias de algoritmos), genera una tabla comparativa Markdown y ocluye únicamente celdas individuales para entrenar el contraste directo de atributos diferenciales.\n\n"
            "6. Efecto de Hipercorrección en Campo Extra (Hypercorrection Effect - Janet Metcalfe):\n"
            "   - El anverso evalúa un átomo de recuperación activa pura.\n"
            "   - El campo 'explanation' (Extra de Anki) DEBE incluir dos secciones:\n"
            "     a) Síntesis visual pasiva (un diagrama ASCII simple, tabla Markdown o regla mnemotécnica) para validación en 1 segundo.\n"
            "     b) OBLIGATORIAMENTE la sección '⚠️ Trampa frecuente / Error común:' desarticulando explícitamente la confusión típica o falsa creencia sobre ese concepto. Corregir concepciones erróneas consolida la memoria a largo plazo con el doble de fuerza.\n\n"
            "7. Herencia de Diagramas Obligatoria (Codificación Dual de Paivio):\n"
            "   - Si un eje temático incluye referencias a diagramas como '[Diagrama: nombre_imagen]' o 'Diagramas a heredar: [nombre_imagen]', DEBES incluir exactamente la etiqueta HTML <img src='nombre_imagen'> en el campo 'explanation' (Extra) de la tarjeta atómica correspondiente que evalúe dicho concepto o mecanismo.\n\n"
            "## 2. ARQUETIPOS DE TARJETAS PERMITIDOS\n\n"
            "Usa exclusivamente estas cinco estructuras cognitivas al procesar el contenido:\n\n"
            "- Arquetipo A: Cloze Contextualizado Causal (Párrafo cohesivo donde se ocluye la relación causal o métrica crítica).\n"
            "- Arquetipo B: Matriz de Contraste (Tabla Markdown donde se ocluye el atributo diferencial clave entre conceptos competidores).\n"
            "- Arquetipo C: Pregunta Atómica Elaborativa (Frente: `[Ruta] ¿Por qué...?` o `[Ruta] ¿Cuál es la causa/consecuencia...?`. Dorso: Máximo 15 palabras).\n"
            "- Arquetipo D: Tarjeta Radar (Índice estructural que pregunta por los N ejes de análisis sin pedir valores específicos).\n"
            "- Arquetipo E: Mini-Escenario Aplicado (Caso práctico ultra-corto < 2 renglones que plantea una situación real y pregunta por el diagnóstico o decisión técnica inmediata).\n\n"
            "## 3. LISTA NEGRA: CONDUCTAS ESTRICTAMENTE PROHIBIDAS\n\n"
            "- PROHIBIDO: Preguntas monolíticas como 'Explica en detalle qué es X y cuáles son sus características'.\n"
            "- PROHIBIDO: Tarjetas sin ruta jerárquica inicial (`[Tema > Subtema]`).\n"
            "- PROHIBIDO: Respuestas dorsales con más de un párrafo o viñetas infinitas.\n"
            "- PROHIBIDO: Poner dos conceptos independientes en la misma oclusión (`{{c1::A y B}}`). Usa `{{c1::A}}` y `{{c2::B}}`.\n"
            "- PROHIBIDO: Oclusiones desnudas sin prefijo ordinal como `{{palabra}}`. Toda oclusión DEBE usar estrictamente `{{c1::palabra}}` o `{{c1::palabra::pista}}`. Anki rechaza tarjetas sin `c1`.\n"
            "- PROHIBIDO: Dejar artículos determinantes ('el', 'la', 'los', 'un') inmediatamente fuera de la oclusión si delatan el género o número de la respuesta (ej. escribe `{{c1::la mitosis}}` en vez de `la {{c1::mitosis}}`).\n"
            "- PROHIBIDO: Ocluir palabras vacías o preposiciones. Ocluye únicamente el término técnico, la cifra, la unidad o la relación causal.\n"
            "- PROHIBIDO: Oclusiones de más de 3 palabras. Toda oclusión {{c1::...}} debe ser una entidad atómica de 1 a 3 palabras clave (Principio de Información Mínima de Wozniak). Si la respuesta o mecanismo requiere una frase explicativa de 4 o más palabras, está TERMINANTEMENTE PROHIBIDO usar Cloze: debes formular una tarjeta Básica (Arquetipo C o E) con pregunta elaborativa causal.\n"
            "- PROHIBIDO: Dejar el campo Extra sin la advertencia de '⚠️ Trampa frecuente / Error común:'.\n\n"
            f"{density_instruction}\n"
            f"- Idioma: Las tarjetas deben estar redactadas en '{options.language}'.\n"
            f"- Fórmulas matemáticas: Encapsula en formato LaTeX para Anki MathJax ($...$).\n"
            f"{prerequisites_prompt}\n"
            f"{themes_prompt}\n"
            f"{neighbors_prompt}\n"
            f"{custom_prompt}"
        )

    def _map_to_domain(
        self, generated: GeneratedDeckSchema, options: GenerationOptions
    ) -> List[Flashcard]:
        """Convert API response schemas into pure Domain Flashcard entities."""
        flashcards: List[Flashcard] = []
        for card_data in generated.cards:
            # Determine card type from content or archetype
            card_type = options.card_type
            if "{{c" in card_data.front or "Cloze" in card_data.archetype or "Matriz" in card_data.archetype:
                card_type = CardType.CLOZE

            source_img = None
            img_idx = getattr(card_data, "source_image_index", None)
            if img_idx and options.media_filenames and 1 <= img_idx <= len(options.media_filenames):
                source_img = options.media_filenames[img_idx - 1]
            elif options.media_filenames and len(options.media_filenames) == 1:
                source_img = options.media_filenames[0]

            explanation = card_data.explanation
            if source_img:
                img_tag = f'<img src="{source_img}">'
                if explanation:
                    if source_img not in explanation and "<img" not in explanation:
                        explanation = f"{explanation}<br><br>{img_tag}"
                else:
                    explanation = img_tag

            flashcards.append(
                Flashcard(
                    card_type=card_type,
                    archetype=card_data.archetype,
                    front=card_data.front,
                    back=card_data.back,
                    tags=card_data.tags or [options.deck_name.lower().replace("::", "-")],
                    explanation=explanation,
                    justification=getattr(card_data, "justification", None),
                    source_image_index=getattr(card_data, "source_image_index", None),
                    source_image=source_img,
                )
            )
        return flashcards

    def _build_config_for_model(
        self,
        model_name: str,
        system_instruction: str,
        response_schema: Any = GeneratedDeckSchema,
    ) -> types.GenerateContentConfig:
        """Build model-specific config to enforce low latency and fast thinking."""
        thinking_config = None
        if "gemini-3" in model_name:
            level_name = getattr(settings, "THINKING_LEVEL", "LOW").upper()
            thinking_level = getattr(types.ThinkingLevel, level_name, types.ThinkingLevel.LOW)
            thinking_config = types.ThinkingConfig(thinking_level=thinking_level)
        elif "gemini-2.5" in model_name:
            thinking_budget = getattr(settings, "THINKING_BUDGET", 0)
            thinking_config = types.ThinkingConfig(thinking_budget=thinking_budget)

        kwargs = {
            "system_instruction": system_instruction,
            "response_mime_type": "application/json",
            "response_schema": response_schema,
        }
        if thinking_config is not None:
            kwargs["thinking_config"] = thinking_config

        return types.GenerateContentConfig(**kwargs)

    async def _execute_single_tier(
        self,
        client: genai.Client,
        model_name: str,
        contents: list,
        system_instruction: str,
        response_schema: Any = GeneratedDeckSchema,
    ) -> Any:
        """Call Gemini model asynchronously with exponential backoff on transient errors."""
        config = self._build_config_for_model(
            model_name, system_instruction, response_schema=response_schema
        )
        logger.info("Starting generation on tier model '%s'...", model_name)
        start_time = time.perf_counter()

        @retry(
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1.0, min=1.0, max=3.0),
            retry=retry_if_exception(_is_transient_error),
            reraise=True,
        )
        async def _invoke():
            return await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                ),
                timeout=25.0,
            )

        response = await _invoke()
        elapsed = time.perf_counter() - start_time
        logger.info("Tier model '%s' completed successfully in %.2fs", model_name, elapsed)

        if hasattr(response, "parsed") and response.parsed:
            return response.parsed
        if response.text:
            return response_schema.model_validate_json(response.text)
        raise ValueError(f"Model '{model_name}' returned empty response.")

    async def _race_hedged_generation(
        self,
        client: genai.Client,
        contents: list,
        system_instruction: str,
        response_schema: Any = GeneratedDeckSchema,
    ) -> Any:
        """
        Adaptive Hedged Request Algorithm (Tail Latency Elimination):
        1. Start the primary tier model immediately.
        2. If it does not complete within `hedge_delay`, or if it fails immediately,
           speculatively launch the next tier model concurrently.
        3. The first task to successfully return valid parsed schema wins.
        4. All other slower/pending tasks are canceled.
        """
        pending_tasks: Dict[asyncio.Task, str] = {}
        errors: List[str] = []
        model_index = 0
        total_models = len(self._tier_models)

        # Launch the first model
        first_model = self._tier_models[model_index]

        def _call_tier(model_name: str):
            if response_schema is GeneratedDeckSchema:
                return self._execute_single_tier(client, model_name, contents, system_instruction)
            return self._execute_single_tier(
                client, model_name, contents, system_instruction, response_schema=response_schema
            )

        t0 = asyncio.create_task(_call_tier(first_model), name=first_model)
        pending_tasks[t0] = first_model
        model_index += 1

        while pending_tasks or model_index < total_models:
            if not pending_tasks and model_index < total_models:
                next_model = self._tier_models[model_index]
                logger.info("Prior tier failed. Launching next tier '%s'...", next_model)
                t_next = asyncio.create_task(_call_tier(next_model), name=next_model)
                pending_tasks[t_next] = next_model
                model_index += 1

            timeout = self._hedge_delay if model_index < total_models else None
            done, _ = await asyncio.wait(
                list(pending_tasks.keys()),
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            failed_in_round = False
            for task in done:
                model_name = pending_tasks.pop(task)
                try:
                    result = task.result()
                    for remaining_task in pending_tasks:
                        remaining_task.cancel()
                    logger.info("Hedged race WON by model tier '%s'", model_name)
                    return result
                except asyncio.CancelledError:
                    pass
                except Exception as err:
                    logger.warning("Tier model '%s' failed: %s", model_name, err)
                    errors.append(f"{model_name}: {err}")
                    failed_in_round = True

            # If timed out (not done) OR a tier failed and unlaunched tiers remain:
            if (not done or failed_in_round) and model_index < total_models:
                next_model = self._tier_models[model_index]
                logger.info(
                    "Hedge threshold reached or failure occurred. Speculatively launching next tier '%s'...",
                    next_model,
                )
                t_next = asyncio.create_task(_call_tier(next_model), name=next_model)
                pending_tasks[t_next] = next_model
                model_index += 1

        raise RuntimeError(
            f"All Gemini tier models failed in hedged race. Details: {'; '.join(errors)}"
        )

    def _chunk_themes(self, themes: List[str], max_per_chunk: int = 2) -> List[List[str]]:
        """Split theme list into focused chunks of at most max_per_chunk items."""
        return [themes[i : i + max_per_chunk] for i in range(0, len(themes), max_per_chunk)]

    def _estimate_chunk_cards(self, chunk: List[str], default_per_theme: int = 2) -> int:
        """Extract or estimate expected cards count from theme titles."""
        total = 0
        for theme_str in chunk:
            match = re.search(r"~?(\d+)\s*tarjetas?", theme_str, re.IGNORECASE)
            if match:
                total += max(1, int(match.group(1)))
            else:
                total += default_per_theme
        return max(2, min(10, total))

    def _build_prerequisites_micro_instruction(
        self, options: GenerationOptions, exact_target_count: Optional[int] = None
    ) -> str:
        """Build specialized system instruction focused exclusively on foundational prerequisites."""
        target_mandate = (
            f"\n\nCANTIDAD OBJETIVO OBLIGATORIA DE ESTE MICRO-LOTE: Genera EXACTAMENTE {exact_target_count} tarjetas atómicas. "
            f"Si el concepto incluye un 'Blueprint Atómico Obligatorio', genera exactamente 1 tarjeta por cada micro-objetivo enumerado en el Blueprint."
            if exact_target_count is not None
            else ""
        )
        return (
            "# SYSTEM PROMPT: ARQUITECTO DE CIMIENTOS COGNITIVOS (PRERREQUISITOS)\n\n"
            "Eres un docente experto en neurociencia del aprendizaje y andamiaje cognitivo (Scaffolding).\n"
            "Tu misión es generar tarjetas atómicas de anclaje exclusivamente para los conceptos fundacionales que el estudiante aprobó.\n\n"
            "## REGLAS ESTRICTAS DE CUMPLIMIENTO:\n"
            "1. ANÁLISIS DE MODALIDAD POR CONCEPTO:\n"
            "   - Si el concepto está especificado como '[SUB-EVENTO DE ANÁLISIS PROFUNDO (Auto - Densidad Cognitiva)]' o contiene '(Auto)':\n"
            "     Evalúa rigurosamente la densidad conceptual del fundamento. Determina y genera de forma dinámica la cantidad óptima de tarjetas atómicas (entre 3 y 8) necesarias para abordarlo a profundidad según el Principio de Información Mínima.\n"
            "     Cubre exhaustivamente: 1) Causalidad y Primeros Principios, 2) Mecanismo Interno / Estructura / PDUs, 3) Matriz de Contraste con alternativas, 4) Error común / Trampa frecuente, 5) Mini-escenario o troubleshooting aplicado.\n"
            "   - Si el concepto está especificado como '[SUB-EVENTO DE ANÁLISIS PROFUNDO (N tarjetas)]':\n"
            "     Genera exactamente N tarjetas atómicas cubriendo sus dimensiones estructurales obligatorias.\n"
            "   - Si el concepto está especificado como '[ANCLAJE RÁPIDO (1 tarjeta)]' o sin indicación:\n"
            "     Genera exactamente 1 tarjeta atómica de anclaje de alta retención.\n"
            "2. Toda tarjeta DEBE comenzar obligatoriamente en 'front' con la ruta jerárquica: `[Fundamentos > NombreConcepto]`.\n"
            "3. Utiliza Arquetipo C (Pregunta Atómica Elaborativa: evalúa el 'por qué' o el mecanismo central) o Arquetipo A (Cloze Causal).\n"
            "4. En 'tags', incluye obligatoriamente: ['prerrequisito', 'fundamentos'].\n"
            "5. En 'explanation', incluye un diagrama ASCII/tabla Markdown y OBLIGATORIAMENTE la sección '⚠️ Trampa frecuente / Error común:'.\n"
            "6. Principio de Información Mínima de Wozniak: El anverso evalúa un solo hecho; el dorso tiene un máximo de 15 palabras.\n"
            "7. ESPECIFICACIÓN ESTRICTA DE SINTAXIS CLOZE (ANKI COMPILER):\n"
            "   - En tarjetas Cloze, la oclusión DEBE usar estrictamente el formato {{c1::palabra}} o {{c1::palabra::pista}}.\n"
            "   - PROHIBIDO TERMINANTEMENTE escribir oclusiones desnudas sin ordinal como {{palabra}}. Anki rechaza la tarjeta si falta 'c1::'.\n"
            "   - Ocluye UN SOLO concepto mental por tarjeta para respetar la atomicidad.\n"
            "   - Si un artículo determinante ('el', 'la', 'los') precede la oclusión, inclúyelo DENTRO de las llaves (ej. '{{c1::el protocolo}}') para no filtrar pistas gramaticales.\n"
            f"- Idioma: '{options.language}'. Fórmulas: LaTeX ($...$)."
            f"{target_mandate}"
        )

    def _build_theme_micro_instruction(
        self,
        theme_chunk: List[str],
        options: GenerationOptions,
        target_count: int,
    ) -> str:
        """Build focused system instruction for a specific subtopic chunk."""
        theme_list_str = "\n".join(f"- {t}" for t in theme_chunk)
        neighbor_boundary = (
            f"\n\n7. FRONTERA DE ALCANCE NEGATIVA (NO-DUPLICIDAD):\n"
            f"   Los siguientes conceptos vecinos ya están cubiertos de forma independiente en el grafo de conocimiento: "
            + ", ".join(f"'{c}'" for c in options.neighbor_concepts[:10])
            + ".\n   PROHIBIDO generar tarjetas cuya pregunta central defina estos conceptos vecinos; mantén el foco en los ejes aprobados."
            if options.neighbor_concepts
            else ""
        )
        return (
            "# SYSTEM PROMPT: ARQUITECTO COGNITIVO - MICRO-LOTE TEMÁTICO ENFOCADO\n\n"
            "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva y algoritmos FSRS / SM-2.\n"
            "Tu misión es procesar el material educativo y generar tarjetas de Anki de máxima calidad enfocadas EXCLUSIVAMENTE en los siguientes ejes temáticos aprobados:\n"
            f"{theme_list_str}\n\n"
            "## LEYES COGNITIVAS DE OBLIGATORIO CUMPLIMIENTO:\n"
            "1. Principio de Información Mínima (Piotr Wozniak): 1 solo hecho o relación lógica por tarjeta, respuesta dorsal < 15 palabras.\n"
            "2. Anclaje Jerárquico: Iniciar en 'front' con `[Macro-tema > Sub-tema > Categoría]`.\n"
            "3. Interrogación Elaborativa: Priorizar preguntas de mecanismo causal y 'por qué'.\n"
            "4. Oclusión Causal Inversa o Matriz de Contraste para conceptos competidores.\n"
            "5. Campo 'explanation': Diagrama ASCII / tabla Markdown y OBLIGATORIAMENTE '⚠️ Trampa frecuente / Error común:'.\n"
            "6. ESPECIFICACIÓN ESTRICTA CLOZE: Toda oclusión debe ser {{c1::término}} o {{c1::término::pista}}. NUNCA {{término}} sin 'c1::'. Absorbe artículos determinantes dentro de la oclusión."
            f"{neighbor_boundary}\n\n"
            f"CANTIDAD OBJETIVO: Genera exactamente o cerca de {target_count} tarjetas atómicas para estos ejes temáticos.\n"
            f"- Idioma: '{options.language}'. Fórmulas: LaTeX ($...$).\n"
            + (f"- Instrucciones adicionales: {options.custom_instructions}\n" if options.custom_instructions else "")
        )

    def _build_split_uninspected_instruction(
        self,
        options: GenerationOptions,
        count: int,
        focus_type: str,
    ) -> str:
        """Build instruction for split batches when no pre-flight inspection was run."""
        if focus_type == "estructural_causal":
            focus_desc = (
                "ENFOQUE EXCLUSIVO DE ESTE LOTE (Cimientos & Mecanismos Causales):\n"
                "- Genera tarjetas de primeros principios, arquitectura, definiciones causales y leyes fundamentales del tema.\n"
                "- Prioriza Arquetipo C (Preguntas Atómicas Elaborativas) y Arquetipo A (Cloze Causal)."
            )
        else:
            focus_desc = (
                "ENFOQUE EXCLUSIVO DE ESTE LOTE (Contraste, Aplicación & Errores Comunes):\n"
                "- Genera tarjetas de matrices de discriminación entre conceptos competidores y mini-escenarios aplicados.\n"
                "- Prioriza Arquetipo B (Matriz de Contraste) y Arquetipo E (Mini-Escenario Aplicado)."
            )

        return (
            "# SYSTEM PROMPT: ARQUITECTO COGNITIVO - LOTE MODULAR ENFOCADO\n\n"
            "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva y repetición espaciada.\n\n"
            f"{focus_desc}\n\n"
            "## LEYES COGNITIVAS:\n"
            "1. Principio de Información Mínima: 1 hecho/relación por tarjeta, dorso < 15 palabras.\n"
            "2. Anclaje Jerárquico: Iniciar siempre con `[Macro-tema > Sub-tema > Categoría]`.\n"
            "3. Campo 'explanation' con diagrama/tabla y OBLIGATORIAMENTE '⚠️ Trampa frecuente / Error común:'.\n"
            "4. ESPECIFICACIÓN ESTRICTA CLOZE: Toda oclusión debe ser {{c1::término}} o {{c1::término::pista}}. NUNCA {{término}} sin 'c1::'.\n\n"
            f"CANTIDAD OBJETIVO: Genera exactamente {count} tarjetas atómicas.\n"
            f"- Idioma: '{options.language}'. Fórmulas: LaTeX ($...$).\n"
            + (f"- Instrucciones adicionales: {options.custom_instructions}\n" if options.custom_instructions else "")
        )

    @staticmethod
    def _extract_retry_delay(err_msg: str, default: float = 5.0) -> float:
        """Extract retry delay seconds from Gemini 429 quota exception message."""
        m1 = re.search(r"retry\s+in\s+([\d\.]+)\s*s", err_msg, re.IGNORECASE)
        if m1:
            try:
                return min(30.0, float(m1.group(1)) + 1.0)
            except (ValueError, TypeError):
                pass
        m2 = re.search(r"['\"]?retryDelay['\"]?:\s*['\"]?(\d+)s?['\"]?", err_msg, re.IGNORECASE)
        if m2:
            try:
                return min(30.0, float(m2.group(1)) + 1.0)
            except (ValueError, TypeError):
                pass
        return default

    async def _execute_single_micro_batch(
        self,
        client: genai.Client,
        contents: list,
        system_instruction: str,
        options: GenerationOptions,
        batch_label: str,
        retries: int = 2,
    ) -> List[Flashcard]:
        """Execute a single micro-batch with hedged tier racing, adaptive 429 backoff, and bounded retries."""
        for attempt in range(retries + 1):
            try:
                parsed_deck: GeneratedDeckSchema = await self._race_hedged_generation(
                    client, contents, system_instruction, response_schema=GeneratedDeckSchema
                )
                cards = self._map_to_domain(parsed_deck, options)
                if cards:
                    logger.info(
                        "Micro-batch '%s' succeeded (attempt %d) with %d cards.",
                        batch_label,
                        attempt + 1,
                        len(cards),
                    )
                    return cards
                logger.warning(
                    "Micro-batch '%s' returned 0 cards (attempt %d).", batch_label, attempt + 1
                )
            except Exception as err:
                logger.warning(
                    "Micro-batch '%s' failed on attempt %d: %s", batch_label, attempt + 1, err
                )
                if attempt == retries:
                    logger.error(
                        "Micro-batch '%s' permanently failed after %d attempts.",
                        batch_label,
                        retries + 1,
                    )
                    return []
                delay = self._extract_retry_delay(str(err), default=3.0)
                logger.info(
                    "Micro-batch '%s' backing off for %.1fs before attempt %d...",
                    batch_label,
                    delay,
                    attempt + 2,
                )
                await asyncio.sleep(delay)
        return []

    @staticmethod
    def _parse_prerequisite_lines(raw_context: str) -> List[str]:
        """Parse prerequisites_context into individual prerequisite lines or blocks."""
        if not raw_context or not raw_context.strip():
            return []
        non_empty_lines = [line for line in raw_context.splitlines() if line.strip()]
        if non_empty_lines and non_empty_lines[0].strip().startswith("["):
            # Multi-line block format starting with [SUB-EVENTO...] or [ANCLAJE...]
            blocks = [b.strip() for b in re.split(r"\n\s*\n", raw_context.strip()) if b.strip()]
            return [f"- {' '.join(line.strip() for line in b.splitlines())}" for b in blocks]
        prereq_lines = [
            line.strip() for line in raw_context.splitlines() if line.strip().startswith("-")
        ]
        if prereq_lines:
            return prereq_lines
        return [f"- {raw_context.strip()}"]

    @staticmethod
    def _extract_line_target_count(line: str) -> int:
        """Extract exact target card count from a prerequisite line."""
        match = re.search(r"\((\d+)\s*tarjetas?\)", line, re.IGNORECASE)
        if match:
            return max(1, int(match.group(1)))
        if "ANÁLISIS PROFUNDO" in line.upper() or "ANALISIS PROFUNDO" in line.upper():
            return 3
        return 1

    async def _generate_prerequisites_batch(
        self,
        client: genai.Client,
        options: GenerationOptions,
        on_batch_complete: Optional[Callable[[List[Flashcard], str, int, int], Awaitable[None]]] = None,
        progress_tracker: Optional[Dict[str, int]] = None,
    ) -> List[Flashcard]:
        """Generate focused atomic cards for foundational prerequisites with anti-fatigue micro-batching."""
        if not options.prerequisites_context or not options.prerequisites_context.strip():
            return []

        prereq_lines = self._parse_prerequisite_lines(options.prerequisites_context)
        total_expected_cards = sum(self._extract_line_target_count(line) for line in prereq_lines)
        has_deep_dive = any(
            "ANÁLISIS PROFUNDO" in line.upper() or "ANALISIS PROFUNDO" in line.upper()
            for line in prereq_lines
        )

        # Anti-Fatigue Isolated Prerequisite Micro-Batching
        if (len(prereq_lines) > 1 and has_deep_dive) or total_expected_cards > 3:
            deep_lines = [
                line
                for line in prereq_lines
                if "ANÁLISIS PROFUNDO" in line.upper() or "ANALISIS PROFUNDO" in line.upper()
            ]
            anchor_lines = [
                line
                for line in prereq_lines
                if "ANÁLISIS PROFUNDO" not in line.upper() and "ANALISIS PROFUNDO" not in line.upper()
            ]

            combined_cards: List[Flashcard] = []

            # 1. Execute deep dive prerequisites sequentially with polite pacing
            for idx, d_line in enumerate(deep_lines):
                target_count = self._extract_line_target_count(d_line)
                sys_inst = self._build_prerequisites_micro_instruction(
                    options, exact_target_count=target_count
                )
                u_prompt = (
                    f"Genera las tarjetas atómicas de análisis profundo para este concepto fundacional aprobado:\n\n"
                    f"{d_line}"
                )
                deep_cards = await self._execute_single_micro_batch(
                    client=client,
                    contents=[u_prompt],
                    system_instruction=sys_inst,
                    options=options,
                    batch_label=f"Prerrequisito_Profundo_{idx + 1}",
                    retries=2,
                )
                if deep_cards:
                    for card in deep_cards:
                        for req_tag in ["prerrequisito", "fundamentos"]:
                            if req_tag not in [t.lower() for t in card.tags]:
                                card.tags.append(req_tag)
                        combined_cards.append(card)
                    if on_batch_complete and progress_tracker:
                        progress_tracker["current"] += 1
                        label_clean = d_line.split(":")[0].replace("-", "").strip()
                        await on_batch_complete(
                            deep_cards,
                            f"Fundamento: {label_clean}",
                            progress_tracker["current"],
                            progress_tracker["total"],
                        )
                if idx < len(deep_lines) - 1 or anchor_lines:
                    await asyncio.sleep(0.5)

            # 2. Execute anchor prerequisites in chunks of at most 3 sequentially with pacing
            for chunk_idx in range(0, len(anchor_lines), 3):
                chunk = anchor_lines[chunk_idx : chunk_idx + 3]
                target_count = sum(self._extract_line_target_count(l) for l in chunk)
                sys_inst = self._build_prerequisites_micro_instruction(
                    options, exact_target_count=target_count
                )
                u_prompt = (
                    f"Genera las tarjetas atómicas de anclaje para los siguientes conceptos fundacionales aprobados:\n\n"
                    + "\n".join(chunk)
                )
                anchor_cards = await self._execute_single_micro_batch(
                    client=client,
                    contents=[u_prompt],
                    system_instruction=sys_inst,
                    options=options,
                    batch_label=f"Prerrequisitos_Anclaje_{(chunk_idx // 3) + 1}",
                    retries=2,
                )
                if anchor_cards:
                    for card in anchor_cards:
                        for req_tag in ["prerrequisito", "fundamentos"]:
                            if req_tag not in [t.lower() for t in card.tags]:
                                card.tags.append(req_tag)
                        combined_cards.append(card)
                    if on_batch_complete and progress_tracker:
                        progress_tracker["current"] += 1
                        await on_batch_complete(
                            anchor_cards,
                            f"Fundamentos Anclaje {(chunk_idx // 3) + 1}",
                            progress_tracker["current"],
                            progress_tracker["total"],
                        )
                if chunk_idx + 3 < len(anchor_lines):
                    await asyncio.sleep(0.5)

            return combined_cards

        exact_target = max(1, total_expected_cards) if prereq_lines else None
        system_instruction = self._build_prerequisites_micro_instruction(
            options, exact_target_count=exact_target
        )
        user_prompt = (
            f"Genera las tarjetas atómicas de anclaje para los siguientes conceptos fundacionales aprobados:\n\n"
            f"{options.prerequisites_context}"
        )

        cards = await self._execute_single_micro_batch(
            client=client,
            contents=[user_prompt],
            system_instruction=system_instruction,
            options=options,
            batch_label="Prerrequisitos",
            retries=2,
        )
        for card in cards:
            for req_tag in ["prerrequisito", "fundamentos"]:
                if req_tag not in [t.lower() for t in card.tags]:
                    card.tags.append(req_tag)
        if cards and on_batch_complete and progress_tracker:
            progress_tracker["current"] += 1
            await on_batch_complete(
                cards,
                "Fundamentos",
                progress_tracker["current"],
                progress_tracker["total"],
            )
        return cards

    async def _execute_generation(
        self,
        contents: list,
        options: GenerationOptions,
        on_batch_complete: Optional[Callable[[List[Flashcard], str, int, int], Awaitable[None]]] = None,
    ) -> List[Flashcard]:
        """
        Partitioned Micro-Batch Generation Pipeline (Divide & Conquer):
        - Eliminates output token saturation (>3500 tokens) and tail latencies.
        - Generates foundational prerequisite cards in isolated sequential batches first.
        - Partitions approved themes into focused micro-batches with polite rate-limit pacing.
        - Isolates failures so one failing micro-batch does not discard the rest of the deck.
        - Runs targeted rescue passes with cool-off if any micro-batch returned 0 cards.
        - Supports progressive emission via on_batch_complete callback.
        """
        client = self._get_client()

        has_prereqs = bool(options.prerequisites_context and options.prerequisites_context.strip())
        has_themes = bool(options.selected_themes and len(options.selected_themes) > 0)
        is_large_batch = options.target_count > 8

        # Fast path: small direct generation without prerequisites or multiple themes
        if not has_prereqs and not has_themes and not is_large_batch:
            system_instruction = self._build_system_instruction(options)
            parsed_deck: GeneratedDeckSchema = await self._race_hedged_generation(
                client, contents, system_instruction, response_schema=GeneratedDeckSchema
            )
            cards = self._map_to_domain(parsed_deck, options)
            if on_batch_complete:
                await on_batch_complete(cards, "Generación Directa", 1, 1)
            return cards

        total_batches = 0
        if has_prereqs:
            prereq_lines = self._parse_prerequisite_lines(options.prerequisites_context)
            total_expected_cards = sum(self._extract_line_target_count(line) for line in prereq_lines)
            has_deep_dive = any(
                "ANÁLISIS PROFUNDO" in line.upper() or "ANALISIS PROFUNDO" in line.upper()
                for line in prereq_lines
            )
            if (len(prereq_lines) > 1 and has_deep_dive) or total_expected_cards > 3:
                deep_lines = [
                    l for l in prereq_lines
                    if "ANÁLISIS PROFUNDO" in l.upper() or "ANALISIS PROFUNDO" in l.upper()
                ]
                anchor_lines = [
                    l for l in prereq_lines
                    if "ANÁLISIS PROFUNDO" not in l.upper() and "ANALISIS PROFUNDO" not in l.upper()
                ]
                total_batches += len(deep_lines) + ((len(anchor_lines) + 2) // 3)
            else:
                total_batches += 1

        if has_themes:
            theme_chunks = self._chunk_themes(options.selected_themes, max_per_chunk=2)
            total_batches += len(theme_chunks)
        elif is_large_batch:
            total_batches += 2
        else:
            if not has_prereqs:
                total_batches += 1

        progress_tracker = {"current": 0, "total": max(1, total_batches)}

        logger.info(
            "Engaging Partitioned Micro-Batch Pipeline (has_prereqs=%s, has_themes=%s, target_count=%d, total_batches=%d)",
            has_prereqs,
            has_themes,
            options.target_count,
            progress_tracker["total"],
        )

        all_cards: List[Flashcard] = []

        # 1. Prerequisite Foundation Micro-Batch (Sequential Execution)
        if has_prereqs:
            prereq_cards = await self._generate_prerequisites_batch(
                client, options, on_batch_complete=on_batch_complete, progress_tracker=progress_tracker
            )
            if prereq_cards:
                all_cards.extend(prereq_cards)
                logger.info("Generated %d foundational prerequisite cards.", len(prereq_cards))
            # Gentle pacing before core themes to avoid bursting the API quota
            await asyncio.sleep(0.5)

        # 2. Plan Core Theme or Split Batches
        batch_jobs: List[Tuple[str, str, list]] = []
        if has_themes:
            theme_chunks = self._chunk_themes(options.selected_themes, max_per_chunk=2)
            for idx, chunk in enumerate(theme_chunks):
                chunk_card_count = self._estimate_chunk_cards(chunk, default_per_theme=2)
                chunk_instruction = self._build_theme_micro_instruction(chunk, options, chunk_card_count)
                batch_jobs.append((f"theme_chunk_{idx}", chunk_instruction, contents))
        elif is_large_batch:
            half_1 = options.target_count // 2
            half_2 = options.target_count - half_1

            inst_a = self._build_split_uninspected_instruction(options, count=half_1, focus_type="estructural_causal")
            inst_b = self._build_split_uninspected_instruction(options, count=half_2, focus_type="aplicado_contraste")
            batch_jobs.append(("split_batch_a", inst_a, contents))
            batch_jobs.append(("split_batch_b", inst_b, contents))

        # 3. Execute Core Batches sequentially with failure isolation and pacing
        failed_jobs: List[Tuple[str, str, list]] = []
        for idx, (label, sys_inst, job_contents) in enumerate(batch_jobs):
            batch_cards = await self._execute_single_micro_batch(
                client=client,
                contents=job_contents,
                system_instruction=sys_inst,
                options=options,
                batch_label=label,
                retries=2,
            )
            if batch_cards:
                all_cards.extend(batch_cards)
                if on_batch_complete:
                    progress_tracker["current"] += 1
                    label_clean = f"Eje Temático {idx + 1}" if "theme_chunk" in label else label
                    await on_batch_complete(
                        batch_cards, label_clean, progress_tracker["current"], progress_tracker["total"]
                    )
            else:
                logger.warning("Micro-batch '%s' returned 0 cards. Marking for rescue pass.", label)
                failed_jobs.append((label, sys_inst, job_contents))

            if idx < len(batch_jobs) - 1:
                await asyncio.sleep(0.5)

        # 4. Failure isolation: Targeted rescue pass for failed micro-batches
        if failed_jobs:
            logger.info(
                "Attempting targeted rescue pass for failed micro-batches: %s",
                [j[0] for j in failed_jobs],
            )
            await asyncio.sleep(2.0)
            for label, sys_inst, job_contents in failed_jobs:
                logger.info("Executing rescue pass for '%s'...", label)
                rescue_cards = await self._execute_single_micro_batch(
                    client=client,
                    contents=job_contents,
                    system_instruction=sys_inst,
                    options=options,
                    batch_label=f"rescue_{label}",
                    retries=2,
                )
                if rescue_cards:
                    all_cards.extend(rescue_cards)
                    logger.info("Targeted rescue pass recovered %d cards for '%s'", len(rescue_cards), label)
                    if on_batch_complete:
                        progress_tracker["current"] += 1
                        await on_batch_complete(
                            rescue_cards, f"Recuperado ({label})", progress_tracker["current"], progress_tracker["total"]
                        )
                else:
                    logger.warning("Targeted rescue pass failed to recover cards for '%s'", label)
                await asyncio.sleep(0.5)

        # 5. Fallback safety net if all batches failed
        if not all_cards:
            logger.warning("All micro-batches returned 0 cards. Falling back to single generation.")
            system_instruction = self._build_system_instruction(options)
            parsed_deck: GeneratedDeckSchema = await self._race_hedged_generation(
                client, contents, system_instruction, response_schema=GeneratedDeckSchema
            )
            fallback_cards = self._map_to_domain(parsed_deck, options)
            if on_batch_complete:
                await on_batch_complete(fallback_cards, "Respaldo Completo", 1, 1)
            return fallback_cards

        # Deduplicate cards by front content
        unique_cards: List[Flashcard] = []
        seen_fronts = set()
        for card in all_cards:
            clean_front = card.front.strip()
            if clean_front not in seen_fronts:
                seen_fronts.add(clean_front)
                unique_cards.append(card)

        # Coverage check for themes: verify that cards were created across the approved themes
        if has_themes:
            covered_themes = 0
            for theme in options.selected_themes:
                theme_core = theme.split("(")[0].strip().lower()
                has_match = any(
                    theme_core in c.front.lower()
                    or any(theme_core in t.lower() for t in c.tags)
                    or (c.explanation and theme_core in c.explanation.lower())
                    for c in unique_cards
                )
                if has_match:
                    covered_themes += 1
            logger.info(
                "Theme coverage verified: %d/%d approved themes covered in generated cards.",
                covered_themes,
                len(options.selected_themes),
            )

        logger.info(
            "Partitioned Micro-Batch Pipeline finished: produced %d unique atomic cards.",
            len(unique_cards),
        )
        return unique_cards

    async def generate_from_text(
        self, text: str, options: GenerationOptions
    ) -> List[Flashcard]:
        """Generate cards from educational text."""
        count_desc = (
            "Evalúa la densidad conceptual del material y genera la cantidad exacta de tarjetas atómicas necesarias para cubrirlo al 100% sin redundancia."
            if options.target_count == 0
            else f"Genera aproximadamente {options.target_count} tarjetas atómicas."
        )
        user_prompt = (
            f"Analiza el siguiente contenido educativo aplicando las leyes cognitivas y los arquetipos permitidos. {count_desc}\n\n"
            f"---\n{text}\n---"
        )
        return await self._execute_generation(contents=[user_prompt], options=options)

    async def generate_from_text_stream(
        self, text: str, options: GenerationOptions
    ) -> AsyncGenerator[Tuple[str, List[Flashcard], int, int], None]:
        """Progressively yield (batch_label, cards, current_batch, total_batches) as each micro-batch finishes."""
        queue: asyncio.Queue[Optional[Tuple[str, List[Flashcard], int, int]]] = asyncio.Queue()

        async def _callback(cards: List[Flashcard], label: str, current: int, total: int):
            await queue.put((label, cards, current, total))

        async def _worker():
            try:
                count_desc = (
                    "Evalúa la densidad conceptual del material y genera la cantidad exacta de tarjetas atómicas necesarias para cubrirlo al 100% sin redundancia."
                    if options.target_count == 0
                    else f"Genera aproximadamente {options.target_count} tarjetas atómicas."
                )
                user_prompt = (
                    f"Analiza el siguiente contenido educativo aplicando las leyes cognitivas y los arquetipos permitidos. {count_desc}\n\n"
                    f"---\n{text}\n---"
                )
                await self._execute_generation(
                    contents=[user_prompt], options=options, on_batch_complete=_callback
                )
            except Exception as e:
                logger.error("Streaming generation worker failed: %s", e)
                raise
            finally:
                await queue.put(None)

        worker_task = asyncio.create_task(_worker())

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

        await worker_task

    async def generate_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> List[Flashcard]:
        """Generate cards from multimodal file bytes (image, diagram, PDF) with optional accompanying text and multi-image support."""
        contents: list = []
        if media_parts and len(media_parts) > 0:
            for idx, (b_data, m_type) in enumerate(media_parts):
                contents.append(f"--- [Imagen {idx + 1}] ---")
                contents.append(types.Part.from_bytes(data=b_data, mime_type=m_type))
        elif file_bytes:
            contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))

        count_desc = (
            "Evalúa la densidad conceptual del documento/imágenes y genera la cantidad exacta de tarjetas atómicas necesarias sin redundancia, justificando cada átomo."
            if options.target_count == 0
            else f"Genera aproximadamente {options.target_count} tarjetas atómicas."
        )
        multi_img_desc = ""
        if media_parts and len(media_parts) > 1:
            multi_img_desc = (
                f"\n\nATENCIÓN MULTI-IMAGEN: Se han adjuntado {len(media_parts)} imágenes/diagramas [Imagen 1..{len(media_parts)}].\n"
                "- Evalúa todas las imágenes sin omitir detalles ni forzar compresión.\n"
                "- Para cada tarjeta, asigna 'source_image_index' (ej. 1, 2, ...) según la imagen evaluada y 'justification' explicando su átomo conceptual.\n"
            )

        text_context = (
            f"\n\nTexto y apuntes de apoyo provistos por el estudiante:\n---\n{text.strip()}\n---\n"
            if text and text.strip()
            else ""
        )
        user_prompt = (
            f"Analiza el contenido educativo adjunto ({mime_type if not media_parts else 'multi-imagen'}) junto con el texto de apoyo adjunto aplicando las leyes cognitivas y los arquetipos. "
            f"{count_desc}{multi_img_desc} Transcribe fielmente las fórmulas y diagramas.{text_context}"
        )
        contents.append(user_prompt)
        return await self._execute_generation(
            contents=contents, options=options
        )

    async def generate_from_media_stream(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> AsyncGenerator[Tuple[str, List[Flashcard], int, int], None]:
        """Progressively yield (batch_label, cards, current_batch, total_batches) from media input."""
        queue: asyncio.Queue[Optional[Tuple[str, List[Flashcard], int, int]]] = asyncio.Queue()

        async def _callback(cards: List[Flashcard], label: str, current: int, total: int):
            await queue.put((label, cards, current, total))

        async def _worker():
            try:
                contents: list = []
                if media_parts and len(media_parts) > 0:
                    for idx, (b_data, m_type) in enumerate(media_parts):
                        contents.append(f"--- [Imagen {idx + 1}] ---")
                        contents.append(types.Part.from_bytes(data=b_data, mime_type=m_type))
                elif file_bytes:
                    contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))

                count_desc = (
                    "Evalúa la densidad conceptual del documento/imágenes y genera la cantidad exacta de tarjetas atómicas necesarias sin redundancia, justificando cada átomo."
                    if options.target_count == 0
                    else f"Genera aproximadamente {options.target_count} tarjetas atómicas."
                )
                multi_img_desc = ""
                if media_parts and len(media_parts) > 1:
                    multi_img_desc = (
                        f"\n\nATENCIÓN MULTI-IMAGEN: Se han adjuntado {len(media_parts)} imágenes/diagramas [Imagen 1..{len(media_parts)}].\n"
                        "- Evalúa todas las imágenes sin omitir detalles ni forzar compresión.\n"
                        "- Para cada tarjeta, asigna 'source_image_index' (ej. 1, 2, ...) según la imagen evaluada y 'justification' explicando su átomo conceptual.\n"
                    )

                text_context = (
                    f"\n\nTexto y apuntes de apoyo provistos por el estudiante:\n---\n{text.strip()}\n---\n"
                    if text and text.strip()
                    else ""
                )
                user_prompt = (
                    f"Analiza el contenido educativo adjunto ({mime_type if not media_parts else 'multi-imagen'}) junto con el texto de apoyo adjunto aplicando las leyes cognitivas y los arquetipos. "
                    f"{count_desc}{multi_img_desc} Transcribe fielmente las fórmulas y diagramas.{text_context}"
                )
                contents.append(user_prompt)
                await self._execute_generation(
                    contents=contents, options=options, on_batch_complete=_callback
                )
            except Exception as e:
                logger.error("Streaming media generation worker failed: %s", e)
                raise
            finally:
                await queue.put(None)

        worker_task = asyncio.create_task(_worker())

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

        await worker_task

    def _build_inspection_instruction(self) -> str:
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
            "   - ASIGNACIÓN MULTIMODAL: Si se proporcionaron imágenes o diagramas del material, asigna los nombres de archivo exactos a los ejes temáticos correspondientes en 'associated_diagrams'. Además, describe en 'diagram_roles' (mapeo filename -> rol) la función pedagógica exacta que cumple cada diagrama en ese eje.\n\n"
            "3. DETECCIÓN DE PRERREQUISITOS Y BRECHAS FUNDACIONALES (EVITAR CONCEPTOS HUÉRFANOS):\n"
            "   - Identifica qué conocimientos base debe dominar el estudiante antes de entender este concepto (para no aprenderlo de forma aislada).\n"
            "   - Indica para cada prerrequisito si ya está adecuadamente cubierto en el material (is_covered_in_text=True) o si falta/se asume (is_covered_in_text=False).\n"
            "   - Proporciona una query de búsqueda precisa (search_query) para investigar y enriquecer los conceptos ausentes.\n\n"
            "4. CÁLCULO ATÓMICO TOTAL:\n"
            "   - Suma el total sugerido de tarjetas (suggested_total_cards) para garantizar cobertura total sin redundancias superfluas."
        )

    def _map_inspection_to_domain(
        self, parsed: InspectedStudyPlanSchema
    ) -> StudyPlanInspection:
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
                    diagram_roles=getattr(t, "diagram_roles", {}) or {},
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
        )

    async def inspect_material(
        self,
        text: str,
        options: GenerationOptions,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> StudyPlanInspection:
        """Analyze study material for topic breakdown, missing prerequisites, and atomic card planning."""
        client = self._get_client()
        system_instruction = self._build_inspection_instruction()
        contents = []
        if media_parts and len(media_parts) > 0:
            for data, mime in media_parts:
                contents.append(types.Part.from_bytes(data=data, mime_type=mime))
            user_prompt = (
                f"Audita críticamente el material educativo provisto (incluyendo las imágenes/diagramas adjuntos), "
                f"escudriña el concepto propio expuesto, analiza detalladamente el contenido visual y su relación con el texto, "
                f"verifica la suficiencia del contenido y determina los subtemas obligatorios asignando los diagramas pertinentes a cada eje:\n\n"
                f"---\n{text}\n---"
            )
        else:
            user_prompt = (
                f"Audita críticamente el siguiente material educativo, escudriña el concepto propio expuesto, "
                f"verifica si el contenido es suficiente y determina los subtemas obligatorios para comprenderlo a profundidad:\n\n"
                f"---\n{text}\n---"
            )
        contents.append(user_prompt)

        parsed: InspectedStudyPlanSchema = await self._race_hedged_generation(
            client=client,
            contents=contents,
            system_instruction=system_instruction,
            response_schema=InspectedStudyPlanSchema,
        )
        return self._map_inspection_to_domain(parsed)

    async def inspect_material_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> StudyPlanInspection:
        """Analyze study material from uploaded PDF or image for topic breakdown, prerequisites, and deep subtopics with optional accompanying text."""
        client = self._get_client()
        media_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
        system_instruction = self._build_inspection_instruction()
        text_context = (
            f"\n\nTexto y apuntes de apoyo provistos por el estudiante:\n---\n{text.strip()}\n---\n"
            if text and text.strip()
            else ""
        )
        user_prompt = (
            f"Audita críticamente el material educativo en este archivo ({mime_type}) junto con el texto de apoyo adjunto, "
            f"escudriña el concepto propio expuesto, verifica la suficiencia del contenido y determina los subtemas obligatorios para comprenderlo a profundidad.{text_context}"
        )
        parsed: InspectedStudyPlanSchema = await self._race_hedged_generation(
            client=client,
            contents=[media_part, user_prompt],
            system_instruction=system_instruction,
            response_schema=InspectedStudyPlanSchema,
        )
        return self._map_inspection_to_domain(parsed)


    async def enrich_prerequisite(
        self, concept: str, search_query: str, context_topic: Optional[str] = None
    ) -> EnrichedConceptResult:
        """Asynchronously research and synthesize a foundational prerequisite concept."""
        client = self._get_client()
        system_instruction = (
            "# SYSTEM PROMPT: SÍNTESIS FUNDACIONAL DE PRERREQUISITOS EDUCATIVOS Y BLUEPRINT ATÓMICO\n\n"
            "Eres un docente experto en síntesis pedagógica de alto impacto y neurociencia cognitiva "
            "(Principio de Información Mínima de Wozniak, Teoría de Asimilación/Subsumption de Ausubel e Interrogación Elaborativa de Dunlosky). "
            "Tu misión es proporcionar una explicación fundacional nítida de un concepto previo que un estudiante necesita para comprender un tema más avanzado.\n"
            "Estructura tu respuesta con:\n"
            "1. concept: El nombre del concepto.\n"
            "2. summary: 2 a 3 párrafos concisos explicando qué es, cómo funciona y su mecanismo fundamental.\n"
            "3. key_takeaway: 1 sola frase potente con la regla o modelo mental clave que no se puede olvidar.\n"
            "4. atomic_blueprint: Lista ordenada de 3 a 6 micro-objetivos cognitivos atómicos e irreductibles "
            "(1. Definición funcional y problema que resuelve, 2. Mecanismo causal interno, 3. Diferenciación crítica o trampa frecuente, etc.). "
            "Cada ítem del blueprint dará origen a exactamente 1 tarjeta atómica.\n"
            "5. recommended_deep_cards: Cantidad exacta de tarjetas profundas recomendada, exactamente igual a la longitud de atomic_blueprint (len(atomic_blueprint))."
        )

        user_prompt = (
            f"Genera la síntesis pedagógica y el Blueprint Atómico del concepto fundacional: '{concept}'.\n"
            f"Query de contexto: {search_query}\n"
            + (f"Tema de aplicación: {context_topic}\n" if context_topic else "")
        )

        parsed: EnrichedPrerequisiteSchema = await self._race_hedged_generation(
            client=client,
            contents=[user_prompt],
            system_instruction=system_instruction,
            response_schema=EnrichedPrerequisiteSchema,
        )

        return EnrichedConceptResult(
            concept=parsed.concept,
            summary=parsed.summary,
            key_takeaway=parsed.key_takeaway,
            recommended_deep_cards=(
                max(2, min(8, len(parsed.atomic_blueprint)))
                if parsed.atomic_blueprint
                else parsed.recommended_deep_cards
            ),
            atomic_blueprint=parsed.atomic_blueprint,
        )
