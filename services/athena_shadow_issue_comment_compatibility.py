"""Pure retained comment syntax adapter; no dispatch or execution authority."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re

from domain import current_shadow_fixture_date_request as legacy
from domain.run_contracts import canonical_json_bytes
from services.athena_run_request_parser import CLI_TIMEZONE, parse_explicit_request

POLICY_ID = "ATHENA_SHADOW_ISSUE_COMMENT_COMPATIBILITY_V1"
SCOPE_GRAMMAR = r"/athena-shadow target=([0-9]+) scope=(today|three-day)"
EXPLICIT_DATES_GRAMMAR = r"/athena-shadow target=([0-9]+) dates=([0-9]{8}(?:,[0-9]{8}){0,6})"
REPRESENTABLE = "CANONICAL_REQUEST_EXACTLY_REPRESENTABLE"
UNREPRESENTABLE = "RETAINED_COMPATIBILITY_UNREPRESENTABLE_WITHOUT_DATE_SHIFT"
DISPOSITION = "EXPLICIT_RETAINED_THIN_SYNTAX_ADAPTER_NOT_MIGRATED"


@dataclass(frozen=True)
class CommentCompatibility:
    original_command: str
    grammar_kind: str
    target_legs: int
    legacy_fixture_scope: str
    legacy_fixture_dates: str
    legacy_utc_resolved_dates: tuple[str, ...]
    compatibility_status: str
    canonical_request_bytes: bytes | None
    canonical_request_sha256: str | None
    dispatch_authority: bool = False


def resolve_comment(command: str, *, now: datetime) -> CommentCompatibility:
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("comment clock must be timezone-aware")
    if type(command) is not str:
        raise ValueError("comment must be exact text")
    scope_match = re.fullmatch(SCOPE_GRAMMAR, command)
    dates_match = re.fullmatch(EXPLICIT_DATES_GRAMMAR, command)
    match = scope_match or dates_match
    if match is None:
        raise ValueError("comment does not match the reviewed command grammar")
    target = int(match.group(1))
    if not 1 <= target <= 50:
        raise ValueError("target must be an integer from 1 through 50")
    today = now.astimezone(timezone.utc).date()
    if scope_match is not None:
        kind, scope, text = "SCOPE", scope_match.group(2), ""
        dates = tuple((today + timedelta(days=i)).strftime("%Y%m%d")
                      for i in range(1 if scope == "today" else 3))
    else:
        kind, scope, text = "EXPLICIT_DATES", "today", dates_match.group(2)
        dates = legacy.parse_fixture_dates_text(text)
    dates = legacy.validate_fixture_dates(dates, current_utc=now)
    concrete = tuple(datetime.strptime(day, "%Y%m%d").date() for day in dates)
    local_today = now.astimezone(CLI_TIMEZONE).date()
    # Reject the mapping, not the retained UTC intent. Never repair or shift it.
    if any(not local_today <= day <= local_today + timedelta(days=6) for day in concrete):
        raw, digest, status = None, None, UNREPRESENTABLE
    else:
        request = parse_explicit_request(
            days=",".join(day.isoformat() for day in concrete), target_legs=target,
            bookie="sportybet", profile="shadow", create_share_code=True,
            target_total_odds=None, now=now,
        )
        raw = canonical_json_bytes(request)
        digest, status = hashlib.sha256(raw).hexdigest(), REPRESENTABLE
    return CommentCompatibility(command, kind, target, scope, text, dates, status, raw, digest)
