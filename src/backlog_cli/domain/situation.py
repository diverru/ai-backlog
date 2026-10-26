"""What is going on with one active item, computed in one place.

`list`, `show`, `list --attention` and the list filters read this object; none
of them works out stuck, ready to close, overdue or blocked by itself.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from backlog_cli.domain.action import Action
from backlog_cli.domain.item import Item
from backlog_cli.domain.part import Blocker
from backlog_cli.domain.vocabulary import (
    DisplayStatus,
    ItemStatus,
    ListSort,
    Outcome,
    Priority,
)
from backlog_cli.moment import Moment


@dataclass(frozen=True)
class PendingCheck:
    """A post-release action that waits for a result after a release."""

    unit_id: str
    action: Action


@dataclass(frozen=True)
class ItemSituation:
    item: Item
    display_status: DisplayStatus
    open_blockers: tuple[Blocker, ...]
    pending_checks: tuple[PendingCheck, ...]
    unmet_dependencies: tuple[str, ...]  # ids not archived as done
    unmet_dependency_marks: tuple[str, ...]  # `7`, or `7(cancelled)` if archived
    is_overdue: bool
    is_reminder_due: bool
    is_ready_to_close: bool
    is_stuck: bool
    unblocks: tuple[int, ...]  # items for which this is the last unmet dependency
    closing_line: str | None  # shown by `list` once every unit is finished
    next_line: str | None  # shown by the card of an open item

    @classmethod
    def of(
        cls,
        item: Item,
        dependency_outcomes: Mapping[str, Outcome | None],
        now: str,
        unblocks: tuple[int, ...] = (),
    ) -> "ItemSituation":
        is_stuck = item.has_no_completed_work
        obstacles = item.get_done_obstacles(dependency_outcomes)
        is_ready = item.completion is None and not obstacles
        return cls(
            item=item,
            display_status=cls._get_display_status(item, is_stuck),
            open_blockers=tuple(item.blockers),
            pending_checks=cls._get_pending_checks(item),
            unmet_dependencies=tuple(
                dependency_id
                for dependency_id in item.depends_on
                if dependency_outcomes.get(dependency_id) != Outcome.DONE
            ),
            unmet_dependency_marks=tuple(
                cls._mark_dependency(dependency_id, dependency_outcomes)
                for dependency_id in item.depends_on
                if dependency_outcomes.get(dependency_id) != Outcome.DONE
            ),
            is_overdue=cls._is_overdue(item, now),
            is_reminder_due=item.remind_at is not None
            and item.remind_at[:10] <= now[:10],
            is_ready_to_close=is_ready,
            is_stuck=is_stuck,
            unblocks=unblocks,
            closing_line=cls._get_closing_line(item, is_ready, obstacles, unblocks),
            next_line=cls._get_card_line(item, is_ready, obstacles, unblocks),
        )

    @staticmethod
    def describe_unblocks(unblocks: tuple[int, ...]) -> str:
        return f" (unblocks {', '.join(map(str, unblocks))})" if unblocks else ""

    @property
    def can_start(self) -> bool:
        """Still todo, nothing blocks it and every dependency is done."""
        return (
            self.item.current_status == ItemStatus.TODO
            and not self.is_stuck
            and not self.open_blockers
            and not self.unmet_dependencies
        )

    def matches_status(self, status: DisplayStatus) -> bool:
        """The stored status, or `stuck`."""
        return status in (self.display_status, self.item.status)

    def matches_assignee(self, text: str) -> bool:
        return self.item.has_assignee_matching(text)

    def get_sort_key(self, order: ListSort) -> tuple:
        number = self.item.number
        if order == ListSort.PRIORITY:
            return (list(Priority).index(self.item.priority), number)
        if order == ListSort.DUE:
            due = self.item.due_at
            moment = Moment.to_datetime(due).timestamp() if due else 0
            return (due is None, moment, number)
        return (number,)

    @staticmethod
    def _get_display_status(item: Item, is_stuck: bool) -> DisplayStatus:
        if is_stuck:
            return DisplayStatus.STUCK
        return DisplayStatus(str(item.status))

    @staticmethod
    def _mark_dependency(
        dependency_id: str, outcomes: Mapping[str, Outcome | None]
    ) -> str:
        number = Item.get_number(dependency_id)
        outcome = outcomes.get(dependency_id)
        return str(number) if outcome is None else f"{number}({outcome})"

    @staticmethod
    def _get_pending_checks(item: Item) -> tuple[PendingCheck, ...]:
        return tuple(
            PendingCheck(unit.id, action)
            for unit in item.work
            if unit.has_release
            for action in unit.pending_actions
        )

    @staticmethod
    def _is_overdue(item: Item, now: str) -> bool:
        if item.due_at is None:
            return False
        return Moment.is_before(item.due_at, now, by_day=Moment.is_date(item.due_at))

    @classmethod
    def _get_card_line(
        cls, item: Item, is_ready: bool, obstacles: list, unblocks: tuple[int, ...]
    ) -> str | None:
        """What the card says: the next command, what an unstarted item waits for,
        or why closing is blocked. Work that has not started is never told to
        record a merge.
        """
        if item.completion is not None:
            return None
        if is_ready:
            return f"next: {cls._get_closing_line(item, True, obstacles, unblocks)}"
        is_unstarted = item.current_status == ItemStatus.TODO
        if item.work and is_unstarted and not item.has_finished_units:
            return cls._get_waiting_line(item, obstacles)
        line = cls._get_closing_line(item, False, obstacles, unblocks, True)
        return f"closing: {line}" if line else None

    @staticmethod
    def _get_waiting_line(item: Item, obstacles: list) -> str | None:
        waits = [o.reason for o in obstacles if o.group == "Unfinished dependencies"]
        if waits:
            return "waiting: " + "; ".join(waits)
        open_unit = next((unit for unit in item.work if not unit.is_terminal), None)
        if open_unit is None:
            return None
        return (
            "not started: assign an agent to start a unit: "
            f"backlog {item.number}/{open_unit.id} assign --agent NAME"
        )

    @staticmethod
    def _get_closing_line(
        item: Item,
        is_ready: bool,
        obstacles: list,
        unblocks: tuple[int, ...],
        is_card: bool = False,
    ) -> str | None:
        """Either `done` would pass now, or the first thing that stops it."""
        if is_ready:
            frees = ItemSituation.describe_unblocks(unblocks)
            return f"ready to close: {item.done_hint}{frees}"
        if not item.has_finished_units and not is_card:
            return None
        if item.completion is not None:
            return None
        if not obstacles:
            return None
        first = obstacles[0]
        line = f"blocked: {first.reason}"
        if first.hint is not None:
            line += f". Next: {first.hint.command.replace(chr(10), ' or ')}"
        dead = [
            other
            for other in obstacles[1:]
            if other.group == "Unfinished dependencies"
            and "archived as" in other.reason
        ]
        if dead:
            line += "; also " + "; ".join(other.reason for other in dead)
        return line
