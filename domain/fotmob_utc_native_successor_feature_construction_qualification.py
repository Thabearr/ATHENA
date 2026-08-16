"""Execute the reviewed FotMob UTC-native feature-construction protocol offline.

The runner reuses the exact PR119 artifact re-execution path to obtain the
already-qualified 21,326 ordinary-FT rows, then constructs source-native
pre-match form, overall Elo and fatigue from timezone-aware UTC only. It does
not train/tune expected goals, calculate probabilities, inspect bookmaker data,
or authorize production/BET use.
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import itertools
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable

import domain.fotmob_utc_native_successor_feature_construction_protocol as pr134
import scripts.qualify_fotmob_historical_source_history_completeness_materialization as pr119_exec


QUALIFICATION_STATE = (
    "EXECUTED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION_MODEL_USE_UNREVIEWED"
)
QUALIFICATION_STATUS = "QUALIFIED_EXACT_PR119_UTC_NATIVE_FEATURE_PROJECTION"
NEXT_REQUIRED_BOUNDARY = (
    "PRE_REGISTER_REVIEWED_FOTMOB_UTC_NATIVE_EXPECTED_GOALS_MODEL_VALIDATION_PROTOCOL"
)

PR134_PROTOCOL_SHA256 = "b3cc9a8e5ca05f199b7e404fa8288074e77d76fa5f21224c5bddb48ca1aac411"
PR134_PROTOCOL_SIZE = 5_809
PR134_PROTOCOL_BLOB_SHA = "57cc133a7fb9daa76c5d5d8e9156903e583c6575"
PR119_EXECUTOR_BLOB_SHA = "2409676b4993a25024e2e8554e84e3525e7c5e6e"
EXPECTED_ROW_COUNT = 21_326
SOURCE_NAMESPACE = "fotmob_data_matches_reviewed_ordinary_ft_finished_score"
HISTORICAL_FRESHNESS_STATUS = "NOT_RECONSTRUCTIBLE_WITH_CURRENT_EVIDENCE"

SAFETY_KEYS = frozenset(
    {
        "bet_authorized",
        "calibration_for_production_authorized",
        "expected_goals_production_authorized",
        "expected_goals_transform_approved",
        "market_activation_authorized",
        "model_training_authorized",
        "pricing_authorized",
        "probability_adjustment_authorized",
        "probability_inference_authorized",
        "production_approval_authorized",
        "score_matrix_authorized",
        "selection_authorized",
        "successor_candidate_approved",
        "successor_live_inputs_qualified",
    }
)


class FotMobUTCNativeFeatureQualificationError(RuntimeError):
    """Raised when the exact offline feature qualification cannot be proven."""


def _error(message: str) -> FotMobUTCNativeFeatureQualificationError:
    return FotMobUTCNativeFeatureQualificationError(message)


def _canonical(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical serialization failed") from exc
    return (encoded + "\n").encode("utf-8")


def _git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise _error(f"{label} must be exact UTC Z text")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise _error(f"{label} is malformed") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise _error(f"{label} must be timezone-aware UTC")
    return parsed.astimezone(dt.timezone.utc)


def _utc_text(value: dt.datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0):
        raise _error("UTC output must remain timezone-aware")
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _exact_identifier(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise _error(f"{label} must be exact non-empty text")
    return value


def _fixture_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def _rating_state(state: dict[str, dict[str, int]], team: str) -> dict[str, int]:
    current = state.get(team)
    if current is None:
        return {"rating": 1500, "matches": 0}
    return dict(current)


def _k_factor(matches: int) -> int:
    if type(matches) is not int or matches < 0:
        raise _error("Elo match count must be a non-negative integer")
    if matches < 20:
        return 32
    if matches < 50:
        return 24
    return 16


def _form_value(history: list[tuple[dt.datetime, int, int]]) -> tuple[str, float | None]:
    recent = history[-5:]
    if not recent:
        return "MISSING", None
    points = 0
    for _, goals_for, goals_against in recent:
        if goals_for > goals_against:
            points += 3
        elif goals_for == goals_against:
            points += 1
    value = round(0.10 + ((points / (len(recent) * 3)) * 0.85), 3)
    return "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY", value


def _fatigue_value(
    target: dt.datetime,
    home_history: list[tuple[dt.datetime, int, int]],
    away_history: list[tuple[dt.datetime, int, int]],
) -> tuple[str, float | None, int | None, int | None, int | None]:
    if not home_history or not away_history:
        return "MISSING", None, None, None, None
    home_rest = (target - home_history[-1][0]).days
    away_rest = (target - away_history[-1][0]).days
    if home_rest < 0 or away_rest < 0:
        raise _error("strict-prior fatigue state cannot produce negative rest days")
    differential = home_rest - away_rest
    value = 0.30 if differential < -2 else 0.10 if differential < 0 else 0.0
    return (
        "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY",
        value,
        home_rest,
        away_rest,
        differential,
    )


def _validated_row(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error("PR119 projection row must be an object")
    required = {
        "source_namespace",
        "fixture_identifier",
        "kickoff_utc",
        "home_team_identifier",
        "away_team_identifier",
        "home_goals",
        "away_goals",
        "evidence_sha256",
        "evidence_reference",
    }
    missing = required.difference(value)
    if missing:
        raise _error(f"PR119 projection row missing fields: {sorted(missing)}")
    if value["source_namespace"] != SOURCE_NAMESPACE:
        raise _error("PR119 source namespace changed")
    fixture_id = _exact_identifier(value["fixture_identifier"], "fixture_identifier")
    home = _exact_identifier(value["home_team_identifier"], "home_team_identifier")
    away = _exact_identifier(value["away_team_identifier"], "away_team_identifier")
    if home == away:
        raise _error("fixture cannot use one team twice")
    home_goals = value["home_goals"]
    away_goals = value["away_goals"]
    if (
        type(home_goals) is not int
        or home_goals < 0
        or type(away_goals) is not int
        or away_goals < 0
    ):
        raise _error("goals must be exact non-negative integers")
    evidence_sha = value["evidence_sha256"]
    if (
        type(evidence_sha) is not str
        or len(evidence_sha) != 64
        or any(ch not in "0123456789abcdef" for ch in evidence_sha)
    ):
        raise _error("evidence SHA-256 is malformed")
    evidence_reference = _exact_identifier(
        value["evidence_reference"], "evidence_reference"
    )
    return {
        "source_namespace": SOURCE_NAMESPACE,
        "fixture_identifier": fixture_id,
        "kickoff": _parse_utc(value["kickoff_utc"], "kickoff_utc"),
        "home_team_identifier": home,
        "away_team_identifier": away,
        "home_goals": home_goals,
        "away_goals": away_goals,
        "evidence_sha256": evidence_sha,
        "evidence_reference": evidence_reference,
    }


def construct_utc_native_feature_projection(
    rows: Iterable[dict[str, Any]],
) -> tuple[bytes, dict[str, Any]]:
    """Construct deterministic UTC-native features from already-qualified rows."""
    validated = [_validated_row(row) for row in rows]
    validated.sort(
        key=lambda row: (
            row["kickoff"],
            _fixture_sort_key(row["fixture_identifier"]),
        )
    )
    fixture_ids: set[str] = set()
    for row in validated:
        fixture_id = row["fixture_identifier"]
        if fixture_id in fixture_ids:
            raise _error("duplicate source fixture identity")
        fixture_ids.add(fixture_id)

    histories: dict[str, list[tuple[dt.datetime, int, int]]] = collections.defaultdict(list)
    elo_state: dict[str, dict[str, int]] = {}
    output: list[dict[str, Any]] = []
    counters: collections.Counter[str] = collections.Counter()
    same_kickoff_groups = 0

    for kickoff, group_iter in itertools.groupby(validated, key=lambda row: row["kickoff"]):
        group = list(group_iter)
        if len(group) > 1:
            same_kickoff_groups += 1
        teams_in_group: set[str] = set()
        for row in group:
            for team in (row["home_team_identifier"], row["away_team_identifier"]):
                if team in teams_in_group:
                    raise _error("same source-scoped team appears twice at one UTC kickoff")
                teams_in_group.add(team)

        pending_updates: list[dict[str, Any]] = []
        for row in group:
            home = row["home_team_identifier"]
            away = row["away_team_identifier"]
            home_history = histories[home]
            away_history = histories[away]

            home_form_status, home_form = _form_value(home_history)
            away_form_status, away_form = _form_value(away_history)
            fatigue_status, fatigue, home_rest, away_rest, rest_diff = _fatigue_value(
                kickoff, home_history, away_history
            )

            home_rating = _rating_state(elo_state, home)
            away_rating = _rating_state(elo_state, away)
            home_elo_status = (
                "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION"
                if home_rating["matches"] == 0
                else "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"
            )
            away_elo_status = (
                "CONSTRUCTED_FROM_FROZEN_INITIAL_STATE_ASSUMPTION"
                if away_rating["matches"] == 0
                else "CONSTRUCTED_FROM_STRICTLY_PRIOR_UTC_HISTORY"
            )

            record = {
                "schema_version": 1,
                "source_namespace": SOURCE_NAMESPACE,
                "fixture_identifier": row["fixture_identifier"],
                "kickoff_utc": _utc_text(kickoff),
                "home_team_identifier": home,
                "away_team_identifier": away,
                "home_goals": row["home_goals"],
                "away_goals": row["away_goals"],
                "home_form": {"status": home_form_status, "value": home_form},
                "away_form": {"status": away_form_status, "value": away_form},
                "home_elo": {
                    "status": home_elo_status,
                    "value": home_rating["rating"],
                    "matches_before": home_rating["matches"],
                    "rating_component": "OVERALL",
                },
                "away_elo": {
                    "status": away_elo_status,
                    "value": away_rating["rating"],
                    "matches_before": away_rating["matches"],
                    "rating_component": "OVERALL",
                },
                "fatigue": {
                    "status": fatigue_status,
                    "value": fatigue,
                    "home_rest_days": home_rest,
                    "away_rest_days": away_rest,
                    "rest_day_differential": rest_diff,
                },
                "historical_live_data_freshness": {
                    "status": HISTORICAL_FRESHNESS_STATUS,
                    "value": None,
                },
                "evidence_sha256": row["evidence_sha256"],
                "evidence_reference": row["evidence_reference"],
            }
            output.append(record)
            counters[f"home_form:{home_form_status}"] += 1
            counters[f"away_form:{away_form_status}"] += 1
            counters[f"home_elo:{home_elo_status}"] += 1
            counters[f"away_elo:{away_elo_status}"] += 1
            counters[f"fatigue:{fatigue_status}"] += 1

            home_score = (
                1.0
                if row["home_goals"] > row["away_goals"]
                else 0.5
                if row["home_goals"] == row["away_goals"]
                else 0.0
            )
            away_score = 1.0 - home_score
            home_expected = 1.0 / (
                1.0
                + 10.0
                ** ((away_rating["rating"] - (home_rating["rating"] + 50)) / 400.0)
            )
            away_expected = 1.0 / (
                1.0
                + 10.0
                ** ((home_rating["rating"] - away_rating["rating"]) / 400.0)
            )
            pending_updates.append(
                {
                    "home": home,
                    "away": away,
                    "home_goals": row["home_goals"],
                    "away_goals": row["away_goals"],
                    "home_new_rating": int(
                        home_rating["rating"]
                        + _k_factor(home_rating["matches"])
                        * (home_score - home_expected)
                    ),
                    "away_new_rating": int(
                        away_rating["rating"]
                        + _k_factor(away_rating["matches"])
                        * (away_score - away_expected)
                    ),
                    "home_matches": home_rating["matches"] + 1,
                    "away_matches": away_rating["matches"] + 1,
                }
            )

        for update in pending_updates:
            home = update["home"]
            away = update["away"]
            elo_state[home] = {
                "rating": update["home_new_rating"],
                "matches": update["home_matches"],
            }
            elo_state[away] = {
                "rating": update["away_new_rating"],
                "matches": update["away_matches"],
            }
            histories[home].append(
                (kickoff, update["home_goals"], update["away_goals"])
            )
            histories[away].append(
                (kickoff, update["away_goals"], update["home_goals"])
            )

    projection = b"".join(_canonical(record) for record in output)
    summary = {
        "record_count": len(output),
        "same_kickoff_group_count": same_kickoff_groups,
        "feature_status_counts": dict(sorted(counters.items())),
        "unique_fixture_count": len(fixture_ids),
        "unique_team_count": len(histories),
    }
    return projection, summary


def _verify_upstream() -> None:
    pr134.build_fotmob_utc_native_successor_feature_construction_protocol()
    raw = pr134.canonical_fotmob_utc_native_successor_feature_construction_protocol_bytes()
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        PR134_PROTOCOL_SHA256,
        PR134_PROTOCOL_SIZE,
    ):
        raise _error("PR134 protocol identity changed")
    if _git_blob_sha(Path(pr134.__file__)) != PR134_PROTOCOL_BLOB_SHA:
        raise _error("PR134 protocol implementation blob changed")
    if pr134.NEXT_REQUIRED_BOUNDARY != (
        "EXECUTE_REVIEWED_FOTMOB_UTC_NATIVE_SUCCESSOR_FEATURE_CONSTRUCTION_QUALIFICATION"
    ):
        raise _error("PR134 next boundary changed")
    if _git_blob_sha(Path(pr119_exec.__file__)) != PR119_EXECUTOR_BLOB_SHA:
        raise _error("PR119 executor implementation changed")


def build_qualification(
    artifact: Path,
    *,
    projection_output: Path | None = None,
) -> dict[str, Any]:
    """Re-execute PR119 and build the exact UTC-native feature projection."""
    _verify_upstream()
    artifact = Path(artifact)
    if not artifact.exists():
        raise _error("preserved FotMob campaign artifact path does not exist")

    with tempfile.TemporaryDirectory(prefix="athena-utc-native-") as temp:
        pr119_projection = Path(temp) / "pr119-materialized.ndjson"
        pr119_receipt = pr119_exec.build_receipt(
            artifact,
            projection_output=pr119_projection,
        )
        pr119_receipt_raw = _canonical(pr119_receipt)
        if (hashlib.sha256(pr119_receipt_raw).hexdigest(), len(pr119_receipt_raw)) != (
            pr134.PR119_RECEIPT_SHA256,
            pr134.PR119_RECEIPT_SIZE,
        ):
            raise _error("exact PR119 artifact re-execution changed")

        raw = pr119_projection.read_bytes()
        if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
            pr134.PR119_MATERIALIZATION_PROJECTION_SHA256,
            pr134.PR119_MATERIALIZATION_PROJECTION_SIZE,
        ):
            raise _error("PR119 materialization projection changed")
        lines = raw.splitlines(keepends=True)
        if len(lines) != EXPECTED_ROW_COUNT:
            raise _error("PR119 materialized row count changed")
        rows: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise _error("PR119 materialization row is malformed") from exc
            if not isinstance(value, dict) or line != _canonical(value):
                raise _error("PR119 materialization row is not canonical JSON")
            rows.append(value)

    projection, summary = construct_utc_native_feature_projection(rows)
    if summary["record_count"] != EXPECTED_ROW_COUNT:
        raise _error("UTC-native feature projection row count changed")
    if projection_output is not None:
        projection_output = Path(projection_output)
        projection_output.parent.mkdir(parents=True, exist_ok=True)
        projection_output.write_bytes(projection)

    projection_sha = hashlib.sha256(projection).hexdigest()
    receipt = {
        "schema_version": 1,
        "qualification_state": QUALIFICATION_STATE,
        "qualification_status": QUALIFICATION_STATUS,
        "protocol_sha256": PR134_PROTOCOL_SHA256,
        "protocol_size_bytes": PR134_PROTOCOL_SIZE,
        "upstream": {
            "pr119_receipt_sha256": pr134.PR119_RECEIPT_SHA256,
            "pr119_materialization_projection_sha256": (
                pr134.PR119_MATERIALIZATION_PROJECTION_SHA256
            ),
            "preserved_campaign_artifact_id": pr134.PRESERVED_CAMPAIGN_ARTIFACT_ID,
            "preserved_campaign_artifact_sha256": (
                pr134.PRESERVED_CAMPAIGN_ARTIFACT_SHA256
            ),
        },
        "time_basis": {
            "coordinate": "STATUS_UTCTIME_AWARE_UTC",
            "timezone_conversion_used": False,
            "source_local_parity_claimed": False,
        },
        "projection": {
            "sha256": projection_sha,
            "size_bytes": len(projection),
            **summary,
        },
        "historical_live_data_freshness": {
            "status": HISTORICAL_FRESHNESS_STATUS,
            "numeric_value_produced": False,
            "training_feature_authorized": False,
        },
        "next_required_boundary": NEXT_REQUIRED_BOUNDARY,
        "safety": {key: False for key in sorted(SAFETY_KEYS)},
    }
    return receipt


def canonical_qualification_receipt_bytes(receipt: dict[str, Any]) -> bytes:
    return _canonical(receipt)


__all__ = [
    "HISTORICAL_FRESHNESS_STATUS",
    "NEXT_REQUIRED_BOUNDARY",
    "QUALIFICATION_STATE",
    "QUALIFICATION_STATUS",
    "SAFETY_KEYS",
    "FotMobUTCNativeFeatureQualificationError",
    "build_qualification",
    "canonical_qualification_receipt_bytes",
    "construct_utc_native_feature_projection",
]
