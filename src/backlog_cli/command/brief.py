"""`backlog N brief ...`: the details file of an item."""

from pathlib import Path

from backlog_cli.command.action import ActionSpec, ChangeParser, ReadParser
from backlog_cli.command.base import (
    Change,
    MutatingCommand,
    TextCheck,
    WorkspaceCommand,
)
from backlog_cli.domain.address import Address
from backlog_cli.domain.details_file import DetailsFile
from backlog_cli.domain.item import Item
from backlog_cli.domain.vocabulary import AddressLevel, DetailsSection
from backlog_cli.errors import Refusal, UsageError
from backlog_cli.store.registry import Registry
from backlog_cli.store.workspace import Workspace


class CentralFileCheck:
    """What an executor receives must not point at the central files."""

    FORBIDDEN_TEXTS = (".bklg", "BACKLOG.yaml", "ARCHIVE.yaml", "details/")

    @classmethod
    def require_none(cls, text: str, home: Path) -> None:
        lowered = text.lower()
        found = [
            name
            for name in (*cls.FORBIDDEN_TEXTS, str(home))
            if name.lower() in lowered
        ]
        if found:
            raise Refusal(
                "The details mention the central files "
                f"({', '.join(found)}); an executor must not get them. "
                "Remove those words."
            )


class BriefShowParser(ReadParser):
    section: str | None = None  # Only this section (exact heading text).


class BriefSetParser(ChangeParser):
    from_file: str  # File with the new details (the 8 standard sections).


class BriefTextParser(ChangeParser):
    section: str  # The section (exact heading text).
    text: str | None = None  # The text.
    from_file: str | None = None  # File with the text (instead of --text).

    def configure(self) -> None:
        super().configure()
        names = "; ".join(str(section) for section in DetailsSection)
        self.add_argument(
            "--section", required=True, help=f"The section, exact heading: {names}"
        )


class BriefMixin:
    """What the five brief actions share."""

    GUIDE_SECTION = "brief"
    LEVELS = (AddressLevel.ITEM,)

    @staticmethod
    def get_writable_item(registry: Registry, address: str) -> Item:
        location = registry.find_item(Address.parse(address).item)
        if location.is_archived:
            raise Refusal(
                f"item {location.item.number} is archived; its details are read-only; "
                + location.item.describe_next_item_step()
            )
        return location.item

    @staticmethod
    def read_text_file(path_text: str) -> str:
        path = Path(path_text).expanduser()
        if not path.is_file():
            raise UsageError(f"{path} is not a file")
        try:
            return path.read_text(encoding="utf-8-sig")  # a BOM is dropped
        except UnicodeDecodeError:
            raise UsageError(f"{path} is not UTF-8 text") from None

    @classmethod
    def get_input_text(cls, text: str | None, from_file: str | None) -> str:
        if (text is None) == (from_file is None):
            raise UsageError("give exactly one of --text and --from-file")
        return text if text is not None else cls.read_text_file(from_file)


class BriefShowCommand(BriefMixin, ActionSpec, WorkspaceCommand):
    WORDS = ("brief", "show")
    SUMMARY = "Print the details file or one section."
    USAGE = "backlog N brief show [--section NAME]"
    EXAMPLES = 'Example: backlog 43 brief show --section "Agent handoff"'
    Parser = BriefShowParser

    def run(self, args: BriefShowParser) -> int:
        workspace = self.open_workspace(args)
        item = (
            workspace.load_registry().find_item(Address.parse(args.address).item).item
        )
        text = workspace.read_details(item.id)
        if args.section is None:
            self.print_lines(text.rstrip("\n"))
            return 0
        section = DetailsFile.parse_section_name(args.section)
        self.print_lines(DetailsFile.parse(text).get_section(section))
        return 0


