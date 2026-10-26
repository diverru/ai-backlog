"""The Russian words for why work is not done, shared by the card and Attention."""

from backlog_cli.domain.unit import PrUnit, Unit
from backlog_cli.domain.vocabulary import AttentionGroup, UnitStatus
from backlog_cli.serve.text import HtmlText


class ReasonText:
    # (pill text, pill tone) of a unit line on the Attention page
    PILLS = {
        AttentionGroup.FAILED: ("failed", "c-failed"),
        AttentionGroup.ACTIONS: ("waits for check", "c-merged"),
        AttentionGroup.MERGED: ("waits for release", "c-merged"),
        AttentionGroup.UNASSIGNED: ("no assignee", "c-failed"),
        AttentionGroup.UNSTARTED_UNITS: ("unassigned", "c-todo"),
    }
    GONE_ITEM = "cancelled; the item can only be cancelled"
    # (pill text, pill tone) of a unit, on its card and in the state box
    UNIT_PILLS = {
        UnitStatus.TODO: ("not started", "c-todo"),
        UnitStatus.WIP: ("in progress", "c-wip"),
        UnitStatus.MERGED: ("waits for release", "c-merged"),
        UnitStatus.POST_RELEASE: ("waits for check", "c-released"),
        UnitStatus.DONE: ("done", "c-done"),
        UnitStatus.CANCELLED: ("cancelled", "c-gone"),
        UnitStatus.SUPERSEDED: ("superseded", "c-gone"),
    }
    FAILED_CHECK = ("check failed", "c-failed")

    @staticmethod
    def pill(label: str, tone: str) -> str:
        return f'<span class="pill {tone}">{HtmlText.esc(label)}</span>'

    @staticmethod
    def word(label: str, tone: str) -> str:
        """The same state as a coloured word, for the plain lists."""
        return f'<span class="word {tone}">{HtmlText.esc(label)}</span>'

    @classmethod
    def unit_label(cls, unit: Unit) -> tuple[str, str]:
        label, tone = cls.UNIT_PILLS[unit.status]
        if isinstance(unit, PrUnit) and any(a.is_failed for a in unit.pending_actions):
            label, tone = cls.FAILED_CHECK
        elif unit.status == UnitStatus.SUPERSEDED and unit.completion.superseded_by:
            label = f"superseded by {unit.completion.superseded_by}"
        return label, tone

    @classmethod
    def unit_pill(cls, unit: Unit) -> str:
        return cls.pill(*cls.unit_label(unit))
