from ingestion.sec_exhibits import (
    extract_high_value_exhibits,
    filing_directory_url,
    filing_index_json_url,
)


def test_filing_index_url_is_derived_from_primary_document_url() -> None:
    source_url = "https://www.sec.gov/Archives/edgar/data/123/000000123456000001/form8k.htm"

    assert (
        filing_directory_url(source_url)
        == "https://www.sec.gov/Archives/edgar/data/123/000000123456000001/"
    )
    assert (
        filing_index_json_url(source_url)
        == "https://www.sec.gov/Archives/edgar/data/123/000000123456000001/index.json"
    )


def test_extract_high_value_exhibits_keeps_ex_99_documents_only() -> None:
    payload = {
        "directory": {
            "item": [
                {"name": "aapl-20260331.htm", "type": "8-K", "description": "8-K"},
                {"name": "ex991.htm", "type": "EX-99.1", "description": "Earnings release"},
                {"name": "ex992.htm", "type": "EX-99.2", "description": "Presentation"},
                {"name": "ex101.xml", "type": "EX-101.INS", "description": "XBRL"},
            ]
        }
    }

    exhibits = extract_high_value_exhibits(
        payload,
        "https://www.sec.gov/Archives/edgar/data/123/000000123456000001/form8k.htm",
    )

    assert [exhibit.exhibit_type for exhibit in exhibits] == ["EX-99.1", "EX-99.2"]
    assert exhibits[0].source_url.endswith("/ex991.htm")
    assert exhibits[0].description == "Earnings release"


def test_extract_high_value_exhibits_infers_type_from_sec_filenames() -> None:
    payload = {
        "directory": {
            "item": [
                {
                    "name": "a8-kex991q2202603282026.htm",
                    "type": "text.gif",
                    "description": None,
                },
                {
                    "name": "a8-kex992presentation.htm",
                    "type": "text.gif",
                    "description": None,
                },
                {"name": "aapl-20260430.xsd", "type": "text.gif"},
            ]
        }
    }

    exhibits = extract_high_value_exhibits(
        payload,
        "https://www.sec.gov/Archives/edgar/data/320193/000032019326000011/aapl-20260430.htm",
    )

    assert [exhibit.exhibit_type for exhibit in exhibits] == ["EX-99.1", "EX-99.2"]


def test_ingest_filing_exhibits_stores_each_exhibit_as_document(monkeypatch) -> None:
    from ingestion import load_filing_texts
    from ingestion.load_sec_data import CompanyRecord

    calls = {"documents": [], "chunks": 0}

    monkeypatch.setattr(
        load_filing_texts,
        "fetch_filing_index",
        lambda source_url: {
            "directory": {
                "item": [
                    {
                        "name": "ex991.htm",
                        "type": "EX-99.1",
                        "description": "Earnings release",
                    }
                ]
            }
        },
    )
    monkeypatch.setattr(
        load_filing_texts,
        "fetch_filing_html",
        lambda source_url: "<html><body><p>" + ("Guidance " * 120) + "</p></body></html>",
    )
    monkeypatch.setattr(load_filing_texts, "save_text", lambda text, path: path)

    def fake_insert_document(conn, company, filing, raw_text, **kwargs):
        calls["documents"].append(kwargs)
        return 42

    monkeypatch.setattr(load_filing_texts, "insert_document", fake_insert_document)
    monkeypatch.setattr(load_filing_texts, "insert_chunks", lambda *args: 3)

    counts = load_filing_texts.ingest_filing_exhibits(
        conn=object(),
        company=CompanyRecord(company_id=1, cik="0000000001", ticker="TEST", name="Test Co"),
        filing={
            "filing_id": 10,
            "accession_no": "000000123456000001",
            "form_type": "8-K",
            "filing_date": "2026-01-30",
            "source_url": "https://www.sec.gov/Archives/edgar/data/123/000000123456000001/form8k.htm",
        },
    )

    assert counts == {"documents": 1, "chunks": 3, "exhibits": 1}
    assert calls["documents"][0]["doc_type"] == "8-K EX-99.1"
    assert calls["documents"][0]["source_url"].endswith("/ex991.htm")
