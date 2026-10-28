# backlog

A command line tool that keeps a coordinator's backlog of work in local YAML files: items, the units of work inside them (a PR to merge and release, or a piece of research), releases, post-release checks, and one brief per item. The files are written only by this tool. `backlog serve` starts a read-only local web viewer.

## Install

Python 3.14 and three packages:

```sh
pip install pyyaml typed-argument-parser markdown-it-py
```

Put the `backlog` launcher on your PATH, for example:

```sh
ln -s ~/src/backlog/backlog ~/.local/bin/backlog
```

The data lives under `~/.bklg`, or under `$BKLG_HOME` if it is set.

## Quick start

```sh
backlog bind work                                   # bind this directory to workspace "work"
backlog add search_by_phone --title "Search orders by phone"
backlog 1 unit add engine --kind pr                 # a unit of work: a PR
backlog 1/engine assign --agent "Backend agent"     # todo becomes wip
backlog 1/engine link pr acme/api#123
backlog list --attention                            # what needs a look
backlog serve                                       # read-only viewer in a browser
```

The full manual is `backlog guide all`.

## Reference

Everything from here to Development is generated from `backlog guide`, the manual written for
the agents that use the tool. It is here to show what the tool can do; it speaks to
an agent, and "the user" in it is the person the agent works for.

<!-- guide:start -->
## Overview

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
Unit statuses: todo, wip, merged, post_release, done, cancelled, superseded.

## Workspace

A workspace is an area of coordination. Its data lives under the data root
(`~/.bklg`, or the directory in $BKLG_HOME): `<root>/<workspace>/BACKLOG.yaml`,
ARCHIVE.yaml and details/. The files are written only by this tool; never edit
them. ARCHIVE.yaml is read only by a command that needs archived data.

Which workspace a command uses:

```text
  1. --workspace NAME, before or after the command name (one command);
  2. else the nearest bound directory, from the current one up to /;
  3. else the workspace bound to the origin repository of the current directory
     (`backlog bind NAME --repo OWNER/NAME`; every clone and worktree of it);
  4. else an error that names the directory and the bind commands.
```

Bind a PARENT directory once and every directory below it resolves; if a project
keeps its task worktrees in one directory, bind that directory:

```text
  backlog bind work --dir ~/src/project-worktrees
```

There is no "last used workspace": parallel coordinators never write to each
other's workspace by accident.

## Addresses

Everything is addressed by short paths; the number resolves in the active
registry and in the archive:

```text
  43                  item (or the exact id 0043_fast_order_rt_search)
  43/engine           a unit of work of item 43
```

The address comes first, then the action: `backlog 43 done ...`,
`backlog 43/engine merged ...`. Several units of one release are one
comma-separated address: `backlog 43/engine,44/api released ...`. A post-release
action is named after its action word:
`backlog 43/engine post_release done check_latency ...`.

Item ids are NNNN_slug and are never reused. Unit and action names are short
lowercase words with underscores that you choose. Archived items are read-only:
a change is refused with the command that creates a linked item
(`backlog add <slug> --title "..." --depends-on 43`).

## Lifecycle

The life of a piece of work, with the commands. The first item of a new
workspace is number 1; `add` prints the number of every new item.

```text
  1. Bind the directory to a workspace (once; creates the workspace if new):
       backlog bind work
  2. Add the item, write its handoff, export a copy for the executor:
       backlog add fast_order_rt_search --title "Realtime order search" \
           --tags back,search
       backlog 1 brief append --section "Agent handoff" \
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
       backlog 1/engine post_release add check_latency --kind verification \
           --title "Check search latency" \
           --instructions "Compare p99 before and after the release"
  6. After the production release, check it yourself and record it:
       backlog 1/engine released --at 2026-10-24T12:00:00Z \
           --source "release_status api 123" --tag v1.2.0
  7. Perform each check for real, then confirm it with the result and source:
       backlog 1/engine post_release done check_latency \
           --result "p99 is 1.8 s" --source "how you know it"
     A check that found a problem is recorded with `post_release fail`.
  8. When every unit is finished, `list` and the card say "ready to close". Look,
     then close the item by hand; `done` archives it in the same command:
       backlog 1 done --result "All criteria are met" --source "how you know it"
  9. Find it later: `backlog list --archive`, `backlog search realtime --archive`,
     `backlog 1`.
```

