"""`add`: a new item. Units and post-release actions are added under the item."""

from tap import Positional

from backlog_cli.command.base import (
    Change,
    MutatingCommand,
    DateHelp,
    ListText,
    MutatingParser,
    TextCheck,
)
from backlog_cli.domain.address import Address
from backlog_cli.domain.details_file import DetailsFile
from backlog_cli.domain.item import Item
from backlog_cli.domain.vocabulary import AddressLevel, Priority
from backlog_cli.errors import UsageError
from backlog_cli.moment import Moment
from backlog_cli.store.registry import Registry
from backlog_cli.store.workspace import Workspace


class AddParser(MutatingParser):
    slug: Positional[str]  # Short id of the new item: lowercase words with underscores.
    title: str  # What the item is, one line.
    priority: Priority = Priority.NORMAL  # Item priority.
    tags: str | None = None  # Tags: back,search or "back search".
    due: str | None = None  # Deadline.
    reminder: str | None = None  # Reminder.
    depends_on: str | None = None  # Items it depends on: 41,42 or "41 42".

    def configure(self) -> None:
        super().configure()
        self.add_enum_argument("--priority", Priority, "Priority, default normal")
        self.add_argument("--due", help=f"Deadline: {DateHelp.FORMAT}")
        self.add_argument("--reminder", help=f"Reminder: {DateHelp.FORMAT}")


class AddCommand(MutatingCommand):
    NAME = "add"
    SUMMARY = "Add an item; prints its number."
    USAGE = (
        'backlog add SLUG --title "..." [--priority high|normal|low] [--tags a,b]\n'
        "            [--due DATE] [--reminder DATE] [--depends-on 41,42]"
    )
    EXAMPLES = (
        'Example: backlog add fast_order --title "Realtime order search" '
        "--tags back,search"
    )
    Parser = AddParser

    def make_change(
        self, args: AddParser, workspace: Workspace, registry: Registry
    ) -> Change:
        Address.require_new_id(args.slug, "slug")
        registry.require_free_slug(args.slug)
        TextCheck.require("--title", args.title)
        title = args.title.strip()
        dependencies = self._read_dependencies(args.depends_on, registry)
        item_id = registry.allocate_id(args.slug)
        item = Item.new(
            item_id,
            title,
            args.priority or Priority.NORMAL,
            self._parse_when(args.due, "--due"),
            self._parse_when(args.reminder, "--reminder"),
            [dependency.id for dependency in dependencies],
        )
        for tag in ListText.split([args.tags or ""]):
            item.add_tag(tag)
        registry.active.append(item)
        details_text = DetailsFile.create_blank().render(item_id, title)
        return Change(
            [f"Created item {item.number} ({item_id})"], {item_id: details_text}
        )

    @staticmethod
    def _parse_when(text: str | None, flag: str) -> str | None:
        return Moment.parse(text, flag) if text else None

    @staticmethod
    def _read_dependencies(text: str | None, registry: Registry) -> list[Item]:
        dependencies: list[Item] = []
        for reference in ListText.split([text or ""]):
            address = Address.parse(reference)
            if address.level != AddressLevel.ITEM:
                raise UsageError(
                    f"--depends-on takes item numbers or ids, not {reference!r}"
                )
            dependency = registry.accept_dependency(registry.find_item(address.item))
            if dependency not in dependencies:
                dependencies.append(dependency)
        return dependencies
