#!/usr/bin/env python3
"""PR-F hosted wrapper for exact builder-issued history summary SHA reuse."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys

from domain import current_shadow_all_market_runner as runner
from scripts import execute_current_shadow_all_market as cli


WORKER_MODULE = "scripts.execute_current_shadow_all_market_summary_reuse"
_BASE_XG_INSTALLER = cli._install_builder_issued_history_xg_reuse
_original_history_sha = None


def _install_captured_history_lineage_reuse():
    """Build later date-specific histories from the first exact captured evidence.

    The generic PR-F worker already captures every GitHub read consumed by the
    first reviewed PR151 lineage audit and validates that the frozen snapshot
    reproduces the exact audit.  A three-day request previously called the
    private reader builder again for every later current FotMob date.  That
    reran the full projected 200+ archive lineage audit even though all GitHub
    bytes were the same immutable captured snapshot.

    Keep the first live builder unchanged.  Later dates reuse only that exact
    ``GitHubActionsLineageEvidenceBundle`` for the same expected main SHA, rerun
    latest-applicable selection against each date's own source observation, and
    build a new exact durable prefix/current handoff from the selected captured
    artifact.  The handoff/source dataclasses still replace and validate the
    evidence object; the worker's successful exact-evidence replay cache makes
    that validation computationally reusable without granting new authority.
    Different main identities always go through the untouched live builder.
    """

    latest = runner.latest_history
    original = latest.build_current_fotmob_latest_durable_fresh_history_handoff
    evidence_by_main: dict[str, object] = {}

    def build(**kwargs):
        expected_main_sha = kwargs.get("expected_main_sha")
        evidence = evidence_by_main.get(expected_main_sha)
        if evidence is None:
            history = original(**kwargs)
            captured = history.source_bundle.github_evidence
            if captured.expected_main_sha != expected_main_sha:
                raise runner.CurrentShadowAllMarketRunnerError(
                    "captured PR151 lineage evidence main identity drifted"
                )
            evidence_by_main[expected_main_sha] = captured
            return history

        source_manifest = kwargs["source_manifest"]
        observed_at = getattr(source_manifest, "observed_at", None)
        if (
            type(observed_at) is not dt.datetime
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise latest.CurrentLatestDurableFreshHistoryError(
                "current source manifest lost observed_at authority"
            )
        chosen, _artifact, zip_bytes, metadata_digest = latest._select_latest_material(
            evidence=evidence,
            source_observed_at=observed_at,
        )
        try:
            selected_prefix = latest.prefix.build_current_fotmob_durable_fresh_history_prefix_handoff(
                current_bootstrap=kwargs["current_bootstrap"],
                source_raw_json=kwargs["source_raw_json"],
                source_manifest=source_manifest,
                legacy_bootstrap_projection_raw=kwargs["legacy_bootstrap_projection_raw"],
                workflow_run_id=chosen.run_id,
                artifact_name=chosen.artifact_name,
                artifact_zip_bytes=zip_bytes,
                artifact_zip_metadata_digest=metadata_digest,
            )
        except Exception as exc:
            raise latest.CurrentLatestDurableFreshHistoryError(
                "latest applicable success failed exact cumulative prefix replay"
            ) from exc
        source = latest.CurrentLatestDurableFreshHistorySourceBundle(
            github_evidence=evidence,
            selected_prefix=selected_prefix,
        )
        return latest.CurrentLatestDurableFreshHistoryHandoff(
            schema_version=latest.SCHEMA_VERSION,
            dataset_name=latest.DATASET_NAME,
            status=latest.STATUS,
            source_bundle=source,
            latest_applicable_success_selection_proven=True,
            current_fresh_history_prefix_complete=True,
            next_required_boundary=latest.NEXT_REQUIRED_BOUNDARY,
            evidence=latest._evidence(),
            authority=latest._authority(),
        )

    latest.build_current_fotmob_latest_durable_fresh_history_handoff = build
    return original


def _install_builder_issued_history_summary_sha_reuse(
    issued_by_identity: dict[int, object],
):
    """Reuse canonical SHA only for exact same-worker builder-issued histories.

    Run #30 completed Price-all/Router/portfolio-input work for all observed
    reconciled fixtures, then remained inside the PRICE_ALL_ROUTER stage until
    the fixed supervisor expired. The only work after that loop and before the
    next stage is receipt/source-summary materialization, which calls the public
    PR151 history SHA helper again. That helper deliberately reconstructs the
    frozen dataclass and therefore replays deep source validation.

    The PR-F worker has already built and consumed these exact frozen history
    objects through the reviewed builder and PR-C path. Reuse only the canonical
    SHA of the same object identity. Unknown or caller-supplied histories still
    execute the original public helper unchanged. Failed canonicalization is
    never cached.
    """

    original = (
        runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff
    )
    sha_by_identity: dict[int, tuple[object, str]] = {}

    def history_sha(value):
        issued = issued_by_identity.get(id(value))
        if issued is not value:
            return original(value)
        if (
            type(value)
            is not runner.latest_history.CurrentLatestDurableFreshHistoryHandoff
        ):
            return original(value)

        cached = sha_by_identity.get(id(value))
        if cached is not None and cached[0] is value:
            return cached[1]

        try:
            canonical = runner.latest_history._canonical(value.to_dict())
        except Exception as exc:
            raise runner.CurrentShadowAllMarketRunnerError(
                "builder-issued PR151 summary history canonicalization failed"
            ) from exc
        digest = hashlib.sha256(canonical).hexdigest()
        sha_by_identity[id(value)] = (value, digest)
        return digest

    runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff = (
        history_sha
    )
    return original


def _install_xg_and_summary_reuse(issued_by_identity: dict[int, object]):
    global _original_history_sha
    original_xg = _BASE_XG_INSTALLER(issued_by_identity)
    if _original_history_sha is not None:
        raise runner.CurrentShadowAllMarketRunnerError(
            "PR-F summary history SHA reuse installed more than once"
        )
    _original_history_sha = _install_builder_issued_history_summary_sha_reuse(
        issued_by_identity
    )
    return original_xg


def _execute_worker(args) -> int:
    global _original_history_sha
    original_installer = cli._install_builder_issued_history_xg_reuse
    original_lineage_installer = cli._install_history_lineage_reuse
    cli._install_builder_issued_history_xg_reuse = _install_xg_and_summary_reuse
    cli._install_history_lineage_reuse = _install_captured_history_lineage_reuse
    try:
        return cli._execute_once(args)
    finally:
        cli._install_builder_issued_history_xg_reuse = original_installer
        cli._install_history_lineage_reuse = original_lineage_installer
        if _original_history_sha is not None:
            runner.latest_history.sha256_current_fotmob_latest_durable_fresh_history_handoff = (
                _original_history_sha
            )
            _original_history_sha = None


def main(argv: list[str] | None = None) -> int:
    args = cli.build_parser().parse_args(argv)
    if os.environ.get(cli.WORKER_ENV) == "1":
        return _execute_worker(args)

    env = dict(os.environ)
    env[cli.WORKER_ENV] = "1"
    command = [
        sys.executable,
        "-m",
        WORKER_MODULE,
        "--target-size",
        str(args.target_size),
        "--output-dir",
        str(args.output_dir),
    ]
    try:
        completed = subprocess.run(
            command,
            env=env,
            check=False,
            timeout=runner.CURRENT_SHADOW_RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        result = runner.write_current_shadow_timeout_receipt(
            target_size=args.target_size,
            output_dir=args.output_dir,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return 0
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())