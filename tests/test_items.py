"""Items: add, edit, tags, blockers, dependencies, archived items."""

import pytest

from backlog_cli.domain.vocabulary import DetailsSection
from conftest import Backlog, OldWords


def test_add_stores_the_defaults_and_creates_the_details_file(
    workspace: Backlog,
) -> None:
    out = workspace.ok_line('add fast_order --title "Fast order"')
    assert out.splitlines()[0] == "Created item 1 (0001_fast_order)"
    item = workspace.read_item(1)
    assert (item["priority"], item["status"], item["work"]) == ("normal", "todo", [])
    assert item["due_at"] is None and item["completion"] is None
    text = workspace.workspace_file("details/0001_fast_order.md").read_text()
    assert text.startswith("# 0001_fast_order: Fast order")
    headings = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert headings == [str(section) for section in DetailsSection]


def test_add_with_every_option(workspace: Backlog) -> None:
    workspace.add_item("base")
    workspace.ok_line(
        "add rich --title Rich --priority high --tags back,search --due 2026-11-01 "
        "--reminder 2026-10-30T09:00:00+03:00 --depends-on 1"
    )
    item = workspace.read_item(2)
    assert (item["priority"], item["tags"]) == ("high", ["back", "search"])
    assert (item["due_at"], item["remind_at"]) == ("2026-11-01", "2026-10-30T06:00:00Z")
    assert item["depends_on"] == ["0001_base"]


def test_add_refuses_bad_input_and_writes_nothing(workspace: Backlog) -> None:
    for line in (
        "add thing",  # no title
        "add 12345 --title t",
        "add Bad-Slug --title t",
        "add thing --title t --kind pr",
        "add thing --title t --priority urgent",
        f"add thing --title t {OldWords.NEXT_FLAG} x",
        "add thing --title t --due 2026-11-01T10:00:00",  # no offset
        'add thing --title t --tags "Bad Tag"',
        "add thing --title t --depends-on 99",
        f"add {'a' * 61} --title t",
        "add 1bad --title t",
    ):
        workspace.refuse(line, code=2)
    assert workspace.read_items() == []
    workspace.ok_line(f"add {'a' * 60} --title t")


