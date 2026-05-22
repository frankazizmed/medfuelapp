from __future__ import annotations

from abc import ABC, abstractmethod

from medfuel.models.schemas import (
    CompanyIdentity,
    JurisdictionScope,
    RawSourceRecord,
    SourceType,
)


class SourceAdapter(ABC):
    """Contract every official-source or web adapter implements.

    Adapters are stateless apart from their HTTP client and must return typed
    `RawSourceRecord` instances. They never persist; persistence is the
    registry's job. They never extract structured facts; extraction is Phase 2.
    """

    source_type: SourceType
    jurisdiction: str

    @abstractmethod
    async def discover(
        self,
        identity: CompanyIdentity,
        scope: JurisdictionScope,
    ) -> list[RawSourceRecord]:
        """Return raw documents/payloads relevant to the given company.

        Implementations must be safe to call concurrently; failures should be
        surfaced as exceptions for the orchestrator to capture (not swallowed).
        """

    @property
    def name(self) -> str:
        return self.__class__.__name__
