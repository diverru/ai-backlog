"""`backlog serve`: the read-only viewer, over real HTTP on a free port."""

import http.client
import json
import re
import socket
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pytest

from backlog_cli.command.search import SearchTimeLimit
from backlog_cli.domain.vocabulary import Readiness
from backlog_cli.serve.server import ViewerServer
from backlog_cli.serve.site import Site
from backlog_cli.serve.text import LocalDate
from backlog_cli.store.workspace import Workspace
from backlog_cli.serve.opener import Opener
from backlog_cli.serve.path_links import PathLinks
from conftest import Backlog

XSS_TITLE = '<script>alert(1)</script> "><img onerror=x>'


@dataclass
class Reply:
    status: int
    body: str
    headers: dict[str, str]


class Viewer:
    """The server answers in the main thread, as `backlog serve` does; the client
    of each request runs in a helper thread.
    """

    def __init__(self, home: Path) -> None:
        self.server = ViewerServer(0, Site(home))
        self.acceptor = self.server.start_accepting()

    def request(
        self,
        path: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
    ) -> Reply:
        replies: list[Reply] = []
        client = threading.Thread(
            target=lambda: replies.append(self._fetch(path, method, headers, body))
        )
        client.start()
        self.server.answer_next(20)
        client.join()
        return replies[0]

    def _fetch(
        self,
        path: str,
        method: str,
        headers: dict[str, str] | None,
        body: str | None,
    ) -> Reply:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        body = response.read().decode(errors="replace")
        connection.close()
        return Reply(response.status, body, dict(response.getheaders()))

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def get(self, path: str) -> str:
        reply = self.request(path)
        assert reply.status == 200, f"{path}: {reply.status}"
        return reply.body

    def stop(self) -> None:
        self.server.shutdown()
        self.acceptor.join()
        self.server.server_close()


@pytest.fixture
def viewer(workspace: Backlog):
    started = Viewer(workspace.home)
    yield started
    started.stop()


def tree(home: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(home)): (path.stat().st_mtime_ns, path.read_bytes())
        for path in sorted(home.rglob("*"))
        if path.is_file()
    }


def build_demo(workspace: Backlog) -> int:
    """An item with a failed check, a research unit and a cancelled unit."""
    number = workspace.failed_check()
    workspace.ok_line(f"{number} unit add study --kind research")
    workspace.ok_line(f"{number}/study assign --agent R")
    workspace.ok_line(f"{number} unit add gone --kind research")
    workspace.ok_line(f"{number}/gone cancel --reason nope")
    return number


def test_no_workspace_shows_how_to_bind_and_two_are_listed(backlog: Backlog) -> None:
    started = Viewer(backlog.home)
    try:
        assert "No workspace yet" in started.get("/")
        backlog.ok("bind", "zeta", "--dir", str(backlog.work))
        (backlog.work / "b").mkdir()
        backlog.ok("bind", "alpha", "--dir", str(backlog.work / "b"))
        reply = started.request("/")
        assert (reply.status, reply.headers["Location"]) == (302, "/alpha/")
        page = started.get("/alpha/")
        assert '<a class="ws-row" href="/alpha/">alpha</a>' in page
        assert '<a class="ws-row" href="/zeta/">zeta</a>' in page  # nothing waits
        assert "<select" not in page and 'href="/alpha/items"' in page
        assert 'class="ws-pages"' not in started.get("/zeta/").split("zeta")[0]
        assert started.request("/_/go?ws=zeta&to=items").status == 404
    finally:
        started.stop()


def test_unknown_and_bad_workspace_names_are_404(
    viewer: Viewer, workspace: Backlog
) -> None:
    (workspace.home.parent / "secret").mkdir()
    for path in (
        "/nope/",
        "/../",
        "/%2e%2e/",
        "/%2e%2e/work/",
        "/ws/../x",
        "/ws/nothing",
    ):
        assert viewer.request(path).status == 404, path
    assert viewer.request("/ws/items/abc").status == 404
    page = viewer.request("/ws/items/99")
    assert page.status == 404 and 'href="/ws/items"' in page.body


