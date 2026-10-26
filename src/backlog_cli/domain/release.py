"""Facts about integration and production: a merged PR and its release.

The tool checks nothing itself: each fact is recorded with its source.
"""

from dataclasses import dataclass

from backlog_cli.domain.part import Evidence
from backlog_cli.domain.record import Record


@dataclass
class Merge(Record):
    merged_at: str | None
    evidence: Evidence

    @classmethod
    def from_dict(cls, data: dict) -> "Merge":
        return cls(
            merged_at=data["merged_at"],
            evidence=Evidence.from_dict(data["evidence"]),
        )


@dataclass
class Release(Record):
    """The production release of a PR.

    released_at is when the release happened, never the time of recording.
    """

    tag: str | None
    released_at: str
    evidence: Evidence

    @classmethod
    def from_dict(cls, data: dict) -> "Release":
        return cls(
            tag=data["tag"],
            released_at=data["released_at"],
            evidence=Evidence.from_dict(data["evidence"]),
        )