def test_ids_and_slugs_are_never_reused(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.refuse("add work --title again", f"item {number}")
    workspace.ok(str(number), "cancel", "--reason", "x")
    workspace.refuse("add work --title again", f"item {number}")  # archived too
    assert workspace.ok_line("add again --title Again").startswith("Created item 2")


def test_add_dry_run_writes_nothing(workspace: Backlog) -> None:
    before = workspace.snapshot()
    out = workspace.ok_line("add thing --title t --dry-run")
    assert "Dry run" in out and "Created item 1 (0001_thing)" in out
    assert workspace.snapshot() == before
    assert not workspace.workspace_file("details/0001_thing.md").exists()


def test_item_fields_change_one_action_at_a_time(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    n = str(number)
    assert "title -> New title" in workspace.ok(n, "rename", "New title")
    assert "priority -> high" in workspace.ok(n, "priority", "high")
    workspace.ok_line(f"{n} tag add back perf")
    workspace.ok_line(f"{n} due add 2026-11-05")
    workspace.ok_line(f"{n} reminder add 2026-11-01")
    item = workspace.read_item(number)
    assert (item["title"], item["priority"], item["tags"]) == (
        "New title",
        "high",
        ["back", "perf"],
    )
    assert (item["due_at"], item["remind_at"]) == ("2026-11-05", "2026-11-01")
    details = workspace.workspace_file("details/0001_work.md").read_text()
    assert details.startswith("# 0001_work: New title")
    assert f"{number}: due: 2026-11-05 -> 2026-11-15" in workspace.ok_line(
        f"{n} due add 2026-11-15"
    )
    workspace.ok_line(f"{n} tag remove perf")
    workspace.ok_line(f"{n} due delete")
    workspace.ok_line(f"{n} reminder delete")
    item = workspace.read_item(number)
    assert (item["tags"], item["due_at"], item["remind_at"]) == (["back"], None, None)
    assert "has no deadline" in workspace.run(n, "due", "delete").err


def test_edit_refuses_bad_values_and_changes_nothing(workspace: Backlog) -> None:
    n = str(workspace.add_item("work", "--tags", "back"))
    for line in (
        f"{n} priority urgent",
        f"{n} priority",
        f'{n} tag add "Bad Tag"',
        f"{n} tag remove absent",
        f"{n} due add 2026-11-01T10:00:00",
        f"{n} due add 23.10.2026",
        f"{n} status done",
        f"{n} due add 1999-12-31",
        f"{n} due add 2099-01-01",
    ):
        workspace.refuse(line, code=2)
    workspace.refuse(f'{n} rename "   "', code=2)
    out = workspace.ok_line(f"{n} tag add back")
    assert "already has tag back" in out and "tags ->" not in out


def test_blockers_have_ids_that_are_never_reused(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    n = str(number)
    assert "blocker b1 added" in workspace.ok_line(
        f"{n} block add First --waiting-on admin"
    )
    workspace.ok_line(f"{n} block add Second")
    workspace.refuse(f"{n} block add First", "b1")  # the text of an open blocker
    workspace.refuse(f"{n} block remove b1", code=2)  # a reason is needed
    workspace.refuse(f"{n} block remove b9 --reason r", "open blockers: b1, b2", 2)
    workspace.ok_line(f'{n} block remove 2 --reason "Admin replied"')
    workspace.ok_line(f"{n} block add Third")
    item = workspace.read_item(number)
    assert [b["id"] for b in item["blockers"]] == ["b1", "b3"]
    resolved = item["resolved_blockers"][0]
    assert (resolved["id"], resolved["reason"]) == ("b2", "Admin replied")
    assert item["next_blocker_id"] == 4
    assert "next_blocker_id" not in workspace.ok(n)
    assert "resolved_blockers:" in workspace.ok_line(f"{n} show --full")


def test_dependency_add_remove_and_show(workspace: Backlog) -> None:
    first = workspace.add_item("first")
    second = workspace.add_item("second")
    n = str(second)
    out = workspace.ok_line(f"{n} dependency add {first} acme/web#202")
    assert f"{second}: now waits for {first} (todo)" in out
    assert "added prerequisite PR acme/web#202" in out
    assert "informational and does not block start or closure" in out
    item = workspace.read_item(second)
    assert item["depends_on"] == ["0001_first"]
    assert item["prerequisite_prs"] == [{"repo": "acme/web", "number": 202}]
    workspace.ok_line(f"{n} dependency add {first} acme/api#1 acme/api#1")  # one PR
    assert len(workspace.read_item(second)["prerequisite_prs"]) == 2
    workspace.ok_line(f"{n} block add Waiting --waiting-on admin")
    shown = workspace.ok_line(f"{n} dependency")
    assert f"{first}  first  todo  active" in shown
    assert "Blockers (external conditions):\n  b1  Waiting (waiting on admin)" in shown
    assert "Prerequisite PRs (informational):\n  acme/web#202" in shown
    assert f"{second}  second" in workspace.ok_line(f"{first} dependency --dependents")
    gone = workspace.add_item("gone")
    workspace.ok_line(f"{n} dependency add {gone}")
    workspace.ok_line(f"{gone} cancel --reason x")
    assert f"{gone}  gone  cancelled  archive" in workspace.ok_line(f"{n} dependency")
    workspace.ok_line(f"{n} dependency remove {gone}")
    workspace.ok_line(f"{n} dependency remove {first} acme/web#202 acme/api#1")
    assert workspace.read_item(second)["depends_on"] == []
    for line in (
        f"{n} dependency remove {first}",
        f"{n} dependency remove acme/web#202",
        f"{n} dependency add",
        f"{n} dependency add 99",
    ):
        workspace.refuse(line, code=2)


def test_self_dependency_cycles_and_dead_items_are_refused(workspace: Backlog) -> None:
    first = workspace.add_item("first")
    second = workspace.add_item("second", "--depends-on", str(first))
    third = workspace.add_item("third", "--depends-on", str(second))
    workspace.refuse(f"{first} dependency add {first}", "cannot depend on itself", 2)
    workspace.refuse(f"{first} dependency add {third}", "dependency cycle", 2)
    dead = workspace.add_item("dead")
    workspace.ok(str(dead), "cancel", "--reason", "r")
    workspace.refuse(f"{first} dependency add {dead}", "will never be done", 2)
    workspace.refuse(f"add x --title t --depends-on {dead}", "archived as cancelled", 2)


def test_a_dead_dependency_offers_the_last_successor(workspace: Backlog) -> None:
    first, second, third = (workspace.add_item(name) for name in ("a", "b", "c"))
    top = workspace.add_item("top", "--depends-on", str(first))
    workspace.ok_line(f"{first} supersede --by {second} --reason r")
    workspace.ok_line(f"{second} supersede --by {third} --reason r")
    err = workspace.refuse(f"{top} dependency add {first}", "", 2)
    assert f"backlog {top} dependency add {third}" in err
    assert f"dependency add {second}" not in err
    workspace.ok_line(f"{top} dependency remove {first}")
    workspace.ok_line(f"{top} dependency add {third}")
    err = workspace.refuse(f"{third} dependency add {first}", "", 2)
    assert f"dependency add {third}" not in err  # never the item itself


@pytest.mark.parametrize("separator", [",", " ", ", "])
def test_lists_take_commas_spaces_or_both(workspace: Backlog, separator: str) -> None:
    first, second = workspace.add_item("first"), workspace.add_item("second")
    deps = separator.join([str(first), str(second)])
    third = workspace.add_item(
        "third", "--tags", separator.join(["a", "b"]), "--depends-on", deps
    )
    assert workspace.read_item(third)["tags"] == ["a", "b"]
    workspace.ok(str(third), "tag", "add", separator.join(["c", "d"]), "e")
    workspace.ok(str(third), "tag", "remove", separator.join(["c", "d"]))
    assert workspace.read_item(third)["tags"] == ["a", "b", "e"]
    workspace.ok(str(third), "dependency", "remove", deps)
    assert workspace.read_item(third)["depends_on"] == []


def test_archived_items_are_read_only(workspace: Backlog) -> None:
    number = str(workspace.add_item("work"))
    workspace.ok(number, "cancel", "--reason", "gone")
    for line in (
        f"{number} rename x",
        f"{number} priority low",
        f"{number} tag add x",
        f"{number} block add x",
        f"{number} unit add u",
        f"{number} brief append --section 'Agent handoff' --text x",
    ):
        err = workspace.refuse(line, "read-only")
        assert "backlog add" in err and "--depends-on" not in err  # a cancelled item
    assert "[archived]" in workspace.ok(number)
    done = workspace.add_item("done_one")
    workspace.finish_item(done)
    err = workspace.refuse(f"{done} priority low", "read-only")
    assert f"--depends-on {done}" in err
