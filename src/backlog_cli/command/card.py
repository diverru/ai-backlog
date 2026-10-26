"""The readable card of `backlog N` and `backlog N/UNIT`."""

from backlog_cli.command.unit_line import UnitLine
from backlog_cli.domain.completion import ItemCompletion, UnitCompletion
from backlog_cli.domain.item import Item
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.unit import Unit
from backlog_cli.domain.vocabulary import Outcome


class Card:
    INDENT = "  "
    INSTRUCTIONS_WIDTH = 200

    @classmethod
    def build_item(
        cls,
        item: Item,
        situation: ItemSituation,
        outcomes: dict[str, Outcome | None],
        is_archived: bool,
    ) -> list[str]:
        archived = "  [archived]" if is_archived else ""
        lines = [f"{item.number}  {item.title}{archived}"]
        lines.append(
            f"{cls.INDENT}status {situation.display_status}, priority {item.priority}"
        )
        if item.tags:
            lines.append(f"{cls.INDENT}tags {', '.join(item.tags)}")
        dates = [
            f"{label} {value}"
            for label, value in (("due", item.due_at), ("reminder", item.remind_at))
            if value
        ]
        if dates:
            lines.append(f"{cls.INDENT}{', '.join(dates)}")
        lines += cls._build_dependencies(item, outcomes)
        if item.blockers:
            lines.append(f"{cls.INDENT}blockers:")
            for blocker in item.blockers:
                waiting = (
                    f" (waiting on {blocker.waiting_on})" if blocker.waiting_on else ""
                )
                lines.append(
                    f"{cls.INDENT * 2}{blocker.id}  {blocker.description}{waiting}"
                )
        if item.work:
            lines.append(f"{cls.INDENT}units:")
            for unit in item.work:
                lines += cls._indent(
                    UnitLine.format(unit, situation, with_checks=False)
                )
        lines += cls._build_actions(item.work)
        lines += cls._build_corrections(item.work)
        if is_archived:
            lines.append(
                f"{cls.INDENT}closed: {cls._describe_completion(item.completion)}"
            )
        elif situation.next_line:
            lines.append(f"{cls.INDENT}{situation.next_line}")
        return lines

    @classmethod
    def build_unit(cls, item: Item, unit: Unit, situation: ItemSituation) -> list[str]:
        lines = [f"item {item.number}: {item.title}"]
        lines += [
            cls.INDENT + line.strip()
            for line in UnitLine.format(unit, situation, with_checks=False)
        ]
        pr_unit = unit.get_pr_unit()
        if pr_unit is not None and pr_unit.merge is not None:
            merged = pr_unit.merge
            lines.append(
                f"{cls.INDENT}merged {merged.merged_at or '(time not given)'} "
                f"(source: {merged.evidence.source})"
            )
        if pr_unit is not None and pr_unit.release is not None:
            release = pr_unit.release
            tag = f" {release.tag}" if release.tag else ""
            lines.append(
                f"{cls.INDENT}release{tag} at {release.released_at} "
                f"(source: {release.evidence.source})"
            )
        lines += cls._build_actions([unit])
        lines += cls._build_corrections([unit])
        if unit.completion is not None:
            lines.append(
                f"{cls.INDENT}closed: {cls._describe_completion(unit.completion)}"
            )
        return lines

    @classmethod
    def _build_dependencies(
        cls, item: Item, outcomes: dict[str, Outcome | None]
    ) -> list[str]:
        parts = []
        for dependency_id in item.depends_on:
            number = Item.get_number(dependency_id)
            outcome = outcomes.get(dependency_id)
            if outcome == Outcome.DONE:
                parts.append(f"{number} (done)")
            elif outcome is None:
                parts.append(f"{number} (NOT DONE: still active)")
            else:
                parts.append(f"{number} (NOT DONE: {outcome}, never will be)")
        lines = []
        if parts:
            lines.append(f"{cls.INDENT}depends on: {', '.join(parts)}")
        if item.prerequisite_prs:
            prs = ", ".join(str(pr) for pr in item.prerequisite_prs)
            lines.append(f"{cls.INDENT}prerequisite PRs: {prs}")
        return lines

    @classmethod
    def _build_actions(cls, units: list[Unit]) -> list[str]:
        lines = []
        for unit in units:
            pr_unit = unit.get_pr_unit()
            for action in pr_unit.post_release_actions if pr_unit else []:
                lines.append(
                    f"{cls.INDENT * 2}{unit.id}/{action.id}  {action.kind.label}  "
                    f"{action.status}  {action.description}"
                )
                lines.append(
                    f"{cls.INDENT * 3}instructions: "
                    f"{cls._shorten(action.instructions, cls.INSTRUCTIONS_WIDTH)}"
                )
                if action.confirmation is not None:
                    done = action.confirmation
                    lines.append(
                        f"{cls.INDENT * 3}confirmed "
                        f"{done.observed_at or done.recorded_at}: {done.result} "
                        f"(source: {done.source})"
                    )
                lines += [
                    f"{cls.INDENT * 3}finding {finding.at}: {finding.text} "
                    f"(source: {finding.source})"
                    for finding in action.findings
                ]
        return [f"{cls.INDENT}post-release actions:", *lines] if lines else []

    @classmethod
    def _build_corrections(cls, units: list[Unit]) -> list[str]:
        lines = []
        for unit in units:
            pr_unit = unit.get_pr_unit()
            for correction in pr_unit.corrections if pr_unit else []:
                lines.append(
                    f"{cls.INDENT * 2}{unit.id} {correction.subject}, "
                    f"{correction.at}: {correction.reason} "
                    f"(was {correction.describe()})"
                )
        return [f"{cls.INDENT}corrections:", *lines] if lines else []

    @staticmethod
    def _describe_completion(completion: ItemCompletion | UnitCompletion) -> str:
        happened = completion.completed_at
        if completion.evidence is not None and completion.evidence.observed_at:
            happened = completion.evidence.observed_at  # the --at, not the record
        by = ""
        if isinstance(completion, ItemCompletion) and completion.follow_up:
            by = f" by {Item.get_number(completion.follow_up)}"
        text = f"{completion.outcome}{by} at {happened}"
        if completion.reason:
            text += f": {completion.reason}"
        if completion.evidence is not None:
            text += (
                f": {completion.evidence.result} (source: {completion.evidence.source})"
            )
        return text

    @staticmethod
    def _shorten(text: str, width: int) -> str:
        one_line = " ".join(text.split())
        return one_line if len(one_line) <= width else one_line[:width] + "..."

    @staticmethod
    def _indent(lines: list[str]) -> list[str]:
        return [Card.INDENT * 2 + line.strip() for line in lines]
