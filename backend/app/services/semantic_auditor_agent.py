import asyncio
import base64
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from google import genai
from google.genai import types

from app.core.config import settings
from app.ports.anki_bridge_port import IAnkiBridgePort
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """Strip HTML tags and unescape common entities for clean text comparison."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = (
        cleaned.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    return " ".join(cleaned.split()).strip()


class SemanticAuditorAgent:
    """
    Agente Auditor Semántico de Calidad.
    Audits flashcards against neurocognitive learning laws:
    - Minimum Information Principle (Piotr Wozniak)
    - Inequivocality & Anchoring (David Ausubel)
    - Hypercorrection & Diagnostic Feedback (Janet Metcalfe)
    - Anti-Slide Dump (Text-in-Image detection)
    Supports multimodal evaluation via AnkiConnect collection.media across
    Ollama, NVIDIA NIM, Groq, and Gemini, with robust heuristic fallback.
    """

    def __init__(
        self,
        anki_bridge: IAnkiBridgePort,
        store: DeckKnowledgeStore,
    ):
        self._anki_bridge = anki_bridge
        self._store = store

    def _build_system_instruction(self) -> str:
        return (
            "Eres un Auditor Senior de Calidad Neurocognitiva para Sistemas de Repetición Espaciada (Anki).\n"
            "Tu misión es auditar tarjetas según el Principio de Información Mínima de Piotr Wozniak, "
            "la Inequivocidad Ausubeliana y el Protocolo de Hipercorrección de Janet Metcalfe.\n"
            "NUNCA seas complaciente. Si una tarjeta es enciclopédica, ambigua, un volcado de diapositiva (slide dump), ilegible o sin atomicidad, "
            "DEBES clasificarla como 'bad'."
        )

    def _build_user_prompt(
        self,
        clean_front: str,
        clean_back: str,
        clean_exp: str,
        images_count: int,
    ) -> str:
        return f"""Audita la siguiente tarjeta de estudio:

- ANVERSO: "{clean_front}"
- REVERSO (Texto): "{clean_back}"
- EXPLICACIÓN/EXTRA: "{clean_exp}"
- IMÁGENES ADJUNTAS: {"Sí (" + str(images_count) + " imagen/es adjunta/s)" if images_count > 0 else "No"}

RÚBRICA DE EVALUACIÓN COGNITIVA CON COMPUERTAS DURAS (HARD GATES):
1. COMPUERTA DE ATOMICIDAD (Principio de Información Mínima de Wozniak):
   - ¿El reverso contiene más de 1 hecho atómico? (Ej: una tabla comparativa entera, múltiples conceptos o más de 20 palabras de texto denso que demanden >5s de repaso).
   - Si la respuesta es SÍ: VIOLACIÓN DIRECTA -> Clasificar como 'bad'.
2. COMPUERTA DE VOLCADO DE DIAPOSITIVA (Slide Dump / Text-in-Image):
   - Si el reverso consiste en una captura de pantalla que contiene tablas, listas densas o múltiples diapositivas en vez de un diagrama visual enfocado: VIOLACIÓN DIRECTA -> Clasificar como 'bad'.
3. COMPUERTA DE INEQUIVOCIDAD (Ausubel):
   - Si el anverso es una pregunta genérica ("¿Qué es X?") ante un reverso complejo y multifacético sin delimitar qué faceta específica se debe evocar: Clasificar como 'bad'.
4. COMPUERTA DE CORRUPCIÓN / ILEGIBILIDAD:
   - Si el anverso está vacío, la pregunta es incomprensible, o la imagen es ilegible: Clasificar como 'bad'.
5. ESTADO ÓPTIMO ('optimal'):
   - Únicamente si el anverso es unívoco, el reverso es atómico (<15-20 palabras o diagrama simple) y evalúa una sola relación conceptual directa.