Other actions:

```text
  - Back from wip to todo (the only way back): `backlog N/UNIT return_to_todo
    --reason "..."`. `unassign` changes no status.
  - A unit that will not be done: `backlog 1/engine cancel --reason "..."` or
    `supersede --by other_unit --reason "..."`. An item: `backlog N cancel
    --reason "..."` or `backlog N supersede --by M --reason "..."`; both archive
    it.
  - Several units released together:
    `backlog 1/engine,2/api released --at ... --source ... --no-post-release 2/api`.
  - A failed post-release check: see `backlog guide post_release`.
```

## Serve

```text
backlog serve [--port N]
```

A local web viewer of every workspace in the data root (BKLG_HOME, default
~/.bklg). It listens on 127.0.0.1 only, prints its address and runs until
Ctrl+C. --port N picks the port (default 8765); a port in use is exit 2.

It never writes to the data: no lock, no repair, nothing cached; every page
reads the files again, so F5 shows what the CLI changed a moment ago.
A path in a text that exists on disk is a link: a click shows a preview of the
file (markdown rendered, text, image) with buttons to open it, reveal it in
Finder or copy the path; a folder offers Finder or copy. Open and reveal run
the macOS `open` command, the only program the viewer starts. Requests with a
foreign Host header, and an open request from another origin, are refused.
Pages of a workspace:

```text
  /NAME/               what needs attention (the groups of `list --attention`)
  /NAME/items          active items; filters status and tag, sort (default:
                       closest to closing first, by the least advanced unit)
  /NAME/items/N        the card: units, post-release checks, corrections,
                       links, the brief rendered from markdown; an archived
                       item shows its outcome
  /NAME/archive        archived items, newest first
  /NAME/search?q=...   `search`; add &regex=1 for a regular expression and
                       &archive=1 for the archive
```

`/` opens the first workspace. The archive file is opened only by the archive
pages, the archive search and the card of an archived item.
Every workspace in the rail shows its attention and active item counts, read
from its BACKLOG file only.

To keep it running, save a launchd job as
~/Library/LaunchAgents/local.backlog.serve.plist (backlog does not install it)
and load it with `launchctl load` on that file:

```text
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
   "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0"><dict>
    <key>Label</key><string>local.backlog.serve</string>
    <key>ProgramArguments</key><array>
      <string>/ABSOLUTE/PATH/TO/backlog</string><string>serve</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardErrorPath</key><string>/tmp/backlog-serve.log</string>
  </dict></plist>
```

Examples:

```text
  backlog serve
  backlog serve --port 9000
```

## Commands

