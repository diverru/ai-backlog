"""A workspace found by the origin repository of the current directory."""

from pathlib import Path

import pytest
import yaml

from conftest import Backlog


def make_clone(root: Path, name: str, remotes: dict[str, str]) -> Path:
    """A clone: a `.git` directory whose config holds the remotes."""
    clone = root / name
    (clone / ".git").mkdir(parents=True)
    blocks = [f'[remote "{key}"]\n\turl = {url}\n' for key, url in remotes.items()]
    (clone / ".git" / "config").write_text(
        "[core]\n\tbare = false\n" + "".join(blocks), encoding="utf-8"
    )
    (clone / "src" / "deep").mkdir(parents=True)
    return clone


def make_worktree(root: Path, name: str, clone: Path) -> Path:
    """A worktree: `.git` is a file that points into the clone's `.git/worktrees`."""
    git_dir = clone / ".git" / "worktrees" / name
    git_dir.mkdir(parents=True)
    (git_dir / "commondir").write_text("../..\n")
    worktree = root / name
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {git_dir}\n")
    return worktree


def test_a_clone_and_a_worktree_resolve_by_origin(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "Bound repository acme/api to workspace ws" in backlog.ok(
        "bind", "ws", "--repo", "acme/api", "--repo", "acme/web"
    )
    clone = make_clone(backlog.root, "clone", {"origin": "git@github.com:Acme/Api.git"})
    worktree = make_worktree(backlog.root, "task", clone)
    for directory in (clone / "src" / "deep", worktree):
        monkeypatch.chdir(directory)
        result = backlog.run("add", f"in_{directory.name}", "--title", "t")
        assert "Created item" in result.out
        assert "found by repository acme/api" in result.err
    assert len(backlog.read_items()) == 2
    monkeypatch.chdir(clone)
    result = backlog.run("list", "--attention")
    assert "found by repository" in result.err and "found by" not in result.out
    assert "workspace:" not in backlog.ok("list")


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:acme/api",
        "ssh://git@github.com/acme/api.git",
        "https://github.com/acme/api.git",
        "https://github.com/ACME/API",
        "https://token@github.com/acme/api/",
    ],
)
def test_every_origin_form_is_read(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    backlog.ok("bind", "ws", "--repo", "acme/api")
    monkeypatch.chdir(make_clone(backlog.root, "c", {"origin": url}))
    assert "found by repository" in backlog.run("list").err


def test_only_origin_counts_and_unknown_hosts_are_not_resolved(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    backlog.ok("bind", "ws", "--repo", "acme/api")
    fork = make_clone(
        backlog.root,
        "fork",
        {"upstream": "git@github.com:acme/api.git", "origin": "git@github.com:me/x"},
    )
    other_host = make_clone(
        backlog.root, "gl", {"origin": "git@gitlab.com:acme/api.git"}
    )
    no_origin = make_clone(
        backlog.root, "none", {"upstream": "git@github.com:acme/api.git"}
    )
    for directory in (fork, other_host, no_origin):
        monkeypatch.chdir(directory)
        result = backlog.run("list")
        assert result.code == 2 and "--repo OWNER/NAME" in result.err


def test_a_directory_binding_wins_over_the_repository(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    backlog.ok("bind", "by_repo", "--repo", "acme/api")
    clone = make_clone(backlog.root, "c", {"origin": "git@github.com:acme/api.git"})
    backlog.ok("bind", "by_dir", "--dir", str(clone))
    monkeypatch.chdir(clone)
    assert "found by repository" not in backlog.run("add", "x", "--title", "t").text
    assert len(backlog.read_items(workspace="by_dir")) == 1


def test_a_repository_of_another_workspace_is_refused_and_nothing_changes(
    backlog: Backlog,
) -> None:
    backlog.ok("bind", "ws", "--repo", "acme/api")
    before = (backlog.home / "config.yaml").read_text()
    err = backlog.refuse("bind two --repo Acme/Api", "backlog unbind --repo")
    assert "workspace ws" in err
    assert (backlog.home / "config.yaml").read_text() == before
    assert not (backlog.home / "two").exists()
    assert "already bound to ws" in backlog.ok("bind", "ws", "--repo", "ACME/api")
    assert "Unbound repository" in backlog.ok("unbind", "--repo", "acme/API")
    backlog.ok("bind", "two", "--repo", "acme/api")
    assert "bad" in backlog.run("bind", "two", "--repo", "bad").err


def test_an_old_config_without_repos_loads_and_stays_without_them(
    backlog: Backlog, monkeypatch: pytest.MonkeyPatch
) -> None:
    backlog.ok("bind", "ws")
    config = backlog.home / "config.yaml"
    assert "repos" not in yaml.safe_load(config.read_text())
    backlog.ok("bind", "ws", "--repo", "a/b")
    assert yaml.safe_load(config.read_text())["repos"] == {"a/b": "ws"}
    backlog.ok("unbind", "--repo", "a/b")
    assert "repos" not in yaml.safe_load(config.read_text())
    assert backlog.ok("list").startswith("workspace: ws")


def test_no_binding_at_all_has_the_repo_hint(backlog: Backlog) -> None:
    result = backlog.run("list")
    assert result.code == 2
    assert "backlog bind WORKSPACE --repo OWNER/NAME" in result.err
