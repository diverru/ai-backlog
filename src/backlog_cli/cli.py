"""The command line: global commands by name, everything else by address."""

import difflib
import os
import re
import sys
from typing import NoReturn
from pathlib import Path

from backlog_cli.command.add import AddCommand
from backlog_cli.command.base import (
    Command,
    Session,
    ShortHelpParser,
    TextCheck,
)
from backlog_cli.command.binding import BindCommand, UnbindCommand
from backlog_cli.command.guide import GuideCommand
from backlog_cli.command.listing import ListCommand
from backlog_cli.command.router import Router
from backlog_cli.command.search import SearchCommand
from backlog_cli.command.serve import ServeCommand
from backlog_cli.errors import BacklogError, UsageError


class RootParser(ShortHelpParser):
    workspace: str | None = None  # Workspace for this command (else: bound dir).

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.hide_flags(["workspace"])  # the usage line shows it
        self.error_command: type[Command] | None = None

    def error(self, message: str) -> NoReturn:
        """Flags the subcommand did not know arrive here: show its usage."""
        if self.error_command is None:
            super().error(message)
        print(f"usage: {self.error_command.USAGE}", file=sys.stderr)
        self.exit(
            2,
            f"backlog {self.error_command.NAME}: error: {message}"
            f"{self.suggest_flag(message)}\n"
            f"See: backlog guide {self.error_command.NAME}\n",
        )

    def suggest_flag(self, message: str) -> str:
        """`. Did you mean --x?` for the first unknown flag that has a close match."""
        valid = self.error_command.get_flag_names()
        for word in message.split():
            close = (
                difflib.get_close_matches(word, valid, n=1)
                if word.startswith("--")
                else []
            )
            if close:
                return f". Did you mean {close[0]}?"
        return ""

    def configure(self) -> None:
        self.add_subparsers(dest="command", title="commands", metavar="COMMAND")
        for command_class in Cli.COMMANDS:
            command_class.register(self)


class Cli:
    COMMANDS: list[type[Command]] = [
        AddCommand,
        ListCommand,
        SearchCommand,
        GuideCommand,
        BindCommand,
        UnbindCommand,
        ServeCommand,
    ]

    ROOT_HELP = """\
backlog: the coordinator's backlog. An item holds units of work (a PR or research);
a PR unit has post-release actions. Run `backlog guide` once; `guide all` is the manual.
Global commands:   backlog [--workspace NAME] COMMAND
  add SLUG --title "..."        new item, prints its number
  list [--attention|--can-start|--status|--sort|--archive]  items with units
  search TEXT                   find items, details, archive
  guide [SECTION]               manual: overview, lifecycle, a command, all
  bind NAME | unbind            bind a directory to a workspace
  serve [--port N]              read-only web viewer of all workspaces
Item:   backlog N ACTION        (N = item number; no action = show)
  show | rename | priority | tag add|remove | due add|delete | reminder add|delete
  block add|remove | dependency [add|remove] | done | cancel | supersede
  brief show|set|replace|append|export | unit [add]
Unit:   backlog N/UNIT ACTION   (no action = show)
  show | link pr | assign | unassign | return_to_todo | done (research) | merged
  released (several: N/A,N/B) | cancel | supersede
  post_release [add|edit|fail|done|cancel]
  A wrong merged or released record is replaced with --correction "why".
Help: backlog N --help, backlog N/UNIT --help, backlog N/UNIT post_release --help
list the actions of a level; add --help after an action for its flags.
Every change takes --dry-run (show, write nothing) and --workspace NAME.
Exit codes: 0 ok, 1 refused (nothing changed), 2 usage error.
Data root: ~/.bklg or $BKLG_HOME."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @classmethod
    def build_parser(cls) -> RootParser:
        return RootParser(
            prog="backlog",
            usage="backlog [--workspace NAME] COMMAND ...",
            underscores_to_dashes=True,
        )

    @classmethod
    def main(cls, argv: list[str] | None = None) -> int:
        home = Path(os.environ.get("BKLG_HOME") or Path.home() / ".bklg")
        session = Session(home=home, cwd=Path.cwd().resolve(), out=sys.stdout)
        return cls(session).run(sys.argv[1:] if argv is None else argv)

    @classmethod
    def find_first_word(cls, argv: list[str]) -> str | None:
        """The first word that is not a flag (and not the value of --workspace)."""
        words = iter(argv)
        for word in words:
            if word == "--workspace":
                next(words, None)
            elif not word.startswith("-"):
                return word
        return None

    @classmethod
    def find_command(cls, word: str | None) -> type[Command] | None:
        return next((command for command in cls.COMMANDS if command.NAME == word), None)

    @staticmethod
    def has_invalid_utf8(argv: list[str]) -> bool:
        """The shell hands over bytes that are not UTF-8 as lone surrogates."""
        try:
            for word in argv:
                word.encode("utf-8")
        except UnicodeEncodeError:
            return True
        return False

    def run(self, argv: list[str]) -> int:
        if self.has_invalid_utf8(argv):
            print(
                "an argument is not valid UTF-8 text; fix the encoding", file=sys.stderr
            )
            return 2
        first = argv[2:3] if argv[:1] == ["--workspace"] else argv[:1]
        if first and re.fullmatch(r"-[0-9]+", first[0]):
            print(f"{first[0]} is not an item number", file=sys.stderr)
            return 2
        word = self.find_first_word(argv)
        if word is None:
            asked_for_help = "-h" in argv or "--help" in argv
            if argv and not asked_for_help:
                print(
                    f"unknown option {argv[0]!r}; run backlog --help", file=sys.stderr
                )
                return 2
            print(self.ROOT_HELP, file=self.session.out)
            return 0 if asked_for_help else 2
        try:
            if self.find_command(word):
                return self.run_global(argv, word)
            self.require_address_like(word)
            return Router(self.session).run(argv)
        except BacklogError as error:
            print(error, file=sys.stderr)
            return error.exit_code

    def run_global(self, argv: list[str], word: str) -> int:
        command_class = self.find_command(word)
        parser = self.build_parser()
        parser.error_command = command_class
        args = parser.parse_args(argv)
        TextCheck.require_single_lines(args, command_class.get_flag_names())
        return command_class(self.session).run(args)

    def require_address_like(self, word: str) -> None:
        """A word that is no command and does not start an address is unknown."""
        if word[0].isdigit():
            return
        names = [command.NAME for command in self.COMMANDS]
        close = difflib.get_close_matches(word, names, n=1)
        hint = f"; did you mean {close[0]}?" if close else ""
        raise UsageError(
            f"unknown command {word!r}{hint}\n"
            f"Commands: {' '.join(names)}; or an address: backlog N ACTION, "
            "backlog N/UNIT ACTION\nSee: backlog --help"
        )
