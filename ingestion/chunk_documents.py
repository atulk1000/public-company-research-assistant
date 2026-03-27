from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_index: int
    chunk_text: str
    start_char: int
    end_char: int
    section_name: str = "body"


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[Chunk]:
    chunks: list[Chunk] = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = min(len(text), start + chunk_size)
        chunks.append(
            Chunk(
                chunk_index=chunk_index,
                chunk_text=text[start:end],
                start_char=start,
                end_char=end,
            )
        )
        if end == len(text):
            break
        start = max(0, end - overlap)
        chunk_index += 1

    return chunks
