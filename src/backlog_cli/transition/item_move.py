"""Item transitions.

The status of an item is derived from its units. An item moves by `done`,
`cancel` or `supersede`; each ends it and archives it in the same command.
"""

from collections.abc import Callable

from backlog_cli.domain.address import Address
from backlog_cli.domain.item import Item
from backlog_cli.domain.unit import Unit
from backlog_cli.domain.vocabulary import MoveStatus, Outcome
from backlog_cli.errors import Refusal
from backlog_cli.store.registry import Target
from backlog_cli.transition.base import AssigneeNote, Move
from backlog_cli.transition.unit_move import UnitMove


class ItemMove(Move):
    def get_handlers(self) -> dict[MoveStatus, Callable[[Target], None]]:
        return {
            MoveStatus.DONE: self.move_to_done,
            MoveStatus.CANCELLED: self.move_to_cancelled,
            MoveStatus.SUPERSEDED: self.move_to_superseded,
        }

    def apply(self, target: Target) -> list[str]:
        self.notes: list[str] = []
        lines = super().apply(target)
        item = target.item
        if item.completion is not None:
            lines.append(
                f"{target.address}: archived as {item.id} ({item.completion.outcome})"
            )
        return lines + self.notes

    def move_to_done(self, target: Target) -> None:
        """Close the item as done and archive it in the same command.

        A finished item can then never be edited.
        """
        item = target.item
        outcomes = self.context.registry.get_dependency_outcomes(item)
        self.refuse_if_any(item.get_done_obstacles(outcomes))
        self._require_not_before_units(item)
        item.complete(self.build_done_evidence())
        self.context.registry.archive(item)

    def _require_not_before_units(self, item: Item) -> None:
        """The item is closed after the releases of its units."""
        for unit in item.work:
            pr_unit = unit.get_pr_unit()
            if pr_unit and pr_unit.release:
                self.require_observed_not_before(
                    pr_unit.release.released_at, f"the release of {unit.id}"
                )

    def move_to_cancelled(self, target: Target) -> None:
        self._abandon(target, Outcome.CANCELLED, None)

    def move_to_superseded(self, target: Target) -> None:
        self._abandon(target, Outcome.SUPERSEDED, self._find_follow_up(target))

    def _abandon(self, target: Target, outcome: Outcome, follow_up: str | None) -> None:
        """End an item that will not be completed and archive it."""
        item, registry = target.item, self.context.registry
        open_units = [unit for unit in item.work if not unit.is_terminal]
        merged = [
            UnitMove.get_merged_obstacle(item.number, unit) for unit in open_units
        ]
        self.refuse_if_any(
            [obstacle for obstacle in merged if obstacle]
            + item.refine_obstacles(
                [
                    obstacle
                    for unit in open_units
                    for obstacle in unit.get_pending_obstacles(item.number)
                ]
            )
        )
        item.abandon(outcome, self.request.reason, follow_up)
        left_behind = item.get_left_behind_actions()
        dependents = sorted(
            registry.get_active_dependents(item), key=lambda other: other.number
        )
        registry.archive(item)
        self._note_closed_units(item, open_units)
        if left_behind:
            self.notes.append("Pending actions left behind:")
            self.notes += [
                f"  {action.address} — {action.description}" for action in left_behind
            ]
        if dependents:
            self.notes.append("Active items that depend on it:")
            self.notes += [f"  {other.number} — {other.title}" for other in dependents]

    def _note_closed_units(self, item: Item, open_units: list[Unit]) -> None:
        """Say which units were closed with the item and who still works on them."""
        if open_units:
            self.notes.append("Units closed with the item:")
            self.notes += [
                f"  {item.number}/{unit.id} — {unit.label} (was {unit.status})"
                for unit in open_units
            ]
        self.notes += [
            line
            for unit in open_units
            for line in AssigneeNote.build_lines(
                f"{item.number}/{unit.id}", unit.assignees
            )
        ]

    def _find_follow_up(self, target: Target) -> str:
        """`--by` is the item that continues the work."""
        registry = self.context.registry
        location = registry.find_item(Address.parse(self.request.by).item)
        follow_up = location.item
        if follow_up.id == target.item.id:
            raise Refusal("an item cannot supersede itself")
        self._require_not_ready_to_close(target.item)
        if location.is_archived and follow_up.completion.outcome != Outcome.DONE:
            raise Refusal(
                f"item {follow_up.number} is archived as "
                f"{follow_up.completion.outcome} and cannot carry the work; "
                "name an active item or one archived as done"
            )
        chain = registry.find_dependency_chain(follow_up, target.item)
        if chain:
            numbers = " -> ".join(str(Item.get_number(item_id)) for item_id in chain)
            raise Refusal(
                f"item {follow_up.number} depends on item {target.item.number} "
                f"({numbers}), so it could never be done; name an item that does "
                "not depend on this one"
            )
        self._require_no_self_wait(follow_up, target.item)
        return follow_up.id

    def _require_not_ready_to_close(self, item: Item) -> None:
        """All the work is finished: the item is closed, not handed over."""
        outcomes = self.context.registry.get_dependency_outcomes(item)
        if item.work and not item.get_done_obstacles(outcomes):
            raise Refusal(
                f"item {item.number} is ready to close: all its work is finished, "
                "so it cannot be superseded.\n"
                f"Next: {item.done_hint}"
            )

    def _require_no_self_wait(self, follow_up: Item, item: Item) -> None:
        """M must not wait for an item whose work goes to N and then to M itself."""
        registry = self.context.registry
        for dependency_id in follow_up.depends_on:
            current = dependency_id
            while current is not None and current != item.id:
                found = registry.find_item(Item.get_number(current)).item
                outcome = found.completion.outcome if found.completion else None
                current = (
                    found.completion.follow_up
                    if outcome == Outcome.SUPERSEDED
                    else None
                )
            if current == item.id and dependency_id != item.id:
                raise Refusal(
                    f"item {follow_up.number} depends on item "
                    f"{Item.get_number(dependency_id)}, whose work goes to item "
                    f"{item.number} and then to {follow_up.number}: it would wait "
                    "for itself.\n"
                    f"Next: backlog {follow_up.number} dependency remove "
                    f"{Item.get_number(dependency_id)}"
                )
