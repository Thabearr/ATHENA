"""Bookmaker export preparation without fabricated integrations.

ATHENA currently has no authenticated bookmaker integration. This adapter
validates and preserves slip legs, creates a deterministic *internal*
reference, and reports the integration as unavailable. It never manufactures
booking codes or share-bet URLs.
"""

import hashlib
import json
from typing import Any, Dict, List

from domain.markets import serialize_leg


INTEGRATION_UNAVAILABLE = "integration_unavailable"


class BookieAutomator:
    """Prepare an auditable export payload for a future real integration."""

    def _prepare_legs(self, legs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [serialize_leg(leg) for leg in legs]

    def generate_slip_reference(self, legs: List[Dict[str, Any]]) -> str:
        """Return a deterministic ATHENA-internal reference for these legs."""
        prepared_legs = self._prepare_legs(legs)
        canonical_json = json.dumps(
            prepared_legs,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return f"ATHENA-{digest[:12].upper()}"

    def prepare_export(
        self,
        bookmaker: str,
        acca_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validate a slip and report the unavailable bookmaker integration."""
        legs = acca_data.get("legs", [])
        if not isinstance(legs, list) or not legs:
            raise ValueError("No legs were provided for export preparation.")

        prepared_legs = self._prepare_legs(legs)
        slip_reference = self.generate_slip_reference(prepared_legs)
        normalized_bookmaker = str(bookmaker or "").strip().lower()

        return {
            "success": True,
            "integration_status": INTEGRATION_UNAVAILABLE,
            "bookmaker": normalized_bookmaker,
            "slip_reference": slip_reference,
            "bookmaker_code": None,
            "bookmaker_code_is_genuine": False,
            "message": (
                "Slip validated and assigned an internal ATHENA reference. "
                "No bookmaker slip was registered and no genuine bookmaker "
                "code was created."
            ),
            "legs": prepared_legs,
        }


__all__ = ["BookieAutomator", "INTEGRATION_UNAVAILABLE"]
