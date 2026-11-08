"""Standing, append-only registry of exact source successors (SRC-01).

An admitted successor is an exact (before, after) identity pair for one existing
file that a frozen record pins. Each mission registers its pairs in ONE new batch
file, ``scripts/source_successor_batch_NNNN_<slug>.py``; consumers read them
through ``scripts.audit_phase_a_workflow_successor`` and never gain new hooks.

Properties enforced here (every violation raises ``SuccessorRegistryError``):

* Batch files are found by one exact name pattern and imported in SEQUENCE
  order, so a batch cannot exist without being loaded. A name that starts with
  the batch prefix but does not match the pattern is an error.
* SEQUENCE is contiguous from 1 and equals the 4-digit number in the file name.
  PREVIOUS_BATCH_SHA256 is the sha256 of the previous batch file's LF bytes
  ("" for batch 1), so batches form a hash chain.
* An entry is an exact ``Successor`` with well-formed 40/64-hex identities and a
  literal, wildcard-free repository path. There are no patterns or prefixes.
* Entries for one path form a chain: steps are contiguous from 1, and each
  step's before identity is the previous step's after identity. A gap, a fork
  or a duplicate (path, step) fails closed.
* VAR-05: a batch may also declare ADDED_PATHS (literal paths of the NEW files
  its mission adds, same path rules, never an ENTRIES path, each an existing
  regular unlinked file) with FIRST_GENERATION (the A2 generation that first
  lists them). The additive allowlist and the exact B1 census read these, so a
  mission no longer edits them by hand. ENTRIES may be empty only when
  ADDED_PATHS is not. Existence is re-checked on every call.

The executed bytes are exactly the bytes that were hashed. Batch files are
authenticated by the A2 source inventory like every other governed source, and
the history test in tests/test_source_successor_registry.py proves a batch file
is byte-identical in every A2 generation since it first appeared.

This module reads files only. It has no network, subprocess or write path and
grants no provider, trigger, delivery or model authority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import stat
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
BATCH_DIR = "scripts"
BATCH_PREFIX = "source_successor_batch_"
_BATCH_NAME = re.compile(r"^source_successor_batch_(\d{4})_([a-z0-9]+(?:_[a-z0-9]+)*)\.py$")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MISSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PATH = re.compile(r"^[A-Za-z0-9._@+-]+(?:/[A-Za-z0-9._@+-]+)*$")
_PREFIX = "successor registry: "


class SuccessorRegistryError(ValueError):
    """The registry, a batch file or a chain is malformed, forked or tampered."""


def _fail(detail: str) -> None:
    raise SuccessorRegistryError(_PREFIX + detail)


@dataclasses.dataclass(frozen=True)
class Successor:
    path: str
    before_blob: str
    before_sha256: str
    after_blob: str
    after_sha256: str
    hunks: tuple[bytes, ...]
    reason: str
    step: int = 1


@dataclasses.dataclass(frozen=True)
class Batch:
    sequence: int
    slug: str
    mission: str
    name: str
    sha256: str
    previous_sha256: str
    entries: tuple[Successor, ...]
    added_paths: tuple[str, ...] = ()
    first_generation: int | None = None


@dataclasses.dataclass(frozen=True)
class Chain:
    """Entries for one path: steps 1..n, root identity first, head identity last."""

    path: str
    steps: tuple[Successor, ...]

    @property
    def identities(self) -> tuple[tuple[str, str], ...]:
        first = self.steps[0]
        return ((first.before_blob, first.before_sha256),) + tuple(
            (step.after_blob, step.after_sha256) for step in self.steps)


@dataclasses.dataclass(frozen=True)
class Registry:
    batches: tuple[Batch, ...]
    chains: Mapping[str, Chain]

    def entries_of(self, mission: str) -> tuple[Successor, ...]:
        return tuple(entry for batch in self.batches if batch.mission == mission
                     for entry in batch.entries)

    def added_paths(self) -> dict[str, int]:
        """Every batch-declared new path mapped to the A2 generation that first lists it."""
        return {path: batch.first_generation for batch in self.batches for path in batch.added_paths}


def _check_entry(number: int, entry: object) -> Successor:
    where = f"batch {number:04d}"
    if type(entry) is not Successor:
        _fail(f"{where} entry is not a Successor")
    assert isinstance(entry, Successor)
    path = entry.path
    if not isinstance(path, str) or not _PATH.fullmatch(path) or any(
            part in (".", "..") for part in path.split("/")):
        _fail(f"malformed id in {where}: path {path!r}")
    for field in ("before_blob", "after_blob"):
        value = getattr(entry, field)
        if not isinstance(value, str) or not _HEX40.fullmatch(value):
            _fail(f"malformed id in {where}: {path} {field}")
    for field in ("before_sha256", "after_sha256"):
        value = getattr(entry, field)
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            _fail(f"malformed id in {where}: {path} {field}")
    if (entry.before_blob, entry.before_sha256) == (entry.after_blob, entry.after_sha256):
        _fail(f"malformed id in {where}: {path} before and after are identical")
    if (not isinstance(entry.hunks, tuple) or not entry.hunks
            or not all(isinstance(hunk, bytes) and hunk for hunk in entry.hunks)):
        _fail(f"{where} entry has malformed hunks: {path}")
    if not isinstance(entry.reason, str) or not entry.reason.strip():
        _fail(f"{where} entry has no reason: {path}")
    if type(entry.step) is not int or entry.step < 1:
        _fail(f"{where} entry has a malformed step: {path}")
    return entry


def _check_path(where: str, path: object) -> str:
    if not isinstance(path, str) or not _PATH.fullmatch(path) or any(
            part in (".", "..") for part in path.split("/")):
        _fail(f"malformed id in {where}: path {path!r}")
    assert isinstance(path, str)
    return path


def _check_added(number: int, namespace: dict) -> tuple[tuple[str, ...], int | None]:
    where = f"batch {number:04d}"
    added = namespace.get("ADDED_PATHS", ())
    first = namespace.get("FIRST_GENERATION")
    if not isinstance(added, tuple):
        _fail(f"{where} ADDED_PATHS must be a tuple")
    checked = tuple(_check_path(where + " ADDED_PATHS", path) for path in added)
    if len(set(checked)) != len(checked):
        _fail(f"{where} ADDED_PATHS lists a path twice")
    if checked:
        if type(first) is not int or first < 1:
            _fail(f"{where} declares ADDED_PATHS without a valid FIRST_GENERATION")
    elif first is not None:
        _fail(f"{where} declares FIRST_GENERATION without ADDED_PATHS")
    return checked, first


def _require_regular_files(base: Path, registry: "Registry") -> None:
    for path in registry.added_paths():
        parts = Path(path).parts
        for depth in range(1, len(parts) + 1):
            node = base.joinpath(*parts[:depth])
            try:
                info = node.lstat()
            except OSError:
                _fail(f"added path is missing: {path}")
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                _fail(f"added path is linked: {path}")
        if not stat.S_ISREG(base.joinpath(*parts).lstat().st_mode):
            _fail(f"added path is not a regular file: {path}")


def _execute(name: str, number: int, source: bytes) -> dict:
    namespace: dict = {"__name__": f"_athena_successor_batch_{number:04d}", "__file__": name}
    try:
        exec(compile(source, name, "exec"), namespace)
    except TypeError as exc:
        _fail(f"batch {number:04d} has an unknown field or malformed entry: {exc}")
    except Exception as exc:  # noqa: BLE001 - any load failure must fail closed
        _fail(f"batch {number:04d} failed to load: {type(exc).__name__}")
    return namespace


def _build_chains(batches: tuple[Batch, ...]) -> dict[str, Chain]:
    steps: dict[str, list[Successor]] = {}
    for batch in batches:
        for entry in batch.entries:
            chain = steps.setdefault(entry.path, [])
            if any(existing.step == entry.step for existing in chain):
                _fail(f"duplicate (path, step): {entry.path} step {entry.step}")
            if entry.step != len(chain) + 1:
                _fail(f"chain gap for {entry.path}: expected step {len(chain) + 1}, got {entry.step}")
            if chain:
                previous = chain[-1]
                if (entry.before_blob, entry.before_sha256) != (previous.after_blob, previous.after_sha256):
                    earlier = {(chain[0].before_blob, chain[0].before_sha256)} | {
                        (item.after_blob, item.after_sha256) for item in chain[:-1]}
                    if (entry.before_blob, entry.before_sha256) in earlier:
                        _fail(f"chain fork for {entry.path} at step {entry.step}")
                    _fail(f"chain break for {entry.path} at step {entry.step}: "
                          "before identity is not the previous step's after identity")
            chain.append(entry)
    return {path: Chain(path=path, steps=tuple(chain)) for path, chain in steps.items()}


def _discover(directory: Path) -> tuple[tuple[int, str, str, bytes], ...]:
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        _fail("batch directory is unreadable")
    found: list[tuple[int, str, str, bytes]] = []
    seen: set[int] = set()
    for name in names:
        if not name.startswith(BATCH_PREFIX):
            continue
        match = _BATCH_NAME.fullmatch(name)
        if match is None:
            _fail(f"batch file name is malformed: {name}")
        number = int(match.group(1))
        if number in seen:
            _fail(f"duplicate batch sequence {number:04d}")
        seen.add(number)
        path = directory / name
        try:
            info = path.lstat()
        except OSError:
            _fail(f"batch file is unreadable: {name}")
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400 \
                or not stat.S_ISREG(info.st_mode):
            _fail(f"batch file is linked or not a regular file: {name}")
        found.append((number, match.group(2), name, path.read_bytes().replace(b"\r\n", b"\n")))
    return tuple(sorted(found))


_CACHE: dict[tuple, Registry] = {}


def load(root: Path | str | None = None) -> Registry:
    """Discover, validate and return the registry rooted at ``root`` (default: repo)."""
    base = ROOT if root is None else Path(root)
    files = _discover(base / BATCH_DIR)
    if not files:
        _fail("no batch files found")
    key = (str(base),) + tuple((number, name, hashlib.sha256(source).hexdigest())
                               for number, _, name, source in files)
    cached = _CACHE.get(key)
    if cached is not None:
        _require_regular_files(base, cached)
        return cached
    batches: list[Batch] = []
    previous_sha = ""
    for expected, (number, slug, name, source) in enumerate(files, start=1):
        if number != expected:
            _fail(f"batch sequence gap: expected {expected:04d}, found {number:04d}")
        namespace = _execute(name, number, source)
        for declaration in ("SEQUENCE", "MISSION", "PREVIOUS_BATCH_SHA256", "ENTRIES"):
            if declaration not in namespace:
                _fail(f"batch {number:04d} is missing {declaration}")
        sequence = namespace["SEQUENCE"]
        if type(sequence) is not int or sequence != number:
            _fail(f"batch {number:04d} declares SEQUENCE {sequence!r}")
        mission = namespace["MISSION"]
        if not isinstance(mission, str) or not _MISSION.fullmatch(mission):
            _fail(f"batch {number:04d} has a malformed MISSION")
        previous = namespace["PREVIOUS_BATCH_SHA256"]
        if not isinstance(previous, str) or previous != previous_sha:
            _fail(f"batch {number:04d} previous batch hash mismatch")
        entries = namespace["ENTRIES"]
        added, first_generation = _check_added(number, namespace)
        if not isinstance(entries, tuple) or (not entries and not added):
            _fail(f"batch {number:04d} ENTRIES must be a non-empty tuple")
        checked = tuple(_check_entry(number, entry) for entry in entries)
        digest = hashlib.sha256(source).hexdigest()
        batches.append(Batch(sequence=number, slug=slug, mission=mission, name=name,
                             sha256=digest, previous_sha256=previous, entries=checked,
                             added_paths=added, first_generation=first_generation))
        previous_sha = digest
    ordered = tuple(batches)
    chains = _build_chains(ordered)
    seen_added: set[str] = set()
    for batch in ordered:
        for path in batch.added_paths:
            if path in chains:
                _fail(f"batch {batch.sequence:04d} ADDED_PATHS overlaps an ENTRIES path: {path}")
            if path in seen_added:
                _fail(f"batch {batch.sequence:04d} ADDED_PATHS repeats a path added earlier: {path}")
            seen_added.add(path)
    registry = Registry(batches=ordered, chains=chains)
    _require_regular_files(base, registry)
    _CACHE[key] = registry
    return registry


def current(root: Path | str | None = None) -> Registry:
    """The validated registry for the repository (or ``root``); re-read on every call."""
    return load(root)
