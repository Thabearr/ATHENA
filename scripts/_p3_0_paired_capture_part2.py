from scripts._p3_0_paired_capture_part1 import *  # noqa: F401,F403


def _legacy_observations(
    sources: Sequence[Any],
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]]]:
    """Run each exact fixture independently so filtered/error rows cannot shift
    positional pairing or be attached to a different canonical fixture.
    """
    pipeline = _legacy_pipeline()
    by_fixture: dict[str, Mapping[str, Any]] = {}
    incomplete: list[dict[str, Any]] = []
    for source in sources:
        observer = evidence.LegacyEvidenceObserver()
        exported = pipeline.run_pipeline_snapshot(
            override_fixtures=[_legacy_override_fixture(source)],
            evidence_observer=observer,
        )
        observations = observer.observations()
        if len(observations) != 1 or len(exported) != 1:
            incomplete.append({
                "failure_code": evidence.LEGACY_EVIDENCE_OBSERVER_INCOMPLETE,
                "fixture_identity": source.fixture_identity,
                "provider_event_id": source.provider_event_id,
                "observation_count": len(observations),
                "exported_row_count": len(exported),
            })
            continue
        observation = observations[0]
        legacy_input = observation["legacy_input"]
        legacy_fixture_id = legacy_input["fixture_id"]
        if type(legacy_fixture_id) is not int or legacy_fixture_id <= 0:
            raise P30PairedCaptureError("legacy observer fixture ID is not exact positive integer")
        fixture_identity = f"FOTMOB:{legacy_fixture_id}"
        state = _fixture_state(source)
        if (
            fixture_identity != source.fixture_identity
            or legacy_input.get("home_team") != state["home_team"]
            or legacy_input.get("away_team") != state["away_team"]
            or legacy_input.get("match_date") != state["kickoff_utc"]
        ):
            raise P30PairedCaptureError("legacy observer fixture projection drifted")
        if fixture_identity in by_fixture:
            raise P30PairedCaptureError("legacy observer emitted duplicate fixture identity")
        by_fixture[fixture_identity] = observation
    return by_fixture, incomplete


def _legacy_identity(source: Any, observation: Mapping[str, Any]) -> dict[str, Any]:
    state = _fixture_state(source)
    legacy_input = observation["legacy_input"]
    if (
        legacy_input.get("fixture_id") != _legacy_fixture_id(source)
        or legacy_input.get("home_team") != state["home_team"]
        or legacy_input.get("away_team") != state["away_team"]
        or legacy_input.get("match_date") != state["kickoff_utc"]
    ):
        raise P30PairedCaptureError("legacy/canonical fixture identity is not exact")
    return _fixture_identity(source)


def _artifact_hashes(repository_root: Path) -> dict[str, Any]:
    return {
        "repository_commit_sha": _git_head(repository_root),
        "athena_database_sha256": _hash_if_file(repository_root / "database" / "athena.db"),
        "model_weights_sha256": _hash_if_file(repository_root / "config" / "model_weights.json"),
        "goals_model_sha256": _hash_if_file(repository_root / "models" / "goals_model.joblib"),
    }


_ZERO_ROUTER_DIAGNOSTIC_PREFIX = "P3.0-E1 source acquisition produced zero Router inputs: "


