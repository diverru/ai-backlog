"""Shared shape of a command: a Tap parser class, the help text, and `run`."""

import argparse
import difflib
import re
import sys
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, NoReturn, TextIO

from tap import Tap

from backlog_cli.errors import UsageError
from backlog_cli.store.binding import BindingConfig
from backlog_cli.store.repo_origin import RepoOrigin
from backlog_cli.store.registry import Registry
from backlog_cli.store.workspace import Workspace


@dataclass
class Session:
    """Where the command runs: data root, working directory, output stream."""

    home: Path
    cwd: Path
    out: TextIO


class ShortHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """One line per flag: a wide help column and no blank lines."""

    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=38, width=104)


class TypePrefix:
    """Tap starts every help with `(type, default=...)`; the short help drops it."""

    PATTERN = re.compile(r"^\(.*?\) ")

    @classmethod
    def strip(cls, help_text: str) -> str:
        return cls.PATTERN.sub("", help_text)


class ChoiceArgument:
    """An argparse `type`: the allowed values, and the closest one when it is typed
    wrong.
    """

    def __init__(
        self, allowed: Iterable[str], convert: Callable[[str], object] = str
    ) -> None:
        self.allowed = [str(value) for value in allowed]
        self.convert = convert

    @classmethod
    def of_enum(
        cls, enum_class: type[StrEnum], members: Iterable[StrEnum] | None = None
    ) -> "ChoiceArgument":
        return cls(members or enum_class, enum_class)

    def __call__(self, text: str) -> object:
        if text in self.allowed:
            return self.convert(text)
        message = f"invalid value {text!r}; allowed: {'|'.join(self.allowed)}"
        close = difflib.get_close_matches(text, self.allowed, n=1)
        if close:
            message += f"; did you mean {close[0]}?"
        raise argparse.ArgumentTypeError(message)


class TextCheck:
    """The one character filter of every text the tool stores or prints.

    No control characters (a multi-line text may hold `\n` and `\t`) and no
    bidi marks: they hide what a reader sees. A one-line value has no line break.
    """

    BIDI = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
    LINE_SEPARATORS = "\u2028\u2029"
    MAX_LENGTH = 300
    MULTILINE_FIELDS = ("text", "instructions")

    @classmethod
    def find_hidden(cls, text: str, allowed: str = "") -> str | None:
        """The first control or bidi character that is not `allowed`."""
        return next(
            (
                character
                for character in text
                if character not in allowed
                and (unicodedata.category(character) == "Cc" or character in cls.BIDI)
            ),
            None,
        )

    @classmethod
    def require_clean_text(cls, text: str) -> None:
        hidden = cls.find_hidden(text, "\n\t")
        if hidden is not None:
            raise UsageError(
                f"the text has a control character (U+{ord(hidden):04X}); remove it"
            )

    @classmethod
    def require(cls, name: str, text: str | None) -> None:
        if text is not None and not text.strip():
            raise UsageError(f"{name} must not be empty")

    @classmethod
    def require_single_lines(cls, args: Tap, flag_names: list[str]) -> None:
        """Every text flag except the multi-line ones is one clean line."""
        for name, value in args.as_dict().items():
            if name in cls.MULTILINE_FIELDS:
                continue
            values = value if isinstance(value, list) else [value]
            flag = f"--{name.replace('_', '-')}"
            label = flag if flag in flag_names else name
            for text in values:
                if isinstance(text, str):
                    cls._require_one_line(label, text)

    @classmethod
    def _require_one_line(cls, label: str, text: str) -> None:
        if text and not text.strip():
            raise UsageError(f"{label} must not be empty")
        has_break = any(c in text for c in "\n\t" + cls.LINE_SEPARATORS)
        if has_break:
            raise UsageError(f"{label} must be one line; it has a line break or a tab")
        hidden = cls.find_hidden(text)
        if hidden is not None:
            raise UsageError(
                f"{label} has a control character (U+{ord(hidden):04X}); remove it"
            )
        if len(text) > cls.MAX_LENGTH:
            raise UsageError(
                f"{label} is {len(text)} characters; at most {cls.MAX_LENGTH}"
            )


