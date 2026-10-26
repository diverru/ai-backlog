"""search, list, show and the cards."""

import signal
import time

import pytest
import yaml

from backlog_cli.command.search import SearchTimeLimit
from conftest import Backlog, days_from_now

HANDOFF = "--section 'Agent handoff'"


def seed(workspace: Backlog) -> int:
    number = workspace.add_item("search_work", "--tags", "search")
    workspace.add_unit(number, "engine")
    workspace.ok_line(f"{number}/engine link pr acme/api#123")
    workspace.ok_line(
        f"{number} brief append --section 'Known facts and sources' "
        "--text 'The deadlock appears under load.\nSecond line mentions deadlock too.'"
    )
    return number


def test_search_shows_where_it_matched(workspace: Backlog) -> None:
    number = seed(workspace)
    out = workspace.ok_line("search acme/api")
    assert "registry work.engine.pr.repo: acme/api" in out
    out = workspace.ok_line("search deadlock")
    text = workspace.workspace_file("details/0001_search_work.md").read_text()
    line = next(
        i for i, t in enumerate(text.splitlines(), 1) if "deadlock appears" in t
    )
    assert f"details Known facts and sources, line {line}: The deadlock appears" in out
    assert f"{number}  todo  search work" in out and "1 item matches." in out
    assert "No matches" in workspace.ok_line("search DEADLOCK --case-sensitive")
    assert workspace.ok_line("search search").count("registry title") == 1
    assert "deadlock" in workspace.ok_line("search DEADLOCK")


def test_plain_words_must_all_occur_and_no_character_is_special(
    workspace: Backlog,
) -> None:
    both = workspace.add_item("both", "--tags", "alpha")
    workspace.ok_line(
        f"{both} brief append {HANDOFF} --text 'beta here: f(x) [now] a.b'"
    )
    only = workspace.add_item("only", "--tags", "alpha")
    out = workspace.ok_line("search beta ALPHA")
    assert f"{both}  " in out and f"{only}  " not in out
    assert workspace.ok_line("search 'alpha beta'") == out
    for query in ("f(x)", "[now]", "a.b"):
        assert "1 item matches" in workspace.ok("search", query), query
    out = workspace.ok_line("search a.c")
    assert out.splitlines()[0] == "No matches"
    assert "searched as plain text; for a regular expression add --regex" in out
    for flag in ("--regex", "-E"):
        assert "1 item matches" in workspace.ok_line(f"search {flag} 'be.a|dead'")
    assert "searched as plain text" not in workspace.ok_line("search -E 'no.*thing'")


