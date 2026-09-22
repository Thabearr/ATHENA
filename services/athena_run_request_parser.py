"""Pure parsing for the canonical ATHENA CLI request surface.

Relative dates intentionally resolve as Lagos calendar dates.  This module
does not perform I/O and returns only the existing immutable ``RunRequest``
contract; it is not an orchestration or decision authority.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from zoneinfo import ZoneInfo

from domain.run_contracts import RunContractError, RunRequest


CLI_TIMEZONE_ID = "Africa/Lagos"
CLI_TIMEZONE = ZoneInfo(CLI_TIMEZONE_ID)
_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", re.ASCII)
_DAY_TOKEN_PATTERN = r"(?:today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday|[0-9]{4}-[0-9]{2}-[0-9]{2})"
_SHORTHAND_SCOPE_RE = re.compile(
    rf"^(?P<start>{_DAY_TOKEN_PATTERN})(?:-(?P<end>{_DAY_TOKEN_PATTERN}))?$",
    re.ASCII,
)
_ACCA_TOKEN_RE = re.compile(r"^(?P<count>[1-9][0-9]*)acca$", re.ASCII)


class AthenaRunRequestParseError(ValueError):
    """Raised when CLI text cannot be resolved without ambiguity."""


def _local_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(CLI_TIMEZONE)
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise AthenaRunRequestParseError("now must be a timezone-aware datetime")
    try:
        return now.astimezone(CLI_TIMEZONE)
    except (OverflowError, TypeError, ValueError) as exc:
        raise AthenaRunRequestParseError("now is not a valid timezone-aware datetime") from exc


def _horizon(now: datetime) -> tuple[date, date]:
    today = now.date()
    return today, today + timedelta(days=6)


def _resolve_day_token(token: str, today: date, last_day: date) -> date:
    if type(token) is not str or not token or token != token.strip():
        raise AthenaRunRequestParseError("date token must be exact non-empty text")
    if token == "today":
        resolved = today
    elif token == "tomorrow":
        resolved = today + timedelta(days=1)
    elif token in _WEEKDAYS:
        resolved = today + timedelta(days=(_WEEKDAYS[token] - today.weekday()) % 7)
    elif _ISO_DATE_RE.fullmatch(token):
        try:
            resolved = date.fromisoformat(token)
        except ValueError as exc:
            raise AthenaRunRequestParseError(f"invalid ISO calendar date: {token}") from exc
        if resolved.isoformat() != token:
            raise AthenaRunRequestParseError(f"non-canonical ISO calendar date: {token}")
    else:
        raise AthenaRunRequestParseError(f"unsupported date token: {token}")
    if not today <= resolved <= last_day:
        raise AthenaRunRequestParseError("date is outside the local today-through-six-day horizon")
    return resolved


def _parse_days(days: str, now: datetime | None) -> tuple[date, ...]:
    if type(days) is not str:
        raise AthenaRunRequestParseError("days must be comma-separated text")
    # Whitespace around tokens is accepted as presentation whitespace, but
    # empty tokens, repeated tokens, and colliding resolutions fail closed.
    tokens = [item.strip() for item in days.split(",")]
    if not 1 <= len(tokens) <= 7:
        raise AthenaRunRequestParseError("select between one and seven days")
    if any(not token for token in tokens):
        raise AthenaRunRequestParseError("days contains an empty token")
    if len(set(tokens)) != len(tokens):
        raise AthenaRunRequestParseError("duplicate date token")
    local_now = _local_now(now)
    today, last_day = _horizon(local_now)
    resolved = tuple(_resolve_day_token(token, today, last_day) for token in tokens)
    if len(set(resolved)) != len(resolved):
        raise AthenaRunRequestParseError("distinct date tokens resolve to the same calendar date")
    return tuple(sorted(resolved))


def _parse_target_legs(value: int) -> int:
    if type(value) is not int or not 1 <= value <= 50:
        raise AthenaRunRequestParseError("target_legs must be an exact integer from 1 through 50")
    return value


def _parse_bookie(bookie: str) -> str:
    if type(bookie) is not str or bookie != "sportybet":
        raise AthenaRunRequestParseError("only the exact bookie 'sportybet' is supported")
    return bookie


def _profile_fields(profile: str) -> tuple[str, str, bool]:
    if profile == "main":
        return "MAIN", "main_application", False
    if profile == "shadow":
        return "SHADOW", "research_shadow", True
    raise AthenaRunRequestParseError("profile must be exactly 'main' or 'shadow'")


def _parse_target_total_odds(value: Decimal | str | None) -> Decimal | None:
    if value is None:
        return None
    if type(value) is Decimal:
        parsed = value
    elif type(value) is str and value and value == value.strip():
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise AthenaRunRequestParseError("target_total_odds must be a decimal value") from exc
    else:
        raise AthenaRunRequestParseError("target_total_odds must be Decimal, decimal text, or None")
    if not parsed.is_finite() or parsed <= 0:
        raise AthenaRunRequestParseError("target_total_odds must be a positive finite decimal")
    return parsed


def parse_explicit_request(
    *,
    days: str,
    target_legs: int,
    bookie: str = "sportybet",
    profile: str,
    target_total_odds: Decimal | str | None = None,
    now: datetime | None = None,
) -> RunRequest:
    """Resolve explicit CLI arguments to an exact immutable ``RunRequest``."""
    resolved_days = _parse_days(days, now)
    legs = _parse_target_legs(target_legs)
    selected_bookie = _parse_bookie(bookie)
    authority_profile, mode, share_code = _profile_fields(profile)
    objective = _parse_target_total_odds(target_total_odds)
    try:
        return RunRequest(
            dates=resolved_days,
            target_legs=legs,
            target_total_odds=objective,
            bookie=selected_bookie,
            mode=mode,
            authority_profile=authority_profile,
            create_share_code=share_code,
            place_wager=False,
        )
    except RunContractError as exc:
        raise AthenaRunRequestParseError(str(exc)) from exc


def parse_shorthand_request(
    *,
    date_scope: str,
    acca_token: str,
    bookie: str,
    now: datetime | None = None,
) -> RunRequest:
    """Parse ``<date-scope> <N>acca <bookie>`` into the same request contract."""
    match = _SHORTHAND_SCOPE_RE.fullmatch(date_scope) if type(date_scope) is str else None
    if match is None:
        raise AthenaRunRequestParseError("date scope must be one token or an inclusive A-B range")
    count_match = _ACCA_TOKEN_RE.fullmatch(acca_token) if type(acca_token) is str else None
    if count_match is None:
        raise AthenaRunRequestParseError("acca token must be an exact integer from 1 through 50 followed by 'acca'")
    target_legs = int(count_match.group("count"))
    _parse_target_legs(target_legs)
    selected_bookie = _parse_bookie(bookie)
    local_now = _local_now(now)
    today, last_day = _horizon(local_now)
    start = _resolve_day_token(match.group("start"), today, last_day)
    end_token = match.group("end")
    if end_token is None:
        resolved_days = (start,)
    else:
        end = _resolve_day_token(end_token, today, last_day)
        if end < start:
            raise AthenaRunRequestParseError("shorthand date range end precedes start; ranges do not wrap")
        resolved_days = tuple(start + timedelta(days=offset) for offset in range((end - start).days + 1))
        if not 1 <= len(resolved_days) <= 7:
            raise AthenaRunRequestParseError("shorthand range must contain one through seven dates")
    try:
        return RunRequest(
            dates=resolved_days,
            target_legs=target_legs,
            target_total_odds=None,
            bookie=selected_bookie,
            mode="research_shadow",
            authority_profile="SHADOW",
            create_share_code=True,
            place_wager=False,
        )
    except RunContractError as exc:
        raise AthenaRunRequestParseError(str(exc)) from exc


__all__ = [
    "AthenaRunRequestParseError",
    "CLI_TIMEZONE",
    "CLI_TIMEZONE_ID",
    "parse_explicit_request",
    "parse_shorthand_request",
]
