"""Research-only broad FotMob history state for Current Shadow xG coverage.

The frozen PR119/PR149 history and fresh-holdout contracts remain unchanged.
This module consumes the exact preserved PR119 source-campaign artifact, verifies
its immutable outer/cache identities through the reviewed PR117 adapter helpers,
and derives a separate Shadow-only UTC history state from ordinary full-time
fixtures that are byte-semantically stable across each day's two preserved
captures.

It never guesses a team, fills missing history with neutral values, mutates the
frozen holdout ledger, or grants production/pricing/BET authority.  The only
purpose is to provide a provenance-bound research fallback when the narrower
frozen PR119 projection cannot construct current-as-of form/fatigue inputs.
"""
from __future__ import annotations

import collections
import dataclasses
import datetime as dt
import hashlib
import itertools
import json
import os
from pathlib import Path
import tempfile
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from domain import fotmob_utc_native_successor_feature_construction_qualification as utc_features
from domain import fotmob_utc_native_expected_goals_fresh_holdout as fresh
from scripts import qualify_fotmob_historical_source_history_adapter as pr117


SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-paired-fotmob-history-v1"
POLICY_ID = "ATHENA_CURRENT_SHADOW_EXACT_PAIRED_FOTMOB_HISTORY_RESEARCH_V1"
ARTIFACT_ENV = "ATHENA_CURRENT_SHADOW_PAIRED_HISTORY_ARTIFACT"
ARTIFACT_ID = pr117.ARTIFACT_ID
ARTIFACT_SHA256 = pr117.ARTIFACT_SHA256
ARTIFACT_SIZE = pr117.ARTIFACT_SIZE
CACHE_SHA256 = pr117.CACHE_SHA256
CACHE_SIZE = pr117.CACHE_SIZE

_AUTHORITY = MappingProxyType({
    "research_shadow_history_fallback": True,
    "production_model": False,
    "production_probability": False,
    "pricing": False,
    "selection": False,
    "sportybet_execution": False,
    "login": False,
    "cookies": False,
    "wallet": False,
    "staking": False,
    "bet": False,
    "wager_placed": False,
})


class CurrentShadowPairedHistoryError(ValueError):
    pass


def _error(message: str) -> CurrentShadowPairedHistoryError:
    return CurrentShadowPairedHistoryError(message)


def _canonical(value: Any) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                           separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("paired history canonical serialization failed") from exc


def _utc_text(value: dt.datetime) -> str:
    if type(value) is not dt.datetime or value.tzinfo is None or value.utcoffset() is None:
        raise _error("paired history timestamp must be timezone-aware")
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


@dataclasses.dataclass(frozen=True)
class TeamHistoryState:
    rating: int
    matches: int
    recent: tuple[tuple[dt.datetime, int, int], ...]

    def __post_init__(self) -> None:
        if type(self.rating) is not int or type(self.matches) is not int or self.matches < 0:
            raise _error("paired team Elo state is invalid")
        if type(self.recent) is not tuple or len(self.recent) > 5:
            raise _error("paired team recent history is invalid")
        previous: dt.datetime | None = None
        copied = []
        for kickoff, goals_for, goals_against in self.recent:
            if type(kickoff) is not dt.datetime or kickoff.tzinfo is None or kickoff.utcoffset() is None:
                raise _error("paired team history kickoff is invalid")
            kickoff = kickoff.astimezone(dt.timezone.utc)
            if previous is not None and kickoff < previous:
                raise _error("paired team recent history is not chronological")
            if type(goals_for) is not int or goals_for < 0 or type(goals_against) is not int or goals_against < 0:
                raise _error("paired team recent score is invalid")
            previous = kickoff
            copied.append((kickoff, goals_for, goals_against))
        object.__setattr__(self, "recent", tuple(copied))

    def to_dict(self) -> dict[str, Any]:
        return {
            "rating": self.rating,
            "matches": self.matches,
            "recent": [[_utc_text(k), gf, ga] for k, gf, ga in self.recent],
        }


