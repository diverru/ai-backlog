"""`backlog ADDRESS ACTION ...`: find the action a user typed and run it."""

import difflib
from dataclasses import dataclass

from backlog_cli.command.action import ActionSpec
from backlog_cli.command.base import Session, TextCheck
from backlog_cli.command.brief import (
    BriefAppendCommand,
    BriefExportCommand,
    BriefReplaceCommand,
    BriefSetCommand,
    BriefShowCommand,
)
from backlog_cli.command.item_edit import (
    DueAddCommand,
    DueDeleteCommand,
    PriorityCommand,
    ReminderAddCommand,
    ReminderDeleteCommand,
    RenameCommand,
    TagAddCommand,
    TagRemoveCommand,
)
from backlog_cli.command.item_link import (
    BlockAddCommand,
    BlockRemoveCommand,
    DependencyAddCommand,
    DependencyCommand,
    DependencyRemoveCommand,
    UnitAddCommand,
    UnitListCommand,
)
from backlog_cli.command.post_release import (
    PostReleaseAddCommand,
    PostReleaseEditCommand,
    PostReleaseFailCommand,
    PostReleaseListCommand,
)
from backlog_cli.command.show import ShowCommand
from backlog_cli.command.transition_actions import (
    CancelCommand,
    DoneCommand,
    MergedCommand,
    PostReleaseCancelCommand,
    PostReleaseDoneCommand,
    ReleasedCommand,
    ReturnToTodoCommand,
    SupersedeCommand,
)
from backlog_cli.command.work_assign import (
    AssignCommand,
    LinkPrCommand,
    UnassignCommand,
)
from backlog_cli.domain.address import Address
from backlog_cli.domain.vocabulary import AddressLevel
from backlog_cli.errors import UsageError


@dataclass(frozen=True)
class AddressedCall:
    """The command line split into what the router needs."""

    address_text: str
    level: AddressLevel
    leading_flags: list[str]  # `--workspace NAME` given before the address
    rest: list[str]  # everything after the address


class ActionTable:
    """Every action of the grammar, found by the words that follow the address."""

    ACTIONS: list[type[ActionSpec]] = [
        ShowCommand,
        RenameCommand,
        PriorityCommand,
        TagAddCommand,
        TagRemoveCommand,
        DueAddCommand,
        DueDeleteCommand,
        ReminderAddCommand,
        ReminderDeleteCommand,
        BlockAddCommand,
        BlockRemoveCommand,
        DependencyCommand,
        DependencyAddCommand,
        DependencyRemoveCommand,
        AssignCommand,
        UnassignCommand,
        ReturnToTodoCommand,
        CancelCommand,
        SupersedeCommand,
        BriefShowCommand,
        BriefSetCommand,
        BriefReplaceCommand,
        BriefAppendCommand,
        BriefExportCommand,
        UnitListCommand,
        UnitAddCommand,
        LinkPrCommand,
        DoneCommand,
        MergedCommand,
        ReleasedCommand,
        PostReleaseListCommand,
        PostReleaseAddCommand,
        PostReleaseEditCommand,
        PostReleaseFailCommand,
        PostReleaseDoneCommand,
        PostReleaseCancelCommand,
    ]
    DEFAULT_WORDS = ("show",)
    HELP_FLAGS = ("-h", "--help")

    @classmethod
    def find(cls, words: tuple[str, ...]) -> type[ActionSpec] | None:
        return next((action for action in cls.ACTIONS if action.WORDS == words), None)

    @classmethod
    def for_level(cls, level: AddressLevel) -> list[type[ActionSpec]]:
        return [action for action in cls.ACTIONS if level in action.LEVELS]

    @classmethod
    def get_group_words(cls) -> set[str]:
        """First words of two-word actions: tag, due, brief, unit, ..."""
        return {action.WORDS[0] for action in cls.ACTIONS if len(action.WORDS) > 1}

    @classmethod
    def wants_help(cls, words: list[str]) -> bool:
        return any(flag in words for flag in cls.HELP_FLAGS)


