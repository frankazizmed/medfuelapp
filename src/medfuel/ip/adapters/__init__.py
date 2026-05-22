from medfuel.ip.adapters.base import IPSourceAdapter
from medfuel.ip.adapters.epo import EPOAdapter
from medfuel.ip.adapters.google_patents import GooglePatentsAdapter
from medfuel.ip.adapters.litigation import LitigationAdapter
from medfuel.ip.adapters.patentsview import PatentsViewAdapter
from medfuel.ip.adapters.ptab import PTABAdapter
from medfuel.ip.adapters.uspto_assignment import USPTOAssignmentAdapter

__all__ = [
    "EPOAdapter",
    "GooglePatentsAdapter",
    "IPSourceAdapter",
    "LitigationAdapter",
    "PTABAdapter",
    "PatentsViewAdapter",
    "USPTOAssignmentAdapter",
]