def _require_nonempty_router_inputs(sources_bundle: Any) -> None:
    """Fail closed when source acquisition cannot yield one exact Router input.

    The Current Shadow source bundle already carries bounded reconciliation counts.
    Preserve those counts in the failure message so the hosted failure artifact can
    identify the next evidence boundary without another provider acquisition.
    """
    router_inputs = getattr(sources_bundle, "router_inputs", None)
    if type(router_inputs) is not tuple:
        raise P30PairedCaptureError("P3.0-E1 source bundle router_inputs is malformed")
    if router_inputs:
        return

    def checked_count(name: str) -> int:
        value = getattr(sources_bundle, name, None)
        if type(value) is not int or value < 0:
            raise P30PairedCaptureError(
                f"P3.0-E1 zero Router input diagnostic is malformed: {name}"
            )
        return value

    top_counts = {
        "reviewed_fixture_count": checked_count("reviewed_fixture_count"),
        "reconciled_fixture_count": checked_count("reconciled_fixture_count"),
        "provider_event_count": checked_count("provider_event_count"),
        "priced_fixture_count": checked_count("priced_fixture_count"),
    }
    summary = getattr(sources_bundle, "source_summary", None)
    if not isinstance(summary, Mapping):
        raise P30PairedCaptureError(
            "P3.0-E1 zero Router input diagnostic is malformed: source_summary"
        )
    source_count_fields = (
        "provider_event_count",
        "provider_prematch_bookable_count",
        "provider_inplay_count",
        "provider_future_lead_eligible_count",
        "provider_too_close_count",
    )
    source_counts: dict[str, int] = {}
    for field in source_count_fields:
        value = summary.get(field)
        if type(value) is not int or value < 0:
            raise P30PairedCaptureError(
                f"P3.0-E1 zero Router input diagnostic is malformed: {field}"
            )
        source_counts[field] = value
    source_method = summary.get("provider_discovery_source_method")
    source_strategy = summary.get("provider_discovery_strategy_id")
    source_observed_at = summary.get("provider_discovery_observed_at")
    source_viability = summary.get("source_viability")
    if (
        type(source_method) is not str
        or not source_method
        or type(source_strategy) is not str
        or not source_strategy
        or type(source_observed_at) is not str
        or not source_observed_at
        or type(source_viability) is not str
        or not source_viability
    ):
        raise P30PairedCaptureError(
            "P3.0-E1 zero Router input diagnostic is malformed: provider discovery identity"
        )
    reconciliation_by_date = summary.get("current_reconciliation_by_request_date")
    if not isinstance(reconciliation_by_date, Mapping) or not reconciliation_by_date:
        raise P30PairedCaptureError(
            "P3.0-E1 zero Router input diagnostic is malformed: reconciliation_by_date"
        )

    request_date_counts: dict[str, dict[str, int]] = {}
    disposition_totals: dict[str, int] = {}
    for request_date in sorted(reconciliation_by_date):
        if (
            type(request_date) is not str
            or len(request_date) != 8
            or not request_date.isdigit()
        ):
            raise P30PairedCaptureError(
                "P3.0-E1 zero Router input diagnostic is malformed: request_date"
            )
        row = reconciliation_by_date[request_date]
        if not isinstance(row, Mapping):
            raise P30PairedCaptureError(
                "P3.0-E1 zero Router input diagnostic is malformed: reconciliation_row"
            )
        provider_count = row.get("provider_event_count")
        reconciled_count = row.get("reconciled_fixture_count")
        if (
            type(provider_count) is not int
            or provider_count < 0
            or type(reconciled_count) is not int
            or reconciled_count < 0
        ):
            raise P30PairedCaptureError(
                "P3.0-E1 zero Router input diagnostic is malformed: request_date_counts"
            )
        row_source_counts: dict[str, int] = {}
        for field in source_count_fields[1:]:
            value = row.get(field)
            if type(value) is not int or value < 0:
                raise P30PairedCaptureError(
                    f"P3.0-E1 zero Router input diagnostic is malformed: {field}"
                )
            row_source_counts[field] = value
        request_date_counts[request_date] = {
            "provider_event_count": provider_count,
            **row_source_counts,
            "reconciled_fixture_count": reconciled_count,
        }

        dispositions = row.get("disposition_counts")
        if not isinstance(dispositions, Mapping):
            raise P30PairedCaptureError(
                "P3.0-E1 zero Router input diagnostic is malformed: disposition_counts"
            )
        for disposition in sorted(dispositions):
            count = dispositions[disposition]
            if type(disposition) is not str or not disposition or type(count) is not int or count < 0:
                raise P30PairedCaptureError(
                    "P3.0-E1 zero Router input diagnostic is malformed: disposition_row"
                )
            disposition_totals[disposition] = disposition_totals.get(disposition, 0) + count

    if (
        top_counts["provider_event_count"] > 0
        and source_counts["provider_prematch_bookable_count"] == 0
    ):
        failure_code = "PROVIDER_DISCOVERY_NO_PREMATCH_EVENTS"
    elif top_counts["provider_event_count"] == 0:
        failure_code = "NO_RECONCILED_PROVIDER_EVENTS_DISCOVERED"
    elif top_counts["reconciled_fixture_count"] == 0:
        failure_code = "NO_RECONCILIATION_AUTHORIZED_FOTMOB_COUNTERPART"
    elif top_counts["priced_fixture_count"] == 0:
        failure_code = "NO_MARKETS_RECONCILED_FOR_ROUTER"
    else:
        failure_code = "ZERO_ROUTER_INPUTS_POST_PRICING"

    diagnostic = {
        "failure_code": failure_code,
        **top_counts,
        **source_counts,
        "provider_discovery_source_method": source_method,
        "provider_discovery_strategy_id": source_strategy,
        "provider_discovery_observed_at": source_observed_at,
        "source_viability": source_viability,
        "request_date_counts": request_date_counts,
        "disposition_totals": {key: disposition_totals[key] for key in sorted(disposition_totals)},
    }

    def encoded(value: Mapping[str, Any]) -> str:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    payload = encoded(diagnostic)
    if len(_ZERO_ROUTER_DIAGNOSTIC_PREFIX) + len(payload) > FAILURE_MESSAGE_MAX_CHARS:
        payload = encoded({
            "failure_code": failure_code,
            **top_counts,
            **source_counts,
            "provider_discovery_source_method": source_method,
            "provider_discovery_strategy_id": source_strategy,
            "provider_discovery_observed_at": source_observed_at,
            "source_viability": source_viability,
            "request_date_count": len(request_date_counts),
            "disposition_totals": diagnostic["disposition_totals"],
        })
    if len(_ZERO_ROUTER_DIAGNOSTIC_PREFIX) + len(payload) > FAILURE_MESSAGE_MAX_CHARS:
        payload = encoded({"failure_code": failure_code, **top_counts})
    message = _ZERO_ROUTER_DIAGNOSTIC_PREFIX + payload
    if len(message) > FAILURE_MESSAGE_MAX_CHARS:
        raise P30PairedCaptureError(
            "P3.0-E1 zero Router input diagnostic exceeded the failure-message bound"
        )
    raise P30PairedCaptureError(message)


