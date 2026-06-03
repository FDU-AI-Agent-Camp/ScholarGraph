"""Business services — workflow and API call these facades, not BE modules directly."""

# Import from submodules directly (e.g. backend.services.paper_service) to avoid
# graph ↔ services circular imports at package load time.
