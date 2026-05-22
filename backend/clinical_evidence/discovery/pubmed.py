"""PubMed E-utilities source fetcher.

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from clinical_evidence.config import get_settings
from clinical_evidence.discovery._http import fetch_json, fetch_text, sha256
from clinical_evidence.schemas import (
    CompanyContext,
    DiscoveryResult,
    Publication,
    RawDocument,
    SourceKind,
)

log = logging.getLogger(__name__)

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


async def _search(query: str, retmax: int) -> list[str]:
    settings = get_settings()
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    }
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key
    data = await fetch_json(_ESEARCH, params=params)
    return (data.get("esearchresult", {}) or {}).get("idlist", []) or []


async def _fetch_pubmed_xml(pmids: list[str]) -> str:
    settings = get_settings()
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    if settings.ncbi_api_key:
        params["api_key"] = settings.ncbi_api_key
    return await fetch_text(_EFETCH, params=params)


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _parse_articles(xml_text: str, company: CompanyContext) -> tuple[list[Publication], list[RawDocument]]:
    pubs: list[Publication] = []
    docs: list[RawDocument] = []
    now = datetime.now(timezone.utc)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("PubMed XML parse failure: %s", exc)
        return pubs, docs

    for art in root.findall(".//PubmedArticle"):
        medline = art.find("MedlineCitation")
        if medline is None:
            continue
        article = medline.find("Article")
        if article is None:
            continue
        pmid_node = medline.find("PMID")
        pmid = _text(pmid_node) or None

        title = _text(article.find("ArticleTitle"))
        journal = _text(article.find(".//Journal/Title"))
        year_node = article.find(".//Journal/JournalIssue/PubDate/Year")
        year = int(_text(year_node)) if year_node is not None and _text(year_node).isdigit() else None

        authors: list[str] = []
        for a in article.findall(".//AuthorList/Author"):
            last = _text(a.find("LastName"))
            init = _text(a.find("Initials"))
            if last:
                authors.append(f"{last} {init}".strip())

        abstract_parts = [_text(p) for p in article.findall(".//Abstract/AbstractText")]
        abstract = "\n".join(p for p in abstract_parts if p)

        doi = None
        for aid in article.findall(".//ELocationID"):
            if aid.attrib.get("EIdType") == "doi":
                doi = _text(aid)
                break

        nct_ids: list[str] = []
        for db in art.findall(".//DataBankList/DataBank"):
            name = _text(db.find("DataBankName"))
            if name and name.lower() == "clinicaltrials.gov":
                nct_ids.extend(_text(acc) for acc in db.findall(".//AccessionNumber"))

        text_body = f"{title}\n\n{abstract}\n\nAuthors: {', '.join(authors)}\nJournal: {journal}"
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (
            f"https://doi.org/{doi}" if doi else "https://pubmed.ncbi.nlm.nih.gov/"
        )
        doc_id = f"pm-{pmid or doi or sha256(title)[:12]}"

        doc = RawDocument(
            doc_id=doc_id,
            company_id=company.company_id,
            source=SourceKind.pubmed,
            url=url,
            title=title,
            fetched_at=now,
            text=text_body,
            metadata={"pmid": pmid, "doi": doi, "nct_ids": nct_ids},
            sha256=sha256(text_body),
        )
        docs.append(doc)

        pubs.append(
            Publication(
                pub_id=f"pub-{pmid or sha256(title)[:12]}",
                company_id=company.company_id,
                doi=doi,
                pmid=pmid,
                title=title or "(untitled)",
                journal=journal or None,
                year=year,
                authors=authors,
                linked_nct_ids=nct_ids,
                source_doc_id=doc.doc_id,
            )
        )

    return pubs, docs


async def fetch(company: CompanyContext) -> DiscoveryResult:
    """Query PubMed for company name + each asset; return abstract-level pubs + docs."""

    queries: list[str] = [company.name]
    queries.extend(company.assets)

    pmids: list[str] = []
    seen: set[str] = set()
    for q in queries:
        try:
            ids = await _search(q, retmax=40)
        except Exception as exc:  # noqa: BLE001
            log.warning("PubMed esearch failed for %r: %s", q, exc)
            continue
        for pid in ids:
            if pid not in seen:
                seen.add(pid)
                pmids.append(pid)

    if not pmids:
        return DiscoveryResult()

    # Chunk fetches so a single call doesn't go over the API limit
    pubs: list[Publication] = []
    docs: list[RawDocument] = []
    for i in range(0, len(pmids), 50):
        chunk = pmids[i : i + 50]
        try:
            xml = await _fetch_pubmed_xml(chunk)
        except Exception as exc:  # noqa: BLE001
            log.warning("PubMed efetch failed: %s", exc)
            continue
        p, d = _parse_articles(xml, company)
        pubs.extend(p)
        docs.extend(d)

    log.info("PubMed returned %d publications for %s", len(pubs), company.name)
    return DiscoveryResult(publications=pubs, documents=docs)
