from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RawDocument:
    title: str
    doc_type: str
    doc_date: str
    source_url: str
    raw_text: str


def clean_document_text(text: str) -> str:
    return " ".join(text.split())


def parse_document(record: RawDocument) -> dict:
    return {
        "title": record.title,
        "doc_type": record.doc_type,
        "doc_date": record.doc_date,
        "source_url": record.source_url,
        "raw_text": clean_document_text(record.raw_text),
    }
