"""The box under the title: what is still open, or the outcome, and the links."""

from backlog_cli.domain.item import Item
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.unit import PrUnit, ResearchUnit, Unit
from backlog_cli.domain.vocabulary import UnitStatus
from backlog_cli.serve.anchor import Anchor
from backlog_cli.serve.items_page import StatusStyle
from backlog_cli.serve.path_links import PathLinks
from backlog_cli.serve.reasons import ReasonText
from backlog_cli.serve.text import HtmlText, LocalDate
from backlog_cli.serve.view import WorkspaceView
from backlog_cli.store.registry import ItemLocation


esc = HtmlText.esc


class StateBox:
    """Two blocks under the head: the parts that are open, then the dependencies."""

    @classmethod
    def render(cls, view: WorkspaceView, location: ItemLocation) -> str:
        parts = cls._render_parts(view, location)
        dependencies = DependencyBlock.render(view, location)
        return f'<div class="state-split">{parts}{dependencies}</div>'

    @classmethod
    def _render_parts(cls, view: WorkspaceView, location: ItemLocation) -> str:
        resolved = cls._render_resolved_blockers(location.item)
        if location.is_archived:
            return cls._render_outcome(view, location.item, resolved)
        situation = view.registry.get_situation(location.item)
        if situation.is_ready_to_close:
            return (
                '<section class="parts ready"><p>All units done \u2014 '
                f"ready to close</p>{resolved}</section>"
            )
        lines = "".join(cls._build_lines(view, situation))
        return (
            f'<section class="parts open"><ul class="open-list">{lines}</ul>'
            f"{resolved}</section>"
        )

    @classmethod
    def _render_outcome(cls, view: WorkspaceView, item: Item, resolved: str) -> str:
        completion = item.completion
        head = esc(completion.outcome)
        if completion.follow_up:
            number = Item.get_number(completion.follow_up)
            link = view.url(f"items/{number}")
            slug = completion.follow_up.split("_", 1)[1]
            head += (
                f' \u2192 <a class="addr" href="{link}">{number}</a> '
                f'<span class="slug">{esc(slug)}</span>'
            )
        source = ""
        if completion.evidence is not None:
            source = f" \u00b7 source: {PathLinks.html(completion.evidence.source)}"
        return (
            f'<section class="parts outcome o-{esc(completion.outcome)}">'
            f"<p><strong>{head}</strong></p><p>"
            f"{LocalDate.html(completion.completed_at)} \u00b7 "
            f"{PathLinks.html(completion.reason_text)}{source}</p>{resolved}</section>"
        )

    @staticmethod
    def _render_resolved_blockers(item: Item) -> str:
        rows = []
        for resolved in item.resolved_blockers:
            reason = (
                f" \u00b7 {PathLinks.html(resolved.reason)}" if resolved.reason else ""
            )
            rows.append(
                f'<li class="resolved"><span class="num">{esc(resolved.id)}</span>'
                f"<s>{PathLinks.html(resolved.description)}</s>"
                f'<span class="sub">{LocalDate.html(resolved.resolved_at, False)}'
                f"{reason}</span></li>"
            )
        return f'<ul class="open-list">{"".join(rows)}</ul>' if rows else ""

    @classmethod
    def _build_lines(cls, view: WorkspaceView, situation: ItemSituation) -> list[str]:
        """One line per open thing; a click anywhere on it opens its place."""
        item = situation.item
        if not item.work:
            return ["<li>no units yet</li>"]
        lines = []
        for index, unit in enumerate(item.work, 1):
            lines += cls._build_unit_lines(view, unit, item, index)
        for blocker in situation.open_blockers:
            anchor = Anchor.blocker(blocker.id)
            who = PathLinks.html(blocker.waiting_on) if blocker.waiting_on else ""
            waiting = f'<span class="sub">waits for {who}</span>' if who else ""
            lines.append(
                cls._row(
                    view.card_url(item.number, anchor),
                    f'<span class="num blocker-id">{esc(blocker.id)}</span>',
                    f"<span>{PathLinks.html(blocker.description)}</span>{waiting}",
                    anchor,
                )
            )
        return lines

    @staticmethod
    def _row(href: str, main_html: str, rest_html: str, anchor: str = "") -> str:
        """The main link holds the number and the name; inner links stay apart."""
        ident = f' id="{anchor}"' if anchor else ""
        return (
            f'<li class="rowlink"{ident}><a class="main" href="{href}">{main_html}</a>'
            f"{rest_html}</li>"
        )

    @classmethod
    def _build_unit_lines(
        cls, view: WorkspaceView, unit: Unit, item: Item, index: int
    ) -> list[str]:
        """`index` is the number the unit card shows, so the two can be matched."""
        name = (
            f'<span class="num">{index}.</span>'
            f'<span class="uname">{esc(unit.id)}</span>'
        )
        href = view.card_url(item.number, Anchor.unit(unit.id))
        if unit.is_terminal:
            if not item.has_no_completed_work:
                return []
            word = ReasonText.word("cancelled", "c-gone")
            return [cls._line(href, name, word, esc(ReasonText.GONE_ITEM))]
        if isinstance(unit, PrUnit) and unit.status == UnitStatus.POST_RELEASE:
            return cls._build_check_lines(view, item.number, unit, name)
        word = ReasonText.word(*ReasonText.unit_label(unit))
        return [cls._line(href, name, word, cls._describe_detail(unit))]

    @classmethod
    def _build_check_lines(
        cls, view: WorkspaceView, number: int, unit: PrUnit, name: str
    ) -> list[str]:
        lines = []
        failed = [action for action in unit.pending_actions if action.is_failed]
        waiting = [action for action in unit.pending_actions if not action.is_failed]
        for action in failed:
            anchor = Anchor.finding(unit.id, action.id, len(action.findings))
            word = ReasonText.word(f"check {action.id} failed", "c-failed")
            text = PathLinks.html(action.findings[-1].text)
            lines.append(cls._line(view.card_url(number, anchor), name, word, text))
        if waiting:
            anchor = Anchor.action(unit.id, waiting[0].id)
            names = ", ".join(action.id for action in waiting)
            word = ReasonText.word(f"waits for check {names}", "c-released")
            lines.append(cls._line(view.card_url(number, anchor), name, word, ""))
        return lines

    @staticmethod
    def _describe_detail(unit: Unit) -> str:
        if isinstance(unit, ResearchUnit) and unit.status == UnitStatus.WIP:
            return "research"
        if not isinstance(unit, PrUnit) or unit.status != UnitStatus.MERGED:
            return ""
        parts = [HtmlText.pr_link(unit.pr)] if unit.pr else []
        if unit.merge is not None:
            merge = unit.merge
            when = LocalDate.html(merge.merged_at or merge.evidence.recorded_at, False)
            parts.append(f"merged {when}")
        return ", ".join(parts)

    @classmethod
    def _line(cls, href: str, name: str, word: str, detail_html: str) -> str:
        """Number, name and state word in the main link; the detail after it."""
        detail = f'<span class="sub">{detail_html}</span>' if detail_html else ""
        return cls._row(href, name + word, detail)


