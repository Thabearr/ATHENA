"""Local UI snapshot, never a run-admission or market-authority decision."""
from __future__ import annotations

import hashlib

from domain.component_authority_registry import ComponentAuthorityRegistry

from runtime.release_identity import DevelopmentCheckoutIdentity, InstalledReleaseIdentity
from runtime.resources import ResourceResolver
from services.athena_preview_service import AthenaPreviewAdmissionService


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
    def __init__(self, resources: ResourceResolver, *, preview_admission_service: AthenaPreviewAdmissionService):
        if (type(resources) is not ResourceResolver
                or type(preview_admission_service) is not AthenaPreviewAdmissionService
                or preview_admission_service.resources is not resources):
            raise ValueError("verified capability dependencies required")
        self.resources = resources
        self.preview_admission_service = preview_admission_service

    def snapshot(self):
        raw = self.resources.read_bytes(CONTRACT_PATH, expected_role="AUTHORITY_REGISTRY")
        contract = ComponentAuthorityRegistry.from_json_bytes(raw)
        reference = hashlib.sha256(raw).hexdigest()
        # Parsing a verified registry proves local contract availability only.
        # It grants no execution/provider authority and no model qualification.
        preview_available = self.preview_admission_service.preview_source_available()
        rows = [
            ("local_contract_inspection", "available" if contract.records else "unavailable_unproven",
             "Verified authority records: " + str(len(contract.records)) + ". This is local inspection only."),
            ("run_preview", "available" if preview_available else "unavailable_unproven",
             "Preview is local read-only computation and grants no execution authority." if preview_available
             else "The verified source identity is currently unavailable for local preview."),
            ("run_admission", "blocked_implementation",
             "Durable app run storage and the later job service are not implemented by this shell."),
            ("run_history", "blocked_implementation",
             "The durable run index and ordered event store are owned by later storage work."),
            ("retained_fixtures", "blocked_implementation",
             "A provider-free retained fixture index is not available in this shell."),
            ("local_export", "blocked_implementation",
             "The durable export repository and service are owned by later storage work."),
            ("cancel_intent", "blocked_implementation",
             "A durable run store for cooperative cancel intent is not available in this shell."),
            ("provider_acquisition", "blocked_authority", "This local control plane has no acquisition authority."),
            ("market_model_readiness", "unavailable_unproven", "No current model or market qualification is supplied."),
            ("legacy_generate", "deprecated_blocked",
             "Synchronous legacy generation is blocked; use the versioned preview and admission contract."),
            ("legacy_provider_api", "retained_compatibility", "Retained development routes are outside this shell."),
        ]
        return {"contract": "ATHENA_LOCAL_CAPABILITIES_V1", "release": release_summary(self.resources.identity),
                "registry_contract_ref": contract.canonical_sha256,
                "qualified_execution": [],
                "run_admission_authority": False,
                "capabilities": [{"capability_id": key, "state": state, "reason": reason,
                                  "authority_profile": "LOCAL_CONTROL_PLANE", "scope": "UI_INFORMATION_ONLY",
                                  "identity_refs": [reference]} for key, state, reason in rows]}
