"""Pages that carry no data: the empty root, not found, and a read failure."""

from backlog_cli.serve.text import HtmlText
from backlog_cli.serve.view import NavSection, PageContent


class NoticePage:
    @staticmethod
    def build_empty_root() -> PageContent:
        return PageContent(
            "No workspace",
            "<h1>No workspace yet</h1>"
            '<p class="empty-state">The data root is empty. '
            "A workspace appears when the coordinator creates one.</p>",
        )

    @staticmethod
    def build_not_found(text: str, link_url: str, link_text: str) -> PageContent:
        return PageContent(
            "Not found",
            f'<h1>Not found</h1><p class="empty-state">{HtmlText.esc(text)} '
            f'<a href="{HtmlText.esc(link_url)}">{HtmlText.esc(link_text)}</a></p>',
            NavSection.ITEMS,
        )

    @staticmethod
    def build_error(workspace_name: str | None, reason: str) -> PageContent:
        esc = HtmlText.esc
        where = (
            f"workspace <code>{esc(workspace_name)}</code>"
            if workspace_name
            else "the data"
        )
        return PageContent(
            "Read error",
            f"<h1>Could not read {where}</h1>"
            f'<div class="error panel"><p>{esc(reason)}</p>'
            '<p class="sub">No file was changed. '
            "Details are in the stderr of the server.</p></div>",
        )
