"""Clinical Evidence Intelligence Engine — self-contained MedFuel island.

The host MedFuel app integrates this island by mounting one router and one
React component. The island owns its own routes, schemas, DB tables (ce_*),
config (CE_*), and pipeline. It shares only the host's company contract.
"""

from clinical_evidence.router import router

__all__ = ["router"]
__version__ = "0.1.0"
