"""Guide text of the commands that change items and units."""


class ChangeGuide:
    ADD = """\
backlog add SLUG --title "..." [--priority high|normal|low] [--tags a,b]
            [--due DATE] [--reminder DATE] [--depends-on 41,42]

Add a new item and print its number. SLUG is lowercase letters, digits,
underscores and dashes, starts with a letter, at most 60 characters
(fast_order_rt_search). A slug that an active or an archived item has is
refused (exit 1) with that item's number. The id is the number plus the slug:
0043_fast_order_rt_search. Creates an empty details file (eight standard
sections). Units and actions are added under the item: `backlog N unit add ...`.

  --title        required, one line.
  --priority     default normal.
  --tags         lowercase words with dashes; commas, spaces or both separate
                 them: back,search or "back search".
  --due          deadline. --reminder: the day `list --attention` shows it.
  --depends-on   existing items, separated by commas, spaces or both; no cycle,
                 and not an item archived as cancelled or superseded.

Dates are YYYY-MM-DD or an ISO 8601 datetime with an offset (2026-10-23T16:00:00
+03:00, or Z for UTC). Adding an item does not start an agent. Takes --dry-run.

Examples:
  backlog add fast_order_rt_search --title "Realtime order search" \\
      --tags back,search --priority high
  backlog add check_billing --title "Why is billing slow" --depends-on 41
"""

    ITEM = """\
Actions of an item: `backlog N ACTION`; `backlog N` alone is `show`. An archived
item is read-only: only `show`, `dependency` and `brief show` work. All changes
take --dry-run.

  rename "TITLE"               also updates the heading of the details
  priority high|normal|low
  tag add X [X ...]            commas, spaces or both separate the tags
  tag remove X [X ...]
                               example tag `side-fix`: small work that can be
                               included in another suitable PR; the tag does not
                               authorize expanding that task's scope
  due add DATE | due delete    the deadline; the output shows `due: OLD -> NEW`
  reminder add DATE | reminder delete
  block add "TEXT" [--waiting-on WHO]
                               an external condition; prints its id b1, b2, ...
  block remove bK --reason "..."
                               closes the blocker (1 means b1) and keeps it with
                               the reason (`show` prints resolved_blockers)
  unit, unit add NAME [--kind pr|research]      see: backlog guide unit
  dependency ...                                see: backlog guide dependency
  done, cancel, supersede                       see: backlog guide finish
  brief ...                                     see: backlog guide brief

Not editable: id, status (it follows the units), completion, created_at,
updated_at. Priority and deadline change only on the user's instruction.

Examples:
  backlog 43 priority high
  backlog 43 tag add perf search
  backlog 7 tag add side-fix
  backlog 43 due add 2026-11-15
  backlog 43 block add "Needs an administrator" --waiting-on admin
  backlog 43 block remove b1 --reason "Administrator did it"
"""

    DEPENDENCY = """\
backlog N dependency [--dependents]
backlog N dependency add X [X ...]
backlog N dependency remove X [X ...]

X is an item number (or the exact id), active or archived, or a PR as
OWNER/NAME#N (always with the owner); several X are separated by spaces,
commas or both. An item dependency must exist, not be archived as cancelled or
superseded, and not close a cycle; `done` of the item stays refused until every
item dependency is archived as done. For a dependency archived as superseded the
refusal names the successor item and the commands that move the dependency.
A PR is informational (a prerequisite PR): it never blocks start or closure.

Without an action the command shows the dependencies, the open blockers and the
prerequisite PRs; `--dependents` shows the items that depend on this one.

Examples:
  backlog 43 dependency add 41 acme/api#123
  backlog 43 dependency remove 41
  backlog 41 dependency --dependents
"""

    ASSIGN = """\
Who works on a unit, and how work starts. Assignees exist only on units; an item
has none. Work statuses are todo and wip.

  backlog N/UNIT assign --agent A [--task T] [--role R]
  backlog N/UNIT unassign (--agent A | --task T | --role R)
  backlog N/UNIT return_to_todo --reason "..."

`assign` adds an assignee and moves a todo unit to wip; T is PROJECT:SEQ
(api:456). A unit that already has assignees keeps them: the output says so and
names the `unassign` command. `unassign` removes the assignees that match and
changes no status. `return_to_todo` is the only way back from wip to todo and
stores the reason; a merged unit never goes back. When the item still waits for
a dependency, `assign` prints `note: item N still waits for M (status)`; the
work is not blocked.

Assign everyone started for this unit, a reviewer started only for it too
(`--role review`). Do not assign permanent reviewers that serve every task.

Examples:
  backlog 43/engine assign --agent "Backend agent" --task api:456 --role back
  backlog 43/engine unassign --agent "Backend agent"
  backlog 43/engine return_to_todo --reason "The agent stopped, task is free"
"""

    FINISH = """\
Ending an item. Each of these archives the item in the same command; a done item
is never reopened (the continuation is a new item with --depends-on).

  backlog N done --result "..." --source "..." [--at DATE]
    Closes the item by hand. --source says how you know it, really: if you did
    not see it yourself, ask the user and write the answer as the source. Needs
    every unit finished, one unit done, no open blocker, no pending action and
    every dependency archived as done; an item without units is refused (add a
    unit, or cancel it). Every obstacle is listed with its next command. --at is
    not earlier than the release of a unit of the item.
  backlog N cancel --reason "..."
  backlog N supersede --by M --reason "..."
    Also work on an item without units. M continues the work: active or
    archived as done, not the item itself, not depending on N.

When the last open unit ends, the output says `N: all units finished; close it:
backlog N done ...`; `merged` and `released` print the stored time.
`list` and the card say `ready to close: backlog N done ...` (with the items it
unblocks) when `done` would pass now, else `blocked:` with the first obstacle.
The card of an item that has not started says what it waits for (a dependency,
or an agent to assign). `cancel` and `supersede` are refused while a merged unit
exists or a released unit has a pending action; each is listed with the command
that settles it. The output lists the units closed with the item, every assignee
left (`tell them to stop`) and the active items that depend on it. `stuck` marks
an item whose units were all cancelled or superseded; the way out is `cancel` or
a new unit.

Examples:
  backlog 43 done --result "All criteria are met" --source "how you know it"
  backlog 43 cancel --reason "Not needed any more"
  backlog 43 supersede --by 50 --reason "Merged into a bigger rewrite"
"""

    UNIT = """\
Units of work: a PR to merge and release (kind pr) or a piece of research.
`backlog N unit` lists the units, one line each; `backlog N/UNIT` shows one.

  backlog N unit add NAME [--kind pr|research]      default pr
  backlog N/UNIT link pr OWNER/NAME#N               before the merge is recorded
  backlog N/UNIT assign|unassign|return_to_todo     see: backlog guide assign
  backlog N/UNIT merged --source S [--at T] [--result R] [--pr OWNER/NAME#N]
      [--correction "why"]
  backlog N/UNIT released --at T --source S [--tag TAG] [--no-post-release]
      [--correction "why"]
  backlog N/UNIT done --result R --source S [--at T]      research units only
  backlog N/UNIT cancel --reason R
  backlog N/UNIT supersede --by OTHER_UNIT --reason R
  backlog N/UNIT post_release ...                   see: backlog guide post_release

STATUSES  todo, wip, merged, post_release, done, cancelled, superseded.
  A pr unit goes todo -> wip (assign) -> merged -> post_release -> done; it is
  never moved to done by hand. A research unit goes todo -> wip -> done. The
  item is todo until a unit has started, else wip.

merged: the PR is merged; --source says how, --at when (default now), --result
  defaults to "merged". The PR comes from --pr or `link pr`; a different --pr is
  refused. One PR may close units of several items: `merged` is written to
  every unit of that PR (a unit whose PR is already merged copies that merge).
released: only from merged. --at is when it reached production (required),
  --tag is optional and has no whitespace. Several units of one release are one
  address: `backlog 43/a,44/b released --at T --source S --no-post-release 44/b`.
  `released` must list every merged unit of the same PR; the refusal gives the
  full group.
  The same release is written to each unit. All or nothing: one refusal writes
  nothing, and the hint repeats the whole group with your --at, --source, --tag.
  The post-release decision is per unit: units with actions become post_release;
  units with no actions need --no-post-release and are done at once; undecided
  units, or --no-post-release over actions, are refused.
cancel, supersede: from todo, wip or after a release; --by is an open unit of
  the same item. A unit in merged is refused (see UNDOING MERGED WORK); a
  released unit with a pending action is refused with the commands that settle
  it. A unit that was never merged cancels its pending actions with it.

UNDOING MERGED WORK  Merged code is in the trunk. Only a PR that reverts it
  undoes it: add a revert unit (`backlog N unit add NAME --kind pr`), merge it,
  release both (`backlog N/U,N/NAME released ...`), then close the item.

CORRECTION  To replace a wrong `merged` or `released` record repeat it with
  --correction "why". What you give replaces the old value; what you leave out
  (--result, --at, --tag) stays. The old values and the reason are kept in the
  unit (`show`). A correction changes only the unit it addresses; one that
  changes nothing is refused. A merge cannot be moved after the release, and
  the PR of a released unit cannot change. `--tag ""` removes a tag.

TIMES  --at is YYYY-MM-DD or an ISO 8601 datetime with an offset. A date alone
  means the end of that day (23:59:59 UTC), and now for today. It says when the
  fact happened, never when you ran the command. Refused (exit 2, with both
  dates): later than now; a release earlier than the merge; a post-release
  result earlier than the release or the last finding; a failed check earlier
  than the release; `done` of an item earlier than a release of its units.

REFUSALS  A refused action exits with 1, changes nothing, and lists every
  obstacle with its address, reason and next command. All forms take --dry-run.

Examples:
  backlog 43 unit add engine
  backlog 43/engine merged --pr acme/api#123 --source "gh pr view 123"
  backlog 43/engine released --at 2026-10-24 --source "release_status" \\
      --tag v1.2.0 --no-post-release
  backlog 43/engine supersede --by engine_v2 --reason "Redesigned" --dry-run
"""

    POST_RELEASE = """\
Something to do or check in production after a release, kept on a pr unit.

  backlog N/UNIT post_release                      list the actions
  backlog N/UNIT post_release add NAME --kind command|verification|admin_change \\
      --title "..." --instructions "..."
  backlog N/UNIT post_release edit NAME [--title "..."] [--instructions "..."]
  backlog N/UNIT post_release fail NAME --finding "..." --source "..." [--at DATE]
  backlog N/UNIT post_release done NAME [NAME ...] --result "..." --source "..."
      [--at DATE]
  backlog N/UNIT post_release cancel NAME --reason "..." [--not-needed]

add: NAME follows the rule of a slug. Allowed while the unit is open.
edit: pending actions only, and not one that has a finding.
done: you type done; the file stores confirmed. Only after the release, with a
  result and a source; a confirmation is final. Several names share one result
  and source. --at is not earlier than the release or the last finding. The card
  shows the date, result and source of a confirmed check under it.
cancel: only a pending action; never a successful check. After the release
  --not-needed is required (say it only when the check is not needed any more).
fail: the check was done and found a problem. Only after the release. The action
  stays pending and each call stores a finding (time, text, source); --at is when
  the check failed (not before the release). The same text as the last finding
  is refused. `list` shows `check K: text — FAILED: finding`, `show` all the
  findings, `list --attention` the group "Failed post-release checks".

A FAILED POST-RELEASE CHECK  Never record it as done or cancel it. Record it with
  `fail`, then add the fix as a new unit of the same item (`backlog N unit add
  NAME --kind pr`; a fix in another item does not count), merge and release it.
  Only a release of a unit that was added after the finding unlocks `done` and
  `cancel --not-needed` of that action; release dates and corrections of a
  release never do. The item stays wip while the fix is open.

Examples:
  backlog 43/engine post_release add check_latency --kind verification \\
      --title "Check search latency" \\
      --instructions "Compare p99 before and after the release"
  backlog 43/engine post_release done check_latency check_order \\
      --result "Both checks passed on the replica" --source "how you know it"
  backlog 43/engine post_release fail check_latency --at 2026-10-24 \\
      --finding "p99 is 4.1 s, before 1.8 s" --source "how you know it"
"""
