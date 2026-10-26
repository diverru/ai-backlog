"""A post-release action: something to do or check in production after a release."""

from dataclasses import dataclass, field

from backlog_cli.domain.part import Evidence, Finding
from backlog_cli.domain.record import Record
from backlog_cli.domain.vocabulary import ActionKind, ActionStatus
from backlog_cli.errors import Refusal
from backlog_cli.moment import Moment


@dataclass
class Action(Record):
    """Users say `done`; the file stores `confirmed`.

    Only a recorded result confirms anything.
    """

    id: str
    kind: ActionKind
    description: str
    instructions: str
    status: ActionStatus
    confirmation: Evidence | None
    cancel_reason: str | None
    findings: list[Finding] = field(default_factory=list)
    cancelled_at: str | None = None

    @classmethod
    def new(
        cls,
        action_id: str,
        kind: ActionKind,
        description: str,
        instructions: str,
    ) -> "Action":
        return cls(
            action_id,
            kind,
            description,
            instructions,
            ActionStatus.PENDING,
            None,
            None,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Action":
        confirmation = data["confirmation"]
        return cls(
            id=data["id"],
            kind=ActionKind(data["kind"]),
            description=data["description"],
            instructions=data["instructions"],
            status=ActionStatus(data["status"]),
            confirmation=Evidence.from_dict(confirmation) if confirmation else None,
            cancel_reason=data["cancel_reason"],
            findings=[Finding.from_dict(entry) for entry in data["findings"]],
            cancelled_at=data["cancelled_at"],
        )

    @property
    def is_pending(self) -> bool:
        return self.status == ActionStatus.PENDING

    def confirm(self, evidence: Evidence) -> None:
        self._require_pending()
        self.status = ActionStatus.CONFIRMED
        self.confirmation = evidence

    def cancel(self, reason: str) -> None:
        self._require_pending()
        self.status = ActionStatus.CANCELLED
        self.cancel_reason = reason
        self.cancelled_at = Moment.now()

    def record_failure(
        self, text: str, source: str, known_units: list[str], at: str | None
    ) -> Finding:
        """A failed check: the action stays pending, the finding is kept."""
        self._require_pending()
        if self.findings and self.findings[-1].text == text:
            raise Refusal(
                f"action {self.id} already has this finding as its last one; "
                "record a new finding only when the check found something new"
            )
        finding = Finding(at or Moment.now(), text, source, known_units, Moment.now())
        self.findings.append(finding)
        return finding

    @property
    def is_failed(self) -> bool:
        return self.is_pending and bool(self.findings)

    def _require_pending(self) -> None:
        if not self.is_pending:
            raise Refusal(
                f"action {self.id} is already {self.status}; "
                "a confirmation or cancellation is final"
            )
