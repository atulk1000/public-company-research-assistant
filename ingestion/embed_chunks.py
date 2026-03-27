from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EmbeddedChunk:
    chunk_text: str
    embedding: list[float]


def fake_embed(text: str) -> list[float]:
    """Temporary placeholder until live embeddings are wired in."""
    text = text.lower()
    return [float(len(text)), float(text.count("ai")), float(text.count("margin"))]


def embed_chunk_texts(chunk_texts: list[str]) -> list[EmbeddedChunk]:
    return [EmbeddedChunk(chunk_text=chunk_text, embedding=fake_embed(chunk_text)) for chunk_text in chunk_texts]
