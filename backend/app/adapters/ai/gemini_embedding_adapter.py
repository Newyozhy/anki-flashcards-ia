import asyncio
import logging
import re
import time
from typing import List, Optional
from google import genai
from google.genai import types

from app.core.config import settings
from app.ports.embedding_port import IEmbeddingPort

logger = logging.getLogger(__name__)


class GeminiEmbeddingAdapter(IEmbeddingPort):
    """Adapter for Google Gemini Embedding API using the modern google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model = model or getattr(settings, "GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Lazily initialize the Gemini client."""
        if not self._api_key:
            raise ValueError(
                "GEMINI_API_KEY is required for embedding generation. "
                "Please configure it in settings or provide a dynamic key."
            )
        if self._client is None:
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=60000),
            )
        return self._client

    def _extract_retry_delay(self, err_msg: str, default: float = 15.0) -> float:
        """Extract retry delay seconds from Gemini 429 quota exception message."""
        m1 = re.search(r"retry\s+in\s+([\d\.]+)\s*s", err_msg, re.IGNORECASE)
        if m1:
            try:
                return float(m1.group(1)) + 1.0
            except (ValueError, TypeError):
                pass
        m2 = re.search(r"['\"]?retryDelay['\"]?:\s*['\"]?(\d+)s?['\"]?", err_msg, re.IGNORECASE)
        if m2:
            try:
                return float(m2.group(1)) + 1.0
            except (ValueError, TypeError):
                pass
        return default

    def _sync_embed_batch(self, client: genai.Client, batch: List[str]) -> List[List[float]]:
        """Synchronously request embeddings for a batch of strings with intelligent 429 rate-limit backoff."""
        # Replace empty strings with a single space to avoid API validation errors
        safe_batch = [t.strip() if t and t.strip() else " " for t in batch]

        # Only use active Gemini-era models; deprecated legacy models (text-embedding-004) are removed
        candidate_models = list(dict.fromkeys([
            self._model,
            "gemini-embedding-001",
            "models/gemini-embedding-001",
        ]))

        response = None
        last_error = None
        max_rate_limit_retries = 3

        for cand in candidate_models:
            retries = 0
            while retries <= max_rate_limit_retries:
                try:
                    # Attempt with 768 dimensions for compact, fast cosine matching
                    try:
                        response = client.models.embed_content(
                            model=cand,
                            contents=safe_batch,
                            config=types.EmbedContentConfig(output_dimensionality=768),
                        )
                    except Exception as dim_err:
                        dim_err_str = str(dim_err)
                        if "429" in dim_err_str or "RESOURCE_EXHAUSTED" in dim_err_str:
                            raise dim_err
                        response = client.models.embed_content(
                            model=cand,
                            contents=safe_batch,
                        )
                    self._model = cand  # Cache working model for subsequent calls
                    logger.info("Successfully generated embeddings for batch of %d items using model '%s'", len(batch), cand)
                    break
                except Exception as err:
                    last_error = err
                    err_str = str(err)
                    is_rate_limit = (
                        "429" in err_str
                        or "RESOURCE_EXHAUSTED" in err_str
                        or "quota" in err_str.lower()
                    )

                    if is_rate_limit and retries < max_rate_limit_retries:
                        retries += 1
                        delay = self._extract_retry_delay(err_str, default=15.0)
                        logger.warning(
                            "Gemini Embedding rate limit (429 RESOURCE_EXHAUSTED) hit on model '%s'. "
                            "Backing off for %.1fs before retry (attempt %d/%d)...",
                            cand, delay, retries, max_rate_limit_retries
                        )
                        time.sleep(delay)
                        continue
                    else:
                        logger.warning("Embedding candidate '%s' failed: %s. Trying next candidate...", cand, err)
                        break

            if response is not None:
                break

        if response is None:
            raise RuntimeError(f"All Gemini embedding candidate models failed. Last error: {last_error}")

        embeddings_list = []
        raw_list = getattr(response, "embeddings", None)
        if raw_list is None and hasattr(response, "embedding"):
            raw_list = [response.embedding]

        if not raw_list:
            raise RuntimeError("Gemini embed_content returned an empty embeddings response.")

        for emb in raw_list:
            if hasattr(emb, "values"):
                vec = [float(x) for x in emb.values]
            elif isinstance(emb, dict) and "values" in emb:
                vec = [float(x) for x in emb["values"]]
            else:
                vec = [float(x) for x in emb]
            embeddings_list.append(vec)

        return embeddings_list

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of strings in batches of up to 50 texts with rate pacing."""
        if not texts:
            return []

        client = self._get_client()
        all_embeddings: List[List[float]] = []
        batch_size = 50

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_result = await asyncio.to_thread(self._sync_embed_batch, client, batch)
            all_embeddings.extend(batch_result)
            if i + batch_size < len(texts):
                await asyncio.sleep(1.0)  # Gentle rate pacing between batches

        return all_embeddings

    async def embed_single(self, text: str) -> List[float]:
        """Embed a single string."""
        if not text or not text.strip():
            text = " "
        results = await self.embed_texts([text])
        if not results:
            raise RuntimeError(f"Failed to generate embedding for text: {text[:40]}")
        return results[0]

    async def get_embedding(self, text: str) -> List[float]:
        """Compatibility alias for embed_single."""
        return await self.embed_single(text)

