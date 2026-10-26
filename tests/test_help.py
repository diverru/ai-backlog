"""Short help, the guide, and short errors."""

import re
import shlex

import pytest

from backlog_cli.cli import Cli
from backlog_cli.command.guide import GuideCommand
from backlog_cli.command.router import ActionTable
from backlog_cli.domain.vocabulary import AddressLevel
from backlog_cli.guide.overview_guide import OverviewGuide
from conftest import Backlog, OldWords

ROOT_LINE_LIMIT = 30
ACTION_LINE_LIMIT = 15
ADDRESS_OF_LEVEL = {AddressLevel.ITEM: "1", AddressLevel.UNIT: "1/engine"}
# `backlog 1 dependency --help` lists the group; the card of a word that also
# starts a group is its group listing.
EVERY_ACTION = [
    (action, level)
    for action in ActionTable.ACTIONS
    for level in action.LEVELS
    if len(action.WORDS) > 1 or action.WORDS[0] not in ActionTable.get_group_words()
]


@pytest.mark.parametrize("command", Cli.COMMANDS, ids=lambda c: c.NAME)
def test_every_global_help_stays_short(backlog: Backlog, command: type) -> None:
    result = backlog.run(command.NAME, "--help")
    assert result.code == 0
    lines = result.out.splitlines()
    assert len(lines) <= ACTION_LINE_LIMIT, f"{command.NAME}:\n{result.out}"
    assert lines[0].startswith("usage: backlog ")


@pytest.mark.parametrize(
    "action,level",
    EVERY_ACTION,
    ids=lambda value: " ".join(value.WORDS) if hasattr(value, "WORDS") else str(value),
)
def test_every_action_help_stays_short(
    backlog: Backlog, action: type, level: AddressLevel
) -> None:
    result = backlog.run(ADDRESS_OF_LEVEL[level], *action.WORDS, "--help")
    assert result.code == 0, result.text
    lines = result.out.splitlines()
    assert len(lines) <= ACTION_LINE_LIMIT, (
        f"{action.WORDS}: {len(lines)}\n{result.out}"
    )
    assert lines[0].startswith("usage: backlog ")
    assert lines[-1].startswith("Example")
    flags = re.findall(r"^  (--[a-z-]+)", result.out, re.MULTILINE)
    assert len(flags) == len(set(flags))  # one line per flag


def test_root_help_is_short_and_names_every_action(backlog: Backlog) -> None:
    for arguments in (("--help",), ()):
        result = backlog.run(*arguments)
        assert result.code == (0 if arguments else 2)
        assert len(result.out.splitlines()) <= ROOT_LINE_LIMIT, result.out
    out = backlog.run("--help").out
    assert "Read `backlog guide`" in out or "Run `backlog guide`" in out
    assert "Item:" in out and "Unit:" in out
    for command in Cli.COMMANDS:
        assert command.NAME in out
    for action in ActionTable.ACTIONS:
        assert action.WORDS[0] in out, action.WORDS


@pytest.mark.parametrize(
    "address,level",
    [("1", AddressLevel.ITEM), ("1/engine", AddressLevel.UNIT)],
)
def test_level_help_lists_one_line_per_action(
    backlog: Backlog, address: str, level: AddressLevel
) -> None:
    out = backlog.run(address, "--help").out
    lines = out.splitlines()[1:]
    expected = [" ".join(action.WORDS) for action in ActionTable.for_level(level)]
    assert [line.split("  ")[1].strip() for line in lines] == expected
    assert all(line.startswith("  ") for line in lines)


def test_group_help_lists_the_actions_of_the_group(backlog: Backlog) -> None:
    out = backlog.run("1/engine", "post_release", "--help").out
    names = [line.split("  ")[1].strip() for line in out.splitlines()[1:]]
    assert names == [
        "post_release",
        "post_release add",
        "post_release edit",
        "post_release fail",
        "post_release done",
        "post_release cancel",
    ]
    out = backlog.run("1", "brief", "--help").out
    assert out.count("brief ") >= 5 and "post_release" not in out


def test_an_action_of_the_wrong_level_says_where_it_lives(backlog: Backlog) -> None:
    unit_action = backlog.run("1", "merged", "--source", "x")
    assert unit_action.code == 2
    assert unit_action.err.startswith("merged is a unit action: backlog N/UNIT merged")
    item_action = backlog.run("1/engine", "priority", "low")
    assert item_action.code == 2
    assert item_action.err.startswith("priority is an item action: backlog N priority")
    assert backlog.run("1/engine", "tag", "add", "x").err.startswith(
        "tag add is an item"
    )


def test_a_mistyped_action_or_command_gets_did_you_mean(backlog: Backlog) -> None:
    assert "did you mean assign?" in backlog.run("1/engine", "asign").err
    assert (
        "did you mean return_to_todo?" in backlog.run("1/engine", "return_to_tod").err
    )
    assert "did you mean merged?" in backlog.run("1/engine", "mergd").err
    assert "did you mean list?" in backlog.run("lst").err
    assert "needs an action: tag add|remove" in backlog.run("1", "tag").err
    assert "tag add|remove" in backlog.run("1", "tag", "adds", "x").err
    for old in OldWords.COMMANDS:
        result = backlog.run(old, "1")
        assert result.code == 2 and f"unknown command {old!r}" in result.err
    for old_flag in (OldWords.NEXT_FLAG, "--to", "--follow-up"):
        assert backlog.run("list", old_flag).code == 2


