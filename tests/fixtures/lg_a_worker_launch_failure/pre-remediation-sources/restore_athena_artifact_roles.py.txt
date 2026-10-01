"""Restore canonical-first roles via fixed, read-only GitHub transport.

No provider, dispatch, upload, release mutation or authority transport exists here.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from services import athena_artifact_role_resolver as roles


class GitHubTransport:
    def api(self, endpoint: str, *, binary: bool = False):
        args = ["gh", "api", endpoint]
        if binary:
            args += ["-H", "Accept: application/octet-stream"]
        completed = subprocess.run(args, check=True, capture_output=True, timeout=180)
        return completed.stdout if binary else json.loads(completed.stdout)

    def pages(self, endpoint: str, field: str):
        result, page = [], 1
        while True:
            rows = self.api(f"{endpoint}&page={page}")[field]
            roles.require(type(rows) is list, "GitHub metadata list differs")
            result.extend(rows)
            if len(rows) < 100:
                return result
            page += 1

    def candidates(self, workflow: str, *, canonical_producer: bool, artifact_name: str | None = None):
        runs = self.pages(f"repos/{roles.REPOSITORY}/actions/workflows/{Path(workflow).name}/runs?status=success&branch=main&per_page=100", "workflow_runs")
        result = []
        for run in runs:
            if (run.get("repository", {}).get("full_name") != roles.REPOSITORY or
                    run.get("head_repository", {}).get("full_name") != roles.REPOSITORY or
                    run.get("path", "").split("@")[0] != workflow or run.get("head_branch") != "main" or
                    run.get("status") != "completed" or run.get("conclusion") != "success" or
                    type(run.get("id")) is not int or not roles.hex_sha(run.get("head_sha"), 40)):
                continue
            name = f"athena-run-{run['id']}" if canonical_producer else artifact_name
            artifacts = self.pages(f"repos/{roles.REPOSITORY}/actions/runs/{run['id']}/artifacts?per_page=100", "artifacts")
            matches = [item for item in artifacts if item.get("name") == name and item.get("expired") is False]
            if len(matches) != 1:
                continue
            item = matches[0]
            binding = item.get("workflow_run", {})
            if (binding.get("id") != run["id"] or binding.get("head_sha") != run["head_sha"] or
                    binding.get("head_branch") != "main" or type(item.get("id")) is not int):
                continue
            result.append(roles.Candidate(run["id"], run["head_sha"], workflow, item["id"], name,
                                          event_name=run.get("event")))
        return result

    def artifact(self, candidate: roles.Candidate) -> bytes:
        return self.api(f"repos/{roles.REPOSITORY}/actions/artifacts/{candidate.artifact_id}/zip", binary=True)

    def bootstrap(self) -> bytes:
        info = self.api(f"repos/{roles.REPOSITORY}/releases/tags/{roles.LEGACY_PRODUCERS['PR119_BOOTSTRAP']['release']}")
        roles.require(info.get("tag_name") == roles.LEGACY_PRODUCERS["PR119_BOOTSTRAP"]["release"], "release tag differs")
        matches = [item for item in info["assets"] if item.get("name") == roles.BOOTSTRAP_FILENAME]
        roles.require(len(matches) == 1 and type(matches[0].get("id")) is int, "fixed asset missing/ambiguous")
        self.bootstrap_origin = {"release_id": info["id"], "asset_id": matches[0]["id"],
                                 "asset_size_bytes": matches[0]["size"]}
        return self.api(f"repos/{roles.REPOSITORY}/releases/assets/{matches[0]['id']}", binary=True)


def extract_verified_paths(raw: bytes, destination: Path) -> None:
    """Never delegate extraction of untrusted ZIP paths to gh or extractall."""
    roles.require(zipfile.is_zipfile(io.BytesIO(raw)), "artifact is not a ZIP archive")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        seen = set()
        for item in archive.infolist():
            roles.require(item.orig_filename == item.filename, "ZIP path normalization forbidden")
            roles.require("\\" not in item.orig_filename, "ZIP backslash path forbidden")
            name = item.filename.rstrip("/") if item.is_dir() else item.filename
            target = roles.safe_path(destination, name)
            roles.require(name not in seen, "duplicate ZIP member")
            seen.add(name)
            mode = (item.external_attr >> 16) & 0o170000
            roles.require(mode not in {0o120000, 0o020000, 0o060000, 0o010000}, "ZIP non-regular member")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as stream:
                    stream.write(archive.read(item))


def manifest_root(download: Path) -> Path:
    choices = [download, download / "athena-run-workflow", download / "artifacts/athena-run-workflow"]
    found = [root for root in choices if (root / roles.MANIFEST_FILENAME).is_file()]
    roles.require(len(found) == 1, "canonical manifest missing/ambiguous")
    return found[0]


def legacy_role(role_id: str, candidate: roles.Candidate, download: Path):
    origin = {"source_kind": "LEGACY_ACTIONS", "repository": roles.REPOSITORY,
              "workflow_path": candidate.workflow_path, "run_id": candidate.run_id,
              "head_sha": candidate.head_sha, "artifact_name": candidate.artifact_name,
              "artifact_id": candidate.artifact_id}
    if role_id == "DURABLE_HISTORY_PRIME":
        root = download
    else:
        choices = list(download.rglob(roles.STATE_FILENAME))
        roles.require(len(choices) == 1, "legacy identity absent/ambiguous")
        root = download / "verified-identity-role"
        root.mkdir()
        shutil.copyfile(choices[0], root / roles.STATE_FILENAME)
    origin["inventory_sha256"] = roles.sha(roles.canonical(roles.inventory(root)))
    if role_id == "DURABLE_HISTORY_PRIME":
        from scripts import restore_current_shadow_history_prime_artifact as prime
        origin["receipt_sha256"] = roles.sha((root / prime.PRIME_RECEIPT_FILENAME).read_bytes())
    roles.validate_payload(role_id, root, origin)
    return root, origin


def restore_inputs(workspace: Path, transport, *, current_run_id: int,
                   canonical_candidates=None, legacy_candidates=None) -> dict:
    """Injected fixture transport uses exactly the production verification path."""
    artifact_root = roles.safe_path(workspace, "artifacts/athena-run-workflow")
    artifact_root.mkdir(parents=True, exist_ok=True)
    canonical_candidates = (transport.candidates(roles.CANONICAL_WORKFLOW, canonical_producer=True)
                            if canonical_candidates is None else canonical_candidates)
    restored = {}
    with tempfile.TemporaryDirectory(prefix="athena-role-restore-") as directory:
        scratch = Path(directory)
        downloads = {}

        def load(candidate):
            if candidate.artifact_id not in downloads:
                target = scratch / f"artifact-{candidate.artifact_id}"
                target.mkdir()
                try:
                    extract_verified_paths(transport.artifact(candidate), target)
                except (zipfile.BadZipFile, RuntimeError, subprocess.CalledProcessError) as exc:
                    raise roles.ArtifactRoleError("canonical archive download/integrity rejected") from exc
                downloads[candidate.artifact_id] = target
            root = manifest_root(downloads[candidate.artifact_id])
            return root, (root / roles.MANIFEST_FILENAME).read_bytes()

        for role_id in roles.ROLE_IDS[:3]:
            selected = roles.select_canonical(role_id, canonical_candidates, load, current_run_id=current_run_id)
            if selected:
                candidate, source, row = selected
                origin = row["origin_provenance"]
                selected_source = {"source_kind": "CANONICAL_ROLE", "run_id": candidate.run_id,
                                   "head_sha": candidate.head_sha, "artifact_id": candidate.artifact_id,
                                   "manifest_sha256": roles.sha(load(candidate)[1])}
            elif role_id != "PR119_BOOTSTRAP":
                mapping = roles.LEGACY_PRODUCERS[role_id]
                candidates = (transport.candidates(mapping["workflow_path"], canonical_producer=False,
                                                  artifact_name=mapping["artifact_name"])
                              if legacy_candidates is None else legacy_candidates.get(role_id, []))
                source = None
                for candidate in sorted(candidates, key=lambda item: item.run_id, reverse=True):
                    try:
                        roles.validate_candidate(candidate, current_run_id=current_run_id,
                                                 role_id=role_id, canonical_producer=False)
                        target = scratch / f"legacy-{role_id}-{candidate.artifact_id}"
                        target.mkdir()
                        extract_verified_paths(transport.artifact(candidate), target)
                        source, origin = legacy_role(role_id, candidate, target)
                        selected_source = {"source_kind": "LEGACY_READ_ONLY_COMPATIBILITY",
                                           "run_id": candidate.run_id, "head_sha": candidate.head_sha,
                                           "artifact_id": candidate.artifact_id}
                        break
                    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile,
                            subprocess.CalledProcessError):
                        continue
                if source is None:
                    continue  # preserve existing optional fallback/empty-worker semantics
            else:
                source = scratch / "fixed-bootstrap"
                source.mkdir()
                (source / roles.BOOTSTRAP_FILENAME).write_bytes(transport.bootstrap())
                origin = {"source_kind": "FIXED_RELEASE", "repository": roles.REPOSITORY,
                          **roles.LEGACY_PRODUCERS[role_id], **transport.bootstrap_origin,
                          "payload_sha256": roles.BOOTSTRAP_SHA256}
                roles.validate_payload(role_id, source, origin)  # required, before provider execution
                selected_source = {"source_kind": "FIXED_RELEASE_READ_ONLY_COMPATIBILITY"}
            destination = roles.safe_path(artifact_root, roles.ROLE_ROOTS[role_id])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination)
            roles.validate_payload(role_id, destination, origin)
            if role_id == "DURABLE_HISTORY_PRIME":
                from scripts import restore_current_shadow_history_prime_artifact as prime
                prime.restore(artifact_dir=destination,
                              cache_dir=roles.safe_path(workspace, ".cache/athena-research/current-shadow-history-github-binary-cache-v1"),
                              expected_prime_commit_sha=origin["head_sha"])
            else:
                relative = (".cache/athena-research/pr119-bootstrap/" + roles.BOOTSTRAP_FILENAME
                            if role_id == "PR119_BOOTSTRAP" else
                            ".cache/athena-research/current-shadow-fixture-identity-v2/" + roles.STATE_FILENAME)
                output = roles.safe_path(workspace, relative)
                output.parent.mkdir(parents=True, exist_ok=True)
                roles.require(not output.exists(), "restore target already exists; refusing overwrite")
                shutil.copyfile(destination / Path(relative).name, output)
            restored[role_id] = {"origin_provenance": origin, "selected_source": selected_source,
                                 "inventory_sha256": roles.sha(roles.canonical(roles.inventory(destination)))}
    state = roles.safe_path(workspace, ".cache/athena-research/current-shadow-fixture-identity-v2/" + roles.STATE_FILENAME)
    state.parent.mkdir(parents=True, exist_ok=True)
    (artifact_root / "artifact-role-restore-provenance-v1.json").write_bytes(roles.canonical(restored))
    return {"roles": restored, "identity_state_path": str(state)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restore-inputs", action="store_true", required=True)
    args = parser.parse_args()
    del args
    roles.require(os.environ.get("GITHUB_REPOSITORY") == roles.REPOSITORY, "repository environment differs")
    run_id = int(os.environ["GITHUB_RUN_ID"])
    roles.require(run_id > 0 and os.environ.get("GITHUB_REF") == "refs/heads/main", "restore caller must be main")
    result = restore_inputs(Path.cwd(), GitHubTransport(), current_run_id=run_id)
    with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as stream:
        stream.write(f"ATHENA_CURRENT_SHADOW_IDENTITY_STATE_PATH={result['identity_state_path']}\n")
    print(roles.canonical({"restored_roles": sorted(result["roles"]), "live_provider_actions": 0}).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
