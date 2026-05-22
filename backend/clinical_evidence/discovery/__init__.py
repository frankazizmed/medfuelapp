"""Discovery layer — fans out across public clinical/regulatory sources.

Each module exposes one async function: ``fetch(company: CompanyContext) ->
DiscoveryResult``. The orchestrator dedupes, persists, and returns the union.
"""
