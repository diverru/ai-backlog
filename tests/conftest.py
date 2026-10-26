"""Test fixtures: a temporary data root and an in-process CLI."""

import contextlib
import io
import shlex
import sys
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backlog_cli.cli import Cli  # noqa: E402
from backlog_cli.domain.vocabulary import DetailsSection  # noqa: E402


def days_from_now(days: int) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).strftime("%Y-%m-%d")


def valid_details(handoff: str = "Do the thing.") -> str:
    """A details file with the eight standard sections."""
    parts = []
    for section in DetailsSection:
        body = handoff if section == DetailsSection.HANDOFF else f"Text of {section}."
        parts.append(f"## {section}\n\n{body}")
    return "\n\n".join(parts) + "\n"


class OldWords:
    """Words of the removed grammar, built from parts so no source text holds them."""

    NEXT_FLAG = "--" + "next"
    STATUS_MIDDLE = "post_" + "deploy"
    VERB = "deploy" + "ed"
    NOUN = "deploy" + "ment"
    COMMANDS = ("mo" + "ve", "se" + "t", "de" + "ps", "arch" + "ive")
    ITEM_CLOSE = "acc" + "ept"


@dataclass
class RunResult:
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out + self.err


class Backlog:
    """Runs the CLI in-process against a temporary data root."""

    RELEASE_FLAGS = (
        "--at",
        "2026-10-23T12:00:00Z",
        "--source",
        "release_status api 123",
        "--tag",
        "v1.2.0",
    )

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root
        self.home = root / "home"
        self.work = root / "work"
        self.work.mkdir(parents=True)
        self.next_pr_number = 11000
        monkeypatch.setenv("BKLG_HOME", str(self.home))
        monkeypatch.chdir(self.work)

    @staticmethod
    def now_utc() -> str:
        """The current UTC time to the second, as `--at` takes it."""
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def today() -> str:
        """The current UTC date: a fact dated before it predates a new item."""
        return datetime.now(UTC).date().isoformat()

    def run(self, *arguments: str) -> RunResult:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = Cli.main(list(arguments))
            except SystemExit as exit_request:
                code = int(exit_request.code or 0)
        return RunResult(code, out.getvalue(), err.getvalue())

    def ok(self, *arguments: str) -> str:
        result = self.run(*arguments)
        assert result.code == 0, f"{arguments} exited {result.code}:\n{result.text}"
        return result.out

    def run_line(self, line: str) -> RunResult:
        """Run a command given as one shell-like line."""
        return self.run(*shlex.split(line))

    def ok_line(self, line: str) -> str:
        return self.ok(*shlex.split(line))

    def refuse(self, line: str, text: str = "", code: int = 1) -> str:
        """The command is refused with `code`, names `text` and changes nothing."""
        before = self.snapshot()
        result = self.run_line(line)
        assert result.code == code, f"{line}\n{result.text}"
        assert text in result.err, f"{line}\n{result.err}"
        assert "Traceback" not in result.text
        assert self.snapshot() == before, line
        return result.err

    def workspace_file(self, name: str, workspace: str = "ws") -> Path:
        return self.home / workspace / name

    def read_items(self, archive: bool = False, workspace: str = "ws") -> list[dict]:
        name = "ARCHIVE.yaml" if archive else "BACKLOG.yaml"
        return yaml.safe_load(self.workspace_file(name, workspace).read_text())["items"]

    def read_item(self, number: int, archive: bool = False) -> dict:
        for item in self.read_items(archive):
            if int(item["id"].split("_")[0]) == number:
                return item
        raise AssertionError(f"item {number} not found (archive={archive})")

    def read_unit(self, number: int, unit_id: str, archive: bool = False) -> dict:
        item = self.read_item(number, archive)
        return next(unit for unit in item["work"] if unit["id"] == unit_id)

    def snapshot(self) -> tuple[str, str]:
        return (
            self.workspace_file("BACKLOG.yaml").read_text(),
            self.workspace_file("ARCHIVE.yaml").read_text(),
        )

    def add_item(self, slug: str, *flags: str) -> int:
        output = self.ok("add", slug, "--title", slug.replace("_", " "), *flags)
        return int(output.split()[2])

    def release(self, target: str, *extra: str) -> str:
        """Record a release with the standard reported facts."""
        return self.ok(target, "released", *self.RELEASE_FLAGS, *extra)

    def start_item(self, number: int) -> None:
        """Make an item wip: an assigned research unit `work`."""
        self.add_unit(number, "work", "--kind", "research")
        self.ok(f"{number}/work", "assign", "--agent", "A")

    def finish_units(self, number: int) -> None:
        """An item whose only unit, a research `work`, is done: ready to close."""
        self.start_item(number)
        self.ok(f"{number}/work", "done", "--result", "r", "--source", "s")

    def finish_item(self, number: int, *at: str) -> None:
        """Close an item as done through one finished research unit."""
        self.finish_units(number)
        self.ok(str(number), "done", "--result", "r", "--source", "s", *at)

    def add_check(self, number: int, name: str, unit_id: str = "engine") -> str:
        """A pending verification action on a unit."""
        return self.ok(
            f"{number}/{unit_id}",
            "post_release",
            "add",
            name,
            "--kind",
            "verification",
            "--title",
            f"Check {name}",
            "--instructions",
            "Look",
        )

    def failed_check(self) -> int:
        """A released unit whose only check has failed; returns the item number."""
        number = self.add_merged_unit("work")
        self.add_check(number, "check")
        self.release(f"{number}/engine")
        self.ok_line(
            f'{number}/engine post_release fail check --finding "p99 is 4 s" '
            '--source "the panel"'
        )
        return number

    def release_fix(self, number: int, at: str | None = None) -> None:
        """Add a unit `fix`, merge it and release it (the fix of a failed check)."""
        self.next_pr_number += 1
        self.add_unit(number, "fix")
        self.ok(f"{number}/fix", "assign", "--agent", "Fixer")
        self.ok_line(
            f"{number}/fix merged --pr acme/api#{self.next_pr_number} --source gh"
        )
        self.ok_line(
            f"{number}/fix released --at {at or self.now_utc()} --source rs "
            "--no-post-release"
        )

    def add_unit(self, number: int, unit_id: str, *flags: str) -> str:
        return self.ok(str(number), "unit", "add", unit_id, *flags)

    def add_merged_unit(
        self,
        slug: str,
        unit_id: str = "engine",
        pr_number: int | None = None,
        repo: str = "acme/api",
    ) -> int:
        """An item with one PR unit that is merged and recorded.

        A PR is linked to one unit only, so each call takes the next number.
        """
        if pr_number is None:
            self.next_pr_number += 1
            pr_number = self.next_pr_number
        number = self.add_item(slug)
        self.add_unit(number, unit_id)
        self.ok(f"{number}/{unit_id}", "assign", "--agent", "Agent")
        self.ok(
            f"{number}/{unit_id}",
            "merged",
            "--pr",
            f"{repo}#{pr_number}",
            "--source",
            "gh pr view",
        )
        return number


@pytest.fixture
def backlog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Backlog:
    return Backlog(tmp_path, monkeypatch)


@pytest.fixture
def workspace(backlog: Backlog) -> Backlog:
    """A bound workspace `ws`."""
    backlog.ok("bind", "ws")
    return backlog
