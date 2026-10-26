"""Post-release actions of a unit: list, add and edit (done and cancel move status)."""

from tap import Positional

from backlog_cli.command.action import ActionSpec, ChangeParser, ReadParser
from backlog_cli.command.base import (
    Change,
    ChoiceArgument,
    DateHelp,
    MutatingCommand,
    TextCheck,
    WorkspaceCommand,
)
from backlog_cli.domain.address import Address
from backlog_cli.domain.vocabulary import ActionKind, ActionStatus, AddressLevel
from backlog_cli.errors import Refusal, UsageError
from backlog_cli.moment import Moment
from backlog_cli.store.registry import Registry
from backlog_cli.store.workspace import Workspace


class PostReleaseListCommand(ActionSpec, WorkspaceCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("post_release",)
    GUIDE_SECTION = "post_release"
    SUMMARY = "List the post-release actions of the unit, one line each."
    USAGE = "backlog N/UNIT post_release"
    EXAMPLES = "Example: backlog 43/engine post_release"
    Parser = ReadParser

    def run(self, args: ReadParser) -> int:
        registry = self.open_workspace(args).load_registry()
        target = registry.resolve_target(Address.parse(args.address))
        pr_unit = target.unit.get_pr_unit()
        actions = pr_unit.post_release_actions if pr_unit else []
        if not actions:
            self.print_lines(f"{target.address} has no post-release actions.")
            return 0
        for action in actions:
            status = (
                "done"
                if action.status == ActionStatus.CONFIRMED
                else str(action.status)
            )
            self.print_lines(
                f"{action.id}  {action.kind}  {status}  {action.description}"
            )
        return 0


class PostReleaseAddParser(ChangeParser):
    name: Positional[str]  # The action name: a short word you choose.
    kind: str  # command, verification or admin_change.
    title: str  # What it is, one line.
    instructions: str  # What exactly to do or check, with the expected result.

    def configure(self) -> None:
        super().configure()
        self.add_argument(
            "--kind",
            type=ChoiceArgument(ActionKind),
            metavar="KIND",
            required=True,
            help=f"Kind of action ({'|'.join(ActionKind)})",
        )


class PostReleaseAddCommand(ActionSpec, MutatingCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("post_release", "add")
    GUIDE_SECTION = "post_release"
    SUMMARY = "Add something to do or check in production after the release."
    USAGE = (
        "backlog N/UNIT post_release add NAME "
        "--kind command|verification|admin_change\n"
        '       --title "..." --instructions "..."'
    )
    EXAMPLES = (
        "Example: backlog 43/engine post_release add check_latency "
        '--kind verification --title "p95 latency" --instructions "p95 under 3 s"'
    )
    Parser = PostReleaseAddParser

    def make_change(
        self, args: PostReleaseAddParser, workspace: Workspace, registry: Registry
    ) -> Change:
        Address.require_new_id(args.name, "action id")
        TextCheck.require("--title", args.title)
        TextCheck.require("--instructions", args.instructions)
        TextCheck.require_clean_text(args.instructions or "")
        target = self.get_active_target(registry, args.address)
        action = target.unit.add_action(
            args.name,
            ActionKind(args.kind),
            args.title.strip(),
            args.instructions.strip(),
        )
        return Change(
            [f"Added post-release action {target.address}/{action.id} ({action.kind})"]
        )


class PostReleaseEditParser(ChangeParser):
    name: Positional[str]  # The action name.
    title: str | None = None  # The new title, one line.
    instructions: str | None = None  # The new instructions.


class PostReleaseEditCommand(ActionSpec, MutatingCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("post_release", "edit")
    GUIDE_SECTION = "post_release"
    SUMMARY = "Change the title or instructions of a pending action."
    USAGE = (
        'backlog N/UNIT post_release edit NAME [--title "..."] [--instructions "..."]'
    )
    EXAMPLES = (
        'Example: backlog 43/engine post_release edit check_latency --title "p99"'
    )
    Parser = PostReleaseEditParser

    def make_change(
        self, args: PostReleaseEditParser, workspace: Workspace, registry: Registry
    ) -> Change:
        if args.title is None and args.instructions is None:
            raise UsageError("nothing to change; give --title or --instructions")
        TextCheck.require("--title", args.title)
        TextCheck.require("--instructions", args.instructions)
        TextCheck.require_clean_text(args.instructions or "")
        target = self.get_active_target(registry, args.address)
        pr_unit = target.unit.get_pr_unit()
        if pr_unit is None:
            raise Refusal(
                f"{target.address} is research and has no post-release actions"
            )
        action = pr_unit.get_action(args.name)
        if not action.is_pending:
            raise Refusal(
                f"{target.address}/{action.id} is {action.status}; "
                "only pending actions can be edited"
            )
        if action.findings:
            raise Refusal(
                f"{target.address}/{action.id} has a finding; its title and "
                "instructions cannot change after the check failed"
            )
        lines = []
        if args.title is not None:
            action.description = args.title.strip()
            lines.append(f"{target.address}/{action.id}: title -> {action.description}")
        if args.instructions is not None:
            action.instructions = args.instructions.strip()
            lines.append(f"{target.address}/{action.id}: instructions changed")
        return Change(lines)


class PostReleaseFailParser(ChangeParser):
    name: Positional[str]  # The action name.
    finding: str  # What the check found, in a sentence.
    source: str  # How you know it: the command or panel you looked at.
    at: str | None = None  # When the check failed (default now).

    def configure(self) -> None:
        super().configure()
        self.add_argument("--at", help=DateHelp.past("When the check failed", True))


class PostReleaseFailCommand(ActionSpec, MutatingCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("post_release", "fail")
    GUIDE_SECTION = "post_release"
    SUMMARY = "Record that a check failed; the action stays pending."
    USAGE = (
        'backlog N/UNIT post_release fail NAME --finding "..." --source "..."\n'
        "       [--at DATE]"
    )
    EXAMPLES = (
        "Example: backlog 43/engine post_release fail check_latency "
        '--finding "p99 is 4.1 s" --source "how you know it"'
    )
    Parser = PostReleaseFailParser

    def make_change(
        self, args: PostReleaseFailParser, workspace: Workspace, registry: Registry
    ) -> Change:
        TextCheck.require("--finding", args.finding)
        TextCheck.require("--source", args.source)
        target = self.get_active_target(registry, args.address)
        pr_unit = target.unit.get_pr_unit()
        if pr_unit is None:
            raise Refusal(
                f"{target.address} is research and has no post-release actions"
            )
        observed = Moment.parse_instant(args.at, "--at") if args.at else None
        if observed is not None:
            Moment.require_not_future(observed, "--at", "a failed check")
        pr_unit.fail_action(
            args.name,
            args.finding.strip(),
            args.source.strip(),
            [unit.id for unit in target.item.work],
            observed,
        )
        count = len(pr_unit.get_action(args.name).findings)
        return Change(
            [
                f"{target.address}/{args.name}: failed check recorded "
                f"(finding {count}); the action stays pending. "
                f"Add a fix unit: backlog {target.item.number} unit add NAME "
                "--kind pr"
            ]
        )
