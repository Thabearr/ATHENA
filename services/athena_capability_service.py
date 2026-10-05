"""Local UI snapshot, never a run-admission or market-authority decision."""
from __future__ import annotations

import hashlib

from domain.component_authority_registry import ComponentAuthorityRegistry

from runtime.release_identity import DevelopmentCheckoutIdentity, InstalledReleaseIdentity
from runtime.resources import ResourceResolver


CONTRACT_PATH = "config/architecture/component-authority-registry-v1.json"


def release_summary(identity):
    if type(identity) is InstalledReleaseIdentity:
        return {"source_mode": identity.identity_kind, "release_id": identity.release_id,
                "build_id": identity.build_id, "identity_ref": identity.manifest_sha256,
                "platform": identity.platform_tag, "architecture": identity.architecture_tag}
    if type(identity) is DevelopmentCheckoutIdentity:
        return {"source_mode": identity.identity_kind, "release_id": "development-checkout",
                "build_id": identity.head_commit_sha, "identity_ref": identity.head_commit_sha}
    raise ValueError("verified release identity required")


class AthenaCapabilityService:
    def __init__(self, resources: ResourceResolver):
        if type(resources) is not ResourceResolver:
            raise ValueError("verified resource resolver required")
        self.resources = resources

    def snapshot(self):
        raw = self.resources.read_bytes(CONTRACT_PATH, expected_role="AUTHORITY_REGISTRY")
        contract = ComponentAuthorityRegistry.from_json_bytes(raw)
        reference = hashlib.sha256(raw).hexdigest()
        # Parsing a verified registry proves local contract availability only.
        # It grants no execution/provider authority and no model qualification.
        rows = [
            ("local_contract_inspection", "available" if contract.records else "unavailable_unproven",
             "Verified authority records: " + str(len(contract.records)) + ". This is local inspection only."),
            ("run_preview", "blocked_implementation", "APP-01B admission is not implemented by this shell."),
            ("provider_acquisition", "blocked_authority", "This local control plane has no acquisition authority."),
            ("market_model_readiness", "unavailable_unproven", "No current model or market qualification is supplied."),
            ("legacy_provider_api", "retained_compatibility", "Retained development routes are outside this shell."),
        ]
        return {"contract": "ATHENA_LOCAL_CAPABILITIES_V1", "release": release_summary(self.resources.identity),
                "registry_contract_ref": contract.canonical_sha256,
                "qualified_execution": [],
                "run_admission_authority": False,
                "capabilities": [{"capability_id": key, "state": state, "reason": reason,
                                  "authority_profile": "LOCAL_CONTROL_PLANE", "scope": "UI_INFORMATION_ONLY",
                                  "identity_refs": [reference]} for key, state, reason in rows]}
