"""Actions about who works on an item or a unit, and the PR of a unit."""

from tap import Positional

from backlog_cli.command.action import ActionSpec, ChangeParser
from backlog_cli.command.base import Change, MutatingCommand, TextCheck
from backlog_cli.domain.item import Item
from backlog_cli.domain.part import Assignee, PrRef
from backlog_cli.domain.vocabulary import AddressLevel, Outcome
from backlog_cli.errors import Refusal, UsageError
from backlog_cli.store.registry import Registry, Target
from backlog_cli.store.workspace import Workspace
from backlog_cli.transition.base import StatusSnapshot


class AssignParser(ChangeParser):
    agent: str  # Who works on it (required).
    task: str | None = None  # The agent's task as PROJECT:SEQ, e.g. api:456.
    role: str | None = None  # The role, e.g. back.


class UnassignParser(ChangeParser):
    agent: str | None = None  # Remove the assignee with this agent name.
    task: str | None = None  # Remove the assignees with this task.
    role: str | None = None  # Remove the assignees with this role.


class AssignCommand(ActionSpec, MutatingCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("assign",)
    GUIDE_SECTION = "assign"
    SUMMARY = "Give a unit to an agent: adds an assignee; todo becomes wip."
    USAGE = "backlog N/UNIT assign --agent A [--task T] [--role R]"
    EXAMPLES = (
        'Example: backlog 43/engine assign --agent "Backend agent" --task api:456'
    )
    Parser = AssignParser

    def make_change(
        self, args: AssignParser, workspace: Workspace, registry: Registry
    ) -> Change:
        TextCheck.require("--agent", args.agent)
        target = self.get_active_target(registry, args.address)
        assignee = Assignee.from_flags(args.task, args.agent, args.role)[0]
        before = StatusSnapshot.take(target)
        previous = list(target.unit.assignees)
        target.unit.add_assignee(assignee)
        lines = [f"{target.address}: assigned {assignee.named_text}"]
        if previous:
            who = ", ".join(old.short_text for old in previous)
            lines.append(
                f"{target.address}: this added an assignee; still assigned: {who}. "
                f'To remove one: backlog {target.address} unassign --agent "NAME"'
            )
        lines += [
            old.describe_move_to(new)
            for old, new in StatusSnapshot.get_changed(
                before, StatusSnapshot.take(target)
            )
        ]
        return Change(lines + self._describe_waits(registry, target))

    @staticmethod
    def _describe_waits(registry: Registry, target: Target) -> list[str]:
        """The work may start, but say what the item still waits for."""
        item = target.item
        outcomes = registry.get_dependency_outcomes(item)
        notes = []
        for dependency_id in item.depends_on:
            if outcomes.get(dependency_id) == Outcome.DONE:
                continue
            dependency = registry.find_item(Item.get_number(dependency_id)).item
            status = (
                dependency.status
                if dependency.completion is not None
                else dependency.current_status
            )
            notes.append(
                f"note: item {item.number} still waits for {dependency.number} "
                f"({status})"
            )
        return notes


class UnassignCommand(ActionSpec, MutatingCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("unassign",)
    GUIDE_SECTION = "assign"
    SUMMARY = "Remove assignees by agent, task or role; the status does not change."
    USAGE = "backlog N/UNIT unassign (--agent A | --task T | --role R)"
    EXAMPLES = 'Example: backlog 43/engine unassign --agent "Backend agent"'
    Parser = UnassignParser

    def make_change(
        self, args: UnassignParser, workspace: Workspace, registry: Registry
    ) -> Change:
        if not (args.agent or args.task or args.role):
            raise UsageError("unassign needs --agent, --task or --role")
        target = self.get_active_target(registry, args.address)
        removed = target.unit.remove_assignees(args.agent, args.task, args.role)
        who = ", ".join(assignee.short_text for assignee in removed)
        return Change([f"{target.address}: unassigned {who}"])


class LinkPrParser(ChangeParser):
    pr: Positional[str]  # OWNER/NAME#N.


class LinkPrCommand(ActionSpec, MutatingCommand):
    LEVELS = (AddressLevel.UNIT,)
    WORDS = ("link", "pr")
    GUIDE_SECTION = "unit"
    SUMMARY = "Record the PR of a unit, before its merge is recorded."
    USAGE = "backlog N/UNIT link pr OWNER/NAME#N"
    EXAMPLES = "Example: backlog 43/engine link pr acme/api#123"
    Parser = LinkPrParser

    def make_change(
        self, args: LinkPrParser, workspace: Workspace, registry: Registry
    ) -> Change:
        target = self.get_active_target(registry, args.address)
        pr = PrRef.from_text(args.pr, "PR")
        other = registry.find_other_unit_with_pr(pr, target.item, target.unit)
        if other is not None:
            raise Refusal(f"PR {pr} is already linked to unit {other}")
        pr_unit = target.unit.get_pr_unit()
        old = pr_unit.pr if pr_unit else None
        target.unit.set_pr(pr)
        before = f"{old} " if old is not None else ""
        return Change([f"{target.address}: pr {before}-> {target.unit.pr}"])
