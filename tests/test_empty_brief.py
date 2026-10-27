"""An empty `Problem and expected result` section: a hint, never a block, and a
group in the attention list and in the viewer.
"""

from backlog_cli.domain.vocabulary import AttentionGroup
from backlog_cli.serve.view import WorkspaceView
from backlog_cli.store.workspace import Workspace
from conftest import Backlog, valid_details
from test_serve import Viewer

PROBLEM = "--section 'Problem and expected result'"
HANDOFF = "--section 'Agent handoff'"


def hint(number: int) -> str:
    return (
        f"Note: the brief of {number} is empty. "
        f"Fill it: backlog {number} brief set --from-file FILE"
    )


def fill(workspace: Backlog, number: int) -> None:
    path = workspace.work / f"filled_{number}.md"
    path.write_text(valid_details())
    workspace.ok(str(number), "brief", "set", "--from-file", str(path))


def test_add_prints_the_hint_after_the_normal_output(workspace: Backlog) -> None:
    result = workspace.run("add", "x", "--title", "T")
    assert result.code == 0
    assert result.out.splitlines() == ["Created item 1 (0001_x)", hint(1)]
    dry = workspace.run("add", "y", "--title", "Y", "--dry-run")
    assert dry.code == 0 and dry.out.splitlines()[-1] == hint(2)


def test_a_change_to_an_item_with_a_blank_problem_ends_with_the_hint(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    assert workspace.ok(str(number), "unit", "add", "engine").endswith(
        hint(number) + "\n"
    )
    out = workspace.ok(f"{number}/engine", "assign", "--agent", "A")
    assert out.splitlines()[-1] == hint(number)
    fill(workspace, number)
    assert "Note:" not in workspace.ok(f"{number}/engine", "unassign", "--agent", "A")


def test_brief_commands_decide_by_the_text_after_the_change(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    path = workspace.work / "details.md"
    path.write_text(valid_details())
    assert "Note:" not in workspace.ok(
        str(number), "brief", "set", "--from-file", str(path)
    )
    blank = workspace.add_item("blank")
    other = workspace.ok_line(f"{blank} brief append {HANDOFF} --text 'Build it.'")
    assert other.splitlines()[-1] == hint(blank)
    problem = workspace.ok_line(f"{blank} brief append {PROBLEM} --text 'Why.'")
    assert "Note:" not in problem


def test_an_item_that_leaves_the_registry_gets_no_hint(workspace: Backlog) -> None:
    cancelled = workspace.add_item("gone")
    assert "Note:" not in workspace.ok(str(cancelled), "cancel", "--reason", "x")
    finished = workspace.add_item("finished")
    workspace.finish_units(finished)
    done = workspace.ok(str(finished), "done", "--result", "r", "--source", "s")
    assert "Note:" not in done


def test_an_unreadable_details_file_gives_no_hint(workspace: Backlog) -> None:
    broken = workspace.add_item("broken")
    missing = workspace.add_item("missing")
    workspace.workspace_file("details/0001_broken.md").write_text("no headings")
    workspace.workspace_file("details/0002_missing.md").unlink()
    for number in (broken, missing):
        result = workspace.run(str(number), "unit", "add", "engine")
        assert result.code == 0 and "Note:" not in result.out, number


def test_a_command_that_touches_two_items_hints_each_in_number_order(
    workspace: Backlog,
) -> None:
    first = workspace.add_merged_unit("first")
    second = workspace.add_merged_unit("second")
    flags = "--at 2026-10-23T12:00:00Z --source release_status --tag v1"
    out = workspace.ok_line(
        f"{first}/engine,{second}/engine released {flags} --no-post-release "
        f"{first}/engine {second}/engine"
    )
    assert out.splitlines()[-2:] == [hint(first), hint(second)]


def test_read_commands_print_no_hint(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    for line in (f"{number} show", "list", f"{number} brief show", "guide all"):
        assert "is empty. Fill it" not in workspace.ok_line(line), line


def test_attention_lists_active_items_with_a_blank_problem(workspace: Backlog) -> None:
    blank = workspace.add_item("blank")
    filled = workspace.add_item("filled")
    fill(workspace, filled)
    archived = workspace.add_item("archived")
    workspace.ok(str(archived), "cancel", "--reason", "x")
    broken = workspace.add_item("broken")
    workspace.workspace_file(f"details/{broken:04d}_broken.md").write_text("no")
    lines = workspace.ok_line("list --attention").splitlines()
    assert lines[-2:] == [
        "Empty brief:",
        f"  {blank} blank: backlog {blank} brief set --from-file FILE",
    ]


def test_the_empty_brief_group_is_last_and_counted(workspace: Backlog) -> None:
    number = workspace.add_item("blank")
    work = Workspace.open(workspace.home, "ws")
    view = WorkspaceView(workspace.home, work, work.load_registry())
    assert list(view.attention) == [
        AttentionGroup.CAN_START,
        AttentionGroup.EMPTY_BRIEF,
    ]
    assert view.attention_count == 2  # one row per group
    fill(workspace, number)
    view = WorkspaceView(workspace.home, work, work.load_registry())
    assert view.attention_count == 1 and "Empty brief" not in workspace.ok_line(
        "list --attention"
    )


def test_the_attention_page_notes_an_empty_brief(workspace: Backlog) -> None:
    blank = workspace.add_item("blank")
    filled = workspace.add_item("filled")
    fill(workspace, filled)
    viewer = Viewer(workspace.home)
    try:
        page = viewer.get("/ws/")
    finally:
        viewer.stop()
    group = page.split("Empty brief", 1)[1]
    assert '<section class="group g-start"><h2>Empty brief ' in page
    assert '<span class="line-note item-note">brief is empty</span>' in group
    assert f'href="/ws/items/{blank}"' in group
    assert f'href="/ws/items/{filled}"' not in group
