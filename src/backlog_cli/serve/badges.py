"""Priority pills and hashtags, the same on every page that lists items."""

from urllib.parse import urlencode

from backlog_cli.serve.text import HtmlText
from backlog_cli.serve.view import WorkspaceView


class Badge:
    PRIORITY = {"high": "p-high", "normal": "p-normal", "low": "p-low"}

    @classmethod
    def priority(cls, priority: object) -> str:
        css = cls.PRIORITY.get(str(priority), "p-normal")
        return f'<span class="pill {css}">{HtmlText.esc(priority)}</span>'

    @staticmethod
    def tags(view: WorkspaceView, tags: list[str]) -> str:
        """`#back`: a click lists the items with that tag."""
        return "".join(
            f'<a class="hashtag" href="{view.url("items")}?{urlencode({"tag": tag})}">'
            f"#{HtmlText.esc(tag)}</a>"
            for tag in tags
        )
