"""Local UI snapshot, never a run-admission or market-authority decision."""
from __future__ import annotations

import hashlib

from domain.component_authority_registry import ComponentAuthorityRegistry

from runtime.release_identity import DevelopmentCheckoutIdentity, InstalledReleaseIdentity
from runtime.resources import ResourceResolver
from services.athena_preview_service import AthenaPreviewAdmissionService
from services.athena_read_service import AthenaReadService


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
    def __init__(self, resources: ResourceResolver, *, preview_admission_service: AthenaPreviewAdmissionService,
                 read_service=None, job_service=None):
        if (type(resources) is not ResourceResolver
                or type(preview_admission_service) is not AthenaPreviewAdmissionService
                or preview_admission_service.resources is not resources):
            raise ValueError("verified capability dependencies required")
        if read_service is not None and type(read_service) is not AthenaReadService:
            raise ValueError("verified capability dependencies required")
        self.resources = resources
        self.preview_admission_service = preview_admission_service
        self.read_service = read_service
        if job_service is not None:
            from services.athena_job_service import AthenaJobService
            if (type(job_service) is not AthenaJobService
                    or job_service.preview_service is not preview_admission_service):
                raise ValueError("verified capability job dependency required")
        self.job_service = job_service

    def snapshot(self):
        raw = self.resources.read_bytes(CONTRACT_PATH, expected_role="AUTHORITY_REGISTRY")
        contract = ComponentAuthorityRegistry.from_json_bytes(raw)
        reference = hashlib.sha256(raw).hexdigest()
        # Parsing a verified registry proves local contract availability only.
        # It grants no execution/provider authority and no model qualification.
        preview_available = self.preview_admission_service.preview_source_available()
        admission_repository = getattr(self.preview_admission_service, "admission_repository", None)
        from database.run_repository import DurableRunRepository
        from services.athena_job_service import DurableRunReadAdapter
        durable_admission = (self.job_service is not None
                             and type(admission_repository) is DurableRunRepository
                             and self.job_service.run_repository is admission_repository)
        read_repository = getattr(self.read_service, "run_repository", None) if self.read_service is not None else None
        durable_history = type(read_repository) is DurableRunReadAdapter
        rows = [
            ("local_contract_inspection", "available" if contract.records else "unavailable_unproven",
             "Verified authority records: " + str(len(contract.records)) + ". This is local inspection only."),
            ("run_preview", "available" if preview_available else "unavailable_unproven",
             "Preview is local read-only computation and grants no execution authority." if preview_available
             else "The verified source identity is currently unavailable for local preview."),
            ("run_admission", "available" if durable_admission else "blocked_implementation",
             "Durable transactional admission with one offline-probe worker per admitted run." if durable_admission
             else "Durable app run storage and the later job service are not implemented by this shell."),
            ("run_history", "available" if durable_history else "blocked_implementation",
             "Durable run index and ordered event store over proven app state." if durable_history
             else "The durable run index and ordered event store are owned by later storage work."),
            ("retained_fixtures", "blocked_implementation",
             "A provider-free retained fixture index is not available in this shell."),
            ("local_export", "blocked_implementation",
             "The durable export repository and service are owned by later storage work."),
            ("cancel_intent", "blocked_implementation",
             "Cancellation remains deferred to E3; E1 exposes observation only."),
            ("provider_acquisition", "blocked_authority", "This local control plane has no acquisition authority."),
            ("market_model_readiness", "unavailable_unproven", "No current model or market qualification is supplied."),
            ("legacy_generate", "deprecated_blocked",
             "Synchronous legacy generation is blocked; use the versioned preview and admission contract."),
            ("legacy_provider_api", "retained_compatibility", "Retained development routes are outside this shell."),
        ]
        return {"contract": "ATHENA_LOCAL_CAPABILITIES_V1", "release": release_summary(self.resources.identity),
                "registry_contract_ref": contract.canonical_sha256,
                "qualified_execution": [],
                "run_admission_authority": bool(durable_admission),
                "capabilities": [{"capability_id": key, "state": state, "reason": reason,
                                  "authority_profile": "LOCAL_CONTROL_PLANE", "scope": "UI_INFORMATION_ONLY",
                                  "identity_refs": [reference]} for key, state, reason in rows]}
