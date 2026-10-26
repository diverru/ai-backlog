"""One PR may close units of several items: link, merge and release together."""

from conftest import Backlog

PR = "acme/api#5"
FLAGS = "--at 2026-10-23T12:00:00Z --source rs --tag v1"


def start_unit(workspace: Backlog, slug: str, unit_id: str = "engine") -> str:
    number = workspace.add_item(slug)
    workspace.add_unit(number, unit_id)
    workspace.ok(f"{number}/{unit_id}", "assign", "--agent", "Agent")
    return f"{number}/{unit_id}"


def two_units_with_one_pr(workspace: Backlog) -> tuple[str, str]:
    first = start_unit(workspace, "one")
    second = start_unit(workspace, "two", "fix")
    workspace.ok_line(f"{first} link pr {PR}")
    workspace.ok_line(f"{second} link pr {PR}")
    return first, second


def test_link_pr_accepts_a_pr_of_another_unit_and_says_so(workspace: Backlog) -> None:
    first, second = two_units_with_one_pr(workspace)
    assert f"shared with {first}" in workspace.ok_line(f"{second} link pr {PR}")
    assert "shared" not in workspace.ok_line(f"{first} link pr acme/api#6")


def test_merged_is_written_to_every_active_unit_of_the_pr(workspace: Backlog) -> None:
    first, second = two_units_with_one_pr(workspace)
    third = start_unit(workspace, "three", "gone")
    workspace.ok_line(f"{third} link pr {PR}")
    workspace.ok_line(f"{third} cancel --reason no")
    out = workspace.ok_line(
        f"{first} merged --source gh --at 2026-10-23T10:00:00Z --result ok"
    )
    assert f"also merged: {second}" in out and third not in out
    merges = []
    for address in (first, second):
        number, unit_id = address.split("/")
        unit = workspace.read_unit(int(number), unit_id)
        assert unit["status"] == "merged"
        merges.append(unit["merge"])
    assert merges[0] == merges[1]
    assert merges[0]["merged_at"] == "2026-10-23T10:00:00Z"
    number, unit_id = third.split("/")
    assert workspace.read_unit(int(number), unit_id)["merge"] is None


def test_merged_after_another_unit_copies_that_merge(workspace: Backlog) -> None:
    first = start_unit(workspace, "one")
    workspace.ok_line(f"{first} link pr {PR}")
    workspace.ok_line(f"{first} merged --source gh --at 2026-10-23T10:00:00Z")
    second = start_unit(workspace, "two", "fix")
    out = workspace.ok_line(
        f"{second} merged --pr {PR} --source other --at 2026-10-23T11:00:00Z"
    )
    assert f"merge copied from {first}" in out
    unit = workspace.read_unit(int(second.split("/")[0]), "fix")
    assert unit["merge"]["merged_at"] == "2026-10-23T10:00:00Z"
    assert unit["merge"]["evidence"]["source"] == "gh"


def test_released_alone_is_refused_with_the_whole_group(workspace: Backlog) -> None:
    first, second = two_units_with_one_pr(workspace)
    workspace.ok_line(f"{first} merged --source gh")
    err = workspace.refuse(f"{first} released {FLAGS}", second)
    assert f"backlog {first},{second} released {FLAGS}" in err
    out = workspace.ok_line(
        f"{first},{second} released {FLAGS} --no-post-release {first} {second}"
    )
    assert f"{first}: merged -> done" in out and f"{second}: merged -> done" in out


def test_post_release_decision_stays_per_unit_in_a_shared_release(
    workspace: Backlog,
) -> None:
    first, second = two_units_with_one_pr(workspace)
    workspace.ok_line(f"{first} merged --source gh")
    workspace.add_check(int(first.split("/")[0]), "check", "engine")
    out = workspace.ok_line(
        f"{first},{second} released {FLAGS} --no-post-release {second}"
    )
    assert f"{first}: merged -> post_release" in out
    assert f"{second}: merged -> done" in out


def test_two_units_of_one_item_may_share_a_pr(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    for unit_id in ("a", "b"):
        workspace.add_unit(number, unit_id)
    workspace.ok_line(f"{number}/a link pr {PR}")
    assert f"shared with {number}/a" in workspace.ok_line(f"{number}/b link pr {PR}")
    out = workspace.ok_line(f"{number}/a merged --source gh")
    assert f"also merged: {number}/b" in out
    workspace.refuse(f"{number}/a released {FLAGS}", f"{number}/a,{number}/b")


def test_a_superseded_unit_is_ignored_by_the_shared_rules(workspace: Backlog) -> None:
    first, second = two_units_with_one_pr(workspace)
    workspace.ok_line(f"{second} cancel --reason no")
    workspace.ok_line(f"{first} merged --source gh")
    workspace.ok_line(f"{first} released {FLAGS} --no-post-release")
