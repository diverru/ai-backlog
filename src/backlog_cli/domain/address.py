"""Addresses: `43`, `0043_slug`, `43/unit`, `43/unit/action`."""

import re
from dataclasses import dataclass

from backlog_cli.domain.vocabulary import AddressLevel
from backlog_cli.errors import UsageError


@dataclass(frozen=True)
class Address:
    # Wide enough for every id an earlier version wrote.
    ITEM_ID_PATTERN = re.compile(r"^[0-9]{4,}_[a-z0-9][a-z0-9_-]*$")
    LOCAL_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")
    NEW_ID_WHAT = (
        "lowercase letters, digits, underscores and dashes, starting with a letter"
    )
    NEW_ID_MAX_LENGTH = 60

    item: int | str  # a number, or a full item id
    unit: str | None = None
    action: str | None = None

    @classmethod
    def parse(cls, text: str) -> "Address":
        parts = text.split("/")
        if len(parts) == 2 and parts[0] and not parts[1]:
            raise UsageError(f"unit address is N/UNIT, e.g. {parts[0]}/engine")
        if len(parts) > 3 or not all(parts):
            raise UsageError(f"bad address {text!r}; use 43 or 43/unit")
        item = cls._parse_item(parts[0], text)
        for local_id in parts[1:]:
            if not cls.LOCAL_ID_PATTERN.match(local_id):
                raise UsageError(
                    f"bad address {text!r}; {local_id!r} is not a unit or action id"
                )
        return cls(item, *parts[1:])

    @classmethod
    def require_new_id(cls, text: str, what: str) -> None:
        """The rule for a slug, unit id or action id that is being created."""
        if not cls.LOCAL_ID_PATTERN.match(text):
            raise UsageError(f"bad {what} {text!r}; use {cls.NEW_ID_WHAT}")
        if len(text) > cls.NEW_ID_MAX_LENGTH:
            raise UsageError(
                f"{what} {text[:20]!r}... is {len(text)} characters long; "
                f"at most {cls.NEW_ID_MAX_LENGTH}"
            )

    @classmethod
    def _parse_item(cls, text: str, whole_address: str) -> int | str:
        if text.isascii() and text.isdecimal():
            return int(text)
        if cls.ITEM_ID_PATTERN.match(text):
            return text
        raise UsageError(
            f"bad item in address {whole_address!r}; "
            "use the number (43) or the exact id (0043_slug)"
        )

    @property
    def level(self) -> AddressLevel:
        if self.action:
            return AddressLevel.ACTION
        if self.unit:
            return AddressLevel.UNIT
        return AddressLevel.ITEM

    def __str__(self) -> str:
        parts = (self.item, self.unit, self.action)
        return "/".join(str(part) for part in parts if part is not None)
