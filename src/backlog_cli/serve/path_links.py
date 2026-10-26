"""Paths in data texts: an existing file or folder becomes a link the page can
preview or open. A path that does not exist stays plain text.
"""

import os
import re
from dataclasses import dataclass
from urllib.parse import quote

from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from markdown_it.token import Token

from backlog_cli.serve.text import HtmlText


@dataclass(frozen=True)
class PathHit:
    start: int
    end: int
    absolute: str
    is_dir: bool


class PathLinks:
    # Segments never hold `/`, so the repetition cannot backtrack.
    PATTERN = re.compile(
        r"(?<![\w/.~:-])(?:~(?:/[^\s'\"`)\]>,/]+)+|(?:/[^\s'\"`)\]>,/]+){2,})/?"
    )
    TRAILING = ".:;"

    @classmethod
    def find(cls, text: str) -> list[PathHit]:
        """The existing paths in the text."""
        hits = []
        for match in cls.PATTERN.finditer(text):
            candidate = match.group().rstrip(cls.TRAILING)
            absolute = os.path.expanduser(candidate)
            # a bare top-level folder (`/usr`) is not worth a link
            if absolute.rstrip("/").count("/") >= 2 and os.path.exists(absolute):
                hits.append(
                    PathHit(
                        match.start(),
                        match.start() + len(candidate),
                        absolute,
                        os.path.isdir(absolute),
                    )
                )
        return hits

    @staticmethod
    def build_attrs(hit: PathHit) -> list[list[str]]:
        kind = "dir" if hit.is_dir else "file"
        href = "#" if hit.is_dir else f"/_/file?path={quote(hit.absolute, safe='')}"
        return [
            ["href", href],
            ["class", "path"],
            ["data-path", hit.absolute],
            ["data-kind", kind],
        ]

    @classmethod
    def html(cls, text: str) -> str:
        """Escaped text with a link for each existing path."""
        out, position = [], 0
        for hit in cls.find(text):
            attrs = "".join(
                f' {name}="{HtmlText.esc(value)}"'
                for name, value in cls.build_attrs(hit)
            )
            out.append(HtmlText.esc(text[position : hit.start]))
            out.append(f"<a{attrs}>{HtmlText.esc(text[hit.start : hit.end])}</a>")
            position = hit.end
        out.append(HtmlText.esc(text[position:]))
        return "".join(out)

    @classmethod
    def install(cls, renderer: MarkdownIt) -> MarkdownIt:
        """Link the paths of text and inline code; code blocks stay as they are."""
        renderer.core.ruler.push("path_links", cls._apply)
        return renderer

    @classmethod
    def _apply(cls, state: StateCore) -> None:
        for block in state.tokens:
            if block.type == "inline" and block.children:
                block.children = cls._link_children(block.children)

    @classmethod
    def _link_children(cls, children: list[Token]) -> list[Token]:
        result: list[Token] = []
        depth = 0
        for token in children:
            depth += {"link_open": 1, "link_close": -1}.get(token.type, 0)
            if depth == 0 and token.type in ("text", "code_inline"):
                result += cls._split(token)
            else:
                result.append(token)
        return result

    @classmethod
    def _split(cls, token: Token) -> list[Token]:
        hits = cls.find(token.content)
        if not hits:
            return [token]
        parts: list[Token] = []
        position = 0
        for hit in hits:
            parts += cls._piece(token, token.content[position : hit.start])
            link = Token("link_open", "a", 1)
            link.attrs = {name: value for name, value in cls.build_attrs(hit)}
            parts.append(link)
            parts += cls._piece(token, token.content[hit.start : hit.end])
            parts.append(Token("link_close", "a", -1))
            position = hit.end
        return parts + cls._piece(token, token.content[position:])

    @staticmethod
    def _piece(token: Token, content: str) -> list[Token]:
        if not content:
            return []
        piece = Token(token.type, token.tag, 0)
        piece.content = content
        piece.markup = token.markup
        return [piece]
