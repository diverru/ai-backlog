"""merged, released, group release, corrections and the dates they take."""

from datetime import UTC, datetime, timedelta

from conftest import Backlog, days_from_now


def start_unit(workspace: Backlog, slug: str = "work") -> int:
    number = workspace.add_item(slug)
    workspace.add_unit(number, "engine")
    workspace.ok(f"{number}/engine", "assign", "--agent", "Agent")
    return number


def test_merge_is_recorded_with_its_source(workspace: Backlog) -> None:
    number = start_unit(workspace)
    workspace.ok_line(
        f"{number}/engine merged --pr acme/api#123 --source 'gh pr view' "
        "--at 2026-10-23T10:00:00Z"
    )
    unit = workspace.read_unit(number, "engine")
    assert unit["status"] == "merged"
    assert unit["pr"] == {"repo": "acme/api", "number": 123}
    merge = unit["merge"]
    assert merge["merged_at"] == "2026-10-23T10:00:00Z"
    evidence = merge["evidence"]
    assert (evidence["source"], evidence["result"]) == ("gh pr view", "merged")
    assert evidence["observed_at"] == "2026-10-23T10:00:00Z"
    other = start_unit(workspace, "other")
    workspace.ok_line(
        f"{other}/engine merged --pr acme/api#5 --source 'the user said so' "
        '--result "merged into develop"'
    )
    merge = workspace.read_unit(other, "engine")["merge"]
    assert merge["merged_at"] is None and merge["evidence"]["observed_at"] is None
    assert merge["evidence"]["result"] == "merged into develop"
    workspace.refuse(
        f"{start_unit(workspace, 'x')}/engine merged --pr acme/api#9", "", 2
    )


