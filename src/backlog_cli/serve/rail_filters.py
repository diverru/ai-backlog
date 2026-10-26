"""Status and tag filters in the rail: plain links to the Items page."""

from collections import Counter

from backlog_cli.domain.vocabulary import DisplayStatus
from backlog_cli.serve.items_page import StatusStyle
from backlog_cli.serve.text import HtmlText
from backlog_cli.serve.view import ItemFilter, WorkspaceView


class RailFilters:
    @classmethod
    def render(cls, view: WorkspaceView, flt: ItemFilter) -> str:
        """The section twice: open on a wide screen, folded on a narrow one."""
        statuses = cls._render_statuses(view, flt)
        tags = cls._render_tags(view, flt)
        if not statuses and not tags:
            return ""
        clear = ""
        if flt.status or flt.tag:
            clear = (
                f'<a class="f-clear" href="{view.url("items")}'
                f'{flt.query(status="", tag="")}">Clear filters</a>'
            )
        inner = f"{statuses}{tags}{clear}"
        return (
            f'<div class="f-wide"><div class="rail-label">Filters</div>{inner}</div>'
            f'<details class="f-narrow"><summary>Filters</summary>{inner}</details>'
        )

    @staticmethod
    def _chip(
        view: WorkspaceView, query: str, is_active: bool, inner: str, css: str = ""
    ) -> str:
        current = ' aria-current="true"' if is_active else ""
        return (
            f'<a class="fchip {css}" href="{view.url("items")}{query}"{current}>'
            f"{inner}</a>"
        )

    @classmethod
    def _render_statuses(cls, view: WorkspaceView, flt: ItemFilter) -> str:
        chips = []
        for status in DisplayStatus:
            count = sum(1 for s in view.situations if s.matches_status(status))
            if not count:
                continue
            tone = StatusStyle.CLASSES.get(str(status), "s-todo").replace("s-", "c-")
            is_active = flt.status == str(status)
            query = flt.query(status="" if is_active else str(status))
            inner = (
                f'<span class="sdot"></span>{HtmlText.esc(status)}'
                f'<span class="n">{count}</span>'
            )
            chips.append(cls._chip(view, query, is_active, inner, tone))
        return cls._group("Status", chips)

    @classmethod
    def _render_tags(cls, view: WorkspaceView, flt: ItemFilter) -> str:
        counts = Counter(tag for item in view.registry.active for tag in item.tags)
        chips = []
        for tag in sorted(counts, key=lambda name: (-counts[name], name)):
            is_active = flt.tag == tag
            query = flt.query(tag="" if is_active else tag)
            inner = f"#{HtmlText.esc(tag)}"
            chips.append(cls._chip(view, query, is_active, inner, "tagchip"))
        return cls._group("Tags", chips)

    @staticmethod
    def _group(label: str, chips: list[str]) -> str:
        if not chips:
            return ""
        return (
            f'<div class="f-group"><div class="f-sub">{label}</div>'
            f'<div class="chips">{"".join(chips)}</div></div>'
        )