def test_only_get_and_head_and_pages_never_write(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = build_demo(workspace)
    workspace.ok_line("add done_one --title 'Done one'")
    workspace.ok_line("2 cancel --reason r")
    before = tree(workspace.home)
    for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS"):
        reply = viewer.request(f"/ws/items/{number}", method)
        assert reply.status == 405 and "GET" in reply.headers["Allow"], method
    assert viewer.request("/ws/", "HEAD").body == ""
    for path in (
        "/ws/",
        "/ws/items",
        f"/ws/items/{number}",
        "/ws/items/2",
        "/ws/archive",
        "/ws/search?q=check&archive=1",
        "/ws/search?q=ch.ck&regex=1",
    ):
        viewer.get(path)
    assert tree(workspace.home) == before  # no file changed, no lock file made


def test_every_request_reads_the_files_again(
    viewer: Viewer, workspace: Backlog
) -> None:
    assert "Nothing needs a decision" in viewer.get("/ws/")
    number = workspace.add_item("work")
    assert "No items match" not in viewer.get("/ws/items")
    workspace.ok_line(f"{number} rename 'Renamed by the CLI'")
    assert "Renamed by the CLI" in viewer.get("/ws/items")
    workspace.ok_line(f"{number} unit add u --kind research")
    workspace.ok_line(f"{number}/u assign --agent A")
    workspace.ok_line(f"{number}/u done --result r --source s")
    page = viewer.get("/ws/")
    assert (
        "all units done" in page
        and "backlog" not in page.split("<main>")[1].split("</main>")[0]
    )


def test_titles_and_briefs_are_escaped_on_every_page(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = workspace.add_item("work")
    workspace.ok(str(number), "rename", XSS_TITLE)
    workspace.ok_line(
        f"{number} brief append --section 'Agent handoff' "
        f"--text '{XSS_TITLE} [x](javascript:alert(1))'"
    )
    workspace.start_item(number)
    workspace.ok(f"{number}/work", "done", "--result", XSS_TITLE, "--source", XSS_TITLE)
    workspace.ok(str(number), "done", "--result", XSS_TITLE, "--source", XSS_TITLE)
    live = workspace.add_item("live")
    workspace.ok(str(live), "rename", XSS_TITLE)
    workspace.add_unit(live, "u", "--kind", "research")
    workspace.ok_line(f"{live}/u assign --agent '{XSS_TITLE}'")
    for path in (
        "/ws/",
        "/ws/items",
        f"/ws/items/{number}",
        f"/ws/items/{live}",
        "/ws/archive",
        "/ws/search?q=script&archive=1",
        "/ws/search?q=script",
    ):
        page = viewer.get(path)
        assert "<script>alert" not in page and "<img" not in page, path
        assert 'href="javascript' not in page, path
    assert "&lt;script&gt;alert(1)" in viewer.get(f"/ws/items/{live}")


def test_the_item_card_state_box_units_and_head(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = build_demo(workspace)
    page = viewer.get(f"/ws/items/{number}")
    main = page.split("<main>")[1].split("</main>")[0]
    assert 'class="parts open"' in main and "Not closed yet" not in main
    assert "ready to close" not in main and 'class="side"' not in main
    assert "<h3>" not in main.split('class="state-split')[1].split("<h2>")[0]
    assert (
        "check check failed" in main and "p99 is 4 s" in main and ">research<" in main
    )
    assert "backlog " not in main
    head = main.split('class="state-split')[0]
    assert '<h1 class="titled"><span class="pill lg c-' in head
    assert "priority" not in head and "created" in head and "updated" in head
    assert 'class="group g-failed"' in viewer.get("/ws/")
    assert 'class="unit-card r-failed" id="u-engine"' in main
    assert 'id="a-engine-check"' in main and 'id="f-engine-check-1"' in main
    assert main.count('class="stop na"') == 6  # two research units, three each
    assert 'class="unit-card r-gone" id="u-gone"' in main and "cancelled" in main
    assert "Corrections:" not in page
    ready = workspace.add_item("ready")
    workspace.finish_units(ready)
    box = viewer.get(f"/ws/items/{ready}").split("<main>")[1]
    assert 'class="parts ready"' in box and "ready to close" in box
    assert "backlog " not in box.split("</main>")[0]
    workspace.ok_line(f"{ready} done --result r --source s")
    archived = viewer.get(f"/ws/items/{ready}")
    assert 'class="parts open"' not in archived
    assert 'class="parts outcome o-done"' in archived


def test_the_state_box_says_in_words_what_is_still_open(
    viewer: Viewer, workspace: Backlog
) -> None:
    empty = workspace.add_item("empty")
    assert "no units yet" in viewer.get(f"/ws/items/{empty}")
    base = workspace.add_item("base")
    waiting = workspace.add_item("waiting", "--depends-on", str(base))
    workspace.add_unit(waiting, "u")
    workspace.ok_line(f"{waiting} block add 'Needs the DBA' --waiting-on DBA")
    page = viewer.get(f"/ws/items/{waiting}")
    assert "not started" in page and "Needs the DBA" in page
    assert '<span class="num blocker-id">b1</span>' in page
    assert 'id="b-1"' in page and "waits for item" not in page
    assert "Waits for</div>" in page and "Blocks</div>" not in page
    rows = re.findall(r'<li class="rowlink"><span class="addr num">.*?</li>', page)
    assert len(rows) == 1 and 'class="slug">base' in rows[0]
    assert rows[0].count('class="main') == 1 and f'href="/ws/items/{base}"' in rows[0]
    merged = workspace.add_merged_unit("shipped")
    assert "waits for release" in viewer.get(f"/ws/items/{merged}")
    gone = workspace.add_item("gone")
    workspace.add_unit(gone, "u", "--kind", "research")
    workspace.ok_line(f"{gone}/u cancel --reason r")
    assert "cancelled" in viewer.get(f"/ws/items/{gone}")
    assert "the item can only be cancelled" in viewer.get(f"/ws/items/{gone}")


def test_every_attention_line_links_to_its_place_in_the_card(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = build_demo(workspace)
    waiting = workspace.add_item("waiting")
    workspace.add_unit(waiting, "u")
    workspace.ok_line(f"{waiting} block add 'Needs the DBA'")
    shipped = workspace.add_merged_unit("shipped")
    attention = viewer.get("/ws/")
    card = f"/ws/items/{number}"
    assert f'<a class="main uname" href="{card}#f-engine-check-1">' in attention
    assert f'href="/ws/items/{waiting}#b-1"' in attention
    assert f'href="/ws/items/{shipped}#u-' in attention
    for target in (
        viewer.get(card),
        viewer.get(f"/ws/items/{waiting}"),
        viewer.get(f"/ws/items/{shipped}"),
    ):
        for anchor in re.findall(r'href="/ws/items/\d+#([^"]+)"', target):
            assert f'id="{anchor}"' in target
    for anchor in re.findall(r'href="/ws/items/(\d+#[^"]+)"', attention):
        number_text, name = anchor.split("#")
        assert f'id="{name}"' in viewer.get(f"/ws/items/{number_text}"), anchor
    for path in ("/ws/", "/ws/items", "/ws/archive", f"/ws/items/{number}"):
        page = viewer.get(path)
        assert not re.search(r"<a [^>]*>(?:(?!</a>).)*<a ", page, re.S), path
    assert 'class="item-head rowlink"' in attention


def test_the_brief_is_markdown_with_raw_html_and_bad_links_defused(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = workspace.add_item("work")
    text = (
        "Some **bold** [bad](javascript:alert(1)) [ok](https://example.com) "
        "<script>alert(1)</script>"
    )
    workspace.ok_line(
        f"{number} brief append --section 'Agent handoff' --text '{text}'"
    )
    workspace.ok_line(
        f"{number} brief append --section 'Scope and exclusions' "
        "--text '| a | b |\n|---|---|\n| 1 | 2 |'"
    )
    page = viewer.get(f"/ws/items/{number}")
    assert "<strong>bold</strong>" in page and 'href="https://example.com"' in page
    assert 'href="javascript' not in page and "<script>alert" not in page
    assert "&lt;script&gt;alert(1)" in page and "<table>" in page


def test_corrections_and_superseded_outcome_are_shown(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.release(f"{number}/engine", "--no-post-release")
    workspace.ok_line(
        f"{number}/engine released --correction 'wrong tag' --at 2026-10-24T12:00:00Z "
        "--source rs --tag v9"
    )
    page = viewer.get(f"/ws/items/{number}")
    assert "Corrections: 1" in page and "<del>" in page and "wrong tag" in page
    other = workspace.add_item("other")
    workspace.ok_line(f"{other} supersede --by {number} --reason 'moved on'")
    card = viewer.get(f"/ws/items/{other}")
    assert f'href="/ws/items/{number}"' in card and "moved on" in card
    assert "superseded by" in viewer.get("/ws/archive")


def test_items_list_filters_and_search(viewer: Viewer, workspace: Backlog) -> None:
    workspace.add_item("back_one", "--tags", "back", "--priority", "low")
    workspace.add_item("front_one", "--tags", "front", "--priority", "high")
    page = viewer.get("/ws/items?tag=back")
    assert "back one" in page and "front one" not in page
    ordered = viewer.get("/ws/items?sort=priority")
    assert ordered.index("front one") < ordered.index("back one")
    assert "No items match" in viewer.get("/ws/items?status=stuck")
    assert 'aria-sort="ascending"><a class="sort asc"' in ordered
    assert 'href="/ws/items?sort=priority&amp;dir=desc"' in ordered
    assert '<a class="hashtag" href="/ws/items?tag=back">#back</a>' in page
    assert 'class="pill p-high">high' in ordered and "priority <b>" not in ordered
    assert "<mark>back</mark>" in viewer.get("/ws/search?q=back")
    assert "Nothing found" in viewer.get("/ws/search?q=zzzz")
    bad = viewer.request("/ws/search?q=(a&regex=1")
    assert bad.status == 200 and "bad regular expression" in bad.body


def test_the_archive_is_searched_only_on_request(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = workspace.add_item("old_thing")
    workspace.finish_item(number)
    assert "Nothing found" in viewer.get("/ws/search?q=old")
    assert "old thing" in viewer.get("/ws/search?q=old&archive=1")


def test_a_slow_regex_stops_at_the_time_limit(
    viewer: Viewer, workspace: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SearchTimeLimit, "SECONDS", 1)
    number = workspace.add_item("work")
    workspace.ok_line(
        f"{number} brief append --section 'Agent handoff' --text '{'a' * 20000}!'"
    )
    page = viewer.get("/ws/search?q=(a|a?)%2B%24&regex=1")
    assert "pattern took longer than 1 s" in page
    assert "wor" in viewer.get("/ws/search?q=wor.&regex=1")


def test_the_archive_file_stays_closed_for_active_pages(
    viewer: Viewer, workspace: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    number = build_demo(workspace)

    def refuse(self: Workspace) -> None:
        raise AssertionError("the archive was opened")

    monkeypatch.setattr(Workspace, "read_archive", refuse)
    for path in ("/ws/", "/ws/items", f"/ws/items/{number}", "/ws/search?q=check"):
        viewer.get(path)
    assert viewer.request("/ws/archive").status == 500


def test_an_unreadable_workspace_is_an_error_page(
    viewer: Viewer, workspace: Backlog, capsys: pytest.CaptureFixture[str]
) -> None:
    workspace.workspace_file("BACKLOG.yaml").write_text("items: [unclosed")
    reply = viewer.request("/ws/")
    assert reply.status == 500 and "<code>ws</code>" in reply.body
    assert "Traceback" not in reply.body
    assert "Traceback" in capsys.readouterr().err


def test_an_interrupted_archive_is_shown_as_the_archive_copy(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = workspace.add_item("work")
    workspace.finish_units(number)
    before_archive = workspace.workspace_file("BACKLOG.yaml").read_text()
    workspace.ok_line(f"{number} done --result r --source s")
    workspace.workspace_file("BACKLOG.yaml").write_text(before_archive)
    workspace.workspace_file(".archiving").write_text("x\n")
    files = tree(workspace.home)
    card = viewer.get(f"/ws/items/{number}")
    assert "Will be recovered by the next CLI command" in card and "done" in card
    assert viewer.get("/ws/items").count("<tr>") == 0
    assert tree(workspace.home) == files


def test_a_newer_schema_is_read_as_the_cli_reads_it(
    viewer: Viewer, workspace: Backlog
) -> None:
    workspace.add_item("work")
    path = workspace.workspace_file("BACKLOG.yaml")
    path.write_text(
        path.read_text().replace("schema_version: 1", "schema_version: 2", 1)
    )
    assert "newer version of backlog" in viewer.get("/ws/")


def test_dates_are_short_and_local_with_the_stored_value_on_hover() -> None:
    year = date.today().year
    assert LocalDate.format(f"{year}-03-05") == "5 Mar"
    assert LocalDate.format(f"{year - 1}-03-05") == f"5 Mar {year - 1}"
    html = LocalDate.html("2026-10-21T23:59:59Z")
    assert 'title="2026-10-21T23:59:59Z"' in html and "Oct" in html


def test_serve_binds_loopback_and_reports_a_busy_port(backlog: Backlog) -> None:
    started = Viewer(backlog.home)
    try:
        assert started.server.server_address[0] == "127.0.0.1"
        port = started.server.server_address[1]
        result = backlog.run("serve", "--port", str(port))
        assert result.code == 2 and "--port" in result.err
        assert "Traceback" not in result.text
        assert backlog.run("serve", "--port", "70000").code == 2
        assert backlog.run("serve", "--host", "0.0.0.0").code == 2
    finally:
        started.stop()


def test_ctrl_c_stops_the_server_with_exit_0(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(self: ViewerServer, *args: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(ViewerServer, "serve_forever", interrupt)
    result = backlog.run("serve", "--port", "0")
    assert result.code == 0 and "http://127.0.0.1:" in result.out
    assert "Traceback" not in result.text


def test_an_idle_socket_does_not_block_other_requests(viewer: Viewer) -> None:
    with socket.create_connection(("127.0.0.1", viewer.port)):
        started = time.monotonic()
        assert viewer.get("/ws/")
        assert time.monotonic() - started < 2


def test_the_page_is_one_centred_column_with_a_theme_switch(
    viewer: Viewer, workspace: Backlog
) -> None:
    page = viewer.get("/ws/")
    assert '<div class="app">' in page and "to right, var(--rail)" not in page
    assert "max-width: 1360px" in page and "~/" not in page
    assert page.count('role="radio"') == 3 and 'role="radiogroup"' in page
    for theme in ("auto", "light", "dark"):
        assert f'data-theme="{theme}"' in page
    head = page.split("</head>")[0]
    assert "localStorage.getItem('backlog-theme')" in head
    assert "<noscript><style>.theme{display:none}" in head
    assert page.count("@media (prefers-color-scheme: dark)") == 1
    assert ':root:not([data-theme="light"])' in page
    assert ':root[data-theme="dark"]' in page
    dark_tokens = page.split("/* dark:begin */")[1].split("/* dark:end */")[0]
    assert page.count(dark_tokens) == 2  # the same tokens, emitted twice


def test_existing_paths_become_links_and_the_rest_stays_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "report.md").write_text("# r")
    folder = tmp_path / "dir"
    folder.mkdir()
    text = (
        f"see {tmp_path}/report.md, then ~/report.md; also {folder}. gone /no/such/file"
    )
    hits = PathLinks.find(text)
    assert [h.absolute for h in hits] == [
        f"{tmp_path}/report.md",
        f"{tmp_path}/report.md",
        str(folder),
    ]
    assert [h.is_dir for h in hits] == [False, False, True]
    html = PathLinks.html(text)
    assert html.count('class="path"') == 3 and "/no/such/file</a>" not in html
    assert html.endswith("/no/such/file")
    assert f"{folder}</a>." in html  # the trailing dot stays outside the link


def test_a_path_in_markdown_text_and_inline_code_links_but_a_block_does_not(
    tmp_path: Path,
) -> None:
    from backlog_cli.serve.item_page import ItemPage

    (tmp_path / "a.md").write_text("x")
    path = f"{tmp_path}/a.md"
    html = ItemPage.render_markdown(f"text {path}\n\n`{path}`\n\n```\n{path}\n```\n")
    assert html.count('class="path"') == 2
    assert f"<pre><code>{path}" in html


def test_a_script_in_a_file_name_is_escaped(tmp_path: Path) -> None:
    name = tmp_path / "a<script>x.md"
    name.write_text("x")
    html = PathLinks.html(f"open {name}")
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_file_preview_of_markdown_text_binary_missing_and_the_1mb_cut(
    viewer: Viewer, tmp_path: Path
) -> None:
    (tmp_path / "r.md").write_text("## Head\n\n**bold** <b>raw</b>")
    (tmp_path / "t.txt").write_text("a < b")
    (tmp_path / "b.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "big.txt").write_text("z" * (1024 * 1024 + 10))
    (tmp_path / "p.png").write_bytes(b"\x89PNG")

    def preview(name: str) -> dict:
        reply = viewer.request(f"/_/file?path={tmp_path}/{name}")
        return {"status": reply.status, **json.loads(reply.body)}

    md = preview("r.md")
    assert md["kind"] == "md" and "<strong>bold</strong>" in md["html"]
    assert "<b>raw</b>" not in md["html"]
    assert "a &lt; b" in preview("t.txt")["html"]
    assert preview("b.bin")["kind"] == "binary"
    assert preview("p.png")["kind"] == "image"
    big = preview("big.txt")
    assert big["note"] == "first 1 MB shown" and big["html"].count("z") == 1024 * 1024
    assert preview("absent.md")["status"] == 404
    raw = viewer.request(f"/_/raw?path={tmp_path}/p.png")
    assert raw.status == 200 and raw.headers["Content-Type"] == "image/png"
    assert viewer.request(f"/_/raw?path={tmp_path}/t.txt").status == 404


def test_a_foreign_host_header_is_refused(viewer: Viewer) -> None:
    reply = viewer.request("/", headers={"Host": f"evil.example:{viewer.port}"})
    assert reply.status == 403
    ok = viewer.request("/", headers={"Host": f"localhost:{viewer.port}"})
    assert ok.status != 403


def test_open_needs_the_viewer_origin_and_an_existing_path(
    viewer: Viewer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        Opener, "open", lambda path, reveal: calls.append((path, reveal))
    )
    target = tmp_path / "f.txt"
    target.write_text("x")
    form = f"path={target}&reveal=1"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    for origin in (None, "http://evil.example", "http://localhost:1"):
        extra = headers | ({"Origin": origin} if origin else {})
        assert viewer.request("/_/open", "POST", extra, form).status == 403
    assert calls == []
    own = headers | {"Origin": f"http://127.0.0.1:{viewer.port}"}
    missing = viewer.request("/_/open", "POST", own, "path=/no/such/f&reveal=0")
    assert missing.status == 404 and calls == []
    assert viewer.request("/_/open", "POST", own, form).status == 200
    assert calls == [(str(target), True)]


def test_a_bare_top_level_folder_and_dots_after_a_path_are_not_linked() -> None:
    assert PathLinks.find("see /usr and /private, /tmp/ and /usr/...") == []
    assert PathLinks.find("a /usr/... b") == []


def test_the_slug_is_shown_next_to_the_number_on_every_page(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = workspace.add_item("slug_one", "--tags", "back")
    card = viewer.get(f"/ws/items/{number}")
    assert f'<span class="addr">{number}</span> · <span class="slug">slug_one' in card
    assert card.count('class="slug">slug_one') == 2  # crumbs and the meta line
    for path in ("/ws/items", "/ws/search?q=slug"):
        assert 'class="slug">slug_one' in viewer.get(path), path
    workspace.ok_line(f"{number} cancel --reason r")
    assert 'class="slug">slug_one' in viewer.get("/ws/archive")
    build_demo(workspace)
    assert 'class="slug">' in viewer.get("/ws/")


def test_external_links_open_in_a_new_tab_and_the_ui_is_english(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = build_demo(workspace)
    workspace.ok_line(
        f"{number} brief append --section 'Agent handoff' "
        "--text 'See [docs](https://example.com/a) and [card](/ws/items/1)'"
    )
    page = viewer.get(f"/ws/items/{number}")
    assert (
        '<a href="https://example.com/a" target="_blank" rel="noopener noreferrer">'
        in page
    )
    assert '<a href="/ws/items/1">card</a>' in page
    assert re.search(
        r'<a href="https://github.com/[^"]+" class="addr" target="_blank"', page
    )
    for path in ("/ws/", "/ws/items", "/ws/archive", "/ws/search?q=a", "/nope/"):
        text = viewer.request(path).body
        assert '<html lang="en">' in text and "Бриф" not in text, path
        assert not re.search("[А-Яа-яЁё]", text), path
    assert "<h2>Brief</h2>" not in page


def test_a_research_route_runs_through_the_skipped_stations(
    viewer: Viewer, workspace: Backlog
) -> None:
    number = workspace.add_item("study")
    workspace.add_unit(number, "r", "--kind", "research")
    workspace.ok_line(f"{number}/r assign --agent A")
    wip = viewer.get(f"/ws/items/{number}")
    assert wip.count('class="stop na"') == 3 and 'class="lbl">—<' not in wip
    assert '<span class="lbl">Released</span>' in wip
    workspace.ok_line(f"{number}/r done --result r --source s")
    done = viewer.get(f"/ws/items/{number}")
    assert done.count('class="stop na on"') == 3


def test_rail_filters_and_sortable_headers_keep_each_other(
    viewer: Viewer, workspace: Backlog
) -> None:
    workspace.add_item("back_one", "--tags", "back,perf", "--priority", "low")
    workspace.add_item("front_one", "--tags", "front,perf", "--priority", "high")
    workspace.start_item(workspace.add_item("busy", "--tags", "back"))
    page = viewer.get("/ws/items")
    rail = page.split('class="f-wide"')[1].split('class="f-narrow"')[0]
    assert (
        'href="/ws/items?status=todo"' in rail and 'href="/ws/items?status=wip"' in rail
    )
    assert 'href="/ws/items?tag=perf"' in rail and 'class="n">2' in rail
    assert rail.index("#back") < rail.index("#front")  # by count, then by name
    both = viewer.get("/ws/items?status=todo&tag=perf&sort=priority&dir=desc")
    assert both.count('class="rowlink"><td class="addr">') == 2
    rail = both.split('class="f-wide"')[1].split('class="f-narrow"')[0]
    assert "#perf</a>" in rail and 'class="n">' in rail
    assert "#perf<span" not in rail  # a tag chip has no count
    assert 'aria-current="true"' in rail and ">Clear filters<" in rail
    assert 'aria-sort="descending"' in both
    assert (
        'href="/ws/items?status=todo&amp;tag=perf&amp;sort=priority&amp;dir=asc"'
        in both
    )
    plain_rail = page.split('class="f-wide"')[1].split('class="f-narrow"')[0]
    assert (
        ">Clear filters<" not in plain_rail and 'aria-current="true"' not in plain_rail
    )
    assert '<th aria-sort="ascending"><a class="sort asc"' in page
    assert "<h1>All items \u00b7 2</h1>" in both and "<h1>All items</h1>" in page
    archive = viewer.get("/ws/archive")
    assert "<h1>Archive</h1>" in archive and 'class="f-wide"' in archive


def ws_counts(page: str, name: str) -> list[str]:
    """The numbers shown in the rail row of one workspace."""
    row = re.search(rf'<a class="ws-row" href="/{name}/">(.*?)</a>', page).group(1)
    return re.findall(r'<span class="count"[^>]*>(\d+)</span>', row)


def test_closed_workspace_rows_show_their_attention_count(
    viewer: Viewer, workspace: Backlog
) -> None:
    build_demo(workspace)
    workspace.add_item("plain")
    (workspace.work / "z").mkdir()
    workspace.ok("bind", "zeta", "--dir", str(workspace.work / "z"))
    (workspace.work / "o").mkdir()
    workspace.ok("bind", "omega", "--dir", str(workspace.work / "o"))
    for slug in ("one", "two", "three"):
        workspace.ok("--workspace", "zeta", "add", slug, "--title", slug)
    workspace.ok("--workspace", "zeta", "1", "cancel", "--reason", "x")
    workspace.workspace_file("ARCHIVE.yaml", "zeta").write_text("not yaml: [")
    for path in ("/ws/", "/ws/items/1"):
        page = viewer.get(path)
        assert ws_counts(page, "ws") == []  # open: its pages show the counts
        assert ws_counts(page, "zeta") == [
            "4"
        ]  # two items: can start and empty brief each
        assert ws_counts(page, "omega") == []  # no attention: no number
    page = viewer.get("/zeta/items")
    assert ws_counts(page, "zeta") == []
    assert ws_counts(page, "ws") == ["4"]  # failed check, can start, two empty briefs
    workspace.workspace_file("BACKLOG.yaml", "zeta").write_text("items: [unclosed")
    assert ws_counts(viewer.get("/ws/"), "zeta") == []


def build_one_item_per_stage(workspace: Backlog) -> None:
    """Numbers 1-6: todo, wip, merged, post_release, ready to close, a second wip."""
    workspace.add_item("todo_item", "--tags", "back")
    workspace.start_item(workspace.add_item("wip_item", "--tags", "back"))
    workspace.add_merged_unit("merged_item")
    post = workspace.add_merged_unit("post_item")
    workspace.add_check(post, "check")
    workspace.release(f"{post}/engine")
    workspace.finish_units(workspace.add_item("ready_item"))
    workspace.start_item(workspace.add_item("wip_two"))


def listed_numbers(page: str) -> list[int]:
    return [
        int(n) for n in re.findall(r'class="rowlink"><td class="addr">(\d+)<', page)
    ]


def test_all_items_are_sorted_by_readiness_by_default(
    viewer: Viewer, workspace: Backlog
) -> None:
    build_one_item_per_stage(workspace)
    assert listed_numbers(viewer.get("/ws/items")) == [5, 4, 3, 2, 6, 1]
    reversed_page = viewer.get("/ws/items?sort=readiness&dir=desc")
    assert listed_numbers(reversed_page) == [1, 6, 2, 3, 4, 5]
    assert '<th aria-sort="descending"><a class="sort desc"' in reversed_page
    assert listed_numbers(viewer.get("/ws/items?sort=number")) == [1, 2, 3, 4, 5, 6]
    filtered = viewer.get("/ws/items?tag=back")
    assert listed_numbers(filtered) == [2, 1]
    assert 'href="/ws/items?tag=back&amp;sort=readiness&amp;dir=desc"' in filtered
    assert 'href="/ws/items?tag=back&amp;sort=title&amp;dir=asc"' in filtered


def test_the_stage_follows_the_least_advanced_open_unit(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("mixed")
    registry = Workspace.open(workspace.home, "ws").load_registry()
    item = registry.find_item(number).item
    assert item.readiness == Readiness.MERGED
    workspace.add_unit(number, "other")
    registry = Workspace.open(workspace.home, "ws").load_registry()
    assert registry.find_item(number).item.readiness == Readiness.WIP


def test_a_shared_pr_links_to_the_other_units_on_the_card(
    viewer: Viewer, workspace: Backlog
) -> None:
    first = workspace.add_merged_unit("one", pr_number=5)
    second = workspace.add_item("two")
    workspace.add_unit(second, "fix")
    workspace.ok_line(f"{second}/fix link pr acme/api#5")
    card = viewer.get(f"/ws/items/{second}")
    assert (
        f'<span class="who">shared with <a href="/ws/items/{first}#u-engine">'
        f"{first}/engine</a></span>" in card
    )
    assert "shared with" in viewer.get(f"/ws/items/{first}")
    workspace.ok_line(f"{second}/fix link pr acme/api#6")
    assert "shared with" not in viewer.get(f"/ws/items/{second}")