class ListText:
    """A list given as words: commas, spaces or both separate the entries."""

    @staticmethod
    def split(texts: list[str]) -> list[str]:
        return [word for text in texts for word in text.replace(",", " ").split()]


class DateHelp:
    """The help of a date flag, the same everywhere."""

    FORMAT = "YYYY-MM-DD or ISO datetime with offset (UTC Z ok)"
    PAST = (
        f"{FORMAT}; not in the future; "
        "a date alone means the end of that day, or now for today"
    )

    @classmethod
    def past(cls, what: str, default_now: bool) -> str:
        return f"{what}: {cls.PAST}" + (" (default now)" if default_now else "")


class HelpCard:
    """Flags every command accepts; the root help explains them once."""

    COMMON_FLAGS = ("help", "workspace", "dry_run")


class ShortHelpParser(Tap):
    """A Tap parser whose help is a short card: usage, one line per flag, example."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        kwargs.setdefault("formatter_class", ShortHelpFormatter)
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)
        self.guide_section: str | None = None
        for action in self._actions:
            if action.help:
                action.help = TypePrefix.strip(action.help)

    def error(self, message: str) -> NoReturn:
        """A usage error: this parser's usage line, a hint and its guide section."""
        pointer = (
            f"\nSee: backlog guide {self.guide_section}" if self.guide_section else ""
        )
        self.print_usage(sys.stderr)
        self.exit(
            2, f"{self.prog}: error: {message}{self.suggest_flag(message)}{pointer}\n"
        )

    def suggest_flag(self, message: str) -> str:
        """`. Did you mean --x?` for the first unknown flag with a close match."""
        if "unrecognized arguments" not in message:
            return ""
        valid = [
            flag
            for action in self._actions
            for flag in action.option_strings
            if flag.startswith("--")
        ]
        for word in message.split():
            close = (
                difflib.get_close_matches(word, valid, n=1)
                if word.startswith("--")
                else []
            )
            if close:
                return f". Did you mean {close[0]}?"
        return ""

    def hide_flags(self, names: Iterable[str]) -> None:
        """Leave these flags out of `--help`; usage or a group list names them."""
        hidden = set(names)
        for action in self._actions:
            if action.dest in hidden:
                action.help = argparse.SUPPRESS

    def format_help(self) -> str:
        lines = [f"usage: {self.usage}"] if self.usage else []
        if self.description:
            lines.append(self.description)
        formatter = self._get_formatter()
        rows = [
            (formatter._format_action_invocation(action), action.help)
            for action in self._actions
            if action.option_strings
            and action.dest not in HelpCard.COMMON_FLAGS
            and action.help
            and action.help != argparse.SUPPRESS
        ]
        width = max((len(name) for name, _ in rows), default=0)
        lines += [f"  {name:<{width}}  {text}" for name, text in rows]
        if self.epilog:
            lines.append(self.epilog)
        return "\n".join(lines) + "\n"


class CommandParser(ShortHelpParser):
    """Arguments every command that uses a workspace accepts."""

    workspace: str  # Workspace for this command (default: the bound directory).

    def configure(self) -> None:
        # SUPPRESS keeps a value given before the command name from being reset.
        self.add_argument(
            "--workspace",
            default=argparse.SUPPRESS,
            help="Workspace for this command (default: the bound directory)",
        )

    def add_enum_argument(
        self,
        flag: str,
        enum_class: type[StrEnum],
        description: str,
        allowed: list[StrEnum] | None = None,
    ) -> None:
        """Offer exactly the members of an enum and convert the text to a member."""
        members = allowed or list(enum_class)
        self.add_argument(
            flag,
            type=ChoiceArgument.of_enum(enum_class, members),
            default=None,
            metavar=flag.lstrip("-").upper().replace("-", "_"),
            help=f"{description} ({'|'.join(members)})",
        )


class MutatingParser(CommandParser):
    """Arguments of every command that changes data."""

    dry_run: bool = False  # Print what would change and write nothing.


@dataclass
class Change:
    lines: list[str]
    new_details: dict[str, str] = field(default_factory=dict)


