"""Links that leave the viewer open in a new tab."""

from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore


class ExternalLinks:
    PREFIXES = ("http://", "https://")

    @classmethod
    def install(cls, renderer: MarkdownIt) -> MarkdownIt:
        renderer.core.ruler.push("external_links", cls._apply)
        return renderer

    @classmethod
    def _apply(cls, state: StateCore) -> None:
        for block in state.tokens:
            for token in block.children or []:
                href = token.attrGet("href") if token.type == "link_open" else None
                if isinstance(href, str) and href.lower().startswith(cls.PREFIXES):
                    token.attrSet("target", "_blank")
                    token.attrSet("rel", "noopener noreferrer")
