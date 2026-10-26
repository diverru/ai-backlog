"""One named part of the guide."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GuideSection:
    name: str
    text: str
