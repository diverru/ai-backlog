# backlog CLI

`backlog` is the coordinator's backlog tool. It keeps items, the units of work
inside them (a PR to merge and release, or a piece of research), the post-release
actions of a PR, and one details file per item, for one workspace. The data lives in `~/.bklg/<workspace>/` (or `$BKLG_HOME`) and is
written only by this tool. The user manual is `backlog guide all`; read it before
changing behaviour and keep it true: every behaviour change updates the guide.

## Layout

- `backlog` — launcher: puts `src/` on `sys.path`, checks PyYAML,
  typed-argument-parser and markdown-it-py, calls `Cli.main`.
- `src/backlog_cli/` — the package, absolute imports only.
  - `domain/` — records (`Item`, `Unit`, `PrUnit`, `ResearchUnit`, `Action`,
    `Release`, `Merge`, `Evidence`), `Address`, `DetailsFile`, the enums of every
    closed value set (`vocabulary.py`), and `situation.py` (`ItemSituation`:
    stuck, ready to close, blocked, overdue; `list`, `show` and `list
    --attention` read it, no command computes these itself).
  - `store/` — `Workspace` (paths, lock, atomic writes), `Registry` (active
    items; the archive is read lazily), `BindingConfig`, `YamlFile`.
  - `transition/` — the rules of the status changes, one class per level.
  - `command/` — one class per command or action with its Tap parser.
    `cli.py` runs the global commands by name; `router.py` runs everything else
    as `backlog ADDRESS ACTION`. An action derives from `ActionSpec` (levels,
    words, guide section, help card).
  - `guide/` — the text of `backlog guide`.
  - `serve/` — `backlog serve`: the read-only web viewer (`Site` routes a GET to a
    page; one module per page; `viewer.css` is inlined into every page).
- `tests/` — pytest, by rule. Run from this directory: `python3 -m pytest -q`.

Dependencies: Python 3.14, PyYAML, typed-argument-parser, markdown-it-py (the viewer
renders the briefs).

## Behaviour rules

- An empty brief is a blank `Problem and expected result` section of an active
  item (`Workspace.has_empty_brief`; an unreadable file is not empty). A command
  that writes prints a hint for each touched item; it never blocks.
- The files are written only by this tool; the loader does not defend against
  hand edits. User input is validated with clear errors and no traceback (exit
  2); refused transitions list every obstacle with the next command (exit 1).
- Writes are locked (`flock`) and atomic. The archive is written before the
  registry; the next mutating command repairs an item found in both files (the
  archive copy wins, the `archived_item_ids` and `archived_outcomes` indexes are
  rebuilt by the same method as a normal archive).
- Never run tests or experiments against real data under `~/.bklg/<workspace>/`;
  tests use a temporary `BKLG_HOME`.
- The tool runs no external program and calls no service: no `subprocess`, `gh`
  or release check. The one exception is `serve/opener.py`: the viewer runs
  macOS `open` for a file or folder the reader clicked (a test greps `src`).
  The agent checks a fact and records it with `--source` ("how you know it"; no
  example names an invented source).
- BACKLOG.yaml keeps `next_id`, `archived_outcomes` (outcomes of archived items
  that an active item depends on) and `archived_item_ids` (so `add` refuses an
  archived slug without opening the archive). `.archiving` marks an item that
  may be in both files.
- `settle()` (derived status, `updated_at`) runs only in `run_change`. Use
  `Item.current_status` to print a status before it is stored.
- The stored format is schema 1; the version is raised when a stored key is added
  or changes meaning, and a higher version is read-only. Nothing is released yet,
  so there is no migration code: when the format changes, rebuild
  `tests/fixtures/workspace_schema1` with the real commands.
- Item status follows its units only: todo until a unit has started
  (`Unit.has_started`), else wip; no units means todo. Assignees exist only on
  units. `done` of an item without units is refused; `cancel` and `supersede`
  work. The coordinator closes every item by hand; `ready to close` has one rule
  (`ItemSituation.is_ready_to_close`). The card says what an unstarted item waits
  for and never offers a merge for todo work.
