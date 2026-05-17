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

PERIODIC_REPORT_FORMS = {
    "10-K",
    "10-K/A",
    "10-Q",
    "10-Q/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}

EVENT_REPORT_FORMS = {
    "8-K",
    "8-K/A",
    "6-K",
    "6-K/A",
}

PROXY_FORMS = {
    "DEF 14A",
    "DEFA14A",
    "DEFM14A",
    "DEFM14A/A",
    "PREM14A",
    "PREM14A/A",
    "DEFC14A",
    "DEFC14A/A",
    "PREC14A",
    "PREC14A/A",
}

REGISTRATION_AND_PROSPECTUS_FORMS = {
    "S-1",
    "S-1/A",
    "S-3",
    "S-3/A",
    "S-4",
    "S-4/A",
    "424B1",
    "424B2",
    "424B3",
    "424B4",
    "424B5",
    "424B7",
    "424B8",
    "FWP",
    "425",
}

OWNERSHIP_FORMS = {
    "3",
    "3/A",
    "4",
    "4/A",
    "5",
    "5/A",
}

BENEFICIAL_OWNERSHIP_FORMS = {
    "SC 13D",
    "SC 13D/A",
    "SC 13G",
    "SC 13G/A",
}

INSTITUTIONAL_HOLDINGS_FORMS = {
    "13F-HR",
    "13F-HR/A",
}

TENDER_AND_MERGER_FORMS = {
    "SC TO-I",
    "SC TO-I/A",
    "SC TO-T",
    "SC TO-T/A",
    "SC 14D9",
    "SC 14D9/A",
}

EVENT_EXHIBIT_PARENT_FORMS = EVENT_REPORT_FORMS

HIGH_VALUE_EXHIBIT_TYPES = {
    "EX-99",
    "EX-99.1",
    "EX-99.01",
    "EX-99.2",
    "EX-99.02",
}

UNSTRUCTURED_DOCUMENT_FORMS = (
    PERIODIC_REPORT_FORMS
    | EVENT_REPORT_FORMS
    | PROXY_FORMS
    | REGISTRATION_AND_PROSPECTUS_FORMS
    | OWNERSHIP_FORMS
    | BENEFICIAL_OWNERSHIP_FORMS
    | INSTITUTIONAL_HOLDINGS_FORMS
    | TENDER_AND_MERGER_FORMS
)

DOCUMENT_FORM_PRIORITY_GROUPS = (
    PERIODIC_REPORT_FORMS,
    EVENT_REPORT_FORMS,
    PROXY_FORMS,
    REGISTRATION_AND_PROSPECTUS_FORMS,
    TENDER_AND_MERGER_FORMS | BENEFICIAL_OWNERSHIP_FORMS,
    INSTITUTIONAL_HOLDINGS_FORMS | OWNERSHIP_FORMS,
)

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
    "Prospectus forms: 424B, 425, FWP",
    "Insider ownership: Forms 3 / 4 / 5",
    "Beneficial ownership: Schedule 13D / 13G",
    "Institutional holdings: 13F-HR",
    "Tender / merger / contested proxy forms: SC TO, SC 14D9, DEFM14A, PREM14A",
)


def is_supported_document_form(form_type: str | None) -> bool:
    return bool(form_type and form_type.upper() in UNSTRUCTURED_DOCUMENT_FORMS)


def is_supported_structured_form(form_type: str | None) -> bool:
    return bool(form_type and form_type.upper() in STRUCTURED_FACT_FORMS)


def is_supported_event_exhibit_parent_form(form_type: str | None) -> bool:
    return bool(form_type and form_type.upper() in EVENT_EXHIBIT_PARENT_FORMS)


def is_supported_exhibit_type(exhibit_type: str | None) -> bool:
    return bool(exhibit_type and exhibit_type.upper() in HIGH_VALUE_EXHIBIT_TYPES)


def document_form_priority_case_sql(column: str = "form_type") -> str:
    cases = []
    for priority, forms in enumerate(DOCUMENT_FORM_PRIORITY_GROUPS, start=1):
        form_list = ", ".join(f"'{form}'" for form in sorted(forms))
        cases.append(f"WHEN UPPER({column}) IN ({form_list}) THEN {priority}")
    return (
        "CASE\n                    "
        + "\n                    ".join(cases)
        + "\n                    ELSE 99\n                END"
    )


def is_supported_currency_unit(unit: str | None) -> bool:
    if not unit:
        return False
    normalized = unit.upper()
    return len(normalized) == 3 and normalized.isalpha()
