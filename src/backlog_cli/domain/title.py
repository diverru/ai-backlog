"""How a title is shown where items are listed."""


class TitleText:
    WIDTH = 72

    @classmethod
    def shorten(cls, title: str) -> str:
        """One line: a long title is cut to WIDTH characters with `...`."""
        if len(title) <= cls.WIDTH:
            return title
        return title[: cls.WIDTH - 3] + "..."
