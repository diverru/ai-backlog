"""Item actions about what the item waits for: block, dependency, unit."""

from tap import Positional

from backlog_cli.command.action import ActionSpec, ChangeParser, ReadParser
from backlog_cli.command.base import (
    Change,
    ChoiceArgument,
    ListText,
    TextCheck,
    WorkspaceCommand,
)
from backlog_cli.command.item_edit import ItemEditCommand
from backlog_cli.command.unit_line import UnitLine
from backlog_cli.domain.address import Address
from backlog_cli.domain.item import Item
from backlog_cli.domain.part import Blocker, PrRef
from backlog_cli.domain.unit import PrUnit, ResearchUnit, Unit
from backlog_cli.domain.vocabulary import AddressLevel, ItemSource, UnitKind
from backlog_cli.errors import UsageError
from backlog_cli.store.registry import ItemLocation, Registry
from backlog_cli.store.workspace import Workspace


class BlockAddParser(ChangeParser):
    condition: Positional[str]  # What the item waits for, one line.
    waiting_on: str | None = None  # Who it waits on.


class BlockAddCommand(ItemEditCommand):
    WORDS = ("block", "add")
    GUIDE_SECTION = "item"
    SUMMARY = "Record an outside condition the item waits for; prints its id."
    USAGE = 'backlog N block add "TEXT" [--waiting-on WHO]'
    EXAMPLES = 'Example: backlog 43 block add "Vendor key" --waiting-on admin'
    Parser = BlockAddParser

    def edit(
        self,
        args: BlockAddParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        TextCheck.require("TEXT", args.condition)
        TextCheck.require("--waiting-on", args.waiting_on)
        blocker = item.add_blocker(args.condition.strip(), args.waiting_on)
        return Change([f"{item.number}: blocker {blocker.id} added"])


class BlockRemoveParser(ChangeParser):
    blocker: Positional[str]  # The blocker id, b1 or 1.
    reason: str  # Why it no longer blocks.


class BlockRemoveCommand(ItemEditCommand):
    WORDS = ("block", "remove")
    GUIDE_SECTION = "item"
    SUMMARY = "Close a blocker and keep it in the record, with the reason."
    USAGE = 'backlog N block remove bK --reason "..."'
    EXAMPLES = 'Example: backlog 43 block remove b1 --reason "Key received"'
    Parser = BlockRemoveParser

    def edit(
        self,
        args: BlockRemoveParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        TextCheck.require("--reason", args.reason)
        closed = item.resolve_blocker(args.blocker, args.reason)
        return Change([f"{item.number}: blocker {closed} removed"])


class DependencyParser(ReadParser):
    dependents: bool = False  # Show the items that depend on this one instead.


class DependencyCommand(ActionSpec, WorkspaceCommand):
    LEVELS = (AddressLevel.ITEM,)
    WORDS = ("dependency",)
    GUIDE_SECTION = "dependency"
    SUMMARY = "Show dependencies, blockers, prerequisite PRs (--dependents: reverse)."
    USAGE = "backlog N dependency [--dependents]"
    EXAMPLES = "Example: backlog 43 dependency --dependents"
    Parser = DependencyParser

    def run(self, args: DependencyParser) -> int:
        registry = self.open_workspace(args).load_registry()
        item = registry.resolve_target(Address.parse(args.address)).item
        if args.dependents:
            self.print_lines(f"Items that depend on {item.number} ({item.title}):")
            related = [
                ItemLocation(other, other in registry.archived)
                for other in registry.get_dependents(item)
            ]
        else:
            self.print_lines(f"Dependencies of {item.number} ({item.title}):")
            related = [
                registry.find_item(dependency_id) for dependency_id in item.depends_on
            ]
        self.print_lines(*(self._format(location) for location in related))
        if not related:
            self.print_lines("  none")
        if args.dependents:
            return 0
        self.print_lines("Blockers (external conditions):")
        self.print_lines(*(self._format_blocker(blocker) for blocker in item.blockers))
        if not item.blockers:
            self.print_lines("  none")
        self.print_lines("Prerequisite PRs (informational):")
        self.print_lines(*(f"  {pr}" for pr in item.prerequisite_prs))
        if not item.prerequisite_prs:
            self.print_lines("  none")
        return 0

    @staticmethod
    def _format(location: ItemLocation) -> str:
        other = location.item
        label = f"  {other.number}  {other.title}"
        if location.is_archived:
            return f"{label}  {other.completion.outcome}  {ItemSource.ARCHIVE}"
        return f"{label}  {other.current_status}  {ItemSource.ACTIVE}"

    @staticmethod
    def _format_blocker(blocker: Blocker) -> str:
        waiting = f" (waiting on {blocker.waiting_on})" if blocker.waiting_on else ""
        return f"  {blocker.id}  {blocker.description}{waiting}"


class DependencyChangeParser(ChangeParser):
    references: Positional[list[str]]  # Item numbers, or PRs as OWNER/NAME#N.

    def configure(self) -> None:
        super().configure()
        self.add_argument("references", nargs="+", metavar="X")


class DependencyAddCommand(ItemEditCommand):
    WORDS = ("dependency", "add")
    GUIDE_SECTION = "dependency"
    SUMMARY = "Depend on items (by number) or on PRs (OWNER/NAME#N)."
    USAGE = "backlog N dependency add X [X ...]"
    EXAMPLES = "Example: backlog 43 dependency add 41 acme/api#123"
    Parser = DependencyChangeParser
    PR_MARK = "#"

    def edit(
        self,
        args: DependencyChangeParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        lines = []
        seen: set[str] = set()
        for reference in ListText.split(args.references):
            if self.PR_MARK in reference:
                pr = PrRef.from_text(reference, "PR")
                if str(pr) in seen:
                    continue
                seen.add(str(pr))
                if pr not in item.prerequisite_prs:
                    item.prerequisite_prs.append(pr)
                lines.append(
                    f"{item.number}: added prerequisite PR {pr}; it is "
                    "informational and does not block start or closure"
                )
                continue
            location = registry.find_item(Address.parse(reference).item)
            dependency = registry.require_valid_dependency(item, location)
            if dependency.id in seen:
                continue
            seen.add(dependency.id)
            if dependency.id in item.depends_on:
                lines.append(f"{item.number}: already depends on {dependency.number}")
                continue
            item.depends_on.append(dependency.id)
            lines.append(self._describe_wait(item, dependency, location.is_archived))
        return Change(lines)

    @staticmethod
    def _describe_wait(item: Item, dependency: Item, is_archived: bool) -> str:
        if is_archived:
            return (
                f"{item.number}: depends on {dependency.number}, which is done: "
                "nothing to wait for"
            )
        return (
            f"{item.number}: now waits for {dependency.number} "
            f"({dependency.current_status})"
        )


class DependencyRemoveCommand(ItemEditCommand):
    WORDS = ("dependency", "remove")
    GUIDE_SECTION = "dependency"
    SUMMARY = "Drop dependencies: items by number, PRs as OWNER/NAME#N."
    USAGE = "backlog N dependency remove X [X ...]"
    EXAMPLES = "Example: backlog 43 dependency remove 41"
    Parser = DependencyChangeParser

    def edit(
        self,
        args: DependencyChangeParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        lines = []
        for reference in ListText.split(args.references):
            if DependencyAddCommand.PR_MARK in reference:
                pr = PrRef.from_text(reference, "PR")
                if pr not in item.prerequisite_prs:
                    raise UsageError(f"item {item.number} does not depend on PR {pr}")
                item.prerequisite_prs.remove(pr)
                lines.append(f"{item.number}: no longer depends on PR {pr}")
                continue
            dependency = registry.find_item(Address.parse(reference).item)
            if dependency.item.id not in item.depends_on:
                raise UsageError(
                    f"item {item.number} does not depend on {dependency.item.id}"
                )
            item.depends_on.remove(dependency.item.id)
            lines.append(f"{item.number}: no longer depends on {dependency.item.id}")
        return Change(lines)


class UnitListCommand(ActionSpec, WorkspaceCommand):
    LEVELS = (AddressLevel.ITEM,)
    WORDS = ("unit",)
    GUIDE_SECTION = "unit"
    SUMMARY = "List the units of the item, one line each."
    USAGE = "backlog N unit"
    EXAMPLES = "Example: backlog 43 unit"
    Parser = ReadParser

    def run(self, args: ReadParser) -> int:
        registry = self.open_workspace(args).load_registry()
        item = registry.resolve_target(Address.parse(args.address)).item
        situation = registry.get_situation(item)
        if not item.work:
            self.print_lines(f"Item {item.number} has no units.")
            return 0
        for unit in item.work:
            self.print_lines(*UnitLine.format(unit, situation))
        return 0


class UnitAddParser(ChangeParser):
    name: Positional[str]  # The unit id: a short word you choose, e.g. engine.
    kind: UnitKind = UnitKind.PR  # pr (default) or research.

    def configure(self) -> None:
        super().configure()
        self.add_argument(
            "--kind",
            type=ChoiceArgument.of_enum(UnitKind),
            default=UnitKind.PR,
            metavar="KIND",
            help=f"Kind of unit, default pr ({'|'.join(UnitKind)})",
        )


class UnitAddCommand(ItemEditCommand):
    WORDS = ("unit", "add")
    GUIDE_SECTION = "unit"
    SUMMARY = "Add a unit of work: a PR to merge and release, or research."
    USAGE = "backlog N unit add NAME [--kind pr|research]"
    EXAMPLES = "Example: backlog 43 unit add engine --kind pr"
    Parser = UnitAddParser

    def edit(
        self,
        args: UnitAddParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        Address.require_new_id(args.name, "unit id")
        unit: Unit = (
            ResearchUnit.new(args.name)
            if args.kind == UnitKind.RESEARCH
            else PrUnit.new(args.name)
        )
        item.add_unit(unit)
        return Change(
            [
                f"Added unit {item.number}/{unit.id} ({unit.kind}, {unit.status}); "
                f"item is now {item.current_status}"
            ]
        )
