"""`/<ws>/archive`: the archived items, newest first."""

from backlog_cli.domain.item import Item
from backlog_cli.serve.items_page import StatusStyle
from backlog_cli.serve.text import HtmlText, LocalDate
from backlog_cli.serve.table_sort import SortHeader
from backlog_cli.serve.view import ItemFilter, NavSection, PageContent, WorkspaceView


class ArchivePage:
    REASON_WIDTH = 160

    SORTS = ("number", "title", "outcome", "closed")

    @classmethod
    def build(cls, view: WorkspaceView, params: dict[str, str]) -> PageContent:
        sort = params.get("sort") if params.get("sort") in cls.SORTS else "closed"
        default = "desc" if sort == "closed" else "asc"
        direction = (
            params.get("dir") if params.get("dir") in ("asc", "desc") else default
        )
        keys = {
            "number": lambda item: (item.number,),
            "title": lambda item: (item.title.lower(), item.number),
            "outcome": lambda item: (str(item.completion.outcome), item.number),
            "closed": lambda item: (item.completion.completed_at, item.number),
        }
        items = sorted(
            view.registry.archived, key=keys[sort], reverse=direction == "desc"
        )
        flt = ItemFilter()
        body = [
            view.crumbs("<span>Archive</span>"),
            "<h1>Archive</h1>",
            f'<div class="meta"><span>{len(items)} closed items</span></div>',
        ]
        if items:
            rows = "".join(cls._render_row(view, item) for item in items)

            def head(key: str, label: str) -> str:
                return SortHeader.render(
                    view.url("archive"), key, label, flt, sort, direction
                )

            body.append(
                '<div class="panel table-wrap"><table class="table"><thead><tr>'
                f"{head('number', '№')}{head('title', 'Title')}"
                f"{head('outcome', 'Outcome')}{head('closed', 'Closed')}"
                f"<th>Result or reason</th></tr></thead><tbody>{rows}"
                "</tbody></table></div>"
            )
        else:
            body.append('<p class="empty-state">The archive is empty</p>')
        return PageContent("Archive", "\n".join(body), NavSection.ARCHIVE)

    @classmethod
    def _render_row(cls, view: WorkspaceView, item: Item) -> str:
        esc, completion = HtmlText.esc, item.completion
        href = view.url(f"items/{item.number}")
        why = completion.reason_text
        by = ""
        if completion.follow_up:
            number = Item.get_number(completion.follow_up)
            link = view.url(f"items/{number}")
            slug = completion.follow_up.split("_", 1)[1]
            by = (
                f'superseded by <a class="addr" href="{link}">{number}</a> '
                f'<span class="slug">{esc(slug)}</span> '
            )
        shown = esc(HtmlText.shorten(why, cls.REASON_WIDTH))
        return (
            f'<tr class="rowlink"><td class="addr">{item.number}</td>'
            f'<td><a class="title main" href="{href}">{esc(item.title)}</a>'
            f'<div class="slug">{esc(item.slug)}</div></td>'
            f"<td>{StatusStyle.pill(str(completion.outcome))}</td>"
            f"<td>{LocalDate.html(completion.completed_at)}</td>"
            f'<td class="why" title="{esc(why)}">{by}{shown}</td></tr>'
        )
