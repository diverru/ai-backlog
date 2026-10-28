"""The guide text as Markdown: prose stays plain, commands and lists go in fences."""

from backlog_cli.guide.guide_section import GuideSection


class MarkdownGuide:
    FENCE = "```"
    COMMAND_STARTS = ("backlog ", "$ ")

    @classmethod
    def format_section(cls, section: GuideSection) -> str:
        title = section.name.replace("_", " ").capitalize()
        return f"## {title}\n\n{cls.convert_text(section.text)}"

    @classmethod
    def convert_text(cls, text: str) -> str:
        return "\n\n".join(cls.convert_block(block) for block in cls.split_blocks(text))

    @staticmethod
    def split_blocks(text: str) -> list[list[str]]:
        """Runs of lines between blank lines."""
        blocks: list[list[str]] = [[]]
        for line in text.splitlines():
            if line.strip():
                blocks[-1].append(line)
            elif blocks[-1]:
                blocks.append([])
        return [block for block in blocks if block]

    @classmethod
    def convert_block(cls, lines: list[str]) -> str:
        body = "\n".join(lines)
        is_code = lines[0].startswith(" ") or any(
            line.startswith(cls.COMMAND_STARTS) for line in lines
        )
        return f"{cls.FENCE}text\n{body}\n{cls.FENCE}" if is_code else body
