"""`search`: words (or one regular expression) over the fields and details of items."""

import re
import shlex
import signal
from dataclasses import dataclass

from tap import Positional

from backlog_cli.command.base import CommandParser, WorkspaceCommand
from backlog_cli.domain.details_file import DetailsFile
from backlog_cli.domain.item import Item
from backlog_cli.errors import UsageError
from backlog_cli.store.registry import ItemLocation, Registry
from backlog_cli.store.workspace import Workspace


class SearchParser(CommandParser):
    query: Positional[list[str]]  # Words; an item must contain every one of them.
    regex: bool = False  # Read the query as one regular expression.
    archive: bool = False  # Also search archived items.
    case_sensitive: bool = False  # Match case (default: ignore case).

    def configure(self) -> None:
        super().configure()
        self.add_argument("query", nargs="+", metavar="WORD")
        self.add_argument(
            "-E",
            "--regex",
            action="store_true",
            help="Read the query as one Python regular expression",
        )


@dataclass(frozen=True)
class SearchMatch:
    where: str
    context: str


@dataclass(frozen=True)
class SearchLine:
    where: str
    text: str


@dataclass(frozen=True)
class ItemMatch:
    item: Item
    is_archived: bool
    matches: list[SearchMatch]


class SearchTimeLimit:
    """Run a regular-expression search for at most SECONDS seconds.

    shortcut: SIGALRM only (no Windows), a portable limit needs the regex module
    (it has a timeout; Python `re` has none).
    """

    SECONDS = 5

    def __enter__(self) -> "SearchTimeLimit":
        self._old_handler = signal.signal(signal.SIGALRM, self._stop)
        signal.setitimer(signal.ITIMER_REAL, self.SECONDS)
        return self

    def __exit__(self, *error: object) -> None:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self._old_handler)

    @classmethod
    def _stop(cls, signal_number: int, frame: object) -> None:
        raise UsageError(f"pattern took longer than {cls.SECONDS} s; simplify it")


