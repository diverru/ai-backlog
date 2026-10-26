"""Base of every stored object: it writes itself as a mapping."""

from collections.abc import Iterator
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class FieldValue:
    path: str
    text: str


class Record:
    """A dataclass stored in YAML.

    The order of the fields is the order of the keys in the file. Reading is
    done by the `from_dict` of each class: the files are written only by this
    tool.
    """

    def to_dict(self) -> dict:
        return self._to_plain(asdict(self))

    @classmethod
    def _to_plain(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._to_plain(child) for key, child in value.items()}
        if isinstance(value, list):
            return [cls._to_plain(element) for element in value]
        if isinstance(value, Enum):
            return str(value)
        return value

    def walk_fields(self, path: str = "") -> Iterator[FieldValue]:
        """Every non-empty leaf with its dotted path, for `search`."""
        for name, value in vars(self).items():
            yield from self._walk_value(value, f"{path}.{name}" if path else name)

    @classmethod
    def _walk_value(cls, value: Any, path: str) -> Iterator[FieldValue]:
        if isinstance(value, Record):
            yield from value.walk_fields(path)
        elif isinstance(value, list):
            for index, element in enumerate(value):
                has_id = isinstance(element, Record) and "id" in vars(element)
                label = f".{element.id}" if has_id else f"[{index}]"
                yield from cls._walk_value(element, path + label)
        elif value is not None:
            yield FieldValue(path, str(value))