class BriefExportCommand(BriefMixin, ActionSpec, WorkspaceCommand):
    WORDS = ("brief", "export")
    SUMMARY = (
        "Print the executor copy to stdout: title, number and the sections "
        f"({'; '.join(str(section) for section in DetailsSection)}); "
        "an empty section says (empty)."
    )
    USAGE = "backlog N brief export > handoff.md"
    EXAMPLES = "Example: backlog 43 brief export > handoff.md"
    Parser = ReadParser
    RULES_FILE = "export_rules.md"

    def read_rules(self) -> str:
        """The user's own rules for every executor, the same in every workspace."""
        try:
            return (self.session.home / self.RULES_FILE).read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    def run(self, args: ReadParser) -> int:
        workspace = self.open_workspace(args)
        item = (
            workspace.load_registry().find_item(Address.parse(args.address).item).item
        )
        details = DetailsFile.parse(workspace.read_details(item.id))
        exported = details.render(str(item.number), item.title, "(empty)")
        rules = self.read_rules().strip()
        if rules:
            exported = f"{exported.rstrip()}\n\n---\n\n{rules}\n"
        CentralFileCheck.require_none(exported, self.session.home)
        self.print_lines(exported.rstrip("\n"))
        return 0


class BriefSetCommand(BriefMixin, ActionSpec, MutatingCommand):
    WORDS = ("brief", "set")
    SUMMARY = "Replace the details with a UTF-8 file (8 sections, no title line)."
    USAGE = "backlog N brief set --from-file FILE"
    EXAMPLES = "Example: backlog 43 brief set --from-file details.md"
    Parser = BriefSetParser

    @staticmethod
    def _drop_own_title(text: str, item: Item) -> str:
        """The first line of `brief show` may come back: it is the generated one."""
        generated = f"# {item.id}: {item.title}"
        lines = text.split("\n")
        first = next((n for n, line in enumerate(lines) if line.strip()), None)
        if first is not None and lines[first].rstrip() == generated:
            return "\n".join(lines[first + 1 :])
        return text

    def make_change(
        self, args: BriefSetParser, workspace: Workspace, registry: Registry
    ) -> Change:
        file_text = self.read_text_file(args.from_file)
        TextCheck.require_clean_text(file_text)
        item = self.get_writable_item(registry, args.address)
        details = DetailsFile.parse(self._drop_own_title(file_text, item), True)
        text = details.render(item.id, item.title)
        DetailsFile.require_size(text)
        CentralFileCheck.require_none(text, self.session.home)
        return Change([f"Details of {item.number} replaced"], {item.id: text})


class BriefTextCommand(BriefMixin, ActionSpec, MutatingCommand):
    """A brief action that changes one section from a text."""

    def make_change(
        self, args: BriefTextParser, workspace: Workspace, registry: Registry
    ) -> Change:
        section = DetailsFile.parse_section_name(args.section)
        text = self.get_input_text(args.text, args.from_file)
        TextCheck.require_clean_text(text)
        CentralFileCheck.require_none(text, self.session.home)
        item = self.get_writable_item(registry, args.address)
        details = DetailsFile.parse(workspace.read_details(item.id))
        line = self.change_section(details, section, text, item)
        rendered = details.render(item.id, item.title)
        DetailsFile.require_size(rendered)
        return Change([line], {item.id: rendered})

    def change_section(
        self, details: DetailsFile, section: str, text: str, item: Item
    ) -> str:
        raise NotImplementedError


class BriefReplaceCommand(BriefTextCommand):
    WORDS = ("brief", "replace")
    SUMMARY = "Replace the whole content of one section."
    USAGE = "backlog N brief replace --section NAME (--text TEXT | --from-file FILE)"
    EXAMPLES = (
        'Example: backlog 43 brief replace --section "Agent handoff" --text "..."'
    )
    Parser = BriefTextParser

    def change_section(
        self, details: DetailsFile, section: str, text: str, item: Item
    ) -> str:
        details.replace_text(section, text)
        return f"Section '{section}' of {item.number} replaced"


class BriefAppendCommand(BriefTextCommand):
    WORDS = ("brief", "append")
    SUMMARY = "Append text to one section."
    USAGE = "backlog N brief append --section NAME (--text TEXT | --from-file FILE)"
    EXAMPLES = 'Example: backlog 43 brief append --section "Agent handoff" --text "..."'
    Parser = BriefTextParser

    def change_section(
        self, details: DetailsFile, section: str, text: str, item: Item
    ) -> str:
        TextCheck.require("--text", text)
        details.append_text(section, text)
        return f"Text appended to '{section}' of {item.number}"