- A unit has at most one `Release`. `released` for several units writes the same
  release to each in one atomic command; a correction changes only its own unit.
  A repeated `merged` or `released` needs `--correction "why"`: the given fields
  replace the old ones, the others stay, and the old evidence goes to
  `PrUnit.corrections`. A merge in `merged` cannot be cancelled or superseded
  (a revert unit undoes it). One PR may belong to units of several items:
  `merged` is written to every unmerged unit of that PR (a unit whose PR is already
  merged copies that merge), and `released` must list every merged unit of it.
  PR owner and name are stored lower case.
- A failed check (`post_release fail`, with its own `--at`) stores a `Finding`
  and leaves the action pending. It is settled only when a unit that the item did
  not have at the finding (`Finding.known_units`) has been released
  (`Item.has_fix_after`); release dates and corrections never unlock it.
- Chronology checks (refused with exit 2): not in the future; release not before
  the merge; `post_release done` not before the release or the last finding;
  `post_release fail` not before the release; item `done --at` not before the
  releases of its units. `--at` with a date alone is the end of that day, and now
  for today, in the check and in the stored value.
- One character filter (`TextCheck`): no control characters (a multi-line text
  keeps `\n` and `\t`) and no bidi marks; a one-line field has no line break and
  at most 300 characters. A non-UTF-8 argument is a usage error. The central
  file names are looked for in brief text without regard to case.
- The viewer only reads: GET and HEAD, no lock, no repair, no cache, every data
  string escaped; the archive file is opened only by the archive pages, the
  archive search and the card of an archived item.
- `search` is plain text by default and `--regex` is one expression under a 5 s
  SIGALRM limit (`SearchTimeLimit`); neither matches service fields.
- Lists (tags, dependencies, `--no-post-release`) take commas, spaces or both
  (`ListText`). A hint that needs a free unit name says `NAME`.
- Grammar: the address first, then one action. A request fact (`--result`,
  `--source`, `--at`, `--reason`, `--by`, `--pr`, `--tag`, `--no-post-release`,
  `--not-needed`) is a `MoveFlag`. A field of a Tap parser must not be named like
  an `argparse.ArgumentParser` attribute (a test checks it).
- Help has levels: the root card (at most 30 lines), the action lists of `N` and
  `N/UNIT` and `post_release`, and each action's `--help` (at most 15 lines; the
  last line starts with "Example"). Errors are short, give the next command and
  never print help.

## Who changes the code

Only on the user's explicit request. A coordinator or any other agent that uses
backlog never edits its code, data files or config; it reports the problem to
the user: what it ran, what happened, what it expected.

## Running viewer

The viewer may run all the time under the launchd job `local.backlog.serve`
(set up as `backlog guide read` shows). It reads data on every request but
loads the code once, so after a code change restart it:

    launchctl kickstart -k gui/$(id -u)/local.backlog.serve

Never kill it by pid and never start another server on its port; test copies use
another port.

## Code standards

Names
- Full descriptive names, no abbreviations (`args` only for a command's Tap
  object). Class and module names are singular. Methods start with a verb;
  getters are `get_*`, predicates `is_`/`has_`/`can_`/`should_`; nouns are
  properties. A static method that uses its class is a class method.

Structure
- Methods at most 50 lines, one job, early returns. Annotate everything
  (`X | None`, `list[...]`). Values returned together are a dataclass, not a
  tuple. No walrus, no `global`, no mutable module state.
- Domain objects are dataclasses with `from_dict` and `to_dict`; YAML mappings
  exist only at the store boundary. Rules live on the object they are about.
- No module-level constants: regexes, limits and texts are class attributes (not
  on a Tap parser: Tap turns them into arguments). Every closed value set is a
  `StrEnum` whose values equal the stored strings; no `.value`; a branch on an
  enum never lets its last branch stand for every other member.
- Absolute imports at the top of the file; a local import only to break a cycle.

Comments and style
- Prefer a name to a comment; comment only why, at most 3 lines. Code, messages
  and help are English.
- 88 columns, f-strings, files under about 400 lines. `ruff format --isolated`
  and `ruff check --isolated --no-fix` on `src tests` stay clean.
- Minimal diffs: change what the task needs and nothing else.
- Specific exceptions (`UsageError`, `Refusal`, `LockError`), caught at the layer
  that can handle them; messages name the reason and the next command.
