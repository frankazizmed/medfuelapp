"""Deterministic fixtures for offline pipeline + signal tests."""

from __future__ import annotations

from datetime import datetime, timezone

from clinical_evidence.schemas import (
    ClinicalFinding,
    CompanyContext,
    DiscoveryResult,
    EndpointType,
    FindingType,
    Publication,
    RawDocument,
    SignalScores,
    SourceKind,
    StatisticalResult,
    Trial,
    TrialPhase,
    VerificationStatus,
)


def sample_company() -> CompanyContext:
    return CompanyContext(
        company_id="co-acme",
        name="Acme Therapeutics",
        tickers=["ACME"],
        indications=["heart failure"],
        assets=["acme-101"],
    )


def sample_trials() -> list[Trial]:
    return [
        Trial(
            trial_id="tr-NCT01",
            company_id="co-acme",
            nct_id="NCT01000001",
            title="ACME-101 Phase 3 in HFrEF",
            phase=TrialPhase.phase3,
            indication="heart failure",
            enrollment=2400,
            randomized=True,
            blinded=True,
            placebo_controlled=True,
            primary_endpoints=["CV death or HF hospitalization"],
            secondary_endpoints=["NT-proBNP", "KCCQ"],
            status="Completed",
            start_date="2022-01-01",
            primary_completion_date="2024-06-30",
            source_doc_ids=["ct-NCT01000001"],
        )
    ]


def sample_documents() -> list[RawDocument]:
    now = datetime.now(timezone.utc)
    return [
        RawDocument(
            doc_id="ct-NCT01000001",
            company_id="co-acme",
            source=SourceKind.clinicaltrials,
            url="https://clinicaltrials.gov/study/NCT01000001",
            title="ACME-101 in HFrEF (NCT01000001)",
            fetched_at=now,
            text="Randomized double-blind placebo-controlled phase 3 study...",
            metadata={},
            sha256="a" * 64,
        ),
        RawDocument(
            doc_id="pm-12345",
            company_id="co-acme",
            source=SourceKind.pubmed,
            url="https://pubmed.ncbi.nlm.nih.gov/12345/",
            title="ACME-101 reduces CV death and HF hospitalization",
            fetched_at=now,
            text="Primary endpoint HR 0.78 p<0.001 n=2400.",
            metadata={"pmid": "12345", "nct_ids": ["NCT01000001"]},
            sha256="b" * 64,
        ),
        RawDocument(
            doc_id="pr-1",
            company_id="co-acme",
            source=SourceKind.press_release,
            url="https://acme.example/news/phase3",
            title="ACME-101 hits primary endpoint",
            fetched_at=now,
            text="ACME-101 reduced CV death and HF hospitalization (HR 0.78, p<0.001).",
            metadata={},
            sha256="c" * 64,
        ),
    ]


def sample_publications() -> list[Publication]:
    return [
        Publication(
            pub_id="pub-12345",
            company_id="co-acme",
            doi="10.1056/example",
            pmid="12345",
            title="ACME-101 reduces CV death and HF hospitalization",
            journal="NEJM",
            year=2025,
            authors=["Smith J", "Patel R"],
            linked_nct_ids=["NCT01000001"],
            source_doc_id="pm-12345",
        )
    ]


def sample_findings() -> list[ClinicalFinding]:
    return [
        ClinicalFinding(
            finding_id="f-eff-1",
            company_id="co-acme",
            trial_id="tr-NCT01",
            pub_id="pub-12345",
            source_doc_id="pm-12345",
            finding_type=FindingType.efficacy,
            endpoint="CV death or HF hospitalization",
            endpoint_type=EndpointType.hard,
            description="Primary composite endpoint of CV death or HF hospitalization "
            "reduced vs placebo at median 28 months follow-up.",
            result=StatisticalResult(measure="HR", value=0.78, p_value=0.0009, ci_low=0.69, ci_high=0.88, n=2400),
            follow_up_months=28,
            verification_status=VerificationStatus.REPORTED,
            scores=SignalScores(),
            risk_flags=[],
            raw_excerpt="HR 0.78 (95% CI 0.69-0.88), p<0.001",
        ),
        ClinicalFinding(
            finding_id="f-saf-1",
            company_id="co-acme",
            trial_id="tr-NCT01",
            pub_id="pub-12345",
            source_doc_id="pm-12345",
            finding_type=FindingType.safety,
            endpoint="Serious adverse events",
            description="Serious adverse events 18% treatment vs 19% placebo.",
            result=StatisticalResult(value=18.0, units="%", n=2400),
            verification_status=VerificationStatus.REPORTED,
            scores=SignalScores(),
            risk_flags=[],
            raw_excerpt="SAE 18% vs 19% placebo",
        ),
        ClinicalFinding(
            finding_id="f-fluff",
            company_id="co-acme",
            source_doc_id="pr-1",
            finding_type=FindingType.efficacy,
            endpoint="overall benefit",
            description="ACME-101 is a promising and potentially transformative therapy.",
            result=None,
            verification_status=VerificationStatus.REPORTED,
            scores=SignalScores(),
            risk_flags=[],
            raw_excerpt="promising and potentially transformative",
        ),
        ClinicalFinding(
            finding_id="f-subgroup-thin",
            company_id="co-acme",
            trial_id="tr-NCT01",
            source_doc_id="pm-12345",
            finding_type=FindingType.subgroup,
            endpoint="response in women n=20",
            description="In a subgroup of 20 women, response rate was 32% (exploratory).",
            result=StatisticalResult(value=32.0, units="%", n=20, p_value=0.21),
            verification_status=VerificationStatus.REPORTED,
            scores=SignalScores(),
            risk_flags=[],
            raw_excerpt="n=20 exploratory",
        ),
    ]


def sample_discovery() -> DiscoveryResult:
    return DiscoveryResult(
        trials=sample_trials(),
        publications=sample_publications(),
        documents=sample_documents(),
    )
