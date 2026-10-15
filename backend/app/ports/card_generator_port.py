from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
from app.domain.models import Flashcard, GenerationOptions, StudyPlanInspection, EnrichedConceptResult


class ICardGeneratorPort(ABC):
    """Port interface for AI-based flashcard generation."""

    @abstractmethod
    async def generate_from_text(
        self, text: str, options: GenerationOptions
    ) -> List[Flashcard]:
        """Generate flashcards from raw educational text."""
        pass

    async def generate_from_text_stream(
        self, text: str, options: GenerationOptions
    ):
        """Yield (batch_label, cards, current_batch, total_batches) progressively. Fallback yields all at once."""
        cards = await self.generate_from_text(text, options)
        yield ("Completo", cards, 1, 1)

    @abstractmethod
    async def generate_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> List[Flashcard]:
        """Generate flashcards from multimodal media (images, diagrams, PDFs) with optional accompanying text and multi-image parts."""
        pass

    async def generate_from_media_stream(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ):
        """Yield (batch_label, cards, current_batch, total_batches) progressively. Fallback yields all at once."""
        cards = await self.generate_from_media(
            file_bytes, mime_type, options, text=text, media_parts=media_parts
        )
        yield ("Completo", cards, 1, 1)

    @abstractmethod
    async def inspect_material(
        self,
        text: str,
        options: GenerationOptions,
        media_parts: Optional[List[Tuple[bytes, str]]] = None,
    ) -> StudyPlanInspection:
        """Analyze study material for topic breakdown, missing prerequisites, and atomic card planning."""
        pass

    @abstractmethod
    async def inspect_material_from_media(
        self,
        file_bytes: bytes,
        mime_type: str,
        options: GenerationOptions,
        text: Optional[str] = None,
    ) -> StudyPlanInspection:
        """Analyze study material from uploaded PDF or image for topic breakdown, prerequisites, and deep subtopics with optional accompanying text."""
        pass

    @abstractmethod
    async def enrich_prerequisite(
        self, concept: str, search_query: str, context_topic: Optional[str] = None
    ) -> EnrichedConceptResult:
        """Asynchronously research and synthesize a foundational prerequisite concept."""
        pass


