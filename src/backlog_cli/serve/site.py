"""Routes a GET request to a page. No sockets here: a request in, a response out."""

import sys
import traceback
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from backlog_cli.errors import UsageError
from backlog_cli.serve.archive_page import ArchivePage
from backlog_cli.serve.attention_page import AttentionPage
from backlog_cli.serve.file_routes import FileRoutes, Response
from backlog_cli.serve.item_page import ItemPage
from backlog_cli.serve.items_page import ItemsPage
from backlog_cli.serve.layout import PageLayout
from backlog_cli.serve.notice_page import NoticePage
from backlog_cli.serve.search_page import SearchPage
from backlog_cli.serve.view import PageContent, WorkspaceView
from backlog_cli.store.workspace import Workspace


class Site:
    READ_METHODS = ("GET", "HEAD")

    def __init__(self, home: Path) -> None:
        self.home = home
        self.port: int | None = None  # set when the server is bound
        self.layout = PageLayout(PageLayout.read_css())

    def list_workspaces(self) -> list[str]:
        """Every directory of the data root that holds a registry, by name."""
        if not self.home.is_dir():
            return []
        return sorted(
            path.name
            for path in self.home.iterdir()
            if Workspace.NAME_PATTERN.match(path.name)
            and path.is_dir()
            and (path / "BACKLOG.yaml").is_file()
        )

    def is_own_host(self, host: str | None) -> bool:
        """A request must name this server: a rebound DNS name is refused."""
        if self.port is None:
            return True
        return host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def handle(
        self,
        method: str,
        target: str,
        host: str | None = None,
        origin: str | None = None,
        body: bytes = b"",
    ) -> Response:
        if not self.is_own_host(host):
            return Response(403, "403 Forbidden\n", content_type="text/plain")
        parts = urlsplit(target)
        segments = [unquote(segment) for segment in parts.path.split("/") if segment]
        if method == "POST" and segments == ["_", "open"]:
            form = parse_qs(body.decode("utf-8", "replace"))
            fields = {name: values[0] for name, values in form.items()}
            return FileRoutes.open(fields, origin == f"http://{host}")
        if method not in self.READ_METHODS:
            return Response(405, "405 Method Not Allowed\n", {"Allow": "GET, HEAD"})
        query = parse_qs(parts.query, keep_blank_values=True)
        params = {name: values[0] for name, values in query.items()}
        try:
            return self._route(segments, params)
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            return self._render_page(
                NoticePage.build_error(None, str(error)), None, 500
            )

    def _route(self, segments: list[str], params: dict[str, str]) -> Response:
        names = self.list_workspaces()
        if not segments:
            if not names:
                return self._render_page(NoticePage.build_empty_root(), None)
            return self._redirect(f"/{names[0]}/")
        if segments == ["_", "file"]:
            return FileRoutes.preview(params, ItemPage.render_markdown)
        if segments == ["_", "raw"]:
            return FileRoutes.raw(params)
        return self._route_workspace(names, segments[0], segments[1:], params)

    def _route_workspace(
        self, names: list[str], name: str, rest: list[str], params: dict[str, str]
    ) -> Response:
        if name not in names:
            return self._not_found(names)
        workspace = Workspace.open(self.home, name)
        try:
            view = WorkspaceView(self.home, workspace, workspace.load_registry())
            status, content = self._build_page(view, rest, params)
            return self._render_page(content, view, status, names)
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            reason = f"{type(error).__name__}: {error}"
            return self._render_page(
                NoticePage.build_error(name, reason), None, 500, names
            )

    def _build_page(
        self, view: WorkspaceView, rest: list[str], params: dict[str, str]
    ) -> tuple[int, PageContent]:
        if not rest:
            return 200, AttentionPage.build(view)
        if rest == ["items"]:
            return 200, ItemsPage.build(view, params)
        if rest == ["archive"]:
            return 200, ArchivePage.build(view, params)
        if rest == ["search"]:
            return 200, SearchPage.build(view, params)
        if len(rest) == 2 and rest[0] == "items" and rest[1].isdecimal():
            return self._build_item_page(view, int(rest[1]))
        return 404, NoticePage.build_not_found(
            "No such page.", view.url("items"), "To the items list"
        )

    @staticmethod
    def _build_item_page(view: WorkspaceView, number: int) -> tuple[int, PageContent]:
        try:
            location = view.registry.find_item(number)
        except UsageError:
            content = NoticePage.build_not_found(
                f"Item {number} is neither active nor archived.",
                view.url("items"),
                "To the items list",
            )
            return 404, content
        return 200, ItemPage.build(view, location)

    def _not_found(self, names: list[str]) -> Response:
        content = NoticePage.build_not_found("No such workspace.", "/", "Home")
        return self._render_page(content, None, 404, names)

    def _render_page(
        self,
        content: PageContent,
        view: WorkspaceView | None,
        status: int = 200,
        names: list[str] | None = None,
    ) -> Response:
        names = self.list_workspaces() if names is None else names
        return Response(status, self.layout.render(content, names, view))

    @staticmethod
    def _redirect(location: str) -> Response:
        return Response(302, "", {"Location": location})
