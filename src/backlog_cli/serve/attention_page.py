"""`/<ws>/`: what needs a decision now, the rows of each group under their item."""

from backlog_cli.domain.attention import AttentionRow
from backlog_cli.domain.item import Item
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.unit import PrUnit, Unit
from backlog_cli.domain.vocabulary import AttentionGroup, Priority
from backlog_cli.serve.anchor import Anchor
from backlog_cli.serve.badges import Badge
from backlog_cli.serve.path_links import PathLinks
from backlog_cli.serve.items_page import StatusStyle
from backlog_cli.serve.reasons import ReasonText
from backlog_cli.serve.text import HtmlText, LocalDate
from backlog_cli.serve.unit_board import MiniRoute, UnitRoute
from backlog_cli.serve.view import NavSection, PageContent, WorkspaceView


class AttentionPage:
    TONES = {
        AttentionGroup.BLOCKERS: "g-blocked",
        AttentionGroup.REMINDERS: "g-blocked",
        AttentionGroup.OVERDUE: "g-blocked",
        AttentionGroup.READY_TO_CLOSE: "g-ready",
        AttentionGroup.FAILED: "g-failed",
        AttentionGroup.ACTIONS: "g-merged",
        AttentionGroup.MERGED: "g-merged",
        AttentionGroup.UNASSIGNED: "g-unassigned",
        AttentionGroup.UNSTARTED_UNITS: "g-unassigned",
        AttentionGroup.STUCK: "g-failed",
        AttentionGroup.CAN_START: "g-start",
        AttentionGroup.EMPTY_BRIEF: "g-start",
    }
    ITEM_NOTES = {
        AttentionGroup.STUCK: "every unit is cancelled or superseded",
        AttentionGroup.EMPTY_BRIEF: "brief is empty",
    }

    @classmethod
    def build(cls, view: WorkspaceView) -> PageContent:
        body = [view.crumbs("<span>Attention</span>"), "<h1>Attention</h1>"]
        if not view.attention:
            body.append('<p class="empty-state">Nothing needs a decision</p>')
        situations = {situation.item.number: situation for situation in view.situations}
        for group, rows in view.attention.items():
            body.append(cls._render_group(view, situations, group, rows))
        body.append(cls._render_schema_note(view))
        return PageContent("Attention", "\n".join(body), NavSection.ATTENTION)

    @staticmethod
    def _render_schema_note(view: WorkspaceView) -> str:
        if not view.registry.is_from_newer_schema:
            return ""
        return (
            '<p class="note">The files were written by a newer version of backlog; '
            "shown as the CLI reads them, read-only.</p>"
        )

    @classmethod
    def _render_group(
        cls,
        view: WorkspaceView,
        situations: dict[int, ItemSituation],
        group: AttentionGroup,
        rows: list[AttentionRow],
    ) -> str:
        by_item: dict[int, list[AttentionRow]] = {}
        for row in rows:
            by_item.setdefault(row.number, []).append(row)
        items = "".join(
            cls._render_item(view, situations[number], group, item_rows)
            for number, item_rows in by_item.items()
        )
        return (
            f'<section class="group {cls.TONES[group]}">'
            f"<h2>{HtmlText.esc(group.value)} "
            f'<span class="n">{len(rows)}</span></h2>'
            f'<div class="items">{items}</div></section>'
        )

    @classmethod
    def _render_item(
        cls,
        view: WorkspaceView,
        situation: ItemSituation,
        group: AttentionGroup,
        rows: list[AttentionRow],
    ) -> str:
        lines = "".join(cls._render_line(view, situation, group, row) for row in rows)
        subs = f'<ul class="subs">{lines}</ul>' if lines else ""
        return (
            f'<div class="item">{cls._render_head(view, situation, group, rows[0])}'
            f"{subs}</div>"
        )

    @classmethod
    def _render_head(
        cls,
        view: WorkspaceView,
        situation: ItemSituation,
        group: AttentionGroup,
        first: AttentionRow,
    ) -> str:
        esc, item = HtmlText.esc, situation.item
        if group == AttentionGroup.READY_TO_CLOSE:
            facts = StatusStyle.pill("done", "all units done")
            if first.unblocks:
                numbers = ", ".join(str(number) for number in first.unblocks)
                facts += f"<span>unblocks {numbers}</span>"
        else:
            facts = StatusStyle.pill(str(situation.display_status))
            if item.priority == Priority.HIGH:
                facts += Badge.priority(item.priority)
            facts += Badge.tags(view, item.tags)
            if item.due_at:
                facts += f"<span>due {LocalDate.html(item.due_at, False)}</span>"
        return (
            '<div class="item-head rowlink">'
            f'<span class="item-num">{item.number}</span>'
            '<span class="name">'
            f'<a class="main item-title" href="{view.card_url(item.number)}">'
            f"{esc(item.title)}</a>"
            f'<span class="slug">{esc(item.slug)}</span></span>'
            f'<span class="facts">{facts}</span></div>'
        )

    @classmethod
    def _render_line(
        cls,
        view: WorkspaceView,
        situation: ItemSituation,
        group: AttentionGroup,
        row: AttentionRow,
    ) -> str:
        """A sub-line opens its unit, action, finding or blocker in the card."""
        esc = HtmlText.esc
        item = situation.item
        if group == AttentionGroup.BLOCKERS:
            waiting = (
                f'<span class="sub">waits for {PathLinks.html(row.detail)}</span>'
                if row.detail
                else ""
            )
            href = view.card_url(item.number, Anchor.blocker(row.subject))
            return (
                '<li class="rowlink">'
                f'<a class="main pill c-failed" href="{href}" '
                f'title="blocker {esc(row.subject)}">blocker</a>'
                f'<span class="uinfo"><span>{PathLinks.html(row.text)}</span>'
                f"</span>{waiting}</li>"
            )
        if row.unit_id is None:
            return cls._render_item_line(group, row)
        unit = next(unit for unit in item.work if unit.id == row.unit_id)
        return cls._render_unit_line(view, item, unit, group, row)

    @classmethod
    def _render_item_line(cls, group: AttentionGroup, row: AttentionRow) -> str:
        """A line that is about the item itself: a note, with nothing to open."""
        day = LocalDate.html(row.moment, False)
        notes = {
            AttentionGroup.REMINDERS: f"reminder for {day}",
            AttentionGroup.OVERDUE: f"was due {day}",
        }
        note = notes.get(group, cls.ITEM_NOTES.get(group, ""))
        if not note:
            return ""  # the item head already says it all
        return f'<li><span class="line-note item-note">{note}</span></li>'

    @classmethod
    def _render_unit_line(
        cls,
        view: WorkspaceView,
        item: Item,
        unit: Unit,
        group: AttentionGroup,
        row: AttentionRow,
    ) -> str:
        esc = HtmlText.esc
        name = f"{unit.id}/{row.subject}" if row.subject else unit.id
        facts = [esc(assignee.short_text) for assignee in unit.assignees]
        text, tone = ReasonText.PILLS[group]
        pill = f'<span class="pill {tone}">{text}</span>'
        note = cls._describe_failure(group, row)
        if group == AttentionGroup.MERGED:
            facts.append(f"merged {LocalDate.html(row.moment, False)}")
        if group in (AttentionGroup.FAILED, AttentionGroup.ACTIONS):
            facts.append(PathLinks.html(row.text))
        pr = ""
        if isinstance(unit, PrUnit):
            pr = HtmlText.pr_link(unit.pr) if unit.pr else ""
            if unit.pr is None:
                facts.insert(0, "no PR yet")
        info = f'<span class="sub">{" · ".join(facts)}</span>' if facts else ""
        href = view.card_url(item.number, cls._find_anchor(unit, group, row))
        return (
            f'<li class="rowlink {UnitRoute.build_css(unit)}">{MiniRoute.render(unit)}'
            f'<span class="uinfo"><a class="main uname" href="{href}">{esc(name)}</a>'
            f"{pr}{info}</span>{pill}{note}</li>"
        )

    @staticmethod
    def _find_anchor(unit: Unit, group: AttentionGroup, row: AttentionRow) -> str:
        """Where the line leads: the failed finding, the action, or the unit."""
        if group == AttentionGroup.FAILED and isinstance(unit, PrUnit):
            action = next(a for a in unit.post_release_actions if a.id == row.subject)
            return Anchor.finding(unit.id, action.id, len(action.findings))
        if group == AttentionGroup.ACTIONS:
            return Anchor.action(unit.id, row.subject)
        return Anchor.unit(unit.id)

    @staticmethod
    def _describe_failure(group: AttentionGroup, row: AttentionRow) -> str:
        """The finding under a failed check; other lines have no note."""
        if group != AttentionGroup.FAILED:
            return ""
        day = LocalDate.html(row.moment, False)
        text = PathLinks.html(row.detail)
        return f'<span class="line-note bad">{text} · {day}</span>'
