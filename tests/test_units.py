"""Units, assignees, item status, and ending units and items."""

import argparse

from backlog_cli.cli import Cli
from backlog_cli.command.router import ActionTable
from conftest import Backlog


def test_unit_add_defaults_to_pr_and_refuses_bad_input(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    assert "Added unit 1/engine (pr, todo)" in workspace.add_unit(number, "engine")
    unit = workspace.read_unit(number, "engine")
    assert (unit["kind"], unit["status"], unit["pr"]) == ("pr", "todo", None)
    assert unit["merge"] is None and unit["release"] is None
    workspace.add_unit(number, "study", "--kind", "research")
    assert "pr" not in workspace.read_unit(number, "study")
    for line in (
        f"{number} unit add",
        f"{number} unit add Bad-Id",
        f"{number} unit add x --kind pull",
        f"{number} unit add x --pr a/b#1",
        f"{number} unit add {'u' * 61}",
        "9 unit add engine",
    ):
        workspace.refuse(line, code=2)
    workspace.refuse(f"{number} unit add engine", "already has a unit")


def test_assign_adds_assignees_and_starts_the_unit(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    address = f"{number}/engine"
    out = workspace.ok_line(
        f'{address} assign --agent "Back agent" --task api:9 --role back'
    )
    assert f'{address}: assigned agent "Back agent", task api:9, role back' in out
    assert f"{address}: todo -> wip" in out
    assert workspace.read_unit(number, "engine")["assignees"] == [
        {"project": "api", "task_seq": 9, "agent": "Back agent", "role": "back"}
    ]
    out = workspace.ok_line(f"{address} assign --agent Second")
    assert "added an assignee; still assigned: api:9 Back agent" in out
    assert f'backlog {address} unassign --agent "NAME"' in out
    assert "adds an assignee" in workspace.ok_line(f"{address} assign --help")
    workspace.ok_line(f"{address} unassign --agent Second")
    workspace.ok_line(f"{address} unassign --task api:9")
    unit = workspace.read_unit(number, "engine")
    assert unit["assignees"] == [] and unit["status"] == "wip"  # no status change


def test_assign_refuses_bad_input(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    address = f"{number}/engine"
    workspace.refuse(f"{address} assign", code=2)
    workspace.refuse(f"{address} assign --agent A --task bad", code=2)
    workspace.refuse(f'{address} assign --agent " "', code=2)
    workspace.ok_line(f"{address} assign --agent A")
    workspace.refuse(f"{address} assign --agent A", "already assigned")
    workspace.refuse(f"{address} unassign", code=2)
    workspace.refuse(f"{address} unassign --agent Nobody", "Nobody")
    workspace.ok_line(f"{address} cancel --reason x")
    workspace.refuse(f"{address} assign --agent B")


def test_an_item_has_no_assignees_and_no_status_to_set(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    for word in ("assign --agent A", "unassign --agent A", "return_to_todo --reason r"):
        err = workspace.refuse(f"{number} {word}", "", 2)
        assert f"is a unit action: backlog N/UNIT {word.split()[0]}" in err
    for word in ("status plan", "plan", "wip"):
        workspace.refuse(f"{number} {word}", code=2)


def test_a_unit_returns_to_todo_only_with_a_reason_from_wip(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    address = f"{number}/engine"
    workspace.refuse(f"{address} return_to_todo --reason r", "already todo")
    workspace.ok_line(f"{address} assign --agent A")
    workspace.refuse(f"{address} return_to_todo", code=2)
    workspace.refuse(f'{address} return_to_todo --reason " "', code=2)
    out = workspace.ok_line(f'{address} return_to_todo --reason "Agent stopped"')
    assert f"{address}: wip -> todo" in out
    assert workspace.read_unit(number, "engine")["returns"][0]["reason"] == (
        "Agent stopped"
    )
    merged = workspace.add_merged_unit("merged_one")
    workspace.refuse(f"{merged}/engine return_to_todo --reason r", "never goes back")


def test_the_item_status_follows_its_units(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    for unit in ("a", "b"):
        workspace.add_unit(number, unit)
    status = lambda: workspace.read_item(number)["status"]  # noqa: E731
    workspace.ok_line(f"{number}/a cancel --reason no")  # a todo unit never started
    assert status() == "todo"
    workspace.ok_line(f"{number}/b assign --agent A")
    assert status() == "wip"
    workspace.ok_line(f"{number}/b return_to_todo --reason paused")
    assert status() == "todo"
    merged = workspace.add_merged_unit("merged_one")
    workspace.add_unit(merged, "frontend")  # a todo unit next to a merged one
    assert workspace.read_item(merged)["status"] == "wip"
    assert f"{merged:>4}  " not in workspace.ok_line("list --can-start")


def test_research_goes_todo_wip_done_and_a_pr_unit_is_never_done_by_hand(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "study", "--kind", "research")
    address = f"{number}/study"
    workspace.refuse(f"{address} done --result r --source s", "assign it first")
    workspace.ok_line(f"{address} assign --agent Researcher")
    workspace.ok_line(f'{address} done --result "The answer" --source notes')
    done = workspace.read_unit(number, "study")
    assert done["completion"]["evidence"]["result"] == "The answer"
    workspace.refuse(f"{number}/study done --result r --source s")  # finished
    workspace.add_unit(number, "engine")
    workspace.ok_line(f"{number}/engine assign --agent A")
    workspace.refuse(f"{number}/engine done --result r --source s", "never marked")
    workspace.refuse(f"{number}/study merged --source gh", "research unit")
    workspace.refuse(f"{number}/study link pr acme/api#8", "research")


def test_done_archives_the_item_and_lists_every_obstacle(workspace: Backlog) -> None:
    dependency = workspace.add_item("dependency")
    number = workspace.add_merged_unit("work", "engine", 123)
    workspace.add_check(number, "check")
    workspace.release(f"{number}/engine")
    workspace.add_unit(number, "frontend")
    workspace.add_unit(number, "backend")
    workspace.ok_line(f"{number}/backend link pr acme/api#203")
    workspace.ok_line(f"{number}/backend merged --source gh")
    workspace.add_unit(number, "study", "--kind", "research")
    workspace.ok_line(f"{number} dependency add {dependency}")
    workspace.ok_line(f"{number} block add Wait")
    text = workspace.refuse(f"{number} done --result r --source s")
    assert text.startswith(f"Cannot apply 'done' to {number}. Nothing changed.")
    for obstacle in (
        f"{number}/engine/check — Check check: not confirmed",
        f"{number}/backend — PR acme/api#203: no production release recorded",
        f"{number}/frontend — pr unit: no merge recorded (status todo)",
        f"backlog {number}/frontend assign --agent NAME",
        f"{number}/study — research: research not finished",
        "is not archived yet",
        "blocker b1",
        f'backlog {number}/engine post_release done check --result "..." --source',
        f"backlog {number}/backend released --at DATE",
        f"backlog {number} block remove b1",
    ):
        assert obstacle in text, obstacle
    lines = [line for line in text.splitlines() if line.strip()]
    assert len(lines) == len(set(lines))  # no line is repeated


def test_done_closes_and_archives_in_one_command(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    workspace.release(f"{number}/engine", "--no-post-release")
    expected = f'backlog {number} done --result "..." --source "..."'
    assert f"ready to close: {expected}" in workspace.ok("list")
    assert f"next: ready to close: {expected}" in workspace.ok(str(number))
    out = workspace.ok_line(
        f'{number} done --result "All criteria met" --source "I looked" '
        f"--at {workspace.today()}"
    )
    assert "archived as" in out
    item = workspace.read_item(number, archive=True)
    assert (item["status"], item["completion"]["outcome"]) == ("done", "done")
    assert item["completion"]["evidence"]["result"] == "All criteria met"
    assert not item["completion"]["evidence"]["observed_at"].endswith("T23:59:59Z")
    assert all(not i["id"].startswith("0001") for i in workspace.read_items())
    for line in (
        f"{number}/engine return_to_todo --reason x",
        f"{number} rename x",
        f"{number} unit add more",
        f"{number} cancel --reason x",
    ):
        err = workspace.refuse(line, "read-only")
        assert f"--depends-on {number}" in err


def test_done_needs_units_a_result_and_a_source(workspace: Backlog) -> None:
    number = workspace.add_item("question")
    err = workspace.refuse(f"{number} done --result r --source s", "has no units")
    assert f"backlog {number} unit add NAME --kind pr" in err
    assert f'backlog {number} cancel --reason "..."' in err
    assert "ready to close" not in workspace.ok("list")
    assert f"backlog {number} unit add NAME --kind pr" in workspace.ok(str(number))
    for line in (
        f"{number} done --source s",
        f"{number} done --result r",
        f'{number} done --result " " --source s',
    ):
        workspace.refuse(line, code=2)
    workspace.ok_line(f'{number} cancel --reason "a question, not work"')
    assert workspace.read_item(number, archive=True)["status"] == "cancelled"


def test_a_cancelled_unit_leaves_the_item_stuck_and_closable_only_by_cancel(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    workspace.ok_line(f"{number}/engine cancel --reason dropped")
    assert workspace.read_item(number)["status"] == "todo"
    err = workspace.refuse(f"{number} done --result r --source s")
    assert "every unit is cancelled or superseded" in err
    assert f"   {number}  stuck" in workspace.ok("list", "--status", "stuck")
    for output in (workspace.ok("list"), workspace.ok(str(number))):
        assert "blocked: every unit is cancelled or superseded. Next:" in output
    assert "status stuck," in workspace.ok(str(number))
    assert "Stuck" in workspace.ok("list", "--attention")


def test_the_card_of_a_blocked_item_names_the_first_obstacle(
    workspace: Backlog,
) -> None:
    blocking = workspace.add_item("blocking")
    number = workspace.add_merged_unit("finished")
    workspace.release(f"{number}/engine", "--no-post-release")
    workspace.ok_line(f"{number} dependency add {blocking}")
    shown = workspace.ok(str(number))
    assert "ready to close" not in shown
    assert "closing: blocked: dependency 0001_blocking is not archived yet" in shown
    workspace.ok_line(f"{blocking} cancel --reason x")
    shown = workspace.ok(str(number))
    assert (
        "closing: blocked: dependency 0001_blocking is archived as cancelled" in shown
    )
    assert f"Next: backlog {number} dependency remove 1 or " in shown


def test_an_unstarted_item_says_what_it_waits_for(workspace: Backlog) -> None:
    base = workspace.add_item("base")
    number = workspace.add_item("work", "--depends-on", str(base))
    workspace.add_unit(number, "engine")
    card = workspace.ok(str(number))
    assert "waiting: dependency 0001_base is not archived yet" in card
    assert "merged" not in card and "next:" not in card
    out = workspace.ok_line(f"{number}/engine assign --agent A")
    assert f"note: item {number} still waits for {base} (todo)" in out
    other = workspace.add_item("other")
    workspace.add_unit(other, "engine")
    card = workspace.ok(str(other))
    assert (
        f"not started: assign an agent to start a unit: backlog {other}/engine" in card
    )
    assert "note:" not in workspace.ok_line(f"{other}/engine assign --agent A")


def test_a_released_unit_without_pending_actions_can_be_cancelled(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.release(f"{number}/engine", "--no-post-release")
    workspace.add_unit(number, "other")
    workspace.ok_line(f"{number} cancel --reason x")  # nothing is merged any more


def test_long_titles_are_cut_in_refusals_and_attention(workspace: Backlog) -> None:
    title = "word " * 40
    workspace.ok_line(f"add long --title '{title}' --reminder 2026-10-01")
    attention = workspace.ok_line("list --attention")
    assert title.strip() not in attention and "..." in attention
    err = workspace.refuse("1 done --result r --source s", "...")
    assert title.strip() not in err


def test_cancel_and_supersede_of_an_item(workspace: Backlog) -> None:
    other = workspace.add_item("other")
    started = workspace.add_item("started", "--depends-on", str(other))
    workspace.add_unit(started, "engine")
    workspace.ok_line(f"{started}/engine assign --agent Agent --task api:456")
    waiting = workspace.add_item("waiting", "--depends-on", str(started))
    s = str(started)
    workspace.refuse(f"{s} supersede --reason x", code=2)  # --by is needed
    workspace.refuse(f"{s} cancel", code=2)  # a reason is needed
    workspace.refuse(f'{s} cancel --reason " "', code=2)
    workspace.refuse(f"{s} supersede --by {s} --reason x", "cannot supersede itself")
    out = workspace.ok_line(f"{s} supersede --by {other} --reason Replaced")
    assert f"{waiting} — waiting" in out
    assert "Units closed with the item" in out
    assert f"{started}/engine: assignee left: agent Agent, task api:456" in out
    item = workspace.read_item(started, archive=True)
    assert item["status"] == "superseded"
    assert item["completion"]["follow_up"] == "0001_other"
    assert item["work"][0]["status"] == "wip"
    assert f"superseded by {other}" in workspace.ok("list", "--archive")


def test_a_follow_up_must_be_able_to_carry_the_work(workspace: Backlog) -> None:
    old, dropped, ready = (workspace.add_item(n) for n in ("old", "dropped", "ready"))
    third = workspace.add_item("third")
    workspace.ok_line(f"{dropped} cancel --reason x")
    workspace.finish_units(ready)
    err = workspace.refuse(f"{old} supersede --by {dropped} --reason r")
    assert "cannot carry the work" in err
    workspace.refuse(f"{old} supersede --by 99 --reason r", code=2)
    err = workspace.refuse(f"{ready} supersede --by {third} --reason r")
    assert "all its work is finished" in err and f"backlog {ready} done" in err
    follow = workspace.add_item("follow", "--depends-on", str(old))
    workspace.ok_line(f"{old} supersede --by {third} --reason r")
    err = workspace.refuse(f"{third} supersede --by {follow} --reason r")
    assert "wait for itself" in err
    workspace.ok_line(f"{follow} dependency remove {old}")
    workspace.ok_line(f"{third} supersede --by {follow} --reason r")


def test_a_merged_unit_cannot_be_cancelled_and_a_revert_undoes_it(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_unit(number, "other")
    successor = workspace.add_item("next")
    for line in (
        f"{number}/engine cancel --reason x",
        f"{number}/engine supersede --reason x --by other",
        f"{number} cancel --reason x",
        f"{number} supersede --reason x --by {successor}",
    ):
        err = workspace.refuse(line, "the code is already in the trunk")
        assert f"backlog {number} unit add NAME --kind pr" in err
        assert f"backlog {number}/engine,{number}/NAME released" in err
    workspace.add_unit(number, "revert")
    workspace.ok(f"{number}/revert", "assign", "--agent", "R")
    workspace.ok_line(f"{number}/revert merged --pr acme/api#8000 --source s")
    workspace.ok_line(
        f"{number}/engine,{number}/revert released --at {workspace.now_utc()} "
        f"--source s --no-post-release {number}/engine {number}/revert"
    )
    assert workspace.read_unit(number, "revert")["status"] == "done"
    workspace.ok_line(f"{number}/other cancel --reason x")
    workspace.ok_line(f"{number} done --result reverted --source s")
    assert workspace.read_item(number, archive=True)["status"] == "done"


def test_a_unit_is_replaced_by_an_open_unit_of_the_same_item(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    other = workspace.add_item("other")
    for unit in ("a", "b", "c"):
        workspace.add_unit(number, unit, "--kind", "research")
    workspace.add_unit(other, "fix")
    workspace.ok_line(f"{number}/a supersede --reason r --by b")
    err = workspace.refuse(f"{number}/b supersede --reason r --by a", "", 2)
    assert "can only be replaced by an open unit" in err
    workspace.refuse(f"{number}/b supersede --reason r --by b", "supersede itself", 2)
    workspace.refuse(
        f"{number}/b supersede --reason r --by {other}/fix", "another item", 2
    )
    workspace.ok_line(f"{number}/c supersede --reason r --by 0001_work/b")
    assert workspace.read_unit(number, "c")["completion"]["superseded_by"] == "b"


def test_ending_an_item_lists_the_pending_actions_and_the_assignees_left(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_check(number, "one")
    workspace.add_check(number, "two")
    replacement = workspace.add_item("next")
    workspace.add_unit(number, "api")
    workspace.add_unit(number, "frontend")
    workspace.release(f"{number}/engine")
    for line in (
        f"{number} cancel --reason x",
        f"{number} supersede --by {replacement} --reason x",
    ):
        err = workspace.refuse(line)
        for name in ("one", "two"):
            assert (
                f'backlog {number}/engine post_release cancel {name} --reason "..."'
                in err
            )
    workspace.ok_line(f"{number}/api assign --agent Back --task api:456")
    for name in ("one", "two"):
        workspace.ok_line(
            f"{number}/engine post_release cancel {name} --reason r --not-needed"
        )
    out = workspace.ok_line(f"{number} cancel --reason x")
    assert f"{number}/api" in out and f"{number}/frontend" in out
    assert f"{number}/api: assignee left: agent Back, task api:456 — tell them" in out


def test_no_parser_field_collides_with_an_argparse_attribute() -> None:
    """A field named like `description` would be read from the parser, not the user."""
    reserved = set(dir(argparse.ArgumentParser)) | {"prog", "usage", "epilog"}
    parsers = [(action.WORDS, action.build_parser()) for action in ActionTable.ACTIONS]
    parsers += [
        ((command.NAME,), command.Parser(underscores_to_dashes=True))
        for command in Cli.COMMANDS
    ]
    for words, parser in parsers:
        for argument in parser._actions:
            assert argument.dest not in reserved, (words, argument.dest)


def test_the_last_unit_to_end_tells_the_item_is_ready_to_close(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "a", "--kind", "research")
    workspace.add_unit(number, "b", "--kind", "research")
    for unit in ("a", "b"):
        workspace.ok_line(f"{number}/{unit} assign --agent A")
    ready = f"{number}: all units finished; close it: backlog {number} done"
    first = workspace.ok_line(f"{number}/a done --result r --source s")
    assert ready not in first
    last = workspace.ok_line(f"{number}/b done --result r --source s")
    assert ready in last and last.count("all units finished") == 1
