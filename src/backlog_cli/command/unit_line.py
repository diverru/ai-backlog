"""The lines of a unit in `list` and in `backlog N unit`."""

from backlog_cli.domain.action import Action
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.unit import Unit


class UnitLine:
    INDENT = " " * 8

    @classmethod
    def format(
        cls, unit: Unit, situation: ItemSituation, with_checks: bool = True
    ) -> list[str]:
        """The unit, then each post-release action that still waits for a result."""
        parts = [
            f"{cls.INDENT}{unit.id}",
            str(unit.kind),
            str(unit.status),
            unit.detail,
        ]
        if unit.assignees:
            parts.append(", ".join(assignee.short_text for assignee in unit.assignees))
        if unit.release_label:
            parts.append(unit.release_label)
        lines = ["  ".join(part for part in parts if part)]
        if with_checks:
            lines += [
                cls.format_check(check.action)
                for check in situation.pending_checks
                if check.unit_id == unit.id
            ]
        return lines

    @classmethod
    def format_check(cls, action: Action) -> str:
        line = f"{cls.INDENT}    {action.kind.label} {action.id}: {action.description}"
        if action.is_failed:
            line += f" — FAILED: {action.findings[-1].text}"
        return line
