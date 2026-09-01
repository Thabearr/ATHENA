"""Reviewed exact team-name aliases for current SportyBet Shadow reconciliation.

These aliases are narrow evidence-backed identity bridges only. They never use
fuzzy matching, substring matching, token similarity, club-suffix stripping, or
home/away reversal. An alias is valid only for the exact source competition and
exact source/provider team-name pair recorded below; kickoff and competition
matching remain separate exact reconciliation requirements.

Evidence source: ATHENA current Shadow run 33523353650 on 2026-09-01,
artifact ``current-shadow-all-market-request`` with digest
``sha256:1f3610d5bb05838b6840ce1e5d4f3771a5176289b3ed117ea38f1d1eddb33803``.
The retained provider/FotMob evidence showed these deterministic naming variants.
"""
from __future__ import annotations


POLICY_ID = "ATHENA_CURRENT_SHADOW_EXACT_TEAM_ALIAS_REGISTRY_V1"
EVIDENCE_RUN_ID = 33523353650
EVIDENCE_ARTIFACT_SHA256 = (
    "1f3610d5bb05838b6840ce1e5d4f3771a5176289b3ed117ea38f1d1eddb33803"
)

# (exact FotMob competition, exact FotMob source team name, exact SportyBet name)
_EXACT_SOURCE_PROVIDER_ALIASES = frozenset(
    {
        ("Championship", "Portsmouth", "Portsmouth FC"),
        ("Saudi Pro League", "Al Hilal", "Al Hilal SFC"),
        ("Saudi Pro League", "Al Ahli", "Al Ahli Saudi FC"),
        ("Super League", "FC Zürich", "FC Zurich"),
        ("Super League", "Young Boys", "Young Boys Bern"),
    }
)


def exact_provider_team_alias_matches(
    *, competition: object, source_name: object, provider_name: object
) -> bool:
    """Return true only for one explicitly reviewed scoped alias triple."""

    if any(type(value) is not str for value in (competition, source_name, provider_name)):
        return False
    if any(not value or value != value.strip() for value in (competition, source_name, provider_name)):
        return False
    return (competition, source_name, provider_name) in _EXACT_SOURCE_PROVIDER_ALIASES


__all__ = [
    "EVIDENCE_ARTIFACT_SHA256",
    "EVIDENCE_RUN_ID",
    "POLICY_ID",
    "exact_provider_team_alias_matches",
]
