"""Immutable source-controlled composition bindings for the Current Shadow core.

The binding selects no alternate model, price, Router, Portfolio, transport, or
authority owner. It provides one explicit semantic replay path and a per-run
memo of contexts already fully replay-verified under that exact binding.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from domain._current_shadow_price_core import ShadowPriceError


POLICY_ID = "ATHENA_CURRENT_SHADOW_RUNTIME_COMPOSITION_BINDINGS_V1"
STANDARD_COMPOSITION = "STANDARD"
FRESH_REPRICE_COMPOSITION = "FRESH_REPRICE"


def policy_payload(*, composition: str) -> dict[str, Any]:
    if composition not in {STANDARD_COMPOSITION, FRESH_REPRICE_COMPOSITION}:
        raise ShadowPriceError("unknown Current Shadow runtime composition")
    return {
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "composition": composition,
        "canonical_core_adapter": "domain.current_shadow_canonical_core_adapter",
        "price_context_verifier": "domain._current_shadow_quote_binding.verify_current_shadow_price_context",
        "price_all_owner": "domain.current_shadow_all_market_price_all",
        "router_owner": "domain.current_shadow_all_market_router",
        "portfolio_owner": "domain.current_shadow_all_market_portfolio",
        "reconciliation_dispatch": "domain._current_shadow_quote_binding.verify_current_shadow_reconciliation_bundle",
        "fresh_context_mode": "PRF_CURRENT_RECONCILIATION_FRESH_REPRICE",
        "fresh_reprice_contract": {
            "exact_context_type": "CurrentShadowPriceContext",
            "exact_source_context_policy_id": (
                "PRF_RETAINED_EXACT_RECONCILIATION_PLUS_FRESH_DIRECT_EVENT_REPRICE_V1"
            ),
            "same_fixture_identity": True,
            "same_provider_event_id": True,
            "same_reconciliation_replay": True,
            "same_fotmob_identity": True,
            "same_home_away_kickoff_and_competition": True,
            "fresh_observation_strictly_newer_than_reconciliation_and_prior_quote": True,
            "evaluation_time_equals_fresh_observation": True,
            "raw_manifest_inventory_and_registry_ancestry_replayed": True,
            "legacy_mapping_and_bridge_identities": False,
            "worker_local_issued_context_registry_is_authority": False,
            "unknown_source_context_mode_fails_closed": True,
        },
        "semantic_correctness_depends_on_monkeypatch_install_order": False,
        "context_cache_key": [
            "exact source-context canonical SHA-256",
            "verifier policy identity",
            "execution binding identity",
        ],
        "cache_hit_requires_same_verified_context_object_and_canonical_bytes": True,
        "cache_hit_is_authority": False,
        "unknown_context_full_replay_required": True,
        "main_authority": False,
        "login": False,
        "cookies": False,
        "wallet": False,
        "staking": False,
        "bet": False,
        "wager_placed": False,
    }


def _binding_sha256(*, composition: str) -> str:
    raw = json.dumps(
        policy_payload(composition=composition),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def policy_sha256(*, composition: str) -> str:
    """Return the deterministic source-controlled identity for one composition."""

    return _binding_sha256(composition=composition)


@dataclass(frozen=True)
class _VerifiedContext:
    source: Any
    canonical_bytes: bytes
    canonical_sha256: str
    verifier_policy_id: str
    binding_identity: str
    verified: Any


class _VerifiedContextMemo:
    """A non-authoritative memo that only reuses a same-object full verification."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: dict[tuple[str, str, str], _VerifiedContext] = {}

    def get(
        self,
        *,
        source: Any,
        canonical_bytes: bytes,
        canonical_sha256: str,
        verifier_policy_id: str,
        binding_identity: str,
    ) -> Any | None:
        key = (canonical_sha256, verifier_policy_id, binding_identity)
        with self._lock:
            row = self._rows.get(key)
        if (
            row is not None
            and row.source is source
            and row.canonical_bytes == canonical_bytes
            and row.canonical_sha256 == canonical_sha256
            and row.verifier_policy_id == verifier_policy_id
            and row.binding_identity == binding_identity
        ):
            return row.verified
        return None

    def put(
        self,
        *,
        source: Any,
        canonical_bytes: bytes,
        canonical_sha256: str,
        verifier_policy_id: str,
        binding_identity: str,
        verified: Any,
    ) -> None:
        key = (canonical_sha256, verifier_policy_id, binding_identity)
        row = _VerifiedContext(
            source=source,
            canonical_bytes=canonical_bytes,
            canonical_sha256=canonical_sha256,
            verifier_policy_id=verifier_policy_id,
            binding_identity=binding_identity,
            verified=verified,
        )
        with self._lock:
            self._rows[key] = row


