"""An item: one independent result to deliver.

Once an item has units, its status comes from them.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace

from backlog_cli.domain.action import Action
from backlog_cli.domain.address import Address
from backlog_cli.domain.completion import ItemCompletion
from backlog_cli.domain.part import (
    Blocker,
    Evidence,
    Finding,
    PrRef,
    ResolvedBlocker,
)
from backlog_cli.domain.record import Record
from backlog_cli.domain.title import TitleText
from backlog_cli.domain.unit import Unit
from backlog_cli.domain.vocabulary import ItemStatus, Outcome, Priority, UnitStatus
from backlog_cli.errors import Hint, Obstacle, Refusal, UsageError
from backlog_cli.moment import Moment


@dataclass(frozen=True)
class LeftBehindAction:
    address: Address
    description: str


@dataclass
class Item(Record):
    TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")
    id: str
    title: str
    priority: Priority
    status: ItemStatus
    tags: list[str]
    due_at: str | None
    remind_at: str | None
    depends_on: list[str]
    prerequisite_prs: list[PrRef]
    blockers: list[Blocker]
    resolved_blockers: list[ResolvedBlocker]
    next_blocker_id: int  # never goes down, so a removed blocker id is not reissued
    work: list[Unit]
    created_at: str
    updated_at: str
    completion: ItemCompletion | None

    @classmethod
    def new(
        cls,
        item_id: str,
        title: str,
        priority: Priority,
        due_at: str | None,
        remind_at: str | None,
        depends_on: list[str],
    ) -> "Item":
        now = Moment.now()
        return cls(
            id=item_id,
            title=title,
            priority=priority,
            status=ItemStatus.TODO,
            tags=[],
            due_at=due_at,
            remind_at=remind_at,
            depends_on=depends_on,
            prerequisite_prs=[],
            blockers=[],
            resolved_blockers=[],
            next_blocker_id=1,
            work=[],
            created_at=now,
            updated_at=now,
            completion=None,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Item":
        completion = data["completion"]
        blockers = [Blocker.from_dict(entry) for entry in data["blockers"]]
        resolved = [
            ResolvedBlocker.from_dict(entry) for entry in data["resolved_blockers"]
        ]
        return cls(
            id=data["id"],
            title=data["title"],
            priority=Priority(data["priority"]),
            status=ItemStatus(data["status"]),
            tags=data["tags"],
            due_at=data["due_at"],
            remind_at=data["remind_at"],
            depends_on=data["depends_on"],
            prerequisite_prs=[
                PrRef.from_dict(entry) for entry in data["prerequisite_prs"]
            ],
            blockers=blockers,
            resolved_blockers=resolved,
            next_blocker_id=data["next_blocker_id"],
            work=[Unit.from_dict(entry) for entry in data["work"]],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            completion=ItemCompletion.from_dict(completion) if completion else None,
        )

    @staticmethod
    def get_number(item_id: str) -> int:
        return int(item_id.split("_")[0])

    @property
    def number(self) -> int:
        return self.get_number(self.id)

    @property
    def slug(self) -> str:
        """The part of the id after `NNNN_`."""
        return self.id.split("_", 1)[1]

    @property
    def short_title(self) -> str:
        """One line wherever titles are listed: a long title is cut."""
        return TitleText.shorten(self.title)

    @property
    def address(self) -> Address:
        return Address(self.number)

    @property
    def derived_status(self) -> ItemStatus:
        """todo until a unit has started; an item without units is always todo."""
        if any(unit.has_started for unit in self.work):
            return ItemStatus.WIP
        return ItemStatus.TODO

    @property
    def has_finished_units(self) -> bool:
        """Units exist, every one is finished, and the item is still open."""
        return (
            bool(self.work)
            and self.completion is None
            and all(unit.is_terminal for unit in self.work)
        )

    @property
    def done_hint(self) -> str:
        return f'backlog {self.number} done --result "..." --source "..."'

    @property
    def current_status(self) -> ItemStatus:
        """The status the item has now, before the write path stores it."""
        return self.status if self.completion is not None else self.derived_status

    def settle(self) -> None:
        """Follow the units after every change and move the update time.

        A completed item keeps the status it was completed with.
        """
        if self.completion is None:
            self.status = self.derived_status
        self.updated_at = Moment.now()

    def build_fix_hint(self, finding: Finding) -> Hint:
        """Finish the fix unit that already exists, else add one."""
        for unit in self.work:
            if unit.id in finding.known_units or unit.is_terminal:
                continue
            address = Address(self.number, unit.id)
            if unit.status == UnitStatus.MERGED:
                command = f'backlog {address} released --at DATE --source "..."'
            else:
                command = f'backlog {address} merged --pr OWNER/NAME#N --source "..."'
            return Hint("A fix unit exists: finish it and release it", command)
        return Hint(
            "Fix it, then release the fix",
            f"backlog {self.number} unit add NAME --kind pr",
        )

    def has_fix_after(self, finding: Finding) -> bool:
        """A unit that the item did not have at the finding has been released.

        The release date of the fix does not matter, and correcting any release
        never counts: only a new unit that went out unlocks a failed check.
        """
        return any(
            unit.has_release and unit.id not in finding.known_units
            for unit in self.work
        )

    def get_unit(self, unit_id: str) -> Unit:
        for unit in self.work:
            if unit.id == unit_id:
                return unit
        raise UsageError(f"item {self.number} has no unit {unit_id!r}")

    def add_unit(self, unit: Unit) -> None:
        if any(known.id == unit.id for known in self.work):
            raise Refusal(f"item {self.number} already has a unit {unit.id!r}")
        self.work.append(unit)

    def has_assignee_matching(self, text: str) -> bool:
        """An assignee of a unit has an agent, task or role like it."""
        needle = text.lower()
        assignees = [assignee for unit in self.work for assignee in unit.assignees]
        return any(
            needle in field.lower()
            for assignee in assignees
            for field in (assignee.agent, assignee.task_text, assignee.role or "")
        )

    def add_blocker(self, description: str, waiting_on: str | None) -> Blocker:
        same = next((b for b in self.blockers if b.description == description), None)
        if same is not None:
            raise Refusal(
                f"item {self.number} already has the open blocker {same.id} "
                "with this text"
            )
        blocker = Blocker(f"b{self.next_blocker_id}", description, waiting_on)
        self.next_blocker_id += 1
        self.blockers.append(blocker)
        return blocker

    def resolve_blocker(self, blocker_id: str, reason: str) -> str:
        """Close a blocker by id and keep it; a bare number means `b<number>`."""
        if blocker_id.isascii() and blocker_id.isdecimal():
            blocker_id = f"b{blocker_id}"
        found = next(
            (blocker for blocker in self.blockers if blocker.id == blocker_id), None
        )
        if found is None:
            open_ids = ", ".join(blocker.id for blocker in self.blockers) or "none"
            raise UsageError(
                f"item {self.number} has no open blocker {blocker_id!r}; "
                f"open blockers: {open_ids}"
            )
        self.blockers.remove(found)
        self.resolved_blockers.append(
            ResolvedBlocker(
                found.id, found.description, found.waiting_on, Moment.now(), reason
            )
        )
        return blocker_id

    def add_tag(self, tag: str) -> None:
        if not self.TAG_PATTERN.match(tag):
            raise UsageError(
                f"bad tag {tag!r}; use lowercase letters, digits and dashes"
            )
        if tag not in self.tags:
            self.tags.append(tag)

    def remove_tag(self, tag: str) -> None:
        if tag not in self.tags:
            raise UsageError(f"item {self.number} has no tag {tag!r}")
        self.tags.remove(tag)

    def get_left_behind_actions(self) -> list[LeftBehindAction]:
        """Pending actions that stay unfinished when the item is archived."""
        left_behind = []
        for unit in self.work:
            for action in unit.pending_actions:
                address = Address(self.number, unit.id, action.id)
                left_behind.append(LeftBehindAction(address, action.description))
        return left_behind

    def get_done_obstacles(
        self, dependency_outcomes: Mapping[str, Outcome | None]
    ) -> list[Obstacle]:
        """Everything that stops `done`."""
        obstacles = []
        for unit in self.work:
            obstacles += self._get_unit_obstacles(unit)
        obstacles += self._get_no_completed_work_obstacles()
        obstacles += self._get_no_units_obstacles()
        obstacles += self._get_blocker_obstacles()
        for dependency_id in self.depends_on:
            outcome = dependency_outcomes.get(dependency_id)
            if outcome != Outcome.DONE:
                obstacles.append(self._get_dependency_obstacle(dependency_id, outcome))
        return obstacles

    def complete(self, evidence: Evidence) -> None:
        self.completion = ItemCompletion.done(evidence)
        self.status = ItemStatus.DONE
        self.updated_at = Moment.now()

    def abandon(self, outcome: Outcome, reason: str, follow_up: str | None) -> None:
        self.completion = ItemCompletion.abandoned(outcome, reason, follow_up)
        self.status = ItemStatus(str(outcome))
        self.updated_at = Moment.now()

    @property
    def has_no_completed_work(self) -> bool:
        """Units exist and every one of them was cancelled or superseded."""
        all_finished = all(unit.is_terminal for unit in self.work)
        any_done = any(unit.status == UnitStatus.DONE for unit in self.work)
        return bool(self.work) and all_finished and not any_done

    def _get_no_units_obstacles(self) -> list[Obstacle]:
        """An item is work with at least one unit; `done` closes it through them."""
        if self.work:
            return []
        hint = Hint(
            "Add a unit of work and finish it, or drop the item",
            f"backlog {self.number} unit add NAME --kind pr\n"
            f'backlog {self.number} cancel --reason "..."',
        )
        return [
            Obstacle(
                str(self.address),
                self.title,
                "the item has no units; it is closed through its units",
                "No units",
                hint,
            )
        ]

    def _get_blocker_obstacles(self) -> list[Obstacle]:
        return [
            Obstacle(
                str(self.address),
                "",
                f"blocker {blocker.id}: {blocker.description}",
                "Open blockers",
                Hint(
                    "Remove the blocker when it no longer blocks",
                    f'backlog {self.number} block remove {blocker.id} --reason "..."',
                ),
            )
            for blocker in self.blockers
        ]

    def describe_next_item_step(self) -> str:
        """What to do instead of changing an archived item."""
        add = 'backlog add <slug> --title "..."'
        if self.completion is not None and self.completion.outcome == Outcome.DONE:
            return f"create a linked item ({add} --depends-on {self.number})"
        return f"create a new item ({add})"

    def _get_no_completed_work_obstacles(self) -> list[Obstacle]:
        if not self.has_no_completed_work:
            return []
        hint = Hint(
            "Nothing was completed; close the item instead",
            f'backlog {self.number} cancel --reason "..."',
        )
        return [
            Obstacle(
                str(self.address),
                self.title,
                "every unit is cancelled or superseded",
                "No completed work",
                hint,
            )
        ]

    def _get_dependency_obstacle(
        self, dependency_id: str, outcome: Outcome | None
    ) -> Obstacle:
        if outcome is None:
            state = "not archived yet"
            hint = Hint("Inspect the dependency", f"backlog {self.number} dependency")
        else:
            state = f"archived as {outcome}"
            hint = Hint(
                "It will never be done: drop the dependency, or close this item",
                f"backlog {self.number} dependency remove "
                f"{Item.get_number(dependency_id)}\n"
                f'backlog {self.number} cancel --reason "..."',
            )
        return Obstacle(
            str(self.address),
            "",
            f"dependency {dependency_id} is {state}",
            "Unfinished dependencies",
            hint,
        )

    def _get_unit_obstacles(self, unit: Unit) -> list[Obstacle]:
        if unit.is_terminal:
            return []
        return self.refine_obstacles(unit.get_done_obstacles(self.number))

    def refine_obstacles(self, obstacles: list[Obstacle]) -> list[Obstacle]:
        """A failed check that no release has fixed yet is not settled by
        `post_release done`: the hint says to fix and release first.
        """
        refined = []
        for obstacle in obstacles:
            action = self._find_unfixed_failed_action(obstacle.address)
            if action is None:
                refined.append(obstacle)
                continue
            hint = self.build_fix_hint(action.findings[-1])
            reason = (
                f'the check failed ("{action.findings[-1].text}"); release a unit '
                "added after the finding to unlock it"
            )
            refined.append(replace(obstacle, reason=reason, hint=hint, extra_hint=None))
        return refined

    def _find_unfixed_failed_action(self, address: str) -> Action | None:
        parts = address.split("/")
        if len(parts) != 3:
            return None
        unit = next((unit for unit in self.work if unit.id == parts[1]), None)
        pr_unit = unit.get_pr_unit() if unit else None
        if pr_unit is None:
            return None
        action = next(
            (a for a in pr_unit.post_release_actions if a.id == parts[2]), None
        )
        if action is None or not action.is_failed:
            return None
        if self.has_fix_after(action.findings[-1]):
            return None
        return action