- `backlog add SLUG --title "..." [--priority high|normal|low] [--tags a,b] [--due DATE] [--reminder DATE] [--depends-on 41,42]` — Add an item; prints its number.
- `backlog list [--attention] [--status S] [--priority P] [--tag T] [--assignee TEXT] [--can-start] [--sort number|priority|due] [--remind-before DATE] [--archive]` — List items with their units.
- `backlog search WORD [WORD ...] [--regex] [--archive] [--case-sensitive]` — Search items and details for words, or one regular expression.
- `backlog guide [SECTION] [--markdown]` — Print the overview and lifecycle, one section, or all.
- `backlog bind WORKSPACE [--dir PATH | --repo OWNER/NAME ...]` — Bind a directory or repositories to a workspace (created if new).
- `backlog unbind [--dir PATH | --repo OWNER/NAME]` — Remove the binding of a directory or a repository (data is kept).
- `backlog serve [--port N]` — Show every workspace in a browser; read-only, local.
- `backlog N[/UNIT] [show] [--full]` — Show an item or a unit as a readable card (archived items too).
- `backlog N rename "TITLE"` — Change the title of the item.
- `backlog N priority high|normal|low` — Set the priority of the item.
- `backlog N tag add TAG [TAG ...]` — Add tags (lowercase letters, digits, dashes).
- `backlog N tag remove TAG [TAG ...]` — Remove tags the item has.
- `backlog N due add DATE` — Set the deadline (replaces the old one).
- `backlog N due delete` — Remove the deadline.
- `backlog N reminder add DATE` — Set the reminder (replaces the old one).
- `backlog N reminder delete` — Remove the reminder.
- `backlog N block add "TEXT" [--waiting-on WHO]` — Record an outside condition the item waits for; prints its id.
- `backlog N block remove bK --reason "..."` — Close a blocker and keep it in the record, with the reason.
- `backlog N dependency [--dependents]` — Show dependencies, blockers, prerequisite PRs (--dependents: reverse).
- `backlog N dependency add X [X ...]` — Depend on items (by number) or on PRs (OWNER/NAME#N).
- `backlog N dependency remove X [X ...]` — Drop dependencies: items by number, PRs as OWNER/NAME#N.
- `backlog N/UNIT assign --agent A [--task T] [--role R]` — Give a unit to an agent: adds an assignee; todo becomes wip.
- `backlog N/UNIT unassign (--agent A | --task T | --role R)` — Remove assignees by agent, task or role; the status does not change.
- `backlog N/UNIT return_to_todo --reason "..."` — Send a unit back from wip to todo.
- `backlog N[/UNIT] cancel --reason "..."` — Drop the item (it is archived) or the unit; it will not be done.
- `backlog N[/UNIT] supersede --by M|U2 --reason "..."` — Replace the item (archived) or the unit by one that continues it.
- `backlog N brief show [--section NAME]` — Print the details file or one section.
- `backlog N brief set --from-file FILE` — Replace the details with a UTF-8 file (8 sections, no title line).
- `backlog N brief replace --section NAME (--text TEXT | --from-file FILE)` — Replace the whole content of one section.
- `backlog N brief append --section NAME (--text TEXT | --from-file FILE)` — Append text to one section.
- `backlog N brief export > handoff.md` — Print the executor copy to stdout: title, number and the sections (Problem and expected result; Scope and exclusions; Known facts and sources; Decisions and rationale; Acceptance criteria; Agent handoff; Implementation and release history; Verification results, limitations and post-release instructions); an empty section says (empty).
- `backlog N unit` — List the units of the item, one line each.
- `backlog N unit add NAME [--kind pr|research]` — Add a unit of work: a PR to merge and release, or research.
- `backlog N/UNIT link pr OWNER/NAME#N` — Record the PR of a unit, before its merge is recorded.
- `backlog N[/UNIT] done --result "..." --source "..." [--at DATE]` — Close the item with your result (it is archived as done), or finish a research unit.
- `backlog N/UNIT merged --source "..." [--at DATE] [--result "..."] [--pr PR] [--correction "why"]` — Record that the PR of the unit is merged, with how you checked it.
- `backlog N/UNIT[,N/UNIT ...] released --at DATE --source "..." [--tag TAG] [--no-post-release [N/UNIT]] [--correction "why"]` — Record that merged units reached production (several: 43/a,44/b).
- `backlog N/UNIT post_release` — List the post-release actions of the unit, one line each.
- `backlog N/UNIT post_release add NAME --kind command|verification|admin_change --title "..." --instructions "..."` — Add something to do or check in production after the release.
- `backlog N/UNIT post_release edit NAME [--title "..."] [--instructions "..."]` — Change the title or instructions of a pending action.
- `backlog N/UNIT post_release fail NAME --finding "..." --source "..." [--at DATE]` — Record that a check failed; the action stays pending.
- `backlog N/UNIT post_release done NAME [NAME ...] --result "..." --source "..."` — Record the result of post-release actions that were run.
- `backlog N/UNIT post_release cancel NAME --reason "..." [--not-needed]` — Cancel a post-release action; after release it must be --not-needed.
<!-- guide:end -->

## Development

```sh
python3 -m pytest -q
python3 tools/update_readme.py   # after a change of the guide or of a command's help
```
