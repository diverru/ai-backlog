"""Dates and times. Stored datetimes are UTC with a trailing Z; dates are YYYY-MM-DD."""

import re
from datetime import UTC, date, datetime, timedelta

from backlog_cli.errors import UsageError


class Moment:
    DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    EARLIEST = date(2000, 1, 1)
    DAYS_AHEAD = 5 * 365 + 1

    @staticmethod
    def now() -> str:
        return (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )

    @classmethod
    def is_date(cls, value: str) -> bool:
        if not cls.DATE_PATTERN.match(value):
            return False
        try:
            date.fromisoformat(value)
        except ValueError:
            return False
        return True

    @classmethod
    def to_datetime(cls, stored: str) -> datetime:
        """A stored date or UTC datetime as an aware datetime (a date is 00:00 UTC)."""
        if cls.is_date(stored):
            return datetime.fromisoformat(f"{stored}T00:00:00+00:00")
        return datetime.fromisoformat(stored)

    @classmethod
    def is_before(cls, stored: str, reference: str, by_day: bool = False) -> bool:
        """`stored` is earlier than `reference`; by_day compares UTC dates only.

        A plain date given by the user means a day, not 00:00, so it is compared
        by day.
        """
        first, second = cls.to_datetime(stored), cls.to_datetime(reference)
        if by_day:
            return first.date() < second.date()
        return first < second

    @classmethod
    def require_not_future(cls, stored: str, flag: str, what: str) -> None:
        """Refuse a fact dated after now."""
        now = Moment.now()
        if cls.is_before(now, stored):
            raise UsageError(
                f"{flag} {stored} is later than now ({now}); {what} cannot be in "
                "the future"
            )

    @classmethod
    def require_not_before(
        cls, stored: str, flag: str, reference: str, what: str
    ) -> None:
        """Refuse a fact dated before the event it must follow."""
        if cls.is_before(stored, reference):
            raise UsageError(f"{flag} {stored} is earlier than {what} ({reference})")

    @classmethod
    def require_in_range(cls, moment: datetime, text: str, flag: str) -> None:
        """Dates before 2000 or more than five years ahead are typing errors."""
        now = datetime.now(UTC)
        limit = now + timedelta(days=cls.DAYS_AHEAD)
        earliest = datetime(cls.EARLIEST.year, 1, 1, tzinfo=UTC)
        if earliest <= moment <= limit:
            return
        raise UsageError(
            f"{flag}: {text} is out of range; use a date from {cls.EARLIEST} "
            f"to {limit.date()} (five years from now)"
        )

    @classmethod
    def normalize(cls, text: str) -> str:
        """A datetime with offset in the stored UTC form.

        Raises ValueError for anything else.
        """
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            raise ValueError(f"{text!r} has no offset")
        try:
            converted = parsed.astimezone(UTC)
        except OverflowError:
            raise ValueError(f"{text!r} is out of range") from None
        return converted.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @classmethod
    def parse_instant(cls, text: str, flag: str) -> str:
        """Like `parse`, but always a datetime. A plain date means the end of
        that day (23:59:59Z), and now for today, so a check and the stored value
        use the same moment.
        """
        if cls.is_date(text):
            cls.require_in_range(cls.to_datetime(text), text, flag)
            if text == Moment.now()[:10]:
                return Moment.now()
            return f"{text}T23:59:59Z"
        return cls.parse(text, flag)

    @classmethod
    def parse(cls, text: str, flag: str) -> str:
        """Parse CLI input: a date or a datetime with offset, in the stored form."""
        if cls.is_date(text):
            cls.require_in_range(cls.to_datetime(text), text, flag)
            return text
        if cls.DATE_PATTERN.match(text):
            raise UsageError(f"{flag}: {text!r} is not a real calendar date")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise UsageError(
                f"{flag}: invalid format {text!r}; "
                "use YYYY-MM-DD or an ISO 8601 datetime with offset"
            ) from None
        if parsed.tzinfo is None:
            raise UsageError(
                f"{flag}: {text!r} has no time zone offset; add Z or +03:00"
            )
        try:
            normalized = cls.normalize(text)
        except ValueError:
            raise UsageError(f"{flag}: {text} is out of range") from None
        cls.require_in_range(cls.to_datetime(normalized), text, flag)
        return normalized
