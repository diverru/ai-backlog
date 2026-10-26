"""`/<ws>/items/<N>`: the card of one item, active or archived."""

from markdown_it import MarkdownIt

from backlog_cli.domain.details_file import DetailsFile
from backlog_cli.domain.item import Item
from backlog_cli.errors import UsageError
from backlog_cli.serve.badges import Badge
from backlog_cli.serve.items_page import StatusStyle
from backlog_cli.serve.external_links import ExternalLinks
from backlog_cli.serve.path_links import PathLinks
from backlog_cli.serve.text import HtmlText, LocalDate
from backlog_cli.serve.state_box import StateBox
from backlog_cli.serve.unit_board import CorrectionHistory, UnitCards
from backlog_cli.serve.view import NavSection, PageContent, WorkspaceView
from backlog_cli.store.registry import ItemLocation


class ItemPage:
    # Raw HTML stays escaped and markdown-it refuses `javascript:` links.
    MARKDOWN = ExternalLinks.install(
        PathLinks.install(
            MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
        )
    )

    @classmethod
    def render_markdown(cls, text: str) -> str:
        return cls.MARKDOWN.render(text)

    @classmethod
    def build(cls, view: WorkspaceView, location: ItemLocation) -> PageContent:
        item = location.item
        section = "Archive" if location.is_archived else "All items"
        link = "archive" if location.is_archived else "items"
        body = [
            view.crumbs(
                f'<a href="{view.url(link)}">{section}</a>',
                f'<span class="addr">{item.number}</span> · '
                f'<span class="slug">{HtmlText.esc(item.slug)}</span>',
            ),
            cls._render_head(view, location),
            StateBox.render(view, location),
            cls._render_recovery_note(view, item),
            f'<h2>Units <span class="n">{len(item.work)}</span></h2>',
            UnitCards.render(item.work)
            if item.work
            else '<p class="empty-state">No units yet</p>',
            CorrectionHistory.render(item.work),
            cls._render_brief(view, item),
        ]
        nav = NavSection.ARCHIVE if location.is_archived else NavSection.ITEMS
        return PageContent(f"{item.number} {item.title}", "\n".join(body), nav)

    @classmethod
    def _render_head(cls, view: WorkspaceView, location: ItemLocation) -> str:
        """The status pill leads the title; priority, tags and dates follow."""
        esc, item = HtmlText.esc, location.item
        if location.is_archived:
            status = str(item.completion.outcome)
        else:
            status = str(view.registry.get_situation(item).display_status)
        parts = [Badge.priority(item.priority), Badge.tags(view, item.tags)]
        if item.due_at:
            parts.append(f"<span>due {LocalDate.html(item.due_at, False)}</span>")
        if item.remind_at:
            parts.append(f"<span>remind {LocalDate.html(item.remind_at, False)}</span>")
        parts.append(
            f'<span class="slug">{esc(item.slug)}</span>'
            f"<span>created {LocalDate.html(item.created_at)} · "
            f"updated {LocalDate.html(item.updated_at)}</span>"
        )
        return (
            f'<h1 class="titled">{StatusStyle.pill(status, large=True)}'
            f'<span class="t">{esc(item.title)}</span></h1>'
            f'<div class="meta">{"".join(parts)}</div>'
        )

    @staticmethod
    def _render_recovery_note(view: WorkspaceView, item: Item) -> str:
        if item.id not in view.registry.recovered_ids:
            return ""
        return '<p class="note">Will be recovered by the next CLI command.</p>'

    @classmethod
    def _render_brief(cls, view: WorkspaceView, item: Item) -> str:
        try:
            text = view.workspace.read_details(item.id)
        except OSError as error:
            reason = HtmlText.esc(error.strerror or error)
            return (
                '<div class="panel brief"><p class="sub">'
                f"The brief file cannot be read: {reason}</p></div>"
            )
        try:
            sections = DetailsFile.parse(text).sections
        except UsageError as error:
            return (
                '<div class="panel brief"><div class="doc"><p class="sub">'
                f"The brief file cannot be parsed: {HtmlText.esc(error)}</p>"
                f"<pre>{HtmlText.esc(text)}</pre></div></div>"
            )
        parts = []
        for name, body in sections.items():
            rendered = cls.render_markdown(body) or '<p class="empty">(empty)</p>'
            parts.append(f'<h3 class="sec">{HtmlText.esc(name)}</h3>{rendered}')
        return f'<div class="panel brief"><div class="doc">{"".join(parts)}</div></div>'
