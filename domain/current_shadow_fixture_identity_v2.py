"""Stable-ID fixture reconciliation for ATHENA's research-only current Shadow lane.

Names may bootstrap identity, but durable matching uses source/provider-native IDs.
Full UTC kickoff, home/away orientation and one-to-one identity remain exact.
No fuzzy matching, suffix stripping, reversal or time tolerance is authorized.
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
POLICY_ID = "ATHENA_CURRENT_SHADOW_STABLE_SOURCE_PROVIDER_IDENTITY_V2"
MATCHING_BASIS = (
    "EXACT_FULL_UTC_HOME_AWAY_STABLE_FOTMOB_PROVIDER_NATIVE_IDS_"
    "EXACT_SHORT_LONG_OR_REVIEWED_ALIAS_BOOTSTRAP_NO_FUZZY_NO_SUFFIX_NO_REVERSAL_NO_TIME_TOLERANCE"
)
EVIDENCE_BASIS = (
    "CURRENT_SHADOW_RUN38_RETAINED_RAW_EVIDENCE_ARTIFACT_SHA256_"
    "3ff8371b67cf4b197cdf03b5215dfd52ad45ecbfa6a65f12d7dc00a1169420f8"
)

_COMPETITOR_RE = re.compile(r"^sr:competitor:[1-9][0-9]*$", re.ASCII)
_CATEGORY_RE = re.compile(r"^sr:category:.+$", re.ASCII)
_TOURNAMENT_RE = re.compile(r"^sr:(?:tournament|simple_tournament):.+$", re.ASCII)
_EVENT_RE = re.compile(r"^sr:match:[1-9][0-9]*$", re.ASCII)

# (FotMob source team ID, SportyBet/Sportradar competitor ID), human-reviewed
# from run #38 retained raw evidence. Stable IDs survive later display-name drift.
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

# (FotMob ccode, primary competition ID, provider category ID, tournament ID).
COMPETITION_IDENTITY_SEEDS = (
    ("BEL",40,"sr:category:33","sr:tournament:38"),("DEN",46,"sr:category:8","sr:tournament:39"),
    ("ENG",48,"sr:category:1","sr:tournament:18"),("ENG",108,"sr:category:1","sr:tournament:24"),
    ("ESP",87,"sr:category:32","sr:tournament:8"),("FRA",53,"sr:category:7","sr:tournament:34"),
    ("GER",209,"sr:category:30","sr:tournament:217"),("ITA",141,"sr:category:31","sr:tournament:328"),
    ("KSA",536,"sr:category:310","sr:tournament:955"),("SCO",64,"sr:category:22","sr:tournament:36"),
    ("SUI",69,"sr:category:25","sr:tournament:215"),("SWE",67,"sr:category:9","sr:tournament:40"),
)


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
_team_forward: dict[int,str] = {}
_team_reverse: dict[str,int] = {}
_comp_forward: dict[tuple[str,int],tuple[str,str]] = {}
_comp_reverse: dict[tuple[str,str],tuple[str,int]] = {}


def reset_runtime_evidence() -> None:
    _fotmob.clear(); _provider.clear(); _team_forward.clear(); _team_reverse.clear()
    _comp_forward.clear(); _comp_reverse.clear()
    for source_id, provider_id in TEAM_IDENTITY_SEEDS:
        _team_forward[source_id] = provider_id; _team_reverse[provider_id] = source_id
    for ccode, primary, category, tournament in COMPETITION_IDENTITY_SEEDS:
        _comp_forward[(ccode,primary)] = (category,tournament)
        _comp_reverse[(category,tournament)] = (ccode,primary)


reset_runtime_evidence()


def _utc_text(value: Any) -> datetime | None:
    if type(value) is not str or not value.endswith("Z"): return None
    try: return datetime.fromisoformat(value[:-1]+"+00:00").astimezone(timezone.utc)
    except (TypeError,ValueError,OverflowError): return None


def _provider_kickoff(value: Any) -> datetime | None:
    if isinstance(value,bool) or not isinstance(value,(int,float)): return None
    try: return datetime.fromtimestamp(float(value)/1000.0,tz=timezone.utc)
    except (ValueError,OSError,OverflowError): return None


def observe_fotmob_payload(raw: bytes) -> None:
    if type(raw) is not bytes or not raw: return
    try: payload=json.loads(raw.decode("utf-8",errors="strict"))
    except (UnicodeDecodeError,json.JSONDecodeError): return
    leagues=payload.get("leagues") if type(payload) is dict else None
    if type(leagues) is not list: return
    for league in leagues:
        if type(league) is not dict or type(league.get("matches")) is not list: continue
        ccode,primary,comp=league.get("ccode"),league.get("primaryId"),league.get("name")
        if type(ccode) is not str or type(primary) is not int or type(comp) is not str: continue
        for match in league["matches"]:
            if type(match) is not dict or type(match.get("id")) is not int: continue
            home,away,status=match.get("home"),match.get("away"),match.get("status")
            if type(home) is not dict or type(away) is not dict or type(status) is not dict: continue
            kickoff=_utc_text(status.get("utcTime"))
            vals=(home.get("id"),home.get("name"),home.get("longName"),away.get("id"),away.get("name"),away.get("longName"))
            if kickoff is None or type(vals[0]) is not int or type(vals[3]) is not int or any(type(v) is not str for v in (vals[1],vals[2],vals[4],vals[5])): continue
            key=str(match["id"]); row={"ccode":ccode,"primary":primary,"competition":comp,"kickoff":kickoff,
                "home_id":vals[0],"home":vals[1],"home_long":vals[2],"away_id":vals[3],"away":vals[4],"away_long":vals[5]}
            prior=_fotmob.get(key)
            if prior is None: _fotmob[key]=row
            elif prior!=row: _fotmob.pop(key,None)


def observe_fotmob_captures(captures: Iterable[Any]) -> None:
    for entry in captures:
        if type(entry) is tuple and len(entry)==2 and type(entry[0]) is bytes: observe_fotmob_payload(entry[0])


def _walk(root: Any):
    stack=[root]
    while stack:
        value=stack.pop()
        if type(value) is dict:
            yield value; stack.extend(value.values())
        elif type(value) is list: stack.extend(value)


def observe_provider_payload(raw: bytes) -> None:
    if type(raw) is not bytes or not raw: return
    try: payload=json.loads(raw.decode("utf-8",errors="strict"))
    except (UnicodeDecodeError,json.JSONDecodeError): return
    for value in _walk(payload):
        event_id=value.get("eventId")
        if type(event_id) is not str or _EVENT_RE.fullmatch(event_id) is None: continue
        hi,ai,hn,an=value.get("homeTeamId"),value.get("awayTeamId"),value.get("homeTeamName"),value.get("awayTeamName")
        sport=value.get("sport")
        if type(hi) is not str or _COMPETITOR_RE.fullmatch(hi) is None or type(ai) is not str or _COMPETITOR_RE.fullmatch(ai) is None: continue
        if type(hn) is not str or type(an) is not str or type(sport) is not dict: continue
        category=sport.get("category")
        if type(category) is not dict or type(category.get("tournament")) is not dict: continue
        tournament=category["tournament"]; ci,ti,comp=category.get("id"),tournament.get("id"),tournament.get("name")
        kickoff=_provider_kickoff(value.get("estimateStartTime"))
        if type(ci) is not str or _CATEGORY_RE.fullmatch(ci) is None or type(ti) is not str or _TOURNAMENT_RE.fullmatch(ti) is None or type(comp) is not str or kickoff is None: continue
        row={"category":ci,"tournament":ti,"competition":comp,"kickoff":kickoff,"home_id":hi,"home":hn,"away_id":ai,"away":an}
        prior=_provider.get(event_id)
        if prior is None: _provider[event_id]=row
        elif prior!=row: _provider.pop(event_id,None)


def observe_provider_directory(directory: Any) -> None:
    try: root=Path(directory)/"tournaments"
    except TypeError: return
    if not root.is_dir(): return
    for path in sorted(root.glob("*.json")):
        try: observe_provider_payload(path.read_bytes())
        except OSError: continue


def _bind_team(source_id:int,provider_id:str) -> bool:
    a,b=_team_forward.get(source_id),_team_reverse.get(provider_id)
    if a not in (None,provider_id) or b not in (None,source_id): return False
    _team_forward[source_id]=provider_id; _team_reverse[provider_id]=source_id; return True


def _bind_comp(source_key:tuple[str,int],provider_key:tuple[str,str]) -> bool:
    a,b=_comp_forward.get(source_key),_comp_reverse.get(provider_key)
    if a not in (None,provider_key) or b not in (None,source_key): return False
    _comp_forward[source_key]=provider_key; _comp_reverse[provider_key]=source_key; return True


def _competition_matches(source:dict[str,Any],provider:dict[str,Any],reviewed_name:str) -> bool:
    sk=(source["ccode"],source["primary"]); pk=(provider["category"],provider["tournament"])
    bound=_comp_forward.get(sk)
    if bound is not None: return bound==pk
    if pk in _comp_reverse: return False
    return (provider["competition"] in {reviewed_name,source["competition"]}) and _bind_comp(sk,pk)


def _team_matches(*,competition:str,source_id:int,short:str,long:str,provider_id:str,provider_name:str) -> bool:
    bound=_team_forward.get(source_id)
    if bound is not None: return bound==provider_id
    if provider_id in _team_reverse: return False
    exact=provider_name==short or provider_name==long
    reviewed=aliases.team_identity_matches(competition=competition,fotmob_name=short,sportybet_name=provider_name)
    return (exact or reviewed) and _bind_team(source_id,provider_id)


def match_event(event: Any, reviewed_rows: Sequence[Any]) -> tuple[Any,...]:
    event_id=getattr(event,"event_id",None); provider=_provider.get(event_id) if type(event_id) is str else None
    if provider is None: return aliases.match_event(event,reviewed_rows)
    try: kickoff=getattr(event,"kickoff_utc").astimezone(timezone.utc)
    except Exception: return ()
    if provider["kickoff"]!=kickoff or provider["home"]!=getattr(event,"home_team_name",None) or provider["away"]!=getattr(event,"away_team_name",None): return ()
    matches=[]
    for row in reviewed_rows:
        source=_fotmob.get(str(getattr(row,"source_fixture_identifier","")))
        if source is None: continue
        try: row_kickoff=getattr(row,"kickoff").astimezone(timezone.utc)
        except Exception: continue
        if row_kickoff!=kickoff or source["kickoff"]!=kickoff: continue
        reviewed_comp=str(getattr(row,"competition",""))
        if not _competition_matches(source,provider,reviewed_comp): continue
        home=_team_matches(competition=reviewed_comp,source_id=source["home_id"],short=source["home"],long=source["home_long"],provider_id=provider["home_id"],provider_name=provider["home"])
        away=_team_matches(competition=reviewed_comp,source_id=source["away_id"],short=source["away"],long=source["away_long"],provider_id=provider["away_id"],provider_name=provider["away"])
        if home and away: matches.append(row)
    return tuple(matches)


def registry_payload() -> dict[str,Any]:
    return {"schema_version":SCHEMA_VERSION,"policy_id":POLICY_ID,"matching_basis":MATCHING_BASIS,"evidence_basis":EVIDENCE_BASIS,
        "team_identity_seeds":[list(x) for x in TEAM_IDENTITY_SEEDS],"competition_identity_seeds":[list(x) for x in COMPETITION_IDENTITY_SEEDS],
        "legacy_alias_registry_sha256":aliases.REGISTRY_SHA256,"authority":{"research_shadow_fixture_reconciliation":True,"production_model":False,
        "pricing":False,"selection":False,"sportybet_execution":False,"login":False,"cookies":False,"wallet":False,"staking":False,"bet":False,"wager_placed":False}}


def registry_sha256() -> str:
    raw=json.dumps(registry_payload(),ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


REGISTRY_SHA256=registry_sha256()

__all__=["COMPETITION_IDENTITY_SEEDS","EVIDENCE_BASIS","MATCHING_BASIS","POLICY_ID","REGISTRY_SHA256","SCHEMA_VERSION","TEAM_IDENTITY_SEEDS",
    "match_event","observe_fotmob_captures","observe_fotmob_payload","observe_provider_directory","observe_provider_payload","registry_payload","registry_sha256","reset_runtime_evidence"]