class Router:
    """Runs `backlog ADDRESS [ACTION] [flags]`."""

    RENAMED_ACTION = "accept"

    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def split_call(argv: list[str]) -> AddressedCall:
        """The first word that is not a flag is the address."""
        leading: list[str] = []
        index = 0
        while index < len(argv):
            word = argv[index]
            if word == "--workspace" and index + 1 < len(argv):
                leading += argv[index : index + 2]
                index += 2
            elif word.startswith("--workspace="):
                leading.append(word)
                index += 1
            elif word.startswith("-"):
                raise UsageError(f"unexpected {word!r} before the address")
            else:
                break
        text = argv[index]
        level = Router.get_address_level(text)
        return AddressedCall(text, level, leading, argv[index + 1 :])

    @staticmethod
    def get_address_level(text: str) -> AddressLevel:
        """`43` is an item, `43/engine` a unit; units may be listed with commas."""
        parts = [Address.parse(part) for part in text.split(",")]
        for part in parts:
            if part.level == AddressLevel.ACTION:
                raise UsageError(
                    f"bad address {text!r}; a post-release action is named in the "
                    "command: backlog N/UNIT post_release done NAME"
                )
            if len(parts) > 1 and part.level != AddressLevel.UNIT:
                raise UsageError(
                    f"{part} is an {part.level}; several addresses work only for "
                    "released, which takes unit addresses N/U"
                )
        return parts[0].level

    def run(self, argv: list[str]) -> int:
        call = self.split_call(argv)
        words, consumed = self.pick_words(call)
        if words is None:
            return 0
        action = self.require_action(call, words)
        parser = action.build_parser()
        args = parser.parse_args(call.leading_flags + call.rest[consumed:])
        args.address = call.address_text
        TextCheck.require_single_lines(args, action.get_flag_names())
        return action(self.session).run(args)

    def pick_words(self, call: AddressedCall) -> tuple[tuple[str, ...] | None, int]:
        """The words of the action, how many arguments they use; None = help shown."""
        rest = call.rest
        first = rest[0] if rest and not rest[0].startswith("-") else None
        if first is None:
            if ActionTable.wants_help(rest):
                self.print_level_help(call, None)
                return None, 0
            return ActionTable.DEFAULT_WORDS, 0
        second = rest[1] if len(rest) > 1 and not rest[1].startswith("-") else None
        if second and ActionTable.find((first, second)):
            return (first, second), 2
        is_group = first in ActionTable.get_group_words()
        if is_group and second is None and ActionTable.wants_help(rest):
            self.print_level_help(call, first)
            return None, 0
        if ActionTable.find((first,)):
            return (first,), 1
        if is_group:
            raise UsageError(self.build_group_message(call, first, second))
        raise UsageError(self.build_unknown_action_message(call, first))

    def require_action(
        self, call: AddressedCall, words: tuple[str, ...]
    ) -> type[ActionSpec]:
        action = ActionTable.find(words)
        if call.level not in action.LEVELS:
            levels = " or ".join(str(level) for level in action.LEVELS)
            article = "an" if levels.startswith("item") else "a"
            raise UsageError(
                f"{' '.join(words)} is {article} {levels} action: {action.USAGE}"
            )
        if "," in call.address_text and not action.MULTI_TARGET:
            raise UsageError(
                f"{' '.join(words)} takes one address; only `released` takes "
                "several units: 43/engine,44/api"
            )
        return action

    def build_group_message(
        self, call: AddressedCall, group: str, wrong: str | None
    ) -> str:
        known = [
            action.WORDS[1]
            for action in ActionTable.for_level(call.level)
            if action.WORDS[0] == group and len(action.WORDS) > 1
        ]
        shown = f" {wrong!r} is not one of them;" if wrong else ""
        return f"`{group}` needs an action:{shown} {group} {'|'.join(known)}"

    def build_unknown_action_message(self, call: AddressedCall, word: str) -> str:
        if word == self.RENAMED_ACTION:
            return (
                f"{word} was renamed to done: "
                'backlog N done --result "..." --source "..." [--at DATE]'
            )
        names = sorted({a.WORDS[0] for a in ActionTable.for_level(call.level)})
        close = difflib.get_close_matches(word, names, n=1)
        hint = f"; did you mean {close[0]}?" if close else ""
        pattern = "N/UNIT" if call.level == AddressLevel.UNIT else "N"
        return (
            f"unknown {call.level} action {word!r}{hint}\n"
            f"Actions: backlog {pattern} --help"
        )

    def print_level_help(self, call: AddressedCall, group: str | None) -> None:
        """One line per action of this level, or of one group."""
        pattern = "N/UNIT" if call.level == AddressLevel.UNIT else "N"
        actions = ActionTable.for_level(call.level)
        if group:
            actions = [a for a in actions if a.WORDS[0] == group]
        heading = f"backlog {pattern} {group or 'ACTION'}"
        rows = [(" ".join(action.WORDS), action.SUMMARY) for action in actions]
        width = max(len(name) for name, _ in rows)
        print(
            f"{heading}   (`... --help` after an action: its flags)",
            file=self.session.out,
        )
        for name, summary in rows:
            print(f"  {name:<{width}}  {summary}", file=self.session.out)
