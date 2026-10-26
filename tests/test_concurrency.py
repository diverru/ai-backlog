"""Atomic writes, parallel writers, and the rule that no program is started."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from backlog_cli.store.atomic import AtomicFile
from conftest import Backlog


def test_a_failed_write_leaves_no_temp_file(workspace: Backlog) -> None:
    directory = workspace.work / "taken"
    directory.mkdir()
    with pytest.raises(IsADirectoryError):
        AtomicFile.write(directory, "text")
    assert [path.name for path in workspace.root.rglob("*.tmp")] == []


def test_parallel_adds_get_distinct_ids(workspace: Backlog) -> None:
    launcher = Path(__file__).resolve().parents[1] / "backlog"
    processes = [
        subprocess.Popen(
            [sys.executable, str(launcher), "add", f"item{i}", "--title", f"Item {i}"],
            cwd=workspace.work,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(8)
    ]
    outputs = [process.communicate() for process in processes]
    assert [process.returncode for process in processes] == [0] * 8, outputs
    ids = [item["id"] for item in workspace.read_items()]
    assert sorted(int(item_id.split("_")[0]) for item_id in ids) == list(range(1, 9))
    assert "next_id: 9" in workspace.workspace_file("BACKLOG.yaml").read_text()


def test_the_source_starts_one_program_only_to_open_a_clicked_path() -> None:
    source = Path(__file__).resolve().parents[1] / "src"
    offenders = [p for p in source.rglob("*.py") if "subprocess" in p.read_text()]
    assert [p.relative_to(source).as_posix() for p in offenders] == [
        "backlog_cli/serve/opener.py"
    ]
