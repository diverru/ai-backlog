"""`/<ws>/search`: the CLI search, with the matched text marked."""

from dataclasses import dataclass

from backlog_cli.command.search import QueryMatcher, SearchCommand, SearchTimeLimit
from backlog_cli.errors import UsageError
from backlog_cli.serve.text import HtmlText
from backlog_cli.serve.view import NavSection, PageContent, WorkspaceView
from backlog_cli.store.registry import ItemLocation


@dataclass(frozen=True)
class HitLine:
    where: str
    context_html: str


@dataclass(frozen=True)
class ItemHit:
    number: int
    slug: str
    title: str
    outcome: str | None  # the archive outcome; None for an active item
    lines: list[HitLine]
    hidden: int


class SearchPage:
    LINES_PER_ITEM = SearchCommand.MATCHES_PER_ITEM

    @classmethod
    def build(cls, view: WorkspaceView, params: dict[str, str]) -> PageContent:
        query = params.get("q", "").strip()
        is_regex = params.get("regex") == "1"
        in_archive = params.get("archive") == "1"
        body = [
            view.crumbs("<span>Search</span>"),
            "<h1>Search</h1>",
            cls._render_form(view, query, is_regex, in_archive),
        ]
        if query:
            body.append(cls._render_result(view, query, is_regex, in_archive))
        return PageContent("Search", "\n".join(body), NavSection.SEARCH)

    @staticmethod
    def _render_form(
        view: WorkspaceView, query: str, is_regex: bool, in_archive: bool
    ) -> str:
        def checked(flag: bool) -> str:
            return " checked" if flag else ""

        return (
            f'<form class="filters" action="{view.url("search")}" method="get">'
            f'<input type="search" name="q" value="{HtmlText.esc(query)}" '
            'aria-label="Query" placeholder="Words or a regular expression">'
            f'<label><input type="checkbox" name="regex" value="1"{checked(is_regex)}> '
            "regex</label>"
            f'<label><input type="checkbox" name="archive" value="1"'
            f"{checked(in_archive)}> and archive</label>"
            '<button type="submit">Search</button></form>'
        )

    @classmethod
    def _render_result(
        cls, view: WorkspaceView, query: str, is_regex: bool, in_archive: bool
    ) -> str:
        try:
            hits = cls._search(view, query, is_regex, in_archive)
        except UsageError as error:
            return f'<div class="error panel"><p>{HtmlText.esc(error)}</p></div>'
        if not hits:
            hint = ""
            if (
                not is_regex
                and QueryMatcher(query, False, False).has_regex_characters()
            ):
                hint = (
                    " The query was searched as plain text; "
                    "tick regex for a regular expression."
                )
            return f'<p class="empty-state">Nothing found.{hint}</p>'
        count = HtmlText.plural(len(hits), "item", "items")
        groups = "".join(cls._render_hit(view, hit) for hit in hits)
        return f'<div class="meta"><span>found: {count}</span></div>{groups}'

    @classmethod
    def _search(
        cls, view: WorkspaceView, query: str, is_regex: bool, in_archive: bool
    ) -> list[ItemHit]:
        if len(query) > SearchCommand.MAX_QUERY_LENGTH:
            raise UsageError(
                f"the query is {len(query)} characters long; "
                f"at most {SearchCommand.MAX_QUERY_LENGTH}"
            )
        matcher = QueryMatcher.build(query, is_regex, False)
        if not is_regex:
            return cls._collect(view, matcher, in_archive)
        with SearchTimeLimit():
            return cls._collect(view, matcher, in_archive)

    @classmethod
    def _collect(
        cls, view: WorkspaceView, matcher: QueryMatcher, in_archive: bool
    ) -> list[ItemHit]:
        registry = view.registry
        searched = [ItemLocation(item, False) for item in registry.active]
        if in_archive:
            searched += [ItemLocation(item, True) for item in registry.archived]
        hits = []
        for location in sorted(searched, key=lambda found: found.item.number):
            item = location.item
            matches = SearchCommand.find_matches(matcher, item, view.workspace)
            if not matches:
                continue
            lines = [
                HitLine(match.where, cls._mark(matcher, match.context))
                for match in matches[: cls.LINES_PER_ITEM]
            ]
            outcome = str(item.completion.outcome) if location.is_archived else None
            hits.append(
                ItemHit(
                    item.number,
                    item.slug,
                    item.title,
                    outcome,
                    lines,
                    len(matches) - len(lines),
                )
            )
        return hits

    @staticmethod
    def _mark(matcher: QueryMatcher, text: str) -> str:
        pieces, position = [], 0
        for start, end in matcher.find_spans(text):
            pieces.append(HtmlText.esc(text[position:start]))
            pieces.append(f"<mark>{HtmlText.esc(text[start:end])}</mark>")
            position = end
        pieces.append(HtmlText.esc(text[position:]))
        return "".join(pieces)

    @staticmethod
    def _render_hit(view: WorkspaceView, hit: ItemHit) -> str:
        esc = HtmlText.esc
        href = view.url(f"items/{hit.number}")
        outcome = (
            f'<span class="chip">archive: {esc(hit.outcome)}</span>'
            if hit.outcome
            else ""
        )
        lines = "".join(
            f'<li><code class="where">{esc(line.where)}</code>'
            f'<span class="ctx">{line.context_html}</span></li>'
            for line in hit.lines
        )
        more = f'<li class="sub">and {hit.hidden} more</li>' if hit.hidden else ""
        return (
            f'<section class="group rowlink"><h2><span class="addr">{hit.number}</span>'
            f'<a class="title main" href="{href}">{esc(hit.title)}</a>'
            f'<span class="slug">{esc(hit.slug)}</span>{outcome}</h2>'
            f'<ul class="rows panel hits">{lines}{more}</ul></section>'
        )