class DependencyBlock:
    """Under the parts: what this item waits for, and what waits for it."""

    @classmethod
    def render(cls, view: WorkspaceView, location: ItemLocation) -> str:
        item = location.item
        waits = cls._render_needs(view, location) + cls._render_prerequisites(item)
        blocks = cls._render_blocks(view, location)
        groups = [
            cls._render_group(label, rows)
            for label, rows in (("Waits for", waits), ("Blocks", blocks))
            if rows
        ]
        return f'<section class="deps">{"".join(groups)}</section>' if groups else ""

    @staticmethod
    def _render_group(label: str, rows: list[str]) -> str:
        return (
            f'<div class="dep-group"><div class="dep-label">{label}</div>'
            f'<ul class="dep-list">{"".join(rows)}</ul></div>'
        )

    @classmethod
    def _render_item_row(
        cls, view: WorkspaceView, item_id: str, title: str | None, status: str
    ) -> str:
        number = Item.get_number(item_id)
        slug = item_id.split("_", 1)[1]
        # an archived item is known by its id only: the archive file stays closed
        text = esc(title) if title else esc(slug)
        return (
            f'<li class="rowlink"><span class="addr num">{number}</span>'
            '<span class="name">'
            f'<a class="main title" href="{view.card_url(number)}">{text}</a>'
            f'<span class="slug">{esc(slug)}</span></span>'
            f"{status}</li>"
        )

    @classmethod
    def _render_needs(cls, view: WorkspaceView, location: ItemLocation) -> list[str]:
        item, registry = location.item, view.registry
        outcomes = (
            registry.get_archived_dependency_outcomes(item)
            if location.is_archived
            else registry.get_dependency_outcomes(item)
        )
        active = {other.id: other for other in registry.active}
        rows = []
        for dependency_id in item.depends_on:
            other = active.get(dependency_id)
            if other is not None:
                status = StatusStyle.word(str(other.current_status))
                title = other.title
            else:
                outcome = outcomes.get(dependency_id)
                status = StatusStyle.word(str(outcome)) if outcome else ""
                title = None
            rows.append(cls._render_item_row(view, dependency_id, title, status))
        return rows

    @classmethod
    def _render_blocks(cls, view: WorkspaceView, location: ItemLocation) -> list[str]:
        item, registry = location.item, view.registry
        dependents = (
            registry.get_dependents(item)
            if location.is_archived
            else registry.get_active_dependents(item)
        )
        return [
            cls._render_item_row(
                view, other.id, other.title, StatusStyle.word(str(other.current_status))
            )
            for other in sorted(dependents, key=lambda other: other.number)
        ]

    @staticmethod
    def _render_prerequisites(item: Item) -> list[str]:
        return [
            f'<li><span class="addr num">PR</span>{HtmlText.pr_link(pr)}'
            '<span class="sub">does not block</span></li>'
            for pr in item.prerequisite_prs
        ]
