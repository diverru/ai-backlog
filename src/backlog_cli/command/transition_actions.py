"""The actions that end or advance work: done, merged, released, cancel, ..."""

from tap import Positional, Tap

from backlog_cli.command.action import ChangeParser
from backlog_cli.command.base import DateHelp
from backlog_cli.command.transition_command import TransitionCommand
from backlog_cli.domain.address import Address
from backlog_cli.domain.vocabulary import AddressLevel, MoveStatus
from backlog_cli.errors import UsageError
from backlog_cli.store.registry import Registry, Target


class ReasonParser(ChangeParser):
    reason: str  # Why, in a sentence.


class ReturnToTodoCommand(TransitionCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("return_to_todo",)
    STATUS = MoveStatus.TODO
    GUIDE_SECTION = "assign"
    SUMMARY = "Send a unit back from wip to todo."
    USAGE = 'backlog N/UNIT return_to_todo --reason "..."'
    EXAMPLES = 'Example: backlog 43/engine return_to_todo --reason "Agent stopped"'
    Parser = ReasonParser


class CancelCommand(TransitionCommand):
    LEVELS = (AddressLevel.ITEM, AddressLevel.UNIT)
    WORDS = ("cancel",)
    STATUS = MoveStatus.CANCELLED
    GUIDE_SECTION = "finish"
    SUMMARY = "Drop the item (it is archived) or the unit; it will not be done."
    USAGE = 'backlog N[/UNIT] cancel --reason "..."'
    EXAMPLES = 'Example: backlog 43 cancel --reason "Cancelled by the user"'
    Parser = ReasonParser


class SupersedeParser(ChangeParser):
    by: str  # The item (M) or unit (U2) that continues the work.
    reason: str  # Why, in a sentence.


class SupersedeCommand(TransitionCommand):
    LEVELS = (AddressLevel.ITEM, AddressLevel.UNIT)
    WORDS = ("supersede",)
    STATUS = MoveStatus.SUPERSEDED
    GUIDE_SECTION = "finish"
    SUMMARY = "Replace the item (archived) or the unit by one that continues it."
    USAGE = 'backlog N[/UNIT] supersede --by M|U2 --reason "..."'
    EXAMPLES = 'Example: backlog 43 supersede --by 45 --reason "Split into 45"'
    Parser = SupersedeParser


class ResultParser(ChangeParser):
    result: str  # What was observed.
    source: str  # How you know it: the command, link or check you used.
    at: str | None = None  # When it happened (default now).

    def configure(self) -> None:
        super().configure()
        self.add_argument("--at", help=DateHelp.past("When it happened", True))


class DoneCommand(TransitionCommand):
    LEVELS = (AddressLevel.ITEM, AddressLevel.UNIT)
    WORDS = ("done",)
    STATUS = MoveStatus.DONE
    GUIDE_SECTION = "finish"
    SUMMARY = (
        "Close the item with your result (it is archived as done), "
        "or finish a research unit."
    )
    USAGE = 'backlog N[/UNIT] done --result "..." --source "..." [--at DATE]'
    EXAMPLES = (
        "Write the results into the details first (backlog N brief append); "
        "after done they are read-only.\n"
        'Example: backlog 43 done --result "Orders found in 3 s" '
        '--source "how you know it"'
    )
    Parser = ResultParser


class MergedParser(ChangeParser):
    source: str  # How you know it is merged: `gh pr view 123`.
    at: str | None = None  # When it was merged (default now).
    result: str | None = None  # What you saw, if more than the source says.
    pr: str | None = None  # The PR as OWNER/NAME#N, if not linked before.
    correction: str | None = None  # Replace a recorded merge: why it was wrong.

    def configure(self) -> None:
        super().configure()
        self.add_argument("--at", help=DateHelp.past("When it was merged", True))


class MergedCommand(TransitionCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("merged",)
    STATUS = MoveStatus.MERGED
    GUIDE_SECTION = "unit"
    SUMMARY = "Record that the PR of the unit is merged, with how you checked it."
    USAGE = (
        'backlog N/UNIT merged --source "..." [--at DATE] [--result "..."] [--pr PR]\n'
        '       [--correction "why"]'
    )
    EXAMPLES = (
        'Example: backlog 43/engine merged --pr acme/api#123 --source "gh pr view 123"'
    )
    Parser = MergedParser


class ReleasedParser(ChangeParser):
    at: str  # When it reached production.
    source: str  # How you know it: `release_status` output, a release log.
    tag: str | None = None  # The release tag, if there is one.
    correction: str | None = None  # Replace the recorded release: why it was wrong.
    no_post_release: list[str] = []  # Unit with no post-release work.

    def configure(self) -> None:
        super().configure()
        self.add_argument(
            "--at",
            required=True,
            help=DateHelp.past("When it reached production", False),
        )
        self.add_argument(
            "--no-post-release",
            action="append",
            nargs="*",
            default=[],
            metavar="UNIT",
            help="Units with no post-release work: 4/a 5/b or 4/a,5/b",
        )

    def process_args(self) -> None:
        # A bare flag is [] (the only unit); every use may name several units.
        self.no_post_release = [
            word for group in self.no_post_release for word in (group or [""])
        ]


class ReleasedCommand(TransitionCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("released",)
    STATUS = MoveStatus.RELEASED
    GUIDE_SECTION = "unit"
    MULTI_TARGET = True
    SUMMARY = "Record that merged units reached production (several: 43/a,44/b)."
    USAGE = (
        'backlog N/UNIT[,N/UNIT ...] released --at DATE --source "..." [--tag TAG]\n'
        '       [--no-post-release [N/UNIT]] [--correction "why"]'
    )
    EXAMPLES = (
        "Example, two units (44/api has no post-release work, 43/engine has "
        "actions): backlog 43/engine,44/api released --at 2026-10-23 "
        '--source "release_status" --no-post-release 44/api'
    )
    Parser = ReleasedParser


class ActionResultParser(ResultParser):
    names: Positional[list[str]]  # One or more post-release action names.

    def configure(self) -> None:
        super().configure()
        self.add_argument("names", nargs="+", metavar="NAME")


class ActionCancelParser(ChangeParser):
    name: Positional[str]  # The post-release action name.
    reason: str  # Why.
    not_needed: bool = False  # The action is no longer needed (required after release).


class ActionTransitionCommand(TransitionCommand):
    """A post-release action of a unit: the address names the unit."""

    LEVELS = (AddressLevel.UNIT,)

    def resolve_targets(self, args: Tap, registry: Registry) -> list[Target]:
        unit = Address.parse(args.address)
        names = self.get_names(args)
        if len(set(names)) != len(names):
            raise UsageError("the same action is listed twice; list each one once")
        return [
            registry.resolve_target(Address(unit.item, unit.unit, name))
            for name in names
        ]

    def get_names(self, args: Tap) -> list[str]:
        raise NotImplementedError


class PostReleaseDoneCommand(ActionTransitionCommand):
    WORDS = ("post_release", "done")
    STATUS = MoveStatus.DONE
    GUIDE_SECTION = "post_release"
    SUMMARY = "Record the result of post-release actions that were run."
    USAGE = (
        'backlog N/UNIT post_release done NAME [NAME ...] --result "..." --source "..."'
    )
    EXAMPLES = (
        'Example: backlog 43/engine post_release done check_latency --result "p95 2 s" '
        '--source "how you know it"'
    )
    Parser = ActionResultParser

    def get_names(self, args: ActionResultParser) -> list[str]:
        return args.names


class PostReleaseCancelCommand(ActionTransitionCommand):
    WORDS = ("post_release", "cancel")
    STATUS = MoveStatus.CANCELLED
    GUIDE_SECTION = "post_release"
    SUMMARY = "Cancel a post-release action; after release it must be --not-needed."
    USAGE = 'backlog N/UNIT post_release cancel NAME --reason "..." [--not-needed]'
    EXAMPLES = (
        "Example: backlog 43/engine post_release cancel check_latency --not-needed "
        '--reason "Nothing to check"'
    )
    Parser = ActionCancelParser

    def get_names(self, args: ActionCancelParser) -> list[str]:
        return [args.name]
