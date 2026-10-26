"""The stored files: key order, the fixture, the schema guard, the lazy archive,
and the repair of an interrupted archive.

tests/fixtures/workspace_schema1 is built with the real commands. Before the first
release it is rebuilt whenever the stored format changes; after the first release it
is never edited and a format change must still read it.
"""

import shutil
from pathlib import Path

import pytest
import yaml

from backlog_cli.store.workspace import Workspace
from backlog_cli.store.yamlfile import YamlFile
from conftest import Backlog

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "workspace_schema1"


def install_fixture(backlog: Backlog) -> None:
    shutil.copytree(FIXTURE, backlog.home / "ws")
    backlog.ok("bind", "ws")


def crash_backlog_write(
    workspace: Backlog, monkeypatch: pytest.MonkeyPatch, *line: str
) -> None:
    """Run a command whose second write (BACKLOG.yaml) fails after the archive."""

    def crash(self: Workspace, text: str) -> None:
        raise OSError("disk went away")

    with monkeypatch.context() as patch:
        patch.setattr(Workspace, "write_backlog_file", crash)
        with pytest.raises(OSError):
            workspace.run(*line)


def test_every_record_is_stored_with_its_keys_in_order(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_unit(number, "study", "--kind", "research")
    workspace.add_check(number, "check")
    stored = yaml.safe_load(workspace.workspace_file("BACKLOG.yaml").read_text())
    assert list(stored) == [
        "schema_version",
        "next_id",
        "archived_outcomes",
        "archived_item_ids",
        "items",
    ]
    assert list(stored["items"][0]) == [
        "id",
        "title",
        "priority",
        "status",
        "tags",
        "due_at",
        "remind_at",
        "depends_on",
        "prerequisite_prs",
        "blockers",
        "resolved_blockers",
        "next_blocker_id",
        "work",
        "created_at",
        "updated_at",
        "completion",
    ]
    assert list(workspace.read_unit(number, "engine")) == [
        "id",
        "kind",
        "status",
        "assignees",
        "returns",
        "pr",
        "merge",
        "release",
        "corrections",
        "post_release_required",
        "post_release_actions",
        "completion",
    ]
    assert list(workspace.read_unit(number, "study")) == [
        "id",
        "kind",
        "status",
        "assignees",
        "returns",
        "completion",
    ]
    action = workspace.read_unit(number, "engine")["post_release_actions"][0]
    assert list(action) == [
        "id",
        "kind",
        "description",
        "instructions",
        "status",
        "confirmation",
        "cancel_reason",
        "findings",
        "cancelled_at",
    ]


def test_the_fixture_workspace_loads_and_is_read_by_every_command(
    backlog: Backlog,
) -> None:
    stored = yaml.safe_load((FIXTURE / "BACKLOG.yaml").read_text())
    assert stored["schema_version"] == 1 and YamlFile.SCHEMA_VERSION >= 1
    assert stored["archived_outcomes"] == {"0001_base_work": "done"}
    install_fixture(backlog)
    listing = backlog.ok("list")
    assert "blocker b1: Needs an administrator (waiting on admin)" in listing
    assert "check check_latency: Check search latency — FAILED: p99 is 4 s" in listing
    assert "study  research  wip  Researcher (analyst)" in listing
    assert "Base work" in backlog.ok("list", "--archive")
    shown = backlog.ok("3", "show", "--full")
    assert "tag: v1.2.0" in shown and "next_blocker_id: 3" in shown
    assert "release v1.2.0" in backlog.ok("3/engine")
    assert "p99 is 4 s" in backlog.ok("3/engine", "show")
    assert "The first source was too short" in backlog.ok("1", "show")
    assert "Paused" in backlog.ok("6", "show", "--full")
    assert "check_latency" in backlog.ok("3/engine", "post_release")
    assert "Needs an administrator" in backlog.ok("search", "administrator")
    assert "acme/web#201" in backlog.ok("4", "dependency")
    assert "# 3: Realtime order search" in backlog.ok("3", "brief", "export")
    assert "Failed post-release checks:" in backlog.ok("list", "--attention")


def test_commands_write_into_the_fixture_workspace(backlog: Backlog) -> None:
    install_fixture(backlog)
    backlog.ok("7", "priority", "high")
    backlog.ok_line("3 block remove b1 --reason 'Admin replied'")
    backlog.ok_line("3 brief append --section 'Agent handoff' --text More.")
    backlog.ok("3", "unit", "add", "fix")
    backlog.ok("3/fix", "assign", "--agent", "Fixer")
    backlog.ok_line("3/fix merged --pr acme/api#124 --source gh")
    backlog.ok_line(
        f"3/fix released --at {backlog.now_utc()} --source rs --no-post-release"
    )
    backlog.ok_line(
        "3/engine post_release done check_latency --result fine --source panel"
    )
    backlog.ok_line("6/study done --result Answer --source notes")
    backlog.ok_line("6 done --result Answer --source notes")
    backlog.ok_line("7 cancel --reason 'not needed'")
    backlog.ok("4", "dependency", "add", "1")
    stored = yaml.safe_load(backlog.workspace_file("BACKLOG.yaml").read_text())
    assert stored["schema_version"] == 1
    assert stored["archived_outcomes"] == {"0001_base_work": "done"}
    third = next(item for item in stored["items"] if item["id"] == "0003_search_rt")
    assert [b["id"] for b in third["resolved_blockers"]] == ["b2", "b1"]
    assert "depends on: 1 (done)" in backlog.ok("4")


def test_a_workspace_from_a_newer_schema_is_readable_but_never_written(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    path = workspace.workspace_file("BACKLOG.yaml")
    newer = YamlFile.SCHEMA_VERSION + 1
    path.write_text(
        path.read_text().replace(
            f"schema_version: {YamlFile.SCHEMA_VERSION}", f"schema_version: {newer}", 1
        )
    )
    assert "work" in workspace.ok("list") and "work" in workspace.ok(str(number))
    for line in (
        "add other --title t",
        f"{number} priority low",
        f"{number} brief append --section 'Agent handoff' --text x",
    ):
        err = workspace.refuse(line, f"written by a newer backlog (schema {newer}")
        assert "Update backlog." in err


def test_the_archive_is_read_only_by_commands_that_need_it(workspace: Backlog) -> None:
    base = workspace.add_item("base")
    workspace.finish_item(base)
    top = workspace.add_item("top", "--depends-on", str(base))
    workspace.add_item("other")
    workspace.workspace_file("ARCHIVE.yaml").write_text("{{{ not: yaml [")
    for line in (
        "list",
        "list --attention",
        str(top),
        f"{top} priority low",
        "add third --title t",
        "search top",
    ):
        workspace.ok_line(line)
    workspace.add_unit(top, "study", "--kind", "research")
    workspace.ok_line(f"{top}/study assign --agent A")
    workspace.ok_line(f"{top}/study done --result r --source s")
    for line in ("list --archive", "search x --archive", str(base)):
        err = workspace.refuse(line, "ARCHIVE.yaml cannot be read")
        assert "Traceback" not in err


def test_the_outcome_of_an_archived_dependency_lives_in_the_registry(
    workspace: Backlog,
) -> None:
    kept = workspace.add_item("kept")
    dropped = workspace.add_item("dropped")
    top = workspace.add_item("top", "--depends-on", str(kept))
    for number in (kept, dropped):
        workspace.ok(str(number), "cancel", "--reason", "r")
    stored = yaml.safe_load(workspace.workspace_file("BACKLOG.yaml").read_text())
    assert stored["archived_outcomes"] == {"0001_kept": "cancelled"}
    workspace.workspace_file("ARCHIVE.yaml").write_text("{{{")
    workspace.refuse(f"{top} done --result r --source s", "archived as cancelled")


def test_the_fast_loader_reads_what_the_plain_loader_reads(workspace: Backlog) -> None:
    workspace.add_item("work", "--tags", "a,b")
    text = workspace.workspace_file("BACKLOG.yaml").read_text()
    assert yaml.load(text, Loader=YamlFile.LOADER) == yaml.safe_load(text)


def test_a_brief_edit_moves_updated_at(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    path = workspace.workspace_file("BACKLOG.yaml")
    stored = yaml.safe_load(path.read_text())
    stored["items"][0]["updated_at"] = "2020-01-01T00:00:00Z"
    path.write_text(YamlFile.dump(stored))
    workspace.ok_line(f"{number} brief append --section 'Agent handoff' --text x")
    assert workspace.read_item(number)["updated_at"] != "2020-01-01T00:00:00Z"


def test_an_interrupted_archive_is_repaired_by_every_writing_command(
    workspace: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = workspace.add_item("work")
    top = workspace.add_item("top", "--depends-on", str(base))
    workspace.finish_units(base)
    crash_backlog_write(
        workspace, monkeypatch, str(base), "done", "--result", "r", "--source", "s"
    )
    in_backlog = [item["id"] for item in workspace.read_items()]
    in_archive = [item["id"] for item in workspace.read_items(archive=True)]
    assert "0001_work" in in_backlog and "0001_work" in in_archive  # never lost
    assert "0001_work" not in workspace.ok("list")  # readers see the archive copy
    assert "Recovered interrupted archive of 0001_work" in workspace.ok_line(
        f"{top} priority low"
    )
    assert [item["id"] for item in workspace.read_items()] == ["0002_top"]
    assert workspace.read_item(base, archive=True)["completion"]["outcome"] == "done"
    # the indexes are rebuilt like in a normal archive
    workspace.finish_units(top)
    workspace.ok_line(f"{top} done --result r --source s")  # the dependency is done
    workspace.refuse("add work --title again", "already used")


@pytest.mark.parametrize("command", ["append", "set", "priority"])
def test_each_kind_of_writing_command_repairs_an_interrupted_archive(
    workspace: Backlog, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    workspace.add_item("work")
    other = workspace.add_item("other")
    crash_backlog_write(workspace, monkeypatch, "1", "cancel", "--reason", "x")
    arguments = {
        "append": f"{other} brief append --section 'Agent handoff' --text x",
        "set": f"{other} brief set --from-file {workspace.work / 'details.md'}",
        "priority": f"{other} priority low",
    }[command]
    (workspace.work / "details.md").write_text(
        workspace.workspace_file("details/0002_other.md").read_text().split("\n", 2)[2]
    )
    assert "Recovered interrupted archive of 0001_work" in workspace.ok_line(arguments)
    assert [item["id"] for item in workspace.read_items()] == ["0002_other"]
