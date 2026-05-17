from ingestion.source_registry import (
    UNSTRUCTURED_SOURCE_LABELS,
    document_form_priority_case_sql,
    is_supported_exhibit_type,
    is_supported_document_form,
    is_supported_event_exhibit_parent_form,
    is_supported_structured_form,
)


def test_expanded_sec_document_forms_are_supported() -> None:
    supported_forms = [
        "4",
        "SC 13D",
        "SC 13G/A",
        "13F-HR",
        "DEFM14A",
        "PREM14A",
        "424B5",
        "FWP",
        "SC TO-I",
        "SC 14D9",
    ]

    for form in supported_forms:
        assert is_supported_document_form(form)


def test_expanded_sec_forms_do_not_become_structured_fact_forms() -> None:
    assert not is_supported_structured_form("4")
    assert not is_supported_structured_form("SC 13D")
    assert not is_supported_structured_form("424B5")


def test_source_labels_explain_expanded_sec_coverage() -> None:
    labels = " ".join(UNSTRUCTURED_SOURCE_LABELS)

    assert "Forms 3 / 4 / 5" in labels
    assert "Schedule 13D / 13G" in labels
    assert "13F-HR" in labels
    assert "424B" in labels
    assert "SC TO" in labels


def test_document_form_priority_case_keeps_periodic_filings_first() -> None:
    priority_case = document_form_priority_case_sql("form_type")

    assert "WHEN UPPER(form_type) IN" in priority_case
    assert "'10-K'" in priority_case
    assert "'4'" in priority_case
    assert priority_case.index("'10-K'") < priority_case.index("'4'")


def test_high_value_event_exhibit_types_are_supported() -> None:
    assert is_supported_event_exhibit_parent_form("8-K")
    assert is_supported_event_exhibit_parent_form("6-K")
    assert is_supported_exhibit_type("EX-99.1")
    assert is_supported_exhibit_type("EX-99.2")
    assert not is_supported_exhibit_type("EX-101.INS")
