"""User-facing errors and the one renderer of refusals.

Exit code 2 means bad input; exit code 1 means a valid request that the
current state does not allow.
"""

from dataclasses import dataclass

from backlog_cli.domain.title import TitleText


class BacklogError(Exception):
    exit_code = 2


class UsageError(BacklogError):
    """Bad input: an unknown address, an invalid value, a wrong flag."""

    exit_code = 2


class LockError(BacklogError):
    exit_code = 1


@dataclass(frozen=True)
class Hint:
    """A next command, introduced by a sentence.

    Hints with the same sentence are listed together. A command may hold
    alternatives, one per line.
    """

    sentence: str
    command: str


@dataclass(frozen=True)
class Obstacle:
    address: str
    name: str
    reason: str
    group: str
    hint: Hint | None = None
    extra_hint: Hint | None = None


class Refusal(BacklogError):
    """A valid request the current state does not allow.

    With obstacles it prints every one of them, grouped.
    """

    exit_code = 1

    def __init__(self, head: str, obstacles: list[Obstacle] | None = None) -> None:
        super().__init__(head)
        self.head = head
        self.obstacles = list(dict.fromkeys(obstacles or []))

    def __str__(self) -> str:
        return self.render() if self.obstacles else self.head

    def render(self, head: str | None = None) -> str:
        lines = [f"{head or self.head} Nothing changed.", ""]
        lines += self._render_groups()
        lines += self._render_hints()
        return "\n".join(lines).rstrip()

    def _render_groups(self) -> list[str]:
        by_group: dict[str, list[Obstacle]] = {}
        for obstacle in self.obstacles:
            by_group.setdefault(obstacle.group, []).append(obstacle)
        lines = []
        for group, members in by_group.items():
            lines.append(f"{group}:")
            for obstacle in members:
                subject = f"{obstacle.address} — {TitleText.shorten(obstacle.name)}"
                if not obstacle.name:
                    subject = obstacle.address
                lines.append(f"  {subject}: {obstacle.reason}")
            lines.append("")
        return lines

    def _render_hints(self) -> list[str]:
        commands_by_sentence: dict[str, list[str]] = {}
        for obstacle in self.obstacles:
            for hint in (obstacle.hint, obstacle.extra_hint):
                if hint is None:
                    continue
                commands = commands_by_sentence.setdefault(hint.sentence, [])
                if hint.command not in commands:
                    commands.append(hint.command)
        lines = []
        for sentence, commands in commands_by_sentence.items():
            lines.append(f"{sentence}:")
            shown = dict.fromkeys(
                f"  {line}" for command in commands for line in command.split("\n")
            )
            lines += list(shown)
            lines.append("")
        return lines
