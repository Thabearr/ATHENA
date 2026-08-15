from __future__ import annotations

import hashlib
from pathlib import Path

from domain.fotmob_data_matches_capture import manifest_from_mapping, strict_manifest_json_loads
from domain.fotmob_data_matches_ordinary_ft_finished_score_adapter_validation import (
    execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation,
    canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "evidence" / "fotmob_data_matches" / "pr83_post_finish_pair" / "20260814"
FIRST_DIR = EVIDENCE_ROOT / "a18e843fabe5aca74846b160"
SECOND_DIR = EVIDENCE_ROOT / "e28d9ce746c1ef9102995517"


def _load(directory: Path):
    raw = (directory / "response.json").read_bytes()
    manifest = manifest_from_mapping(strict_manifest_json_loads((directory / "manifest.json").read_bytes()))
    return raw, manifest


def test_probe_exact_pr96_receipt_identity() -> None:
    first_raw, first_manifest = _load(FIRST_DIR)
    second_raw, second_manifest = _load(SECOND_DIR)
    receipt = execute_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation(
        first_raw, first_manifest, second_raw, second_manifest
    )
    exact = canonical_fotmob_data_matches_ordinary_ft_finished_score_adapter_validation_receipt_bytes(receipt)
    raise AssertionError(
        "PR96_PROBE "
        f"adapter_result_sha256={receipt['adapter_result_sha256']} "
        f"adapter_result_size={receipt['adapter_result_size']} "
        f"qualified_scores_projection_sha256={receipt['qualified_scores_projection_sha256']} "
        f"terminal_candidate_union_count={receipt['terminal_candidate_union_count']} "
        f"blocked_fixture_ids_by_status={dict(receipt['blocked_fixture_ids_by_status'])!r} "
        f"receipt_sha256={hashlib.sha256(exact).hexdigest()} "
        f"receipt_size={len(exact)}"
    )
