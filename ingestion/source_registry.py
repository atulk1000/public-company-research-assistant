from __future__ import annotations

STRUCTURED_FACT_FORMS = {
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}

UNSTRUCTURED_DOCUMENT_FORMS = {
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "8-K",
    "8-K/A",
    "20-F",
    "20-F/A",
    "6-K",
    "6-K/A",
    "40-F",
    "40-F/A",
    "DEF 14A",
    "DEFA14A",
    "S-1",
    "S-1/A",
    "S-3",
    "S-3/A",
    "S-4",
    "S-4/A",
}

STRUCTURED_SOURCE_LABELS = (
    "SEC submissions metadata",
    "SEC company facts / XBRL",
    "Annual and quarterly fact forms: 10-K, 10-Q, 20-F, 40-F, plus amendments",
)

UNSTRUCTURED_SOURCE_LABELS = (
    "10-K / 10-Q",
    "8-K",
    "20-F / 6-K / 40-F",
    "DEF 14A / DEFA14A",
    "S-1 / S-3 / S-4",
)


def is_supported_document_form(form_type: str | None) -> bool:
    return bool(form_type and form_type.upper() in UNSTRUCTURED_DOCUMENT_FORMS)


def is_supported_structured_form(form_type: str | None) -> bool:
    return bool(form_type and form_type.upper() in STRUCTURED_FACT_FORMS)


def is_supported_currency_unit(unit: str | None) -> bool:
    if not unit:
        return False
    normalized = unit.upper()
    return len(normalized) == 3 and normalized.isalpha()
