from medfuel.adapters.base import SourceAdapter
from medfuel.adapters.clinicaltrials import ClinicalTrialsAdapter
from medfuel.adapters.company_web import CompanyWebAdapter
from medfuel.adapters.ema import EMAAdapter
from medfuel.adapters.fda import FDAAdapter
from medfuel.adapters.firecrawl import FirecrawlClient
from medfuel.adapters.mhra import MHRAAdapter
from medfuel.adapters.ncbi import NCBIAdapter
from medfuel.adapters.pmda import PMDAAdapter
from medfuel.adapters.sec import SECAdapter
from medfuel.adapters.uspto import USPTOAdapter

__all__ = [
    "ClinicalTrialsAdapter",
    "CompanyWebAdapter",
    "EMAAdapter",
    "FDAAdapter",
    "FirecrawlClient",
    "MHRAAdapter",
    "NCBIAdapter",
    "PMDAAdapter",
    "SECAdapter",
    "SourceAdapter",
    "USPTOAdapter",
]
