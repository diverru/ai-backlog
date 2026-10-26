"""What a page is built from: the data of one workspace read for this request."""

from dataclasses import dataclass
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from urllib.parse import urlencode

from backlog_cli.domain.attention import AttentionRow, AttentionRows
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.vocabulary import AttentionGroup
from backlog_cli.serve.text import HtmlText
from backlog_cli.store.registry import Registry
from backlog_cli.store.workspace import Workspace


class NavSection(StrEnum):
    """The rail entries; the value is the path after the workspace name."""

    ATTENTION = ""
    ITEMS = "items"
    ARCHIVE = "archive"
    SEARCH = "search"


@dataclass(frozen=True)
class ItemFilter:
    """What the Items page was asked for; the rail and the sort links keep it."""

    status: str = ""
    tag: str = ""
    sort: str = ""
    direction: str = ""

    def query(self, **changes: str) -> str:
        """`?status=wip&tag=back`, with `changes` applied; empty values drop out."""
        values = {
            "status": self.status,
            "tag": self.tag,
            "sort": self.sort,
            "dir": self.direction,
        } | changes
        pairs = {name: value for name, value in values.items() if value}
        return f"?{urlencode(pairs)}" if pairs else ""


@dataclass
class PageContent:
    title: str
    body: str
    section: NavSection = NavSection.ATTENTION
    filter: ItemFilter = ItemFilter()


@dataclass
class WorkspaceView:
    home: Path
    workspace: Workspace
    registry: Registry

    @property
    def name(self) -> str:
        return self.workspace.name

    @cached_property
    def situations(self) -> list[ItemSituation]:
        return [self.registry.get_situation(item) for item in self.registry.active]

    @cached_property
    def attention(self) -> dict[AttentionGroup, list[AttentionRow]]:
        return AttentionRows.collect(self.situations)

    @property
    def attention_count(self) -> int:
        return sum(len(rows) for rows in self.attention.values())

    @property
    def archived_count(self) -> int:
        """From BACKLOG.yaml, so the archive file stays closed."""
        return len(self.registry.archived_item_ids)

    def crumbs(self, *trail: str) -> str:
        """The path above the title: the workspace, then each HTML piece of `trail`."""
        home = f'<a href="{self.url()}">{HtmlText.esc(self.name)}</a>'
        return f'<div class="crumbs">{" / ".join([home, *trail])}</div>'

    def url(self, path: str = "") -> str:
        return f"/{self.name}/{path}"

    def card_url(self, number: int, anchor: str = "") -> str:
        """The card of an item, at an anchor of it when there is one."""
        return self.url(f"items/{number}") + (f"#{anchor}" if anchor else "")
