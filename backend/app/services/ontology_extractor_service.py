import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx
from google import genai
from google.genai import types

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.core.config import settings
from app.domain.models import (
    DeckConceptDAG,
    ExtractOntologyBatchResponse,
    ExtractedNoteKnowledge,
)
from app.services.deck_dag_service import DeckDAGService

logger = logging.getLogger(__name__)


def _strip_html(text: str) -> str:
    """Strip HTML tags and unescape common entities."""
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


class OntologyExtractorService:
    """Service to perform bottom-up semantic micro-extraction of atomic facts and concepts from Anki notes."""

    def __init__(
        self,
        store: DeckKnowledgeStore,
        dag_service: DeckDAGService,
        gemini_api_key: Optional[str] = None,
        nvidia_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
    ):
        self._store = store
        self._dag_service = dag_service
        self._gemini_api_key = gemini_api_key or settings.GEMINI_API_KEY
        self._nvidia_api_key = nvidia_api_key or settings.NVIDIA_API_KEY
        self._groq_api_key = groq_api_key or settings.GROQ_API_KEY

    def _build_system_instruction(self) -> str:
        return (
            "Eres un Parser Ontológico y Arquitecto de Conocimiento experto en grafos de aprendizaje (DAG).\n"
            "Tu misión es analizar una tarjeta educativa y descomponerla en:\n"
            "1. 'extracted_facts': Lista de hechos o proposiciones atómicas expresadas en la tarjeta (máximo 15 palabras cada una).\n"
            "2. 'target_concepts': Lista de 1 a 3 conceptos centrales o entidades que esta tarjeta define, explica o evalúa.\n"
            "3. 'assumed_prerequisites': Lista de conceptos o fundamentos previos que el estudiante DEBE dominar antes para comprender esta tarjeta.\n"
            "4. 'taxonomy_path': Ruta taxonómica jerárquica con separador '::' (ej. 'redes::enrutamiento::tablas').\n\n"
            "IMPORTANTE: Devuelve EXCLUSIVAMENTE un objeto JSON válido con estas 4 claves. Sin markdown, sin explicaciones adicionales."
        )

    def _build_user_prompt(self, note: Dict[str, Any], known_concepts: Optional[List[str]] = None) -> str:
        front = _strip_html(note.get("front", ""))
        back = _strip_html(note.get("back", ""))
        tags = note.get("tags") or []
        tag_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        
        known_section = ""
        if known_concepts:
            canonical_sample = ", ".join(f"'{c}'" for c in known_concepts[:40])
            known_section = (
                f"\nVOCABULARIO CANÓNICO EXISTENTE EN EL GRAFO: [{canonical_sample}]\n"
                "REGLA DE CONVERGENCIA ONTOLÓGICA: Si los conceptos o prerrequisitos de esta tarjeta corresponden "
                "semánticamente a conceptos ya presentes en la lista anterior, REUTILIZA EXACTAMENTE su nombre "
                "para evitar duplicar nodos sinónimos (ej. si ya existe 'OCI VCN', no inventes 'VCN' por separado).\n"
            )

        return (
            f"ID de Nota: {note.get('note_id', 0)}\n"
            f"Etiquetas: {tag_str}\n"
            f"Anverso (Pregunta/Frente): {front}\n"
            f"Reverso (Respuesta/Dato): {back}\n"
            f"{known_section}\n"
            "Extrae la tupla ontológica en JSON estricto."
        )

    async def _extract_with_gemini(self, prompt: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        key = api_key or self._gemini_api_key
        if not key:
            return None

        client = genai.Client(api_key=key)
        for model_name in ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-1.5-flash"]:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=self._build_system_instruction(),
                        temperature=0.1,
                        response_mime_type="application/json",
                    ),
                )
                if response and response.text:
                    clean = response.text.strip()
                    clean = re.sub(r"^```json\s*", "", clean)
                    clean = re.sub(r"\s*```$", "", clean)
                    return json.loads(clean)
            except Exception as e:
                logger.debug("Gemini extraction tier '%s' failed: %s", model_name, e)
                continue
        return None

    async def _extract_with_groq(self, prompt: str, api_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        key = api_key or self._groq_api_key
        if not key:
            return None

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": self._build_system_instruction()},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
        return None

    def _fallback_heuristic_extraction(self, note: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic fallback parser if all LLM endpoints fail."""
        front = _strip_html(note.get("front", ""))
        back = _strip_html(note.get("back", ""))
        tags = note.get("tags") or []

        # Simple keyword-based heuristics
        words = [w for w in re.findall(r"\b[A-Za-z0-9_-]{4,}\b", front) if w.lower() not in {"que", "como", "cual", "donde", "para", "anki"}]
        main_concept = words[0] if words else "concepto_general"

        tax = "general"
        if tags and isinstance(tags, list):
            tax = "::".join(tags[:2])

        return {
            "extracted_facts": [f"{front}: {back[:100]}"] if front and back else ["Hecho educativo básico"],
            "target_concepts": [main_concept],
            "assumed_prerequisites": [],
            "taxonomy_path": tax,
        }

    async def extract_note_knowledge(
        self,
        note: Dict[str, Any],
        ai_provider: Optional[str] = None,
        api_key: Optional[str] = None,
        known_concepts: Optional[List[str]] = None,
    ) -> ExtractedNoteKnowledge:
        """Extract ontological knowledge from an individual note with multi-provider cascade."""
        nid = note.get("note_id") or 0
        prompt = self._build_user_prompt(note, known_concepts=known_concepts)
        provider = (ai_provider or "gemini").lower()

        data: Optional[Dict[str, Any]] = None

        if provider == "groq" or (not data and self._groq_api_key):
            try:
                data = await self._extract_with_groq(prompt, api_key=api_key)
            except Exception as e:
                logger.debug("Groq extraction failed for note %d: %s", nid, e)

        if not data and (provider == "gemini" or self._gemini_api_key or api_key):
            try:
                data = await self._extract_with_gemini(prompt, api_key=api_key)
            except Exception as e:
                logger.debug("Gemini extraction failed for note %d: %s", nid, e)

        if not data:
            logger.warning("All LLM providers failed for note %d; applying fallback heuristic extraction.", nid)
            data = self._fallback_heuristic_extraction(note)

        return ExtractedNoteKnowledge(
            source_note_id=nid,
            raw_front=note.get("front", ""),
            raw_back=note.get("back", ""),
            extracted_facts=data.get("extracted_facts") or [],
            target_concepts=data.get("target_concepts") or [],
            assumed_prerequisites=data.get("assumed_prerequisites") or [],
            taxonomy_path=data.get("taxonomy_path") or "general",
        )

    async def extract_deck_batch(
        self,
        deck_name: str,
        notes: List[Dict[str, Any]],
        batch_size: int = 5,
        ai_provider: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> ExtractOntologyBatchResponse:
        """Process a batch of deck notes, extract their ontology, and update the DAG in SQLite."""
        selected_notes = notes[:batch_size]
        remaining_count = max(0, len(notes) - len(selected_notes))

        # Retrieve known concepts in deck to inject as canonical vocabulary (G-07)
        existing_nodes = self._store.get_deck_concepts(deck_name)
        known_concepts = [c["name"] for c in existing_nodes if c.get("name")]

        # Process notes sequentially or with bounded concurrency (2 concurrent calls) to respect rate limits
        semaphore = asyncio.Semaphore(2)

        async def _process_one(n: Dict[str, Any]) -> ExtractedNoteKnowledge:
            async with semaphore:
                return await self.extract_note_knowledge(
                    n,
                    ai_provider=ai_provider,
                    api_key=api_key,
                    known_concepts=known_concepts,
                )

        tasks = [_process_one(n) for n in selected_notes]
        extractions = await asyncio.gather(*tasks)

        # Ingest extractions into SQLite and recompute DAG
        updated_dag = self._dag_service.ingest_note_extractions(deck_name, extractions)

        return ExtractOntologyBatchResponse(
            deck_name=deck_name,
            processed_notes_count=len(extractions),
            remaining_unextracted_count=remaining_count,
            extracted_knowledge=extractions,
            dag_summary=updated_dag,
        )
