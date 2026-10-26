"""What every `backlog ADDRESS ACTION` command shares: where it lives and its card."""

from typing import ClassVar

from tap import TapIgnore

from backlog_cli.command.base import CommandParser, MutatingParser, ShortHelpParser
from backlog_cli.domain.address import Address
from backlog_cli.domain.vocabulary import AddressLevel
from backlog_cli.store.registry import Registry, Target


class ReadParser(CommandParser):
    # The router sets it from the word before the action; it is not a flag.
    address: TapIgnore[str] = ""


class ChangeParser(MutatingParser):
    address: TapIgnore[str] = ""


class ActionSpec:
    """The place of one action in the grammar, and the text of its help card.

    WORDS is what follows the address: ("assign",) or ("tag", "add").
    """

    LEVELS: ClassVar[tuple[AddressLevel, ...]]
    WORDS: ClassVar[tuple[str, ...]]
    GUIDE_SECTION: ClassVar[str]
    SUMMARY: ClassVar[str]
    USAGE: ClassVar[str]
    EXAMPLES: ClassVar[str]
    Parser: ClassVar[type[ShortHelpParser]]
    MULTI_TARGET: ClassVar[bool] = False  # the address may list units: 43/a,44/b

    @classmethod
    def build_parser(cls) -> ShortHelpParser:
        parser = cls.Parser(
            prog=f"backlog ADDRESS {' '.join(cls.WORDS)}",
            usage=cls.USAGE,
            description=cls.SUMMARY,
            epilog=cls.EXAMPLES,
            underscores_to_dashes=True,
        )
        parser.guide_section = cls.GUIDE_SECTION
        parser.set_defaults(workspace=None)  # nothing sits before the action
        return parser

    @classmethod
    def get_key(cls) -> str:
        return " ".join(cls.WORDS)

    @staticmethod
    def get_active_target(registry: Registry, text: str) -> Target:
        """The target of an address; an archived item refuses every change."""
        target = registry.resolve_target(Address.parse(text))
        target.require_active()
        return target
