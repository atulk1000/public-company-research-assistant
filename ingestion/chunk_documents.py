from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class Chunk:
    chunk_index: int
    chunk_text: str
    start_char: int
    end_char: int
    section_name: str = "body"


def split_long_paragraph(paragraph: str, chunk_size: int, overlap: int) -> list[str]:
    pieces: list[str] = []
    start = 0
    while start < len(paragraph):
        end = min(len(paragraph), start + chunk_size)
        pieces.append(paragraph[start:end].strip())
        if end == len(paragraph):
            break
        start = max(0, end - overlap)
    return [piece for piece in pieces if piece]


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[Chunk]:
    raw_paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
    paragraphs: list[str] = []
    for paragraph in raw_paragraphs:
        if len(paragraph) > chunk_size:
            paragraphs.extend(split_long_paragraph(paragraph, chunk_size=chunk_size, overlap=overlap))
        else:
            paragraphs.append(paragraph)

    if paragraphs:
        chunks: list[Chunk] = []
        chunk_index = 0
        current_parts: list[str] = []
        current_start = 0
        cursor = 0

        for paragraph in paragraphs:
            paragraph_start = text.find(paragraph, cursor)
            if paragraph_start == -1:
                paragraph_start = cursor
            paragraph_end = paragraph_start + len(paragraph)

            current_text = "\n\n".join(current_parts)
            projected_length = len(current_text) + len(paragraph) + (2 if current_parts else 0)
            if current_parts and projected_length > chunk_size:
                chunk_text_value = current_text
                chunks.append(
                    Chunk(
                        chunk_index=chunk_index,
                        chunk_text=chunk_text_value,
                        start_char=current_start,
                        end_char=current_start + len(chunk_text_value),
                    )
                )
                chunk_index += 1

                overlap_parts: list[str] = []
                overlap_length = 0
                for existing in reversed(current_parts):
                    added_length = len(existing) + (2 if overlap_parts else 0)
                    if overlap_length + added_length > overlap:
                        break
                    overlap_parts.insert(0, existing)
                    overlap_length += added_length

                current_parts = overlap_parts[:]
                if current_parts:
                    overlap_text = "\n\n".join(current_parts)
                    current_start = max(0, paragraph_start - len(overlap_text))
                else:
                    current_start = paragraph_start

            if not current_parts:
                current_start = paragraph_start

            current_parts.append(paragraph)
            cursor = paragraph_end

        if current_parts:
            chunk_text_value = "\n\n".join(current_parts)
            chunks.append(
                Chunk(
                    chunk_index=chunk_index,
                    chunk_text=chunk_text_value,
                    start_char=current_start,
                    end_char=current_start + len(chunk_text_value),
                )
            )

        if chunks:
            return chunks

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
