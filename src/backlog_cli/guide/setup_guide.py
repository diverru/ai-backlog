"""Guide text of the commands that set a workspace up."""


class SetupGuide:
    BIND = """\
Bind a directory or a repository to a workspace, so that every backlog command
run there uses the workspace. The workspace (BACKLOG.yaml, ARCHIVE.yaml,
details/ under the data root) is created if it does not exist.

Bind a PARENT directory when many directories work on one workspace. If a
project keeps its task worktrees in one directory, bind that directory once;
every worktree below it then resolves by itself:
  backlog bind work --dir ~/src/project-worktrees

Bind a GitHub repository (OWNER/NAME, repeat --repo for several) and every clone
or worktree of it resolves, wherever it lives. --repo alone binds no directory.
The repository of a directory is the `origin` remote in its .git files; other
remotes are ignored. Only github.com addresses (git@, ssh://, https://) count.
A repository belongs to one workspace: binding it to a second one is refused.

Which workspace a command uses: --workspace; else the nearest bound directory
(from the current one up to /); else the origin repository of the current
directory; else an error. A directory can be bound to one workspace; unbind it
first to change that (binding again to the same one prints "already bound").
A command that found its workspace by repository says so in its first line.
Workspace name: lowercase letters, digits, dots, dashes, underscores; it
starts with a letter or a digit; at most 64 characters.
Side effects: writes config.yaml in the data root (BKLG_HOME, default ~/.bklg)
and may create the workspace files.

Examples:
  backlog bind work
  backlog bind work --dir ~/src/project-worktrees
  backlog bind work --repo acme/api --repo acme/web
  backlog bind home --dir ~/src/project --dry-run
"""

    UNBIND = """\
Remove the binding of one directory (exactly that directory, not its parents)
or, with --repo OWNER/NAME, of one repository. The workspace and its data stay.
Side effects: writes config.yaml in the data root.

Examples:
  backlog unbind
  backlog unbind --repo acme/api
  backlog unbind --dir ~/src/project-worktrees
"""
