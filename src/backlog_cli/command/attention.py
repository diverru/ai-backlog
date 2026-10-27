"""`list --attention`: what needs a decision now, one group per kind."""

from backlog_cli.domain.attention import AttentionRow, AttentionRows
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.title import TitleText
from backlog_cli.domain.vocabulary import AttentionGroup


class AttentionReport:
    """The lines of each group for a set of item situations."""

    @classmethod
    def collect(
        cls, situations: list[ItemSituation], empty_brief_ids: set[str]
    ) -> dict[AttentionGroup, list[str]]:
        return {
            group: [cls.format(row) for row in rows]
            for group, rows in AttentionRows.collect(
                situations, empty_brief_ids
            ).items()
        }

    @staticmethod
    def format(row: AttentionRow) -> str:
        title = TitleText.shorten(row.title)
        address = row.address
        match row.group:
            case AttentionGroup.BLOCKERS:
                waiting = f" (waiting on {row.detail})" if row.detail else ""
                return f"{address} blocker {row.subject}: {row.text}{waiting}"
            case AttentionGroup.REMINDERS:
                return f"{address} remind {row.moment}: {title}"
            case AttentionGroup.OVERDUE:
                return f"{address} due {row.moment}: {title}"
            case AttentionGroup.READY_TO_CLOSE:
                frees = ItemSituation.describe_unblocks(row.unblocks)
                return f"{address} {title}: {row.command}{frees}"
            case AttentionGroup.FAILED:
                line = f"{address} {row.label} {row.subject}: {row.text}"
                return f"{line} — {row.detail}"
            case AttentionGroup.ACTIONS:
                return f"{address} {row.label} {row.subject}: {row.text}"
            case AttentionGroup.MERGED:
                return f"{address} {row.text or 'no PR'}: {title}"
            case AttentionGroup.UNASSIGNED:
                return f"{address}: {title}"
            case AttentionGroup.UNSTARTED_UNITS:
                return f"{address}: {title}: {row.command}"
            case AttentionGroup.EMPTY_BRIEF:
                return f"{address} {title}: {row.command}"
            case AttentionGroup.STUCK | AttentionGroup.CAN_START:
                return f"{address} {title}"