class Command:
    NAME: ClassVar[str]
    SUMMARY: ClassVar[str]
    USAGE: ClassVar[str]
    EXAMPLES: ClassVar[str]
    Parser: ClassVar[type[Tap]]

    def __init__(self, session: Session) -> None:
        self.session = session

    @classmethod
    def register(cls, parent: Tap) -> None:
        parent.add_subparser(
            cls.NAME,
            cls.Parser,
            help=cls.SUMMARY,
            usage=cls.USAGE,
            description=cls.SUMMARY,
            epilog=cls.build_epilog(cls.EXAMPLES, cls.NAME),
        )

    @classmethod
    def get_flag_names(cls) -> list[str]:
        """Every `--flag` of the command and of its subcommands."""
        names: list[str] = []

        def collect(parser: argparse.ArgumentParser) -> None:
            for action in parser._actions:
                names.extend(
                    flag for flag in action.option_strings if flag.startswith("--")
                )
                if isinstance(action, argparse._SubParsersAction):
                    for subparser in action.choices.values():
                        collect(subparser)

        collect(cls.Parser(underscores_to_dashes=True))
        return names

    @staticmethod
    def build_epilog(examples: str, guide_section: str) -> str:
        return f"{examples}\nDetails: backlog guide {guide_section}"

    def run(self, args: Tap) -> int:
        raise NotImplementedError

    def print_lines(self, *lines: str) -> None:
        for line in lines:
            print(line, file=self.session.out)


class WorkspaceCommand(Command):
    found_by_repo: str | None = None

    def open_workspace(self, args: Tap) -> Workspace:
        name = args.workspace
        if not name:
            bindings = BindingConfig.load(self.session.home)
            name = bindings.get_workspace_for(self.session.cwd)
            if not name:
                name = self._find_by_repository(bindings)
        if not name:
            raise UsageError(
                f"No workspace is bound to {self.session.cwd} or any parent directory "
                "or to its repository, and --workspace was not given.\n"
                "Bind a directory (a parent directory covers everything below it):\n"
                "  backlog bind WORKSPACE [--dir PATH]\n"
                "or the repository of this directory:\n"
                "  backlog bind WORKSPACE --repo OWNER/NAME\n"
                "or name the workspace for this one command: "
                "backlog --workspace NAME COMMAND ..."
            )
        return Workspace.open(self.session.home, name)

    def _find_by_repository(self, bindings: BindingConfig) -> str | None:
        """The workspace of the origin repository; it says so on stderr, as the
        agent must see which workspace a command used and stdout may be a file.
        """
        repo = RepoOrigin.find(self.session.cwd)
        found = bindings.find_repo(repo) if repo else None
        if not found:
            return None
        self.found_by_repo = found[0]
        print(f"workspace {found[1]}, found by repository {found[0]}", file=sys.stderr)
        return found[1]

    def run_change(
        self,
        args: Tap,
        make_change: Callable[[Tap, Workspace, Registry], Change],
    ) -> int:
        """Lock, load, repair an interrupted archive, change, save.

        With --dry-run the save is skipped. Every command that writes goes
        through here, so the repair is never skipped.
        """
        workspace = self.open_workspace(args)
        with workspace.acquire_lock():
            registry = workspace.load_registry()
            registry.require_writable()
            for item_id in registry.recovered_ids:
                self.print_lines(f"Recovered interrupted archive of {item_id}")
            snapshot = registry.take_snapshot()
            change = make_change(args, workspace, registry)
            registry.settle_changed(snapshot, set(change.new_details))
            if args.dry_run:
                self.print_lines(
                    "Dry run, nothing written. These changes would be made:"
                )
            else:
                workspace.save(registry, change.new_details)
            self.print_lines(*change.lines)
        return 0


class MutatingCommand(WorkspaceCommand):
    """A command whose whole job is one change."""

    def run(self, args: Tap) -> int:
        return self.run_change(args, self.make_change)

    def make_change(
        self, args: Tap, workspace: Workspace, registry: Registry
    ) -> Change:
        raise NotImplementedError
