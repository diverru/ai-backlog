"""The part of README.md that is generated from the guide and the command classes."""

from backlog_cli.cli import Cli
from backlog_cli.command.guide import GuideCommand
from backlog_cli.command.router import ActionTable
from backlog_cli.errors import UsageError
from backlog_cli.guide.markdown_guide import MarkdownGuide


class ReadmeGuide:
    START = "<!-- guide:start -->"
    END = "<!-- guide:end -->"
    SECTION_NAMES = ("overview", "workspace", "addresses", "lifecycle", "serve")

    @classmethod
    def build(cls) -> str:
        sections = [
            MarkdownGuide.format_section(section)
            for name in cls.SECTION_NAMES
            for section in GuideCommand.SECTIONS
            if section.name == name
        ]
        return "\n\n".join(sections + [cls.build_commands()])

    @staticmethod
    def build_commands() -> str:
        commands = [*Cli.COMMANDS, *ActionTable.ACTIONS]
        lines = [
            f"- `{' '.join(command.USAGE.split())}` — {command.SUMMARY}"
            for command in commands
        ]
        return "\n".join(["## Commands", "", *lines])

    @classmethod
    def refresh(cls, readme: str) -> str:
        """The README with the text between the markers rebuilt."""
        start = readme.find(cls.START)
        end = readme.find(cls.END)
        if start < 0 or end < start:
            raise UsageError(f"README.md needs the lines {cls.START} and {cls.END}")
        head = readme[: start + len(cls.START)]
        return f"{head}\n{cls.build()}\n{readme[end:]}"
