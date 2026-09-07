"""Reviewed user-facing date selection for Current Shadow research requests.

A caller may select any one through seven unique UTC fixture dates inside the
rolling window [today, today + 6 days].  The policy is date selection only; it
grants no source, model, pricing, selection, SportyBet execution, BET, or wager
authority.
"""
from __future__ import annotations

import datetime as dt
import re
from types import MappingProxyType
from typing import Any, Iterable


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_ROLLING_SEVEN_DAY_FIXTURE_REQUEST_V1"
MAX_SELECTED_DATES = 7
MAX_FORWARD_DAYS = 6
_DATE_RE = re.compile(r"^[0-9]{8}$", re.ASCII)

AUTHORITY = MappingProxyType(
    {
        "research_shadow_fixture_date_request": True,
        "source_acquisition": False,
        "production_model": False,
        "pricing": False,
        "selection": False,
        "sportybet_execution": False,
        "bet": False,
        "wager_placed": False,
    }
)


class CurrentShadowFixtureDateRequestError(ValueError):
    pass


def _utc_date(value: Any) -> dt.date:
    if type(value) is dt.datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise CurrentShadowFixtureDateRequestError("current time must be timezone-aware")
        return value.astimezone(dt.timezone.utc).date()
    if type(value) is dt.date:
        return value
    raise CurrentShadowFixtureDateRequestError("current date must be exact date/datetime")


def parse_fixture_dates_text(value: str) -> tuple[str, ...]:
    if type(value) is not str or not value or value != value.strip():
        raise CurrentShadowFixtureDateRequestError(
            "fixture dates must be comma-separated YYYYMMDD values"
        )
    parts = tuple(value.split(","))
    if not 1 <= len(parts) <= MAX_SELECTED_DATES or any(not part for part in parts):
        raise CurrentShadowFixtureDateRequestError("select between one and seven fixture dates")
    if len(set(parts)) != len(parts):
        raise CurrentShadowFixtureDateRequestError("fixture dates must be unique")
    parsed: list[tuple[dt.date, str]] = []
    for part in parts:
        if _DATE_RE.fullmatch(part) is None:
            raise CurrentShadowFixtureDateRequestError(
                "fixture dates must use exact YYYYMMDD format"
            )
        try:
            date = dt.datetime.strptime(part, "%Y%m%d").date()
        except ValueError as exc:
            raise CurrentShadowFixtureDateRequestError("fixture date is not a real UTC date") from exc
        parsed.append((date, part))
    parsed.sort()
    return tuple(part for _date, part in parsed)


def validate_fixture_dates(
    values: Iterable[str], *, current_utc: dt.datetime | dt.date
) -> tuple[str, ...]:
    items = tuple(values)
    if not 1 <= len(items) <= MAX_SELECTED_DATES or len(set(items)) != len(items):
        raise CurrentShadowFixtureDateRequestError(
            "select between one and seven unique fixture dates"
        )
    canonical = parse_fixture_dates_text(",".join(items))
    today = _utc_date(current_utc)
    latest = today + dt.timedelta(days=MAX_FORWARD_DAYS)
    for text in canonical:
        date = dt.datetime.strptime(text, "%Y%m%d").date()
        if date < today or date > latest:
            raise CurrentShadowFixtureDateRequestError(
                "fixture date is outside the rolling today-through-today+6 UTC window"
            )
    return canonical


def policy_summary() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "maximum_selected_dates": MAX_SELECTED_DATES,
        "maximum_forward_days": MAX_FORWARD_DAYS,
        "format": "YYYYMMDD",
        "authority": dict(AUTHORITY),
        "wager_placed": False,
    }


__all__ = [
    "AUTHORITY",
    "CurrentShadowFixtureDateRequestError",
    "MAX_FORWARD_DAYS",
    "MAX_SELECTED_DATES",
    "POLICY_ID",
    "SCHEMA_VERSION",
    "parse_fixture_dates_text",
    "policy_summary",
    "validate_fixture_dates",
]