@dataclasses.dataclass(frozen=True)
class PairedHistoryState:
    stable_fixture_count: int
    omitted_conflict_fixture_count: int
    cutoff_utc: dt.datetime
    teams: Mapping[int, TeamHistoryState]
    state_sha256: str
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        if type(self.stable_fixture_count) is not int or self.stable_fixture_count < 1:
            raise _error("paired history must contain stable fixtures")
        if type(self.omitted_conflict_fixture_count) is not int or self.omitted_conflict_fixture_count < 0:
            raise _error("paired history conflict count is invalid")
        if type(self.cutoff_utc) is not dt.datetime or self.cutoff_utc.tzinfo is None or self.cutoff_utc.utcoffset() is None:
            raise _error("paired history cutoff is invalid")
        cutoff = self.cutoff_utc.astimezone(dt.timezone.utc)
        teams = dict(self.teams)
        if not teams or any(type(key) is not int or key < 1 or type(value) is not TeamHistoryState for key, value in teams.items()):
            raise _error("paired history team state is invalid")
        if type(self.state_sha256) is not str or len(self.state_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.state_sha256):
            raise _error("paired history state SHA-256 is invalid")
        if dict(self.authority) != dict(_AUTHORITY):
            raise _error("paired history authority changed")
        payload = _state_payload(
            stable_fixture_count=self.stable_fixture_count,
            omitted_conflict_fixture_count=self.omitted_conflict_fixture_count,
            cutoff_utc=cutoff,
            teams=teams,
        )
        if hashlib.sha256(_canonical(payload)).hexdigest() != self.state_sha256:
            raise _error("paired history state identity mismatch")
        object.__setattr__(self, "cutoff_utc", cutoff)
        object.__setattr__(self, "teams", MappingProxyType(teams))
        object.__setattr__(self, "authority", MappingProxyType(dict(_AUTHORITY)))


@dataclasses.dataclass(frozen=True)
class PairedCurrentFeatureResult:
    features: Mapping[str, float]
    missing_feature_ids: tuple[str, ...]
    history_identity_sha256: str
    history_row_count: int
    feature_projection_sha256: str
    authority: Mapping[str, bool]

    def __post_init__(self) -> None:
        features = dict(self.features)
        missing = tuple(self.missing_feature_ids)
        if tuple(sorted(set(missing))) != missing:
            raise _error("paired current missing features must be sorted unique")
        if missing:
            if set(features).difference(fresh._FEATURE_IDS):
                raise _error("paired current partial features escaped reviewed IDs")
        elif set(features) != set(fresh._FEATURE_IDS):
            raise _error("paired current complete feature set changed")
        for value in features.values():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise _error("paired current feature is not numeric")
        for digest in (self.history_identity_sha256, self.feature_projection_sha256):
            if type(digest) is not str or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise _error("paired current digest is invalid")
        if type(self.history_row_count) is not int or self.history_row_count < 0:
            raise _error("paired current history row count is invalid")
        if dict(self.authority) != dict(_AUTHORITY):
            raise _error("paired current authority changed")
        object.__setattr__(self, "features", MappingProxyType(features))
        object.__setattr__(self, "missing_feature_ids", missing)
        object.__setattr__(self, "authority", MappingProxyType(dict(_AUTHORITY)))


_state_cache: PairedHistoryState | None = None
_state_cache_path: tuple[str, int, int] | None = None


