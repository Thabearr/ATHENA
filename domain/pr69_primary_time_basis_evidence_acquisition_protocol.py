"""Pre-register primary football-data.co.uk time-basis evidence acquisition.

This boundary freezes capture/provenance/admissibility rules before any runner or
network execution. It does not infer a timezone, backdate current documentation,
or authorize PR80/model/probability/pricing/selection/BET use.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import types
from collections.abc import Mapping
from typing import Any

import domain.pr69_source_local_time_basis_resolution_qualification as pr123

SCHEMA_VERSION = 1
PROTOCOL_ID = "REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_PROTOCOL_V1"
PROTOCOL_SCOPE = "PRE_REGISTERED_PRIMARY_FOOTBALL_DATA_UK_TIME_BASIS_EVIDENCE_ACQUISITION_ONLY_NO_EXECUTION"
PROTOCOL_STATE = "PRE_REGISTERED_NOT_EXECUTED_PRIMARY_TIME_BASIS_EVIDENCE_NOT_CAPTURED"
REPOSITORY_MAIN_SHA = "620d1c5e3bcbb9fe5223a3f6348d04d11ebc1e44"
PR123_QUALIFICATION_BLOB_SHA = "b5b8037264b8c5f57b9728f902f20de75067da6b"
PR123_RECEIPT_SHA256 = "a3736753862781efc9d8ce6c15aa814185b73ed14fea82c4e8ebaa10a3ab656c"
PR123_RECEIPT_SIZE = 12_025
BLOCKING_STATUS = "BLOCKED_NO_ADMISSIBLE_PRIMARY_TIME_BASIS_EVIDENCE"
PRIMARY_ORIGIN = "https://www.football-data.co.uk"
CAPTURE_ROOT = ".cache/athena-research/pr69-primary-time-basis-evidence"
SEASONS = ("2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26")
MODEL_LEAGUE_CODES = ("B1", "D1", "E0", "F1", "G1", "I1", "N1", "P1", "SC0", "SP1", "T1")
SOURCE_FILE_COUNT = 66
SOURCE_FIXTURE_COUNT = 21_226
SOURCE_TOTAL_BYTES = 10_006_877
CAPTURE_SLOTS = ("A", "B")
REQUIRED_SUCCESSFUL_CAPTURE_COUNT = 8
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
NEXT_REQUIRED_BOUNDARY = "IMPLEMENT_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_RUNNER"

LINEAGE_REQUIREMENTS = (
 "PRESERVE_EXACT_HTTP_BODY_BYTES_BEFORE_TEXT_DECODING_OR_NORMALIZATION",
 "RECORD_RAW_SHA256_BYTE_SIZE_TARGET_SLOT_ATTEMPT_URL_REQUEST_AND_RESPONSE_UTC_TIMESTAMPS_AND_SELECTED_RESPONSE_HEADERS",
 "PRESERVE_RAW_BYTES_MANIFEST_CAMPAIGN_INDEX_AND_FAILURE_JOURNAL_WITH_NO_OVERWRITE",
 "RETAIN_EVERY_FAILED_ATTEMPT_EVEN_IF_A_LATER_RETRY_SUCCEEDS",
 "KEEP_RAW_CAPTURE_AND_CAMPAIGN_EVIDENCE_OUTSIDE_GIT",
)
FAILURE_HANDLING_RULES = (
 "ANY_REQUIRED_TARGET_WITHOUT_TWO_VALID_SUCCESSFUL_SLOTS_BLOCKS_ACQUISITION_COMPLETENESS",
 "HTTP_NON_200_TIMEOUT_TLS_CONTENT_TYPE_BODY_SIZE_HASH_MANIFEST_OR_DURABILITY_FAILURE_FAILS_CLOSED_AND_IS_RECORDED",
 "PAIR_CONTENT_DRIFT_IS_PRESERVED_AND_EXPLICITLY_CLASSIFIED_NEVER_OVERWRITTEN",
 "NO_FAILED_OR_MISSING_PRIMARY_CAPTURE_MAY_BE_FILLED_FROM_SEARCH_CACHE_WEB_ARCHIVE_OR_ANOTHER_PROVIDER",
 "REDIRECTS_ARE_NOT_AUTHORIZED",
)
CONFLICT_HANDLING_RULES = (
 "RETAIN_EVERY_CONFLICTING_PRIMARY_STATEMENT_OR_VERSION_WITH_ITS_RAW_HASH_AND_SCOPE_EVIDENCE",
 "DO_NOT_RESOLVE_CONFLICTS_BY_MAJORITY_VOTE_RECENCY_RESULT_FIT_OR_CONVENIENCE",
 "TIMEZONE_OFFSET_DST_OR_CIVIL_TIME_CONFLICT_BLOCKS_RESOLUTION_UNTIL_SEPARATELY_REVIEWED",
 "CURRENT_SEMANTICS_AND_HISTORICAL_EFFECTIVE_SCOPE_ARE_SEPARATE_FACTS",
 "NO_OBSERVED_CONFLICT_DOES_NOT_PROVE_HISTORICAL_SEMANTICS_WERE_UNCHANGED",
)
FORBIDDEN_SHORTCUTS = (
 "DO_NOT_INFER_CSV_TIMEZONE_FROM_LEAGUE_COUNTRY_TEAM_VENUE_OR_COMMON_FOOTBALL_PRACTICE",
 "DO_NOT_TREAT_FOTMOB_EUROPE_OSLO_OR_ANY_CROSS_SOURCE_CLOCK_AS_PRIMARY_REFERENCE_EVIDENCE",
 "DO_NOT_TREAT_SEARCH_SNIPPETS_CACHES_OR_THIRD_PARTY_ARCHIVES_AS_ADMISSIBLE_PRIMARY_EVIDENCE",
 "DO_NOT_BACKDATE_CURRENT_NOTES_TXT_TO_THE_FROZEN_SIX_SEASONS_WITHOUT_PRIMARY_EFFECTIVE_SCOPE_EVIDENCE",
 "DO_NOT_TREAT_SITE_WIDE_UK_TIME_OR_BRITISH_STANDARD_TIME_WORDING_AS_THE_CSV_TIME_RULE_UNLESS_PRIMARY_BYTES_EXPLICITLY_LINK_THEM",
 "DO_NOT_TREAT_HTTP_LAST_MODIFIED_ETAG_OR_CAPTURE_DATE_ALONE_AS_HISTORICAL_EFFECTIVE_SCOPE",
 "DO_NOT_TREAT_TIME_EQUALS_MATCH_KICK_OFF_AS_A_TIMEZONE_OFFSET_OR_DST_RULE",
 "DO_NOT_USE_BROWSER_IMPERSONATION_COOKIES_PROXY_EVASION_OR_ANTI_BOT_BYPASS",
)
SAFETY_KEYS = frozenset({
 "network_acquisition_authorized", "primary_time_basis_evidence_acquisition_executed",
 "primary_time_basis_evidence_admissibility_qualified", "pr69_source_local_time_basis_resolved",
 "source_local_time_semantic_equivalence_qualified", "pr80_constructor_input_authorized",
 "model_training_authorized", "successor_live_inputs_qualified", "successor_candidate_approved",
 "expected_goals_transform_approved", "expected_goals_production_authorized", "score_matrix_authorized",
 "probability_inference_authorized", "probability_adjustment_authorized", "calibration_for_production_authorized",
 "pricing_authorized", "market_activation_authorized", "selection_authorized", "production_approval_authorized", "bet_authorized",
})
PROTOCOL_SHA256 = "28ec0a0208858ce3258a584bad1361577a0e202e5cbdb8eb9b13cdd47d7455a3"
PROTOCOL_SIZE = 9_039

class PR69PrimaryTimeBasisEvidenceAcquisitionProtocolError(ValueError):
 pass

def _error(message: str) -> PR69PrimaryTimeBasisEvidenceAcquisitionProtocolError:
 return PR69PrimaryTimeBasisEvidenceAcquisitionProtocolError(message)

def _canonical(value: Any) -> bytes:
 try:
  encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
 except (TypeError, ValueError, OverflowError) as exc:
  raise _error("PR124 protocol serialization failed") from exc
 return (encoded + "\n").encode("utf-8")

def _safety() -> Mapping[str, bool]:
 return types.MappingProxyType({key: False for key in sorted(SAFETY_KEYS)})

@dataclasses.dataclass(frozen=True)
class PrimaryEvidenceTarget:
 target_id: str
 path: str
 role: str
 content_type_prefix: str
 interpretation_limit: str
 def __post_init__(self) -> None:
  if not all(type(v) is str and v for v in (self.target_id, self.path, self.role, self.content_type_prefix, self.interpretation_limit)):
   raise _error("target fields must be exact non-empty text")
  if not self.path.startswith("/"):
   raise _error("target path must be absolute")
 def to_dict(self) -> dict[str, Any]:
  return {"target_id":self.target_id,"url":PRIMARY_ORIGIN+self.path,"path":self.path,"role":self.role,"content_type_prefix":self.content_type_prefix,"interpretation_limit":self.interpretation_limit}

def _targets() -> tuple[PrimaryEvidenceTarget, ...]:
 return (
  PrimaryEvidenceTarget("NOTES_TXT","/notes.txt","PRIMARY_FIELD_DICTIONARY","text/plain","FIELD_SEMANTICS_ONLY_UNLESS_BYTES_EXPLICITLY_DEFINE_TIMEZONE_OFFSET_DST_AND_EFFECTIVE_SCOPE"),
  PrimaryEvidenceTarget("DATA_OVERVIEW","/data.php","PRIMARY_DATASET_LINEAGE_CONTEXT","text/html","DATASET_CONTEXT_ONLY_NOT_CSV_TIMEZONE_WITHOUT_EXPLICIT_LINKED_SEMANTICS"),
  PrimaryEvidenceTarget("HISTORICAL_DOWNLOAD_OVERVIEW","/downloadm.php","PRIMARY_HISTORICAL_DOWNLOAD_CONTEXT","text/html","CURRENT_PAGE_PRESENCE_ALONE_IS_NOT_RETROACTIVE_SCOPE_PROOF"),
  PrimaryEvidenceTarget("FIXTURES_OVERVIEW","/matches.php","PRIMARY_SITE_CLOCK_CONTEXT","text/html","UK_TIME_OR_BST_WORDING_IS_CONTEXT_ONLY_UNLESS_EXPLICITLY_BOUND_TO_CSV_TIME"),
 )
def _payload() -> dict[str, Any]:
 return {
  "schema_version":SCHEMA_VERSION,"protocol_id":PROTOCOL_ID,"protocol_scope":PROTOCOL_SCOPE,"protocol_state":PROTOCOL_STATE,
  "repository_main_sha":REPOSITORY_MAIN_SHA,"pr123_qualification_blob_sha":PR123_QUALIFICATION_BLOB_SHA,
  "pr123_receipt_sha256":PR123_RECEIPT_SHA256,"pr123_receipt_size":PR123_RECEIPT_SIZE,"blocking_status":BLOCKING_STATUS,
  "prior_discovery":{"url":pr123.DISCOVERY_URL,"observed_time_field_description":pr123.DISCOVERY_TIME_FIELD_DESCRIPTION,"prior_classification":"NON_ADMISSIBLE_PRIMARY_DISCOVERY_CANDIDATE","preserved_as_resolution_evidence":False},
  "request_identity":{"method":"GET","scheme":"https","host":"www.football-data.co.uk","port":443,"request_headers":[["Accept","text/plain,text/html;q=0.9,*/*;q=0.1"],["Accept-Encoding","identity"],["User-Agent","ATHENA/1.0"]],"redirects_authorized":False,"cookies_authorized":False,"browser_impersonation_authorized":False,"proxy_evasion_authorized":False,"tls_verification_required":True},
  "targets":[x.to_dict() for x in _targets()],
  "capture_schedule":{"target_count":4,"capture_slots_per_target":2,"slot_labels":list(CAPTURE_SLOTS),"pass_order":"ALL_TARGETS_SLOT_A_IN_FROZEN_ORDER_THEN_ALL_TARGETS_SLOT_B_IN_FROZEN_ORDER","minimum_same_target_pair_separation_seconds":300,"maximum_same_target_pair_separation_seconds":3600,"minimum_inter_request_seconds":1.0,"maximum_attempts_per_slot":3,"retry_delays_seconds":[60,300],"required_successful_capture_count":REQUIRED_SUCCESSFUL_CAPTURE_COUNT,"failed_attempts_count_as_success":False},
  "capture_contract":{"capture_root":CAPTURE_ROOT,"raw_body_filename":"response.bin","manifest_filename":"manifest.json","campaign_index_filename":"campaign-index.jsonl","failure_journal_filename":"failure-journal.jsonl","hash_algorithm":"SHA256","max_response_bytes":MAX_RESPONSE_BYTES,"accepted_http_statuses":[200],"raw_body_hashed_before_decode":True,"raw_body_line_endings_normalized_before_hash":False,"raw_body_charset_normalized_before_hash":False,"selected_response_headers":["cache-control","content-encoding","content-length","content-type","date","etag","last-modified","location","server"],"manifest_must_record_request_started_at_utc":True,"manifest_must_record_response_completed_at_utc":True,"manifest_must_record_observed_at_utc":True,"manifest_must_record_final_url":True,"manifest_must_record_tls_verified":True,"manifest_must_record_raw_sha256_and_size":True,"no_overwrite":True},
  "admissibility_contract":{"primary_origin_must_equal":PRIMARY_ORIGIN,"exact_raw_bytes_and_sha256_required":True,"successful_capture_manifest_required":True,"same_origin_final_url_required":True,"redirect_chain_must_be_empty":True,"tls_verified_required":True,"content_type_must_match_target":True,"semantic_extract_must_reference_raw_sha256_and_exact_byte_or_line_location":True,"time_field_definition_required":True,"timezone_or_offset_or_civil_time_rule_must_be_explicit_for_direct_resolution":True,"dst_transition_semantics_must_be_explicit_when_applicable":True,"historical_effective_scope_must_be_separately_proven":True,"search_results_and_third_party_archives_discovery_only":True,"current_capture_alone_proves_historical_scope":False,"site_clock_wording_alone_proves_csv_time_basis":False},
  "effective_scope_contract":{"frozen_seasons":list(SEASONS),"frozen_model_league_codes":list(MODEL_LEAGUE_CODES),"source_file_count":SOURCE_FILE_COUNT,"source_fixture_count":SOURCE_FIXTURE_COUNT,"source_total_bytes":SOURCE_TOTAL_BYTES,"every_source_file_must_map_to_primary_effective_scope_or_remain_unresolved":True,"every_fixture_row_must_inherit_only_from_its_proven_source_file_scope":True,"current_documentation_must_not_be_backdated_without_primary_scope_evidence":True,"http_metadata_must_not_substitute_for_semantic_effective_scope":True,"version_changes_and_conflicts_must_be_preserved":True,"full_athena_competition_universe_claimed":False},
  "lineage_requirements":list(LINEAGE_REQUIREMENTS),"failure_handling_rules":list(FAILURE_HANDLING_RULES),"conflict_handling_rules":list(CONFLICT_HANDLING_RULES),"forbidden_shortcuts":list(FORBIDDEN_SHORTCUTS),
  "execution_output_contract":{"raw_capture_bundle_required":True,"campaign_index_required":True,"failure_journal_required":True,"pair_drift_table_required":True,"primary_semantic_extract_inventory_required":True,"historical_effective_scope_inventory_required":True,"primary_evidence_conflict_table_required":True,"source_file_scope_coverage_accounting_required":True,"fixture_row_scope_coverage_accounting_required":True,"pr69_source_local_time_basis_resolution_performed":False,"fotmob_equivalence_assessment_performed":False,"pr80_constructor_input_authorized":False,"next_required_boundary":NEXT_REQUIRED_BOUNDARY},
  "network_acquisition_performed":False,"campaign_runner_implemented":False,"evidence_records_captured":0,"next_required_boundary":NEXT_REQUIRED_BOUNDARY,"safety":dict(_safety()),
 }

def _verify_upstream() -> None:
 if (pr123.RECEIPT_SHA256,pr123.RECEIPT_SIZE)!=(PR123_RECEIPT_SHA256,PR123_RECEIPT_SIZE): raise _error("PR123 receipt identity changed")
 receipt=pr123.load_pr69_source_local_time_basis_resolution_qualification_receipt()
 if pr123.QUALIFICATION_STATUS!=BLOCKING_STATUS: raise _error("PR123 blocker changed")
 if pr123.NEXT_REQUIRED_BOUNDARY!="PRE_REGISTER_REVIEWED_PR69_PRIMARY_TIME_BASIS_EVIDENCE_ACQUISITION_PROTOCOL": raise _error("PR123 next boundary changed")
 if receipt.get("remaining_blockers")!=[BLOCKING_STATUS]: raise _error("PR123 blocker set changed")
 if receipt.get("row_coverage_accounting",{}).get("unresolved_rows")!=SOURCE_FIXTURE_COUNT: raise _error("PR123 unresolved row count changed")
 if receipt.get("frozen_scope")!={"source":"football_data_uk_csv","source_local_timezone_state":"SOURCE_LOCAL_TIMEZONE_UNRESOLVED","source_file_count":SOURCE_FILE_COUNT,"source_total_bytes":SOURCE_TOTAL_BYTES,"source_fixture_count":SOURCE_FIXTURE_COUNT,"seasons":list(SEASONS),"model_league_codes":list(MODEL_LEAGUE_CODES),"full_athena_competition_universe_claimed":False}: raise _error("PR123 frozen scope changed")

@dataclasses.dataclass(frozen=True)
class PR69PrimaryTimeBasisEvidenceAcquisitionProtocol:
 schema_version:int; protocol_id:str; protocol_scope:str; protocol_state:str; repository_main_sha:str; pr123_qualification_blob_sha:str; pr123_receipt_sha256:str; pr123_receipt_size:int; blocking_status:str; prior_discovery:Mapping[str,Any]; request_identity:Mapping[str,Any]; targets:tuple[PrimaryEvidenceTarget,...]; capture_schedule:Mapping[str,Any]; capture_contract:Mapping[str,Any]; admissibility_contract:Mapping[str,Any]; effective_scope_contract:Mapping[str,Any]; lineage_requirements:tuple[str,...]; failure_handling_rules:tuple[str,...]; conflict_handling_rules:tuple[str,...]; forbidden_shortcuts:tuple[str,...]; execution_output_contract:Mapping[str,Any]; network_acquisition_performed:bool; campaign_runner_implemented:bool; evidence_records_captured:int; next_required_boundary:str; safety:Mapping[str,bool]
 def __post_init__(self)->None:
  if self.to_dict()!=_payload(): raise _error("PR124 protocol differs from frozen contract")
  if self.network_acquisition_performed is not False or self.campaign_runner_implemented is not False or self.evidence_records_captured!=0: raise _error("PR124 preregistration may not claim execution")
  if set(self.safety)!=SAFETY_KEYS or any(v is not False for v in self.safety.values()): raise _error("all PR124 safety values must remain false")
 def to_dict(self)->dict[str,Any]:
  return {"schema_version":self.schema_version,"protocol_id":self.protocol_id,"protocol_scope":self.protocol_scope,"protocol_state":self.protocol_state,"repository_main_sha":self.repository_main_sha,"pr123_qualification_blob_sha":self.pr123_qualification_blob_sha,"pr123_receipt_sha256":self.pr123_receipt_sha256,"pr123_receipt_size":self.pr123_receipt_size,"blocking_status":self.blocking_status,"prior_discovery":dict(self.prior_discovery),"request_identity":dict(self.request_identity),"targets":[x.to_dict() for x in self.targets],"capture_schedule":dict(self.capture_schedule),"capture_contract":dict(self.capture_contract),"admissibility_contract":dict(self.admissibility_contract),"effective_scope_contract":dict(self.effective_scope_contract),"lineage_requirements":list(self.lineage_requirements),"failure_handling_rules":list(self.failure_handling_rules),"conflict_handling_rules":list(self.conflict_handling_rules),"forbidden_shortcuts":list(self.forbidden_shortcuts),"execution_output_contract":dict(self.execution_output_contract),"network_acquisition_performed":self.network_acquisition_performed,"campaign_runner_implemented":self.campaign_runner_implemented,"evidence_records_captured":self.evidence_records_captured,"next_required_boundary":self.next_required_boundary,"safety":dict(self.safety)}

def build_pr69_primary_time_basis_evidence_acquisition_protocol()->PR69PrimaryTimeBasisEvidenceAcquisitionProtocol:
 _verify_upstream(); p=_payload()
 return PR69PrimaryTimeBasisEvidenceAcquisitionProtocol(schema_version=p["schema_version"],protocol_id=p["protocol_id"],protocol_scope=p["protocol_scope"],protocol_state=p["protocol_state"],repository_main_sha=p["repository_main_sha"],pr123_qualification_blob_sha=p["pr123_qualification_blob_sha"],pr123_receipt_sha256=p["pr123_receipt_sha256"],pr123_receipt_size=p["pr123_receipt_size"],blocking_status=p["blocking_status"],prior_discovery=types.MappingProxyType(p["prior_discovery"]),request_identity=types.MappingProxyType(p["request_identity"]),targets=_targets(),capture_schedule=types.MappingProxyType(p["capture_schedule"]),capture_contract=types.MappingProxyType(p["capture_contract"]),admissibility_contract=types.MappingProxyType(p["admissibility_contract"]),effective_scope_contract=types.MappingProxyType(p["effective_scope_contract"]),lineage_requirements=tuple(p["lineage_requirements"]),failure_handling_rules=tuple(p["failure_handling_rules"]),conflict_handling_rules=tuple(p["conflict_handling_rules"]),forbidden_shortcuts=tuple(p["forbidden_shortcuts"]),execution_output_contract=types.MappingProxyType(p["execution_output_contract"]),network_acquisition_performed=False,campaign_runner_implemented=False,evidence_records_captured=0,next_required_boundary=NEXT_REQUIRED_BOUNDARY,safety=_safety())

def canonical_pr69_primary_time_basis_evidence_acquisition_protocol_bytes(value:PR69PrimaryTimeBasisEvidenceAcquisitionProtocol)->bytes:
 if type(value) is not PR69PrimaryTimeBasisEvidenceAcquisitionProtocol: raise _error("protocol must be exact PR124 type")
 return _canonical(value.to_dict())
