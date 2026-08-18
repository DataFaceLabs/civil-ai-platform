"""Zoning Change dual-rail scenario models (ADR-0008)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AnalysisBasis = Literal["baseline", "proposed"]
ScenarioStatus = Literal["draft", "computed", "review", "accepted", "rejected"]
RiskLevel = Literal["low", "medium", "high", "unknown"]
DiffKind = Literal["unchanged", "changed", "added", "removed", "incomparable"]
FieldOrigin = Literal["lake", "user", "regtext", "determination", "composed"]
ComputationStatus = Literal["idle", "pending", "succeeded", "failed"]

ZoningRiskDriver = Literal[
    "entitlement_rezoning_required",
    "use_not_permitted",
    "use_conditional",
    "dimensional_more_restrictive",
    "dimensional_more_permissive",
    "impervious_interaction",
    "compatibility_trigger",
    "overlay_conflict",
    "jurisdiction_code_change",
    "corpus_gap",
    "district_unresolved",
    "standards_stale",
]

PROPOSED_BASIS_STATUSES: frozenset[str] = frozenset({"computed", "review", "accepted"})


class ScenarioFieldValue(BaseModel):
    """FieldValue-shaped value with scenario-rail provenance flavor."""

    value: str = ""
    status: str = "empty"
    data_status: str | None = None
    system_populated: bool | None = None
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    source_links: list[dict[str, Any]] = Field(default_factory=list)
    code_semantics: list[dict[str, Any]] = Field(default_factory=list)
    origin: FieldOrigin = "lake"


class OrdinanceEvidence(BaseModel):
    jurisdiction_key: str
    section_id: str
    citation: str
    title: str | None = None
    deep_link: str
    excerpt: str
    effective_date: str | None = None
    retrieved_at: str


class ZoningFactStructured(BaseModel):
    zoning_code: str | None = None
    zoning_base: str | None = None
    overlays: list[str] = Field(default_factory=list)
    jurisdiction_key: str | None = None
    ic_limit_pct: float | None = None


class ZoningFactBundle(BaseModel):
    fields: dict[str, ScenarioFieldValue] = Field(default_factory=dict)
    structured: ZoningFactStructured = Field(default_factory=ZoningFactStructured)


class NumericDiff(BaseModel):
    unit: str
    baseline: float
    proposed: float
    delta: float


class ZoningFactDiff(BaseModel):
    kind: DiffKind
    numeric: NumericDiff | None = None
    summary: str


class ZoningFactRisk(BaseModel):
    level: RiskLevel
    drivers: list[ZoningRiskDriver] = Field(default_factory=list)
    narrative: str | None = None


class ZoningFactComparison(BaseModel):
    fe_code: str
    baseline_value: str | None = None
    proposed_value: str | None = None
    diff: ZoningFactDiff
    risk: ZoningFactRisk
    evidence: list[OrdinanceEvidence] = Field(default_factory=list)
    needs_review: bool = True


class ZoningScenarioIntent(BaseModel):
    proposed_zoning_code: str
    proposed_zoning_base: str | None = None
    jurisdiction_key: str | None = None
    proposed_use_note: str | None = None
    keep_overlays: bool = True
    notes: str | None = None


class ZoningInputFingerprint(BaseModel):
    site_payload_fingerprint: str
    regtext_corpus_version: str | None = None
    dsi_version: str | None = None
    jurisdiction_key: str
    proposed_zoning_code: str


class ZoningRiskSummary(BaseModel):
    overall: RiskLevel = "unknown"
    entitlement_required: bool | None = None
    high_risk_fact_codes: list[str] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)


class ZoningComputationMeta(BaseModel):
    last_computed_at: str | None = None
    status: ComputationStatus = "idle"
    error: str | None = None
    agent_run_id: str | None = None


class ZoningChangeScenario(BaseModel):
    scenario_id: str
    label: str
    status: ScenarioStatus = "draft"
    created_at: str
    updated_at: str
    created_by_user_id: str
    intent: ZoningScenarioIntent
    input_fingerprint: ZoningInputFingerprint | None = None
    baseline: ZoningFactBundle = Field(default_factory=ZoningFactBundle)
    proposed: ZoningFactBundle = Field(default_factory=ZoningFactBundle)
    comparisons: list[ZoningFactComparison] = Field(default_factory=list)
    risk_summary: ZoningRiskSummary = Field(default_factory=ZoningRiskSummary)
    computation: ZoningComputationMeta = Field(default_factory=ZoningComputationMeta)


class OriginalJurisdictionSnapshotEntry(BaseModel):
    code: str
    label: str
    display: str


class OriginalJurisdictionSnapshot(BaseModel):
    """Immutable CAD jurisdiction/zoning capture written once at project create.

    Survives Accept Zone Change and is the source of truth for Recorded panel
    display and for reverting project facts back to the recorded jurisdiction.
    """

    captured_at: str
    entries: list[OriginalJurisdictionSnapshotEntry] = Field(default_factory=list)
    zoning_code: str | None = None
    zoning_text: str | None = None
    # Full restore maps (optional for older payloads).
    site_context_values: dict[str, str] | None = None
    zoning_field_values: dict[str, str] | None = None


class ZoningScenarioState(BaseModel):
    """Project-scoped dual-rail zoning scenario state (ADR-0008)."""

    schema_version: Literal[1] = 1
    analysis_basis: AnalysisBasis = "baseline"
    baseline_jurisdiction_key: str | None = None
    effective_jurisdiction_key: str | None = None
    active_scenario_id: str | None = None
    scenarios: list[ZoningChangeScenario] = Field(default_factory=list)
    # Write-once CAD original; must round-trip through project state PATCH/GET.
    original_jurisdiction_snapshot: OriginalJurisdictionSnapshot | None = None

    @field_validator("scenarios")
    @classmethod
    def _mvp_one_scenario(cls, value: list[ZoningChangeScenario]) -> list[ZoningChangeScenario]:
        if len(value) > 1:
            raise ValueError("MVP allows at most one zoning scenario per project")
        return value

    @model_validator(mode="after")
    def _validate_analysis_basis(self) -> ZoningScenarioState:
        if self.analysis_basis != "proposed":
            return self
        if not self.active_scenario_id:
            raise ValueError("analysis_basis=proposed requires active_scenario_id")
        active = next((s for s in self.scenarios if s.scenario_id == self.active_scenario_id), None)
        if active is None:
            raise ValueError("active_scenario_id does not match any scenario")
        if active.status not in PROPOSED_BASIS_STATUSES:
            raise ValueError(
                "analysis_basis=proposed requires active scenario status "
                f"in {sorted(PROPOSED_BASIS_STATUSES)}"
            )
        return self


def empty_zoning_scenario_state(
    *,
    baseline_jurisdiction_key: str | None = None,
) -> ZoningScenarioState:
    return ZoningScenarioState(baseline_jurisdiction_key=baseline_jurisdiction_key)


def zoning_scenario_from_dict(raw: dict[str, Any] | None) -> ZoningScenarioState | None:
    if raw is None:
        return None
    return ZoningScenarioState.model_validate(raw)
