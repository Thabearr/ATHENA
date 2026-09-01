"""Stable-ID fixture reconciliation for ATHENA's research-only current Shadow lane.

Names may bootstrap identity, but durable matching uses source/provider-native IDs.
Full UTC kickoff, home/away orientation and one-to-one identity remain exact.
No fuzzy matching, suffix stripping, reversal or time tolerance is authorized.

New evidence-backed bindings can be persisted between Shadow runs. Persisted state
contains only stable IDs plus exact source/provider evidence provenance; it grants
no model, pricing, selection, SportyBet execution, wallet, stake or wager authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from domain import current_shadow_fixture_identity_aliases as aliases

SCHEMA_VERSION = 1
STATE_SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_STABLE_SOURCE_PROVIDER_IDENTITY_V2"
MATCHING_BASIS = (
    "EXACT_FULL_UTC_HOME_AWAY_STABLE_FOTMOB_PROVIDER_NATIVE_IDS_"
    "PERSISTED_EVIDENCE_BOUND_EXACT_SHORT_LONG_OR_REVIEWED_ALIAS_BOOTSTRAP_"
    "NO_FUZZY_NO_SUFFIX_NO_REVERSAL_NO_TIME_TOLERANCE"
)
EVIDENCE_BASIS = (
    "CURRENT_SHADOW_RUN38_RETAINED_RAW_EVIDENCE_ARTIFACT_SHA256_"
    "3ff8371b67cf4b197cdf03b5215dfd52ad45ecbfa6a65f12d7dc00a1169420f8"
)
STATE_FILENAME = "current-shadow-fixture-identity-v2-state.json"

_COMPETITOR_RE = re.compile(r"^sr:competitor:[1-9][0-9]*$", re.ASCII)
_CATEGORY_RE = re.compile(r"^sr:category:.+$", re.ASCII)
_TOURNAMENT_RE = re.compile(r"^sr:(?:tournament|simple_tournament):.+$", re.ASCII)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)

TEAM_IDENTITY_SEEDS = (
    (1773,"sr:competitor:2918"),(7730,"sr:competitor:2446"),(7881,"sr:competitor:2688"),
    (7896,"sr:competitor:2443"),(7943,"sr:competitor:2793"),(7978,"sr:competitor:4860"),
    (8071,"sr:competitor:1291"),(8113,"sr:competitor:1289"),(8127,"sr:competitor:1783"),
    (8283,"sr:competitor:23"),(8284,"sr:competitor:2357"),(8344,"sr:competitor:61"),
    (8346,"sr:competitor:72"),(8391,"sr:competitor:1284"),(8451,"sr:competitor:47"),
    (8467,"sr:competitor:2348"),(8483,"sr:competitor:67"),(8485,"sr:competitor:2355"),
    (8529,"sr:competitor:2719"),(8540,"sr:competitor:2715"),(8548,"sr:competitor:2351"),
    (8560,"sr:competitor:2824"),(8571,"sr:competitor:4858"),(8596,"sr:competitor:2363"),
    (8597,"sr:competitor:2347"),(8600,"sr:competitor:2695"),(8635,"sr:competitor:2900"),
    (8639,"sr:competitor:1643"),(8659,"sr:competitor:8"),(9775,"sr:competitor:2581"),
    (9777,"sr:competitor:2448"),(9792,"sr:competitor:134"),(9800,"sr:competitor:2359"),
    (9802,"sr:competitor:1759"),(9823,"sr:competitor:2672"),(9824,"sr:competitor:2463"),
    (9860,"sr:competitor:2353"),(9876,"sr:competitor:2701"),(9889,"sr:competitor:2770"),
    (9891,"sr:competitor:2801"),(9910,"sr:competitor:2821"),(9925,"sr:competitor:2352"),
    (9927,"sr:competitor:2346"),(9931,"sr:competitor:2501"),(9938,"sr:competitor:2349"),
    (9941,"sr:competitor:1681"),(9956,"sr:competitor:2449"),(9991,"sr:competitor:2903"),
    (9997,"sr:competitor:2895"),(10007,"sr:competitor:10"),(10172,"sr:competitor:1"),
    (10179,"sr:competitor:2452"),(10190,"sr:competitor:2442"),(10191,"sr:competitor:2454"),
    (10199,"sr:competitor:2453"),(10202,"sr:competitor:1292"),(10251,"sr:competitor:2354"),
    (101919,"sr:competitor:56027"),(158319,"sr:competitor:23957"),(550433,"sr:competitor:167228"),
    (582749,"sr:competitor:168094"),(1523706,"sr:competitor:386360"),
    (1699505,"sr:competitor:529781"),(1787233,"sr:competitor:168082"),
)

COMPETITION_IDENTITY_SEEDS = (
    ("BEL",40,"sr:category:33","sr:tournament:38"),("DEN",46,"sr:category:8","sr:tournament:39"),
    ("ENG",48,"sr:category:1","sr:tournament:18"),("ENG",108,"sr:category:1","sr:tournament:24"),
    ("ESP",87,"sr:category:32","sr:tournament:8"),("FRA",53,"sr:category:7","sr:tournament:34"),
    ("GER",209,"sr:category:30","sr:tournament:217"),("ITA",141,"sr:category:31","sr:tournament:328"),
    ("KSA",536,"sr:category:310","sr:tournament:955"),("SCO",64,"sr:category:22","sr:tournament:36"),
    ("SUI",69,"sr:category:25","sr:tournament:215"),("SWE",67,"sr:category:9","sr:tournament:40"),
)


class CurrentShadowFixtureIdentityStateError(ValueError):
    """Raised when persisted Shadow identity state is invalid or conflicting."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _validate_seeds() -> None:
    if tuple(sorted(TEAM_IDENTITY_SEEDS)) != TEAM_IDENTITY_SEEDS:
        raise RuntimeError("team identity seeds must be sorted")
    if len({x[0] for x in TEAM_IDENTITY_SEEDS}) != len(TEAM_IDENTITY_SEEDS):
        raise RuntimeError("duplicate FotMob team seed")
    if len({x[1] for x in TEAM_IDENTITY_SEEDS}) != len(TEAM_IDENTITY_SEEDS):
        raise RuntimeError("duplicate provider competitor seed")
    if any(type(x[0]) is not int or x[0] <= 0 or _COMPETITOR_RE.fullmatch(x[1]) is None for x in TEAM_IDENTITY_SEEDS):
        raise RuntimeError("invalid team identity seed")
    source = {(x[0],x[1]) for x in COMPETITION_IDENTITY_SEEDS}
    provider = {(x[2],x[3]) for x in COMPETITION_IDENTITY_SEEDS}
    if len(source) != len(COMPETITION_IDENTITY_SEEDS) or len(provider) != len(COMPETITION_IDENTITY_SEEDS):
        raise RuntimeError("competition seeds must be one-to-one")
    if any(_CATEGORY_RE.fullmatch(x[2]) is None or _TOURNAMENT_RE.fullmatch(x[3]) is None for x in COMPETITION_IDENTITY_SEEDS):
        raise RuntimeError("invalid competition identity seed")


