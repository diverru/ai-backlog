"""`backlog N` / `backlog N/UNIT`: a readable card; `--full` is the stored YAML."""

from backlog_cli.command.action import ActionSpec, ReadParser
from backlog_cli.command.base import WorkspaceCommand
from backlog_cli.command.card import Card
from backlog_cli.domain.address import Address
from backlog_cli.domain.vocabulary import AddressLevel, ItemSource
from backlog_cli.store.yamlfile import YamlFile


class ShowParser(ReadParser):
    full: bool = False  # Print the stored record as YAML, empty values too.


class ShowCommand(ActionSpec, WorkspaceCommand):
    LEVELS = (AddressLevel.ITEM, AddressLevel.UNIT)
    WORDS = ("show",)
    GUIDE_SECTION = "show"
    SUMMARY = "Show an item or a unit as a readable card (archived items too)."
    USAGE = "backlog N[/UNIT] [show] [--full]"
    EXAMPLES = "Examples: backlog 43   backlog 43/engine show --full"
    Parser = ShowParser

    def run(self, args: ShowParser) -> int:
        registry = self.open_workspace(args).load_registry()
        target = registry.resolve_target(Address.parse(args.address))
        item = target.item
        situation = registry.get_situation(item)
        if not args.full:
            if target.unit:
                lines = Card.build_unit(item, target.unit, situation)
            else:
                outcomes = (
                    registry.get_archived_dependency_outcomes(item)
                    if target.is_archived
                    else registry.get_dependency_outcomes(item)
                )
                lines = Card.build_item(item, situation, outcomes, target.is_archived)
            self.print_lines(*lines)
            return 0
        source = ItemSource.ARCHIVE if target.is_archived else ItemSource.ACTIVE
        self.print_lines(f"# source: {source}")
        if target.unit:
            self.print_lines(f"# item {item.number}: {item.title}")
            record = target.unit
        else:
            if situation.closing_line:
                self.print_lines(f"# {situation.closing_line}")
            record = item
        data = record.to_dict()
        if not target.unit and not target.is_archived:
            data["status"] = str(item.current_status)
        self.print_lines(YamlFile.dump(data).rstrip("\n"))
        return 0
