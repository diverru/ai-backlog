"""Column headers that sort a table when clicked."""

from backlog_cli.serve.text import HtmlText
from backlog_cli.serve.view import ItemFilter


class SortHeader:
    ARROW = (
        '<svg class="arrow" viewBox="0 0 10 10" width="8" height="8" '
        'aria-hidden="true">'
        '<path d="M5 1.5 9 8.5H1z"/></svg>'
    )

    @classmethod
    def render(
        cls,
        path: str,
        key: str,
        label: str,
        flt: ItemFilter,
        current: str,
        direction: str,
    ) -> str:
        """A first click sorts ascending, a second one on the same header descends."""
        is_current = key == current
        next_direction = "desc" if is_current and direction == "asc" else "asc"
        href = path + flt.query(sort=key, dir=next_direction)
        aria = ""
        arrow = ""
        if is_current:
            aria = f' aria-sort="{"ascending" if direction == "asc" else "descending"}"'
            arrow = cls.ARROW
        return (
            f'<th{aria}><a class="sort {direction if is_current else ""}" '
            f'href="{HtmlText.esc(href)}">{label}{arrow}</a></th>'
        )
