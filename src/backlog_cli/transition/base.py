"""What every `move` needs: the request flags and the per-target contract."""

from collections.abc import Callable
from dataclasses import dataclass, field

from backlog_cli.domain.address import Address
from backlog_cli.domain.item import Item
from backlog_cli.domain.part import Assignee, Evidence
from backlog_cli.domain.vocabulary import AddressLevel, MoveFlag, MoveStatus
from backlog_cli.errors import Obstacle, Refusal
from backlog_cli.moment import Moment
from backlog_cli.store.registry import Registry, Target


@dataclass
class MoveRequest:
    """What one action asks of its targets: a status and the facts that came with it."""

    status: MoveStatus
    result: str | None = None
    source: str | None = None
    at: str | None = None
    reason: str | None = None
    by: str | None = None
    pr: str | None = None
    tag: str | None = None
    no_post_release: list[str] = field(default_factory=list)  # unit addresses
    not_needed: bool = False
    correction: str | None = None
    batch: list[str] = field(default_factory=list)  # every address of the command

    def declares_no_post_release(self, address: str) -> bool:
        return address in self.no_post_release

    def get_observed_at(self) -> str | None:
        return Moment.parse_instant(self.at, "--at") if self.at else None

    def build_evidence(self, default_result: str | None = None) -> Evidence:
        result = self.result or default_result
        return Evidence.record_now(self.source, result, self.get_observed_at())


class AssigneeNote:
    """The line that tells the coordinator who is still working on closed work."""

    @staticmethod
    def build_lines(address: str, assignees: list[Assignee]) -> list[str]:
        return [
            f"{address}: assignee left: {assignee.describe_left()} — tell them to stop"
            for assignee in assignees
        ]


@dataclass(frozen=True)
class StatusSnapshot:
    address: str
    level: AddressLevel
    status: str

    @classmethod
    def take(cls, target: Target) -> list["StatusSnapshot"]:
        """Most specific first: the action, its unit, its item.

        A confirmed action can finish its unit, and that can move the item.
        """
        snapshots = []
        if target.action:
            snapshots.append(
                cls(str(target.address), AddressLevel.ACTION, str(target.action.status))
            )
        if target.unit:
            unit_address = str(Address(target.item.number, target.unit.id))
            snapshots.append(
                cls(unit_address, AddressLevel.UNIT, str(target.unit.status))
            )
        snapshots.append(
            cls(
                str(target.item.address),
                AddressLevel.ITEM,
                str(target.item.current_status),
            )
        )
        return snapshots

    def describe_move_to(self, new: "StatusSnapshot") -> str:
        return f"{self.address}: {self.status} -> {new.status}"

    @staticmethod
    def get_changed(
        before: list["StatusSnapshot"], after: list["StatusSnapshot"]
    ) -> list[tuple["StatusSnapshot", "StatusSnapshot"]]:
        """The (old, new) pairs whose status differs."""
        return [
            (old, new)
            for old, new in zip(before, after, strict=True)
            if old.status != new.status
        ]


@dataclass
class MoveContext:
    registry: Registry


class Move:
    """Moves the targets of one level to a status."""

    TEXT_FLAGS = (
        MoveFlag.RESULT,
        MoveFlag.SOURCE,
        MoveFlag.REASON,
        MoveFlag.CORRECTION,
    )

    def __init__(self, request: MoveRequest, context: MoveContext) -> None:
        self.request = request
        self.context = context

    @classmethod
    def check_request(cls, request: MoveRequest) -> None:
        """Refuse empty text before touching anything."""
        for flag in cls.TEXT_FLAGS:
            flag.require_text(getattr(request, str(flag)))

    def get_handlers(self) -> dict[MoveStatus, Callable[[Target], None]]:
        """The method that performs the move to each status of this level."""
        raise NotImplementedError

    def apply(self, target: Target) -> list[str]:
        """Change the target in memory; describe every status that changed.

        Raises Refusal when the state does not allow the move.
        """
        before = StatusSnapshot.take(target)
        was_finished = target.item.has_finished_units
        self.get_handlers()[self.request.status](target)
        after = StatusSnapshot.take(target)
        lines = [
            self.describe_change(old, new)
            for old, new in StatusSnapshot.get_changed(before, after)
        ]
        if not was_finished and self._is_ready_to_close(target.item):
            lines.append(
                f"{target.item.number}: all units finished; "
                f"close it: {target.item.done_hint}"
            )
        return lines

    def _is_ready_to_close(self, item: Item) -> bool:
        if not item.has_finished_units:
            return False
        outcomes = self.context.registry.get_dependency_outcomes(item)
        return not item.get_done_obstacles(outcomes)

    def describe_change(self, old: StatusSnapshot, new: StatusSnapshot) -> str:
        return old.describe_move_to(new)

    def require_observed_not_future(self, what: str) -> None:
        observed = self.request.get_observed_at()
        if observed is not None:
            Moment.require_not_future(observed, "--at", what)

    def require_observed_not_before(self, reference: str | None, what: str) -> None:
        observed = self.request.get_observed_at()
        if observed is None or reference is None:
            return
        Moment.require_not_before(observed, "--at", reference, what)

    def build_done_evidence(self) -> Evidence:
        """The evidence of a result; the fact is not in the future."""
        self.require_observed_not_future("the result")
        return self.request.build_evidence()

    @staticmethod
    def refuse_if_any(obstacles: list[Obstacle]) -> None:
        if obstacles:
            raise Refusal("", obstacles)
