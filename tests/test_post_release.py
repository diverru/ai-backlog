"""Post-release actions, their confirmation, and failed checks."""

from conftest import Backlog

DONE = "post_release done check --result ok --source s"


def released_with(workspace: Backlog, *names: str, slug: str = "work") -> int:
    number = workspace.add_merged_unit(slug)
    for name in names:
        workspace.add_check(number, name)
    workspace.release(f"{number}/engine")
    return number


def test_add_marks_the_unit_and_refuses_duplicates_and_blank_text(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    workspace.add_unit(number, "engine")
    address = f"{number}/engine"
    add = f"{address} post_release add check --kind verification"
    workspace.ok_line(f'{add} --title "Check it" --instructions "Look\nat it"')
    unit = workspace.read_unit(number, "engine")
    assert unit["post_release_required"] is True
    assert unit["post_release_actions"][0]["status"] == "pending"
    assert "check  verification  pending  Check it" in workspace.ok_line(
        f"{address} post_release"
    )
    workspace.refuse(f"{add} --title x --instructions y", "already has an action")
    for flag, other in (("--title", "--instructions"), ("--instructions", "--title")):
        for blank in ("''", "'   '"):
            workspace.refuse(
                f"{address} post_release add c2 --kind command "
                f"{flag} {blank} {other} Look",
                "",
                2,
            )
    for line in (
        f"{address} post_release add c2 --kind weird --title t --instructions i",
        f"{address} post_release add Bad-Name --kind command "
        "--title t --instructions i",
    ):
        workspace.refuse(line, code=2)
    workspace.add_unit(number, "study", "--kind", "research")
    study = f"{number}/study"
    assert "no post-release actions" in workspace.ok_line(f"{study} post_release")
    workspace.refuse(
        f"{study} post_release add x --kind command --title t --instructions i",
        "research",
    )


def test_an_action_is_confirmed_only_after_the_release_with_a_result(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_check(number, "check")
    address = f"{number}/engine"
    workspace.refuse(f"{address} {DONE}", "only after the release")
    workspace.release(address)
    for line in (
        f"{address} post_release done check --result '  ' --source s",
        f"{address} post_release done check --result r --source '  '",
        f"{address} post_release cancel check --reason '  '",
        f"{address} post_release done check --result r --source s --not-needed",
    ):
        workspace.refuse(line, code=2)
    out = workspace.ok_line(
        f"{address} post_release done check --result 'p99 1.8s' --source 'the panel' "
        f"--at {workspace.today()}"
    )
    assert f"{address}: post_release -> done (all post-release actions settled)" in out
    assert f"{address}/check: pending -> confirmed" in out
    unit = workspace.read_unit(number, "engine")
    confirmation = unit["post_release_actions"][0]["confirmation"]
    assert (confirmation["result"], confirmation["source"]) == ("p99 1.8s", "the panel")
    assert confirmation["observed_at"].startswith(workspace.today())
    assert unit["status"] == "done"
    assert (
        unit["completion"]["evidence"]["result"] == "all post-release actions confirmed"
    )
    workspace.refuse(f"{address} {DONE}", "unit is done")
    cancel = f"{address} post_release cancel check --reason oops --not-needed"
    workspace.refuse(cancel, "a confirmation or cancellation is final")


def test_several_names_are_all_or_nothing_and_a_name_is_listed_once(
    workspace: Backlog,
) -> None:
    number = released_with(workspace, "one", "two", "three")
    address = f"{number}/engine"
    workspace.ok_line(f"{address} post_release done two --result ok --source s")
    workspace.ok_line(f"{address} post_release cancel three --reason r --not-needed")
    err = workspace.refuse(
        f"{address} post_release done one two three --result ok --source s"
    )
    assert f"{address}/two" in err and f"{address}/three" in err
    assert f"{address}/one" not in err.split("\n\n")[1]
    workspace.refuse(
        f"{address} post_release done one one --result r --source s", "listed twice", 2
    )
    workspace.ok_line(f"{address} post_release done one --result ok --source s")
    assert workspace.read_unit(number, "engine")["status"] == "done"
    assert (
        workspace.read_unit(number, "engine")["completion"]["evidence"]["result"]
        == "all post-release actions confirmed"
    )


def test_cancel_before_and_after_the_release(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_check(number, "check")
    address = f"{number}/engine"
    workspace.ok_line(f"{address} post_release cancel check --reason 'not needed'")
    unit = workspace.read_unit(number, "engine")
    assert unit["post_release_required"] is None  # the decision is open again
    assert unit["post_release_actions"][0]["status"] == "cancelled"
    other = released_with(workspace, "check", slug="other_work")
    err = workspace.refuse(f"{other}/engine post_release cancel check --reason failed")
    assert "If the check failed, do not cancel it" in err
    assert f"backlog {other}/engine post_release fail check --finding" in err
    assert f"backlog {other} unit add NAME --kind pr" in err and "--not-needed" in err
    workspace.ok_line(
        f"{other}/engine post_release cancel check --reason dropped --not-needed"
    )
    done = workspace.read_unit(other, "engine")
    assert (
        done["status"] == "done"
        and "cancelled" in done["completion"]["evidence"]["result"]
    )


def test_a_unit_with_a_pending_action_cannot_be_ended(workspace: Backlog) -> None:
    number = released_with(workspace, "check", "other")
    address = f"{number}/engine"
    workspace.ok_line(f"{address} post_release done other --result ok --source s")
    workspace.add_unit(number, "fix")
    for line in (
        f"{address} cancel --reason x",
        f"{address} supersede --by fix --reason x",
        f"{number} cancel --reason x",
    ):
        err = workspace.refuse(line, f"{address}/check")
        assert "cancel it explicitly with its own reason" in err
        assert f'backlog {address} post_release done check --result "..."' in err
        assert f'backlog {address} post_release cancel check --reason "..."' in err
        assert "other" not in err
    never = workspace.add_item("never")
    workspace.add_unit(never, "engine")
    workspace.add_check(never, "check")
    workspace.ok_line(f"{never}/engine cancel --reason 'rolled back'")
    action = workspace.read_unit(never, "engine")["post_release_actions"][0]
    assert action["status"] == "cancelled" and "rolled back" in action["cancel_reason"]


def test_edit_changes_a_pending_action_only(workspace: Backlog) -> None:
    number = released_with(workspace, "check", "other")
    post = f"{number}/engine post_release"
    workspace.ok_line(f"{post} edit check --title 'New title' --instructions x")
    action = workspace.read_unit(number, "engine")["post_release_actions"][0]
    assert (action["description"], action["instructions"]) == ("New title", "x")
    workspace.refuse(f"{post} edit check", code=2)
    workspace.ok_line(f"{post} done check --result ok --source me")
    workspace.refuse(
        f"{post} edit check --title Late", "only pending actions can be edited"
    )


def test_an_action_is_labelled_by_its_kind(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    for name, kind in (("step", "command"), ("change", "admin_change")):
        workspace.ok_line(
            f"{number}/engine post_release add {name} --kind {kind} "
            "--title 'Do it' --instructions Now"
        )
    workspace.release(f"{number}/engine")
    listing = workspace.ok("list")
    assert "command step: Do it" in listing and "admin change change: Do it" in listing
    attention = workspace.ok_line("list --attention")
    assert f"{number}/engine admin change change" in attention


def test_a_failed_check_stays_pending_and_keeps_its_findings(
    workspace: Backlog,
) -> None:
    number = workspace.failed_check()
    address = f"{number}/engine"
    fail = f"{address} post_release fail check --source 'second look'"
    action = workspace.read_unit(number, "engine")["post_release_actions"][0]
    assert action["status"] == "pending"
    assert action["findings"][0]["text"] == "p99 is 4 s"
    assert action["findings"][0]["recorded_at"]
    workspace.refuse(f'{fail} --finding "p99 is 4 s"', "already has this finding")
    workspace.ok_line(f'{fail} --finding "still 3 s"')
    shown = workspace.ok(address, "show")
    assert "p99 is 4 s" in shown and "still 3 s" in shown
    assert "check check: Check check — FAILED: still 3 s" in workspace.ok("list")
    assert "Failed post-release checks:" in workspace.ok("list", "--attention")
    workspace.refuse(f"{address} post_release edit check --title New", "finding")
    fresh = workspace.add_merged_unit("fresh")
    workspace.add_check(fresh, "check")
    workspace.refuse(
        f"{fresh}/engine post_release fail check --finding f --source s",
        "only after the release",
    )
    workspace.refuse(f"{address} post_release fail check --source s", "--finding", 2)
    workspace.refuse(f"{address} post_release fail check --finding f", "--source", 2)


def test_a_failed_check_takes_the_date_it_failed(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_check(number, "check")
    workspace.release(f"{number}/engine")  # at 2026-10-23T12:00:00Z
    fail = f"{number}/engine post_release fail check --source s --finding bad"
    workspace.refuse(f"{fail} --at 2026-10-22", "the release", 2)
    workspace.refuse(f"{fail} --at 2099-01-01", "", 2)
    workspace.ok_line(f"{fail} --at 2026-10-24")
    finding = workspace.read_unit(number, "engine")["post_release_actions"][0][
        "findings"
    ][0]
    assert finding["at"] == "2026-10-24T23:59:59Z" and finding["recorded_at"]
    workspace.release_fix(number)
    workspace.refuse(
        f"{number}/engine {DONE} --at 2026-10-24T12:00:00Z", "last finding", 2
    )


def test_only_the_release_of_a_unit_added_later_unlocks_a_failed_check(
    workspace: Backlog,
) -> None:
    number = workspace.failed_check()
    address = f"{number}/engine"
    done = f"{address} {DONE}"
    cancel = f"{address} post_release cancel check --reason r --not-needed"
    for line in (done, cancel):
        err = workspace.refuse(line, "p99 is 4 s")
        assert f"backlog {number} unit add NAME --kind pr" in err
    workspace.ok_line(  # moving the release date unlocks nothing
        f"{address} released --correction date --at 2026-10-22 --source s"
    )
    workspace.refuse(done, "release a unit added after the finding")
    workspace.add_unit(number, "fix")
    err = workspace.refuse(done, f"backlog {number}/fix merged")  # an unfinished fix
    assert "unit add NAME" not in err
    workspace.refuse(
        f"{number} done --result r --source s", f"backlog {number}/fix merged"
    )
    workspace.ok(f"{number}/fix", "assign", "--agent", "F")
    workspace.ok_line(f"{number}/fix merged --pr acme/api#7000 --source s")
    workspace.refuse(cancel, f"backlog {number}/fix released")
    workspace.ok_line(
        f"{number}/fix released --at 2026-10-24 --source s --no-post-release"
    )
    workspace.refuse(f"{done} --at 2026-10-24", "last finding", 2)  # before the finding
    workspace.ok_line(f"{done} --at {workspace.now_utc()}")
    assert workspace.read_unit(number, "engine")["status"] == "done"


def test_a_unit_that_was_already_there_does_not_unlock_a_failed_check(
    workspace: Backlog,
) -> None:
    number = workspace.add_merged_unit("work")
    workspace.add_unit(number, "other")
    workspace.ok(f"{number}/other", "assign", "--agent", "O")
    workspace.ok_line(f"{number}/other merged --pr acme/api#9998 --source s")
    workspace.add_check(number, "check")
    workspace.release(f"{number}/engine")
    workspace.ok_line(
        f"{number}/engine post_release fail check --finding bad --source s"
    )
    workspace.ok_line(
        f"{number}/other released --at {workspace.now_utc()} --source s "
        "--no-post-release"
    )
    workspace.refuse(f"{number}/engine {DONE}", "release a unit added after")


def test_a_cancel_of_a_unit_with_a_failed_check_never_offers_not_needed(
    workspace: Backlog,
) -> None:
    number = workspace.failed_check()
    err = workspace.refuse(f"{number}/engine cancel --reason r")
    assert "--not-needed" not in err
    assert f"backlog {number} unit add NAME --kind pr" in err


def test_attention_and_list_agree_on_pending_checks(workspace: Backlog) -> None:
    number = released_with(workspace, "check")
    lines = workspace.ok("list").splitlines()
    unit_line = next(
        line for line in lines if "post_release" in line and "engine" in line
    )
    assert lines[lines.index(unit_line) + 1] == "            check check: Check check"
    assert f"  {number}/engine check check: Check check" in workspace.ok_line(
        "list --attention"
    )
    workspace.ok_line(f"{number}/engine {DONE}")
    assert "Check check" not in workspace.ok("list")