def _expected_verifier_policy_id(value: Any) -> str:
    """Resolve the reviewed verifier identity for the exact source-context mode."""

    from domain import _current_shadow_quote_binding as quote_binding

    mode_to_policy = {
        quote_binding.LEGACY_PR253_FIXTURE_BRIDGE: quote_binding.SOURCE_CONTEXT_POLICY_ID,
        quote_binding.CURRENT_RECONCILIATION_DIRECT: (
            quote_binding.CURRENT_RECONCILIATION_SOURCE_CONTEXT_POLICY_ID
        ),
        quote_binding.FRESH_REPRICE_MODE: quote_binding.FRESH_REPRICE_SOURCE_CONTEXT_POLICY_ID,
    }
    try:
        mode = value.source_context_mode
        if type(mode) is not str:
            raise TypeError("source-context mode must be an exact string")
        expected = mode_to_policy[mode]
    except (AttributeError, KeyError, TypeError) as exc:
        raise ShadowPriceError("unknown current Shadow source-context mode") from exc
    if type(value.source_context_policy_id) is not str or value.source_context_policy_id != expected:
        raise ShadowPriceError("Current Shadow source-context policy does not match its mode")
    return expected


@dataclass(frozen=True, init=False)
class CurrentShadowRuntimeBindings:
    """One immutable execution binding selected by the Current Shadow root."""

    composition: str
    policy_id: str
    canonical_sha256: str
    _verified_contexts: _VerifiedContextMemo = field(repr=False, compare=False)

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise ShadowPriceError("CurrentShadowRuntimeBindings is factory-only")

    @property
    def fresh_reprice_enabled(self) -> bool:
        return self.composition == FRESH_REPRICE_COMPOSITION

    def _validate_self(self) -> None:
        if (
            self.policy_id != POLICY_ID
            or self.composition not in {STANDARD_COMPOSITION, FRESH_REPRICE_COMPOSITION}
            or self.canonical_sha256 != _binding_sha256(composition=self.composition)
            or type(self._verified_contexts) is not _VerifiedContextMemo
        ):
            raise ShadowPriceError("Current Shadow execution binding drifted")

    def verify_context(self, value: Any) -> Any:
        self._validate_self()
        from domain import _current_shadow_quote_binding as quote_binding

        if type(value) is not quote_binding.CurrentShadowPriceContext:
            return quote_binding.verify_current_shadow_price_context(value)
        verifier_policy_id = _expected_verifier_policy_id(value)
        canonical_bytes = quote_binding._canonical_bytes(value.to_dict())
        canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
        cached = self._verified_contexts.get(
            source=value,
            canonical_bytes=canonical_bytes,
            canonical_sha256=canonical_sha256,
            verifier_policy_id=verifier_policy_id,
            binding_identity=self.canonical_sha256,
        )
        if cached is not None:
            return cached
        checked = quote_binding.verify_current_shadow_price_context(value)
        checked_bytes = quote_binding._canonical_bytes(checked.to_dict())
        checked_sha = hashlib.sha256(checked_bytes).hexdigest()
        if checked_sha != canonical_sha256 or checked_bytes != canonical_bytes:
            raise ShadowPriceError("verified Current Shadow context identity drifted")
        self._verified_contexts.put(
            source=value,
            canonical_bytes=canonical_bytes,
            canonical_sha256=canonical_sha256,
            verifier_policy_id=verifier_policy_id,
            binding_identity=self.canonical_sha256,
            verified=checked,
        )
        return checked

    def verify_price_all_bundle(self, value: Any) -> Any:
        self._validate_self()
        from domain import current_shadow_all_market_price_all as price_all

        return price_all._verify_shadow_price_all_bundle(value, runtime_bindings=self)

    def price_all(self, context: Any) -> Any:
        self._validate_self()
        from domain import current_shadow_all_market_price_all as price_all

        return price_all._price_all_shadow_fixture(context, runtime_bindings=self)

    def route(self, price_all_bundle: Any) -> Any:
        self._validate_self()
        from domain import current_shadow_all_market_router as router

        return router._route_shadow_price_results(
            price_all_bundle,
            runtime_bindings=self,
        )

    def build_portfolio_router_input(self, *, price_all_bundle: Any, router_decision: Any) -> Any:
        self._validate_self()
        from domain import current_shadow_all_market_portfolio as portfolio

        return portfolio._build_shadow_portfolio_router_input(
            price_all_bundle=price_all_bundle,
            router_decision=router_decision,
            runtime_bindings=self,
        )

    def verify_portfolio_router_input(self, value: Any) -> Any:
        self._validate_self()
        from domain import current_shadow_all_market_portfolio as portfolio

        return portfolio._verify_shadow_portfolio_router_input(
            value,
            runtime_bindings=self,
        )

    def optimize_portfolio(
        self,
        router_inputs: Any,
        *,
        target_size: int,
        evaluation_time: Any,
    ) -> Any:
        self._validate_self()
        from domain import current_shadow_all_market_portfolio as portfolio

        return portfolio._optimize_shadow_portfolio(
            router_inputs,
            target_size=target_size,
            evaluation_time=evaluation_time,
            runtime_bindings=self,
        )

    def refresh_selected_inputs(self, sources: Any, *, repository_root: Any) -> Any:
        self._validate_self()
        if not self.fresh_reprice_enabled:
            return sources
        from domain import current_shadow_fresh_reprice_runtime as fresh_runtime

        return fresh_runtime.refresh_selected_inputs(
            sources,
            repository_root=repository_root,
            runtime_bindings=self,
        )


