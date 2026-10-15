from abc import ABC, abstractmethod
from typing import List


class IEmbeddingPort(ABC):
    """Abstract port for vector embedding generation."""

    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate float vector embeddings for a list of input texts."""
        pass

    @abstractmethod
    async def embed_single(self, text: str) -> List[float]:
        """Generate a float vector embedding for a single text."""
        pass
