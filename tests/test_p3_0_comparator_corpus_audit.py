import copy
import hashlib
import json
from pathlib import Path
import pytest

AUDIT_PATH = (
    Path(__file__).resolve().parents[1]
    / "artifacts"
    / "p3-0-comparator-corpus-audit.json"
)


def _load_audit() -> dict:
    with open(AUDIT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _compute_canonical_sha256(doc: dict) -> str:
    payload = {k: v for k, v in doc.items() if k != "canonical_sha256"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _verify_audit_invariants(doc: dict) -> None:
    expected_sha = doc.get("canonical_sha256")
    actual_sha = _compute_canonical_sha256(doc)
    if expected_sha != actual_sha:
        raise ValueError(
            f"Canonical SHA256 mismatch: expected {expected_sha}, calculated {actual_sha}"
        )

    seen_artifact_ids = set()
    seen_run_artifact_pairs = set()

    complete = doc.get("complete_corpus_members", [])
    partial_and_unusable = doc.get("partial_and_unusable_artifacts", [])

    for member in complete:
        art_id = member.get("artifact_id")
        run_id = member.get("run_id")
        if art_id in seen_artifact_ids:
            raise ValueError(f"Duplicate artifact_id in audit: {art_id}")
        seen_artifact_ids.add(art_id)

        pair = (run_id, art_id)
        if pair in seen_run_artifact_pairs:
            raise ValueError(f"Duplicate (run_id, artifact_id) in audit: {pair}")
        seen_run_artifact_pairs.add(pair)

        if member.get("classification") != "CORPUS_COMPLETE_MEMBER":
            raise ValueError(
                f"Complete member has invalid classification: {member.get('classification')}"
            )
        if not member.get("manifest_verifies") or not member.get("bundle_verifies"):
            raise ValueError(
                f"Complete member requires manifest_verifies=True and bundle_verifies=True: {art_id}"
            )

    for item in partial_and_unusable:
        art_id = item.get("artifact_id")
        run_id = item.get("run_id")
        if art_id in seen_artifact_ids:
            raise ValueError(f"Duplicate artifact_id in audit: {art_id}")
        seen_artifact_ids.add(art_id)

        pair = (run_id, art_id)
        if pair in seen_run_artifact_pairs:
            raise ValueError(f"Duplicate (run_id, artifact_id) in audit: {pair}")
        seen_run_artifact_pairs.add(pair)

        if item.get("classification") == "CORPUS_COMPLETE_MEMBER":
            raise ValueError(
                f"Partial/unusable list cannot contain CORPUS_COMPLETE_MEMBER: {art_id}"
            )

    summary = doc.get("corpus_summary", {})
    total = summary.get("total_artifacts_audited")
    actual_total = len(seen_artifact_ids)
    if total != actual_total:
        raise ValueError(
            f"total_artifacts_audited mismatch: declared {total}, found {actual_total}"
        )


def test_corpus_audit_file_satisfies_all_invariants() -> None:
    doc = _load_audit()
    _verify_audit_invariants(doc)

    # Specific required artifact checks
    complete = doc["complete_corpus_members"]
    assert len(complete) == 1
    c = complete[0]
    assert c["artifact_id"] == 10603511090
    assert c["run_id"] == 35502639963
    assert c["artifact_digest"] == "sha256:abe4727ae0eaa8e6e0580b2fe4d2298711b13cca0bd00546e958f30613f87c4d"
    assert c["manifest_verifies"] is True
    assert c["bundle_verifies"] is True
    assert c["classification"] == "CORPUS_COMPLETE_MEMBER"

    partial = [
        item
        for item in doc["partial_and_unusable_artifacts"]
        if item["artifact_id"] == 10601394178
    ]
    assert len(partial) == 1
    p = partial[0]
    assert p["run_id"] == 35498127010
    assert p["artifact_digest"] == "sha256:e78c375088f4d05200d1a2ab8071ebc66cd7fac78ceed240f84ac05530028cbc"
    assert p["classification"] == "PARTIAL_NOT_COMPARATOR_AUTHORITY"
    assert p["manifest_verifies"] is False
    assert p["bundle_verifies"] is False

    diag = [
        item
        for item in doc["partial_and_unusable_artifacts"]
        if item["artifact_id"] == 10601359114
    ]
    assert len(diag) == 1
    d = diag[0]
    assert d["artifact_digest"] == "sha256:da6567a2ebb301e38c784ec2acb50af9b4c11f309cfec6fe7fd342de88a99fe9"
    assert d["classification"] == "UNUSABLE_NOT_COMPARATOR_AUTHORITY"


def test_corpus_audit_rejects_digest_mutation() -> None:
    doc = _load_audit()
    doc_mutated = copy.deepcopy(doc)
    doc_mutated["complete_corpus_members"][0]["artifact_digest"] = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    with pytest.raises(ValueError, match="Canonical SHA256 mismatch"):
        _verify_audit_invariants(doc_mutated)


def test_corpus_audit_rejects_duplicate_artifact_id() -> None:
    doc = _load_audit()
    doc_dup = copy.deepcopy(doc)
    # Duplicate complete member into partial list
    doc_dup["partial_and_unusable_artifacts"].append(
        copy.deepcopy(doc_dup["complete_corpus_members"][0])
    )
    doc_dup["canonical_sha256"] = _compute_canonical_sha256(doc_dup)
    with pytest.raises(ValueError, match="Duplicate artifact_id in audit"):
        _verify_audit_invariants(doc_dup)


def test_corpus_audit_rejects_duplicate_run_artifact_pair() -> None:
    doc = _load_audit()
    doc_dup = copy.deepcopy(doc)
    dup_item = copy.deepcopy(doc_dup["partial_and_unusable_artifacts"][0])
    doc_dup["partial_and_unusable_artifacts"].append(dup_item)
    doc_dup["canonical_sha256"] = _compute_canonical_sha256(doc_dup)
    with pytest.raises(ValueError, match="Duplicate artifact_id in audit"):
        _verify_audit_invariants(doc_dup)


def test_corpus_audit_rejects_unverified_complete_member() -> None:
    doc = _load_audit()
    doc_bad = copy.deepcopy(doc)
    doc_bad["complete_corpus_members"][0]["manifest_verifies"] = False
    doc_bad["canonical_sha256"] = _compute_canonical_sha256(doc_bad)
    with pytest.raises(ValueError, match="Complete member requires manifest_verifies=True"):
        _verify_audit_invariants(doc_bad)

    doc_bad2 = copy.deepcopy(doc)
    doc_bad2["complete_corpus_members"][0]["bundle_verifies"] = False
    doc_bad2["canonical_sha256"] = _compute_canonical_sha256(doc_bad2)
    with pytest.raises(ValueError, match="Complete member requires manifest_verifies=True"):
        _verify_audit_invariants(doc_bad2)


def test_corpus_audit_rejects_complete_member_in_unusable_list() -> None:
    doc = _load_audit()
    doc_bad = copy.deepcopy(doc)
    doc_bad["partial_and_unusable_artifacts"][0]["classification"] = "CORPUS_COMPLETE_MEMBER"
    doc_bad["canonical_sha256"] = _compute_canonical_sha256(doc_bad)
    with pytest.raises(ValueError, match="Partial/unusable list cannot contain CORPUS_COMPLETE_MEMBER"):
        _verify_audit_invariants(doc_bad)
