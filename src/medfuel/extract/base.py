from __future__ import annotations

from abc import ABC, abstractmethod

from medfuel.models import CandidateEvent, RawSourceRecord


class Extractor(ABC):
    """Produces CandidateEvent records from a single source document.

    Extractors never persist and never assign IDs — that is the verifier's job.
    Implementations should be safe to call concurrently across documents.
    """

    name: str = "base"

    @abstractmethod
    async def extract(self, *, source_doc_id: str, record: RawSourceRecord) -> list[CandidateEvent]:
        ...
