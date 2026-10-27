"""`list`: one line per item, short indented lines per unit."""

from backlog_cli.command.attention import AttentionReport
from backlog_cli.command.base import CommandParser, WorkspaceCommand
from backlog_cli.command.unit_line import UnitLine
from backlog_cli.domain.item import Item
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.vocabulary import (
    DisplayStatus,
    ListSort,
    Priority,
)
from backlog_cli.errors import UsageError
from backlog_cli.moment import Moment


class ListParser(CommandParser):
    status: DisplayStatus | None = None  # Only items in this status.
    priority: Priority | None = None  # Only items with this priority.
    tag: str | None = None  # Only items with this tag.
    remind_before: str | None = None  # Only reminders before this date.
    assignee: str | None = None  # Only items with an agent, task or role like this.
    can_start: bool = False  # Only items with no open blocker and dependencies done.
    attention: bool = False  # Only what needs a decision now, grouped.
    archive: bool = False  # List the archive (with outcomes) instead.

    def configure(self) -> None:
        super().configure()
        self.add_enum_argument(
            "--status",
            DisplayStatus,
            "Only items in this status",
            [DisplayStatus.TODO, DisplayStatus.WIP, DisplayStatus.STUCK],
        )
        self.add_enum_argument("--priority", Priority, "Only items with this priority")
        self.add_enum_argument("--sort", ListSort, "Order, default number")


class ListCommand(WorkspaceCommand):
    NAME = "list"
    SUMMARY = "List items with their units."
    USAGE = (
        "backlog list [--attention] [--status S] [--priority P] [--tag T] "
        "[--assignee TEXT] [--can-start]\n"
        "             [--sort number|priority|due] [--remind-before DATE] [--archive]"
    )
    EXAMPLES = "Example: backlog list --status wip --sort priority"
    REASON_WIDTH = 60
    Parser = ListParser

    def run(self, args: ListParser) -> int:
        if args.archive and (args.attention or args.can_start):
            raise UsageError(
                "--attention and --can-start are about active items; drop --archive"
            )
        if args.assignee is not None and not args.assignee.strip():
            raise UsageError("--assignee must not be empty")
        workspace = self.open_workspace(args)
        registry = workspace.load_registry()
        items = registry.archived if args.archive else registry.active
        situations = self._filter(
            args, [registry.get_situation(item) for item in items]
        )
        if not self.found_by_repo:
            self.print_lines(f"workspace: {workspace.name}")
        if args.attention:
            self._print_attention(situations, workspace.find_empty_brief_ids(registry))
            return 0
        if not situations:
            self.print_lines("No items.")
            return 0
        for situation in situations:
            if args.archive:
                self.print_lines(self._format_archived(situation.item))
            else:
                self.print_lines(*self._format_active(situation))
        return 0

    def _print_attention(
        self, situations: list[ItemSituation], empty_brief_ids: set[str]
    ) -> None:
        groups = AttentionReport.collect(situations, empty_brief_ids)
        if not groups:
            self.print_lines("Nothing needs attention.")
            return
        for group, lines in groups.items():
            self.print_lines(f"{group}:", *[f"  {line}" for line in lines])

    @staticmethod
    def _filter(
        args: ListParser, situations: list[ItemSituation]
    ) -> list[ItemSituation]:
        if args.status:
            situations = [s for s in situations if s.matches_status(args.status)]
        if args.priority:
            situations = [s for s in situations if s.item.priority == args.priority]
        if args.tag:
            situations = [s for s in situations if args.tag in s.item.tags]
        if args.assignee:
            situations = [s for s in situations if s.matches_assignee(args.assignee)]
        if args.can_start:
            situations = [s for s in situations if s.can_start]
        if args.remind_before:
            limit = Moment.parse(args.remind_before, "--remind-before")[:10]
            situations = [
                s
                for s in situations
                if s.item.remind_at and s.item.remind_at[:10] < limit
            ]
        order = args.sort or ListSort.NUMBER
        return sorted(situations, key=lambda s: s.get_sort_key(order))

    @staticmethod
    def _format_archived(item: Item) -> str:
        outcome = item.completion.outcome
        title = item.short_title
        line = f"{item.number:>4}  {outcome:<10}  {item.priority:<6}  {title}"
        reason = " ".join(item.completion.reason_text.split())
        if item.completion.follow_up:
            by = f"superseded by {Item.get_number(item.completion.follow_up)}"
            reason = f"{by}: {reason}" if reason else by
        if len(reason) > ListCommand.REASON_WIDTH:
            reason = reason[: ListCommand.REASON_WIDTH - 3] + "..."
        return f"{line}  - {reason}" if reason else line

    @staticmethod
    def _format_active(situation: ItemSituation) -> list[str]:
        item = situation.item
        status = str(situation.display_status)
        title = item.short_title
        parts = [f"{item.number:>4}  {status:<11}  {item.priority:<6}  {title}"]
        if item.tags:
            parts.append(f"[{', '.join(item.tags)}]")
        if item.due_at:
            parts.append(f"due {item.due_at}")
        if item.remind_at:
            parts.append(f"remind {item.remind_at}")
        if situation.unmet_dependency_marks:
            parts.append(f"deps: {','.join(situation.unmet_dependency_marks)}")
        lines = ["  ".join(parts)]
        for unit in item.work:
            lines += UnitLine.format(unit, situation)
        for blocker in situation.open_blockers:
            waiting = (
                f" (waiting on {blocker.waiting_on})" if blocker.waiting_on else ""
            )
            lines.append(
                f"        blocker {blocker.id}: {blocker.description}{waiting}"
            )
        if situation.closing_line:
            lines.append(f"        {situation.closing_line}")
        return lines
