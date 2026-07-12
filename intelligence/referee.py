import logging

logger = logging.getLogger("athena.referee_engine")


class RefereeEngine:
    """
    Placeholder for referee-based upset risk.

    IMPORTANT: there is no real referee data source connected yet
    (no assignment API, no historical card/penalty stats). This
    intentionally returns a neutral "no signal" result rather than
    fabricating a volatility score from the fixture_id, which is
    what this file used to do (fixture_id % 10 <= 1).

    Once a real referee data feed is connected, replace `has_data`
    and the logic below with a real lookup.
    """

    def __init__(self):
        self.has_data = False  # flip to True once a real feed is wired in

    def check_referee_anomaly(self, fixture_id: int) -> dict:
        if not self.has_data:
            return {
                "has_data": False,
                "high_volatility": False,
                "reason": "no_referee_data_source_connected",
            }

        # Real logic goes here once we have a data source.
        return {"has_data": True, "high_volatility": False, "reason": "not_implemented"}
