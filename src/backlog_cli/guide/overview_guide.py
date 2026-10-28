"""Guide text that is not about one command: purpose, workspace, lifecycle, rules."""


class OverviewGuide:
    PURPOSE = """\
The tool `backlog` keeps the coordinator's list of work for one workspace. It is the only way to change that list: items, the units of work
inside them (a PR to merge and release, or a piece of research), the post-release
actions of a PR, and a details file per item. Everything it stores and prints is
English. Run `backlog guide` once at the start: it prints this overview and the
lifecycle. `backlog guide SECTION` prints one section; `backlog guide all` the
full manual. With `--markdown` the same text is printed as Markdown.

Found a problem in backlog? Do not edit its code or files; report it to the user
with the command, the output and what you expected.

Grammar: global commands by name (`add`, `list`, `search`, `guide`, `bind`,
`unbind`); everything else is `backlog ADDRESS ACTION`: the address first, then
one action. `backlog 43 --help` and `backlog 43/engine --help` list the actions
of that level; `--help` after an action shows its few flags.

An item is work with at least one unit; the units carry the assignees and the
status. A question for the user does not go into the backlog: ask the user directly.
Item statuses: todo (no unit has started; an item without units is todo), wip
(otherwise), done; an item archived without being done keeps cancelled or
superseded. `stuck` marks an item whose units were all cancelled or superseded.
Unit statuses: todo, wip, merged, post_release, done, cancelled, superseded."""

    WORKSPACE = """\
A workspace is an area of coordination. Its data lives under the data root
(`~/.bklg`, or the directory in $BKLG_HOME): `<root>/<workspace>/BACKLOG.yaml`,
ARCHIVE.yaml and details/. The files are written only by this tool; never edit
them. ARCHIVE.yaml is read only by a command that needs archived data.

Which workspace a command uses:

  1. --workspace NAME, before or after the command name (one command);
  2. else the nearest bound directory, from the current one up to /;
  3. else the workspace bound to the origin repository of the current directory
     (`backlog bind NAME --repo OWNER/NAME`; every clone and worktree of it);
  4. else an error that names the directory and the bind commands.

Bind a PARENT directory once and every directory below it resolves; if a project
keeps its task worktrees in one directory, bind that directory:

  backlog bind work --dir ~/src/project-worktrees

There is no "last used workspace": parallel coordinators never write to each
other's workspace by accident."""

    ADDRESSES = """\
Everything is addressed by short paths; the number resolves in the active
registry and in the archive:

  43                  item (or the exact id 0043_fast_order_rt_search)
  43/engine           a unit of work of item 43

The address comes first, then the action: `backlog 43 done ...`,
`backlog 43/engine merged ...`. Several units of one release are one
comma-separated address: `backlog 43/engine,44/api released ...`. A post-release
action is named after its action word:
`backlog 43/engine post_release done check_latency ...`.

Item ids are NNNN_slug and are never reused. Unit and action names are short
lowercase words with underscores that you choose. Archived items are read-only:
a change is refused with the command that creates a linked item
(`backlog add <slug> --title "..." --depends-on 43`)."""

    LIFECYCLE = """\
The life of a piece of work, with the commands. The first item of a new
workspace is number 1; `add` prints the number of every new item.

  1. Bind the directory to a workspace (once; creates the workspace if new):
       backlog bind work
  2. Add the item, write its handoff, export a copy for the executor:
       backlog add fast_order_rt_search --title "Realtime order search" \\
           --tags back,search
       backlog 1 brief append --section "Agent handoff" \\
           --text "Build realtime order search; new orders searchable in 5 s."
       backlog 1 brief export > handoff.md
  3. Add a unit for the PR, give it to an agent (todo becomes wip), link the PR
     (`acme/api#123` means acme/api#123):
       backlog 1 unit add engine --kind pr
       backlog 1/engine assign --agent "Backend agent" --task api:456 --role back
       backlog 1/engine link pr acme/api#123
  4. The PR is merged: check it yourself (`backlog guide checking`), record it:
       backlog 1/engine merged --source "gh pr view 123" --at 2026-10-23
  5. Decide the post-release work before the release: add each action, or
     declare that there is none (`released --no-post-release`):
       backlog 1/engine post_release add check_latency --kind verification \\
           --title "Check search latency" \\
           --instructions "Compare p99 before and after the release"
  6. After the production release, check it yourself and record it:
       backlog 1/engine released --at 2026-10-24T12:00:00Z \\
           --source "release_status api 123" --tag v1.2.0
  7. Perform each check for real, then confirm it with the result and source:
       backlog 1/engine post_release done check_latency \\
           --result "p99 is 1.8 s" --source "how you know it"
     A check that found a problem is recorded with `post_release fail`.
  8. When every unit is finished, `list` and the card say "ready to close". Look,
     then close the item by hand; `done` archives it in the same command:
       backlog 1 done --result "All criteria are met" --source "how you know it"
  9. Find it later: `backlog list --archive`, `backlog search realtime --archive`,
     `backlog 1`.

Other actions:

  - Back from wip to todo (the only way back): `backlog N/UNIT return_to_todo
    --reason "..."`. `unassign` changes no status.
  - A unit that will not be done: `backlog 1/engine cancel --reason "..."` or
    `supersede --by other_unit --reason "..."`. An item: `backlog N cancel
    --reason "..."` or `backlog N supersede --by M --reason "..."`; both archive
    it.
  - Several units released together:
    `backlog 1/engine,2/api released --at ... --source ... --no-post-release 2/api`.
  - A failed post-release check: see `backlog guide post_release`."""

    CHECKING = """\
The tool checks nothing. It runs no external program and calls no service: it
records what you report, with the source. Before `merged` or `released`, check
the fact with your own tools, then say how in `--source`. --source must state
how you know it, really: if you did not see it yourself, ask the user and write the
answer as the source. Never invent a source.

  Use gh (`gh pr view <N> -R OWNER/NAME`), the release tool of the project, or
    ask the user. Take --tag and --at from the release record. No release record
    means it is not in production yet: do not record it. Never record a guess.

A check that failed is never confirmed or cancelled to hide it; the tool cannot
tell it from `--result`. Record it with `post_release fail`.

Example:
  backlog 1/engine released --at 2026-10-23T12:00:00Z --tag v1.2.0 \\
      --source "release_status api 123" --no-post-release"""

    RULES = """\
Enforced by the CLI (a command that breaks one is refused and changes nothing):
  - Item ids are never reused; a slug is used by one item for good. The status
    of an item follows its units and is never set by hand.
  - `merged` and `released` need `--source`; `released` also needs `--at`.
  - Text fields: a one-line field (title, agent, role, task, blocker text,
    reason, source, result, finding, tag, PR) has no control character, no bidi
    mark and no line break or tab, and is at most 300 characters. Only --text,
    --instructions and brief files may span lines (line breaks and tabs only).
    An argument that is not UTF-8 is refused.
  - Dates lie between 2000-01-01 and five years from now. A slug or unit id is
    lowercase letters, digits, `_` and `-`, starts with a letter, at most 60
    characters.
  - Post-release work is decided before a release (actions, or
    --no-post-release). A confirmation is final. After `post_release fail` the
    action is settled only after a unit added after the finding is released.
  - One PR may close units of several items: `merged` is written to every unit
    of that PR, and `released` must list every unit of that PR in one address.
    A repeated `merged` or `released` needs --correction "why".
  - `done` needs every unit finished, one unit done, no open blocker, no pending
    action and every dependency archived as done. A dependency must exist and
    must not close a cycle.
  - Archived items are read-only; the continuation is a new item with
    --depends-on.
  - A workspace written by a newer backlog (a higher schema version) can be read
    but never written ("Update backlog").
  - Writes are locked and atomic. The archive is written before the registry, so
    a crash never loses an item; the next command that changes data repairs it
    and prints "Recovered interrupted archive of <id>". `.bak` files keep the
    previous copy.

Conventions the coordinator follows (the CLI cannot enforce them):
  - Only the coordinator edits the backlog and the details files. Executors
    never get the path of the central files.
  - Adding an item does not start an agent and does not authorise work. Priority
    and deadline change only on the user's instruction.
  - A progress report updates the existing unit; it never creates a duplicate
    item. Where a fact is unknown, say so; a missing confirmation is not a
    failure and a failure is never recorded as success.
  - An exported brief is a copy; tell a running agent about later changes
    separately."""

    EXIT_CODES = """\
  0   done
  1   a valid request was refused (the state does not allow it), or another
      backlog command holds the write lock. The reason and the next command are
      printed; nothing was changed.
  2   usage error: bad address, flag, value, date, regular expression, or an
      unknown workspace. Nothing was changed.

A wrong value of an enum flag lists the allowed values and, when one is close,
says "did you mean ...?"; an unknown flag suggests the closest valid one. Errors
are short: the reason, the exact command to run next, often "See: backlog guide
<section>". They never print help text."""
