from scripts._p3_0_paired_capture_part1 import *  # noqa: F401,F403

def _legacy_observations(sources: Sequence[Any]) -> dict[str, Mapping[str, Any]]:
    """Run each exact fixture independently so filtered/error rows cannot shift
    positional pairing or be attached to a different canonical fixture.
    """
    pipeline = _legacy_pipeline()
    by_fixture: dict[str, Mapping[str, Any]] = {}
    for source in sources:
        observer = evidence.LegacyEvidenceObserver()
        exported = pipeline.run_pipeline_snapshot(
            override_fixtures=[_legacy_override_fixture(source)],
            evidence_observer=observer,
        )
        observations = observer.observations()
        if len(observations) != 1 or len(exported) != 1:
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
    return by_fixture


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
    selected_sources = tuple(sorted(
        sources_bundle.router_inputs,
        key=lambda source: (source.fixture_identity, source.provider_event_id),
    ))[:fixture_cap]
    legacy_by_fixture = _legacy_observations(selected_sources)
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
    evidence.write_capture_artifact(bundle, output_dir)
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
        complete = sum(
            row["completeness_receipt"]["state"] == "P3_0_CAPTURE_COMPLETE"
            for row in bundle["fixture_records"]
        )
        print(json.dumps({
            "status": "P3_0_E1_CAPTURE_WRITTEN",
            "capture_id": bundle["capture_id"],
            "fixture_count": len(bundle["fixture_records"]),
            "complete_fixture_count": complete,
            "canonical_sha256": bundle["canonical_sha256"],
        }, sort_keys=True))
        return 0
    except Exception as exc:
        _safe_failure(
            args.output_dir, exact_commit_sha=exact_sha,
            capture_id=capture_id, started_at=started, exc=exc,
        )
        print(f"P3_0_E1_CAPTURE_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


__all__ = tuple(name for name in globals() if not name.startswith("__"))
