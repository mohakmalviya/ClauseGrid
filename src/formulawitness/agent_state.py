"""Typed state for the model-directed investigator and independent falsifier."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .formula import validate_formula_subset
from .trace import object_hash


class StrictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CitationEvidence(StrictRecord):
    citation_id: str = Field(pattern=r"^citation-[0-9a-f]{12}$")
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    exact_quote: str = Field(min_length=1, max_length=12_000)
    quote_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CandidateEdit(StrictRecord):
    sheet: str = Field(min_length=1, max_length=128)
    cell: str = Field(pattern=r"^[A-Z]{1,3}[1-9]\d*$")
    old_formula_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    new_formula: str = Field(min_length=2, max_length=8_192)
    rationale: str = Field(min_length=8, max_length=2_000)
    evidence_ids: tuple[str, ...] = Field(min_length=1, max_length=20)

    @field_validator("new_formula")
    @classmethod
    def formula_must_parse(cls, value: str) -> str:
        if not value.startswith("="):
            raise ValueError("Candidate formula must start with '='")
        validate_formula_subset(value)
        return value

    @property
    def edit_id(self) -> str:
        """Stable identity used to bind experiments to this exact edit."""

        return "edit-" + object_hash(self.model_dump(mode="json"))[:16]


class CandidateProposal(StrictRecord):
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    edits: tuple[CandidateEdit, ...] = Field(min_length=1, max_length=5)
    expected_invariants: tuple[str, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_targets(self) -> CandidateProposal:
        targets = {(edit.sheet.casefold(), edit.cell) for edit in self.edits}
        if len(targets) != len(self.edits):
            raise ValueError("Candidate proposal repeats a formula target")
        if len({edit.sheet.casefold() for edit in self.edits}) != 1:
            raise ValueError(
                "Candidate proposal must stay on one calculation sheet for atomic replay"
            )
        return self

    @property
    def proposal_id(self) -> str:
        return "proposal-" + object_hash(self.model_dump(mode="json"))[:16]


class ExperimentEvidence(StrictRecord):
    experiment_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    actor: Literal["audit-manager", "falsifier"]
    proposal_id: str | None = Field(default=None, pattern=r"^proposal-[0-9a-f]{16}$")
    candidate_edit_ids: tuple[str, ...] = Field(default=(), max_length=5)
    candidate_sensitive_observations: tuple[str, ...] = Field(default=(), max_length=100)
    request: dict[str, Any]
    observation: dict[str, Any]

    @model_validator(mode="after")
    def candidate_binding_is_complete(self) -> ExperimentEvidence:
        if self.candidate_edit_ids and self.proposal_id is None:
            raise ValueError("Candidate edit bindings require a proposal id")
        if self.candidate_sensitive_observations and not self.candidate_edit_ids:
            raise ValueError("Candidate-sensitive observations require candidate edit bindings")
        return self


class FalsifierVerdict(StrictRecord):
    status: Literal["BROKEN", "SURVIVED", "INCONCLUSIVE"]
    proposal_id: str = Field(pattern=r"^proposal-[0-9a-f]{16}$")
    experiment_ids: tuple[str, ...] = Field(max_length=50)
    counterexamples: tuple[str, ...] = Field(max_length=20)
    remaining_risks: tuple[str, ...] = Field(max_length=20)
    explanation: str = Field(min_length=8, max_length=4_000)

    @model_validator(mode="after")
    def broken_requires_reproducible_evidence(self) -> FalsifierVerdict:
        if self.status == "BROKEN" and (not self.counterexamples or not self.experiment_ids):
            raise ValueError("A broken verdict requires an executed counterexample")
        return self


class AgentDecision(StrictRecord):
    decision: Literal["REPAIR", "NO_CHANGE", "ABSTAIN"]
    explanation: str = Field(min_length=8, max_length=4_000)
    evidence_ids: tuple[str, ...] = Field(max_length=100)
    proposal_id: str | None = None


@dataclass
class AgentRunState:
    run_id: str
    source_sha256: str
    policy_sha256: str
    citations: dict[str, CitationEvidence] = field(default_factory=dict)
    experiments: dict[str, ExperimentEvidence] = field(default_factory=dict)
    candidate: CandidateProposal | None = None
    falsifier_verdict: FalsifierVerdict | None = None
    decision: AgentDecision | None = None
    candidate_history: list[str] = field(default_factory=list)

    def public_snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source_sha256": self.source_sha256,
            "policy_sha256": self.policy_sha256,
            "citations": {
                key: value.model_dump(mode="json") for key, value in self.citations.items()
            },
            "experiments": {
                key: value.model_dump(mode="json") for key, value in self.experiments.items()
            },
            "candidate": (
                None if self.candidate is None else self.candidate.model_dump(mode="json")
            ),
            "falsifier_verdict": (
                None
                if self.falsifier_verdict is None
                else self.falsifier_verdict.model_dump(mode="json")
            ),
            "decision": None if self.decision is None else self.decision.model_dump(mode="json"),
            "candidate_history": list(self.candidate_history),
        }