_validate_seeds()

_fotmob: dict[str, dict[str, Any]] = {}
_provider: dict[str, dict[str, Any]] = {}
_team_forward: dict[int, str] = {}
_team_reverse: dict[str, int] = {}
_comp_forward: dict[tuple[str, int], tuple[str, str]] = {}
_comp_reverse: dict[tuple[str, str], tuple[str, int]] = {}
_evidence_records: list[dict[str, Any]] = []
_state_path: Path | None = None


def reset_runtime_evidence() -> None:
    _fotmob.clear()
    _provider.clear()
    _team_forward.clear()
    _team_reverse.clear()
    _comp_forward.clear()
    _comp_reverse.clear()
    _evidence_records.clear()
    for source_id, provider_id in TEAM_IDENTITY_SEEDS:
        _team_forward[source_id] = provider_id
        _team_reverse[provider_id] = source_id
    for ccode, primary, category, tournament in COMPETITION_IDENTITY_SEEDS:
        _comp_forward[(ccode, primary)] = (category, tournament)
        _comp_reverse[(category, tournament)] = (ccode, primary)


reset_runtime_evidence()


def _utc_text(value: Any) -> datetime | None:
    if type(value) is not str or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _provider_kickoff(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        return None


def observe_fotmob_payload(raw: bytes) -> None:
    if type(raw) is not bytes or not raw:
        return
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    payload_sha256 = hashlib.sha256(raw).hexdigest()
    leagues = payload.get("leagues") if type(payload) is dict else None
    if type(leagues) is not list:
        return
    for league in leagues:
        if type(league) is not dict or type(league.get("matches")) is not list:
            continue
        ccode, primary, comp = league.get("ccode"), league.get("primaryId"), league.get("name")
        if type(ccode) is not str or type(primary) is not int or type(comp) is not str:
            continue
        for match in league["matches"]:
            if type(match) is not dict or type(match.get("id")) is not int:
                continue
            home, away, status = match.get("home"), match.get("away"), match.get("status")
            if type(home) is not dict or type(away) is not dict or type(status) is not dict:
                continue
            kickoff = _utc_text(status.get("utcTime"))
            vals = (
                home.get("id"), home.get("name"), home.get("longName"),
                away.get("id"), away.get("name"), away.get("longName"),
            )
            if (
                kickoff is None
                or type(vals[0]) is not int
                or type(vals[3]) is not int
                or any(type(v) is not str for v in (vals[1], vals[2], vals[4], vals[5]))
            ):
                continue
            key = str(match["id"])
            row = {
                "ccode": ccode,
                "primary": primary,
                "competition": comp,
                "kickoff": kickoff,
                "home_id": vals[0],
                "home": vals[1],
                "home_long": vals[2],
                "away_id": vals[3],
                "away": vals[4],
                "away_long": vals[5],
                "payload_sha256": payload_sha256,
            }
            prior = _fotmob.get(key)
            if prior is None:
                _fotmob[key] = row
            elif prior != row:
                _fotmob.pop(key, None)


def observe_fotmob_captures(captures: Iterable[Any]) -> None:
    for entry in captures:
        if type(entry) is tuple and len(entry) == 2 and type(entry[0]) is bytes:
            observe_fotmob_payload(entry[0])


def _walk(root: Any):
    stack = [root]
    while stack:
        value = stack.pop()
        if type(value) is dict:
            yield value
            stack.extend(value.values())
        elif type(value) is list:
            stack.extend(value)


def observe_provider_payload(raw: bytes) -> None:
    if type(raw) is not bytes or not raw:
        return
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return
    payload_sha256 = hashlib.sha256(raw).hexdigest()
    for value in _walk(payload):
        event_id = value.get("eventId")
        if type(event_id) is not str or _EVENT_RE.fullmatch(event_id) is None:
            continue
        hi, ai = value.get("homeTeamId"), value.get("awayTeamId")
        hn, an = value.get("homeTeamName"), value.get("awayTeamName")
        sport = value.get("sport")
        if (
            type(hi) is not str
            or _COMPETITOR_RE.fullmatch(hi) is None
            or type(ai) is not str
            or _COMPETITOR_RE.fullmatch(ai) is None
        ):
            continue
        if type(hn) is not str or type(an) is not str or type(sport) is not dict:
            continue
        category = sport.get("category")
        if type(category) is not dict or type(category.get("tournament")) is not dict:
            continue
        tournament = category["tournament"]
        ci, ti, comp = category.get("id"), tournament.get("id"), tournament.get("name")
        kickoff = _provider_kickoff(value.get("estimateStartTime"))
        if (
            type(ci) is not str
            or _CATEGORY_RE.fullmatch(ci) is None
            or type(ti) is not str
            or _TOURNAMENT_RE.fullmatch(ti) is None
            or type(comp) is not str
            or kickoff is None
        ):
            continue
        row = {
            "category": ci,
            "tournament": ti,
            "competition": comp,
            "kickoff": kickoff,
            "home_id": hi,
            "home": hn,
            "away_id": ai,
            "away": an,
            "payload_sha256": payload_sha256,
        }
        prior = _provider.get(event_id)
        if prior is None:
            _provider[event_id] = row
        elif prior != row:
            _provider.pop(event_id, None)


def observe_provider_directory(directory: Any) -> None:
    try:
        root = Path(directory) / "tournaments"
    except TypeError:
        return
    if not root.is_dir():
        return
    for path in sorted(root.glob("*.json")):
        try:
            observe_provider_payload(path.read_bytes())
        except OSError:
            continue


def _bind_team(source_id: int, provider_id: str) -> bool:
    a, b = _team_forward.get(source_id), _team_reverse.get(provider_id)
    if a not in (None, provider_id) or b not in (None, source_id):
        return False
    _team_forward[source_id] = provider_id
    _team_reverse[provider_id] = source_id
    return True


def _bind_comp(source_key: tuple[str, int], provider_key: tuple[str, str]) -> bool:
    a, b = _comp_forward.get(source_key), _comp_reverse.get(provider_key)
    if a not in (None, provider_key) or b not in (None, source_key):
        return False
    _comp_forward[source_key] = provider_key
    _comp_reverse[provider_key] = source_key
    return True


def _snapshot_bindings() -> tuple[
    dict[int, str],
    dict[str, int],
    dict[tuple[str, int], tuple[str, str]],
    dict[tuple[str, str], tuple[str, int]],
]:
    return (
        dict(_team_forward),
        dict(_team_reverse),
        dict(_comp_forward),
        dict(_comp_reverse),
    )


def _restore_bindings(snapshot: tuple[Any, Any, Any, Any]) -> None:
    team_forward, team_reverse, comp_forward, comp_reverse = snapshot
    _team_forward.clear(); _team_forward.update(team_forward)
    _team_reverse.clear(); _team_reverse.update(team_reverse)
    _comp_forward.clear(); _comp_forward.update(comp_forward)
    _comp_reverse.clear(); _comp_reverse.update(comp_reverse)


def _competition_matches(source: dict[str, Any], provider: dict[str, Any], reviewed_name: str) -> bool:
    sk = (source["ccode"], source["primary"])
    pk = (provider["category"], provider["tournament"])
    bound = _comp_forward.get(sk)
    if bound is not None:
        return bound == pk
    if pk in _comp_reverse:
        return False
    return (provider["competition"] in {reviewed_name, source["competition"]}) and _bind_comp(sk, pk)


def _team_matches(
    *,
    competition: str,
    source_id: int,
    short: str,
    long: str,
    provider_id: str,
    provider_name: str,
) -> bool:
    bound = _team_forward.get(source_id)
    if bound is not None:
        return bound == provider_id
    if provider_id in _team_reverse:
        return False
    exact = provider_name == short or provider_name == long
    reviewed = aliases.team_identity_matches(
        competition=competition,
        fotmob_name=short,
        sportybet_name=provider_name,
    )
    return (exact or reviewed) and _bind_team(source_id, provider_id)


def _learned_team_rows() -> list[list[Any]]:
    seeds = dict(TEAM_IDENTITY_SEEDS)
    return [
        [source_id, provider_id]
        for source_id, provider_id in sorted(_team_forward.items())
        if seeds.get(source_id) != provider_id
    ]


def _learned_comp_rows() -> list[list[Any]]:
    seeds = {(a, b): (c, d) for a, b, c, d in COMPETITION_IDENTITY_SEEDS}
    return [
        [source_key[0], source_key[1], provider_key[0], provider_key[1]]
        for source_key, provider_key in sorted(_comp_forward.items())
        if seeds.get(source_key) != provider_key
    ]


def _evidence_supports_team(source_id: int, provider_id: str) -> bool:
    for record in _evidence_records:
        for side in ("home", "away"):
            if (
                record.get(f"{side}_source_team_id") == source_id
                and record.get(f"{side}_provider_competitor_id") == provider_id
            ):
                return True
    return False


def _evidence_supports_comp(row: list[Any]) -> bool:
    ccode, primary, category, tournament = row
    return any(
        record.get("source_ccode") == ccode
        and record.get("source_primary_competition_id") == primary
        and record.get("provider_category_id") == category
        and record.get("provider_tournament_id") == tournament
        for record in _evidence_records
    )


def _state_payload() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "matching_basis": MATCHING_BASIS,
        "seed_registry_sha256": REGISTRY_SHA256,
        "learned_team_identities": _learned_team_rows(),
        "learned_competition_identities": _learned_comp_rows(),
        "evidence_records": sorted(_evidence_records, key=lambda row: _canonical(row)),
        "authority": {
            "research_shadow_fixture_reconciliation": True,
            "production_model": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "staking": False,
            "bet": False,
            "wager_placed": False,
        },
    }


