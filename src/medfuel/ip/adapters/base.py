"""Base for IP source adapters.

IP adapters share the SourceAdapter contract (return RawSourceRecord)
so the existing DocumentRegistry can persist their output without
schema changes. They differ only in the source-type set they target.
"""

from __future__ import annotations

from medfuel.adapters.base import SourceAdapter
from medfuel.ip.models import IPSourceType
from medfuel.models.schemas import SourceType


def source_type_for(ip_source: IPSourceType) -> SourceType:
    """Map an IPSourceType onto the registry's SourceType enum.

    Both enums share string values for IP sources; this helper keeps
    the conversion in one place.
    """
    return SourceType(ip_source.value)


class IPSourceAdapter(SourceAdapter):
    """Marker subclass so the IP pipeline can pick adapters by isinstance.

    All IP adapters must set `ip_source_type`; the parent class's
    `source_type` is derived from it.
    """

    ip_source_type: IPSourceType

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        ip_src = getattr(cls, "ip_source_type", None)
        if ip_src is not None:
            cls.source_type = source_type_for(ip_src)
