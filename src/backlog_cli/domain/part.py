"""Small records used inside items and units."""

import re
from dataclasses import dataclass

from backlog_cli.domain.record import Record
from backlog_cli.errors import Refusal, UsageError
from backlog_cli.moment import Moment


@dataclass
class Evidence(Record):
    """What was observed, where, and when it was recorded.

    observed_at is when the fact happened; it is never the recording time.
    """

    source: str
    result: str
    observed_at: str | None
    recorded_at: str

    @classmethod
    def record_now(
        cls, source: str, result: str, observed_at: str | None = None
    ) -> "Evidence":
        return cls(source, result, observed_at, Moment.now())

    @classmethod
    def from_dict(cls, data: dict) -> "Evidence":
        return cls(
            source=data["source"],
            result=data["result"],
            observed_at=data["observed_at"],
            recorded_at=data["recorded_at"],
        )


@dataclass
class PrRef(Record):
    TEXT_PATTERN = re.compile(
        r"^([A-Za-z0-9][A-Za-z0-9_.-]*)/([A-Za-z0-9][A-Za-z0-9_.-]*)#([1-9][0-9]{0,8})$"
    )
    repo: str
    number: int

    def __str__(self) -> str:
        return f"{self.repo}#{self.number}"

    @classmethod
    def from_text(cls, text: str, flag: str) -> "PrRef":
        match = cls.TEXT_PATTERN.match(text)
        if not match:
            raise UsageError(
                f"{flag}: invalid PR reference {text!r}; "
                "use OWNER/NAME#N (at most 9 digits), e.g. acme/api#123"
            )
        return cls(f"{match[1]}/{match[2]}".lower(), int(match[3]))

    @classmethod
    def from_dict(cls, data: dict) -> "PrRef":
        return cls(repo=data["repo"].lower(), number=data["number"])


@dataclass
class Assignee(Record):
    TASK_PATTERN = re.compile(r"^([^:\s]+):([1-9][0-9]*)$")
    project: str | None
    task_seq: int | None
    agent: str
    role: str | None

    @staticmethod
    def split_matching(
        assignees: list["Assignee"],
        agent: str | None,
        task: str | None,
        role: str | None,
    ) -> tuple[list["Assignee"], list["Assignee"]]:
        """Split into (kept, removed): `removed` have this agent, task or role."""
        removed = [
            known
            for known in assignees
            if (agent is not None and known.agent == agent)
            or (task is not None and known.task_text == task)
            or (role is not None and known.role == role)
        ]
        if not removed:
            wanted = agent or task or role
            raise Refusal(f"no assignee matches {wanted!r}")
        return [known for known in assignees if known not in removed], removed

    def describe_left(self) -> str:
        """`agent X, task api:456`: who was working when the work was closed."""
        task = f", task {self.task_text}" if self.project is not None else ""
        return f"agent {self.agent}{task}"

    @property
    def task_text(self) -> str:
        """`api:470`, or an empty text without a task."""
        return f"{self.project}:{self.task_seq}" if self.project is not None else ""

    @property
    def named_text(self) -> str:
        """`agent "PR agent", task api:900, role back`: every field with its name."""
        parts = [f'agent "{self.agent}"']
        if self.project is not None:
            parts.append(f"task {self.project}:{self.task_seq}")
        if self.role:
            parts.append(f"role {self.role}")
        return ", ".join(parts)

    @property
    def short_text(self) -> str:
        """`api:470 Back agent`, or `Back agent (back)` without a task."""
        if self.project is not None:
            return f"{self.project}:{self.task_seq} {self.agent}"
        return f"{self.agent} ({self.role})" if self.role else self.agent

    @classmethod
    def from_flags(
        cls, task: str | None, agent: str | None, role: str | None
    ) -> list["Assignee"]:
        """Build the assignee of `--task api:456 --agent NAME --role R`.

        No flags at all means no assignee.
        """
        if not (task or agent or role):
            return []
        if not agent:
            raise UsageError("--agent is required when --task or --role is given")
        if not task:
            return [cls(None, None, agent, role)]
        match = cls.TASK_PATTERN.match(task)
        if not match:
            raise UsageError(f"invalid --task {task!r}; use PROJECT:SEQ, e.g. api:456")
        return [cls(match[1], int(match[2]), agent, role)]

    @classmethod
    def from_dict(cls, data: dict) -> "Assignee":
        return cls(
            project=data["project"],
            task_seq=data["task_seq"],
            agent=data["agent"],
            role=data["role"],
        )


@dataclass
class Blocker(Record):
    """An external condition. It is not an item and has no id outside its item."""

    id: str
    description: str
    waiting_on: str | None

    @classmethod
    def from_dict(cls, data: dict) -> "Blocker":
        return cls(
            id=data["id"],
            description=data["description"],
            waiting_on=data["waiting_on"],
        )


@dataclass
class ResolvedBlocker(Record):
    """A blocker that no longer blocks. It is kept, with when and why."""

    id: str
    description: str
    waiting_on: str | None
    resolved_at: str
    reason: str | None

    @classmethod
    def from_dict(cls, data: dict) -> "ResolvedBlocker":
        return cls(
            id=data["id"],
            description=data["description"],
            waiting_on=data["waiting_on"],
            resolved_at=data["resolved_at"],
            reason=data["reason"],
        )


@dataclass
class ReturnRecord(Record):
    """An explicit step back to todo, with why."""

    at: str
    reason: str

    @classmethod
    def from_dict(cls, data: dict) -> "ReturnRecord":
        return cls(at=data["at"], reason=data["reason"])


@dataclass
class Finding(Record):
    """A failed post-release check: what was found, and how it is known."""

    at: str  # When the check found it, never the time of recording.
    text: str
    source: str
    known_units: list[str]  # Units of the item then: a fix is a unit not in it.
    recorded_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "Finding":
        return cls(
            at=data["at"],
            text=data["text"],
            source=data["source"],
            known_units=list(data["known_units"]),
            recorded_at=data["recorded_at"],
        )


@dataclass
class Correction(Record):
    """A wrong merge or release record that was replaced, with the old values."""

    at: str
    subject: str  # `merge` or `release`
    reason: str
    old_pr: PrRef | None
    old_at: str | None
    old_evidence: Evidence | None
    old_tag: str | None

    @classmethod
    def from_dict(cls, data: dict) -> "Correction":
        return cls(
            at=data["at"],
            subject=data["subject"],
            reason=data["reason"],
            old_pr=PrRef.from_dict(data["old_pr"]) if data["old_pr"] else None,
            old_at=data["old_at"],
            old_evidence=(
                Evidence.from_dict(data["old_evidence"])
                if data["old_evidence"]
                else None
            ),
            old_tag=data["old_tag"],
        )

    def describe(self) -> str:
        """The old values in one line, for the output of the correction."""
        parts = [
            f"pr {self.old_pr}" if self.old_pr else "",
            f"at {self.old_at}" if self.old_at else "",
            f"tag {self.old_tag}" if self.old_tag else "",
            f"source {self.old_evidence.source}" if self.old_evidence else "",
        ]
        return ", ".join(part for part in parts if part) or "nothing recorded"