def execute_capture(*, request_dates: tuple[str, ...], fixture_cap: int,
                    output_dir: Path, repository_root: Path | None = None) -> Mapping[str, Any]:
    if type(fixture_cap) is not int or not 1 <= fixture_cap <= MAX_FIXTURE_CAP:
        raise P30PairedCaptureError("fixture_cap must be an integer from 1 through 50")
    root = repository_root or Path(__file__).resolve().parents[1]
    exact_commit_sha = _git_head(root)
    lineage_main_sha = _lineage_main_sha()
    started = _now()
    started_text = _iso(started)
    capture_id = f"p3-0-e1-{exact_commit_sha[:12]}-{started.strftime('%Y%m%dT%H%M%S%fZ')}"
    bindings = shadow_core_adapter.resolve_shadow_canonical_core()
    authority = _authority_projection(bindings)
    sources_bundle = _collect_sources(
        repository_root=root, lineage_main_sha=lineage_main_sha,
        request_dates=request_dates,
    )
    _require_nonempty_router_inputs(sources_bundle)
    selected_sources = tuple(sorted(
        sources_bundle.router_inputs,
        key=lambda source: (source.fixture_identity, source.provider_event_id),
    ))[:fixture_cap]
    legacy_by_fixture, legacy_incompleteness = _legacy_observations(selected_sources)
    completed = _now()
    completed_text = _iso(completed)
    records = []
    artifacts = []
    for source in selected_sources:
        fixture_id = _fixture_identity(source)
        legacy = legacy_by_fixture.get(source.fixture_identity)
        legacy_fixture_id = None if legacy is None else _legacy_identity(source, legacy)
        probability = _probability_projection(source)
        provider = _provider_projection(source)
        quotes = _quote_projection(source)
        price = _price_projection(source)
        router = _router_projection(source)
        quote_times = sorted({row["observed_at"] for row in quotes["quotes"]})
        timing = {
            # The supported legacy pipeline exposes no independent internal
            # model clock.  The observer timestamp is the exact point at which
            # its completed decision became observable in this capture, so it
            # is the fail-closed effective legacy evaluation point.
            "legacy_evidence_observed_at": None if legacy is None else legacy["observed_at"],
            "legacy_evaluation_time": None if legacy is None else legacy["observed_at"],
            "probability_evaluation_time": source.price_all_bundle.to_dict()["evaluation_time"],
            "provider_quote_observed_at": (
                quote_times[0]
                if len(quote_times) == 1
                else _iso(source.source_observed_at)
                if not quote_times
                else None
            ),
            "canonical_price_all_evaluation_time": source.price_all_bundle.to_dict()["evaluation_time"],
            # The P2.1 compatibility Router is pure over the verified Price-All
            # bundle and acquires no second wall clock.  Its effective as-of
            # point is therefore the exact Price-All evaluation timestamp.
            "canonical_router_evaluation_time": source.price_all_bundle.to_dict()["evaluation_time"],
            "kickoff_time": _iso(source.kickoff_utc),
        }
        record = evidence.build_fixture_record(
            source.fixture_identity.replace(":", "-"),
            capture_id=capture_id,
            capture_started_at=started_text,
            capture_completed_at=completed_text,
            legacy_identity=legacy_fixture_id,
            canonical_identity=fixture_id,
            timing=timing,
            canonical_authority=authority,
            legacy_input=None if legacy is None else legacy["legacy_input"],
            legacy_output=None if legacy is None else legacy["legacy_output"],
            canonical_fixture_state=_fixture_state(source),
            probability_bundle=probability,
            provider_semantics=provider,
            quote_snapshot=quotes,
            price_all_output=price,
            router_output=router,
        )
        records.append(record)
        artifacts.extend(_source_artifacts(source))
    if selected_sources and not records:
        raise P30PairedCaptureError(
            "P3.0-E1 zero fixture records after non-empty source selection"
        )
    bundle = evidence.build_capture_bundle(
        repository_commit_sha=exact_commit_sha,
        capture_id=capture_id,
        capture_started_at=started_text,
        capture_completed_at=completed_text,
        requested_dates=request_dates,
        legacy_execution_identity={
            "policy_id": POLICY_ID,
            "supported_path": "AccaBuilder->AnalysisPipeline.run_pipeline_snapshot->MatchAnalyst.compile_master_fixture_prediction->AccaFilter/Accumulator",
            "capture_mode": "AnalysisPipeline override_fixtures plus default-off evidence observer",
            "runtime_artifacts": _artifact_hashes(root),
            "replayability_claim": "CAPTURED_OUTPUT_ONLY_NO_FULL_HISTORICAL_REEXECUTION_CLAIM",
            "legacy_observer_incompleteness": legacy_incompleteness,
        },
        canonical_execution_identity={
            "policy_id": POLICY_ID,
            "source_path": "current_shadow_all_market_runner._acquire_router_inputs",
            "stopped_after": "PRICE_ALL_ROUTER",
            "canonical_core_policy_id": bindings.policy_id,
            "canonical_core_bindings_sha256": bindings.canonical_sha256,
            "authority_profile": bindings.authority_profile,
            "portfolio_optimization_invoked": False,
            "share_code_invoked": False,
        },
        authority_state={
            "authority_profile": "SHADOW", "main_authority": False,
            "provider_acquisition": True, "portfolio_optimization": False,
            "share_code_generation": False, "login": False, "cookies": False,
            "wallet": False, "staking": False, "wager_placed": False,
        },
        source_artifacts=artifacts,
        fixture_records=records,
    )
    try:
        evidence.write_capture_artifact(bundle, output_dir)
    except Exception as exc:
        publication_err = P30PairedCaptureError(
            f"CAPTURE_ARTIFACT_PUBLICATION_FAILED: {type(exc).__name__}: {exc}"
        )
        publication_err.failure_code = evidence.CAPTURE_ARTIFACT_PUBLICATION_FAILED  # type: ignore[attr-defined]
        raise publication_err from exc
    return bundle


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    root = Path(__file__).resolve().parents[1]
    exact_sha: str | None = None
    started = _iso(_now())
    capture_id = f"p3-0-e1-failed-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    try:
        exact_sha = _git_head(root)
        requested = date_request.parse_fixture_dates_text(args.fixture_dates)
        requested = date_request.validate_fixture_dates(requested, current_utc=_now())
        bundle = execute_capture(
            request_dates=requested, fixture_cap=args.fixture_cap,
            output_dir=args.output_dir, repository_root=root,
        )
        exit_code, payload = classify_published_capture_result(bundle)
        if exit_code == 0:
            print(json.dumps(payload, sort_keys=True))
            return 0
        else:
            print(json.dumps(payload, sort_keys=True), file=sys.stderr)
            return exit_code
    except Exception as exc:
        _safe_failure(
            args.output_dir, exact_commit_sha=exact_sha,
            capture_id=capture_id, started_at=started, exc=exc,
        )
        print(f"P3_0_E1_CAPTURE_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


__all__ = tuple(name for name in globals() if not name.startswith("__"))
