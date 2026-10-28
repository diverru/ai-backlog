"""`backlog guide`: the complete manual, or one section of it."""

from backlog_cli.command.base import Command, ShortHelpParser
from backlog_cli.errors import UsageError
from backlog_cli.guide.change_guide import ChangeGuide
from backlog_cli.guide.guide_section import GuideSection
from backlog_cli.guide.markdown_guide import MarkdownGuide
from backlog_cli.guide.overview_guide import OverviewGuide
from backlog_cli.guide.read_guide import ReadGuide
from backlog_cli.guide.setup_guide import SetupGuide


class GuideParser(ShortHelpParser):
    section: str | None = None  # Print only this section, or `all`.
    markdown: bool = False  # Print Markdown instead of plain text.

    def configure(self) -> None:
        self.add_argument(
            "section",
            nargs="?",
            default=None,
            help="Print only this section, or `all` for the full manual",
        )


class GuideCommand(Command):
    NAME = "guide"
    SUMMARY = "Print the overview and lifecycle, one section, or all."
    USAGE = "backlog guide [SECTION] [--markdown]"
    EXAMPLES = "Examples:\n  backlog guide\n  backlog guide unit\n  backlog guide all"
    SECTIONS = [
        GuideSection("overview", OverviewGuide.PURPOSE),
        GuideSection("workspace", OverviewGuide.WORKSPACE),
        GuideSection("addresses", OverviewGuide.ADDRESSES),
        GuideSection("lifecycle", OverviewGuide.LIFECYCLE),
        GuideSection("checking", OverviewGuide.CHECKING),
        GuideSection("bind", SetupGuide.BIND),
        GuideSection("unbind", SetupGuide.UNBIND),
        GuideSection("add", ChangeGuide.ADD),
        GuideSection("list", ReadGuide.LIST),
        GuideSection("search", ReadGuide.SEARCH),
        GuideSection("show", ReadGuide.SHOW),
        GuideSection("item", ChangeGuide.ITEM),
        GuideSection("dependency", ChangeGuide.DEPENDENCY),
        GuideSection("assign", ChangeGuide.ASSIGN),
        GuideSection("finish", ChangeGuide.FINISH),
        GuideSection("unit", ChangeGuide.UNIT),
        GuideSection("post_release", ChangeGuide.POST_RELEASE),
        GuideSection("brief", ReadGuide.BRIEF),
        GuideSection("serve", ReadGuide.SERVE),
        GuideSection("rules", OverviewGuide.RULES),
        GuideSection("codes", OverviewGuide.EXIT_CODES),
    ]
    FIRST_READ = ("overview", "lifecycle")
    ALL = "all"
    Parser = GuideParser

    def run(self, args: GuideParser) -> int:
        if args.section in (None, self.ALL):
            names = self.FIRST_READ if args.section is None else None
            sections = [s for s in self.SECTIONS if names is None or s.name in names]
            if args.markdown:
                self.print_markdown(sections)
                return 0
            self.print_lines(self.build_contents())
            for section in sections:
                self.print_lines("", self.format_section(section))
            return 0
        matching = [
            section for section in self.SECTIONS if section.name == args.section
        ]
        if not matching:
            raise UsageError(
                f"no guide section {args.section!r}; sections: "
                + ", ".join(section.name for section in self.SECTIONS)
                + f", {self.ALL}"
            )
        if args.markdown:
            self.print_markdown(matching)
        else:
            self.print_lines(self.format_section(matching[0]))
        return 0

    def print_markdown(self, sections: list[GuideSection]) -> None:
        self.print_lines(
            "\n\n".join(MarkdownGuide.format_section(section) for section in sections)
        )

    def build_contents(self) -> str:
        names = ", ".join(section.name for section in self.SECTIONS)
        return (
            f"BACKLOG GUIDE. Sections: {names}.\n"
            "Print one section with: backlog guide SECTION; "
            "the full manual with: backlog guide all"
        )

    @staticmethod
    def format_section(section: GuideSection) -> str:
        return f"{'=' * 78}\n{section.name.upper()}\n{'=' * 78}\n{section.text}"
