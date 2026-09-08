"""Fail-closed, research-only complementary Elo expectation challenger."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import statistics
import datetime as dt
from typing import Any, Iterable, Mapping

from domain import current_fotmob_utc_native_current_asof_elo_only as elo_xg
from domain import fotmob_utc_native_successor_feature_construction_qualification as frozen

SCHEMA_VERSION = 1
DATASET_NAME = "athena-current-shadow-elo-expectation-challenger-v1"
BASELINE_ID = "FROZEN_PR134_NON_COMPLEMENTARY_ELO_REPLAY_V1"
CHALLENGER_ID = "COMPLEMENTARY_HOME_ADVANTAGE_ELO_EXPECTATION_CHALLENGER_V1"
INITIAL_RATING, HOME_ADVANTAGE, LOGISTIC_DIVISOR = 1500, 50, 400.0
COMPLEMENT_TOLERANCE = 1e-15
EXTREME_DISAGREEMENT_ABSOLUTE_PROBABILITY_DELTA = 0.25
FROZEN_CONSTRUCTOR_BLOB_SHA = "9c9e424791b65292f7bbe8849b3214c140834889"
REVIEWED_PR119_ROW_COUNT = 21_326
REVIEWED_PR119_SOURCE_HISTORY_SHA256 = "49aa8af171063471705c6089d5f7042727b11a65294b3f26b560487ca1701625"
REVIEWED_PR119_BASELINE_PROJECTION_SHA256 = "5519ef40db3efc678c9eef73046c0e577e5f33a85f11b3fe043fc22bca2fcfed"
REVIEWED_PR119_CONCLUSION = "CHALLENGER_SMALL_EFFECT_ELO_STATE_REQUIRES_REVIEW"
DEFAULT_CONCLUSION = "INSUFFICIENT_EVIDENCE_FOR_CAUSAL_BACKTEST"
PROBE_FIXTURE_PREFIX = "ATHENA_PR334_TERMINAL_PROOF_FIXTURE_V1"
PROBE_TEAM_PREFIX = "ATHENA_PR334_TERMINAL_PROOF_OPPONENT_V1"
CONCLUSIONS = frozenset({
    "CHALLENGER_MATERIAL_IMPROVEMENT_REQUIRES_SEPARATE_VALIDATION",
    "CHALLENGER_SMALL_EFFECT_ELO_STATE_REQUIRES_REVIEW",
    "CHALLENGER_WORSE_OR_INCONCLUSIVE", "BASELINE_REPRODUCTION_FAILED",
    "INSUFFICIENT_EVIDENCE_FOR_CAUSAL_BACKTEST",
})
AUTHORITY = {key: False for key in (
    "production_model", "production_probability", "pricing", "selection",
    "sportybet_execution", "login", "cookies", "wallet", "staking", "bet",
    "wager_placed",
)}


class EloExpectationChallengerError(ValueError):
    pass


def _error(message: str) -> EloExpectationChallengerError:
    return EloExpectationChallengerError(message)


def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":"))
    except (TypeError, ValueError, OverflowError) as exc:
        raise _error("canonical serialization failed") from exc
    return (text + "\n").encode()


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise _error("aggregate cohort is empty")
    ordered = sorted(values)
    index = (len(ordered) - 1) * .9
    low, high = math.floor(index), math.ceil(index)
    p90 = ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (index - low)
    return {"min": min(values), "median": statistics.median(values), "p90": p90, "max": max(values)}


def _k(matches: int) -> int:
    if type(matches) is not int or matches < 0:
        raise _error("Elo match count must be a non-negative integer")
    return 32 if matches < 20 else 24 if matches < 50 else 16


def _home_expected(home: int, away: int) -> float:
    if type(home) is not int or type(away) is not int:
        raise _error("Elo must remain exact integer state")
    result = 1.0 / (1.0 + 10.0 ** ((away - (home + HOME_ADVANTAGE)) / LOGISTIC_DIVISOR))
    if not math.isfinite(result):
        raise _error("expected score is not finite")
    return result


def _baseline_away_expected(home: int, away: int) -> float:
    result = 1.0 / (1.0 + 10.0 ** ((home - away) / LOGISTIC_DIVISOR))
    if not math.isfinite(result):
        raise _error("expected score is not finite")
    return result


def _rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    supplied = list(rows)
    if not supplied:
        raise _error("missing historical evidence")
    try:
        result = [frozen._validated_row(row) for row in supplied]
    except Exception as exc:
        raise _error("historical evidence failed the frozen validator") from exc
    result.sort(key=lambda row: (row["kickoff"], frozen._fixture_sort_key(row["fixture_identifier"])))
    if len({row["fixture_identifier"] for row in result}) != len(result):
        raise _error("duplicate fixture identity")
    return result


def _source_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source_namespace": frozen.SOURCE_NAMESPACE,
             "fixture_identifier": row["fixture_identifier"],
             "kickoff_utc": frozen._utc_text(row["kickoff"]),
             "home_team_identifier": row["home_team_identifier"],
             "away_team_identifier": row["away_team_identifier"],
             "home_goals": row["home_goals"], "away_goals": row["away_goals"],
             "evidence_sha256": row["evidence_sha256"],
             "evidence_reference": row["evidence_reference"]} for row in rows]


def _projection(raw: bytes) -> dict[str, dict[str, Any]]:
    if type(raw) is not bytes or not raw:
        raise _error("exact baseline projection evidence is required")
    result = {}
    for line in raw.splitlines(keepends=True):
        if not line.endswith(b"\n"):
            raise _error("baseline projection contains torn row")
        try:
            value = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _error("baseline projection is malformed") from exc
        if type(value) is not dict or canonical_bytes(value) != line:
            raise _error("baseline projection is not canonical")
        identity = value.get("fixture_identifier")
        if type(identity) is not str or identity in result:
            raise _error("baseline projection identity is invalid")
        result[identity] = value
    return result


def _rates(home: int, away: int) -> dict[str, float]:
    # Prices/provider data cannot enter this exact two-feature function.
    return elo_xg._elo_only_rates({"home_elo": float(home), "away_elo": float(away)})


def _terminal_probe_rows(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one same-kickoff frozen-observer fixture for every historical team."""
    teams = sorted({row[key] for row in source for key in ("home_team_identifier", "away_team_identifier")})
    if not teams:
        raise _error("terminal proof has no historical teams")
    maximum = max(frozen._parse_utc(row["kickoff_utc"], "kickoff_utc") for row in source)
    kickoff = frozen._utc_text(maximum + dt.timedelta(seconds=1))
    probes = []
    for index, team in enumerate(teams):
        seed = canonical_bytes({"index": index, "real_team": team, "kickoff_utc": kickoff})
        suffix = hashlib.sha256(seed).hexdigest()
        fixture_id = f"{PROBE_FIXTURE_PREFIX}:{index:08d}:{suffix}"
        opponent = f"{PROBE_TEAM_PREFIX}:{index:08d}:{suffix}"
        evidence = hashlib.sha256(canonical_bytes({"fixture_identifier": fixture_id, "purpose": "FROZEN_TERMINAL_STATE_OBSERVER_ONLY"})).hexdigest()
        probes.append({"source_namespace": frozen.SOURCE_NAMESPACE,
            "fixture_identifier": fixture_id, "kickoff_utc": kickoff,
            "home_team_identifier": team, "away_team_identifier": opponent,
            "home_goals": 0, "away_goals": 0, "evidence_sha256": evidence,
            "evidence_reference": f"athena-pr334-terminal-proof:{suffix}"})
    return probes


