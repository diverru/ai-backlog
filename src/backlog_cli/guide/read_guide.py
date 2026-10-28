"""Guide text of the commands that read items and details."""


class ReadGuide:
    SHOW = """\
backlog N [show] [--full]      backlog N/UNIT [show] [--full]

Show one item (or one unit) as a card that fits one screen: number and title,
status, priority, tags, due and reminder, the dependencies (each marked done or
NOT DONE), open blockers, the units (one line each, as in `list`), every
post-release action with its findings or its confirmation, the corrections, and
one closing line: `next: ready to close: backlog N done ...`, `closing: blocked:`
with the first obstacle and the command to run, or, for work that has not
started, `waiting:` (the dependency) or `not started:` (assign an agent). An
archived item carries `[archived]` and a `closed:` line with the outcome, the
result or the reason and the source. A unit card shows that unit: its merge, its
release, its actions, corrections and outcome.

--full prints the stored record as YAML instead (the first line is `# source:
active` or `# source: archive`). The details file is read with `backlog N brief
show`.

Examples:
  backlog 43
  backlog 0043_fast_order_rt_search show
  backlog 43/engine show --full
"""

    LIST = """\
The first line is `workspace: NAME`. Active items ordered by number: number,
status, priority, title, tags, due, reminder and `deps: 1,7(cancelled)` (every
dependency that is not done; an archived one is marked with its outcome). Each
open blocker has its own line. The item status is todo or wip (done only in
`list --archive`), or stuck. Once every unit is finished an item gets a line:
`ready to close: backlog N done ...` when `done` would pass now, else
`blocked:` (the first obstacle and the command). Under each item every unit has
a short line (id, kind, status, PR, assignees, `released TAG`); a unit in
post_release adds one line per pending action, `... — FAILED: finding` after
`post_release fail`. `list --archive` shows the archive with the outcome.

Filters (all optional, combined with AND):
  --status todo|wip|stuck
  --priority high|normal|low
  --tag TAG
  --remind-before DATE   reminder strictly before DATE (by date, UTC)
  --assignee TEXT        an agent, task or role of any unit contains TEXT
  --can-start            status todo, no open blocker, every dependency archived
                         as done
  --sort number|priority|due   default number; due: earliest first
  --attention            only what needs a decision now, a group per heading:
                         blockers, reminders due, overdue, ready to close,
                         failed post-release checks, pending actions, merged
                         units waiting for a release, wip without an assignee,
                         todo units of a wip item, stuck items, "Can start
                         now", "Empty brief". Nothing found prints `Nothing needs
                         attention.` Not with --archive.
  --archive              the archive instead: number, outcome, title

Examples:
  backlog list --attention
  backlog list --can-start --sort priority
  backlog list --assignee api:470
  backlog list --status wip --tag back
  backlog list --archive
"""

    SEARCH = """\
backlog search WORD [WORD ...] [--regex] [--archive] [--case-sensitive]

Search the fields of the items and their details files. The query is plain text,
case-insensitive, and no character in it is special. Several words match an item
that contains every word, in any order and in any searched field. Quote a phrase
to keep it as one word. The query is not empty and at most 200 characters.

  --regex, -E        read the query as ONE Python regular expression; quote it
                     in single quotes. It stops after 5 seconds: `pattern took
                     longer than 5 s; simplify it` (exit 2). A bad expression is
                     exit 2.
  --archive          also search archived items and their details
  --case-sensitive   default is case-insensitive

Matches are grouped by item, ordered by number. A registry match shows the field
path (work.engine.pr.repo); a details match the section and line number. At most
5 matches per item ("+N more"). Service fields (ids, statuses, kinds, moments)
never match. No match prints "No matches" (exit 0), with the number of archived
matches and the --archive command, or, when the query has regex characters but
no --regex, "searched as plain text; for a regular expression add --regex".

Examples:
  backlog search timeout deadlock
  backlog search --regex 'search.*index'
  backlog search checkout --archive
"""

    BRIEF = """\
The details file of an item (details/<id>.md) holds the story of the work. It
has a title line managed by the CLI and exactly these eight `##` sections, in
this order:

  ## Problem and expected result
  ## Scope and exclusions
  ## Known facts and sources
  ## Decisions and rationale
  ## Acceptance criteria
  ## Agent handoff
  ## Implementation and release history
  ## Verification results, limitations and post-release instructions

`###` headings inside a section are fine; a text may not hold a line that starts
with `## `. Text may span lines (line breaks and tabs only: no other control
character, no bidi mark). It must not mention the central files (the data root
path, `.bklg`, `BACKLOG.yaml`, `ARCHIVE.yaml`, `details/`, in any case): the
executor receives the whole file. The details of an archived item can be read
but not changed. Every change takes --dry-run.

A command that touches an item with an empty `Problem and expected result`
section prints `Note: the brief of N is empty...` after its output (the exit code
stays 0), and `list --attention` lists the item under "Empty brief".

backlog N brief show [--section NAME]
  The whole file, or the body of one section (NAME is the exact heading).
backlog N brief set --from-file FILE
  Replace the whole file. The file is UTF-8 (a BOM is dropped) with exactly the
  eight headings, once each, in order. A `# ` title line before the first `## `
  is refused; only the exact generated first line of `brief show` is dropped, so
  its output can be fed back.
backlog N brief replace --section NAME (--text TEXT | --from-file FILE)
  Replace the content of one section.
backlog N brief append --section NAME (--text TEXT | --from-file FILE)
  Add a new paragraph at the end of one section.
backlog N brief export
  Print the executor copy to STDOUT (`# <number>: <title>` and every section; an
  empty one says `(empty)`). Redirect it yourself: `backlog 43 brief export >
  ~/coordinator/handoffs/43.md`. The copy does not follow later edits.

Examples:
  backlog 43 brief show --section "Agent handoff"
  backlog 43 brief set --from-file /tmp/details.md
  backlog 43 brief append --section "Decisions and rationale" \\
      --text "Match prefixes only."
"""

    SERVE = """\
backlog serve [--port N]

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

  /NAME/               what needs attention (the groups of `list --attention`)
  /NAME/items          active items; filters status and tag, sort (default:
                       closest to closing first, by the least advanced unit)
  /NAME/items/N        the card: units, post-release checks, corrections,
                       links, the brief rendered from markdown; an archived
                       item shows its outcome
  /NAME/archive        archived items, newest first
  /NAME/search?q=...   `search`; add &regex=1 for a regular expression and
                       &archive=1 for the archive

`/` opens the first workspace. The archive file is opened only by the archive
pages, the archive search and the card of an archived item.
Every workspace in the rail shows its attention and active item counts, read
from its BACKLOG file only.

To keep it running, save a launchd job as
~/Library/LaunchAgents/local.backlog.serve.plist (backlog does not install it)
and load it with `launchctl load` on that file:

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

Examples:

  backlog serve
  backlog serve --port 9000
"""
