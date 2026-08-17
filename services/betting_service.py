from loguru import logger


BOOKMAKER_RESOLUTION_BLOCK_STATE = (
    "BLOCKED_UNTIL_REVIEWED_LIVE_BOOKMAKER_RESOLVER"
)
SLIP_VETTING_BLOCK_STATE = "BLOCKED_UNTIL_REVIEWED_LIVE_SLIP_VETTING"


class BettingService:
    """Resolve and vet bookmaker slips only through reviewed live integrations.

    The previous implementation returned fabricated fixtures, odds, ATHENA edges,
    and approval percentages for SportyBet and Stake. Those values could escape
    through the real API surface, so unsupported resolvers now fail closed.
    """

    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

    @staticmethod
    def _blocked_resolution(bookmaker: str, booking_code: str) -> dict:
        return {
            "success": False,
            "bookmaker": bookmaker,
            "code": booking_code,
            "state": BOOKMAKER_RESOLUTION_BLOCK_STATE,
            "legs": [],
            "athena_approval": None,
            "error": (
                f"{bookmaker} booking-code resolution is not yet backed by a "
                "reviewed live resolver. ATHENA will not fabricate slip data."
            ),
        }

    def resolve_sportybet(self, booking_code: str) -> dict:
        """Fail closed until the reviewed SportyBet live resolver is implemented."""
        logger.info("SportyBet booking-code resolution requested")
        return self._blocked_resolution("SportyBet", booking_code)

    def resolve_stake(self, booking_code: str) -> dict:
        """Fail closed until the reviewed Stake live resolver is implemented."""
        logger.info("Stake booking-code resolution requested")
        return self._blocked_resolution("Stake", booking_code)

    def vet_code(self, bookmaker: str, booking_code: str) -> dict:
        """Resolve and vet a booking code without synthetic approvals."""
        bookie = str(bookmaker or "").strip().lower()

        if bookie == "sportybet":
            slip_data = self.resolve_sportybet(booking_code)
        elif bookie == "stake":
            slip_data = self.resolve_stake(booking_code)
        else:
            return {
                "success": False,
                "bookmaker": bookmaker,
                "code": booking_code,
                "state": BOOKMAKER_RESOLUTION_BLOCK_STATE,
                "legs": [],
                "athena_approval": None,
                "error": (
                    f"A reviewed live booking-code resolver for {bookmaker} "
                    "is not implemented."
                ),
            }

        if not slip_data.get("success"):
            return slip_data

        # A resolver becoming available is not enough to authorize ATHENA
        # approval. Mapping, fixture identity, market equivalence, fresh pricing,
        # and the reviewed runtime decision chain must all be implemented first.
        return {
            "success": False,
            "bookmaker": slip_data.get("bookmaker", bookmaker),
            "code": booking_code,
            "state": SLIP_VETTING_BLOCK_STATE,
            "legs": [],
            "athena_approval": None,
            "error": (
                "Slip resolution succeeded, but reviewed ATHENA live slip "
                "vetting is not yet authorized."
            ),
        }

    def split_slip(self, slip_data: dict, split_count: int = 2) -> list:
        """Split only already-resolved real slip legs."""
        if not slip_data.get("success"):
            return []
        legs = slip_data.get("legs", [])
        if not legs:
            return []
        chunk_size = max(1, len(legs) // max(1, split_count))
        return [legs[i:i + chunk_size] for i in range(0, len(legs), chunk_size)]

    def merge_slips(self, slips: list[dict]) -> dict:
        """Merge only successful resolved slips into a de-duplicated ticket."""
        if not slips or any(not slip.get("success") for slip in slips):
            return {
                "success": False,
                "bookmaker": slips[0].get("bookmaker") if slips else "",
                "codes_merged": 0,
                "legs": [],
                "total_estimated_odds": 0.0,
                "state": BOOKMAKER_RESOLUTION_BLOCK_STATE,
            }

        merged_legs = []
        seen = set()
        for slip in slips:
            for leg in slip.get("legs", []):
                key = (
                    leg.get("fixture"),
                    leg.get("market"),
                    leg.get("selection"),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged_legs.append(leg)

        total_odds = 1.0
        for leg in merged_legs:
            odds = leg.get("odds")
            if isinstance(odds, (int, float)) and odds > 0:
                total_odds *= odds

        return {
            "success": True,
            "bookmaker": slips[0].get("bookmaker", ""),
            "codes_merged": len(slips),
            "legs": merged_legs,
            "total_estimated_odds": (
                round(total_odds, 2) if merged_legs else 0.0
            ),
        }
