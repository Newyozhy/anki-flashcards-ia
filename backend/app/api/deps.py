from functools import lru_cache
from typing import Optional
from app.core.config import settings
from app.ports.card_generator_port import ICardGeneratorPort
from app.adapters.ai.gemini_card_generator_adapter import GeminiCardGeneratorAdapter
from app.adapters.ai.resilient_cascade_adapter import ResilientCascadeAdapter
from app.adapters.ai.ollama_adapter import OllamaCardGeneratorAdapter
from app.adapters.anki.anki_connect_adapter import AnkiConnectAdapter
from app.adapters.anki.genanki_file_adapter import GenankiFileAdapter
from app.adapters.db.deck_knowledge_store import DeckKnowledgeStore
from app.adapters.ai.gemini_embedding_adapter import GeminiEmbeddingAdapter
from app.services.generate_cards_service import GenerateCardsUseCase
from app.services.pedagogical_discriminator_service import PedagogicalDiscriminatorService
from app.services.export_deck_service import ExportDeckUseCase
from app.services.inspect_material_service import InspectMaterialUseCase, EnrichPrerequisiteUseCase
from app.services.deck_intelligence_service import DeckIntelligenceService



@lru_cache()
def get_anki_connect_adapter() -> AnkiConnectAdapter:
    return AnkiConnectAdapter()


@lru_cache()
def get_genanki_file_adapter() -> GenankiFileAdapter:
    return GenankiFileAdapter()


def get_card_generator_adapter(
    provider: str = "gemini",
    api_key: Optional[str] = None,
    local_model: Optional[str] = None,
) -> ICardGeneratorPort:
    if provider.lower() == "ollama":
        return OllamaCardGeneratorAdapter(model=local_model or "qwen2.5:14b")
    return ResilientCascadeAdapter(gemini_api_key=api_key or settings.GEMINI_API_KEY)


def get_pedagogical_discriminator_service(
    api_key: Optional[str] = None,
) -> PedagogicalDiscriminatorService:
    store = get_deck_knowledge_store()
    embedding_adapter = get_gemini_embedding_adapter(api_key=api_key)
    return PedagogicalDiscriminatorService(
        store=store,
        embedding_adapter=embedding_adapter,
    )


def get_generate_cards_service(
    provider: str = "gemini",
    api_key: Optional[str] = None,
    local_model: Optional[str] = None,
) -> GenerateCardsUseCase:
    generator = get_card_generator_adapter(
        provider=provider, api_key=api_key, local_model=local_model
    )
    store = get_deck_knowledge_store()
    dag_service = get_deck_dag_service()
    discriminator = get_pedagogical_discriminator_service(api_key=api_key)
    return GenerateCardsUseCase(
        card_generator=generator,
        pedagogical_discriminator=discriminator,
        store=store,
        dag_service=dag_service,
    )


def get_inspect_material_service(
    provider: str = "gemini",
    api_key: Optional[str] = None,
    local_model: Optional[str] = None,
) -> InspectMaterialUseCase:
    if provider.lower() == "ollama":
        generator = OllamaCardGeneratorAdapter(model=local_model or "qwen2.5:14b")
    else:
        from app.adapters.ai.resilient_cascade_adapter import ResilientCascadeAdapter
        generator = ResilientCascadeAdapter(gemini_api_key=api_key)
    return InspectMaterialUseCase(
        card_generator=generator,
        anki_bridge=get_anki_connect_adapter(),
        store=get_deck_knowledge_store(),
    )


def get_enrich_prerequisite_service(
    provider: str = "gemini",
    api_key: Optional[str] = None,
    local_model: Optional[str] = None,
) -> EnrichPrerequisiteUseCase:
    generator = get_card_generator_adapter(
        provider=provider, api_key=api_key, local_model=local_model
    )
    return EnrichPrerequisiteUseCase(card_generator=generator)


def get_export_deck_service() -> ExportDeckUseCase:
    return ExportDeckUseCase(
        anki_connect_bridge=get_anki_connect_adapter(),
        apkg_bridge=get_genanki_file_adapter(),
        store=get_deck_knowledge_store(),
    )


@lru_cache()
def get_deck_knowledge_store() -> DeckKnowledgeStore:
    return DeckKnowledgeStore()


def get_gemini_embedding_adapter(api_key: Optional[str] = None) -> GeminiEmbeddingAdapter:
    return GeminiEmbeddingAdapter(api_key=api_key or settings.GEMINI_API_KEY)


def get_deck_intelligence_service(api_key: Optional[str] = None) -> DeckIntelligenceService:
    return DeckIntelligenceService(
        anki_bridge=get_anki_connect_adapter(),
        embedding_port=get_gemini_embedding_adapter(api_key=api_key),
        store=get_deck_knowledge_store(),
        card_generator=get_card_generator_adapter(provider="gemini", api_key=api_key),
    )


@lru_cache()
def get_deck_dag_service() -> "DeckDAGService":
    from app.services.deck_dag_service import DeckDAGService
    return DeckDAGService(store=get_deck_knowledge_store())


def get_ontology_extractor_service(api_key: Optional[str] = None) -> "OntologyExtractorService":
    from app.services.ontology_extractor_service import OntologyExtractorService
    return OntologyExtractorService(
        store=get_deck_knowledge_store(),
        dag_service=get_deck_dag_service(),
        gemini_api_key=api_key,
    )


def get_deck_interview_service(api_key: Optional[str] = None) -> "DeckInterviewService":
    from app.services.deck_interview_service import DeckInterviewService
    return DeckInterviewService(
        store=get_deck_knowledge_store(),
        dag_service=get_deck_dag_service(),
        gemini_api_key=api_key,
    )


def get_sanitation_service(api_key: Optional[str] = None) -> "SanitationService":
    from app.services.sanitation_service import SanitationService
    return SanitationService(
        anki_bridge=get_anki_connect_adapter(),
        store=get_deck_knowledge_store(),
        dag_service=get_deck_dag_service(),
        embedding_port=get_gemini_embedding_adapter(api_key=api_key),
    )


def get_deck_expansion_service() -> "DeckExpansionService":
    from app.services.deck_expansion_service import DeckExpansionService
    return DeckExpansionService(
        store=get_deck_knowledge_store(),
        dag_service=get_deck_dag_service(),
        anki_bridge=get_anki_connect_adapter(),
    )


def get_exam_blueprint_service(api_key: Optional[str] = None) -> "ExamBlueprintService":
    from app.services.exam_blueprint_service import ExamBlueprintService
    return ExamBlueprintService(
        store=get_deck_knowledge_store(),
        embedding_port=get_gemini_embedding_adapter(api_key=api_key),
        gemini_api_key=api_key,
    )


def get_socratic_red_teaming_service(api_key: Optional[str] = None) -> "SocraticRedTeamingService":
    from app.services.socratic_red_teaming_service import SocraticRedTeamingService
    return SocraticRedTeamingService(
        store=get_deck_knowledge_store(),
        api_key=api_key,
    )





