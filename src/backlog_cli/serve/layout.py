"""The shell of every page: the rail and the main column, with the CSS inlined."""

from pathlib import Path
from urllib.parse import quote

from backlog_cli.serve.rail_filters import RailFilters
from backlog_cli.serve.text import HtmlText
from backlog_cli.serve.view import NavSection, PageContent, WorkspaceView


class PageLayout:
    ICON = (
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">{}</svg>'
    )
    ICONS = {
        NavSection.ATTENTION: ICON.format(
            '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/>'
            '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>'
        ),
        NavSection.ITEMS: ICON.format(
            '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>'
        ),
        NavSection.ARCHIVE: ICON.format('<path d="M21 8v13H3V8M1 3h22v5H1zM10 12h4"/>'),
    }
    # an amber tile with list bars, to tell the tab apart from others
    FAVICON = (
        "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Crect width='32' height='32' rx='8' fill='%23f2a900'/%3E"
        "%3Cg stroke='%231a1a1f' stroke-width='3.5' stroke-linecap='round'%3E"
        "%3Cpath d='M9 10h14M9 16h10M9 22h6'/%3E%3C/g%3E%3C/svg%3E"
    )
    SEARCH_ICON = (
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'aria-hidden="true"><circle cx="11" cy="11" r="7"/>'
        '<path d="m21 21-4.3-4.3"/></svg>'
    )
    NAV_LABELS = {
        NavSection.ATTENTION: "Attention",
        NavSection.ITEMS: "All items",
        NavSection.ARCHIVE: "Archive",
    }

    def __init__(self, css: str) -> None:
        self.css = css

    @classmethod
    def read_css(cls) -> str:
        """The stylesheet, with the dark tokens repeated for the system theme."""
        css = (Path(__file__).parent / "viewer.css").read_text(encoding="utf-8")
        begin, end = css.index("/* dark:begin */"), css.index("/* dark:end */")
        dark = css[begin:end]
        return (
            f"{css}\n@media (prefers-color-scheme: dark) {{\n"
            f':root:not([data-theme="light"]) {{\n{dark}}}\n}}\n'
        )

    HEAD_SCRIPT = (
        "try{var t=localStorage.getItem('backlog-theme');"
        "if(t==='light'||t==='dark')document.documentElement.dataset.theme=t}"
        "catch(e){}"
    )
    SWITCH_SCRIPT = """\
(function () {
  var buttons = document.querySelectorAll('.theme button');
  var root = document.documentElement;
  function show() {
    var now = root.dataset.theme || 'auto';
    buttons.forEach(function (b) {
      b.setAttribute('aria-checked', String(b.dataset.theme === now));
    });
  }
  buttons.forEach(function (b) {
    b.addEventListener('click', function () {
      var theme = b.dataset.theme;
      if (theme === 'auto') delete root.dataset.theme;
      else root.dataset.theme = theme;
      try {
        if (theme === 'auto') localStorage.removeItem('backlog-theme');
        else localStorage.setItem('backlog-theme', theme);
      } catch (e) {}
      show();
    });
  });
  show();
})();"""
    PREVIEW_MARKUP = """\
<dialog id="preview" aria-label="Preview">
  <div class="pv-head"><span class="pv-title"></span>
    <button type="button" class="pv-close" aria-label="Close">×</button></div>
  <div class="pv-body"></div>
  <div class="pv-foot"><span class="pv-note"></span>
    <button type="button" data-act="open">Open</button>
    <button type="button" data-act="reveal">Show in Finder</button>
    <button type="button" data-act="copy">Copy path</button></div>
</dialog>
<div id="dirmenu" popover>
  <button type="button" data-act="open">Open in Finder</button>
  <button type="button" data-act="copy">Copy path</button>
</div>"""
    PREVIEW_SCRIPT = """\
(function () {
  var dialog = document.getElementById('preview');
  var menu = document.getElementById('dirmenu');
  if (!dialog.showModal || !menu.showPopover) return;
  var current = '';
  function send(reveal) {
    fetch('/_/open', {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: 'path=' + encodeURIComponent(current) + '&reveal=' + reveal
    });
  }
  function copy(button) {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(current).then(function () {
      var label = button.textContent;
      button.textContent = 'Copied';
      setTimeout(function () { button.textContent = label; }, 1500);
    });
  }
  function preview(path) {
    var body = dialog.querySelector('.pv-body');
    current = path;
    dialog.querySelector('.pv-title').textContent = path;
    dialog.querySelector('.pv-note').textContent = '';
    body.textContent = 'Loading…';
    if (!dialog.open) dialog.showModal();
    fetch('/_/file?path=' + encodeURIComponent(path))
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (current !== path) return;
        if (data.error) body.textContent = data.error;
        else body.innerHTML = data.html;  // a fragment the server escaped
        dialog.querySelector('.pv-note').textContent = data.note || '';
      });
  }
  function openMenu(link) {
    var box = link.getBoundingClientRect();
    (dialog.contains(link) ? dialog : document.body).appendChild(menu);
    menu.style.top = box.bottom + 4 + 'px';
    menu.style.left = box.left + 'px';
    menu.showPopover();
  }
  document.addEventListener('click', function (event) {
    var link = event.target.closest('a.path');
    var action = event.target.closest('[data-act]');
    if (link) {
      event.preventDefault();
      current = link.dataset.path;
      if (link.dataset.kind === 'dir') openMenu(link); else preview(current);
    } else if (action) {
      if (action.dataset.act === 'copy') copy(action);
      else send(action.dataset.act === 'reveal' ? 1 : 0);
    } else if (event.target === dialog || event.target.closest('.pv-close')) {
      dialog.close();
    }
  });
})();"""
    ROW_SCRIPT = """\
(function () {
  function follow(event) {
    var row = event.target.closest('.rowlink');
    if (!row) return;
    // a drag that selected text is a selection, not a click
    if (!window.getSelection().isCollapsed) return;
    if (event.target.closest('a, button, input, select, label')) return;
    var link = row.querySelector('a.main');
    if (!link) return;
    var aside = event.button === 1 || event.ctrlKey || event.metaKey;
    if (event.button > 1) return;
    if (aside) window.open(link.href, '_blank', 'noopener');
    else location.href = link.href;
  }
  document.addEventListener('click', function (e) { if (e.button === 0) follow(e); });
  document.addEventListener('auxclick', function (e) {
    if (e.button === 1) follow(e);
  });
})();"""
    THEMES = (("auto", "Auto"), ("light", "Light"), ("dark", "Dark"))

    def render(
        self,
        content: PageContent,
        names: list[str],
        view: WorkspaceView | None,
    ) -> str:
        esc = HtmlText.esc
        where = f" — {esc(view.name)}" if view else ""
        return (
            '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{esc(content.title)}{where} — backlog</title>\n"
            f'<link rel="icon" href="{self.FAVICON}">\n'
            f"<script>{self.HEAD_SCRIPT}</script>\n"
            "<noscript><style>.theme{display:none}</style></noscript>\n"
            f"<style>\n{self.css}\n</style>\n</head>\n<body>\n"
            '<div class="app">\n'
            f"{self._render_rail(content, names, view)}\n"
            f"<main>\n{content.body}\n</main>\n</div>\n"
            f"{self.PREVIEW_MARKUP}\n"
            f"<script>\n{self.SWITCH_SCRIPT}\n{self.PREVIEW_SCRIPT}\n{self.ROW_SCRIPT}\n</script>\n"
            "</body>\n</html>\n"
        )

    def _render_rail(
        self,
        content: PageContent,
        names: list[str],
        view: WorkspaceView | None,
    ) -> str:
        top = ['<div class="brand">backlog<span>.</span></div>']
        mid = []
        if view is not None:
            top.append(self._render_search(view))
        if names:
            mid.append(self._render_workspaces(content, names, view))
        if view is not None:
            mid.append(RailFilters.render(view, content.filter))
        return (
            '<nav class="rail" aria-label="Navigation">'
            f'<div class="rail-top">{"".join(top)}</div>'
            f'<div class="rail-mid">{"".join(mid)}</div>'
            f"{self._render_theme_switch()}</nav>"
        )

    @classmethod
    def _render_theme_switch(cls) -> str:
        buttons = "".join(
            f'<button type="button" role="radio" data-theme="{value}" '
            f'aria-checked="{"true" if value == "auto" else "false"}">{label}</button>'
            for value, label in cls.THEMES
        )
        return (
            f'<div class="theme" role="radiogroup" aria-label="Theme">{buttons}</div>'
        )

    def _render_workspaces(
        self, content: PageContent, names: list[str], view: WorkspaceView | None
    ) -> str:
        """Every workspace is a row; the current one lists its pages under it."""
        esc = HtmlText.esc
        rows = []
        for name in names:
            row = f'<a class="ws-row" href="/{quote(name)}/">{esc(name)}</a>'
            if view is not None and name == view.name:
                rows.append(
                    f'<div class="ws-item current">{row}'
                    f"{self._render_pages(content, view)}</div>"
                )
            else:
                rows.append(f'<div class="ws-item">{row}</div>')
        return f'<div class="rail-label first">Workspaces</div>{"".join(rows)}'

    def _render_pages(self, content: PageContent, view: WorkspaceView) -> str:
        counts = {
            NavSection.ATTENTION: view.attention_count,
            NavSection.ITEMS: len(view.registry.active),
            NavSection.ARCHIVE: view.archived_count,
        }
        links = []
        for section, label in self.NAV_LABELS.items():
            current = ' aria-current="page"' if section == content.section else ""
            quiet = (
                "" if section == NavSection.ATTENTION and counts[section] else " quiet"
            )
            links.append(
                f'<li><a class="pg" href="{view.url(section)}"{current}>'
                f"{self.ICONS[section]}{label}"
                f'<span class="count{quiet}">{counts[section]}</span></a></li>'
            )
        return f'<ul class="ws-pages">{"".join(links)}</ul>'

    @staticmethod
    def _render_search(view: WorkspaceView) -> str:
        return (
            f'<form class="search" role="search" action="{view.url("search")}" '
            f'method="get">{PageLayout.SEARCH_ICON}'
            '<input type="search" name="q" placeholder="Search" '
            'aria-label="Search"></form>'
        )
