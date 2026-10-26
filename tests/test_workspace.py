"""Workspace selection: bindings, the nearest parent, the explicit flag."""

import os

from conftest import Backlog


def test_the_nearest_bound_parent_wins(backlog: Backlog) -> None:
    child = backlog.work / "project" / "task"
    grandchild = child / "deep"
    grandchild.mkdir(parents=True)
    backlog.ok("bind", "outer")
    backlog.ok("bind", "inner", "--dir", str(child))
    backlog.add_item("from_parent")  # the working directory is the outer one
    os.chdir(grandchild)
    backlog.ok_line("add in_inner --title t")
    assert [i["id"] for i in backlog.read_items(workspace="outer")] == [
        "0001_from_parent"
    ]
    assert [i["id"] for i in backlog.read_items(workspace="inner")] == ["0001_in_inner"]


def test_no_binding_is_an_error_before_any_write(backlog: Backlog) -> None:
    result = backlog.run_line("add thing --title t")
    assert result.code == 2
    assert str(backlog.work) in result.err and "backlog bind" in result.err
    assert not backlog.home.exists()
    assert "backlog bind missing" in backlog.run("--workspace", "missing", "list").err


def test_the_workspace_flag_overrides_the_directory(backlog: Backlog) -> None:
    backlog.ok("bind", "one")
    other = backlog.work / "other"
    other.mkdir()
    backlog.ok("bind", "two", "--dir", str(other))
    backlog.ok_line("--workspace two add first --title t")
    backlog.ok_line("add second --title t --workspace two")
    assert len(backlog.read_items(workspace="two")) == 2
    assert backlog.read_items(workspace="one") == []


def test_bind_and_unbind(backlog: Backlog) -> None:
    assert "Next: backlog add" in backlog.ok("bind", "one")
    again = backlog.ok("bind", "one")
    assert "already bound to one" in again and "Bound " not in again
    err = backlog.run("bind", "two").err
    assert "backlog unbind" in err
    backlog.ok_line("add work --title t")
    assert "Next:" not in backlog.ok("bind", "one")
    backlog.ok("unbind")
    backlog.ok("bind", "two")
    for name in ("..", "Bad Name"):
        result = backlog.run("bind", name)
        assert result.code == 2 and "start with a letter or a digit" in result.err


def test_bind_dry_run_writes_nothing(backlog: Backlog) -> None:
    assert "Dry run" in backlog.ok("bind", "ws", "--dry-run")
    assert not backlog.home.exists()


def test_a_workspace_name_has_at_most_64_characters(backlog: Backlog) -> None:
    result = backlog.run("bind", "a" * 300)
    assert result.code == 2 and "64 characters" in result.err
    assert "Traceback" not in result.text
    backlog.ok("bind", "a" * 64)
