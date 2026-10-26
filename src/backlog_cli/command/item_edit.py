"""Item actions that edit one field: rename, priority, tag, due, reminder."""

from tap import Positional

from backlog_cli.command.action import ActionSpec, ChangeParser
from backlog_cli.command.base import (
    Change,
    ChoiceArgument,
    DateHelp,
    ListText,
    MutatingCommand,
    TextCheck,
)
from backlog_cli.domain.details_file import DetailsFile
from backlog_cli.domain.item import Item
from backlog_cli.domain.vocabulary import AddressLevel, Priority
from backlog_cli.errors import Refusal
from backlog_cli.moment import Moment
from backlog_cli.store.registry import Registry
from backlog_cli.store.workspace import Workspace


class ItemEditCommand(ActionSpec, MutatingCommand):
    """An action that changes one field of an active item."""

    LEVELS = (AddressLevel.ITEM,)

    def make_change(
        self, args: ChangeParser, workspace: Workspace, registry: Registry
    ) -> Change:
        target = self.get_active_target(registry, args.address)
        return self.edit(args, workspace, registry, target.item)

    def edit(
        self,
        args: ChangeParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        raise NotImplementedError


class RenameParser(ChangeParser):
    title: Positional[str]  # The new title, one line.


class RenameCommand(ItemEditCommand):
    WORDS = ("rename",)
    GUIDE_SECTION = "item"
    SUMMARY = "Change the title of the item."
    USAGE = 'backlog N rename "TITLE"'
    EXAMPLES = 'Example: backlog 43 rename "Realtime order search"'
    Parser = RenameParser

    def edit(
        self,
        args: RenameParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        TextCheck.require("title", args.title)
        item.title = args.title.strip()
        details = DetailsFile.parse(workspace.read_details(item.id))
        return Change(
            [f"{item.number}: title -> {item.title}"],
            {item.id: details.render(item.id, item.title)},
        )


class PriorityParser(ChangeParser):
    priority: Positional[Priority]  # high, normal or low.

    def configure(self) -> None:
        super().configure()
        self.add_argument(
            "priority",
            type=ChoiceArgument.of_enum(Priority),
            metavar="PRIORITY",
            help=f"One of {'|'.join(Priority)}",
        )


class PriorityCommand(ItemEditCommand):
    WORDS = ("priority",)
    GUIDE_SECTION = "item"
    SUMMARY = "Set the priority of the item."
    USAGE = "backlog N priority high|normal|low"
    EXAMPLES = "Example: backlog 43 priority high"
    Parser = PriorityParser

    def edit(
        self,
        args: PriorityParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        item.priority = args.priority
        return Change([f"{item.number}: priority -> {item.priority}"])


class TagParser(ChangeParser):
    tags: Positional[list[str]]  # One or more tags.

    def configure(self) -> None:
        super().configure()
        self.add_argument("tags", nargs="+", metavar="TAG")


class TagAddCommand(ItemEditCommand):
    WORDS = ("tag", "add")
    GUIDE_SECTION = "item"
    SUMMARY = "Add tags (lowercase letters, digits, dashes)."
    USAGE = "backlog N tag add TAG [TAG ...]"
    EXAMPLES = "Example: backlog 43 tag add back search"
    Parser = TagParser

    def edit(
        self,
        args: TagParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        lines, added = [], False
        for tag in dict.fromkeys(ListText.split(args.tags)):
            if tag in item.tags:
                lines.append(f"{item.number}: already has tag {tag}")
                continue
            item.add_tag(tag)
            added = True
        if added:
            lines.append(f"{item.number}: tags -> {', '.join(item.tags) or 'none'}")
        return Change(lines)


class TagRemoveCommand(ItemEditCommand):
    WORDS = ("tag", "remove")
    GUIDE_SECTION = "item"
    SUMMARY = "Remove tags the item has."
    USAGE = "backlog N tag remove TAG [TAG ...]"
    EXAMPLES = "Example: backlog 43 tag remove search"
    Parser = TagParser

    def edit(
        self,
        args: TagParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        for tag in ListText.split(args.tags):
            item.remove_tag(tag)
        return Change([f"{item.number}: tags -> {', '.join(item.tags) or 'none'}"])


class DateParser(ChangeParser):
    date: Positional[str]  # YYYY-MM-DD or ISO datetime with offset (UTC Z ok).


class DateChange:
    """The output line of a changed date; an old value is printed too."""

    @staticmethod
    def describe(number: int, label: str, old: str | None, new: str) -> str:
        if old is None:
            return f"{number}: {label} -> {new}"
        return f"{number}: {label}: {old} -> {new}"


class NoArgumentParser(ChangeParser):
    """An action that needs nothing but the address."""


class DueAddCommand(ItemEditCommand):
    WORDS = ("due", "add")
    GUIDE_SECTION = "item"
    SUMMARY = "Set the deadline (replaces the old one)."
    USAGE = "backlog N due add DATE"
    EXAMPLES = f"DATE: {DateHelp.FORMAT}\nExample: backlog 43 due add 2026-11-15"
    Parser = DateParser

    def edit(
        self,
        args: DateParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        old, item.due_at = item.due_at, Moment.parse(args.date, "DATE")
        return Change([DateChange.describe(item.number, "due", old, item.due_at)])


class DueDeleteCommand(ItemEditCommand):
    WORDS = ("due", "delete")
    GUIDE_SECTION = "item"
    SUMMARY = "Remove the deadline."
    USAGE = "backlog N due delete"
    EXAMPLES = "Example: backlog 43 due delete"
    Parser = NoArgumentParser

    def edit(
        self,
        args: ChangeParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        if item.due_at is None:
            raise Refusal(f"item {item.number} has no deadline")
        item.due_at = None
        return Change([f"{item.number}: due_at cleared"])


class ReminderAddCommand(ItemEditCommand):
    WORDS = ("reminder", "add")
    GUIDE_SECTION = "item"
    SUMMARY = "Set the reminder (replaces the old one)."
    USAGE = "backlog N reminder add DATE"
    EXAMPLES = f"DATE: {DateHelp.FORMAT}\nExample: backlog 43 reminder add 2026-11-01"
    Parser = DateParser

    def edit(
        self,
        args: DateParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        old, item.remind_at = item.remind_at, Moment.parse(args.date, "DATE")
        return Change(
            [DateChange.describe(item.number, "reminder", old, item.remind_at)]
        )


class ReminderDeleteCommand(ItemEditCommand):
    WORDS = ("reminder", "delete")
    GUIDE_SECTION = "item"
    SUMMARY = "Remove the reminder."
    USAGE = "backlog N reminder delete"
    EXAMPLES = "Example: backlog 43 reminder delete"
    Parser = NoArgumentParser

    def edit(
        self,
        args: ChangeParser,
        workspace: Workspace,
        registry: Registry,
        item: Item,
    ) -> Change:
        if item.remind_at is None:
            raise Refusal(f"item {item.number} has no reminder")
        item.remind_at = None
        return Change([f"{item.number}: remind_at cleared"])
