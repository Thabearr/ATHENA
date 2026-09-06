"""Evidence-bound fixture identity recovery for Current Shadow run #199.

Run #199 retained exact same-kickoff FotMob and SportyBet source evidence for a
set of fixtures that the V2 stable-ID boundary failed to reconcile even though
the provider counterpart was present.  This overlay is deliberately narrower
than a name normalizer: it accepts only literal names, existing reviewed aliases,
or the exact run-199 source/provider display-name pairs below, with exact full
UTC kickoff and home/away orientation.

Competition labels are treated similarly.  This also prevents an old seasonal
SportyBet tournament seed from suppressing a current exact competition label;
the overlay does not rewrite or weaken the V2 registry and does not introduce
fuzzy matching, suffix stripping, token similarity, reversal, or time tolerance.
"""
from __future__ import annotations

from collections.abc import Sequence
import hashlib
import json
from types import MappingProxyType
from typing import Any

from domain import current_shadow_fixture_identity_aliases as reviewed_aliases
from domain import current_shadow_fixture_identity_v2 as stable


SCHEMA_VERSION = 1
POLICY_ID = "ATHENA_CURRENT_SHADOW_RUN199_EXACT_FIXTURE_IDENTITY_OVERLAY_V1"
EVIDENCE_WORKFLOW_RUN_ID = 34052920015
EVIDENCE_ARTIFACT_ID = 9995330762
EVIDENCE_ARTIFACT_SHA256 = (
    "8e257bf9029b421deb5f4e421ec383ea19190e6390ff747444c2b1794b98f2c5"
)
MATCHING_BASIS = (
    "RUN199_EXACT_FULL_UTC_HOME_AWAY_CURRENT_PROVIDER_NATIVE_EVIDENCE_"
    "LITERAL_OR_EXPLICIT_EVIDENCE_BOUND_TEAM_AND_COMPETITION_ALIAS_"
    "NO_FUZZY_NO_SUFFIX_NO_NORMALIZATION_NO_REVERSAL_NO_TIME_TOLERANCE"
)

# These pairs are copied from the retained run-199 source evidence.  They are
# source-competition scoped and are not generic football synonyms.
_TEAM_ALIASES = frozenset(
    {
        ("Super League", "Iraklis", "POT Iraklis"),
        ("Saudi Pro League", "Al Khaleej", "Al-Khaleej Club"),
        ("Saudi Pro League", "Al Riyadh", "Al-Riyadh SC"),
        ("Saudi Pro League", "Al-Ettifaq", "Al-Ettifaq FC"),
        ("Saudi Pro League", "Al-Faisaly", "Al-Faisaly FC"),
        ("Saudi Pro League", "Al Hazem", "Al-Hazm"),
        ("Saudi Pro League", "Al-Taawoun", "Al-Taawoun FC"),
        ("Saudi Pro League", "Al Ittihad", "Al-Ittihad Club"),
        ("Saudi Pro League", "Al-Fayha", "Al-Fayha FC"),
        ("Allsvenskan", "Mjällby", "Mjallby AIF"),
        ("Allsvenskan", "IFK Göteborg", "IFK Goteborg"),
        ("Allsvenskan", "Malmö FF", "Malmo"),
        ("Allsvenskan", "Djurgården", "Djurgardens IF"),
        ("LaLiga", "Celta Vigo", "Celta"),
        ("LaLiga", "Elche", "Elche CF"),
        ("Super Lig", "Rizespor", "Caykur Rizespor"),
        ("Super Lig", "Göztepe", "Goztepe Izmir"),
        ("Liga Portugal", "Gil Vicente", "Gil Vicente Barcelos"),
        ("Liga Portugal", "Académico Viseu", "Academico de Viseu FC"),
        ("Liga Portugal", "Estoril", "Estoril Praia"),
        ("Liga Portugal", "Arouca", "FC Arouca"),
        ("Eredivisie", "Excelsior", "Excelsior Rotterdam"),
        ("Champions League", "LASK", "LASK Linz"),
        ("Champions League", "Dortmund", "Borussia Dortmund"),
        ("Champions League", "FC Porto", "Porto"),
        ("Champions League", "Real Betis", "Betis"),
        ("Championship", "Wrexham", "Wrexham AFC"),
        ("EFL Cup", "Middlesbrough", "Middlesbrough FC"),
        ("EFL Cup", "Millwall", "Millwall FC"),
    }
)
_COMPETITION_ALIASES = frozenset(
    {
        ("Champions League", "UEFA Champions League"),
    }
)

