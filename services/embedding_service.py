"""Gemini embeddings for chunks; GEMINI_EMBEDDING_MODEL defaults to gemini-embedding-001."""

import math
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_MODEL_ENV = "GEMINI_EMBEDDING_MODEL"
GEMINI_API_KEY_ENV = "GEMINI_API_KEY"
MAX_EMBEDDING_BATCH_SIZE = 100


class EmbeddingError(RuntimeError):
    """Raised when Gemini cannot provide usable chunk embeddings."""


def embed_query(query: str, *, client=None, model: str | None = None) -> list[float]:
    """Embed one query with the same model and validation used for chunks."""

    if not isinstance(query, str) or not query.strip():
        raise EmbeddingError("Query text must not be empty.")
    embedded = embed_chunks(
        [{"chunk_index": 0, "text": query}],
        client=client,
        model=model,
    )
    if not embedded:
        raise EmbeddingError("Gemini returned no embedding for the query.")
    return embedded[0]["embedding"]


def _get_client():
    # Match the existing Gemini service's project-local .env configuration,
    # while keeping client construction lazy so extraction needs no API key.
    load_dotenv(
        dotenv_path=Path(__file__).resolve().parents[1] / ".env",
        override=True,
    )
    api_key = os.getenv(GEMINI_API_KEY_ENV)
    if not api_key or not api_key.strip():
        raise EmbeddingError(
            "Gemini API configuration is missing; set GEMINI_API_KEY."
        )
    try:
        return genai.Client(api_key=api_key)
    except Exception as exc:
        raise EmbeddingError(
            "Gemini client could not be initialized; check GEMINI_API_KEY configuration."
        ) from exc


def _embedding_values(response, expected_count: int) -> list[list[float]]:
    embeddings = getattr(response, "embeddings", None)
    if not isinstance(embeddings, (list, tuple)) or len(embeddings) != expected_count:
        raise EmbeddingError("Gemini returned a malformed embedding response.")

    vectors = []
    expected_dimensions = None
    for item in embeddings:
        values = getattr(item, "values", None)
        if not isinstance(values, (list, tuple)) or not values:
            raise EmbeddingError("Gemini returned an empty or malformed embedding.")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise EmbeddingError("Gemini returned an invalid embedding vector.")
        try:
            vector = [float(value) for value in values]
        except (OverflowError, TypeError, ValueError) as exc:
            raise EmbeddingError("Gemini returned an invalid embedding vector.") from exc
        if any(not math.isfinite(value) for value in vector):
            raise EmbeddingError("Gemini returned an invalid embedding vector.")
        if expected_dimensions is None:
            expected_dimensions = len(vector)
        elif len(vector) != expected_dimensions:
            raise EmbeddingError("Gemini returned embeddings with inconsistent dimensions.")
        vectors.append(vector)
    return vectors


def embed_chunks(chunks: list[dict], *, client=None, model: str | None = None) -> list[dict]:
    """Return ordered ``{chunk, embedding}`` records for nonempty chunk text.

    Empty strings are skipped; whitespace-only chunks still receive vectors so
    every nonempty source slice retains its own chunk and embedding association.
    """

    if not chunks:
        return []

    eligible_chunks = []
    for chunk in chunks:
        if not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str):
            raise EmbeddingError("Each chunk must be a mapping with text content.")
        if chunk["text"]:
            eligible_chunks.append(chunk)
    if not eligible_chunks:
        return []

    embedding_model = model or os.getenv(EMBEDDING_MODEL_ENV, DEFAULT_EMBEDDING_MODEL)
    if not embedding_model.strip():
        raise EmbeddingError(f"{EMBEDDING_MODEL_ENV} must not be empty.")
    active_client = client if client is not None else _get_client()
    embedded_chunks = []
    for start in range(0, len(eligible_chunks), MAX_EMBEDDING_BATCH_SIZE):
        batch = eligible_chunks[start : start + MAX_EMBEDDING_BATCH_SIZE]
        try:
            response = active_client.models.embed_content(
                model=embedding_model,
                contents=[chunk["text"] for chunk in batch],
            )
        except Exception as exc:
            raise EmbeddingError(
                "Gemini embedding request failed; check API availability and configuration."
            ) from exc

        vectors = _embedding_values(response, len(batch))
        embedded_chunks.extend(
            {"chunk": chunk, "embedding": vector}
            for chunk, vector in zip(batch, vectors)
        )
    return embedded_chunks