def _state_payload(*, stable_fixture_count: int, omitted_conflict_fixture_count: int,
                   cutoff_utc: dt.datetime, teams: Mapping[int, TeamHistoryState]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_name": DATASET_NAME,
        "policy_id": POLICY_ID,
        "source_artifact": {
            "artifact_id": ARTIFACT_ID,
            "artifact_sha256": ARTIFACT_SHA256,
            "artifact_size": ARTIFACT_SIZE,
            "cache_sha256": CACHE_SHA256,
            "cache_size": CACHE_SIZE,
        },
        "stable_fixture_count": stable_fixture_count,
        "omitted_conflict_fixture_count": omitted_conflict_fixture_count,
        "cutoff_utc": _utc_text(cutoff_utc),
        "teams": {str(key): teams[key].to_dict() for key in sorted(teams)},
        "authority": dict(_AUTHORITY),
    }


def _ordinary_index(payload: Any, request_date: str) -> dict[int, tuple[Any, ...]]:
    if type(payload) is not dict or type(payload.get("leagues")) is not list:
        raise _error("paired campaign payload shape changed")
    result: dict[int, tuple[Any, ...]] = {}
    for league in payload["leagues"]:
        if type(league) is not dict or type(league.get("matches")) is not list:
            continue
        for match in league["matches"]:
            if type(match) is not dict or not pr117.is_ordinary_ft(match):
                continue
            status, home, away = match.get("status"), match.get("home"), match.get("away")
            fixture_id = match.get("id")
            if type(status) is not dict or type(home) is not dict or type(away) is not dict:
                continue
            if type(fixture_id) is not int or fixture_id < 1:
                continue
            home_id, away_id = home.get("id"), away.get("id")
            if type(home_id) is not int or home_id < 1 or type(away_id) is not int or away_id < 1 or home_id == away_id:
                continue
            kickoff = pr117.parse_utc(status.get("utcTime"))
            if kickoff.strftime("%Y%m%d") != request_date:
                continue
            row = (
                fixture_id,
                kickoff,
                home_id,
                away_id,
                home.get("score"),
                away.get("score"),
                match.get("leagueId"),
                status.get("finished"),
                status.get("started"),
                status.get("cancelled"),
                status.get("awarded", "ABSENT"),
                status.get("reason"),
            )
            prior = result.get(fixture_id)
            if prior is None:
                result[fixture_id] = row
            elif prior != row:
                result.pop(fixture_id, None)
    return result


def _k_factor(matches: int) -> int:
    return 32 if matches < 20 else 24 if matches < 50 else 16


def _apply_group(
    teams: dict[int, TeamHistoryState], rows: Sequence[tuple[int, dt.datetime, int, int, int, int]],
) -> int:
    counts: collections.Counter[int] = collections.Counter()
    for _fixture, _kickoff, home, away, _hg, _ag in rows:
        counts[home] += 1
        counts[away] += 1
    safe = [row for row in rows if counts[row[2]] == 1 and counts[row[3]] == 1]
    omitted = len(rows) - len(safe)
    updates: list[tuple[int, int, TeamHistoryState, TeamHistoryState]] = []
    for _fixture, kickoff, home, away, home_goals, away_goals in safe:
        hs = teams.get(home, TeamHistoryState(1500, 0, ()))
        aws = teams.get(away, TeamHistoryState(1500, 0, ()))
        home_score = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
        away_score = 1.0 - home_score
        home_expected = 1.0 / (1.0 + 10.0 ** ((aws.rating - (hs.rating + 50)) / 400.0))
        away_expected = 1.0 / (1.0 + 10.0 ** ((hs.rating - aws.rating) / 400.0))
        home_new = int(hs.rating + _k_factor(hs.matches) * (home_score - home_expected))
        away_new = int(aws.rating + _k_factor(aws.matches) * (away_score - away_expected))
        home_recent = (hs.recent + ((kickoff, home_goals, away_goals),))[-5:]
        away_recent = (aws.recent + ((kickoff, away_goals, home_goals),))[-5:]
        updates.append((home, away,
                        TeamHistoryState(home_new, hs.matches + 1, home_recent),
                        TeamHistoryState(away_new, aws.matches + 1, away_recent)))
    for home, away, hs, aws in updates:
        teams[home] = hs
        teams[away] = aws
    return omitted


