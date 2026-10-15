import asyncio
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional

import pypdf
from google import genai
from google.genai import types

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.core.config import settings
from app.domain.models import (
    BlueprintAlignmentSummary,
    BlueprintDomain,
    BlueprintObjective,
    ExamBlueprint,
)
from app.ports.embedding_port import IEmbeddingPort

logger = logging.getLogger(__name__)


class ExamBlueprintService:
    """Service to ingest, parse, structure, and align official syllabi / exam blueprints with an Anki deck."""

    def __init__(
        self,
        store: DeckKnowledgeStore,
        embedding_port: IEmbeddingPort,
        gemini_api_key: Optional[str] = None,
    ):
        self._store = store
        self._embedding_port = embedding_port
        self._gemini_api_key = gemini_api_key or settings.GEMINI_API_KEY

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Deterministically extract raw text from an uploaded PDF blueprint using pypdf."""
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text: List[str] = []
        for idx, page in enumerate(reader.pages):
            txt = page.extract_text() or ""
            if txt.strip():
                pages_text.append(f"--- Página {idx + 1} ---\n{txt}")
        full_text = "\n\n".join(pages_text)
        return full_text.strip()

    async def parse_blueprint(
        self,
        raw_text: Optional[str] = None,
        exam_name: Optional[str] = None,
        search_web: bool = False,
        api_key: Optional[str] = None,
    ) -> ExamBlueprint:
        """Parse raw text or search the web to extract a structured ExamBlueprint."""
        effective_key = api_key or self._gemini_api_key
        if not effective_key:
            raise ValueError("GEMINI_API_KEY es requerida para estructurar el blueprint con IA.")

        client = genai.Client(api_key=effective_key)

        system_instruction = (
            "Eres un Especialista Senior en Diseño Curricular y Certificaciones Técnicas.\n"
            "Tu misión es extraer y estructurar el temario o blueprint oficial de un examen o curso.\n"
            "Debes descomponer el temario en Dominios (módulos principales con su porcentaje de peso si existe) "
            "y Objetivos Atómicos de Aprendizaje evaluables (habilidades concretas).\n\n"
            "REGLAS:\n"
            "1. Limpia todo el ruido publicitario, logos, avisos legales, políticas de retoma o requisitos de hardware.\n"
            "2. Extrae EXCLUSIVAMENTE conceptos y competencias técnicas que se evalúan.\n"
            "3. Asigna un ID secuencial claro a cada objetivo (ej: '1.1', '1.2', '2.1') y a cada dominio ('D1', 'D2').\n"
            "4. Devuelve el resultado en formato JSON estricto."
        )

        if search_web and exam_name:
            user_prompt = (
                f"Busca en la web el temario o exam blueprint oficial más reciente para la certificación o curso: '{exam_name}'.\n"
                "Extrae todos los dominios oficiales de estudio y sus objetivos o temas evaluables específicos.\n"
                "Si encuentras los porcentajes de peso de cada dominio en el examen, inclúyelos."
            )
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.2,
                tools=[types.Tool(google_search=types.GoogleSearch())],
            )
            response = await client.aio.models.generate_content(
                model=getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
                contents=user_prompt,
                config=config,
            )
            extracted_text = response.text or ""
            # Pass extracted search text through JSON structuring pass
            return await self._structure_raw_text(client, extracted_text, exam_name=exam_name, source_type="web_search")

        if not raw_text or not raw_text.strip():
            raise ValueError("Se requiere texto del temario o activar la búsqueda web con el nombre del examen.")

        return await self._structure_raw_text(client, raw_text, exam_name=exam_name, source_type="upload_or_text")

    async def _structure_raw_text(
        self,
        client: genai.Client,
        raw_text: str,
        exam_name: Optional[str] = None,
        source_type: str = "upload_or_text",
    ) -> ExamBlueprint:
        """Structure raw syllabus text into ExamBlueprint schema via Gemini."""
        prompt = (
            f"Exam / Course Name: {exam_name or 'Temario General'}\n\n"
            f"Raw Content:\n\"\"\"\n{raw_text[:25000]}\n\"\"\"\n\n"
            "Genera el esquema JSON con:\n"
            "{\n"
            "  \"exam_name\": \"Nombre del examen\",\n"
            "  \"provider\": \"Proveedor (Oracle, AWS, Universidad, etc.)\",\n"
            "  \"domains\": [\n"
            "    {\n"
            "      \"domain_id\": \"D1\",\n"
            "      \"name\": \"Nombre del dominio temático\",\n"
            "      \"weight_pct\": 20.0,\n"
            "      \"objectives\": [\n"
            "        {\n"
            "          \"objective_id\": \"1.1\",\n"
            "          \"title\": \"Nombre atómico del objetivo\",\n"
            "          \"description\": \"Detalles o sub-habilidades\",\n"
            "          \"cognitive_level\": \"Understand\" | \"Apply\" | \"Analyze\"\n"
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )

        response = await client.aio.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=config,
        )

        try:
            data = json.loads(response.text or "{}")
        except json.JSONDecodeError as err:
            logger.error("Failed to decode JSON from Gemini blueprint parsing: %s", err)
            raise ValueError(f"Fallo al decodificar la estructura JSON del blueprint: {err}")

        parsed_domains: List[BlueprintDomain] = []
        total_objs = 0

        for d_idx, d in enumerate(data.get("domains", [])):
            d_id = d.get("domain_id") or f"D{d_idx + 1}"
            d_name = d.get("name") or f"Dominio {d_idx + 1}"
            d_weight = d.get("weight_pct")

            objectives: List[BlueprintObjective] = []
            for o_idx, o in enumerate(d.get("objectives", [])):
                total_objs += 1
                o_id = o.get("objective_id") or f"{d_idx + 1}.{o_idx + 1}"
                o_title = o.get("title") or "Objetivo sin título"
                objectives.append(
                    BlueprintObjective(
                        objective_id=o_id,
                        title=o_title,
                        description=o.get("description"),
                        cognitive_level=o.get("cognitive_level") or "Understand",
                        weight_pct=o.get("weight_pct"),
                    )
                )

            parsed_domains.append(
                BlueprintDomain(
                    domain_id=d_id,
                    name=d_name,
                    weight_pct=d_weight,
                    objectives=objectives,
                )
            )

        return ExamBlueprint(
            exam_name=data.get("exam_name") or exam_name or "Temario Oficial",
            provider=data.get("provider"),
            source_type=source_type,
            raw_snippet=raw_text[:200] if raw_text else None,
            domains=parsed_domains,
            total_objectives=total_objs,
        )

    async def align_blueprint_with_deck(
        self,
        deck_name: str,
        blueprint: ExamBlueprint,
        min_similarity_threshold: float = 0.68,
    ) -> BlueprintAlignmentSummary:
        """Cross-reference each objective against deck knowledge base, detect gaps, and register them."""
        # 1. Gather all objectives flatly for batch embedding
        flat_objectives: List[BlueprintObjective] = []
        for d in blueprint.domains:
            flat_objectives.extend(d.objectives)

        if not flat_objectives:
            return BlueprintAlignmentSummary(
                deck_name=deck_name,
                exam_name=blueprint.exam_name,
                total_objectives=0,
                covered_count=0,
                partial_count=0,
                gap_count=0,
                coverage_percentage=100,
                created_gaps_count=0,
                blueprint=blueprint,
            )

        # 2. Embed objectives
        objective_texts = [
            f"{obj.title}. {obj.description or ''}".strip()
            for obj in flat_objectives
        ]

        logger.info(
            "Embedding %d objectives from blueprint '%s' for deck '%s'...",
            len(objective_texts),
            blueprint.exam_name,
            deck_name,
        )
        if hasattr(self._embedding_port, "embed_texts"):
            embeddings = await self._embedding_port.embed_texts(objective_texts)
        elif hasattr(self._embedding_port, "get_embeddings"):
            embeddings = await self._embedding_port.get_embeddings(objective_texts)
        else:
            embeddings = [await self._embedding_port.embed_single(t) for t in objective_texts]

        # 3. Match against deck_knowledge_store
        covered_count = 0
        partial_count = 0
        gap_count = 0
        domain_gaps: Dict[str, List[Dict[str, Any]]] = {}
        domain_covered: Dict[str, List[Dict[str, Any]]] = {}

        for idx, obj in enumerate(flat_objectives):
            obj_vec = embeddings[idx] if idx < len(embeddings) else []
            matches = []
            if obj_vec:
                matches = self._store.semantic_search(
                    deck_name=deck_name,
                    query_embedding=obj_vec,
                    top_k=5,
                    min_similarity=0.55,
                )

            best_sim = matches[0]["similarity"] if matches else 0.0
            obj.similarity_score = round(best_sim, 3)

            # Find parent domain
            parent_domain = next(
                (d for d in blueprint.domains if obj in d.objectives), None
            )
            domain_name = parent_domain.name if parent_domain else "General"

            if best_sim >= 0.76:
                obj.coverage_status = "covered"
                obj.matched_note_ids = [m["note_id"] for m in matches if m["similarity"] >= 0.70]
                covered_count += 1
                domain_covered.setdefault(domain_name, []).append({
                    "facet_title": obj.title,
                    "matched_notes_count": len(obj.matched_note_ids),
                    "best_similarity": obj.similarity_score,
                })
            elif best_sim >= min_similarity_threshold:
                obj.coverage_status = "partial"
                obj.matched_note_ids = [m["note_id"] for m in matches if m["similarity"] >= min_similarity_threshold]
                partial_count += 1
                domain_covered.setdefault(domain_name, []).append({
                    "facet_title": obj.title,
                    "matched_notes_count": len(obj.matched_note_ids),
                    "best_similarity": obj.similarity_score,
                })
            else:
                obj.coverage_status = "gap"
                obj.matched_note_ids = []
                gap_count += 1
                domain_gaps.setdefault(domain_name, []).append({
                    "gap_title": obj.title,
                    "reason": f"Objetivo de examen sin cobertura en mazo (similitud máxima: {best_sim:.2f}). {obj.description or ''}",
                    "status": "pending",
                    "source_objective_id": obj.objective_id,
                })

        # 4. Persist thematic audits for domains with gaps to feed DAG (Fase 1) & Expansion Queue (Fase 4)
        created_gaps = 0
        all_domains = set(list(domain_gaps.keys()) + list(domain_covered.keys()))
        for dom_name in all_domains:
            gaps_in_dom = domain_gaps.get(dom_name, [])
            covered_in_dom = domain_covered.get(dom_name, [])
            total_in_dom = len(gaps_in_dom) + len(covered_in_dom)
            dom_cov_pct = int((len(covered_in_dom) / total_in_dom * 100)) if total_in_dom > 0 else 100

            self._store.save_coverage_audit(
                deck_name=deck_name,
                topic=dom_name,
                description=f"Blueprint Oficial: {blueprint.exam_name}",
                coverage_percentage=dom_cov_pct,
                covered_facets=covered_in_dom,
                orphan_gaps=gaps_in_dom,
                summary_assessment=(
                    f"Contraste contra temario oficial '{blueprint.exam_name}'. "
                    f"{len(covered_in_dom)}/{total_in_dom} objetivos cubiertos ({dom_cov_pct}%)."
                ),
            )
            created_gaps += len(gaps_in_dom)

            # Register orphan concepts into DAG store so they appear in topological expansion
            for g in gaps_in_dom:
                slug_id = re.sub(r"[^a-z0-9_]+", "_", f"{dom_name}_{g['gap_title']}".lower()).strip("_")
                try:
                    self._store.upsert_deck_concept(
                        deck_name=deck_name,
                        concept_id=slug_id,
                        name=g["gap_title"],
                        taxonomy_path=dom_name,
                        description=g["reason"],
                        depth_level=1,
                    )
                except Exception as err:
                    logger.debug("Could not upsert concept '%s': %s", slug_id, err)

        total_all = len(flat_objectives)
        coverage_percentage = int((covered_count / total_all * 100)) if total_all > 0 else 100

        logger.info(
            "Alignment complete for '%s' against blueprint '%s': %d covered, %d partial, %d gaps (%d%% coverage).",
            deck_name,
            blueprint.exam_name,
            covered_count,
            partial_count,
            gap_count,
            coverage_percentage,
        )

        return BlueprintAlignmentSummary(
            deck_name=deck_name,
            exam_name=blueprint.exam_name,
            total_objectives=total_all,
            covered_count=covered_count,
            partial_count=partial_count,
            gap_count=gap_count,
            coverage_percentage=coverage_percentage,
            created_gaps_count=created_gaps,
            blueprint=blueprint,
        )
