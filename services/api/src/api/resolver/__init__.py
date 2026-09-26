"""The ONLY Bedrock call outside the LLM zone: objetivo (free text) -> strategy_id.

Real logic lands in Fase 4 of PLAN.md (4.4). Kept isolated in its own
module per CLAUDE.md so this boundary stays as obvious in the code as it
is in the design document. `services/api` must never gain any other
Bedrock use.
"""