def build_paired_history_state(artifact_path: Path) -> PairedHistoryState:
    """Verify the frozen campaign and build exact paired ordinary-FT team state."""
    global _state_cache, _state_cache_path
    path = Path(artifact_path)
    try:
        stat = path.stat()
    except OSError as exc:
        raise _error("paired history artifact is unavailable") from exc
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    if _state_cache is not None and _state_cache_path == key:
        return _state_cache

    teams: dict[int, TeamHistoryState] = {}
    stable_count = 0
    omitted = 0
    cutoff: dt.datetime | None = None
    with tempfile.TemporaryDirectory(prefix="athena-current-shadow-paired-history-") as temp:
        try:
            captures = pr117.safe_extract_cache(path, Path(temp))
        except Exception as exc:
            raise _error("paired history artifact identity/replay verification failed") from exc
        for request_date in pr117.required_dates():
            try:
                pair = pr117.load_pair(captures / request_date, request_date)
            except Exception as exc:
                raise _error(f"paired history capture verification failed for {request_date}") from exc
            first = _ordinary_index(pair[0][4], request_date)
            second = _ordinary_index(pair[1][4], request_date)
            rows: list[tuple[int, dt.datetime, int, int, int, int]] = []
            for fixture_id in sorted(set(first).intersection(second)):
                if first[fixture_id] != second[fixture_id]:
                    continue
                fixture, kickoff, home, away, hg, ag, *_rest = first[fixture_id]
                if type(hg) is not int or type(ag) is not int:
                    continue
                rows.append((fixture, kickoff, home, away, hg, ag))
            rows.sort(key=lambda row: (row[1], row[0]))
            for kickoff, group in itertools.groupby(rows, key=lambda row: row[1]):
                group_rows = list(group)
                group_omitted = _apply_group(teams, group_rows)
                omitted += group_omitted
                stable_count += len(group_rows) - group_omitted
                if len(group_rows) > group_omitted:
                    cutoff = kickoff if cutoff is None or kickoff > cutoff else cutoff
    if cutoff is None or stable_count < 1:
        raise _error("paired history campaign produced no stable ordinary fixtures")
    payload = _state_payload(
        stable_fixture_count=stable_count,
        omitted_conflict_fixture_count=omitted,
        cutoff_utc=cutoff,
        teams=teams,
    )
    state = PairedHistoryState(
        stable_fixture_count=stable_count,
        omitted_conflict_fixture_count=omitted,
        cutoff_utc=cutoff,
        teams=teams,
        state_sha256=hashlib.sha256(_canonical(payload)).hexdigest(),
        authority=_AUTHORITY,
    )
    _state_cache = state
    _state_cache_path = key
    return state


def _copy_teams(state: PairedHistoryState) -> dict[int, TeamHistoryState]:
    return {team: dataclasses.replace(value) for team, value in state.teams.items()}


def _tail_rows(prefix: Iterable[fresh.FreshHistoryResult], *, cutoff: dt.datetime) -> list[tuple[int, dt.datetime, int, int, int, int]]:
    result = []
    for row in prefix:
        if type(row) is not fresh.FreshHistoryResult:
            raise _error("paired history tail row type changed")
        if row.kickoff_utc <= cutoff:
            continue
        result.append((int(row.fixture_identifier), row.kickoff_utc, row.home_team_id,
                       row.away_team_id, row.home_goals, row.away_goals))
    result.sort(key=lambda row: (row[1], row[0]))
    return result