def _state_document() -> dict[str, Any]:
    payload = _state_payload()
    return {
        "payload": payload,
        "state_sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
    }


def _persist_state() -> None:
    if _state_path is None:
        return
    document = _state_document()
    _state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _state_path.with_name(_state_path.name + ".tmp")
    temporary.write_bytes(_canonical(document) + b"\n")
    temporary.replace(_state_path)


def _validate_loaded_payload(payload: Any) -> None:
    if type(payload) is not dict:
        raise CurrentShadowFixtureIdentityStateError("identity state payload must be an object")
    if payload.get("schema_version") != STATE_SCHEMA_VERSION:
        raise CurrentShadowFixtureIdentityStateError("identity state schema drifted")
    if payload.get("policy_id") != POLICY_ID or payload.get("matching_basis") != MATCHING_BASIS:
        raise CurrentShadowFixtureIdentityStateError("identity state policy drifted")
    if payload.get("seed_registry_sha256") != REGISTRY_SHA256:
        raise CurrentShadowFixtureIdentityStateError("identity state seed registry drifted")
    if type(payload.get("learned_team_identities")) is not list:
        raise CurrentShadowFixtureIdentityStateError("identity state team mappings missing")
    if type(payload.get("learned_competition_identities")) is not list:
        raise CurrentShadowFixtureIdentityStateError("identity state competition mappings missing")
    if type(payload.get("evidence_records")) is not list:
        raise CurrentShadowFixtureIdentityStateError("identity state evidence records missing")


