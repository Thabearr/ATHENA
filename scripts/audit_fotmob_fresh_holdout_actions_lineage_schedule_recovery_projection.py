"""Project the read-only fresh-holdout audit across reviewed no-acquisition recovery.

The underlying lineage audit remains the reviewed engine. This projection updates
only its pinned runtime dependency identities and makes evidence-transparent
compatibility allowances for GitHub runs that exact metadata proves could not
contain a provider observation:

* exact AMBIGUOUS_NO_ACQUISITION successes;
* exact zero-artifact pre-acquisition failures admitted by the current reviewed
  producer-side proof; and
* one exact historical queued workflow_dispatch that never acquired a job or
  artifact and predates the reviewed prospective-continuity run-name boundary;
* one exact, fully replayed historical continuity/natural double-acquisition
  retained as one canonical slot plus one current-only auxiliary execution.

The current producer also contains the separately source-authenticated prospective
continuity transport. This projection admits a continuity collection only after
replaying its immutable dispatch/watchdog provenance; it never relabels that run as
a natural schedule delivery.

The historical queued allowance is identity-bound to the exact GitHub run observed
by the post-PR293 operational proof. It is not a generic queued-run or dispatch
bypass: any metadata drift, job appearance, or artifact appearance fails closed.

The pre-acquisition allowance matches the post-PR207 producer boundary. A proven
pre-acquisition failure may be transparent even after canonical campaign evidence
exists, but projecting it out never reopens Genesis: the unchanged audit engine
still derives campaign-origin state from the remaining chronological evidence.

The historical double-acquisition allowance is identity-bound as well. It first
prefetches the complete paginated run universe, proves both exact executions and
their durable archive prefix, then hides only the later execution from the frozen
nominal-slot map while retaining its provider-acquiring evidence in current-only
metadata. It is not a general multiple-runs-per-slot relaxation.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import copy
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import domain.fotmob_utc_native_expected_goals_fresh_holdout_activation_runner as activation
import domain.fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery as recovery
import domain.fotmob_fresh_holdout_continuity as continuity
import scripts.audit_fotmob_fresh_holdout_actions_lineage as audit
import scripts.mirror_fotmob_fresh_holdout_release_receipt as durable_mirror
import scripts.audit_fotmob_fresh_holdout_actions_lineage_pr175_projection as pr175
import scripts.run_fotmob_fresh_holdout_release_receipt_mirror as receipt_mirror


PRE_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA = pr175.POST_PR175_WORKFLOW_BLOB_SHA
POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA = "ee928ba29c7108c203402ff8efabf3d6fc3e4e00"
SCHEDULE_RECOVERY_BLOB_SHA = "7fe531dfb6bba96c7e6505016b89761f0d25428f"
SCHEDULE_RECOVERY_PATH = (
    "domain/fotmob_utc_native_expected_goals_fresh_holdout_schedule_recovery.py"
)

LEGACY_QUEUED_NO_EXECUTION_RUN_ID = 33576163735
LEGACY_QUEUED_NO_EXECUTION_HEAD_SHA = "548271e960839003d64aef79f6f27f0a1a442abf"
LEGACY_QUEUED_NO_EXECUTION_CREATED_AT = "2026-09-02T00:38:33Z"
LEGACY_QUEUED_NO_EXECUTION_RUN_NUMBER = 423
LEGACY_QUEUED_NO_EXECUTION_TITLE = "FotMob UTC-Native xG Fresh-Holdout Collection Runner"

_ORIGINAL_AUDIT_ACTIONS_LINEAGE = audit.audit_actions_lineage
_ORIGINAL_RUN_IS_COLLECTION_CANDIDATE = audit._run_is_collection_candidate
_ORIGINAL_VALIDATE_CONTROL_LINEAGE = audit.validate_control_lineage


def _fixed_get_run_by_id(
    repository: str,
    run_id: int,
) -> Mapping[str, Any]:
    """Read exactly one Actions run for the direct projection CLI.

    Current-history construction supplies its own recorder-backed reader. This
    helper is only the projection-owned live CLI/workflow fallback, and is
    deliberately limited to the exact run-metadata endpoint.
    """
    if (
        type(repository) is not str
        or repository.count("/") != 1
        or repository != repository.strip()
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity exact-run reader requires an exact repository identity"
        )
    if type(run_id) is not int or run_id <= 0:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity source watchdog run id is invalid"
        )
    return audit._gh_json(f"/repos/{repository}/actions/runs/{run_id}")


def _git_blob_sha(path: Path) -> str:
    import hashlib

    raw = path.read_bytes()
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _projected_noop_record(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "created_at": run.get("created_at"),
        "head_sha": run.get("head_sha"),
        "conclusion": run.get("conclusion"),
        "evidence_state": "VERIFIED_AMBIGUOUS_NO_ACQUISITION",
        "nominal_slot_utc": None,
        "tick_committed": False,
        "archive_name": None,
        "archive_sha256": None,
        "release_state": "NOT_APPLICABLE_NO_ACQUISITION",
        "verification_error": None,
    }


def _projected_preacquisition_record(run: Mapping[str, Any]) -> dict[str, Any]:
    record = {
        "run_id": run.get("id"),
        "created_at": run.get("created_at"),
        "head_sha": run.get("head_sha"),
        "conclusion": run.get("conclusion"),
        "evidence_state": "VERIFIED_PREACQUISITION_CONTROL_FAILURE",
        "nominal_slot_utc": None,
        "tick_committed": False,
        "archive_name": None,
        "archive_sha256": None,
        "release_state": "NOT_APPLICABLE_NO_ACQUISITION",
        "verification_error": None,
    }
    if run.get("event") == "workflow_dispatch":
        record["execution_provenance"] = (
            "PROSPECTIVE_CONTINUITY_DISPATCH_PREACQUISITION_FAILURE"
        )
    return record


def _projected_continuity_noop_record(run: Mapping[str, Any]) -> dict[str, Any]:
    record = _projected_noop_record(run)
    record["execution_provenance"] = (
        "PROSPECTIVE_CONTINUITY_DISPATCH_NO_ACQUISITION"
    )
    return record


def _projected_legacy_queued_no_execution_record(
    run: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run.get("id"),
        "created_at": run.get("created_at"),
        "head_sha": run.get("head_sha"),
        "conclusion": None,
        "evidence_state": "VERIFIED_LEGACY_QUEUED_NO_EXECUTION",
        "execution_provenance": "PRE_CONTINUITY_LEGACY_WORKFLOW_DISPATCH_NO_EXECUTION",
        "nominal_slot_utc": None,
        "tick_committed": False,
        "archive_name": None,
        "archive_sha256": None,
        "release_state": "NOT_APPLICABLE_NO_ACQUISITION",
        "verification_error": None,
    }


_HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID = 33820556400
_HISTORICAL_SAME_SLOT_NATURAL_RUN_ID = 33823663641
_HISTORICAL_SAME_SLOT_UTC = "2026-09-04T00:07:00.000000Z"
_HISTORICAL_SAME_SLOT_SECONDS = "2026-09-04T00:07:00Z"
_HISTORICAL_SAME_SLOT_COMPACT = "20260904T000700Z"
_HISTORICAL_SAME_SLOT_HEAD_SHA = "92da60c93e03c0c958a6d3143b43bb43fa8a2f42"
_HISTORICAL_SAME_SLOT_WORKFLOW_ID = continuity.PRIMARY_WORKFLOW_ID
_HISTORICAL_SAME_SLOT_WORKFLOW_PATH = continuity.PRIMARY_WORKFLOW_PATH
_HISTORICAL_SAME_SLOT_CONTINUITY_CREATED_AT = "2026-09-04T00:08:32Z"
_HISTORICAL_SAME_SLOT_NATURAL_CREATED_AT = "2026-09-04T00:54:24Z"
_HISTORICAL_SAME_SLOT_WATCHDOG_CREATED_AT = "2026-09-03T23:57:11Z"
_HISTORICAL_SAME_SLOT_CONTINUITY_NAME = (
    "ATHENA fresh-holdout workflow_dispatch source=33819767003 "
    "target=2026-09-04T00:07:00Z cron=7 * * * * "
    "confirm=PROSPECTIVE_ONLY_NO_BACKFILL_V1"
)
_HISTORICAL_SAME_SLOT_NATURAL_NAME = (
    "ATHENA fresh-holdout schedule source= target= cron= confirm="
)
_HISTORICAL_SAME_SLOT_WATCHDOG_RUN_ID = 33819767003
_HISTORICAL_CONTINUITY_ARTIFACT_ID = 9918215386
_HISTORICAL_CONTINUITY_ARTIFACT = (
    "failure-20260904T000700Z-run-33820556400.tar.gz"
)
_HISTORICAL_CONTINUITY_ZIP_DIGEST = (
    "sha256:e22fd0c351eb90bb8d7d577f24a94b5f71f8ea0dbd0ef7c648ca03bd7da930df"
)
_HISTORICAL_CONTINUITY_ARCHIVE_SHA256 = (
    "38a51e7acbb0221b223f0523e3484f4159f17ae609b01c0f9813f517e930e112"
)
_HISTORICAL_CONTINUITY_ARCHIVE_SIZE = 1811473
_HISTORICAL_NATURAL_ARTIFACT_ID = 9919255715
_HISTORICAL_NATURAL_ARTIFACT = "failure-20260904T000700Z-run-33823663641.tar.gz"
_HISTORICAL_NATURAL_ZIP_DIGEST = (
    "sha256:792ddba3b8f4b38bc494f8d0a660a80dceb5c8c9f2a9bcdaf88cbba43ac5f43a"
)
_HISTORICAL_NATURAL_ARCHIVE_SHA256 = (
    "32d8c5dfb450238c328af24f1b4a0705b9066cd9a1b02412937c10555aedf864"
)
_HISTORICAL_NATURAL_ARCHIVE_SIZE = 1873913
_HISTORICAL_PROVIDER_REQUEST_DATES = ("20260903", "20260904", "20260905")
_HISTORICAL_RELEASE_TAG = "athena-fresh-holdout-evidence-2026-W36"
_HISTORICAL_FAILURE_DISPOSITION = "TICK_NOT_COMMITTED_REVIEW_FAILURE_EVIDENCE"
_HISTORICAL_DETAIL = "FreshHoldoutActivationError: reviewed fresh capture qualification failed"
_HISTORICAL_PROOF_TOKEN = object()
_RUN_UNIVERSE_TOKEN = object()
_LOWER_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _is_lower_sha256(value: Any) -> bool:
    return type(value) is str and _LOWER_SHA256_RE.fullmatch(value) is not None


@dataclasses.dataclass(frozen=True)
class HistoricalSameSlotProviderDuplicateProof:
    """Complete, current-only proof for the one observed double acquisition.

    This object is deliberately not a generic duplicate policy.  Construction is
    private-by-convention: callers receive it only after the paginated run
    universe, exact run metadata, continuity provenance, Actions transports,
    receipt fields, durable archive bytes, and cumulative journal proof all pass.
    """

    canonical_run_id: int
    auxiliary_run_id: int
    nominal_slot_utc: str
    canonical_archive_name: str
    canonical_archive_sha256: str
    canonical_archive_size_bytes: int
    auxiliary_archive_name: str
    auxiliary_archive_sha256: str
    auxiliary_archive_size_bytes: int
    canonical_actions_artifact_id: int
    canonical_actions_digest: str
    auxiliary_actions_artifact_id: int
    auxiliary_actions_digest: str
    provider_acquisition_count_canonical: int
    provider_acquisition_count_auxiliary: int
    _token: object = dataclasses.field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._token is not _HISTORICAL_PROOF_TOKEN:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical proof must be issued by the complete evidence preflight"
            )
        if self.canonical_run_id != _HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical proof canonical run identity changed"
            )
        if self.auxiliary_run_id != _HISTORICAL_SAME_SLOT_NATURAL_RUN_ID:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical proof auxiliary run identity changed"
            )
        if self.nominal_slot_utc != _HISTORICAL_SAME_SLOT_UTC:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical proof nominal slot changed"
            )
        if self.canonical_archive_name != _HISTORICAL_CONTINUITY_ARTIFACT:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical proof canonical archive identity changed"
            )
        if self.auxiliary_archive_name != _HISTORICAL_NATURAL_ARTIFACT:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical proof auxiliary archive identity changed"
            )
        exact_identity = (
            (self.canonical_archive_sha256, _HISTORICAL_CONTINUITY_ARCHIVE_SHA256),
            (self.canonical_archive_size_bytes, _HISTORICAL_CONTINUITY_ARCHIVE_SIZE),
            (self.auxiliary_archive_sha256, _HISTORICAL_NATURAL_ARCHIVE_SHA256),
            (self.auxiliary_archive_size_bytes, _HISTORICAL_NATURAL_ARCHIVE_SIZE),
            (self.canonical_actions_artifact_id, _HISTORICAL_CONTINUITY_ARTIFACT_ID),
            (self.canonical_actions_digest, _HISTORICAL_CONTINUITY_ZIP_DIGEST),
            (self.auxiliary_actions_artifact_id, _HISTORICAL_NATURAL_ARTIFACT_ID),
            (self.auxiliary_actions_digest, _HISTORICAL_NATURAL_ZIP_DIGEST),
            (self.provider_acquisition_count_canonical, 3),
            (self.provider_acquisition_count_auxiliary, 3),
        )
        for actual, expected in exact_identity:
            if actual != expected:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "historical proof evidence identity changed"
                )
        for value, label in (
            (self.canonical_archive_sha256, "canonical archive SHA-256"),
            (self.auxiliary_archive_sha256, "auxiliary archive SHA-256"),
        ):
            if not _is_lower_sha256(value):
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"{label} is not exact lowercase SHA-256"
                )
        for value, label in (
            (self.canonical_archive_size_bytes, "canonical archive size"),
            (self.auxiliary_archive_size_bytes, "auxiliary archive size"),
            (self.canonical_actions_artifact_id, "canonical Actions artifact id"),
            (self.auxiliary_actions_artifact_id, "auxiliary Actions artifact id"),
            (self.provider_acquisition_count_canonical, "canonical acquisition count"),
            (self.provider_acquisition_count_auxiliary, "auxiliary acquisition count"),
        ):
            if type(value) is not int or value < 1:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"{label} is invalid"
                )
        for value, label in (
            (self.canonical_actions_digest, "canonical Actions digest"),
            (self.auxiliary_actions_digest, "auxiliary Actions digest"),
        ):
            if (
                type(value) is not str
                or not value.startswith("sha256:")
                or len(value) != 71
                or not _is_lower_sha256(value[7:])
            ):
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"{label} is invalid"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            field.name: getattr(self, field.name)
            for field in dataclasses.fields(self)
            if field.name != "_token"
        }


@dataclasses.dataclass(frozen=True)
class _CachedWorkflowRunUniverse:
    pages: tuple[Mapping[str, Any], ...]
    runs: tuple[Mapping[str, Any], ...]
    _token: object = dataclasses.field(repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        if self._token is not _RUN_UNIVERSE_TOKEN:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "workflow run universe must come from the exact page preflight"
            )
        if type(self.pages) is not tuple or type(self.runs) is not tuple:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "workflow run universe snapshots must be immutable tuples"
            )

    def reader(self, page: int, per_page: int) -> Mapping[str, Any]:
        if type(page) is not int or page < 1 or page > len(self.pages):
            raise audit.FreshHoldoutActionsLineageAuditError(
                "cached workflow run page escaped prefetched universe"
            )
        if per_page != 100:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "cached workflow run reader changed reviewed page size"
            )
        # Hand a detached snapshot to each consumer.  A validator or test may
        # inspect/mutate its return value, but that must never mutate the exact
        # cached evidence subsequently replayed by another consumer.
        return copy.deepcopy(self.pages[page - 1])


def _prefetch_workflow_run_universe(
    get_runs_page: Callable[[int, int], Mapping[str, Any]],
) -> _CachedWorkflowRunUniverse:
    """Capture the exact bounded run pages before the raw audit sees any run."""
    if not callable(get_runs_page):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "workflow run page reader must be callable"
        )
    pages: list[Mapping[str, Any]] = []
    runs: list[Mapping[str, Any]] = []
    seen_ids: set[int] = set()
    campaign_start = audit._parse_utc(audit.CAMPAIGN_START_UTC, "campaign start")
    for page in range(1, 101):
        payload = get_runs_page(page, 100)
        if not isinstance(payload, Mapping):
            raise audit.FreshHoldoutActionsLineageAuditError(
                "workflow run page payload is malformed"
            )
        values = payload.get("workflow_runs")
        if type(values) is not list:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "workflow run page workflow_runs is malformed"
            )
        # Retain a detached exact mapping and ordering.  The cached reader is
        # the sole page source subsequently supplied to the frozen audit; a
        # caller cannot mutate the live response after this evidence boundary.
        try:
            snapshot = copy.deepcopy(payload)
        except Exception as exc:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "workflow run page could not be detached for caching"
            ) from exc
        pages.append(snapshot)
        values = snapshot.get("workflow_runs")
        for value in values:
            if type(value) is not dict:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "workflow run page contains a non-object run"
                )
            run_id = value.get("id")
            if type(run_id) is not int or run_id < 1:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "workflow run page contains an invalid run id"
                )
            if run_id in seen_ids:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "workflow run appears more than once in paginated universe"
                )
            seen_ids.add(run_id)
            # Keep the flattened universe detached from the page snapshots as
            # well.  The proof must consume one immutable evidence snapshot,
            # not a dict that a later page-reader consumer could mutate.
            runs.append(copy.deepcopy(value))
        if not values:
            break
        oldest: dt.datetime | None = None
        for value in values:
            created_at = value.get("created_at")
            if type(created_at) is not str:
                continue
            try:
                parsed = audit._parse_utc(created_at, "run created_at")
            except audit.FreshHoldoutActionsLineageAuditError:
                continue
            oldest = parsed if oldest is None or parsed < oldest else oldest
        if len(values) < 100 or (oldest is not None and oldest < campaign_start):
            break
    else:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "workflow run pagination exceeded reviewed bound"
        )
    return _CachedWorkflowRunUniverse(
        tuple(pages), tuple(runs), _token=_RUN_UNIVERSE_TOKEN
    )


def _prove_exact_historical_same_slot_provider_duplicate(
    *,
    run_universe: _CachedWorkflowRunUniverse,
    get_run_by_id: Callable[[int], Mapping[str, Any]],
    get_run_artifacts: Callable[[int], Mapping[str, Any]],
    download_artifact_zip: Callable[[int], bytes],
    get_run_jobs: Callable[[int], Mapping[str, Any]],
) -> HistoricalSameSlotProviderDuplicateProof | None:
    """Prove the one reviewed historical double-acquisition before raw audit.

    The proof intentionally performs no candidate-predicate work.  It consumes
    the complete cached paginated run universe, cross-checks both exact runs,
    replays the existing continuity authentication, verifies both Actions ZIPs
    and their receipts, and compares the durable state archives byte-for-byte.
    Only a fully proven pair yields a proof object; all mutations raise and the
    caller must leave the frozen audit's generic duplicate rule in place.
    """
    if not isinstance(run_universe, _CachedWorkflowRunUniverse):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair proof requires the exact prefetched run universe"
        )
    values = [value for value in run_universe.runs if type(value) is dict]
    if len(values) != len(run_universe.runs):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair universe contains a non-object run"
        )
    # Reconstruct the flattened page identity from the cached pages.  This
    # prevents a caller from presenting an independently fabricated ``runs``
    # tuple while omitting or changing a page in the evidence snapshot.
    flattened_page_runs: list[Mapping[str, Any]] = []
    for page in run_universe.pages:
        if type(page) is not dict or type(page.get("workflow_runs")) is not list:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical pair cached page shape changed"
            )
        if any(type(value) is not dict for value in page["workflow_runs"]):
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical pair cached page contains a non-object run"
            )
        flattened_page_runs.extend(page["workflow_runs"])
    if [value.get("id") for value in flattened_page_runs] != [
        value.get("id") for value in values
    ]:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair flattened pages disagree with cached run universe"
        )
    if flattened_page_runs != values:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair cached run fields disagree with exact page evidence"
        )
    by_id: dict[int, Mapping[str, Any]] = {}
    for value in values:
        run_id = value.get("id")
        if type(run_id) is not int or run_id < 1:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical pair universe contains an invalid run id"
            )
        if run_id in by_id:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical pair universe contains a duplicate run id"
            )
        by_id[run_id] = value

    continuity_run = by_id.get(_HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID)
    natural_run = by_id.get(_HISTORICAL_SAME_SLOT_NATURAL_RUN_ID)
    if continuity_run is None or natural_run is None:
        # The exact historical pair is not in this snapshot.  This is a normal
        # path for synthetic/current universes and must not authorize a pair.
        return None

    direct_cache: dict[int, Mapping[str, Any]] = {}

    def _exact_run(run_id: int) -> Mapping[str, Any]:
        if run_id not in direct_cache:
            direct = get_run_by_id(run_id)
            if type(direct) is not dict:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "historical pair direct run metadata is malformed"
                )
            direct_cache[run_id] = direct
        return direct_cache[run_id]

    def _expected_metadata(run_id: int) -> dict[str, Any]:
        if run_id == _HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID:
            return {
                "id": _HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
                "event": "workflow_dispatch",
                "workflow_id": _HISTORICAL_SAME_SLOT_WORKFLOW_ID,
                "path": _HISTORICAL_SAME_SLOT_WORKFLOW_PATH,
                "head_branch": "main",
                "head_sha": _HISTORICAL_SAME_SLOT_HEAD_SHA,
                "created_at": _HISTORICAL_SAME_SLOT_CONTINUITY_CREATED_AT,
                "conclusion": "failure",
                "status": "completed",
                "name": _HISTORICAL_SAME_SLOT_CONTINUITY_NAME,
                "display_title": _HISTORICAL_SAME_SLOT_CONTINUITY_NAME,
            }
        return {
            "id": _HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
            "event": "schedule",
            "workflow_id": _HISTORICAL_SAME_SLOT_WORKFLOW_ID,
            "path": _HISTORICAL_SAME_SLOT_WORKFLOW_PATH,
            "head_branch": "main",
            "head_sha": _HISTORICAL_SAME_SLOT_HEAD_SHA,
            "created_at": _HISTORICAL_SAME_SLOT_NATURAL_CREATED_AT,
            "conclusion": "failure",
            "status": "completed",
            "name": _HISTORICAL_SAME_SLOT_NATURAL_NAME,
            "display_title": _HISTORICAL_SAME_SLOT_NATURAL_NAME,
        }

    def _cross_check_run(run_id: int, paginated: Mapping[str, Any]) -> Mapping[str, Any]:
        expected = _expected_metadata(run_id)
        direct = _exact_run(run_id)
        for key, expected_value in expected.items():
            if paginated.get(key) != expected_value or direct.get(key) != expected_value:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"historical pair run {run_id} metadata drifted: {key}"
                )
            if paginated.get(key) != direct.get(key):
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"historical pair run {run_id} paginated/direct metadata disagrees: {key}"
                )
        return direct

    continuity_run = _cross_check_run(
        _HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID, continuity_run
    )
    natural_run = _cross_check_run(_HISTORICAL_SAME_SLOT_NATURAL_RUN_ID, natural_run)
    if continuity_run["created_at"] >= natural_run["created_at"]:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical continuity attempt does not precede natural attempt"
        )

    watchdog = _exact_run(_HISTORICAL_SAME_SLOT_WATCHDOG_RUN_ID)
    expected_watchdog = {
        "id": _HISTORICAL_SAME_SLOT_WATCHDOG_RUN_ID,
        "name": continuity.WATCHDOG_WORKFLOW_NAME,
        "path": continuity.WATCHDOG_WORKFLOW_PATH,
        "event": "schedule",
        "head_branch": "main",
        "head_sha": _HISTORICAL_SAME_SLOT_HEAD_SHA,
        "created_at": _HISTORICAL_SAME_SLOT_WATCHDOG_CREATED_AT,
        "status": "completed",
        "conclusion": "success",
    }
    if not isinstance(watchdog, Mapping) or any(
        watchdog.get(key) != value for key, value in expected_watchdog.items()
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical continuity watchdog metadata drifted"
        )

    # The existing reviewed watchdog/continuity validator is the only accepted
    # authentication scheme for the dispatch execution.
    plan = _prove_continuity_candidate(
        continuity_run,
        get_run_by_id=_exact_run,
        get_run_jobs=get_run_jobs,
    )
    if plan.target_slot != audit._parse_utc(
        _HISTORICAL_SAME_SLOT_UTC, "historical continuity target"
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical continuity target differs from reviewed slot"
        )

    def _artifact_for(
        run_id: int,
        *,
        expected_id: int,
        expected_name: str,
        expected_digest: str,
    ) -> tuple[Mapping[str, Any], dict[str, Any]]:
        payload = get_run_artifacts(run_id)
        if not isinstance(payload, Mapping):
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical run {run_id} artifact payload is malformed"
            )
        artifacts = payload.get("artifacts")
        if (
            type(artifacts) is not list
            or len(artifacts) != 1
            or ("total_count" in payload and payload.get("total_count") != 1)
        ):
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical run {run_id} must expose exactly one artifact"
            )
        artifact = artifacts[0]
        if (
            type(artifact) is not dict
            or artifact.get("id") != expected_id
            or artifact.get("name") != expected_name
            or artifact.get("digest") != expected_digest
            or artifact.get("expired") is not False
        ):
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical run {run_id} artifact identity drifted"
            )
        zip_bytes = download_artifact_zip(expected_id)
        try:
            zip_digest = durable_mirror.verify_actions_artifact_zip_digest(
                zip_bytes, expected_digest
            )
            verified = durable_mirror.verify_actions_artifact_bundle(
                run_id=run_id,
                artifact_name=expected_name,
                zip_bytes=zip_bytes,
            )
        except Exception as exc:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical run {run_id} Actions artifact proof failed"
            ) from exc
        if f"sha256:{zip_digest}" != expected_digest:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical run {run_id} Actions digest changed"
            )
        verified["actions_artifact_zip_sha256"] = zip_digest
        return artifact, verified

    def _read_attempt(
        *,
        run_id: int,
        artifact_id: int,
        artifact_name: str,
        artifact_digest: str,
        archive_sha256: str,
        archive_size: int,
    ) -> tuple[Mapping[str, Any], dict[str, bytes], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
        artifact, verified = _artifact_for(
            run_id,
            expected_id=artifact_id,
            expected_name=artifact_name,
            expected_digest=artifact_digest,
        )
        receipt = durable_mirror._parse_canonical_json(
            verified["receipt_bytes"],
            f"historical run {run_id} tick receipt",
        )
        exact_receipt = {
            "schema_version": 1,
            "workflow_run_id": run_id,
            "nominal_scheduled_for_utc": _HISTORICAL_SAME_SLOT_UTC,
            "scheduled_for_utc": "2026-09-04T00:07:00Z",
            "disposition": _HISTORICAL_FAILURE_DISPOSITION,
            "tick_committed": False,
            "backfill_or_retrofill_authorized": False,
            "network_replay_authorized": False,
            "durable_asset_name": artifact_name,
            "durable_asset_sha256": archive_sha256,
            "durable_asset_size_bytes": archive_size,
            "durable_release_tag": _HISTORICAL_RELEASE_TAG,
            "runner_id": activation.RUNNER_ID,
            "workflow_event_schedule": "7 * * * *",
            "failure_lineage_reconcile_outcome": "success",
            "tick_exit_code": 1,
        }
        for key, expected in exact_receipt.items():
            if receipt.get(key) != expected:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"historical run {run_id} receipt drifted: {key}"
                )
        safety = receipt.get("safety")
        if (
            type(safety) is not dict
            or set(safety) != set(activation.SAFETY_KEYS)
            or any(value is not False for value in safety.values())
        ):
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical run {run_id} receipt safety authority changed"
            )
        archive_bytes = verified["archive_bytes"]
        if (
            hashlib.sha256(archive_bytes).hexdigest() != archive_sha256
            or len(archive_bytes) != archive_size
        ):
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical run {run_id} inner archive digest or size changed"
            )
        with tempfile.TemporaryDirectory(prefix="athena-historical-pair-") as temporary:
            root = Path(temporary)
            archive_path = root / "durable-state.tar.gz"
            archive_path.write_bytes(archive_bytes)
            try:
                activation.verify_and_extract_durable_state_archive(
                    archive_path,
                    repository_root=root,
                    expected_sha256=archive_sha256,
                )
            except Exception as exc:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"historical run {run_id} durable archive proof failed"
                ) from exc
            state_root = root / activation.control.CONTROL_ROOT_RELATIVE
            names = {
                "capture": activation.control.CAPTURE_INDEX_FILENAME,
                "control": activation.control.CONTROL_JOURNAL_FILENAME,
                "prediction": activation.control.PREDICTION_JOURNAL_FILENAME,
                "identity": activation.control.POST_SEAL_IDENTITY_JOURNAL_FILENAME,
                "settlement": activation.control.SETTLEMENT_JOURNAL_FILENAME,
                "checkpoint": activation.control.CHECKPOINT_FILENAME,
            }
            state: dict[str, bytes] = {}
            for key, name in names.items():
                path = state_root / name
                if not path.is_file() or path.is_symlink():
                    raise audit.FreshHoldoutActionsLineageAuditError(
                        f"historical run {run_id} durable archive is missing {name}"
                    )
                state[key] = path.read_bytes()
        capture_rows = audit._canonical_rows(
            state["capture"], f"historical run {run_id} capture index"
        )
        control_rows = audit._canonical_rows(
            state["control"], f"historical run {run_id} control journal"
        )
        return artifact, state, capture_rows, control_rows

    canonical_artifact, canonical_state, canonical_capture, canonical_control = _read_attempt(
        run_id=_HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
        artifact_id=_HISTORICAL_CONTINUITY_ARTIFACT_ID,
        artifact_name=_HISTORICAL_CONTINUITY_ARTIFACT,
        artifact_digest=_HISTORICAL_CONTINUITY_ZIP_DIGEST,
        archive_sha256=_HISTORICAL_CONTINUITY_ARCHIVE_SHA256,
        archive_size=_HISTORICAL_CONTINUITY_ARCHIVE_SIZE,
    )
    auxiliary_artifact, auxiliary_state, auxiliary_capture, auxiliary_control = _read_attempt(
        run_id=_HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
        artifact_id=_HISTORICAL_NATURAL_ARTIFACT_ID,
        artifact_name=_HISTORICAL_NATURAL_ARTIFACT,
        artifact_digest=_HISTORICAL_NATURAL_ZIP_DIGEST,
        archive_sha256=_HISTORICAL_NATURAL_ARCHIVE_SHA256,
        archive_size=_HISTORICAL_NATURAL_ARCHIVE_SIZE,
    )

    # Validate both canonical state shapes before comparing them.  This uses
    # the frozen validator captured at import time, never the current
    # compatibility validator installed by current-history construction.
    if len(canonical_capture) != 663 or len(auxiliary_capture) != 666:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair capture row counts changed"
        )
    if len(canonical_control) != 715 or len(auxiliary_control) != 719:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair control row counts changed"
        )
    if auxiliary_state["capture"][: len(canonical_state["capture"])] != canonical_state["capture"]:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical natural capture index is not an exact canonical prefix"
        )
    if auxiliary_state["control"][: len(canonical_state["control"])] != canonical_state["control"]:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical natural control journal is not an exact canonical prefix"
        )
    for key, expected_rows in (
        ("prediction", 3136),
        ("identity", 6071),
        ("settlement", 166),
    ):
        canonical_lines = canonical_state[key].splitlines(keepends=True)
        auxiliary_lines = auxiliary_state[key].splitlines(keepends=True)
        if len(canonical_lines) != expected_rows or len(auxiliary_lines) != expected_rows:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical pair {key} row count changed"
            )
        if canonical_state[key] != auxiliary_state[key]:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical pair {key} journal is not byte-identical"
            )
    if canonical_state["checkpoint"] != auxiliary_state["checkpoint"]:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair checkpoint is not byte-identical"
        )

    def _provider_rows(
        rows: Sequence[Mapping[str, Any]],
        archive_name: str,
    ) -> tuple[Mapping[str, Any], ...]:
        selected = tuple(
            row for row in rows if row.get("durable_asset_name") == archive_name
        )
        if len(selected) != 3:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical archive {archive_name} does not contain exactly three provider captures"
            )
        if tuple(row.get("request_date") for row in selected) != _HISTORICAL_PROVIDER_REQUEST_DATES:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"historical archive {archive_name} request-date sequence changed"
            )
        for row in selected:
            if (
                row.get("network_acquisition_performed") is not True
                or row.get("preserved_from_uncommitted_tick") is not True
                or not _is_lower_sha256(row.get("raw_sha256"))
                or not _is_lower_sha256(row.get("manifest_sha256"))
            ):
                raise audit.FreshHoldoutActionsLineageAuditError(
                    f"historical archive {archive_name} provider acquisition evidence changed"
                )
        return selected

    canonical_provider_rows = _provider_rows(
        canonical_capture, _HISTORICAL_CONTINUITY_ARTIFACT
    )
    natural_capture_append = auxiliary_capture[len(canonical_capture) :]
    if len(natural_capture_append) != 3:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical natural capture append length changed"
        )
    auxiliary_provider_rows = _provider_rows(
        natural_capture_append, _HISTORICAL_NATURAL_ARTIFACT
    )
    if tuple(natural_capture_append) != auxiliary_provider_rows:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical natural capture append contains unexpected rows"
        )

    appended_control = auxiliary_control[len(canonical_control) :]
    if len(appended_control) != 4 or appended_control[0] != {
        "schema_version": 1,
        "event": "SCHEDULER_GAP_RANGE",
        "detected_at_scheduled_for_utc": "2026-09-04T00:07:00.000000Z",
        "previous_committed_tick_utc": "2026-09-03T22:07:00.000000Z",
        "first_missing_tick_utc": "2026-09-03T22:37:00.000000Z",
        "last_missing_tick_utc": "2026-09-03T23:37:00.000000Z",
        "missing_tick_count": 3,
        "backfill_authorized": False,
    }:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical natural control append gap changed"
        )
    for control_row, capture_row in zip(appended_control[1:], auxiliary_provider_rows):
        if (
            set(control_row)
            != {
                "schema_version",
                "event",
                "observed_at",
                "detail",
                "capture_raw_sha256",
                "capture_manifest_sha256",
                "tick_committed",
                "backfill_authorized",
            }
            or control_row.get("event") != "UNCOMMITTED_CAPTURE_QUALIFICATION_FAILED"
            or control_row.get("schema_version") != 1
            or control_row.get("observed_at") != capture_row.get("observed_at")
            or control_row.get("detail") != _HISTORICAL_DETAIL
            or control_row.get("capture_raw_sha256") != capture_row.get("raw_sha256")
            or control_row.get("capture_manifest_sha256") != capture_row.get("manifest_sha256")
            or control_row.get("tick_committed") is not False
            or control_row.get("backfill_authorized") is not False
        ):
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical natural control qualification append changed"
            )

    _ORIGINAL_VALIDATE_CONTROL_LINEAGE(canonical_control)

    # A third provider-attempting execution for this slot is not admissible.
    # Prove absence from the same cached universe and exact artifact metadata,
    # rather than relying on encounter order in the frozen audit.
    for candidate in values:
        candidate_id = candidate.get("id")
        if candidate_id in {
            _HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
            _HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
        }:
            continue
        target_texts = {
            candidate.get("nominal_slot_utc"),
            candidate.get("nominal_scheduled_for_utc"),
            candidate.get("target_slot"),
            candidate.get("scheduled_for_utc"),
        }
        title_text = " ".join(
            text
            for text in (candidate.get("name"), candidate.get("display_title"))
            if type(text) is str
        )
        if (
            _HISTORICAL_SAME_SLOT_UTC in target_texts
            or _HISTORICAL_SAME_SLOT_SECONDS in target_texts
            or (
                "target=2026-09-04T00:07:00Z" in title_text
            )
        ):
            raise audit.FreshHoldoutActionsLineageAuditError(
                "third execution claims the historical nominal slot"
            )
        if (
            candidate.get("workflow_id") == _HISTORICAL_SAME_SLOT_WORKFLOW_ID
            and candidate.get("path") in {
                _HISTORICAL_SAME_SLOT_WORKFLOW_PATH,
                f"{_HISTORICAL_SAME_SLOT_WORKFLOW_PATH}@{candidate.get('head_sha', '')}",
            }
            and candidate.get("event") in {"schedule", "workflow_dispatch"}
            and candidate.get("head_branch") == "main"
        ):
            payload = get_run_artifacts(candidate_id)
            if (
                type(payload) is not dict
                or type(payload.get("artifacts")) is not list
                or (
                    "total_count" in payload
                    and payload.get("total_count") != len(payload["artifacts"])
                )
            ):
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "could not prove absence of a third historical artifact"
                )
            for item in payload["artifacts"]:
                if type(item) is not dict or type(item.get("name")) is not str:
                    raise audit.FreshHoldoutActionsLineageAuditError(
                        "third historical artifact metadata is malformed"
                    )
                name = item["name"]
                if name.startswith(f"failure-{_HISTORICAL_SAME_SLOT_COMPACT}-") or name.startswith(
                    f"success-{_HISTORICAL_SAME_SLOT_COMPACT}-"
                ):
                    raise audit.FreshHoldoutActionsLineageAuditError(
                        "third execution exposes an artifact for the historical slot"
                    )

    return HistoricalSameSlotProviderDuplicateProof(
        canonical_run_id=_HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
        auxiliary_run_id=_HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
        nominal_slot_utc=_HISTORICAL_SAME_SLOT_UTC,
        canonical_archive_name=_HISTORICAL_CONTINUITY_ARTIFACT,
        canonical_archive_sha256=_HISTORICAL_CONTINUITY_ARCHIVE_SHA256,
        canonical_archive_size_bytes=_HISTORICAL_CONTINUITY_ARCHIVE_SIZE,
        auxiliary_archive_name=_HISTORICAL_NATURAL_ARTIFACT,
        auxiliary_archive_sha256=_HISTORICAL_NATURAL_ARCHIVE_SHA256,
        auxiliary_archive_size_bytes=_HISTORICAL_NATURAL_ARCHIVE_SIZE,
        canonical_actions_artifact_id=_HISTORICAL_CONTINUITY_ARTIFACT_ID,
        canonical_actions_digest=_HISTORICAL_CONTINUITY_ZIP_DIGEST,
        auxiliary_actions_artifact_id=_HISTORICAL_NATURAL_ARTIFACT_ID,
        auxiliary_actions_digest=_HISTORICAL_NATURAL_ZIP_DIGEST,
        provider_acquisition_count_canonical=len(canonical_provider_rows),
        provider_acquisition_count_auxiliary=len(auxiliary_provider_rows),
        _token=_HISTORICAL_PROOF_TOKEN,
    )


def _prove_exact_legacy_queued_no_execution_dispatch(
    run: Mapping[str, Any],
    *,
    get_run_artifacts,
    get_run_jobs,
) -> bool:
    """Prove the one historical queued dispatch never reached execution."""
    if run.get("id") != LEGACY_QUEUED_NO_EXECUTION_RUN_ID:
        return False
    expected = {
        "name": LEGACY_QUEUED_NO_EXECUTION_TITLE,
        "display_title": LEGACY_QUEUED_NO_EXECUTION_TITLE,
        "workflow_id": continuity.PRIMARY_WORKFLOW_ID,
        "path": continuity.PRIMARY_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": LEGACY_QUEUED_NO_EXECUTION_HEAD_SHA,
        "status": "queued",
        "conclusion": None,
        "run_number": LEGACY_QUEUED_NO_EXECUTION_RUN_NUMBER,
        "run_attempt": 1,
        "created_at": LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
        "updated_at": LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
        "run_started_at": LEGACY_QUEUED_NO_EXECUTION_CREATED_AT,
    }
    for key, value in expected.items():
        if run.get(key) != value:
            raise audit.FreshHoldoutActionsLineageAuditError(
                f"legacy queued dispatch metadata drifted: {key}"
            )

    artifacts = get_run_artifacts(LEGACY_QUEUED_NO_EXECUTION_RUN_ID)
    if (
        not isinstance(artifacts, Mapping)
        or artifacts.get("total_count") != 0
        or artifacts.get("artifacts") != []
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "legacy queued dispatch unexpectedly acquired artifact evidence"
        )
    jobs = get_run_jobs(LEGACY_QUEUED_NO_EXECUTION_RUN_ID)
    if (
        not isinstance(jobs, Mapping)
        or jobs.get("total_count") != 0
        or jobs.get("jobs") != []
    ):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "legacy queued dispatch unexpectedly acquired execution jobs"
        )
    return True


def _prove_continuity_candidate(
    run: Mapping[str, Any],
    *,
    get_run_by_id,
    get_run_jobs,
) -> continuity.ContinuityPlan:
    """Replay the immutable prospective dispatch provenance before audit admission."""
    title = run.get("display_title")
    match = (
        receipt_mirror.CONTINUITY_RUN_NAME_RE.fullmatch(title)
        if type(title) is str
        else None
    )
    if match is None:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "workflow_dispatch run escaped continuity provenance grammar"
        )
    source_run_id = int(match.group(1))
    dispatch_sha = run.get("head_sha")
    try:
        # A continuity observation remains historical evidence after main moves.
        # Its exact execution SHA, not audit-time main, binds both executions.
        continuity.validate_watchdog_source_jobs(
            get_run_jobs(source_run_id),
            expected_run_id=source_run_id,
            expected_main_sha=dispatch_sha,
        )
        return continuity.validate_continuity_dispatch(
            watchdog_run=get_run_by_id(source_run_id),
            dispatch_run=run,
            source_watchdog_run_id=source_run_id,
            current_main_sha=dispatch_sha,
            requested_target_slot=match.group(2),
            requested_target_cron=match.group(3),
            confirmation=match.group(4),
        )
    except continuity.FreshHoldoutContinuityError as exc:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity dispatch provenance replay failed"
        ) from exc


def _audit_actions_lineage_compatible(*args, **kwargs):
    """Run the unchanged engine across reviewed current-only projections."""
    if args:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "schedule-recovery projection requires keyword audit arguments"
        )

    # get_run_by_id belongs to this compatibility projection only. Consume it
    # before any delegation so the frozen raw audit signature stays untouched.
    get_run_by_id = kwargs.pop("get_run_by_id", None)
    get_run_artifacts = kwargs.get("get_run_artifacts")
    get_run_jobs = kwargs.get("get_run_jobs")
    if not callable(get_run_artifacts) or not callable(get_run_jobs):
        return _ORIGINAL_AUDIT_ACTIONS_LINEAGE(**kwargs)
    original_get_runs_page = kwargs.get("get_runs_page")
    # The production/current audit path always supplies the reviewed paginated
    # run reader.  A few legacy projection-only callers exercise the historical
    # queued/no-execution compatibility with a stub audit and intentionally do
    # not provide that reader (or an Actions ZIP transport).  Such a caller
    # cannot possibly authorize the historical pair, so preserve the old
    # projection API but leave the pair proof absent.  Whenever the reviewed
    # page path is present, the ZIP transport is mandatory and the complete
    # preflight below runs before the frozen audit.
    download_artifact_zip = kwargs.get("download_artifact_zip")
    if callable(original_get_runs_page) and not callable(download_artifact_zip):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "historical pair artifact ZIP reader must be callable"
        )
    if get_run_by_id is None:
        repository = kwargs.get("repository")
        get_run_by_id = lambda run_id: _fixed_get_run_by_id(repository, run_id)
    elif not callable(get_run_by_id):
        raise audit.FreshHoldoutActionsLineageAuditError(
            "continuity exact-run reader must be callable"
        )

    artifact_cache: dict[int, Mapping[str, Any]] = {}
    jobs_cache: dict[int, Mapping[str, Any]] = {}
    zip_cache: dict[int, bytes] = {}

    def cached_artifacts(run_id: int) -> Mapping[str, Any]:
        if run_id not in artifact_cache:
            artifact_cache[run_id] = get_run_artifacts(run_id)
        return artifact_cache[run_id]

    def cached_jobs(run_id: int) -> Mapping[str, Any]:
        if run_id not in jobs_cache:
            jobs_cache[run_id] = get_run_jobs(run_id)
        return jobs_cache[run_id]

    def cached_zip(artifact_id: int) -> bytes:
        if artifact_id not in zip_cache:
            zip_cache[artifact_id] = download_artifact_zip(artifact_id)
        return zip_cache[artifact_id]

    # Prefetch the exact bounded pagination universe before installing the
    # candidate predicate.  The frozen audit evaluates that predicate before
    # sorting; proving the one historical pair here makes its projection
    # independent of GitHub page/run encounter order.
    cached_universe: _CachedWorkflowRunUniverse | None = None
    historical_pair_proof: HistoricalSameSlotProviderDuplicateProof | None = None
    if callable(original_get_runs_page):
        cached_universe = _prefetch_workflow_run_universe(original_get_runs_page)
    # No page universe means no historical pair can be admitted.  The frozen
    # delegate remains responsible for its own page-reader contract when this
    # compatibility helper is used outside the normal production path.
    historical_ids = {
        value.get("id") for value in cached_universe.runs if type(value) is dict
    } if cached_universe is not None else set()
    if {
        _HISTORICAL_SAME_SLOT_CONTINUITY_RUN_ID,
        _HISTORICAL_SAME_SLOT_NATURAL_RUN_ID,
    }.issubset(historical_ids):
        historical_pair_proof = _prove_exact_historical_same_slot_provider_duplicate(
            run_universe=cached_universe,
            get_run_by_id=get_run_by_id,
            get_run_artifacts=cached_artifacts,
            download_artifact_zip=cached_zip,
            get_run_jobs=cached_jobs,
        )
        if historical_pair_proof is None:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "historical same-slot pair was present but could not be proven"
            )

    projected_noops: dict[int, Mapping[str, Any]] = {}
    projected_schedule_duplicates: dict[int, Mapping[str, Any]] = {}
    projected_historical_provider_duplicates: dict[
        int, HistoricalSameSlotProviderDuplicateProof
    ] = {}
    projected_continuity_noops: dict[int, Mapping[str, Any]] = {}
    projected_preacquisition: dict[int, Mapping[str, Any]] = {}
    projected_legacy_queued: dict[int, Mapping[str, Any]] = {}
    projected_continuities: dict[int, continuity.ContinuityPlan] = {}

    def projected_candidate(run: Mapping[str, Any]) -> bool:
        # This decision is based solely on the complete preflight proof, never
        # on whether the continuity run happened to be encountered first.
        if (
            historical_pair_proof is not None
            and run.get("id") == historical_pair_proof.auxiliary_run_id
        ):
            projected_historical_provider_duplicates[run["id"]] = (
                historical_pair_proof
            )
            return False
        if not _ORIGINAL_RUN_IS_COLLECTION_CANDIDATE(run):
            if run.get("event") != "workflow_dispatch":
                return False
            if (
                run.get("workflow_id") != continuity.PRIMARY_WORKFLOW_ID
                or run.get("path") not in {
                    continuity.PRIMARY_WORKFLOW_PATH,
                    f"{continuity.PRIMARY_WORKFLOW_PATH}@{run.get('head_sha', '')}",
                }
                or run.get("head_branch") != "main"
            ):
                return False
            run_id = run.get("id")
            if type(run_id) is not int or run_id <= 0:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "continuity dispatch run id is invalid"
                )
            if _prove_exact_legacy_queued_no_execution_dispatch(
                run,
                get_run_artifacts=cached_artifacts,
                get_run_jobs=cached_jobs,
            ):
                projected_legacy_queued[run_id] = run
                return False
            projected_continuities[run_id] = _prove_continuity_candidate(
                run,
                get_run_by_id=get_run_by_id,
                get_run_jobs=cached_jobs,
            )
            if run.get("status") == "completed" and run.get("conclusion") == "success":
                continuity_artifacts = cached_artifacts(run_id)
                try:
                    continuity_noop = recovery._prove_continuity_duplicate_no_acquisition_success(
                        run,
                        continuity_artifacts,
                        cached_jobs,
                    )
                except recovery.FreshHoldoutFailureLineageError as exc:
                    raise audit.FreshHoldoutActionsLineageAuditError(
                        "continuity duplicate no-acquisition proof failed for run "
                        f"{run_id}"
                    ) from exc
                if continuity_noop:
                    projected_continuity_noops[run_id] = run
                    projected_continuities.pop(run_id, None)
                    return False
            elif run.get("status") == "completed" and run.get("conclusion") == "failure":
                continuity_artifacts = cached_artifacts(run_id)
                try:
                    continuity_preacquisition = (
                        recovery._prove_continuity_preacquisition_control_failure(
                            run,
                            continuity_artifacts,
                            cached_jobs,
                        )
                    )
                except recovery.FreshHoldoutFailureLineageError as exc:
                    raise audit.FreshHoldoutActionsLineageAuditError(
                        "continuity pre-acquisition failure proof failed for run "
                        f"{run_id}"
                    ) from exc
                if continuity_preacquisition:
                    projected_preacquisition[run_id] = run
                    projected_continuities.pop(run_id, None)
                    return False
            return True
        run_id = run.get("id")
        if run.get("status") != "completed" or type(run_id) is not int or run_id <= 0:
            return True

        artifacts = cached_artifacts(run_id)
        if run.get("conclusion") == "success":
            if recovery._prove_schedule_duplicate_no_acquisition_success(
                run,
                artifacts,
                cached_jobs,
            ):
                projected_schedule_duplicates[run_id] = run
                return False
            if recovery._prove_ambiguous_no_acquisition_success(
                run,
                artifacts,
                cached_jobs,
            ):
                projected_noops[run_id] = run
                return False
        elif run.get("conclusion") == "failure":
            try:
                proved_preacquisition = (
                    audit.failure_lineage._prove_preacquisition_control_failure(
                        run,
                        artifacts,
                        cached_jobs,
                    )
                )
            except audit.failure_lineage.FreshHoldoutFailureLineageError as exc:
                raise audit.FreshHoldoutActionsLineageAuditError(
                    "pre-acquisition control-failure projection proof failed for run "
                    f"{run_id}: {exc}"
                ) from exc
            if proved_preacquisition:
                projected_preacquisition[run_id] = run
                return False
        return True

    previous_candidate = audit._run_is_collection_candidate
    audit._run_is_collection_candidate = projected_candidate
    projected_kwargs = dict(kwargs)
    if cached_universe is not None:
        projected_kwargs["get_runs_page"] = cached_universe.reader
    projected_kwargs["get_run_artifacts"] = cached_artifacts
    if callable(download_artifact_zip):
        projected_kwargs["download_artifact_zip"] = cached_zip
    projected_kwargs["get_run_jobs"] = cached_jobs
    try:
        result = _ORIGINAL_AUDIT_ACTIONS_LINEAGE(**projected_kwargs)
    finally:
        audit._run_is_collection_candidate = previous_candidate

    result = dict(result)
    if historical_pair_proof is not None:
        # Retain the auxiliary execution even when the raw candidate predicate
        # happens not to visit it (for example an older GitHub response omits
        # the workflow-name field used by the frozen schedule predicate).
        projected_historical_provider_duplicates[
            historical_pair_proof.auxiliary_run_id
        ] = historical_pair_proof
    for record in result.get("runs", []):
        if type(record) is not dict:
            continue
        plan = projected_continuities.get(record.get("run_id"))
        if plan is None:
            continue
        if record.get("nominal_slot_utc") != plan.target_slot_text:
            raise audit.FreshHoldoutActionsLineageAuditError(
                "continuity artifact nominal slot differs from authenticated target"
            )
        record["execution_provenance"] = "PROSPECTIVE_CONTINUITY_DISPATCH"
        record["continuity_target_slot"] = plan.target_slot_text
        record["continuity_target_cron"] = plan.target_cron
    if projected_continuities:
        result["verified_prospective_continuity_dispatch_count"] = len(
            projected_continuities
        )
    ordered_noops = sorted(
        projected_noops.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    ordered_preacquisition = sorted(
        projected_preacquisition.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    result["verified_ambiguous_no_acquisition_count"] = len(ordered_noops)
    result["projected_ambiguous_no_acquisition_runs"] = [
        _projected_noop_record(run) for run in ordered_noops
    ]
    ordered_schedule_duplicates = sorted(
        projected_schedule_duplicates.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    if ordered_schedule_duplicates:
        result["verified_schedule_duplicate_no_acquisition_count"] = len(
            ordered_schedule_duplicates
        )
        result["projected_schedule_duplicate_no_acquisition_runs"] = [
            _projected_noop_record(run) for run in ordered_schedule_duplicates
        ]
    if projected_historical_provider_duplicates:
        result["verified_same_slot_provider_duplicate_count"] = len(projected_historical_provider_duplicates)
        result["projected_same_slot_provider_duplicate_runs"] = [
            {
                "run_id": proof.auxiliary_run_id,
                "canonical_run_id": proof.canonical_run_id,
                "nominal_slot_utc": proof.nominal_slot_utc,
                "evidence_state": "VERIFIED_DUPLICATE_SAME_SLOT_PROVIDER_ATTEMPT",
                "execution_provenance": "DELAYED_NATURAL_DUPLICATE_PROVIDER_ATTEMPT",
                "provider_acquisition_performed": True,
                "provider_acquisition_count": proof.provider_acquisition_count_auxiliary,
                "tick_committed": False,
                "archive_name": proof.auxiliary_archive_name,
                "archive_sha256": proof.auxiliary_archive_sha256,
                "archive_size_bytes": proof.auxiliary_archive_size_bytes,
                "actions_artifact_id": proof.auxiliary_actions_artifact_id,
                "actions_artifact_digest": proof.auxiliary_actions_digest,
            }
            for proof in sorted(
                projected_historical_provider_duplicates.values(),
                key=lambda value: value.auxiliary_run_id,
            )
        ]
    ordered_continuity_noops = sorted(
        projected_continuity_noops.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    if ordered_continuity_noops:
        result["verified_continuity_duplicate_no_acquisition_count"] = len(
            ordered_continuity_noops
        )
        result["projected_continuity_duplicate_no_acquisition_runs"] = [
            _projected_continuity_noop_record(run)
            for run in ordered_continuity_noops
        ]
    ordered_legacy_queued = sorted(
        projected_legacy_queued.values(),
        key=lambda run: (str(run.get("created_at")), int(run.get("id", 0))),
    )
    if ordered_legacy_queued:
        result["verified_legacy_queued_no_execution_count"] = len(
            ordered_legacy_queued
        )
        result["projected_legacy_queued_no_execution_runs"] = [
            _projected_legacy_queued_no_execution_record(run)
            for run in ordered_legacy_queued
        ]

    existing_preacquisition = result.get(
        "verified_preacquisition_control_failure_count", 0
    )
    if type(existing_preacquisition) is not int or existing_preacquisition < 0:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "audit engine returned invalid pre-acquisition control-failure count"
        )
    result["verified_preacquisition_control_failure_count"] = (
        existing_preacquisition + len(ordered_preacquisition)
    )
    result["projected_preacquisition_control_failure_runs"] = [
        _projected_preacquisition_record(run) for run in ordered_preacquisition
    ]
    if (
        ordered_preacquisition
        and result.get("audit_state") == "NO_COMPLETED_CAMPAIGN_EVIDENCE"
    ):
        # Preserve the base engine's historical semantics: a proven failed control
        # attempt before Genesis is verified metadata, but there is still no nominal
        # source observation to promote into completed campaign evidence.
        result["audit_state"] = "PARTIAL_UNVERIFIED_GITHUB_LINEAGE"
    return result


def _verify_projection_dependencies() -> None:
    repo = Path(__file__).resolve().parents[1]
    helper = repo / SCHEDULE_RECOVERY_PATH
    if not helper.is_file() or helper.is_symlink():
        raise audit.FreshHoldoutActionsLineageAuditError(
            "schedule-recovery helper path is unavailable"
        )
    if _git_blob_sha(helper) != SCHEDULE_RECOVERY_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "schedule-recovery helper blob changed"
        )


def main(argv: Sequence[str] | None = None) -> int:
    if audit.WORKFLOW_BLOB_SHA != pr175.PRE_PR175_WORKFLOW_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine workflow pin drifted before schedule-recovery projection"
        )
    if audit.FAILURE_LINEAGE_BLOB_SHA != pr175.PRE_PREACQUISITION_FALLBACK_BLOB_SHA:
        raise audit.FreshHoldoutActionsLineageAuditError(
            "reviewed audit engine failure-lineage pin drifted before schedule-recovery projection"
        )
    _verify_projection_dependencies()
    audit.WORKFLOW_BLOB_SHA = POST_AMBIGUOUS_NOOP_WORKFLOW_BLOB_SHA
    audit.FAILURE_LINEAGE_BLOB_SHA = pr175.POST_PREACQUISITION_FALLBACK_BLOB_SHA
    audit._gh_download = pr175._gh_download_compatible
    audit.audit_actions_lineage = _audit_actions_lineage_compatible
    return audit.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
