"""Current Shadow-only deterministic fixture-identity reconciliation recovery.

Run 199 proved that the provider catalog contained exact same-kickoff counterparts
that V2 rejected, including cases where FotMob's current competition primary ID
changed while the already-reviewed provider tournament and competition label did
not, and cases such as Champions League where provider/source competition labels
differ but both stable team identities establish the fixture exactly.

This hook keeps full UTC kickoff, home/away orientation, provider-native IDs,
one-to-one team identity and reviewed exact team aliases unchanged. It adds no
fuzzy name matching, suffix stripping, reversal or kickoff tolerance.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Any, Sequence

from domain import current_shadow_fixture_identity_v2 as identity


POLICY_ID = "ATHENA_CURRENT_SHADOW_STABLE_SOURCE_PROVIDER_IDENTITY_RECOVERY_V3"
MATCHING_BASIS = (
    identity.MATCHING_BASIS
    + "_CURRENT_SHADOW_V3_COMPETITION_PRIMARY_ID_DRIFT_ONLY_WHEN_EXACT_COMPETITION_LABEL_"
    "SAME_CCODE_AND_BOTH_TEAMS_CONFIRMED_OR_UNBOUND_COMPETITION_ONLY_WHEN_BOTH_TEAMS_CONFIRMED"
)


def _competition_matches_after_teams(
    source: dict[str, Any],
    provider: dict[str, Any],
    reviewed_name: str,
    *,
    teams_confirmed: bool,
) -> bool:
    source_key = (source["ccode"], source["primary"])
    provider_key = (provider["category"], provider["tournament"])
    bound = identity._comp_forward.get(source_key)
    if bound is not None:
        return bound == provider_key

    exact_label = provider["competition"] in {reviewed_name, source["competition"]}
    reverse = identity._comp_reverse.get(provider_key)
    if reverse is not None:
        # A provider tournament already bound to an older FotMob primary ID may
        # be reused only inside the same source country code, with the exact same
        # competition label and two independently confirmed stable team sides.
        return bool(
            teams_confirmed
            and exact_label
            and reverse[0] == source_key[0]
        )

    # For a provider tournament not previously bound at all, two confirmed team
    # identities plus exact kickoff/orientation uniquely establish the fixture
    # even when the competition display labels differ (for example
    # "Champions League" vs "UEFA Champions League").
    return bool(
        teams_confirmed
        and identity._bind_comp(source_key, provider_key)
    ) or bool(exact_label and identity._bind_comp(source_key, provider_key))


def match_event(event: Any, reviewed_rows: Sequence[Any]) -> tuple[Any, ...]:
    event_id = getattr(event, "event_id", None)
    provider = identity._provider.get(event_id) if type(event_id) is str else None
    if provider is None:
        return identity.aliases.match_event(event, reviewed_rows)
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

    base_bindings = identity._snapshot_bindings()
    successful: list[tuple[Any, tuple[Any, Any, Any, Any], dict[str, Any]]] = []
    for row in reviewed_rows:
        identity._restore_bindings(base_bindings)
        source_identifier = str(getattr(row, "source_fixture_identifier", ""))
        source = identity._fotmob.get(source_identifier)
        if source is None:
            continue
        try:
            row_kickoff = getattr(row, "kickoff").astimezone(timezone.utc)
        except Exception:
            continue
        if row_kickoff != kickoff or source["kickoff"] != kickoff:
            continue
        reviewed_comp = str(getattr(row, "competition", ""))
        home = identity._team_matches(
            competition=reviewed_comp,
            source_id=source["home_id"],
            short=source["home"],
            long=source["home_long"],
            provider_id=provider["home_id"],
            provider_name=provider["home"],
        )
        away = identity._team_matches(
            competition=reviewed_comp,
            source_id=source["away_id"],
            short=source["away"],
            long=source["away_long"],
            provider_id=provider["away_id"],
            provider_name=provider["away"],
        )
        if not (home and away):
            continue
        if not _competition_matches_after_teams(
            source,
            provider,
            reviewed_comp,
            teams_confirmed=True,
        ):
            continue
        successful.append((
            row,
            identity._snapshot_bindings(),
            identity._new_evidence_record(
                source_fixture_identifier=source_identifier,
                provider_event_id=event_id,
                source=source,
                provider=provider,
            ),
        ))

    identity._restore_bindings(base_bindings)
    if len(successful) == 1:
        row, bindings, evidence = successful[0]
        identity._restore_bindings(bindings)
        if identity._learned_team_rows() or identity._learned_comp_rows():
            if evidence not in identity._evidence_records:
                identity._evidence_records.append(evidence)
            identity._persist_state()
        return (row,)
    return tuple(item[0] for item in successful)


@dataclass(frozen=True)
class RecoveryHooks:
    original_match_event: Any
    original_matching_basis: str
    original_expected_contract_sha256: str
    original_legacy_matching_basis: str
    original_legacy_expected_contract_sha256: str


def install(reconciliation_module: Any) -> RecoveryHooks:
    hooks = RecoveryHooks(
        original_match_event=identity.match_event,
        original_matching_basis=reconciliation_module.MATCHING_BASIS,
        original_expected_contract_sha256=reconciliation_module.EXPECTED_CONTRACT_SHA256,
        original_legacy_matching_basis=reconciliation_module.legacy.MATCHING_BASIS,
        original_legacy_expected_contract_sha256=(
            reconciliation_module.legacy.EXPECTED_CONTRACT_SHA256
        ),
    )
    identity.match_event = match_event
    reconciliation_module.MATCHING_BASIS = MATCHING_BASIS
    reconciliation_module.legacy.MATCHING_BASIS = MATCHING_BASIS
    expected = reconciliation_module.calculate_contract_sha256()
    reconciliation_module.EXPECTED_CONTRACT_SHA256 = expected
    reconciliation_module.legacy.EXPECTED_CONTRACT_SHA256 = expected
    reconciliation_module.validate_contract()
    return hooks


def restore(reconciliation_module: Any, hooks: RecoveryHooks) -> None:
    identity.match_event = hooks.original_match_event
    reconciliation_module.MATCHING_BASIS = hooks.original_matching_basis
    reconciliation_module.EXPECTED_CONTRACT_SHA256 = hooks.original_expected_contract_sha256
    reconciliation_module.legacy.MATCHING_BASIS = hooks.original_legacy_matching_basis
    reconciliation_module.legacy.EXPECTED_CONTRACT_SHA256 = (
        hooks.original_legacy_expected_contract_sha256
    )


__all__ = [
    "MATCHING_BASIS",
    "POLICY_ID",
    "RecoveryHooks",
    "install",
    "match_event",
    "restore",
]