def configure_persistent_state(path: Any | None) -> None:
    global _state_path
    _state_path = None if path in (None, "") else Path(path)
    if _state_path is None or not _state_path.exists():
        return
    try:
        document = json.loads(_state_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CurrentShadowFixtureIdentityStateError("identity state cannot be read exactly") from exc
    if type(document) is not dict or type(document.get("state_sha256")) is not str:
        raise CurrentShadowFixtureIdentityStateError("identity state document is invalid")
    payload = document.get("payload")
    _validate_loaded_payload(payload)
    actual = hashlib.sha256(_canonical(payload)).hexdigest()
    if document["state_sha256"] != actual or _SHA_RE.fullmatch(actual) is None:
        raise CurrentShadowFixtureIdentityStateError("identity state hash mismatch")

    _evidence_records[:] = list(payload["evidence_records"])
    team_rows = payload["learned_team_identities"]
    comp_rows = payload["learned_competition_identities"]
    for row in team_rows:
        if (
            type(row) is not list
            or len(row) != 2
            or type(row[0]) is not int
            or row[0] <= 0
            or type(row[1]) is not str
            or _COMPETITOR_RE.fullmatch(row[1]) is None
            or not _evidence_supports_team(row[0], row[1])
            or not _bind_team(row[0], row[1])
        ):
            raise CurrentShadowFixtureIdentityStateError("identity state team mapping conflicts or lacks evidence")
    for row in comp_rows:
        if (
            type(row) is not list
            or len(row) != 4
            or type(row[0]) is not str
            or type(row[1]) is not int
            or type(row[2]) is not str
            or _CATEGORY_RE.fullmatch(row[2]) is None
            or type(row[3]) is not str
            or _TOURNAMENT_RE.fullmatch(row[3]) is None
            or not _evidence_supports_comp(row)
            or not _bind_comp((row[0], row[1]), (row[2], row[3]))
        ):
            raise CurrentShadowFixtureIdentityStateError("identity state competition mapping conflicts or lacks evidence")


def _new_evidence_record(
    *,
    source_fixture_identifier: str,
    provider_event_id: str,
    source: dict[str, Any],
    provider: dict[str, Any],
) -> dict[str, Any]:
    return {
        "source_fixture_identifier": source_fixture_identifier,
        "provider_event_id": provider_event_id,
        "kickoff_utc": source["kickoff"].isoformat().replace("+00:00", "Z"),
        "source_payload_sha256": source["payload_sha256"],
        "provider_payload_sha256": provider["payload_sha256"],
        "source_ccode": source["ccode"],
        "source_primary_competition_id": source["primary"],
        "provider_category_id": provider["category"],
        "provider_tournament_id": provider["tournament"],
        "home_source_team_id": source["home_id"],
        "home_provider_competitor_id": provider["home_id"],
        "away_source_team_id": source["away_id"],
        "away_provider_competitor_id": provider["away_id"],
        "source_competition_name": source["competition"],
        "provider_competition_name": provider["competition"],
        "source_home_name": source["home"],
        "source_home_long_name": source["home_long"],
        "provider_home_name": provider["home"],
        "source_away_name": source["away"],
        "source_away_long_name": source["away_long"],
        "provider_away_name": provider["away"],
    }


def match_event(event: Any, reviewed_rows: Sequence[Any]) -> tuple[Any, ...]:
    event_id = getattr(event, "event_id", None)
    provider = _provider.get(event_id) if type(event_id) is str else None
    if provider is None:
        return aliases.match_event(event, reviewed_rows)
    try:
        kickoff = getattr(event, "kickoff_utc").astimezone(timezone.utc)
    except Exception:
        return ()
    if (
        provider["kickoff"] != kickoff
        or provider["home"] != getattr(event, "home_team_name", None)
        or provider["away"] != getattr(event, "away_team_name", None)
    ):
        return ()

    base_bindings = _snapshot_bindings()
    successful: list[tuple[Any, tuple[Any, Any, Any, Any], dict[str, Any]]] = []
    for row in reviewed_rows:
        _restore_bindings(base_bindings)
        source_identifier = str(getattr(row, "source_fixture_identifier", ""))
        source = _fotmob.get(source_identifier)
        if source is None:
            continue
        try:
            row_kickoff = getattr(row, "kickoff").astimezone(timezone.utc)
        except Exception:
            continue
        if row_kickoff != kickoff or source["kickoff"] != kickoff:
            continue
        reviewed_comp = str(getattr(row, "competition", ""))
        if not _competition_matches(source, provider, reviewed_comp):
            continue
        home = _team_matches(
            competition=reviewed_comp,
            source_id=source["home_id"],
            short=source["home"],
            long=source["home_long"],
            provider_id=provider["home_id"],
            provider_name=provider["home"],
        )
        away = _team_matches(
            competition=reviewed_comp,
            source_id=source["away_id"],
            short=source["away"],
            long=source["away_long"],
            provider_id=provider["away_id"],
            provider_name=provider["away"],
        )
        if home and away:
            successful.append((
                row,
                _snapshot_bindings(),
                _new_evidence_record(
                    source_fixture_identifier=source_identifier,
                    provider_event_id=event_id,
                    source=source,
                    provider=provider,
                ),
            ))

    _restore_bindings(base_bindings)
    if len(successful) == 1:
        row, bindings, evidence = successful[0]
        _restore_bindings(bindings)
        if _learned_team_rows() or _learned_comp_rows():
            if evidence not in _evidence_records:
                _evidence_records.append(evidence)
            _persist_state()
        return (row,)
    return tuple(item[0] for item in successful)


def registry_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "matching_basis": MATCHING_BASIS,
        "evidence_basis": EVIDENCE_BASIS,
        "state_filename": STATE_FILENAME,
        "team_identity_seeds": [list(x) for x in TEAM_IDENTITY_SEEDS],
        "competition_identity_seeds": [list(x) for x in COMPETITION_IDENTITY_SEEDS],
        "legacy_alias_registry_sha256": aliases.REGISTRY_SHA256,
        "authority": {
            "research_shadow_fixture_reconciliation": True,
            "persistent_identity_learning": True,
            "production_model": False,
            "pricing": False,
            "selection": False,
            "sportybet_execution": False,
            "login": False,
            "cookies": False,
            "wallet": False,
            "staking": False,
            "bet": False,
            "wager_placed": False,
        },
    }


def registry_sha256() -> str:
    return hashlib.sha256(_canonical(registry_payload())).hexdigest()


REGISTRY_SHA256 = registry_sha256()

__all__ = [
    "COMPETITION_IDENTITY_SEEDS",
    "CurrentShadowFixtureIdentityStateError",
    "EVIDENCE_BASIS",
    "MATCHING_BASIS",
    "POLICY_ID",
    "REGISTRY_SHA256",
    "SCHEMA_VERSION",
    "STATE_FILENAME",
    "STATE_SCHEMA_VERSION",
    "TEAM_IDENTITY_SEEDS",
    "configure_persistent_state",
    "match_event",
    "observe_fotmob_captures",
    "observe_fotmob_payload",
    "observe_provider_directory",
    "observe_provider_payload",
    "registry_payload",
    "registry_sha256",
    "reset_runtime_evidence",
]