def test_guide_prints_everything_and_single_sections(backlog: Backlog) -> None:
    everything = backlog.ok("guide", "all")
    for section in GuideCommand.SECTIONS:
        assert section.text in everything
    only_unit = backlog.ok("guide", "unit")
    assert "STATUSES" in only_unit and "ADDRESSES" not in only_unit
    assert "Enforced by the CLI" in backlog.ok("guide", "rules")
    result = backlog.run("guide", "nosuch")
    assert result.code == 2 and "sections:" in result.err


def test_every_section_the_commands_point_to_exists(backlog: Backlog) -> None:
    names = {section.name for section in GuideCommand.SECTIONS}
    for action in ActionTable.ACTIONS:
        assert action.GUIDE_SECTION in names, action.WORDS
    for command in Cli.COMMANDS:
        assert command.NAME in names or command.NAME in ("bind", "unbind", "guide")


def test_every_flag_of_every_command_is_in_the_guide(backlog: Backlog) -> None:
    guide = backlog.ok("guide", "all")
    flags = set()
    for command in Cli.COMMANDS:
        flags.update(
            re.findall(r"--[a-z][a-z-]*", backlog.run(command.NAME, "--help").out)
        )
    for action, level in EVERY_ACTION:
        address = ADDRESS_OF_LEVEL[level]
        flags.update(
            re.findall(
                r"--[a-z][a-z-]*", backlog.run(address, *action.WORDS, "--help").out
            )
        )
    for flag in flags - {"--help", "--workspace", "--dry-run"}:
        assert flag in guide, flag


def test_the_guide_uses_no_old_vocabulary(backlog: Backlog) -> None:
    guide = backlog.ok("guide", "all")
    old_words = [
        *(f"backlog {command}" for command in OldWords.COMMANDS),
        OldWords.NEXT_FLAG,
        OldWords.ITEM_CLOSE,
        "to_" + OldWords.ITEM_CLOSE,
        OldWords.STATUS_MIDDLE,
        OldWords.VERB,
        OldWords.NOUN,
        "urgent",
        "medium",
        "plan",
    ]
    for old in old_words:
        assert old not in guide, old


def test_errors_are_short_and_never_print_help(backlog: Backlog) -> None:
    backlog.ok("bind", "ws")
    for arguments in (
        ("99", "done"),
        ("add",),
        ("frobnicate",),
        ("1", "rename"),
        ("1", "frobnicate"),
        ("1/engine", "merged"),
    ):
        result = backlog.run(*arguments)
        assert result.code == 2, arguments
        assert "Traceback" not in result.err
        assert len(result.err.splitlines()) <= 4, result.err


def test_the_guide_invents_no_source_and_says_how_to_state_a_real_one(
    backlog: Backlog,
) -> None:
    guide = backlog.ok("guide", "all")
    for invented in ("User accepted", "Agent report", "prod check"):
        assert invented not in guide, invented
    for section in ("finish", "checking"):
        text = backlog.ok("guide", section)
        assert "if you did not see it yourself, ask the user" in " ".join(text.split())
        assert "write the answer as the source" in " ".join(text.split())


def test_the_guide_overview_is_short_and_the_lifecycle_runs_end_to_end(
    backlog: Backlog,
) -> None:
    short = backlog.ok("guide")
    assert "OVERVIEW" in short and "LIFECYCLE" in short and "guide all" in short
    assert "STATUSES" not in short
    assert "Found a problem in backlog? Do not edit its code or files" in short
    assert len(short.splitlines()) < len(backlog.ok("guide", "all").splitlines()) / 2
    text = OverviewGuide.LIFECYCLE.replace("\\\n", " ")
    for line in text.splitlines():
        if line.strip().startswith("backlog "):
            words = shlex.split(line.strip())[1:]
            words = words[: words.index(">")] if ">" in words else words
            result = backlog.run(*words)
            assert result.code == 0, f"{words}\n{result.text}"
    assert "archive" in backlog.ok("1").splitlines()[0]


def test_date_flags_say_what_a_date_alone_means(backlog: Backlog) -> None:
    date_help = "YYYY-MM-DD or ISO datetime with offset (UTC Z ok)"
    for arguments in (
        ("1/engine", "merged", "--help"),
        ("1/engine", "released", "--help"),
        ("1/engine", "post_release", "fail", "--help"),
        ("1", "done", "--help"),
    ):
        out = backlog.ok(*arguments)
        assert f"{date_help}; not in the future" in out, arguments
        assert "a date alone means the end of that day, or now for today" in out
    for arguments in (("add", "--help"), ("1", "due", "add", "--help")):
        out = backlog.ok(*arguments)
        assert date_help in out and "not in the future" not in out, arguments
    assert "--no-post-release 44/api" in backlog.ok("1/engine", "released", "--help")
    assert "--correction" in backlog.ok("--help")
