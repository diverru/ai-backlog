"""Every closed set of values.

Member values are exactly the strings stored in YAML or printed by the tool.
"""

from enum import StrEnum

from backlog_cli.errors import UsageError


class Priority(StrEnum):
    """Declaration order is the sort order: most important first."""

    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ItemStatus(StrEnum):
    """The status of an item."""

    TODO = "todo"
    WIP = "wip"
    DONE = "done"
    # An item archived without being done keeps its outcome as its status.
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class UnitStatus(StrEnum):
    TODO = "todo"
    WIP = "wip"
    MERGED = "merged"
    POST_RELEASE = "post_release"
    DONE = "done"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"

    @property
    def is_early(self) -> bool:
        return self in (UnitStatus.TODO, UnitStatus.WIP)

    @property
    def is_terminal(self) -> bool:
        return self in (UnitStatus.DONE, UnitStatus.CANCELLED, UnitStatus.SUPERSEDED)


class UnitKind(StrEnum):
    PR = "pr"
    RESEARCH = "research"


class ActionKind(StrEnum):
    COMMAND = "command"
    VERIFICATION = "verification"
    ADMIN_CHANGE = "admin_change"

    @property
    def label(self) -> str:
        """How `list` names an action of this kind: check, command, admin change."""
        if self == ActionKind.VERIFICATION:
            return "check"
        return str(self).replace("_", " ")


class ActionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class Outcome(StrEnum):
    DONE = "done"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class MoveStatus(StrEnum):
    """What an action does to its targets.

    `released` is an event, never a stored status.
    """

    TODO = "todo"
    MERGED = "merged"
    RELEASED = "released"
    DONE = "done"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class DisplayStatus(StrEnum):
    """What `list` shows: the item status, or `stuck`."""

    TODO = "todo"
    WIP = "wip"
    DONE = "done"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    STUCK = "stuck"


class Readiness(StrEnum):
    """How far an item is from closing, the nearest first (the order of the
    members is the order of the Items page).
    """

    READY_TO_CLOSE = "ready_to_close"
    POST_RELEASE = "post_release"
    MERGED = "merged"
    WIP = "wip"
    TODO = "todo"


class ListSort(StrEnum):
    """The order of `list`; number is the default."""

    NUMBER = "number"
    PRIORITY = "priority"
    DUE = "due"


class AttentionGroup(StrEnum):
    """The groups of `list --attention`; the value is the printed heading."""

    BLOCKERS = "Unresolved blockers"
    REMINDERS = "Reminders due"
    OVERDUE = "Overdue"
    READY_TO_CLOSE = "Ready to close"
    FAILED = "Failed post-release checks"
    ACTIONS = "Pending post-release actions"
    MERGED = "Merged, waiting for release"
    UNASSIGNED = "In progress without an assignee"
    UNSTARTED_UNITS = "Units without an assignee"
    STUCK = "Stuck (every unit cancelled or superseded)"
    CAN_START = "Can start now"
    EMPTY_BRIEF = "Empty brief"


class DetailsSection(StrEnum):
    """The eight `##` headings of a details file, in file order."""

    PROBLEM = "Problem and expected result"
    SCOPE = "Scope and exclusions"
    FACTS = "Known facts and sources"
    DECISIONS = "Decisions and rationale"
    ACCEPTANCE = "Acceptance criteria"
    HANDOFF = "Agent handoff"
    HISTORY = "Implementation and release history"
    VERIFICATION = "Verification results, limitations and post-release instructions"


class AddressLevel(StrEnum):
    ITEM = "item"
    UNIT = "unit"
    ACTION = "action"


class ItemSource(StrEnum):
    """Where an item lives."""

    ACTIVE = "active"
    ARCHIVE = "archive"


class FlagEnum(StrEnum):
    """A request field that carries user text; the value is the field name."""

    @property
    def cli_name(self) -> str:
        return "--" + str(self).replace("_", "-")

    def require_text(self, text: str | None) -> None:
        """Text that is given must say something."""
        if text is not None and not text.strip():
            raise UsageError(f"{self.cli_name} must not be empty")


class MoveFlag(FlagEnum):
    """The fields of a MoveRequest; each value is the name of the field."""

    RESULT = "result"
    SOURCE = "source"
    AT = "at"
    REASON = "reason"
    BY = "by"
    PR = "pr"
    TAG = "tag"
    NO_POST_RELEASE = "no_post_release"
    NOT_NEEDED = "not_needed"
    CORRECTION = "correction"
