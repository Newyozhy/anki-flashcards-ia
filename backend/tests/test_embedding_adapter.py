import unittest
from unittest.mock import MagicMock, patch
import pytest

from app.adapters.ai.gemini_embedding_adapter import GeminiEmbeddingAdapter


def test_extract_retry_delay():
    adapter = GeminiEmbeddingAdapter(api_key="test_dummy_key")

    # Pattern with "Please retry in 16.2589s"
    err1 = "Quota exceeded... Please retry in 16.258910353s."
    delay1 = adapter._extract_retry_delay(err1)
    assert 17.0 <= delay1 <= 17.5

    # Pattern with retryDelay: '14s'
    err2 = "{'retryDelay': '14s'}"
    delay2 = adapter._extract_retry_delay(err2)
    assert 14.5 <= delay2 <= 15.5

    # Fallback default
    err3 = "Resource exhausted without delay info"
    delay3 = adapter._extract_retry_delay(err3, default=12.0)
    assert delay3 == 12.0


def test_sync_embed_batch_retry_on_429():
    adapter = GeminiEmbeddingAdapter(api_key="test_dummy_key")
    mock_client = MagicMock()

    # First call raises 429, second call succeeds
    error_429 = Exception("429 RESOURCE_EXHAUSTED: Please retry in 0.01s.")
    mock_resp = MagicMock()
    mock_resp.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]

    mock_client.models.embed_content.side_effect = [error_429, mock_resp]

    with patch("app.adapters.ai.gemini_embedding_adapter.time.sleep", return_value=None) as mock_sleep:
        results = adapter._sync_embed_batch(mock_client, ["Test concept"])
        assert len(results) == 1
        assert results[0] == [0.1, 0.2, 0.3]
        assert mock_sleep.called
        assert mock_client.models.embed_content.call_count == 2
