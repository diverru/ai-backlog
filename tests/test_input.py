"""The character filter, UTF-8 input, and how bad flags are reported."""

import pytest

from conftest import Backlog, OldWords, valid_details

HANDOFF = "--section 'Agent handoff'"


@pytest.mark.parametrize("separator", ["\n", "\r", " ", "\x0b", "\x85", "\t"])
def test_a_line_break_or_tab_in_a_one_line_field_is_refused(
    workspace: Backlog, separator: str
) -> None:
    number = workspace.add_item("work")
    before = workspace.snapshot()
    for arguments in (
        (str(number), "rename", f"a{separator}## Fake"),
        ("add", "other", "--title", f"a{separator}b"),
        (str(number), "block", "add", f"a{separator}b"),
        (str(number), "cancel", "--reason", f"a{separator}b"),
    ):
        result = workspace.run(*arguments)
        assert result.code == 2, arguments
    assert workspace.snapshot() == before
    workspace.ok_line(f"{number} brief append {HANDOFF} --text x")


def test_control_and_bidi_characters_are_refused_everywhere(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    err = workspace.run("add", "slug", "--title", "a\x07b").err
    assert "control character (U+0007)" in err
    for bad in ("a\x1fb", "a‮b", "a⁦b", "a\x1bb"):
        assert workspace.run("add", "slug", "--title", bad).code == 2, repr(bad)
        for arguments in (
            (
                str(number),
                "brief",
                "append",
                "--section",
                "Agent handoff",
                "--text",
                bad,
            ),
            (
                f"{number}/engine",
                "post_release",
                "add",
                "c",
                "--kind",
                "command",
                "--title",
                "T",
                "--instructions",
                bad,
            ),
        ):
            result = workspace.run(*arguments)
            assert result.code == 2 and "control character" in result.err, repr(bad)
    source = workspace.work / "details.md"
    source.write_text(valid_details("red \x1b[31m text"))
    workspace.refuse(f"{number} brief set --from-file {source}", "control character", 2)


def test_multi_line_text_is_allowed_where_it_belongs(workspace: Backlog) -> None:
    number = workspace.add_merged_unit("work")
    workspace.ok(
        f"{number}/engine",
        "post_release",
        "add",
        "check",
        "--kind",
        "verification",
        "--title",
        "Check",
        "--instructions",
        "line one\n\tindented\nline two",
    )
    workspace.ok(
        str(number), "brief", "append", "--section", "Agent handoff", "--text", "a\nb"
    )
    family = "\U0001f468‍\U0001f469"
    workspace.ok_line(f"add emoji --title 'Team {family} café'")
    assert workspace.run("add", "slug", "--title", "   ").code == 2


def test_a_one_line_field_has_at_most_300_characters(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    err = workspace.refuse(
        f"add other --title {'x' * 301}", "301 characters; at most 300", 2
    )
    assert "Traceback" not in err
    workspace.refuse(f"{number} block add {'y' * 301}", code=2)
    workspace.refuse(f"{number} cancel --reason {'r' * 301}", code=2)
    workspace.ok_line(f"add other --title {'x' * 300}")


def test_an_argument_that_is_not_utf8_is_a_usage_error(workspace: Backlog) -> None:
    number = workspace.add_item("work")
    bad = b"a\xffb".decode("utf-8", errors="surrogateescape")
    for arguments in (
        ("add", "other", "--title", bad),
        (str(number), "rename", bad),
        (str(number), "block", "add", bad),
        (str(number), "brief", "append", "--section", "Agent handoff", "--text", bad),
    ):
        result = workspace.run(*arguments)
        assert result.code == 2, arguments
        assert "not valid UTF-8" in result.err and "Traceback" not in result.text


def test_an_unknown_flag_or_value_suggests_the_closest_one(workspace: Backlog) -> None:
    number = str(workspace.add_item("work"))
    err = workspace.refuse("list --archiv", "unrecognized arguments: --archiv", 2)
    assert "Did you mean --archive?" in err
    workspace.refuse(f"{number} cancel --reas x", "--reas", 2)
    assert (
        "Did you mean --remind-before?"
        in workspace.run("list", "--remindbefore", "1").err
    )
    assert (
        "Did you mean --dependents?"
        in workspace.run(number, "dependency", "--dependent").err
    )
    assert "Did you mean" not in workspace.run(number, "dependency", "--zzz").err
    cases = [
        (("list", "--priority", "hgh"), "high"),
        (("list", "--status", "stuk"), "stuck"),
        (("list", "--sort", "priorty"), "priority"),
        (("add", "x", "--title", "t", "--priority", "nrmal"), "normal"),
        ((number, "priority", "hgh"), "high"),
        ((number, "unit", "add", "x", "--kind", "reserch"), "research"),
    ]
    for arguments, close in cases:
        result = workspace.run(*arguments)
        assert result.code == 2 and "allowed:" in result.err, arguments
        assert f"did you mean {close}?" in result.err, arguments
    assert "did you mean" not in workspace.run("list", "--priority", "zzz").err


def test_usage_errors_name_the_action_and_its_guide_section(workspace: Backlog) -> None:
    workspace.add_item("work")
    err = workspace.refuse(
        "1 dependency --reverse", "unrecognized arguments: --reverse", 2
    )
    assert "usage: backlog N dependency [--dependents]" in err
    assert "See: backlog guide dependency" in err and "COMMAND ..." not in err
    err = workspace.run("1", "done").err
    assert "usage: backlog N[/UNIT] done" in err and "See: backlog guide finish" in err
    err = workspace.run("list", "--bogus").err
    assert "usage: backlog list" in err and "See: backlog guide list" in err
    err = workspace.run("1", OldWords.ITEM_CLOSE, "--result", "r").err
    assert f"{OldWords.ITEM_CLOSE} was renamed to done" in err
    assert 'backlog N done --result "..." --source "..."' in err