Responde ESTRICTAMENTE en formato JSON con la siguiente estructura:
{{
  "quality_status": "optimal" | "bad",
  "quality_score": 0.0 a 1.0,
  "violation_type": "ATOMICITY_MONOLITH" | "SLIDE_DUMP" | "AMBIGUOUS_QUESTION" | "MISSING_TRAP" | "NONE",
  "quality_feedback": "Diagnóstico pedagógico conciso de 1 a 2 oraciones en español explicando el problema o virtud cognitiva.",
  "atomic_sister_cards_recommended": [
    "Pregunta de tarjeta hermana 1 sugerida si es bad",
    "Pregunta de tarjeta hermana 2 sugerida si es bad"
  ]
}}"""

    async def _audit_with_ollama(
        self,
        system_instruction: str,
        user_prompt: str,
        images_b64: List[str],
        local_model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ollama_model = local_model or ("qwen2.5vl:7b" if images_b64 else "qwen2.5:14b")
        payload = {
            "model": ollama_model,
            "system": system_instruction,
            "prompt": user_prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 350},
        }
        if images_b64:
            payload["images"] = images_b64
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post("http://127.0.0.1:11434/api/generate", json=payload)
            if resp.status_code == 200:
                raw_json = resp.json().get("response", "{}")
                return json.loads(raw_json)
        return None

    async def _audit_with_nvidia(
        self,
        system_instruction: str,
        user_prompt: str,
        images_b64: List[str],
        api_key: str,
    ) -> Optional[Dict[str, Any]]:
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        user_content: Any = user_prompt
        if images_b64:
            user_content = [{"type": "text", "text": user_prompt}]
            for b64 in images_b64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })

        model = "meta/llama-3.2-11b-vision-instruct" if images_b64 else "meta/llama-3.3-70b-instruct"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
                return json.loads(content)
        return None

    async def _audit_with_groq(
        self,
        system_instruction: str,
        user_prompt: str,
        images_b64: List[str],
        api_key: str,
    ) -> Optional[Dict[str, Any]]:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        user_content: Any = user_prompt
        if images_b64:
            user_content = [{"type": "text", "text": user_prompt}]
            for b64 in images_b64:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
            model = "llama-3.2-11b-vision-preview"
        else:
            model = "llama-3.3-70b-versatile"

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "{}")
                return json.loads(content)
        return None

    async def _audit_with_gemini(
        self,
        system_instruction: str,
        user_prompt: str,
        images_b64: List[str],
        api_key: str,
    ) -> Optional[Dict[str, Any]]:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30000),
        )
        content_parts: List[Any] = []
        for b64 in images_b64:
            img_bytes = base64.b64decode(b64)
            content_parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
        content_parts.append(user_prompt)

        tier_models = list(
            dict.fromkeys(
                [
                    settings.GEMINI_MODEL,
                    settings.GEMINI_FALLBACK_MODEL,
                    "gemini-3.8-flash",
                    "gemini-3.7-flash",
                    "gemini-3.6-flash",
                ]
                + getattr(settings, "GEMINI_TIER_MODELS", [])
            )
        )

        for m_name in tier_models:
            try:
                res = await asyncio.to_thread(
                    client.models.generate_content,
                    model=m_name,
                    contents=content_parts,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        response_mime_type="application/json",
                        temperature=0.1,
                    ),
                )
                text = res.text or "{}"
                text = re.sub(r"^```(?:json)?\s*", "", text.strip())
                text = re.sub(r"\s*```$", "", text.strip())
                return json.loads(text)
            except Exception as tier_err:
                logger.debug("Gemini tier '%s' failed during quality audit: %s", m_name, tier_err)
                continue
        return None

    def _fallback_heuristic(
        self,
        clean_f: str,
        clean_b: str,
        images_b64: List[str],
    ) -> Dict[str, Any]:
        has_multiple_imgs = len(images_b64) > 1
        b_word_count = len(clean_b.split())

        if has_multiple_imgs or b_word_count > 25:
            v_type = "SLIDE_DUMP" if has_multiple_imgs else "ATOMICITY_MONOLITH"
            q_score = 0.3 if has_multiple_imgs else round(max(0.1, 1.0 - (b_word_count / 50)), 2)
            fb = (
                "El reverso contiene múltiples imágenes/diapositivas en una sola tarjeta, violando la atomicidad."
                if has_multiple_imgs
                else f"El reverso excede las 20 palabras atómicas ({b_word_count} palabras). Se recomienda dividir en tarjetas hermanas."
            )
            return {
                "quality_status": "bad",
                "quality_score": q_score,
                "violation_type": v_type,
                "quality_feedback": fb,
                "atomic_sister_cards_recommended": [f"¿Aspecto clave de: {clean_f[:50]}...?"],
            }

        if len(clean_f) < 4:
            return {
                "quality_status": "bad",
                "quality_score": 0.2,
                "violation_type": "AMBIGUOUS_QUESTION",
                "quality_feedback": "El anverso está vacío o es incomprensible.",
                "atomic_sister_cards_recommended": [],
            }

        return {
            "quality_status": "optimal",
            "quality_score": 0.95,
            "violation_type": "NONE",
            "quality_feedback": "Tarjeta atómica y unívoca según las leyes cognitivas.",
            "atomic_sister_cards_recommended": [],
        }

    async def audit_note(
        self,
        note: Dict[str, Any],
        deck_name: str,
        ai_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        local_model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audit a single note and update its evaluation in the persistent SQLite store."""
        nid = note.get("note_id") or 0
        front = note.get("front", "") or ""
        back = note.get("back", "") or ""
        explanation = note.get("explanation", "") or ""

        # Extract embedded images and fetch base64 data
        all_text = f"{front} {back} {explanation}"
        img_filenames = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', all_text)

        images_b64: List[str] = []
        if self._anki_bridge and img_filenames:
            for img_fn in img_filenames[:3]:
                try:
                    b64 = await self._anki_bridge.retrieve_media_base64(img_fn)
                    if b64:
                        images_b64.append(b64)
                except Exception as e:
                    logger.warning("Could not retrieve media '%s' for note %d: %s", img_fn, nid, e)

        clean_f = _strip_html(front)
        clean_b = _strip_html(back)
        clean_exp = _strip_html(explanation)

        system_instruction = self._build_system_instruction()
        user_prompt = self._build_user_prompt(clean_f, clean_b, clean_exp, len(images_b64))

        provider = (ai_provider or "gemini").lower()
        verdict: Optional[Dict[str, Any]] = None

        # 1. Local Ollama
        if provider in ("ollama", "local"):
            try:
                verdict = await self._audit_with_ollama(
                    system_instruction, user_prompt, images_b64, local_model=local_model
                )
            except Exception as e:
                logger.warning("Ollama audit failed for note %d: %s", nid, e)

        # 2. NVIDIA NIM
        nvidia_key = api_key if provider == "nvidia" else (settings.NVIDIA_API_KEY or (api_key if provider == "nvidia" else None))
        if not verdict and (provider == "nvidia" or settings.NVIDIA_API_KEY):
            if nvidia_key:
                try:
                    verdict = await self._audit_with_nvidia(system_instruction, user_prompt, images_b64, nvidia_key)
                except Exception as e:
                    logger.warning("NVIDIA audit failed for note %d: %s", nid, e)

        # 3. Groq API
        groq_key = api_key if provider == "groq" else (settings.GROQ_API_KEY or (api_key if provider == "groq" else None))
        if not verdict and (provider == "groq" or settings.GROQ_API_KEY):
            if groq_key:
                try:
                    verdict = await self._audit_with_groq(system_instruction, user_prompt, images_b64, groq_key)
                except Exception as e:
                    logger.warning("Groq audit failed for note %d: %s", nid, e)

        # 4. Google Gemini
        gemini_key = api_key or settings.GEMINI_API_KEY
        if not verdict and gemini_key and provider not in ("heuristic", "mock"):
            try:
                verdict = await self._audit_with_gemini(system_instruction, user_prompt, images_b64, gemini_key)
            except Exception as e:
                logger.warning("Gemini audit failed for note %d: %s", nid, e)

        # 5. Heuristic fallback
        if not verdict:
            verdict = self._fallback_heuristic(clean_f, clean_b, images_b64)

        raw_status = verdict.get("quality_status", "optimal")
        status = "bad" if raw_status in ("bad", "debt", "broken") else "optimal"
        score = float(verdict.get("quality_score", 0.5))
        v_type = verdict.get("violation_type", "NONE")
        feedback = verdict.get("quality_feedback") or "Evaluada por auditor semántico."
        sister_cards = verdict.get("atomic_sister_cards_recommended", [])
        now_iso = datetime.now(timezone.utc).isoformat()

        audit_result = {
            "note_id": nid,
            "quality_status": status,
            "quality_score": score,
            "violation_type": v_type,
            "quality_feedback": feedback,
            "atomic_sister_cards_recommended": sister_cards,
            "audited_at": now_iso,
        }

        # Persist to SQLite store
        try:
            self._store.update_notes_quality_batch(deck_name, [audit_result])
        except Exception as e:
            logger.warning("Failed to persist quality update for note %d in store: %s", nid, e)

        return audit_result

    async def audit_notes_batch(
        self,
        notes: List[Dict[str, Any]],
        deck_name: str,
        ai_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        local_model: Optional[str] = None,
        concurrency: int = 5,
    ) -> List[Dict[str, Any]]:
        """Audit a batch of notes concurrently and update the database."""
        if not notes:
            return []

        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded_audit(note: Dict[str, Any]) -> Dict[str, Any]:
            async with semaphore:
                return await self.audit_note(
                    note=note,
                    deck_name=deck_name,
                    ai_provider=ai_provider,
                    api_key=api_key,
                    local_model=local_model,
                )

        results = await asyncio.gather(*(_bounded_audit(n) for n in notes), return_exceptions=False)
        return list(results)
