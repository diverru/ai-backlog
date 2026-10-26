"""What needs a decision now: the rows of every group, for `list --attention` and
for the viewer. Each reader words the rows itself.
"""

from dataclasses import dataclass

from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.unit import Unit
from backlog_cli.domain.vocabulary import AttentionGroup, ItemStatus, UnitStatus


@dataclass(frozen=True)
class AttentionRow:
    group: AttentionGroup
    number: int
    unit_id: str | None
    title: str
    subject: str | None = None  # blocker id, action id
    text: str | None = None  # blocker or action text, the PR
    label: str | None = None  # the kind of an action
    detail: str | None = None  # who a blocker waits on, the last finding
    moment: str | None = None  # reminder, due, merge or finding time
    command: str | None = None
    unblocks: tuple[int, ...] = ()

    @property
    def address(self) -> str:
        return f"{self.number}/{self.unit_id}" if self.unit_id else str(self.number)


class AttentionRows:
    @classmethod
    def collect(
        cls, situations: list[ItemSituation]
    ) -> dict[AttentionGroup, list[AttentionRow]]:
        groups: dict[AttentionGroup, list[AttentionRow]] = {
            group: [] for group in AttentionGroup
        }
        for situation in situations:
            for row in cls._read_item(situation):
                groups[row.group].append(row)
        return {group: rows for group, rows in groups.items() if rows}

    @classmethod
    def _read_item(cls, situation: ItemSituation) -> list[AttentionRow]:
        item = situation.item
        number, title = item.number, item.title
        rows = [
            AttentionRow(
                AttentionGroup.BLOCKERS,
                number,
                None,
                title,
                blocker.id,
                blocker.description,
                detail=blocker.waiting_on,
            )
            for blocker in situation.open_blockers
        ]
        if situation.is_reminder_due:
            rows.append(
                AttentionRow(
                    AttentionGroup.REMINDERS, number, None, title, moment=item.remind_at
                )
            )
        if situation.is_overdue:
            rows.append(
                AttentionRow(
                    AttentionGroup.OVERDUE, number, None, title, moment=item.due_at
                )
            )
        if situation.is_ready_to_close:
            rows.append(
                AttentionRow(
                    AttentionGroup.READY_TO_CLOSE,
                    number,
                    None,
                    title,
                    command=item.done_hint,
                    unblocks=situation.unblocks,
                )
            )
        rows += cls._read_checks(situation)
        for unit in item.work:
            rows += cls._read_unit(situation, unit)
        if situation.is_stuck:
            rows.append(AttentionRow(AttentionGroup.STUCK, number, None, title))
        if situation.can_start:
            rows.append(AttentionRow(AttentionGroup.CAN_START, number, None, title))
        return rows

    @staticmethod
    def _read_checks(situation: ItemSituation) -> list[AttentionRow]:
        item, rows = situation.item, []
        for check in situation.pending_checks:
            action = check.action
            failed = action.is_failed
            rows.append(
                AttentionRow(
                    AttentionGroup.FAILED if failed else AttentionGroup.ACTIONS,
                    item.number,
                    check.unit_id,
                    item.title,
                    action.id,
                    action.description,
                    action.kind.label,
                    action.findings[-1].text if failed else None,
                    action.findings[-1].at if failed else None,
                )
            )
        return rows

    @staticmethod
    def _read_unit(situation: ItemSituation, unit: Unit) -> list[AttentionRow]:
        item = situation.item
        if unit.status == UnitStatus.MERGED:
            pr_unit = unit.get_pr_unit()
            merge = pr_unit.merge
            moment = merge.merged_at or merge.evidence.recorded_at
            pr = str(pr_unit.pr) if pr_unit.pr else None
            return [
                AttentionRow(
                    AttentionGroup.MERGED,
                    item.number,
                    unit.id,
                    item.title,
                    text=pr,
                    moment=moment,
                )
            ]
        if unit.status == UnitStatus.WIP and not unit.assignees:
            return [
                AttentionRow(
                    AttentionGroup.UNASSIGNED, item.number, unit.id, item.title
                )
            ]
        if unit.status == UnitStatus.TODO and item.current_status == ItemStatus.WIP:
            command = f"backlog {item.number}/{unit.id} assign --agent NAME"
            return [
                AttentionRow(
                    AttentionGroup.UNSTARTED_UNITS,
                    item.number,
                    unit.id,
                    item.title,
                    command=command,
                )
            ]
        return []