class QueryMatcher:
    """Plain words (every one must occur somewhere in the item) or one regex."""

    REGEX_CHARACTERS = ".*+?()[]|^$\\"

    def __init__(self, query: str, is_regex: bool, is_case_sensitive: bool) -> None:
        self.query = query
        self.is_regex = is_regex
        self.is_case_sensitive = is_case_sensitive
        flags = 0 if is_case_sensitive else re.IGNORECASE
        self.words = [] if is_regex else query.split()
        self.pattern = re.compile(query, flags) if is_regex else None
        if not is_regex:
            self.word_patterns = [
                re.compile(re.escape(word), flags) for word in self.words
            ]

    @classmethod
    def build(
        cls, query: str, is_regex: bool, is_case_sensitive: bool
    ) -> "QueryMatcher":
        try:
            return cls(query, is_regex, is_case_sensitive)
        except re.error as error:
            raise UsageError(f"bad regular expression {query!r}: {error}") from None

    def is_hit(self, text: str) -> bool:
        if self.pattern is not None:
            return bool(self.pattern.search(text))
        return any(pattern.search(text) for pattern in self.word_patterns)

    def find_hits(self, lines: list[SearchLine]) -> list[SearchLine]:
        """The hit lines, or none when the item does not hold every word."""
        hits = [line for line in lines if self.is_hit(line.text)]
        if self.pattern is not None:
            return hits
        whole = "\n".join(line.text for line in lines)
        if all(pattern.search(whole) for pattern in self.word_patterns):
            return hits
        return []

    def find_spans(self, text: str) -> list[tuple[int, int]]:
        """Where the query hits the text, as sorted, non-overlapping (start, end)."""
        patterns = [self.pattern] if self.pattern is not None else self.word_patterns
        spans = sorted(
            match.span()
            for pattern in patterns
            for match in pattern.finditer(text)
            if match.end() > match.start()
        )
        merged: list[tuple[int, int]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return merged

    def has_regex_characters(self) -> bool:
        return any(character in self.query for character in self.REGEX_CHARACTERS)


class SearchCommand(WorkspaceCommand):
    NAME = "search"
    SUMMARY = "Search items and details for words, or one regular expression."
    SERVICE_FIELDS = (
        "id",
        "status",
        "kind",
        "next_blocker_id",
        "known_units",
        "subject",
        "outcome",
    )
    MATCHES_PER_ITEM = 5
    CONTEXT_WIDTH = 100
    MAX_QUERY_LENGTH = 200
    PLAIN_TEXT_HINT = "searched as plain text; for a regular expression add --regex"
    USAGE = "backlog search WORD [WORD ...] [--regex] [--archive] [--case-sensitive]"
    EXAMPLES = (
        "Examples:\n"
        "  backlog search timeout deadlock      (items with both words)\n"
        "  backlog search --regex 'timeout|deadlock' --archive"
    )
    Parser = SearchParser

    def run(self, args: SearchParser) -> int:
        query = " ".join(args.query)
        if not query.strip():
            raise UsageError("query must not be empty")
        if len(query) > self.MAX_QUERY_LENGTH:
            raise UsageError(
                f"the query is {len(query)} characters long; "
                f"at most {self.MAX_QUERY_LENGTH}"
            )
        matcher = QueryMatcher.build(query, args.regex, args.case_sensitive)
        if args.regex:
            with SearchTimeLimit():
                return self._search(args, matcher)
        return self._search(args, matcher)

    def _search(self, args: SearchParser, matcher: QueryMatcher) -> int:
        workspace = self.open_workspace(args)
        registry = workspace.load_registry()
        searched = [ItemLocation(item, is_archived=False) for item in registry.active]
        if args.archive:
            searched += [
                ItemLocation(item, is_archived=True) for item in registry.archived
            ]
        item_matches = []
        for location in sorted(searched, key=lambda found: found.item.number):
            matches = self.find_matches(matcher, location.item, workspace)
            if matches:
                item_matches.append(
                    ItemMatch(location.item, location.is_archived, matches)
                )
        if not item_matches and not args.archive:
            self._print_archive_hint(matcher, registry, args, workspace)
            return 0
        self._print_matches(item_matches)
        if not item_matches and not args.regex and matcher.has_regex_characters():
            self.print_lines(self.PLAIN_TEXT_HINT)
        return 0

    def _print_archive_hint(
        self,
        matcher: QueryMatcher,
        registry: Registry,
        args: SearchParser,
        workspace: Workspace,
    ) -> None:
        archived_count = sum(
            1
            for item in registry.archived
            if self.find_matches(matcher, item, workspace)
        )
        self.print_lines("No matches")
        if archived_count:
            regex_flag = " --regex" if args.regex else ""
            self.print_lines(
                f"{archived_count} archived items match. Search the archive: "
                f"backlog search{regex_flag} {shlex.quote(matcher.query)} --archive"
            )
        elif not args.regex and matcher.has_regex_characters():
            self.print_lines(self.PLAIN_TEXT_HINT)

    @classmethod
    def find_matches(
        cls,
        matcher: QueryMatcher,
        item: Item,
        workspace: Workspace,
    ) -> list[SearchMatch]:
        lines = [
            SearchLine(f"registry {field.path}", field.text)
            for field in item.walk_fields()
            if not cls._is_service_field(field.path)
        ]
        for line in DetailsFile.read_lines(workspace.read_details(item.id)):
            # The managed title line repeats the registry id and title.
            if line.section is not None:
                where = f"details {line.section}, line {line.number}"
                lines.append(SearchLine(where, line.text.strip()))
        return [
            SearchMatch(hit.where, cls._shorten(hit.text))
            for hit in matcher.find_hits(lines)
        ]

    @classmethod
    def _is_service_field(cls, path: str) -> bool:
        """Ids, statuses, kinds and moments: a pattern like `^2026` or `.*` must
        not hit them; they are not text anyone wrote.
        """
        name = path.rsplit(".", 1)[-1].split("[")[0]
        return name in cls.SERVICE_FIELDS or name == "at" or name.endswith("_at")

    @classmethod
    def _shorten(cls, text: str) -> str:
        if len(text) <= cls.CONTEXT_WIDTH:
            return text
        return text[: cls.CONTEXT_WIDTH] + "..."

    def _print_matches(self, item_matches: list[ItemMatch]) -> None:
        if not item_matches:
            self.print_lines("No matches")
            return
        noun = "item matches" if len(item_matches) == 1 else "items match"
        self.print_lines(f"{len(item_matches)} {noun}.")
        for entry in item_matches:
            self.print_lines(*self._format_item(entry))

    def _format_item(self, entry: ItemMatch) -> list[str]:
        archive_note = (
            f"  [archive: {entry.item.completion.outcome}]" if entry.is_archived else ""
        )
        lines = [
            f"{entry.item.number}  {entry.item.status}  "
            f"{entry.item.title}{archive_note}"
        ]
        shown = entry.matches[: self.MATCHES_PER_ITEM]
        lines += [f"    {match.where}: {match.context}" for match in shown]
        hidden = len(entry.matches) - len(shown)
        if hidden:
            lines.append(f"    +{hidden} more")
        return lines