def _make_bindings(composition: str) -> CurrentShadowRuntimeBindings:
    value = object.__new__(CurrentShadowRuntimeBindings)
    object.__setattr__(value, "composition", composition)
    object.__setattr__(value, "policy_id", POLICY_ID)
    object.__setattr__(value, "canonical_sha256", _binding_sha256(composition=composition))
    object.__setattr__(value, "_verified_contexts", _VerifiedContextMemo())
    value._validate_self()
    return value


@lru_cache(maxsize=1)
def default_current_shadow_runtime_bindings() -> CurrentShadowRuntimeBindings:
    return _make_bindings(STANDARD_COMPOSITION)


def fresh_reprice_current_shadow_runtime_bindings() -> CurrentShadowRuntimeBindings:
    return _make_bindings(FRESH_REPRICE_COMPOSITION)


def runtime_bindings_for_context(value: Any) -> CurrentShadowRuntimeBindings:
    from domain import _current_shadow_quote_binding as quote_binding

    if type(value) is not quote_binding.CurrentShadowPriceContext:
        raise ShadowPriceError("runtime binding requires exact CurrentShadowPriceContext")
    candidate = getattr(value, "_runtime_bindings", None)
    if candidate is None:
        return default_current_shadow_runtime_bindings()
    if type(candidate) is not CurrentShadowRuntimeBindings:
        raise ShadowPriceError("Current Shadow context carries an unreviewed execution binding")
    candidate._validate_self()
    return candidate


__all__ = [
    "CurrentShadowRuntimeBindings",
    "FRESH_REPRICE_COMPOSITION",
    "POLICY_ID",
    "STANDARD_COMPOSITION",
    "default_current_shadow_runtime_bindings",
    "fresh_reprice_current_shadow_runtime_bindings",
    "policy_payload",
    "policy_sha256",
    "runtime_bindings_for_context",
]