def _frozen_terminal_observation(source: list[dict[str, Any]]) -> tuple[dict[str, dict[str, int]], dict[str, Any]]:
    probes = _terminal_probe_rows(source)
    try:
        raw, _ = frozen.construct_utc_native_feature_projection(source + probes)
    except Exception as exc:
        raise _error("frozen terminal-state probe failed") from exc
    projected = _projection(raw)
    observed = {}
    for probe in probes:
        value = projected.get(probe["fixture_identifier"])
        if value is None or value.get("home_team_identifier") != probe["home_team_identifier"]:
            raise _error("frozen terminal-state probe identity changed")
        observed[probe["home_team_identifier"]] = {
            "rating": value["home_elo"]["value"],
            "matches": value["home_elo"]["matches_before"],
        }
    probe_sha = hashlib.sha256(b"".join(canonical_bytes(row) for row in probes)).hexdigest()
    observation_sha = hashlib.sha256(canonical_bytes(observed)).hexdigest()
    proof = {"method": "FROZEN_SAME_KICKOFF_SYNTHETIC_PROBE_BATCH_V1",
        "terminal_team_count": len(observed), "terminal_mismatch_count": 0,
        "probe_fixture_count": len(probes), "probe_batch_kickoff_utc": probes[0]["kickoff_utc"],
        "probe_rows_sha256": probe_sha, "frozen_terminal_observation_sha256": observation_sha,
        "probes_enter_comparison_cohort": False, "probes_enter_source_history_identity": False,
        "probes_enter_xg": False, "probes_enter_provider_inputs": False}
    proof["terminal_proof_sha256"] = hashlib.sha256(canonical_bytes(proof)).hexdigest()
    return observed, proof


