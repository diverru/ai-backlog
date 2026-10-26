"""`bind` and `unbind`: which directory or repository belongs to a workspace."""

from dataclasses import dataclass
from pathlib import Path

from tap import Positional

from backlog_cli.command.base import Command, ShortHelpParser
from backlog_cli.errors import UsageError
from backlog_cli.store.atomic import FileLock
from backlog_cli.store.binding import BindingConfig
from backlog_cli.store.repo_origin import RepoOrigin
from backlog_cli.store.workspace import Workspace


class BindParser(ShortHelpParser):
    name: Positional[str]  # Workspace name (a-z, 0-9, . - _); created if new.
    dir: str | None = None  # Directory to bind (default: the current one).
    repo: list[str] = []  # GitHub repository OWNER/NAME to bind; repeat the flag.
    dry_run: bool = False  # Print what would change and write nothing.

    def configure(self) -> None:
        self.add_argument("name", metavar="WORKSPACE")
        self.add_argument("--repo", action="append", default=[], metavar="OWNER/NAME")


class UnbindParser(ShortHelpParser):
    dir: str | None = None  # Directory to unbind (default: the current one).
    repo: str | None = None  # GitHub repository OWNER/NAME to unbind.
    dry_run: bool = False  # Print what would change and write nothing.


@dataclass
class BindPlan:
    config: BindingConfig
    workspace: Workspace
    is_new_workspace: bool
    lines: list[str]


class BindCommand(Command):
    NAME = "bind"
    SUMMARY = "Bind a directory or repositories to a workspace (created if new)."
    USAGE = "backlog bind WORKSPACE [--dir PATH | --repo OWNER/NAME ...]"
    EXAMPLES = (
        "Examples:\n"
        "  backlog bind work --dir ~/src/project-worktrees\n"
        "  backlog bind work --repo acme/api --repo acme/web"
    )
    Parser = BindParser

    def run(self, args: BindParser) -> int:
        if not Workspace.NAME_PATTERN.match(args.name):
            raise UsageError(Workspace.describe_bad_name(args.name))
        repos = [RepoOrigin.require_name(text) for text in args.repo]
        directory = None
        if args.dir or not repos:  # --repo alone binds no directory
            directory = (
                self.session.cwd / Path(args.dir or ".").expanduser()
            ).resolve()
            if not directory.is_dir():
                raise UsageError(f"{directory} is not a directory")
        home = self.session.home
        if args.dry_run:
            plan = self._plan(args.name, directory, repos)
            self.print_lines(
                "Dry run, nothing written. These changes would be made:", *plan.lines
            )
            return 0
        home.mkdir(parents=True, exist_ok=True)
        with FileLock(home / ".lock"):
            plan = self._plan(args.name, directory, repos)
            if plan.is_new_workspace:
                plan.workspace.create()
            plan.config.save()
        lines = list(plan.lines)
        if self._is_empty(plan):
            lines.append('Next: backlog add SLUG --title "..."')
        self.print_lines(*lines)
        return 0

    @staticmethod
    def _is_empty(plan: "BindPlan") -> bool:
        if plan.is_new_workspace:
            return True
        registry = plan.workspace.load_registry()
        return not registry.active and not registry.archived_item_ids

    def _plan(self, name: str, directory: Path | None, repos: list[str]) -> "BindPlan":
        config = BindingConfig.load(self.session.home)
        lines = []
        if directory:
            if config.bind(directory, name):
                lines.append(f"Bound {directory} to workspace {name}")
            else:
                lines.append(f"{directory} is already bound to {name}")
        for repo in repos:
            if config.bind_repo(repo, name):
                lines.append(f"Bound repository {repo} to workspace {name}")
            else:
                lines.append(f"Repository {repo} is already bound to {name}")
        workspace = Workspace(self.session.home, name)
        if not workspace.is_created:
            lines.append(f"Created workspace {name} at {workspace.root}")
        return BindPlan(config, workspace, not workspace.is_created, lines)


class UnbindCommand(Command):
    NAME = "unbind"
    SUMMARY = "Remove the binding of a directory or a repository (data is kept)."
    USAGE = "backlog unbind [--dir PATH | --repo OWNER/NAME]"
    EXAMPLES = (
        "Examples:\n"
        "  backlog unbind --dir ~/src/project-worktrees\n"
        "  backlog unbind --repo acme/api"
    )
    Parser = UnbindParser

    def run(self, args: UnbindParser) -> int:
        home = self.session.home
        if args.dry_run:
            self.print_lines("Dry run, nothing written. These changes would be made:")
            self._unbind(BindingConfig.load(home), args)
            return 0
        home.mkdir(parents=True, exist_ok=True)
        with FileLock(home / ".lock"):
            config = BindingConfig.load(home)
            self._unbind(config, args)
            config.save()
        return 0

    def _unbind(self, config: BindingConfig, args: UnbindParser) -> None:
        if args.repo:
            workspace = config.unbind_repo(RepoOrigin.require_name(args.repo))
            self.print_lines(
                f"Unbound repository {args.repo} (was workspace {workspace}). "
                "Workspace data is kept."
            )
        if args.dir or not args.repo:
            directory = (
                self.session.cwd / Path(args.dir or ".").expanduser()
            ).resolve()
            workspace = config.unbind(directory)
            self.print_lines(
                f"Unbound {directory} (was workspace {workspace}). "
                "Workspace data is kept."
            )