def test_the_pr_comes_from_link_pr_or_the_flag(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    address = f"{number}/engine"
    err = workspace.refuse(f"{address} merged --source gh", "no PR is set")
    assert err.index("link pr") < err.index("merged --pr OWNER")
    assert "acme/api#7" in workspace.ok_line(f"{address} link pr acme/api#7")
    workspace.ok_line(f"{address} link pr other/repo#8")  # a PR is replaced until merge
    assert workspace.ok_line(f"{address} link pr acme/api#9").count("acme/api#9") == 1
    for bad in ("api", "api#7", "acme/api#", "#7", "acme/api#0", "acme/api#1234567890"):
        workspace.refuse(f"{address} link pr {bad}", code=2)
    workspace.refuse(
        f"{address} merged --pr acme/api#2 --source gh", "Link the right one"
    )
    workspace.ok_line(f"{address} merged --source gh")
    assert workspace.read_unit(number, "engine")["pr"]["number"] == 9
    workspace.refuse(f"{address} link pr acme/api#8", "merge is already recorded")


def test_the_pr_is_stored_lower_case(workspace: Backlog) -> None:
    first = workspace.add_merged_unit("one", repo="Acme/API", pr_number=777)
    assert workspace.read_unit(first, "engine")["pr"]["repo"] == "acme/api"


def test_merged_and_released_need_a_source_and_released_needs_at(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.refuse(f"{number}/engine merged --pr acme/api#1", "--source", 2)
    address = f"{number}/engine"
    for line, missing in (
        (f"{address} released --source s --no-post-release", "--at"),
        (f"{address} released --at 2026-10-23 --no-post-release", "--source"),
    ):
        workspace.refuse(line, missing, 2)
    workspace.refuse(f"{address} released --at x --source s --manual", "--manual", 2)
    err = workspace.refuse(
        f"{address} released --at 2026-10-23 --source s --no-post-releas", "", 2
    )
    assert "Did you mean --no-post-release" in err
    workspace.refuse(f"{number} released --at 2026-10-23 --source s", "N/UNIT", 2)
    workspace.refuse(
        f"{address} released --at 2026-10-23 --source s --tag 'v 1'", "whitespace", 2
    )


def test_release_records_the_facts_and_finishes_a_unit_with_no_actions(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    out = workspace.release(f"{number}/engine", "--no-post-release")
    assert (
        f"{number}/engine: merged -> done (released at 2026-10-23T12:00:00Z, "
        "tag v1.2.0)" in out
    )
    unit = workspace.read_unit(number, "engine")
    release = unit["release"]
    assert set(release) == {"tag", "released_at", "evidence"}
    assert (release["tag"], release["released_at"]) == (
        "v1.2.0",
        "2026-10-23T12:00:00Z",
    )
    assert release["evidence"]["source"] == "release_status api 123"
    assert release["evidence"]["result"] == "released"
    assert unit["post_release_required"] is False
    assert unit["completion"]["evidence"]["result"] == (
        "release recorded; no post-release actions required"
    )
    workspace.refuse(
        f"{number}/engine released --at 2026-10-23 --source s", "only a merged"
    )
    other = workspace.add_merged_unit("other")
    workspace.ok_line(
        f"{other}/engine released --at 2026-10-24 --source s --no-post-release"
    )
    assert workspace.read_unit(other, "engine")["release"]["tag"] is None
    assert "released 2026-10-24" in workspace.ok("list")


def test_the_post_release_decision_is_explicit(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    address = f"{number}/engine"
    err = workspace.refuse(f"{address} released --at 2026-10-23 --source s --tag v1")
    assert "post-release work is undecided" in err
    assert (
        f"backlog {address} released --at 2026-10-23 --source s --tag v1 "
        f"--no-post-release {address}" in err
    )
    workspace.add_check(number, "check")
    err = workspace.refuse(
        f"{address} released --at 2026-10-23 --source s --no-post-release"
    )
    assert "has post-release actions" in err
    assert f"backlog {address} post_release cancel check" in err
    assert "released --at" not in err.split("cancel them first")[1]
    workspace.release(address)
    unit = workspace.read_unit(number, "engine")
    assert unit["status"] == "post_release" and unit["completion"] is None
    assert workspace.read_item(number)["status"] == "wip"


def test_a_group_release_writes_the_same_release_to_each_unit_or_nothing(
    workspace: Backlog,
) -> None:
    first = workspace.add_merged_unit("first")
    second = workspace.add_merged_unit("second")
    workspace.add_check(first, "check")
    a, b = f"{first}/engine", f"{second}/engine"
    pair = f"{a},{b}"
    flags = "--at 2026-10-23T12:00:00Z --source 'release_status' --tag v1.2.0"
    err = workspace.refuse(f"{pair} released {flags}", b)
    assert (
        f"backlog {pair} released {flags} --no-post-release {b}".replace(
            "'release_status'", "release_status"
        )
        in err
    )
    assert len([line for line in err.splitlines() if line.strip()]) == len(
        set(line for line in err.splitlines() if line.strip())
    )
    workspace.refuse(f"{pair} released {flags} --no-post-release", "needs the unit", 2)
    workspace.refuse(f"{pair} released {flags} --no-post-release 9/other", "", 2)
    err = workspace.refuse(f"{pair} released {flags} --no-post-release {a}", b)
    assert "has post-release actions" in err
    err = workspace.refuse(
        f"{pair} released {flags} --no-post-release {b} {b}", "twice"
    )
    third = workspace.add_item("third")
    workspace.add_unit(third, "api")
    workspace.refuse(
        f"{pair},{third}/api released {flags} --no-post-release {b}",
        "no PR recorded",
    )
    workspace.refuse(f"{a},{a} released {flags}", "listed twice", 2)
    workspace.refuse(f"{a},{b} merged --source s", "", 2)
    out = workspace.ok_line(f"{pair} released {flags} --no-post-release {b}")
    assert f"{a}: merged -> post_release" in out and f"{b}: merged -> done" in out
    for number in (first, second):
        assert workspace.read_unit(number, "engine")["release"]["tag"] == "v1.2.0"


def test_group_arguments_take_one_value_or_several(workspace: Backlog) -> None:
    first = workspace.add_merged_unit("one")
    second = workspace.add_merged_unit("two")
    third = workspace.add_merged_unit("three")
    units = [f"{n}/engine" for n in (first, second, third)]
    flags = "--at 2026-10-23T12:00:00Z --source s"
    out = workspace.ok_line(
        f"{','.join(units[:2])} released {flags} --no-post-release "
        f"'{units[0]} {units[1]}'"
    )
    assert f"{units[0]}: merged -> done" in out
    workspace.ok_line(f"{units[2]} released {flags} --no-post-release")
    assert workspace.read_unit(third, "engine")["status"] == "done"


def test_a_merge_correction_keeps_what_it_does_not_give(workspace: Backlog) -> None:
    number = start_unit(workspace)
    address = f"{number}/engine"
    workspace.ok_line(
        f"{address} merged --pr acme/api#7 --at 2026-10-01T10:00:00Z "
        "--source 'original source' "
        "--result 'Reviewed tests and CI passed'"
    )
    workspace.refuse(f"{address} merged --pr acme/api#8 --source s", "--correction")
    workspace.refuse(
        f"{address} merged --source 'original source' --pr acme/api#7 --correction same",
        "changes no value",
    )
    workspace.ok_line(f"{address} merged --source corrected --correction 'source typo'")
    workspace.ok_line(f"{number} priority low")  # another write
    unit = workspace.read_unit(number, "engine")
    evidence = unit["merge"]["evidence"]
    assert (evidence["result"], evidence["source"]) == (
        "Reviewed tests and CI passed",
        "corrected",
    )
    assert evidence["observed_at"] == "2026-10-01T10:00:00Z"
    old = unit["corrections"][0]["old_evidence"]
    assert old["result"] == "Reviewed tests and CI passed"
    assert (old["source"], old["observed_at"]) == (
        "original source",
        "2026-10-01T10:00:00Z",
    )
    workspace.ok_line(
        f"{address} merged --pr acme/api#9 --source s --correction 'wrong PR'"
    )
    unit = workspace.read_unit(number, "engine")
    assert unit["pr"]["number"] == 9 and unit["corrections"][1]["old_pr"]["number"] == 7
    assert "wrong PR" in workspace.ok(address, "show")
    workspace.refuse(
        f"{address} merged --source s --at 2099-01-01 --correction x", "", 2
    )


def test_a_release_correction_changes_only_its_unit_and_keeps_the_old_values(
    workspace: Backlog,
) -> None:
    first = workspace.add_merged_unit("first")
    second = workspace.add_merged_unit("second")
    a, b = f"{first}/engine", f"{second}/engine"
    workspace.add_check(first, "check")
    flags = "--at 2026-10-23T12:00:00Z --source s --tag v1.2.0"
    workspace.ok_line(f"{a},{b} released {flags} --no-post-release {b}")
    workspace.refuse(f"{a} released {flags}", "--correction")
    workspace.refuse(f"{a} released {flags} --correction same", "changes no value")
    workspace.ok_line(
        f"{a} released --at 2026-10-23 --source s2 --tag v9 --correction typo"
    )
    assert workspace.read_unit(first, "engine")["release"]["tag"] == "v9"
    assert workspace.read_unit(second, "engine")["release"]["tag"] == "v1.2.0"
    unit = workspace.read_unit(first, "engine")
    assert unit["status"] == "post_release"
    old = unit["corrections"][0]
    assert (old["subject"], old["old_tag"], old["old_evidence"]["source"]) == (
        "release",
        "v1.2.0",
        "s",
    )
    workspace.ok_line(
        f'{a} released --at 2026-10-23 --source s --tag "" --correction x'
    )
    assert workspace.read_unit(first, "engine")["release"]["tag"] is None
    assert "x" in workspace.ok(a, "show")
    fresh = workspace.add_merged_unit("fresh")
    workspace.refuse(
        f"{fresh}/engine released --at 2026-10-23 --source s --correction x",
        "has no release to correct",
    )


def test_a_correction_cannot_break_the_order_of_merge_and_release(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work", pr_number=1)
    address = f"{number}/engine"
    workspace.release(address, "--no-post-release")
    err = workspace.refuse(
        f"{address} merged --at 2026-10-24 --source s --correction late", "", 2
    )
    assert "2026-10-23T12:00:00Z" in err
    err = workspace.refuse(
        f"{address} merged --pr acme/api#2 --source s --correction wrong"
    )
    assert "already released" in err and f"backlog {number} unit add NAME" in err


def test_a_release_is_not_before_its_merge_and_no_fact_is_in_the_future(
    workspace: Backlog,
) -> None:
    number = start_unit(workspace)
    address = f"{number}/engine"
    future = days_from_now(30)
    workspace.refuse(
        f"{address} merged --pr acme/api#1 --source s --at {future}",
        "later than now",
        2,
    )
    workspace.refuse(
        f"{address} merged --pr acme/api#1 --source s --at {future} --dry-run", "", 2
    )
    workspace.ok_line(
        f"{address} merged --pr acme/api#1 --source s --at 2026-10-23T10:00:00Z"
    )
    base = f"{address} released --source s --no-post-release"
    err = workspace.refuse(f"{base} --at 2026-10-23T09:00:00Z", "", 2)
    assert "2026-10-23T09:00:00Z" in err and "2026-10-23T10:00:00Z" in err
    workspace.refuse(f"{base} --at {future}", "later than now", 2)
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    err = workspace.refuse(f"{base} --at {tomorrow}", "", 2)
    assert f"--at {tomorrow} is later than now (20" in err
    workspace.ok_line(f"{base} --at 2026-10-23")  # a date alone is the end of that day
    assert workspace.read_unit(number, "engine")["release"]["released_at"] == (
        "2026-10-23T23:59:59Z"
    )


def test_a_date_alone_is_now_for_today(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    today = Backlog.today()
    workspace.ok_line(
        f"{number}/engine released --at {today} --source s --no-post-release"
    )
    stored = workspace.read_unit(number, "engine")["release"]["released_at"]
    assert stored.startswith(today) and not stored.endswith("T23:59:59Z")
    help_line = "a date alone means the end of that day, or now for today"
    assert help_line in workspace.run(f"{number}/engine", "released", "--help").out


def test_every_date_flag_refuses_a_date_far_from_now(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.finish_units(number)
    for value in ("1999-12-31", "2099-01-01", "9999-12-31T23:59:59-05:00"):
        for line in (
            f"add other --title t --due {value}",
            f"{number} reminder add {value}",
            f"{number} done --result r --source s --at {value}",
        ):
            workspace.refuse(line, code=2)
    for value, expected in (
        ("2026-10-23T12:00", "no time zone offset"),
        ("23.10.2026", "invalid format"),
        ("2026-13-40", "not a real calendar date"),
    ):
        workspace.refuse(f"{number} due add {value}", expected, 2)


def test_results_and_closing_are_not_dated_before_the_release_or_in_the_future(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_check(number, "check")
    workspace.release(f"{number}/engine")  # at 2026-10-23T12:00:00Z
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    done = f"{number}/engine post_release done check --result r --source s"
    err = workspace.refuse(f"{done} --at 2026-10-23T11:00:00Z", "", 2)
    assert "2026-10-23T11:00:00Z" in err and "2026-10-23T12:00:00Z" in err
    workspace.refuse(f"{done} --at {tomorrow}", "future", 2)
    workspace.ok_line(f"{done} --at 2026-10-24")
    err = workspace.refuse(
        f"{number} done --result r --source s --at 2026-10-01", "", 2
    )
    assert "2026-10-01" in err and "the release of engine" in err
    workspace.refuse(
        f"{number} done --result r --source s --at {tomorrow}", "future", 2
    )
    workspace.ok_line(f"{number} done --result r --source s --at 2026-10-24")
    research = workspace.add_item("research")
    workspace.start_item(research)
    workspace.refuse(
        f"{research}/work done --result r --source s --at {tomorrow}", "future", 2
    )


def test_merged_released_and_corrections_print_the_stored_time(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    workspace.ok_line(f"{number}/engine assign --agent A")
    out = workspace.ok_line(
        f"{number}/engine merged --pr acme/api#7 --at 2026-10-21T23:59:59Z --source s"
    )
    assert f"{number}/engine: wip -> merged (merged at 2026-10-21T23:59:59Z)" in out
    out = workspace.ok_line(
        f"{number}/engine merged --correction x --at 2026-10-21T20:00:00Z --source s2"
    )
    assert "now merged at 2026-10-21T20:00:00Z" in out
    out = workspace.ok_line(
        f"{number}/engine released --at 2026-10-22T10:00:00Z --source s "
        "--no-post-release"
    )
    assert "(released at 2026-10-22T10:00:00Z)" in out
    out = workspace.ok_line(
        f"{number}/engine released --correction x --at 2026-10-22T11:00:00Z --source s3"
    )
    assert "now released at 2026-10-22T11:00:00Z" in out
