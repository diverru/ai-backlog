"""The details file: show, set, replace, append, export."""

from backlog_cli.domain.vocabulary import DetailsSection
from conftest import Backlog, valid_details

HANDOFF = "--section 'Agent handoff'"


def write_file(workspace: Backlog, text: str | bytes, name: str = "input.md") -> str:
    path = workspace.work / name
    path.write_bytes(text if isinstance(text, bytes) else text.encode())
    return str(path)


def test_set_replaces_the_details_and_checks_the_headings(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    path = write_file(workspace, valid_details("### Steps\n\n1. one"))
    workspace.ok(str(number), "brief", "set", "--from-file", path)
    text = workspace.ok(str(number), "brief", "show")
    assert text.startswith("# 0001_work: work") and "### Steps" in text
    bad = write_file(
        workspace, "## Problem and expected result\n\nx\n\n## My own heading\n\ny\n"
    )
    err = workspace.refuse(f"{number} brief set --from-file {bad}", "", 2)
    assert "unknown heading: My own heading" in err
    assert "missing heading: Agent handoff" in err
    titled = write_file(workspace, "# Own title\n\n" + valid_details())
    workspace.refuse(f"{number} brief set --from-file {titled}", "starts with '# '", 2)


def test_show_output_can_be_fed_back_to_set(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.ok_line(f"{number} brief append {HANDOFF} --text 'Build it.'")
    shown = workspace.ok(str(number), "brief", "show")
    before = workspace.workspace_file("details/0001_work.md").read_text()
    workspace.ok(
        str(number), "brief", "set", "--from-file", write_file(workspace, shown)
    )
    assert workspace.workspace_file("details/0001_work.md").read_text() == before
    other = write_file(workspace, "# Another title\n\n" + shown.split("\n", 1)[1])
    workspace.refuse(f"{number} brief set --from-file {other}", "starts with '# '", 2)


def test_append_and_replace_change_one_section(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    decisions = "--section 'Decisions and rationale'"
    workspace.ok_line(f"{number} brief append {decisions} --text First.")
    workspace.ok_line(f"{number} brief append {decisions} --text Second.")
    shown = workspace.ok_line(f"{number} brief show {decisions}")
    assert shown.strip() == "First.\n\nSecond."
    workspace.ok_line(f"{number} brief replace {decisions} --text Only.")
    assert workspace.ok_line(f"{number} brief show {decisions}").strip() == "Only."
    path = write_file(workspace, "From a file.")
    workspace.ok_line(f"{number} brief append {decisions} --from-file {path}")
    assert "From a file." in workspace.ok_line(f"{number} brief show {decisions}")
    for line in (
        f"{number} brief append --section Nope --text x",
        f"{number} brief append {HANDOFF}",
        f"{number} brief replace {HANDOFF}",
        f"{number} brief append {HANDOFF} --text ''",
        f"{number} brief append {HANDOFF} --text '   '",
        f"{number} brief append {HANDOFF} --text x --from-file {path}",
    ):
        workspace.refuse(line, code=2)


def test_a_text_may_not_hold_a_heading_line(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    for text in (
        "## Extra",
        "text\n##\tTabbed",
        "   ## Indented",
        "a\n```\n## in a fence\n```",
    ):
        for action in ("append", "replace"):
            err = workspace.refuse(
                f"{number} brief {action} {HANDOFF} --text '{text}'", "", 2
            )
            assert "would split the section" in err, text
    workspace.ok_line(
        f"{number} brief append {HANDOFF} --text 'x\n    ## four spaces are code'"
    )
    shifted = write_file(
        workspace, valid_details().replace("## Agent handoff", "  ## Agent handoff")
    )
    workspace.ok(str(number), "brief", "set", "--from-file", shifted)
    tabbed = write_file(
        workspace, valid_details().replace("## Agent handoff", "##\tAgent handoff")
    )
    workspace.ok(str(number), "brief", "set", "--from-file", tabbed)
    assert "\n## Agent handoff" in workspace.ok(str(number), "brief", "show")


def test_export_prints_the_executor_copy_and_writes_nothing(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.ok_line(f"{number} brief append {HANDOFF} --text 'Build it.'")
    original = workspace.workspace_file("details/0001_work.md").read_text()
    result = workspace.run(str(number), "brief", "export")
    assert result.code == 0 and result.err == ""
    assert result.out.startswith("# 1: work\n")
    headings = [line for line in result.out.splitlines() if line.startswith("## ")]
    assert headings == [f"## {section}" for section in DetailsSection]
    assert result.out.count("(empty)") == 7 and "Build it." in result.out
    assert workspace.workspace_file("details/0001_work.md").read_text() == original
    assert list(workspace.work.iterdir()) == []
    for flags in ("--to x", "--force"):
        workspace.refuse(f"{number} brief export {flags}", "unrecognized", 2)
    assert (
        "Agent handoff" in workspace.run(str(number), "brief", "append", "--help").out
    )


def test_central_file_names_are_refused_in_any_case_at_write_and_export(
    workspace: Backlog,
) -> None:
    number = workspace.add_item("work")
    for name in (
        str(workspace.home),
        ".bklg",
        "BACKLOG.YAML",
        "Archive.yaml",
        "Details/x",
    ):
        path = write_file(workspace, valid_details(f"See {name} now."))
        for line in (
            f"{number} brief append {HANDOFF} --text 'See {name}.'",
            f"{number} brief replace {HANDOFF} --text 'See {name}.'",
            f"{number} brief set --from-file {path}",
        ):
            workspace.refuse(line, "central files")
    path = workspace.workspace_file("details/0001_work.md")  # slipped in before
    path.write_text(
        path.read_text().replace(
            "## Agent handoff", "## Agent handoff\n\nSee BACKLOG.yaml"
        )
    )
    result = workspace.run(str(number), "brief", "export")
    assert result.code == 1 and "central files" in result.err and result.out == ""


def test_text_files_are_utf8_and_a_bom_is_dropped(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    bad = write_file(workspace, b"\xff\xfe\x00bad")
    workspace.refuse(f"{number} brief set --from-file {bad}", "not UTF-8 text", 2)
    bom = write_file(workspace, b"\xef\xbb\xbf" + valid_details().encode(), "bom.md")
    workspace.ok(str(number), "brief", "set", "--from-file", bom)
    text = write_file(workspace, b"\xef\xbb\xbfAppended", "text.md")
    workspace.ok_line(f"{number} brief append {HANDOFF} --from-file {text}")
    assert "﻿" not in workspace.workspace_file("details/0001_work.md").read_text()


def test_archived_details_are_readable_but_not_writable(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    workspace.ok(str(number), "cancel", "--reason", "x")
    assert "# 0001_work: work" in workspace.ok(str(number), "brief", "show")
    workspace.refuse(f"{number} brief append {HANDOFF} --text x", "read-only")


def test_a_details_file_is_at_most_256_kb(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    big = write_file(workspace, "x" * 300_000)
    err = workspace.refuse(
        f"{number} brief append {HANDOFF} --from-file {big}", "at most 256 KB", 2
    )
    assert "would be 2" in err and " bytes)" in err
    huge = write_file(workspace, valid_details("y" * 300_000), "huge.md")
    workspace.refuse(f"{number} brief set --from-file {huge}", "at most 256 KB", 2)
    workspace.refuse(
        f"{number} brief replace {HANDOFF} --from-file {big}", "at most 256 KB", 2
    )