AUTHORITY = MappingProxyType(
    {
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
    }
)


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def policy_payload() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "policy_id": POLICY_ID,
        "matching_basis": MATCHING_BASIS,
        "evidence": {
            "workflow_run_id": EVIDENCE_WORKFLOW_RUN_ID,
            "artifact_id": EVIDENCE_ARTIFACT_ID,
            "artifact_sha256": EVIDENCE_ARTIFACT_SHA256,
        },
        "team_aliases": [list(row) for row in sorted(_TEAM_ALIASES)],
        "competition_aliases": [list(row) for row in sorted(_COMPETITION_ALIASES)],
        "authority": dict(AUTHORITY),
    }


def policy_sha256() -> str:
    return hashlib.sha256(_canonical(policy_payload())).hexdigest()


def _competition_matches(source_name: str, provider_name: str) -> bool:
    return source_name == provider_name or (source_name, provider_name) in _COMPETITION_ALIASES


def _team_matches(
    *,
    competition: str,
    source_id: int,
    short: str,
    long: str,
    provider_id: str,
    provider_name: str,
) -> bool:
    bound = stable._team_forward.get(source_id)
    if bound is not None:
        return bound == provider_id
    if provider_id in stable._team_reverse:
        return False
    if provider_name == short or provider_name == long:
        return stable._bind_team(source_id, provider_id)
    if reviewed_aliases.team_identity_matches(
        competition=competition,
        fotmob_name=short,
        sportybet_name=provider_name,
    ):
        return stable._bind_team(source_id, provider_id)
    if (competition, short, provider_name) in _TEAM_ALIASES:
        return stable._bind_team(source_id, provider_id)
    if long != short and (competition, long, provider_name) in _TEAM_ALIASES:
        return stable._bind_team(source_id, provider_id)
    return False


def match_event(event: Any, reviewed_rows: Sequence[Any]) -> tuple[Any, ...]:
    """Use V2 first, then the exact retained run-199 compatibility boundary."""

    baseline = stable.match_event(event, reviewed_rows)
    if baseline:
        return baseline

    event_id = getattr(event, "event_id", None)
    provider = stable._provider.get(event_id) if type(event_id) is str else None
    if provider is None:
        return ()
    try:
        kickoff = getattr(event, "kickoff_utc").astimezone(stable.timezone.utc)
    except Exception:
        return ()
    if (
        provider["kickoff"] != kickoff
        or provider["home"] != getattr(event, "home_team_name", None)
        or provider["away"] != getattr(event, "away_team_name", None)
    ):
        return ()

    base_bindings = stable._snapshot_bindings()
    successful: list[tuple[Any, tuple[Any, Any, Any, Any], dict[str, Any]]] = []
    for row in reviewed_rows:
        stable._restore_bindings(base_bindings)
        source_identifier = str(getattr(row, "source_fixture_identifier", ""))
        source = stable._fotmob.get(source_identifier)
        if source is None:
            continue
        try:
            row_kickoff = getattr(row, "kickoff").astimezone(stable.timezone.utc)
        except Exception:
            continue
        if row_kickoff != kickoff or source["kickoff"] != kickoff:
            continue
        reviewed_comp = str(getattr(row, "competition", ""))
        if not _competition_matches(reviewed_comp, provider["competition"]):
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
            successful.append(
                (
                    row,
                    stable._snapshot_bindings(),
                    stable._new_evidence_record(
                        source_fixture_identifier=source_identifier,
                        provider_event_id=event_id,
                        source=source,
                        provider=provider,
                    ),
                )
            )

    stable._restore_bindings(base_bindings)
    if len(successful) == 1:
        row, bindings, evidence = successful[0]
        stable._restore_bindings(bindings)
        if stable._learned_team_rows():
            if evidence not in stable._evidence_records:
                stable._evidence_records.append(evidence)
            stable._persist_state()
        return (row,)
    return tuple(item[0] for item in successful)


POLICY_SHA256 = policy_sha256()

__all__ = [
    "AUTHORITY",
    "EVIDENCE_ARTIFACT_ID",
    "EVIDENCE_ARTIFACT_SHA256",
    "EVIDENCE_WORKFLOW_RUN_ID",
    "MATCHING_BASIS",
    "POLICY_ID",
    "POLICY_SHA256",
    "SCHEMA_VERSION",
    "match_event",
    "policy_payload",
    "policy_sha256",
]
