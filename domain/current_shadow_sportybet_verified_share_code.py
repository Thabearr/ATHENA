"""Canonical source-replay-verified anonymous share-code entry point.

The lower research transport module performs the provider network checks, but
this wrapper is the authoritative ATHENA shadow entry point: it accepts only a
builder-issued VerifiedResearchShadowPortfolio and replays every retained
current-history and PR252 mapping source before any semantic SportyBet network
resolution can occur.
"""

from __future__ import annotations

from pathlib import Path

from domain import current_shadow_sportybet_share_code as transport
from domain import current_shadow_sportybet_verified_package as package


class CurrentShadowVerifiedShareCodeError(ValueError):
    """Raised when the canonical research execution package fails source replay."""


def create_verified_current_shadow_sportybet_share_code(
    *,
    verified_portfolio: package.VerifiedResearchShadowPortfolio,
    output_dir: Path,
    delay_seconds: float = 0.25,
) -> transport.ResearchShadowShareCodeReceipt:
    """Re-prove exact sources, then run anonymous semantic/create/reload gates."""
    try:
        checked = package.verify_verified_research_shadow_portfolio(
            verified_portfolio
        )
    except package.CurrentShadowVerifiedPackageError as exc:
        raise CurrentShadowVerifiedShareCodeError(
            "verified research portfolio failed exact retained-source replay"
        ) from exc

    if checked.authority["production_selection"] is not False:
        raise CurrentShadowVerifiedShareCodeError(
            "verified research package acquired production selection authority"
        )
    try:
        return transport.create_current_shadow_sportybet_share_code(
            portfolio=checked.portfolio,
            source_decisions=checked.decisions,
            output_dir=output_dir,
            delay_seconds=delay_seconds,
        )
    except transport.CurrentShadowSportyBetShareCodeError as exc:
        raise CurrentShadowVerifiedShareCodeError(
            "verified research shadow share-code transport failed closed"
        ) from exc


__all__ = [
    "CurrentShadowVerifiedShareCodeError",
    "create_verified_current_shadow_sportybet_share_code",
]