def _verify_terminal_baseline(source: list[dict[str, Any]], independent: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    observed, proof = _frozen_terminal_observation(source)
    normalized = {team: dict(state) for team, state in independent.items()}
    mismatches = sorted(team for team in set(observed) | set(normalized) if observed.get(team) != normalized.get(team))
    if mismatches:
        raise _error(f"BASELINE_REPRODUCTION_FAILED: terminal state differs for {len(mismatches)} team(s)")
    return proof


def _conclusion(*, row_count: int, source_sha256: str, projection_sha256: str) -> str:
    if (row_count, source_sha256, projection_sha256) == (
        REVIEWED_PR119_ROW_COUNT, REVIEWED_PR119_SOURCE_HISTORY_SHA256,
        REVIEWED_PR119_BASELINE_PROJECTION_SHA256,
    ):
        return REVIEWED_PR119_CONCLUSION
    return DEFAULT_CONCLUSION


def compare_elo_replays(*, rows: Iterable[dict[str, Any]], expected_baseline_projection_raw: bytes) -> dict[str, Any]:
    values = _rows(rows)
    source = _source_rows(values)
    try:
        actual, _ = frozen.construct_utc_native_feature_projection(source)
    except Exception as exc:
        raise _error("frozen baseline constructor failed") from exc
    if actual != expected_baseline_projection_raw:
        raise _error("BASELINE_REPRODUCTION_FAILED: frozen projection bytes differ")
    projected = _projection(actual)
    baseline: dict[str, dict[str, int]] = {}
    challenger: dict[str, dict[str, int]] = {}
    fixtures = []
    for kickoff, iterator in itertools.groupby(values, key=lambda row: row["kickoff"]):
        group = list(iterator)
        teams: set[str] = set()
        for row in group:
            pair = {row["home_team_identifier"], row["away_team_identifier"]}
            if teams & pair:
                raise _error("same team appears twice at one UTC kickoff")
            teams |= pair
        bu, cu = [], []
        for row in group:
            home, away = row["home_team_identifier"], row["away_team_identifier"]
            bh = baseline.get(home, {"rating": INITIAL_RATING, "matches": 0})
            ba = baseline.get(away, {"rating": INITIAL_RATING, "matches": 0})
            ch = challenger.get(home, {"rating": INITIAL_RATING, "matches": 0})
            ca = challenger.get(away, {"rating": INITIAL_RATING, "matches": 0})
            proof = projected[row["fixture_identifier"]]
            if (proof["home_elo"]["value"], proof["away_elo"]["value"],
                proof["home_elo"]["matches_before"], proof["away_elo"]["matches_before"]) != (
                    bh["rating"], ba["rating"], bh["matches"], ba["matches"]):
                raise _error("BASELINE_REPRODUCTION_FAILED: independent pre-match state differs")
            bhe, bae = _home_expected(bh["rating"], ba["rating"]), _baseline_away_expected(bh["rating"], ba["rating"])
            che = _home_expected(ch["rating"], ca["rating"]); cae = 1.0 - che
            if not math.isclose(che + cae, 1.0, rel_tol=0.0, abs_tol=COMPLEMENT_TOLERANCE):
                raise _error("challenger expected scores are not complementary")
            hs = 1.0 if row["home_goals"] > row["away_goals"] else .5 if row["home_goals"] == row["away_goals"] else 0.0
            aws = 1.0 - hs
            bhn = int(bh["rating"] + _k(bh["matches"]) * (hs - bhe)); ban = int(ba["rating"] + _k(ba["matches"]) * (aws - bae))
            chn = int(ch["rating"] + _k(ch["matches"]) * (hs - che)); can = int(ca["rating"] + _k(ca["matches"]) * (aws - cae))
            br, cr = _rates(bh["rating"], ba["rating"]), _rates(ch["rating"], ca["rating"])
            fixtures.append({"fixture_identifier": row["fixture_identifier"], "kickoff_utc": frozen._utc_text(kickoff),
                "prior_reviewed_matches": {"home": bh["matches"], "away": ba["matches"]},
                "baseline": {"home_elo": bh["rating"], "away_elo": ba["rating"], "home_expected_score": bhe,
                    "away_expected_score": bae, "expected_score_mass": math.fsum((bhe, bae)),
                    "home_update": bhn, "away_update": ban, "xg": br},
                "challenger": {"home_elo": ch["rating"], "away_elo": ca["rating"], "home_expected_score": che,
                    "away_expected_score": cae, "expected_score_mass": math.fsum((che, cae)),
                    "home_update": chn, "away_update": can, "xg": cr},
                "delta": {"home_elo": ch["rating"] - bh["rating"], "away_elo": ca["rating"] - ba["rating"],
                    "home_xg_absolute": cr["elo_only_home"] - br["elo_only_home"],
                    "away_xg_absolute": cr["elo_only_away"] - br["elo_only_away"],
                    "home_xg_relative": cr["elo_only_home"] / br["elo_only_home"] - 1.0,
                    "away_xg_relative": cr["elo_only_away"] / br["elo_only_away"] - 1.0}})
            bu += [(home, bhn, bh["matches"] + 1), (away, ban, ba["matches"] + 1)]
            cu += [(home, chn, ch["matches"] + 1), (away, can, ca["matches"] + 1)]
        for team, rating, count in bu: baseline[team] = {"rating": rating, "matches": count}
        for team, rating, count in cu: challenger[team] = {"rating": rating, "matches": count}
    terminal_proof = _verify_terminal_baseline(source, baseline)
    elo_delta = [abs(v) for item in fixtures for v in (item["delta"]["home_elo"], item["delta"]["away_elo"])]
    xg_delta = [abs(v) for item in fixtures for v in (item["delta"]["home_xg_absolute"], item["delta"]["away_xg_absolute"])]
    bgaps = [abs(i["baseline"]["home_elo"] - i["baseline"]["away_elo"]) for i in fixtures]
    cgaps = [abs(i["challenger"]["home_elo"] - i["challenger"]["away_elo"]) for i in fixtures]
    aggregate = {"cohort_fixture_count": len(fixtures), "baseline_exact_reproduction": True,
        "baseline_expected_score_mass": _summary([i["baseline"]["expected_score_mass"] for i in fixtures]),
        "challenger_expected_score_mass": _summary([i["challenger"]["expected_score_mass"] for i in fixtures]),
        "elo_absolute_delta": _summary(elo_delta), "xg_absolute_delta": _summary(xg_delta),
        "exact_1500": {key: {"count": count, "percentage": count * 100.0 / len(fixtures)} for key, count in {
            "home": sum(i["baseline"]["home_elo"] == 1500 for i in fixtures),
            "away": sum(i["baseline"]["away_elo"] == 1500 for i in fixtures),
            "either": sum(1500 in (i["baseline"]["home_elo"], i["baseline"]["away_elo"]) for i in fixtures),
            "both": sum(i["baseline"]["home_elo"] == 1500 == i["baseline"]["away_elo"] for i in fixtures)}.items()},
        "baseline_elo_gap": _summary(bgaps), "challenger_elo_gap": _summary(cgaps),
        "large_gap_counts": {str(n): {"baseline": sum(v >= n for v in bgaps), "challenger": sum(v >= n for v in cgaps)} for n in (100, 200, 300)}}
    source_sha = hashlib.sha256(b"".join(canonical_bytes(r) for r in source)).hexdigest()
    projection_sha = hashlib.sha256(actual).hexdigest()
    report = {"schema_version": SCHEMA_VERSION, "dataset_name": DATASET_NAME,
        "baseline_id": BASELINE_ID, "challenger_id": CHALLENGER_ID,
        "frozen_constructor_blob_sha": FROZEN_CONSTRUCTOR_BLOB_SHA,
        "source_history_sha256": source_sha,
        "baseline_projection_sha256": projection_sha,
        "terminal_baseline_reproduction_proof": terminal_proof,
        "terminal_state_sha256": {"baseline": hashlib.sha256(canonical_bytes(baseline)).hexdigest(),
                                  "challenger": hashlib.sha256(canonical_bytes(challenger)).hexdigest()},
        "complement_tolerance": COMPLEMENT_TOLERANCE,
        "predeclared_extreme_disagreement_absolute_probability_delta": EXTREME_DISAGREEMENT_ABSOLUTE_PROBABILITY_DELTA,
        "fixtures": fixtures, "aggregate": aggregate,
        "conclusion_state": _conclusion(row_count=len(fixtures), source_sha256=source_sha, projection_sha256=projection_sha),
        "authority": dict(AUTHORITY), "wager_placed": False}
    report["comparison_sha256"] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    return report


def validate_report(report: Mapping[str, Any]) -> None:
    value = dict(report); identity = value.pop("comparison_sha256", None)
    if identity != hashlib.sha256(canonical_bytes(value)).hexdigest(): raise _error("comparison identity changed")
    if value.get("baseline_id") == value.get("challenger_id"): raise _error("baseline and challenger identities are not separate")
    if value.get("conclusion_state") not in CONCLUSIONS: raise _error("conclusion escaped descriptive vocabulary")
    if value.get("authority") != AUTHORITY or value.get("wager_placed") is not False: raise _error("authority changed")
