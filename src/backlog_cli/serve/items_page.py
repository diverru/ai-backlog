"""`/<ws>/items`: the active items as a table, with filters and a sort."""

from collections import Counter

from backlog_cli.domain.situation import ItemSituation
from backlog_cli.serve.badges import Badge
from backlog_cli.domain.vocabulary import DisplayStatus, ListSort, UnitStatus
from backlog_cli.serve.text import HtmlText, LocalDate
from backlog_cli.serve.table_sort import SortHeader
from backlog_cli.serve.view import ItemFilter, NavSection, PageContent, WorkspaceView


class StatusStyle:
    """The colour class of a status word, shared by every page."""

    CLASSES = {
        "todo": "s-todo",
        "wip": "s-wip",
        "merged": "s-merged",
        "post_release": "s-released",
        "done": "s-done",
        "stuck": "s-failed",
        "cancelled": "s-gone",
        "superseded": "s-gone",
    }

    @classmethod
    def html(cls, status: str) -> str:
        css = cls.CLASSES.get(status, "s-todo")
        return f'<span class="status {css}">{HtmlText.esc(status)}</span>'

    @classmethod
    def word(cls, status: str) -> str:
        """The status as a coloured word without a background."""
        tone = cls.CLASSES.get(status, "s-todo").replace("s-", "c-")
        return f'<span class="word {tone}">{HtmlText.esc(status)}</span>'

    @classmethod
    def pill(cls, status: str, text: str | None = None, large: bool = False) -> str:
        """The status as a pill; `text` replaces the status word."""
        tone = cls.CLASSES.get(status, "s-todo").replace("s-", "c-")
        size = " lg" if large else ""
        return f'<span class="pill{size} {tone}">{HtmlText.esc(text or status)}</span>'


class ItemsPage:
    SORTS = ("number", "title", "status", "priority", "due")

    @classmethod
    def build(cls, view: WorkspaceView, params: dict[str, str]) -> PageContent:
        status = cls._read_enum(DisplayStatus, params.get("status"))
        sort = params.get("sort") if params.get("sort") in cls.SORTS else "number"
        direction = "desc" if params.get("dir") == "desc" else "asc"
        tag = params.get("tag") or None
        shown = [
            situation
            for situation in view.situations
            if (status is None or situation.matches_status(status))
            and (tag is None or tag in situation.item.tags)
        ]
        shown = cls._sort(shown, sort, direction)
        flt = ItemFilter(
            str(status or ""),
            tag or "",
            "" if (sort, direction) == ("number", "asc") else sort,
            "" if (sort, direction) == ("number", "asc") else direction,
        )
        count = f" \u00b7 {len(shown)}" if status or tag else ""
        body = [
            view.crumbs("<span>All items</span>"),
            f"<h1>All items{count}</h1>",
        ]
        if shown:
            body.append(cls._render_table(view, shown, flt, sort, direction))
        else:
            body.append('<p class="empty-state">No items match this filter</p>')
        return PageContent("All items", "\n".join(body), NavSection.ITEMS, flt)

    @staticmethod
    def _sort(
        situations: list[ItemSituation], sort: str, direction: str
    ) -> list[ItemSituation]:
        statuses = list(DisplayStatus)
        keys = {
            "number": lambda s: (s.item.number,),
            "title": lambda s: (s.item.title.lower(), s.item.number),
            "status": lambda s: (statuses.index(s.display_status), s.item.number),
            "priority": lambda s: s.get_sort_key(ListSort.PRIORITY),
            "due": lambda s: s.get_sort_key(ListSort.DUE),
        }
        ordered = sorted(situations, key=keys[sort], reverse=direction == "desc")
        if sort == "due":  # an item without a deadline stays last either way
            ordered.sort(key=lambda s: s.item.due_at is None)
        return ordered

    @staticmethod
    def _read_enum[E](enum_class: type[E], text: str | None) -> E | None:
        try:
            return enum_class(text) if text else None
        except ValueError:
            return None

    @classmethod
    def _render_table(
        cls,
        view: WorkspaceView,
        situations: list[ItemSituation],
        flt: ItemFilter,
        sort: str,
        direction: str,
    ) -> str:
        rows = "".join(cls._render_row(view, situation) for situation in situations)

        def head(key: str, label: str) -> str:
            return SortHeader.render(
                view.url("items"), key, label, flt, sort, direction
            )

        return (
            '<div class="panel table-wrap"><table class="table"><thead><tr>'
            f"{head('number', '№')}{head('title', 'Title')}"
            f"{head('status', 'Status')}{head('priority', 'Priority')}"
            f"<th>Units</th>{head('due', 'Due')}<th>Tags</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></div>"
        )

    @classmethod
    def _render_row(cls, view: WorkspaceView, situation: ItemSituation) -> str:
        esc, item = HtmlText.esc, situation.item
        href = view.url(f"items/{item.number}")
        overdue = " over" if situation.is_overdue else ""
        due = LocalDate.html(item.due_at, False)
        tags = Badge.tags(view, item.tags)
        return (
            f'<tr class="rowlink"><td class="addr">{item.number}</td>'
            f'<td><a class="title main" href="{href}">{esc(item.title)}</a>'
            f'<div class="slug">{esc(item.slug)}</div></td>'
            f"<td>{StatusStyle.pill(str(situation.display_status))}</td>"
            f"<td>{Badge.priority(item.priority)}</td>"
            f"<td>{cls._render_unit_counts(situation)}</td>"
            f'<td class="due{overdue}">{due}</td><td>{tags}</td></tr>'
        )

    @staticmethod
    def _render_unit_counts(situation: ItemSituation) -> str:
        counts = Counter(str(unit.status) for unit in situation.item.work)
        return (
            " ".join(
                f'<span class="count-chip {StatusStyle.CLASSES[str(status)]}">'
                f"{status} {counts[str(status)]}</span>"
                for status in UnitStatus
                if counts[str(status)]
            )
            or '<span class="sub">none</span>'
        )