def test_search_skips_service_fields_and_the_exported_copies(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work", "--tags", "back")
    workspace.add_unit(number, "engine")
    workspace.add_unit(number, "study", "--kind", "research")
    for query in ("engine", "todo", "2026", "research"):
        assert "No matches" in workspace.ok("search", query), query
    for pattern in ("^2026", "^todo$"):
        assert "No matches" in workspace.ok("search", "-E", pattern)
    assert "work" in workspace.ok("search", "-E", "^back$")
    workspace.ok_line(f"{number} brief append {HANDOFF} --text unique-marker")
    (workspace.work / "copy.md").write_text(
        workspace.ok(str(number), "brief", "export")
    )
    assert workspace.ok("search", "unique-marker").count("unique-marker") == 1


def test_search_covers_the_archive_only_on_request_and_caps_matches(
    workspace: Backlog,
) -> None:
    number = seed(workspace)
    workspace.ok_line(f"{number} cancel --reason dropped")
    out = workspace.ok_line("search deadlock")
    assert out.splitlines()[0] == "No matches" and "1 archived items match" in out
    assert "backlog search deadlock --archive" in out
    assert "[archive: cancelled]" in workspace.ok_line("search deadlock --archive")
    many = workspace.add_item("many")
    text = "\n".join(f"needle {i}" for i in range(9))
    workspace.ok(
        str(many), "brief", "append", "--section", "Agent handoff", "--text", text
    )
    out = workspace.ok_line("search needle")
    assert out.count("details Agent handoff") == 5 and "+4 more" in out


def test_search_refuses_bad_queries(workspace: Backlog) -> None:
    workspace.add_item("work")
    for line in (
        "search ''",
        "search '   '",
        f"search {'a' * 201}",
        "search -E '(unclosed'",
    ):
        workspace.refuse(line, code=2)
    workspace.ok("search", "a" * 200)
    for old in ("--limit 1", "--offset 1", "--in details"):
        workspace.refuse(f"search work {old}", "unrecognized", 2)


def test_a_slow_regex_stops_at_the_time_limit(
    workspace: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SearchTimeLimit, "SECONDS", 1)
    number = workspace.add_item("work")
    workspace.ok(
        str(number),
        "brief",
        "append",
        "--section",
        "Agent handoff",
        "--text",
        "a" * 20000 + "!",
    )
    handler = signal.getsignal(signal.SIGALRM)
    started = time.monotonic()
    result = workspace.run("search", "-E", "(a|a?)+$")
    assert (
        result.code == 2 and "pattern took longer than 1 s; simplify it" in result.err
    )
    assert time.monotonic() - started < 5
    assert signal.getsignal(signal.SIGALRM) == handler
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
    assert workspace.run("search", "-E", "wor.").code == 0


def test_list_shows_units_dependencies_blockers_and_archive_reasons(
    workspace: Backlog,
) -> None:
    assert workspace.ok("list").splitlines()[0] == "workspace: ws"
    first = workspace.add_item("first")
    second = workspace.add_item("second", "--depends-on", str(first))
    workspace.ok_line(f"{second} due add 2026-11-05")
    workspace.ok_line(f"{second} block add 'Wait for ops' --waiting-on Ira")
    workspace.add_unit(second, "engine")
    workspace.ok_line(f"{second}/engine assign --task api:470 --agent 'Back agent'")
    workspace.add_unit(second, "study", "--kind", "research")
    workspace.ok_line(f"{second}/study assign --agent Ira --role analyst")
    workspace.ok_line(f"{second}/engine link pr acme/api#1")
    workspace.ok_line(f"{second}/engine merged --source gh")
    workspace.ok_line(
        f"{second}/engine released --at 2026-10-23 --source rs --tag v1.1 "
        "--no-post-release"
    )
    listing = workspace.ok("list")
    line = next(line for line in listing.splitlines() if "second" in line)
    assert "due 2026-11-05" in line and f"deps: {first}" in line
    assert "blocker b1: Wait for ops (waiting on Ira)" in listing
    assert "api:470 Back agent" in listing and "released v1.1" in listing
    assert "Ira (analyst)" in listing
    workspace.ok_line(f"{first} cancel --reason x")
    assert f"deps: {first}(cancelled)" in workspace.ok("list")
    workspace.ok_line(f"{second} block remove 1 --reason ok")
    assert "blocker b1" not in workspace.ok("list")
    other = workspace.add_item("other")
    workspace.ok_line(f"{other} cancel --reason '{'very long reason ' * 10}'")
    archived = next(
        line
        for line in workspace.ok_line("list --archive").splitlines()
        if "very" in line
    )
    assert archived.endswith("...") and len(archived.split("  - ", 1)[1]) <= 60
    workspace.ok_line("add long --title '" + "word " * 50 + "'")
    long = next(
        line for line in workspace.ok("list").splitlines() if "word word" in line
    )
    assert long.endswith("...") and len(long) < 110


def test_list_filters_and_sorts(workspace: Backlog) -> None:
    workspace.add_item("low_one", "--priority", "low", "--due", days_from_now(5))
    workspace.add_item("high_one", "--priority", "high", "--tags", "back")
    workspace.add_item("normal_one", "--priority", "normal", "--due", days_from_now(2))
    workspace.add_unit(1, "engine", "--kind", "research")
    workspace.ok_line("1/engine assign --task api:470 --agent 'Back Agent' --role back")

    def numbers(*flags: str) -> list[str]:
        lines = workspace.ok("list", *flags).splitlines()[1:]
        return [line.split()[0] for line in lines if line[:4].strip().isdigit()]

    assert numbers("--sort", "number") == ["1", "2", "3"]
    assert numbers("--sort", "priority") == ["2", "3", "1"]
    assert numbers("--sort", "due") == ["3", "1", "2"]
    assert numbers("--priority", "high") == ["2"] and numbers("--tag", "back") == ["2"]
    assert numbers("--status", "wip") == ["1"]
    for needle in ("back agent", "API:47", "back"):
        assert numbers("--assignee", needle) == ["1"]
    assert numbers("--can-start") == ["2", "3"]  # todo, nothing blocks them
    assert "No items." in workspace.ok_line("list --assignee nobody")
    for line in (
        "list --sort dua",
        "list --status stuk",
        "list --remind-before 2026-13-01",
        "list --assignee ''",
        "list --attention --archive",
        "list --can-start --archive",
    ):
        workspace.refuse(line, code=2)
    assert "did you mean stuck?" in workspace.run("list", "--status", "stuk").err


def test_can_start_needs_todo_no_blocker_and_done_dependencies(
    workspace: Backlog,
) -> None:
    base = workspace.add_item("base")
    top = workspace.add_item("top", "--depends-on", str(base))
    blocked = workspace.add_item("blocked")
    workspace.ok_line(f"{blocked} block add waiting")
    workspace.start_item(base)
    out = workspace.ok_line("list --can-start")
    assert out.strip().endswith("No items.")  # waiting, blocked and wip: none starts
    workspace.ok_line(f"{base}/work done --result r --source s")
    workspace.ok_line(f"{base} done --result r --source s")
    assert f"{top:>4}  " in workspace.ok_line("list --can-start")
    assert "Can start now:" in workspace.ok_line("list --attention")


def test_attention_shows_each_group_and_omits_the_empty_ones(
    workspace: Backlog,
) -> None:
    first = workspace.add_item(
        "first", "--reminder", days_from_now(-1), "--due", days_from_now(-2)
    )
    workspace.ok_line(f"{first} block add 'Needs an admin' --waiting-on admin")
    ready = workspace.add_merged_unit("ready", pr_number=2)
    workspace.release(f"{ready}/engine", "--no-post-release")
    action = workspace.add_merged_unit("action", pr_number=3)
    workspace.add_check(action, "check")
    workspace.release(f"{action}/engine")
    merged = workspace.add_merged_unit("merged_one")
    started = workspace.add_item("started")
    workspace.add_unit(started, "engine")
    workspace.ok_line(f"{started}/engine assign --agent A")
    workspace.ok_line(f"{started}/engine unassign --agent A")
    stuck = workspace.add_item("stuck")
    workspace.add_unit(stuck, "engine")
    workspace.ok_line(f"{stuck}/engine cancel --reason dropped")
    out = workspace.ok_line("list --attention")
    assert [line for line in out.splitlines() if line.endswith(":")] == [
        "Unresolved blockers:",
        "Reminders due:",
        "Overdue:",
        "Ready to close:",
        "Pending post-release actions:",
        "Merged, waiting for release:",
        "In progress without an assignee:",
        "Stuck (every unit cancelled or superseded):",
    ]
    assert f"  {first} blocker b1: Needs an admin (waiting on admin)" in out
    assert f"{action}/engine check check: Check check" in out
    assert f"{ready} ready: backlog {ready} done" in out
    assert f"{merged}/engine acme/api#" in out and f"{started}/engine: started" in out
    narrowed = workspace.ok_line("list --attention --priority high")
    assert narrowed.strip().endswith("Nothing needs attention.")


def test_ready_to_close_names_what_it_unblocks(workspace: Backlog) -> None:
    base = workspace.add_item("base")
    top = workspace.add_item("top", "--depends-on", str(base))
    other = workspace.add_item("other", "--depends-on", str(base))
    workspace.add_item("both", "--depends-on", f"{base},{other}")
    workspace.finish_units(base)
    assert f"(unblocks {top}, {other})" in workspace.ok("list")
    assert f"(unblocks {top}, {other})" in workspace.ok_line("list --attention")
    waiting = workspace.add_item("waiting")
    assert f"backlog {waiting} done" not in workspace.ok("list")
    assert (
        workspace.run(
            str(base), "done", "--dry-run", "--result", "r", "--source", "s"
        ).code
        == 0
    )
    assert (
        workspace.run(
            str(waiting), "done", "--dry-run", "--result", "r", "--source", "s"
        ).code
        == 1
    )


def test_the_card_shows_everything_on_one_screen(workspace: Backlog) -> None:
    base = workspace.add_item("base")
    number = workspace.add_merged_unit("work", pr_number=7)
    n = str(number)
    workspace.ok_line(f"{n} dependency add {base}")
    workspace.ok_line(f"{n} block add 'Needs an admin' --waiting-on admin")
    workspace.ok_line(f"{n} tag add back")
    workspace.add_check(number, "check")
    workspace.ok_line(
        f"{n}/engine merged --pr acme/api#8 --source s --correction 'wrong PR'"
    )
    workspace.release(f"{n}/engine")
    workspace.add_unit(number, "study", "--kind", "research")
    workspace.ok_line(
        f"{n}/engine post_release fail check --finding 'p99 is 4 s' --source panel"
    )
    card = workspace.ok(n).splitlines()
    assert card[0] == f"{number}  work" and len(card) <= 26
    text = "\n".join(card)
    for expected in (
        "status wip, priority normal",
        "tags back",
        f"depends on: {base} (NOT DONE: still active)",
        "b1  Needs an admin (waiting on admin)",
        "engine  pr  post_release  acme/api#8  Agent  released v1.2.0",
        "study  research  todo",
        "engine/check  check  pending  Check check",
        "instructions: Look",
        "p99 is 4 s (source: panel)",
        "engine merge, ",
        "wrong PR (was pr acme/api#7",
        "closing: blocked: ",
    ):
        assert expected in text, expected
    unit_card = workspace.ok(f"{n}/engine")
    assert "release v1.2.0 at 2026-10-23T12:00:00Z (source: release_status" in unit_card
    long = workspace.add_merged_unit("long")
    workspace.ok_line(
        f"{long}/engine post_release add c --kind verification --title T "
        f"--instructions '{'Look at the panel ' * 30}'"
    )
    line = next(
        line for line in workspace.ok(str(long)).splitlines() if "instructions:" in line
    )
    assert line.endswith("...") and len(line.strip()) < 230


def test_the_card_of_a_confirmed_check_shows_its_result(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_check(number, "check")
    workspace.release(f"{number}/engine")
    workspace.ok_line(
        f"{number}/engine post_release done check --result 'p99 is 1 s' "
        "--source 'the panel' --at 2026-10-24"
    )
    card = workspace.ok(str(number), "show")
    assert "confirmed 2026-10-24T23:59:59Z: p99 is 1 s (source: the panel)" in card


def test_the_card_of_an_archived_item_and_show_full(workspace: Backlog) -> None:
    base = workspace.add_item("base")
    top = workspace.add_item("top", "--depends-on", str(base))
    workspace.finish_item(base, "--at", "2026-10-24")
    workspace.finish_item(top)
    card = workspace.ok(str(top))
    assert f"{top}  top  [archived]" in card and "status done" in card
    assert f"depends on: {base} (done)" in card and "still active" not in card
    assert "closed: done at " in card and "(source: s)" in card and "next:" not in card
    assert "closed: done at 2026-10-24T23:59:59Z" in workspace.ok(str(base))
    full = workspace.ok(str(top), "show", "--full")
    assert full.splitlines()[0] == "# source: archive"
    assert yaml.safe_load(full)["id"].endswith("_top")
    unit = workspace.ok(f"{top}/work", "show")
    assert "item" in unit.splitlines()[0]
    active = workspace.add_merged_unit("active")
    assert (
        workspace.ok(str(active), "show", "--full").splitlines()[0]
        == "# source: active"
    )
    superseded = workspace.add_item("old")
    workspace.ok_line(f"{superseded} supersede --by {active} --reason r")
    assert f"superseded by {active} at " in workspace.ok(str(superseded))


def test_unknown_addresses_are_clear_errors(workspace: Backlog) -> None:
    err = workspace.refuse("1", "workspace 'ws'", 2)
    assert "The workspace is empty. Add the first item: backlog add SLUG" in err
    workspace.add_item("work")
    err = workspace.refuse("9", "workspace 'ws'", 2)
    assert "is empty" not in err
    for line in (
        "7 dependency",
        "7 unit",
        "1/missing",
        "-1 show",
        "١ show",
        "8/",
        "1//db show",
    ):
        workspace.refuse(line, code=2)
    assert "-1 is not an item number" in workspace.run("-1", "show").err
    assert "unit address is N/UNIT, e.g. 8/engine" in workspace.run("8/").err
    assert "bad address" in workspace.run("1//db", "show").err
    assert "work only for released" in workspace.run("1,2", "show").err
    assert workspace.run("--workspace", "ws", "list").code == 0
    assert workspace.run("list", "--workspace", "ws").code == 0


def test_attention_lists_todo_units_of_a_wip_item(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    assert "Units without an assignee" not in workspace.ok_line("list --attention")
    workspace.start_item(number)
    workspace.add_unit(number, "engine")
    out = workspace.ok_line("list --attention")
    assert "Units without an assignee" in out
    assert f"{number}/engine: work: backlog {number}/engine assign --agent NAME" in out
    workspace.ok_line(f"{number}/engine assign --agent B")
    assert "Units without an assignee" not in workspace.ok_line("list --attention")
