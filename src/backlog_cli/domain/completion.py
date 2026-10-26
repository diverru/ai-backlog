"""How a unit or an item ended."""

from dataclasses import dataclass

from backlog_cli.domain.part import Evidence
from backlog_cli.domain.record import Record
from backlog_cli.domain.vocabulary import Outcome
from backlog_cli.moment import Moment


@dataclass
class UnitCompletion(Record):
    outcome: Outcome
    completed_at: str
    reason: str | None
    superseded_by: str | None
    evidence: Evidence | None

    @classmethod
    def done(cls, evidence: Evidence) -> "UnitCompletion":
        return cls(Outcome.DONE, Moment.now(), None, None, evidence)

    @classmethod
    def cancelled(cls, reason: str) -> "UnitCompletion":
        return cls(Outcome.CANCELLED, Moment.now(), reason, None, None)

    @classmethod
    def superseded(cls, reason: str, replacement: str | None) -> "UnitCompletion":
        return cls(Outcome.SUPERSEDED, Moment.now(), reason, replacement, None)

    @classmethod
    def from_dict(cls, data: dict) -> "UnitCompletion":
        evidence = data["evidence"]
        return cls(
            outcome=Outcome(data["outcome"]),
            completed_at=data["completed_at"],
            reason=data["reason"],
            superseded_by=data["superseded_by"],
            evidence=Evidence.from_dict(evidence) if evidence else None,
        )


@dataclass
class ItemCompletion(Record):
    outcome: Outcome
    completed_at: str
    reason: str | None
    follow_up: str | None
    evidence: Evidence | None

    @classmethod
    def done(cls, evidence: Evidence) -> "ItemCompletion":
        return cls(Outcome.DONE, Moment.now(), None, None, evidence)

    @property
    def reason_text(self) -> str:
        """Why the item ended: the reason, or the result."""
        if self.reason:
            return self.reason
        return self.evidence.result if self.evidence else ""

    @classmethod
    def abandoned(
        cls, outcome: Outcome, reason: str, follow_up: str | None
    ) -> "ItemCompletion":
        return cls(outcome, Moment.now(), reason, follow_up, None)

    @classmethod
    def from_dict(cls, data: dict) -> "ItemCompletion":
        evidence = data["evidence"]
        return cls(
            outcome=Outcome(data["outcome"]),
            completed_at=data["completed_at"],
            reason=data["reason"],
            follow_up=data["follow_up"],
            evidence=Evidence.from_dict(evidence) if evidence else None,
        )
