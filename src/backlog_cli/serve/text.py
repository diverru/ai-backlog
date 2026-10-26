"""Escaping and the Russian date form of every page."""

from datetime import date, datetime
from html import escape

from backlog_cli.domain.part import PrRef
from backlog_cli.moment import Moment


class HtmlText:
    """Every data string goes through here before it reaches a page."""

    @staticmethod
    def esc(text: object) -> str:
        return escape(str(text), quote=True)

    @classmethod
    def name(cls, text: str) -> str:
        """A unit or action name that may wrap after `_`, `/` and `-`."""
        out = cls.esc(text)
        for mark in ("_", "/", "-"):
            out = out.replace(mark, f"{mark}<wbr>")
        return out

    @classmethod
    def pr_link(cls, pr: PrRef) -> str:
        url = f"https://github.com/{cls.esc(pr.repo)}/pull/{pr.number}"
        return (
            f'<a href="{url}" class="addr" target="_blank" '
            f'rel="noopener noreferrer">{cls.esc(pr)}</a>'
        )

    @staticmethod
    def plural(count: int, one: str, many: str) -> str:
        """`1 item`, `2 items`."""
        return f"{count} {one if count == 1 else many}"

    @classmethod
    def shorten(cls, text: str, width: int) -> str:
        flat = " ".join(text.split())
        return flat if len(flat) <= width else flat[: width - 1] + "…"


class LocalDate:
    """`25 Oct 18:40` in the local time of the machine; the stored value is the
    `title` of the span, so the exact moment is one hover away.
    """

    MONTHS = (
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    )

    @classmethod
    def format(cls, stored: str | None, with_time: bool = True) -> str:
        """The short text, or an empty text without a value."""
        if not stored:
            return ""
        if Moment.is_date(stored):
            return cls._format_day(date.fromisoformat(stored))
        local = datetime.fromisoformat(stored).astimezone()
        text = cls._format_day(local.date())
        return f"{text} {local:%H:%M}" if with_time else text

    @classmethod
    def _format_day(cls, day: date) -> str:
        text = f"{day.day} {cls.MONTHS[day.month - 1]}"
        return text if day.year == date.today().year else f"{text} {day.year}"

    @classmethod
    def html(cls, stored: str | None, with_time: bool = True) -> str:
        if not stored:
            return ""
        shown = HtmlText.esc(cls.format(stored, with_time))
        return f'<span title="{HtmlText.esc(stored)}">{shown}</span>'