def build_current_features_from_paired_history(
    *,
    history_prefix: Sequence[fresh.FreshHistoryResult],
    selected_capture: fresh.QualifiedCaptureFixture,
    artifact_path: Path | None = None,
) -> PairedCurrentFeatureResult:
    """Derive current target features from paired campaign plus reviewed fresh tail."""
    if type(selected_capture) is not fresh.QualifiedCaptureFixture:
        raise _error("selected_capture must be exact QualifiedCaptureFixture")
    path = artifact_path
    if path is None:
        raw = os.environ.get(ARTIFACT_ENV, "")
        if not raw:
            raise _error(f"{ARTIFACT_ENV} is not configured")
        path = Path(raw)
    state = build_paired_history_state(Path(path))
    teams = _copy_teams(state)
    tail = _tail_rows(history_prefix, cutoff=state.cutoff_utc)
    omitted_tail = 0
    for _kickoff, group in itertools.groupby(tail, key=lambda row: row[1]):
        group_rows = list(group)
        group_omitted = _apply_group(teams, group_rows)
        if group_omitted:
            raise _error("reviewed fresh tail contains same-kickoff team conflict")
        omitted_tail += group_omitted
    home = teams.get(selected_capture.home_team_id)
    away = teams.get(selected_capture.away_team_id)
    values: dict[str, float] = {}
    missing: list[str] = []
    if home is None:
        missing.extend(("home_elo", "home_form", "fatigue"))
    else:
        values["home_elo"] = float(home.rating)
        status, value = utc_features._form_value(list(home.recent))
        if status == "MISSING" or value is None:
            missing.append("home_form")
        else:
            values["home_form"] = float(value)
    if away is None:
        missing.extend(("away_elo", "away_form", "fatigue"))
    else:
        values["away_elo"] = float(away.rating)
        status, value = utc_features._form_value(list(away.recent))
        if status == "MISSING" or value is None:
            missing.append("away_form")
        else:
            values["away_form"] = float(value)
    if home is not None and away is not None:
        status, value, _home_rest, _away_rest, _diff = utc_features._fatigue_value(
            selected_capture.kickoff_utc, list(home.recent), list(away.recent)
        )
        if status == "MISSING" or value is None:
            missing.append("fatigue")
        else:
            values["fatigue"] = float(value)
    missing_tuple = tuple(sorted(set(missing)))
    history_payload = {
        "paired_state_sha256": state.state_sha256,
        "paired_stable_fixture_count": state.stable_fixture_count,
        "paired_omitted_conflict_fixture_count": state.omitted_conflict_fixture_count,
        "paired_cutoff_utc": _utc_text(state.cutoff_utc),
        "reviewed_tail": [
            [fixture, _utc_text(kickoff), home_id, away_id, hg, ag]
            for fixture, kickoff, home_id, away_id, hg, ag in tail
        ],
        "reviewed_tail_omitted_conflict_count": omitted_tail,
    }
    feature_payload = {
        "policy_id": POLICY_ID,
        "fixture_id": selected_capture.fixture_id,
        "kickoff_utc": _utc_text(selected_capture.kickoff_utc),
        "home_team_id": selected_capture.home_team_id,
        "away_team_id": selected_capture.away_team_id,
        "features": values,
        "missing_feature_ids": list(missing_tuple),
        "history_identity_sha256": hashlib.sha256(_canonical(history_payload)).hexdigest(),
        "authority": dict(_AUTHORITY),
    }
    return PairedCurrentFeatureResult(
        features=values,
        missing_feature_ids=missing_tuple,
        history_identity_sha256=feature_payload["history_identity_sha256"],
        history_row_count=state.stable_fixture_count + len(tail),
        feature_projection_sha256=hashlib.sha256(_canonical(feature_payload)).hexdigest(),
        authority=_AUTHORITY,
    )


__all__ = [
    "ARTIFACT_ENV", "ARTIFACT_ID", "ARTIFACT_SHA256", "ARTIFACT_SIZE",
    "CACHE_SHA256", "CACHE_SIZE", "DATASET_NAME", "POLICY_ID", "SCHEMA_VERSION",
    "CurrentShadowPairedHistoryError", "PairedCurrentFeatureResult", "PairedHistoryState",
    "TeamHistoryState", "build_current_features_from_paired_history", "build_paired_history_state",
]
