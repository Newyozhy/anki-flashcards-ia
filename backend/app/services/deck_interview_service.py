import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from google import genai
from google.genai import types

from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.core.config import settings
from app.domain.models import (
    DeckConceptDAG,
    DeckInterviewForm,
    LearningPlanContract,
    SlotQuestion,
    SlotQuestionOption,
)
from app.services.deck_dag_service import DeckDAGService

logger = logging.getLogger(__name__)


class DeckInterviewService:
    """Orchestrates Phase 2 contextual interview and Learning Plan Contract synthesis."""

    def __init__(
        self,
        store: DeckKnowledgeStore,
        dag_service: DeckDAGService,
        gemini_api_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
    ):
        self._store = store
        self._dag_service = dag_service
        self._gemini_api_key = gemini_api_key or settings.GEMINI_API_KEY
        self._groq_api_key = groq_api_key or settings.GROQ_API_KEY

    def _build_form_generator_instruction(self) -> str:
        return (
            "Eres un Director Pedagógico Senior y Diseñador Instruccional especializado en Neurociencia del Aprendizaje.\n"
            "Tu misión es generar un Formulario de Entrevista Personalizado y NO GENÉRICO para establecer un Plan de Estudio (Learning Plan Contract).\n"
            "DEBES generar exactamente 4 preguntas correspondientes a los 4 slots obligatorios:\n"
            "1. 'bloom_level': Nivel cognitivo (memorización declarativa vs diseño arquitectónico vs troubleshooting).\n"
            "2. 'exclusion_boundary': Frontera de exclusión (delimitar qué tecnologías o temas específicos NO entran para evitar sobrecarga).\n"
            "3. 'gap_strategy': Tratamiento de conceptos huérfanos o brechas detectadas (crear tarjetas base, crear tarjetas deep-dive o asumir aprendidos).\n"
            "4. 'operational_depth': Profundidad operativa (conceptos teóricos vs comandos de terminal/CLI vs código/sintaxis).\n\n"
            "REGLA CRÍTICA: Las preguntas y opciones DEBEN citar explícitamente los conceptos, servicios y brechas reales del mazo proporcionado.\n"
            "Devuelve EXCLUSIVAMENTE un objeto JSON válido con la estructura solicitada."
        )

    def _build_form_prompt(self, deck_name: str, dag: DeckConceptDAG) -> str:
        sample_concepts = [n.name for n in dag.nodes[:12]]
        orphans = [dag.nodes[i].name for i, n in enumerate(dag.nodes) if n.is_orphan][:6]
        taxonomies = list({n.taxonomy_path for n in dag.nodes if n.taxonomy_path})[:6]

        return (
            f"Mazo: '{deck_name}'\n"
            f"Total de conceptos extraídos: {dag.total_concepts}\n"
            f"Conceptos principales identificados: {', '.join(sample_concepts) if sample_concepts else 'Conceptos generales'}\n"
            f"Brechas/prerrequisitos huérfanos detectados: {', '.join(orphans) if orphans else 'Ninguna detectada'}\n"
            f"Ramas taxonómicas: {', '.join(taxonomies) if taxonomies else 'general'}\n\n"
            "Genera el formulario contextual en JSON con:\n"
            "{\n"
            "  'topic_overview': 'Breve análisis del dominio del mazo',\n"
            "  'questions': [\n"
            "    {\n"
            "      'slot_key': 'bloom_level' | 'exclusion_boundary' | 'gap_strategy' | 'operational_depth',\n"
            "      'title': 'Título de la pregunta',\n"
            "      'contextual_explanation': 'Justificación pedagógica citando los conceptos reales del mazo',\n"
            "      'options': [\n"
            "        {\n"
            "          'id': 'slug_opcion',\n"
            "          'label': 'Nombre corto',\n"
            "          'description': 'Descripción contextualizada',\n"
            "          'is_recommended': true/false\n"
            "        }\n"
            "      ]\n"
            "    }\n"
            "  ]\n"
            "}"
        )

    async def _call_llm_json(
        self,
        system_instruction: str,
        user_prompt: str,
        api_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        key = api_key or self._gemini_api_key
        if key:
            client = genai.Client(api_key=key)
            for model_name in ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-1.5-flash"]:
                try:
                    resp = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.15,
                            response_mime_type="application/json",
                        ),
                    )
                    if resp and resp.text:
                        clean = resp.text.strip()
                        clean = re.sub(r"^```json\s*", "", clean)
                        clean = re.sub(r"\s*```$", "", clean)
                        return json.loads(clean)
                except Exception as e:
                    logger.debug("Gemini tier '%s' failed in interview service: %s", model_name, e)
                    continue

        # Groq Fallback
        if self._groq_api_key:
            try:
                url = "https://api.groq.com/openai/v1/chat/completions"
                headers = {"Authorization": f"Bearer {self._groq_api_key}", "Content-Type": "application/json"}
                payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.15,
                    "response_format": {"type": "json_object"},
                }
                async with httpx.AsyncClient(timeout=25.0) as http_client:
                    r = await http_client.post(url, headers=headers, json=payload)
                    if r.status_code == 200:
                        content = r.json()["choices"][0]["message"]["content"]
                        return json.loads(content)
            except Exception as ge:
                logger.debug("Groq tier failed in interview service: %s", ge)

        return None

    def _heuristic_fallback_form(self, deck_name: str, dag: DeckConceptDAG) -> DeckInterviewForm:
        """Deterministic tailored fallback form based on extracted DAG concepts."""
        orphans = [dag.nodes[i].name for i, n in enumerate(dag.nodes) if n.is_orphan][:4]
        orphan_str = ", ".join(orphans) if orphans else "conceptos base no cubiertos"

        questions: List[SlotQuestion] = [
            SlotQuestion(
                slot_key="bloom_level",
                title="¿Qué nivel de maestría cognitiva buscás certificar en este mazo?",
                contextual_explanation=f"Definirá si las tarjetas evalúan definiciones atómicas o arquitectura en '{deck_name}'.",
                options=[
                    SlotQuestionOption(
                        id="bloom_understanding",
                        label="Comprensión y Retención Declarativa",
                        description="Identificar definiciones, componentes y propiedades clave.",
                        is_recommended=False,
                    ),
                    SlotQuestionOption(
                        id="bloom_analysis",
                        label="Diseño y Análisis Arquitectónico",
                        description="Comparar alternativas, evaluar compatibilidad y justificar decisiones de diseño.",
                        is_recommended=True,
                    ),
                    SlotQuestionOption(
                        id="bloom_troubleshooting",
                        label="Resolución de Problemas (Troubleshooting)",
                        description="Diagnosticar fallas operativas, errores de configuración y cuellos de botella.",
                        is_recommended=False,
                    ),
                ],
            ),
            SlotQuestion(
                slot_key="exclusion_boundary",
                title="¿Qué frontera de exclusión querés establecer para evitar ruido?",
                contextual_explanation="Delimita qué servicios o subtemas quedan fuera del alcance.",
                options=[
                    SlotQuestionOption(
                        id="exclude_hybrid_legacy",
                        label="Excluir arquitecturas híbridas y servicios legacy",
                        description="Enfocarse exclusivamente en servicios cloud puros y modernos.",
                        is_recommended=True,
                    ),
                    SlotQuestionOption(
                        id="exclude_none",
                        label="Cobertura completa sin exclusiones",
                        description="Incluir todos los aspectos del temario sin recortar alcance.",
                        is_recommended=False,
                    ),
                ],
            ),
            SlotQuestion(
                slot_key="gap_strategy",
                title="¿Cómo trataremos las brechas y prerrequisitos huérfanos detectados?",
                contextual_explanation=f"Detectamos que ({orphan_str}) son prerrequisitos asumidos pero ninguna tarjeta actual los enseña.",
                options=[
                    SlotQuestionOption(
                        id="fill_all_anchors",
                        label="Crear tarjetas base atómicas (Recomendado)",
                        description="Generar tarjetas de anclaje para todos los prerrequisitos huérfanos antes de expandir.",
                        is_recommended=True,
                    ),
                    SlotQuestionOption(
                        id="assume_prerequisites",
                        label="Asumir prerrequisitos como aprendidos",
                        description="No generar tarjetas para los prerrequisitos huérfanos; saltar directo al contenido del mazo.",
                        is_recommended=False,
                    ),
                ],
            ),
            SlotQuestion(
                slot_key="operational_depth",
                title="¿Qué profundidad operativa deben tener las preguntas?",
                contextual_explanation="Determina si las tarjetas deben evaluar comandos de terminal, código o conceptos.",
                options=[
                    SlotQuestionOption(
                        id="theory_and_architecture",
                        label="Lógica y Arquitectura Conceptual (Sin comandos)",
                        description="Evaluar reglas de funcionamiento y arquitectura sin memorizar flags de CLI.",
                        is_recommended=True,
                    ),
                    SlotQuestionOption(
                        id="include_cli_code",
                        label="Incluir Comandos de CLI y Sintaxis",
                        description="Memorizar sintaxis de CLI, parámetros y estructuras de configuración.",
                        is_recommended=False,
                    ),
                ],
            ),
        ]

        return DeckInterviewForm(
            deck_name=deck_name,
            topic_overview=f"Dominio educativo del mazo '{deck_name}'.",
            detected_concepts_count=dag.total_concepts,
            detected_orphans_count=len(dag.orphan_concepts),
            sample_concepts=[n.name for n in dag.nodes[:10]],
            orphan_concepts=dag.orphan_concepts[:6],
            questions=questions,
        )

    async def generate_interview_form(
        self,
        deck_name: str,
        api_key: Optional[str] = None,
    ) -> DeckInterviewForm:
        """Generate tailored 4-slot interview form using the deck's real DAG."""
        dag = self._dag_service.get_deck_dag(deck_name)

        system_instruction = self._build_form_generator_instruction()
        user_prompt = self._build_form_prompt(deck_name, dag)

        data = await self._call_llm_json(system_instruction, user_prompt, api_key=api_key)
        if not data or not data.get("questions") or len(data["questions"]) < 4:
            logger.warning("LLM interview form generation returned incomplete schema; using heuristic DAG fallback.")
            return self._heuristic_fallback_form(deck_name, dag)

        questions: List[SlotQuestion] = []
        for q in data["questions"]:
            options = [
                SlotQuestionOption(
                    id=opt.get("id") or f"opt_{idx}",
                    label=opt.get("label", ""),
                    description=opt.get("description", ""),
                    is_recommended=bool(opt.get("is_recommended", False)),
                )
                for idx, opt in enumerate(q.get("options") or [])
            ]
            questions.append(
                SlotQuestion(
                    slot_key=q.get("slot_key", "general"),
                    title=q.get("title", ""),
                    contextual_explanation=q.get("contextual_explanation", ""),
                    options=options,
                    custom_input_allowed=True,
                )
            )

        return DeckInterviewForm(
            deck_name=deck_name,
            topic_overview=data.get("topic_overview") or f"Análisis ontológico para {deck_name}",
            detected_concepts_count=dag.total_concepts,
            detected_orphans_count=len(dag.orphan_concepts),
            sample_concepts=[n.name for n in dag.nodes[:10]],
            orphan_concepts=dag.orphan_concepts[:6],
            questions=questions,
        )

    async def synthesize_contract(
        self,
        deck_name: str,
        answers: Dict[str, str],
        api_key: Optional[str] = None,
    ) -> LearningPlanContract:
        """Synthesize formal LearningPlanContract preview from the user's answers."""
        dag = self._dag_service.get_deck_dag(deck_name)

        system_instruction = (
            "Eres un Arquitecto Pedagógico. A partir de las respuestas del estudiante para los 4 slots de un mazo Anki, "
            "sintetiza el Contrato Formal de Aprendizaje (LearningPlanContract).\n"
            "Devuelve un JSON con:\n"
            "{\n"
            "  'bloom_level': 'Estándar cognitivo acordado',\n"
            "  'exclusion_boundary': ['Tema 1', 'Tema 2'],\n"
            "  'gap_strategy': 'fill_all_anchors' | 'fill_critical_only' | 'assume_prerequisites',\n"
            "  'operational_depth': 'Profundidad de sintaxis/comandos acordada',\n"
            "  'raw_summary': 'Resumen ejecutivo claro y directo en markdown explicando el acuerdo pedagógico.'\n"
            "}"
        )

        user_prompt = (
            f"Mazo: {deck_name}\n"
            f"Conceptos en DAG: {dag.total_concepts} conceptos\n"
            f"Brechas huérfanas: {', '.join(dag.orphan_concepts[:5])}\n"
            f"Respuestas recibidas:\n{json.dumps(answers, indent=2, ensure_ascii=False)}\n\n"
            "Sintetiza el LearningPlanContract."
        )

        data = await self._call_llm_json(system_instruction, user_prompt, api_key=api_key)
        if not data:
            # Fallback direct synthesis
            bloom = answers.get("bloom_level") or "Diseño y Análisis Arquitectónico"
            exclusion = [answers.get("exclusion_boundary")] if answers.get("exclusion_boundary") else ["Arquitecturas híbridas complejas"]
            gap_strat = answers.get("gap_strategy") or "fill_all_anchors"
            depth = answers.get("operational_depth") or "Lógica y Arquitectura Conceptual"
            summary = (
                f"### Plan Pedagógico Acordado para {deck_name}\n"
                f"- **Nivel Cognitivo:** {bloom}\n"
                f"- **Exclusiones:** {', '.join(exclusion)}\n"
                f"- **Estrategia de Brechas:** {gap_strat}\n"
                f"- **Profundidad:** {depth}"
            )
            contract = LearningPlanContract(
                deck_name=deck_name,
                bloom_level=bloom,
                exclusion_boundary=exclusion,
                gap_strategy=gap_strat,
                operational_depth=depth,
                raw_summary=summary,
                status="draft",
            )
        else:
            contract = LearningPlanContract(
                deck_name=deck_name,
                bloom_level=data.get("bloom_level") or "Diseño y Análisis",
                exclusion_boundary=data.get("exclusion_boundary") or [],
                gap_strategy=data.get("gap_strategy") or "fill_all_anchors",
                operational_depth=data.get("operational_depth") or "Conceptual",
                raw_summary=data.get("raw_summary") or "",
                status="draft",
            )

        # Save draft in store
        self._store.save_learning_contract(deck_name, contract.model_dump(), status="draft")
        return contract

    async def refine_contract(
        self,
        deck_name: str,
        current_contract: LearningPlanContract,
        user_feedback: str,
        api_key: Optional[str] = None,
    ) -> LearningPlanContract:
        """Refine clauses of an existing contract preview using natural language feedback."""
        system_instruction = (
            "Eres un Arquitecto Pedagógico negociando un Contrato de Aprendizaje con el estudiante.\n"
            "Recibes el contrato actual y el feedback/petición de cambio del usuario.\n"
            "Ajusta los campos del contrato (bloom_level, exclusion_boundary, gap_strategy, operational_depth) "
            "y actualiza 'raw_summary' reflejando los acuerdos alcanzados.\n"
            "Devuelve un JSON con la estructura completa del LearningPlanContract."
        )

        user_prompt = (
            f"Mazo: {deck_name}\n"
            f"Contrato Actual:\n{json.dumps(current_contract.model_dump(), indent=2, ensure_ascii=False)}\n\n"
            f"Feedback del estudiante:\n\"{user_feedback}\"\n\n"
            "Aplica los ajustes solicitados y emite el contrato modificado."
        )

        data = await self._call_llm_json(system_instruction, user_prompt, api_key=api_key)
        new_version = current_contract.version + 1

        if not data:
            # Append feedback to summary
            updated_summary = (
                f"{current_contract.raw_summary}\n\n"
                f"**Ajuste v{new_version}:** {user_feedback}"
            )
            refined = current_contract.model_copy(
                update={"raw_summary": updated_summary, "version": new_version}
            )
        else:
            refined = LearningPlanContract(
                deck_name=deck_name,
                bloom_level=data.get("bloom_level") or current_contract.bloom_level,
                exclusion_boundary=data.get("exclusion_boundary") or current_contract.exclusion_boundary,
                gap_strategy=data.get("gap_strategy") or current_contract.gap_strategy,
                operational_depth=data.get("operational_depth") or current_contract.operational_depth,
                raw_summary=data.get("raw_summary") or current_contract.raw_summary,
                version=new_version,
                status="draft",
            )

        self._store.save_learning_contract(deck_name, refined.model_dump(), status="draft")
        return refined

    def approve_contract(self, deck_name: str, contract: LearningPlanContract) -> LearningPlanContract:
        """Finalize and lock the learning plan contract in the persistent store."""
        approved = contract.model_copy(
            update={
                "status": "approved",
                "approved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._store.save_learning_contract(deck_name, approved.model_dump(), status="approved")
        logger.info("LearningPlanContract for deck '%s' APPROVED and locked.", deck_name)
        return approved

    def get_learning_contract(self, deck_name: str) -> Optional[LearningPlanContract]:
        """Retrieve stored contract if available."""
        data = self._store.get_learning_contract(deck_name)
        if not data:
            return None
        return LearningPlanContract(
            deck_name=data.get("deck_name", deck_name),
            bloom_level=data.get("bloom_level", "General"),
            exclusion_boundary=data.get("exclusion_boundary") or [],
            gap_strategy=data.get("gap_strategy", "fill_all_anchors"),
            operational_depth=data.get("operational_depth", "General"),
            raw_summary=data.get("raw_summary", ""),
            version=data.get("version", 1),
            status=data.get("status", "draft"),
            approved_at=data.get("approved_at"),
        )
