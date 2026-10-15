import base64
import io
import json
import logging
import re
from typing import List, Optional, Dict, Any, Tuple
from uuid import uuid4
import httpx

from app.domain.models import (
    Flashcard,
    CardType,
    GenerationOptions,
    StudyPlanInspection,
    EnrichedConceptResult,
    CoreTheme,
    PrerequisiteItem,
)
from app.ports.card_generator_port import ICardGeneratorPort
from app.core.cloze_sanitizer import ClozeSanitizer

logger = logging.getLogger(__name__)


class OllamaCardGeneratorAdapter(ICardGeneratorPort):
    """
    Adapter for local LLM inference via Ollama on Windows.
    Provides offline, zero-token-cost generation and cognitive auditing.
    Default models: qwen2.5:14b (high-reasoning text) or qwen2.5vl:7b (multimodal vision).
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:14b",
        timeout: float = 60.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def check_availability(self) -> Dict[str, Any]:
        """Check if local Ollama daemon is running, list available models, and identify models active in VRAM."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = [m.get("name") for m in data.get("models", [])]

                    running_models = []
                    try:
                        ps_res = await client.get(f"{self.base_url}/api/ps")
                        if ps_res.status_code == 200:
                            ps_data = ps_res.json()
                            running_models = [m.get("name") for m in ps_data.get("models", [])]
                    except Exception as ps_err:
                        logger.debug("Failed to query Ollama running models: %s", ps_err)

                    return {
                        "is_available": True,
                        "models": models,
                        "running_models": running_models,
                        "active_model": self.model,
                    }
        except Exception as err:
            logger.debug("Ollama is not running locally: %s", err)
        return {
            "is_available": False,
            "models": [],
            "running_models": [],
            "active_model": self.model,
            "error": "Ollama server is not running on 127.0.0.1:11434",
        }

    def _should_partition_generation(self, options: GenerationOptions) -> bool:
        """Determine whether to partition generation into anti-fatigue sequential micro-batches."""
        has_prereqs = bool(options.prerequisites_context and options.prerequisites_context.strip())
        has_themes = bool(options.selected_themes and len(options.selected_themes) > 0)
        return (has_prereqs and has_themes) or (options.target_count > 6)

    @staticmethod
    def _parse_prerequisite_lines(raw_context: str) -> List[str]:
        """Parse prerequisites_context into individual prerequisite lines or blocks."""
        if not raw_context or not raw_context.strip():
            return []
        non_empty_lines = [line for line in raw_context.splitlines() if line.strip()]
        if non_empty_lines and non_empty_lines[0].strip().startswith("["):
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

    async def _call_ollama_json(
        self,
        model_to_use: str,
        system_prompt: str,
        user_prompt: str,
        options: GenerationOptions,
        required_tags: Optional[List[str]] = None,
    ) -> List[Flashcard]:
        """Execute a single JSON chat request against Ollama and parse domain Flashcard objects."""
        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama error {res.status_code}: {res.text}")

            data = res.json()
            raw_content = data.get("message", {}).get("content", "{}")
            parsed = json.loads(raw_content)
            cards_list = parsed.get("cards", [])

            flashcards: List[Flashcard] = []
            for c in cards_list:
                front = c.get("front", "").strip()
                card_type = options.card_type
                if "{{c" in front or "cloze" in c.get("archetype", "").lower():
                    card_type = CardType.CLOZE

                tags = list(c.get("tags", [options.deck_name.lower()]))
                if required_tags:
                    for r_tag in required_tags:
                        if r_tag.lower() not in [t.lower() for t in tags]:
                            tags.append(r_tag)

                card = Flashcard(
                    id=str(uuid4()),
                    card_type=card_type,
                    archetype=c.get("archetype", "Arquetipo C: Pregunta Atómica"),
                    front=front,
                    back=c.get("back", "").strip(),
                    tags=tags,
                    explanation=c.get("explanation"),
                )
                flashcards.append(ClozeSanitizer.sanitize_card(card))

            return flashcards

    async def _generate_single_batch_from_text(
        self, text: str, options: GenerationOptions
    ) -> List[Flashcard]:
        """Single-batch fallback generation for small/simple Ollama requests."""
        count_desc = (
            f"Debes generar EXACTAMENTE {options.target_count} tarjetas atómicas en total (cubriendo tanto los prerrequisitos como los temas principales)."
            if options.target_count > 0
            else "Evalúa la densidad conceptual del material y genera la cantidad exacta de tarjetas atómicas necesarias sin redundancia."
        )

        prerequisites_prompt = ""
        if options.prerequisites_context and options.prerequisites_context.strip():
            prerequisites_prompt = (
                f"\n\n## PRERREQUISITOS Y CIMIENTOS COGNITIVOS APROBADOS:\n"
                f"{options.prerequisites_context}\n"
                f"- REGLA OBLIGATORIA: Genera tarjetas atómicas para estos conceptos fundacionales. "
                f"Toda tarjeta de prerrequisito DEBE comenzar en 'front' con la ruta '[Fundamentos > Concepto]' "
                f"y contener en 'tags' la etiqueta 'prerrequisito'."
            )

        themes_prompt = ""
        if options.selected_themes and len(options.selected_themes) > 0:
            themes_list = "\n".join(f"- {t}" for t in options.selected_themes)
            themes_prompt = (
                f"\n\n## EJES TEMÁTICOS PRIORIZADOS:\n"
                f"Distribuye las tarjetas principales cubriendo estos ejes temáticos:\n{themes_list}"
            )

        custom_prompt = ""
        if options.custom_instructions and options.custom_instructions.strip():
            custom_prompt = f"\n\nInstrucciones adicionales del estudiante:\n{options.custom_instructions.strip()}"

        system_prompt = (
            "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva (Wozniak, FSRS).\n"
            "Tu tarea es generar tarjetas de Anki atómicas de alta retención.\n"
            "REGLAS COGNITIVAS:\n"
            "1. Anclaje jerárquico obligatorio en 'front': '[Tema > Subtema] Pregunta o Cloze'.\n"
            "   - Para prerrequisitos fundacionales, usa siempre: '[Fundamentos > NombreConcepto] Pregunta o Cloze'.\n"
            "2. Principio de Información Mínima: 1 solo hecho o relación lógica por tarjeta. Respuestas concisas (< 15 palabras).\n"
            "3. Si es Cloze, DEBE usar estrictamente '{{c1::palabra}}'. NUNCA '{{palabra}}' sin 'c1::'.\n"
            "4. En 'explanation', incluir '⚠️ Trampa frecuente / Error común:'.\n"
            f"5. CANTIDAD DE TARJETAS: {count_desc}\n"
            "6. Responder EXCLUSIVAMENTE con un JSON con la clave 'cards' que contenga una lista de objetos: "
            "[{'archetype': str, 'front': str, 'back': str, 'tags': [str], 'explanation': str}]."
        )

        user_prompt = (
            f"Contenido educativo a procesar:\n\n{text}"
            f"{themes_prompt}"
            f"{prerequisites_prompt}"
            f"{custom_prompt}\n\n"
            f"Genera las tarjetas en idioma '{options.language}'. {count_desc}"
        )

        model_to_use = options.local_model or self.model
        req_tags = ["prerrequisito", "fundamentos"] if (prerequisites_prompt and not themes_prompt) else None
        return await self._call_ollama_json(
            model_to_use=model_to_use,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            options=options,
            required_tags=req_tags,
        )

    async def generate_from_text(
        self, text: str, options: GenerationOptions
    ) -> List[Flashcard]:
        """Generate flashcards from text using the local Ollama model with anti-fatigue micro-batching."""
        if not self._should_partition_generation(options):
            return await self._generate_single_batch_from_text(text, options)

        model_to_use = options.local_model or self.model
        all_cards: List[Flashcard] = []
        prereq_cards_planned = 0

        # 1. Prerequisite micro-batches (isolated Deep Dive + grouped anchors max 3)
        if options.prerequisites_context and options.prerequisites_context.strip():
            prereq_lines = self._parse_prerequisite_lines(options.prerequisites_context)
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

            prereq_batches: List[tuple[List[str], int]] = []
            for d_line in deep_lines:
                cnt = self._extract_line_target_count(d_line)
                prereq_batches.append(([d_line], cnt))
                prereq_cards_planned += cnt

            for idx in range(0, len(anchor_lines), 3):
                chunk = anchor_lines[idx : idx + 3]
                cnt = sum(self._extract_line_target_count(l) for l in chunk)
                prereq_batches.append((chunk, cnt))
                prereq_cards_planned += cnt

            for batch_lines, exact_target_count in prereq_batches:
                prereq_sys = (
                    "Eres un Arquitecto de Cimientos Cognitivos experto en neurociencia (Wozniak, Ausubel).\n"
                    "Tu misión es generar tarjetas de Anki atómicas EXCLUSIVAMENTE para los prerrequisitos fundacionales indicados.\n"
                    "REGLAS OBLIGATORIAS:\n"
                    "1. Toda tarjeta DEBE comenzar en 'front' con el breadcrumb '[Fundamentos > Concepto]'.\n"
                    "2. En 'tags' DEBE incluir obligatoriamente ['prerrequisito', 'fundamentos'].\n"
                    "3. Principio de Información Mínima: 1 solo hecho o mecanismo causal por tarjeta, dorso < 15 palabras.\n"
                    "4. Si es Cloze, usa estrictamente '{{c1::palabra}}'. En 'explanation', incluye '⚠️ Trampa frecuente / Error común:'.\n"
                    f"5. CANTIDAD OBJETIVO OBLIGATORIA DE ESTE MICRO-LOTE: Genera EXACTAMENTE {exact_target_count} tarjetas atómicas. "
                    "Si el concepto incluye un 'Blueprint Atómico Obligatorio', genera exactamente 1 tarjeta por cada micro-objetivo enumerado en el Blueprint.\n"
                    "6. Responde EXCLUSIVAMENTE en JSON con la clave 'cards': "
                    "[{'archetype': str, 'front': str, 'back': str, 'tags': [str], 'explanation': str}]."
                )
                prereq_user = (
                    "## PRERREQUISITOS Y CIMIENTOS COGNITIVOS APROBADOS:\n"
                    + "\n".join(batch_lines)
                    + f"\n\nGenera EXACTAMENTE {exact_target_count} tarjetas atómicas en idioma '{options.language}'."
                )
                try:
                    batch_cards = await self._call_ollama_json(
                        model_to_use=model_to_use,
                        system_prompt=prereq_sys,
                        user_prompt=prereq_user,
                        options=options,
                        required_tags=["prerrequisito", "fundamentos"],
                    )
                    all_cards.extend(batch_cards)
                except Exception as err:
                    logger.warning("Ollama prerequisite micro-batch failed: %s", err)

        # 2. Theme chunks (at most 2 themes per chunk, max 5 cards per chunk)
        if options.selected_themes and len(options.selected_themes) > 0:
            theme_chunks = [
                options.selected_themes[i : i + 2]
                for i in range(0, len(options.selected_themes), 2)
            ]
            for chunk in theme_chunks:
                raw_chunk_count = 0
                for t_str in chunk:
                    m = re.search(r"~?(\d+)\s*tarjetas?", t_str, re.IGNORECASE)
                    raw_chunk_count += int(m.group(1)) if m else 2
                chunk_target = max(1, min(5, raw_chunk_count))
                themes_str = "\n".join(f"- {t}" for t in chunk)

                theme_sys = (
                    "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva (Wozniak, FSRS).\n"
                    "Genera tarjetas de Anki atómicas enfocadas EXCLUSIVAMENTE en los ejes temáticos de este micro-lote.\n"
                    "REGLAS COGNITIVAS:\n"
                    "1. Anclaje jerárquico obligatorio en 'front': '[Tema > Subtema] Pregunta o Cloze'.\n"
                    "2. Principio de Información Mínima: 1 solo hecho por tarjeta, dorso < 15 palabras.\n"
                    "3. Si es Cloze, usa estrictamente '{{c1::palabra}}'. En 'explanation', incluye '⚠️ Trampa frecuente / Error común:'.\n"
                    f"4. CANTIDAD DE TARJETAS: Debes generar EXACTAMENTE {chunk_target} tarjetas atómicas para este micro-lote.\n"
                    "5. Responde EXCLUSIVAMENTE en JSON con la clave 'cards': "
                    "[{'archetype': str, 'front': str, 'back': str, 'tags': [str], 'explanation': str}]."
                )
                theme_user = (
                    f"Contenido educativo a procesar:\n\n{text}\n\n"
                    f"## EJES TEMÁTICOS PRIORIZADOS DE ESTE MICRO-LOTE:\n{themes_str}\n\n"
                    f"Genera EXACTAMENTE {chunk_target} tarjetas atómicas en idioma '{options.language}'."
                )
                try:
                    chunk_cards = await self._call_ollama_json(
                        model_to_use=model_to_use,
                        system_prompt=theme_sys,
                        user_prompt=theme_user,
                        options=options,
                    )
                    all_cards.extend(chunk_cards)
                except Exception as err:
                    logger.warning("Ollama theme micro-batch failed: %s", err)
        elif options.target_count > 6:
            remaining = max(1, options.target_count - prereq_cards_planned)
            chunk_idx = 0
            while remaining > 0:
                batch_n = min(5, remaining)
                remaining -= batch_n
                chunk_idx += 1
                focus_sys = (
                    "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva (Wozniak, FSRS).\n"
                    f"Genera el micro-lote #{chunk_idx} con EXACTAMENTE {batch_n} tarjetas atómicas de alta retención.\n"
                    "REGLAS COGNITIVAS:\n"
                    "1. Anclaje jerárquico obligatorio en 'front': '[Tema > Subtema] Pregunta o Cloze'.\n"
                    "2. Principio de Información Mínima: 1 solo hecho por tarjeta, dorso < 15 palabras.\n"
                    "3. Si es Cloze, usa estrictamente '{{c1::palabra}}'. En 'explanation', incluye '⚠️ Trampa frecuente / Error común:'.\n"
                    "4. Responde EXCLUSIVAMENTE en JSON con la clave 'cards': "
                    "[{'archetype': str, 'front': str, 'back': str, 'tags': [str], 'explanation': str}]."
                )
                focus_user = (
                    f"Contenido educativo a procesar (Micro-lote #{chunk_idx}):\n\n{text}\n\n"
                    f"Debes generar EXACTAMENTE {batch_n} tarjetas atómicas en idioma '{options.language}'."
                )
                try:
                    batch_cards = await self._call_ollama_json(
                        model_to_use=model_to_use,
                        system_prompt=focus_sys,
                        user_prompt=focus_user,
                        options=options,
                    )
                    all_cards.extend(batch_cards)
                except Exception as err:
                    logger.warning("Ollama split micro-batch #%d failed: %s", chunk_idx, err)

        # 3. Deduplicate combined cards by front.strip() and fallback if 0 cards produced
        unique_cards: List[Flashcard] = []
        seen_fronts = set()
        for card in all_cards:
            clean_front = card.front.strip()
            if clean_front and clean_front not in seen_fronts:
                seen_fronts.add(clean_front)
                unique_cards.append(card)

        if not unique_cards:
            logger.warning("Partitioned Ollama calls produced 0 cards. Falling back to single-batch.")
            return await self._generate_single_batch_from_text(text, options)

        return unique_cards

    async def generate_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> List[Flashcard]:
        """Local multimodal card generation supporting PDFs and images."""
        if mime_type == "application/pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                raise RuntimeError(f"Error al extraer texto del PDF en modo local: {e}")
            combined_text = f"{text or ''}\n\n[Contenido extraído del PDF]:\n{extracted_text}".strip()
            return await self.generate_from_text(combined_text, options)

        model_to_use = options.local_model or self.model
        is_vision = any(k in model_to_use.lower() for k in ["vl", "vision", "llava", "minicpm", "pixtral"])
        if not is_vision:
            raise ValueError(
                f"El modelo local '{model_to_use}' es de texto puro y no soporta imágenes. "
                f"Para procesar imágenes localmente, seleccioná un modelo multimodal como 'qwen2.5vl:7b' o utilizá Gemini Cloud."
            )

        count_desc = (
            f"Debes generar EXACTAMENTE {options.target_count} tarjetas atómicas en total (cubriendo tanto los prerrequisitos como los temas principales)."
            if options.target_count > 0
            else "Evalúa la densidad conceptual del documento/imagen y genera la cantidad exacta de tarjetas atómicas necesarias sin redundancia."
        )

        prerequisites_prompt = ""
        if options.prerequisites_context and options.prerequisites_context.strip():
            prerequisites_prompt = (
                f"\n\n## PRERREQUISITOS Y CIMIENTOS COGNITIVOS APROBADOS:\n"
                f"{options.prerequisites_context}\n"
                f"- REGLA OBLIGATORIA: Genera tarjetas atómicas para estos conceptos fundacionales. "
                f"Toda tarjeta de prerrequisito DEBE comenzar en 'front' con la ruta '[Fundamentos > Concepto]' "
                f"y contener en 'tags' la etiqueta 'prerrequisito'."
            )

        themes_prompt = ""
        if options.selected_themes and len(options.selected_themes) > 0:
            themes_list = "\n".join(f"- {t}" for t in options.selected_themes)
            themes_prompt = (
                f"\n\n## EJES TEMÁTICOS PRIORIZADOS:\n"
                f"Distribuye las tarjetas principales cubriendo estos ejes temáticos:\n{themes_list}"
            )

        custom_prompt = ""
        if options.custom_instructions and options.custom_instructions.strip():
            custom_prompt = f"\n\nInstrucciones adicionales del estudiante:\n{options.custom_instructions.strip()}"

        system_prompt = (
            "Eres un Arquitecto de Aprendizaje experto en neurociencia cognitiva (Wozniak, FSRS).\n"
            "Tu tarea es analizar la imagen/diagrama y generar tarjetas de Anki atómicas de alta retención.\n"
            "REGLAS COGNITIVAS:\n"
            "1. Anclaje jerárquico obligatorio en 'front': '[Tema > Subtema] Pregunta o Cloze'.\n"
            "   - Para prerrequisitos fundacionales, usa siempre: '[Fundamentos > NombreConcepto] Pregunta o Cloze'.\n"
            "2. Principio de Información Mínima: 1 solo hecho o relación lógica por tarjeta. Respuestas concisas (< 15 palabras).\n"
            "3. Si es Cloze, DEBE usar estrictamente '{{c1::palabra}}'. NUNCA '{{palabra}}' sin 'c1::'.\n"
            "4. En 'explanation', incluir '⚠️ Trampa frecuente / Error común:'.\n"
            f"5. CANTIDAD DE TARJETAS: {count_desc}\n"
            "6. Responder EXCLUSIVAMENTE con un JSON con la clave 'cards' que contenga una lista de objetos: "
            "[{'archetype': str, 'front': str, 'back': str, 'tags': [str], 'explanation': str}]."
        )
        user_prompt = f"Analiza la imagen educativa adjunta y genera las tarjetas en idioma '{options.language}'. {count_desc}"
        if themes_prompt:
            user_prompt += themes_prompt
        if prerequisites_prompt:
            user_prompt += prerequisites_prompt
        if text and text.strip():
            user_prompt += f"\n\nTexto complementario del estudiante:\n{text.strip()}"
        if custom_prompt:
            user_prompt += custom_prompt

        b64_img = base64.b64encode(file_bytes).decode("utf-8")
        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt, "images": [b64_img]},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": 8192,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama vision error {res.status_code}: {res.text}")

            data = res.json()
            raw_content = data.get("message", {}).get("content", "{}")
            parsed = json.loads(raw_content)
            cards_list = parsed.get("cards", [])

            flashcards: List[Flashcard] = []
            for c in cards_list:
                front = c.get("front", "").strip()
                card_type = options.card_type
                if "{{c" in front or "cloze" in c.get("archetype", "").lower():
                    card_type = CardType.CLOZE

                card = Flashcard(
                    id=str(uuid4()),
                    card_type=card_type,
                    archetype=c.get("archetype", "Arquetipo C: Pregunta Atómica"),
                    front=front,
                    back=c.get("back", "").strip(),
                    tags=c.get("tags", [options.deck_name.lower()]),
                    explanation=c.get("explanation"),
                )
                flashcards.append(ClozeSanitizer.sanitize_card(card))

            return flashcards

    async def inspect_material(
        self,
        text: str,
        options: GenerationOptions,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> StudyPlanInspection:
        """Analyze material locally for self-sufficiency and prerequisite gaps."""
        system_prompt = (
            "Eres un diagnosticador pedagógico experto. Analiza el material educativo y responde en formato JSON "
            "con la siguiente estructura: "
            "{'topic_name': str, 'self_sufficiency_score': int, 'self_sufficiency_verdict': str, "
            "'core_themes': [{'id': str, 'title': str, 'description': str, 'recommended_cards': int}], "
            "'prerequisites': [{'id': str, 'concept': str, 'reason': str, 'is_covered_in_text': bool, 'search_query': str, 'recommended_deep_cards': 3}], "
            "'suggested_total_cards': int}. "
            "Para cada prerrequisito, calcula 'recommended_deep_cards' (entero entre 2 y 6) según el Principio de Información Mínima."
        )

        model_to_use = options.local_model or self.model
        user_msg: Dict[str, Any] = {"role": "user", "content": text}
        if media_parts and len(media_parts) > 0:
            user_msg["images"] = [base64.b64encode(b).decode("utf-8") for b, _ in media_parts]

        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": system_prompt},
                user_msg,
            ],
            "format": "json",
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama inspection failed: {res.text}")

            data = res.json()
            raw = json.loads(data.get("message", {}).get("content", "{}"))

            themes = [
                CoreTheme(
                    id=t.get("id", str(uuid4())),
                    title=t.get("title", ""),
                    description=t.get("description", ""),
                    recommended_cards=t.get("recommended_cards", 2),
                    selected=True,
                )
                for t in raw.get("core_themes", [])
            ]

            prereqs = [
                PrerequisiteItem(
                    id=p.get("id", str(uuid4())),
                    concept=p.get("concept", ""),
                    reason=p.get("reason", ""),
                    is_covered_in_text=p.get("is_covered_in_text", False),
                    search_query=p.get("search_query", ""),
                    selected=not p.get("is_covered_in_text", False),
                    mode="anchor",
                    deep_card_count=0,
                    recommended_deep_cards=max(
                        2, min(8, int(p.get("recommended_deep_cards", 3) or 3))
                    ),
                )
                for p in raw.get("prerequisites", [])
            ]

            return StudyPlanInspection(
                topic_name=raw.get("topic_name", "Tema Principal"),
                self_sufficiency_score=raw.get("self_sufficiency_score", 70),
                self_sufficiency_verdict=raw.get("self_sufficiency_verdict", ""),
                core_themes=themes,
                prerequisites=prereqs,
                suggested_total_cards=raw.get("suggested_total_cards", len(themes) * 2),
            )

    async def inspect_material_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> StudyPlanInspection:
        """Analyze material locally from PDF or image for self-sufficiency and gaps."""
        if mime_type == "application/pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as e:
                raise RuntimeError(f"Error al extraer texto del PDF en modo local: {e}")
            combined_text = f"{text or ''}\n\n[Contenido extraído del PDF]:\n{extracted_text}".strip()
            return await self.inspect_material(combined_text, options)

        model_to_use = options.local_model or self.model
        is_vision = any(k in model_to_use.lower() for k in ["vl", "vision", "llava", "minicpm", "pixtral"])
        if not is_vision:
            raise ValueError(
                f"El modelo local '{model_to_use}' es de texto puro y no soporta imágenes. "
                f"Para procesar imágenes localmente, seleccioná un modelo multimodal como 'qwen2.5vl:7b' o utilizá Gemini Cloud."
            )

        system_prompt = (
            "Eres un diagnosticador pedagógico experto. Analiza la imagen o diagrama educativo y responde en formato JSON "
            "con la siguiente estructura: "
            "{'topic_name': str, 'self_sufficiency_score': int, 'self_sufficiency_verdict': str, "
            "'core_themes': [{'id': str, 'title': str, 'description': str, 'recommended_cards': int}], "
            "'prerequisites': [{'id': str, 'concept': str, 'reason': str, 'is_covered_in_text': bool, 'search_query': str, 'recommended_deep_cards': 3}], "
            "'suggested_total_cards': int}"
        )
        user_prompt = "Diagnostica pedagógicamente la siguiente imagen o diagrama."
        if text and text.strip():
            user_prompt += f"\n\nTexto complementario del estudiante:\n{text.strip()}"

        b64_img = base64.b64encode(file_bytes).decode("utf-8")
        payload = {
            "model": model_to_use,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt, "images": [b64_img]},
            ],
            "format": "json",
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama inspection failed: {res.text}")

            data = res.json()
            raw = json.loads(data.get("message", {}).get("content", "{}"))

            themes = [
                CoreTheme(
                    id=t.get("id", str(uuid4())),
                    title=t.get("title", ""),
                    description=t.get("description", ""),
                    recommended_cards=t.get("recommended_cards", 2),
                    selected=True,
                )
                for t in raw.get("core_themes", [])
            ]

            prereqs = [
                PrerequisiteItem(
                    id=p.get("id", str(uuid4())),
                    concept=p.get("concept", ""),
                    reason=p.get("reason", ""),
                    is_covered_in_text=p.get("is_covered_in_text", False),
                    search_query=p.get("search_query", ""),
                    selected=not p.get("is_covered_in_text", False),
                    mode="anchor",
                    deep_card_count=0,
                    recommended_deep_cards=max(
                        2, min(8, int(p.get("recommended_deep_cards", 3) or 3))
                    ),
                )
                for p in raw.get("prerequisites", [])
            ]

            return StudyPlanInspection(
                topic_name=raw.get("topic_name", "Tema Principal"),
                self_sufficiency_score=raw.get("self_sufficiency_score", 70),
                self_sufficiency_verdict=raw.get("self_sufficiency_verdict", ""),
                core_themes=themes,
                prerequisites=prereqs,
                suggested_total_cards=raw.get("suggested_total_cards", len(themes) * 2),
            )

    async def enrich_prerequisite(
        self, concept: str, search_query: str, context_topic: Optional[str] = None
    ) -> EnrichedConceptResult:
        """Synthesize foundational prerequisite knowledge and atomic blueprint using local model."""
        system_prompt = (
            "Eres un Arquitecto Cognitivo experto en aprendizaje significativo (Ausubel) y Principio de Información Mínima (Wozniak). "
            "Tu tarea es descomponer el concepto fundacional en entre 3 y 5 micro-objetivos técnicos concretos e irreductibles ('atomic_blueprint') "
            "para que un generador cree exactamente 1 flashcard por cada micro-objetivo. "
            "PROHIBIDO copiar textos genéricos o usar corchetes: cada ítem de 'atomic_blueprint' debe mencionar los mecanismos, componentes o reglas reales del concepto investigado."
        )
        prompt = (
            f"Investiga y desglosa el concepto fundacional: '{concept}' (Contexto: {context_topic or 'General'} | Búsqueda: {search_query}).\n"
            f"Responde estrictamente en JSON con estos 4 campos:\n"
            f"- 'atomic_blueprint': array de 3 a 5 strings. Cada string debe ser una pregunta o micro-objetivo técnico específico sobre '{concept}' "
            f"(ej. 1. Propósito arquitectónico específico, 2. Cómo opera su mecanismo técnico o herencia, 3. Regla crítica o error común en producción).\n"
            f"- 'recommended_deep_cards': número entero exactamente igual a la cantidad de elementos en 'atomic_blueprint'.\n"
            f"- 'summary': explicación pedagógica de 2 párrafos sobre cómo funciona '{concept}'.\n"
            f"- 'key_takeaway': 1 sola oración con la regla mental más importante."
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "format": "json",
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/api/chat", json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Ollama prerequisite enrichment failed: {res.text}")

            data = res.json()
            raw = json.loads(data.get("message", {}).get("content", "{}"))
            raw_blueprint = [str(item).strip() for item in raw.get("atomic_blueprint", []) if item and str(item).strip()]
            if not raw_blueprint:
                raw_blueprint = [
                    f"1. Definición funcional y problema técnico que resuelve {concept}",
                    f"2. Mecanismo causal interno y reglas de operación de {concept}",
                    f"3. Diferenciación crítica y error frecuente al configurar {concept}",
                ]
            rec_deep = max(2, min(8, len(raw_blueprint)))
            return EnrichedConceptResult(
                concept=concept,
                summary=raw.get("summary", ""),
                key_takeaway=raw.get("key_takeaway", ""),
                recommended_deep_cards=rec_deep,
                atomic_blueprint=raw_blueprint,
            )
