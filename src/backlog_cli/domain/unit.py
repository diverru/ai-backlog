"""Units of work inside an item: a PR to merge and release, or a piece of research."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

from backlog_cli.domain.action import Action
from backlog_cli.domain.address import Address
from backlog_cli.domain.completion import UnitCompletion
from backlog_cli.domain.part import (
    Assignee,
    Correction,
    Evidence,
    Finding,
    PrRef,
    ReturnRecord,
)
from backlog_cli.domain.record import Record
from backlog_cli.domain.release import Merge, Release
from backlog_cli.domain.vocabulary import (
    ActionKind,
    ActionStatus,
    Outcome,
    UnitKind,
    UnitStatus,
)
from backlog_cli.errors import Hint, Obstacle, Refusal, UsageError
from backlog_cli.moment import Moment


@dataclass
class Unit(Record):
    """Common part. `Unit.from_dict` picks the subclass by `kind`."""

    KIND: ClassVar[UnitKind]
    id: str
    kind: UnitKind
    status: UnitStatus
    assignees: list[Assignee]
    returns: list[ReturnRecord]
    # `completion` is declared by each subclass: the file keeps it last.

    @classmethod
    def from_dict(cls, data: dict) -> "Unit":
        unit_class = {PrUnit.KIND: PrUnit, ResearchUnit.KIND: ResearchUnit}[
            UnitKind(data["kind"])
        ]
        return unit_class.from_dict(data)

    @staticmethod
    def read_assignees(data: dict) -> list[Assignee]:
        return [Assignee.from_dict(entry) for entry in data["assignees"]]

    @staticmethod
    def read_returns(data: dict) -> list[ReturnRecord]:
        return [ReturnRecord.from_dict(entry) for entry in data["returns"]]

    @staticmethod
    def read_completion(data: dict) -> UnitCompletion | None:
        completion = data["completion"]
        return UnitCompletion.from_dict(completion) if completion else None

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    @property
    def label(self) -> str:
        return str(self.KIND)

    @property
    def has_started(self) -> bool:
        """The unit reached wip. A unit that ended is judged by its traces."""
        if self.status == UnitStatus.TODO:
            return False
        if not self.is_terminal or self.status == UnitStatus.DONE:
            return True
        return bool(self.assignees or self.returns)

    @property
    def detail(self) -> str:
        return ""

    @property
    def has_release(self) -> bool:
        return False

    @property
    def pending_actions(self) -> list[Action]:
        return []

    @property
    def release_label(self) -> str | None:
        """`released TAG`, or `released DATE` for a release without a tag."""
        return None

    def get_done_obstacles(self, item_number: int) -> list[Obstacle]:
        """Why this open unit stops `done` of its item."""
        raise NotImplementedError

    def finish(self, item_number: int, build_evidence: Callable[[], Evidence]) -> None:
        """Mark the unit done by hand; the evidence is read after the checks."""
        raise NotImplementedError

    def get_pr_unit(self) -> "PrUnit | None":
        """The unit as a PR unit, or None for research."""
        return None

    def return_to_todo(self, reason: str) -> None:
        """The only way back: an explicit step from wip to todo, with why."""
        self._require_open()
        if self.status == UnitStatus.TODO:
            raise Refusal("already todo")
        if self.status != UnitStatus.WIP:
            raise Refusal(f"{self.status} never goes back; only wip returns to todo")
        self.returns.append(ReturnRecord(Moment.now(), reason))
        self.status = UnitStatus.TODO

    def cancel(self, reason: str, item_number: int) -> None:
        self._require_open()
        self._require_endable(item_number)
        self._end(UnitCompletion.cancelled(reason))

    def supersede(self, reason: str, replacement: str | None, item_number: int) -> None:
        self._require_open()
        self._require_endable(item_number)
        self._end(UnitCompletion.superseded(reason, replacement))

    def get_pending_obstacles(self, item_number: int) -> list[Obstacle]:
        """What must be settled before the unit can end: nothing for research."""
        return []

    def _require_endable(self, item_number: int) -> None:
        """Refuse to end the unit when something must be settled first."""
        obstacles = self.get_pending_obstacles(item_number)
        if obstacles:
            raise Refusal("", obstacles)

    def get_action(self, action_id: str) -> Action:
        raise UsageError(f"unit {self.id} is research and has no actions")

    def add_action(
        self,
        action_id: str,
        kind: ActionKind,
        description: str,
        instructions: str,
    ) -> Action:
        raise Refusal("research units have no PR and therefore no post-release actions")

    def set_pr(self, pr: PrRef) -> None:
        raise Refusal("research units have no PR")

    def add_assignee(self, assignee: Assignee) -> None:
        """Assigning starts the work: a todo unit becomes wip."""
        self._require_open()
        if any(known.agent == assignee.agent for known in self.assignees):
            raise Refusal(f"{assignee.agent} is already assigned")
        self.assignees.append(assignee)
        if self.status == UnitStatus.TODO:
            self.status = UnitStatus.WIP

    def remove_assignees(
        self, agent: str | None, task: str | None, role: str | None
    ) -> list[Assignee]:
        """Remove every assignee with this agent, task or role; say who went."""
        self.assignees, removed = Assignee.split_matching(
            self.assignees, agent, task, role
        )
        return removed

    def _require_open(self) -> None:
        if self.is_terminal:
            raise Refusal(f"unit is {self.status}; a finished unit never changes")

    def _end(self, completion: UnitCompletion) -> None:
        self.status = UnitStatus(completion.outcome)
        self.completion = completion


@dataclass
class ResearchUnit(Unit):
    KIND = UnitKind.RESEARCH
    completion: UnitCompletion | None = None

    @classmethod
    def new(cls, unit_id: str) -> "ResearchUnit":
        return cls(unit_id, cls.KIND, UnitStatus.TODO, [], [])

    @classmethod
    def from_dict(cls, data: dict) -> "ResearchUnit":
        return cls(
            id=data["id"],
            kind=UnitKind(data["kind"]),
            status=UnitStatus(data["status"]),
            assignees=cls.read_assignees(data),
            returns=cls.read_returns(data),
            completion=cls.read_completion(data),
        )

    def get_done_obstacles(self, item_number: int) -> list[Obstacle]:
        address = str(Address(item_number, self.id))
        hint = Hint(
            "Finish the research and record its result",
            f'backlog {address} done --result "..." --source "..."',
        )
        reason = f"research not finished (status {self.status})"
        return [Obstacle(address, self.label, reason, "Unfinished research", hint)]

    def finish(self, item_number: int, build_evidence: Callable[[], Evidence]) -> None:
        self._require_open()
        if self.status != UnitStatus.WIP:
            raise Refusal(
                f"research is finished from wip, not from {self.status}; "
                "assign it first"
            )
        self._end(UnitCompletion.done(build_evidence()))


@dataclass
class PrUnit(Unit):
    KIND = UnitKind.PR
    pr: PrRef | None = None
    merge: Merge | None = None
    release: Release | None = None
    corrections: list[Correction] = field(default_factory=list)
    post_release_required: bool | None = None
    post_release_actions: list[Action] = field(default_factory=list)
    completion: UnitCompletion | None = None

    @classmethod
    def new(cls, unit_id: str, pr: PrRef | None = None) -> "PrUnit":
        return cls(unit_id, cls.KIND, UnitStatus.TODO, [], [], pr=pr)

    @classmethod
    def from_dict(cls, data: dict) -> "PrUnit":
        return cls(
            id=data["id"],
            kind=UnitKind(data["kind"]),
            status=UnitStatus(data["status"]),
            assignees=cls.read_assignees(data),
            returns=cls.read_returns(data),
            completion=cls.read_completion(data),
            pr=PrRef.from_dict(data["pr"]) if data["pr"] else None,
            merge=Merge.from_dict(data["merge"]) if data["merge"] else None,
            release=Release.from_dict(data["release"]) if data["release"] else None,
            corrections=[Correction.from_dict(entry) for entry in data["corrections"]],
            post_release_required=data["post_release_required"],
            post_release_actions=[
                Action.from_dict(entry) for entry in data["post_release_actions"]
            ],
        )

    @property
    def label(self) -> str:
        return f"PR {self.pr}" if self.pr else "pr unit"

    @property
    def has_started(self) -> bool:
        return super().has_started or self.merge is not None

    @property
    def detail(self) -> str:
        return str(self.pr) if self.pr else "no PR recorded"

    @property
    def has_release(self) -> bool:
        return self.release is not None

    @property
    def release_label(self) -> str | None:
        if self.release is None:
            return None
        return f"released {self.release.tag or self.release.released_at[:10]}"

    @property
    def pending_actions(self) -> list[Action]:
        return [action for action in self.post_release_actions if action.is_pending]

    @property
    def live_actions(self) -> list[Action]:
        return [
            action
            for action in self.post_release_actions
            if action.status != ActionStatus.CANCELLED
        ]

    def get_done_obstacles(self, item_number: int) -> list[Obstacle]:
        address = str(Address(item_number, self.id))
        if self.status == UnitStatus.POST_RELEASE:
            return self._get_pending_action_obstacles(address, item_number)
        if self.status == UnitStatus.MERGED:
            return [self._get_missing_release_obstacle(address)]
        return [self._get_unmerged_obstacle(address)]

    def finish(self, item_number: int, build_evidence: Callable[[], Evidence]) -> None:
        message = (
            "a PR unit is never marked done by hand; it finishes by itself "
            "after `released` and its post-release actions"
        )
        if not (self.has_release and self.pending_actions):
            raise Refusal(message)
        address = str(Address(item_number, self.id))
        hint = self.build_failed_check_hint(address, self.pending_actions[0].id)
        raise Refusal(
            "",
            [Obstacle(address, self.label, message, "Not allowed", None, hint)],
        )

    def get_pr_unit(self) -> "PrUnit":
        return self

    def get_action(self, action_id: str) -> Action:
        for action in self.post_release_actions:
            if action.id == action_id:
                return action
        raise UsageError(f"unit {self.id} has no action {action_id!r}")

    def set_pr(self, pr: PrRef) -> None:
        self._require_open()
        if self.merge is not None:
            raise Refusal("the merge is already recorded; the PR can no longer change")
        self.pr = pr

    def record_merge(self, merged_at: str | None, evidence: Evidence) -> None:
        self._require_open()
        if not self.status.is_early:
            raise Refusal(
                f"unit is {self.status}; only a todo or wip unit can be merged. "
                "To replace a wrong merge record, repeat `merged` with "
                '--correction "why"'
            )
        self.merge = Merge(merged_at, evidence)
        self.status = UnitStatus.MERGED

    def correct_merge(
        self,
        pr: PrRef | None,
        merged_at: str | None,
        evidence: Evidence,
        reason: str,
    ) -> Correction:
        """Replace the recorded merge; the old values stay in the history.

        A value the command did not give (`--result`, `--at`) stays as it was.
        """
        if self.merge is None:
            raise Refusal(
                "no merge is recorded yet, so there is nothing to correct; "
                "record it without --correction"
            )
        old = self.merge
        evidence = Evidence(
            evidence.source,
            evidence.result or old.evidence.result,
            evidence.observed_at or old.evidence.observed_at,
            evidence.recorded_at,
        )
        if (
            (pr or self.pr) == self.pr
            and (merged_at or old.merged_at) == old.merged_at
            and evidence.source == old.evidence.source
            and evidence.result == old.evidence.result
        ):
            raise Refusal(
                "this correction changes no value; give the new PR, --at or source"
            )
        correction = Correction(
            Moment.now(),
            "merge",
            reason,
            self.pr,
            old.merged_at,
            old.evidence,
            None,
        )
        self.pr = pr or self.pr
        self.merge = Merge(merged_at or old.merged_at, evidence)
        self.corrections.append(correction)
        return correction

    def correct_release(
        self,
        tag: str | None,
        released_at: str,
        evidence: Evidence,
        reason: str,
    ) -> Correction:
        """Replace the recorded release; the old values stay in the history."""
        if self.release is None:
            raise Refusal(
                "no release is recorded yet, so there is nothing to correct; "
                "record it without --correction"
            )
        old = self.release
        evidence.result = evidence.result or old.evidence.result
        new_tag = old.tag if tag is None else (tag or None)  # "" clears the tag
        if (
            new_tag == old.tag
            and released_at == old.released_at
            and evidence.source == old.evidence.source
        ):
            raise Refusal(
                "this correction changes no value; give the new tag, --at or source"
            )
        correction = Correction(
            Moment.now(),
            "release",
            reason,
            None,
            old.released_at,
            old.evidence,
            old.tag,
        )
        self.release = Release(new_tag, released_at, evidence)
        self.corrections.append(correction)
        return correction

    def get_post_release_problem(self, no_post_release: bool) -> str | None:
        """The post-release decision is explicit: actions exist, or none are needed."""
        if self.live_actions and no_post_release:
            return "--no-post-release given, but the unit has post-release actions"
        if not self.live_actions and not no_post_release:
            return (
                "post-release work is undecided: add actions, or pass --no-post-release"
            )
        return None

    def describe_not_releasable(self) -> str:
        text = f"unit is {self.status}; only a merged unit can be released"
        if self.has_release:
            text += (
                '. To replace a wrong release record, repeat with --correction "why"'
            )
        return text

    def record_release(self, release: Release, no_post_release: bool) -> None:
        self._require_open()
        if self.status != UnitStatus.MERGED:
            raise Refusal(self.describe_not_releasable())
        self.release = release
        self.status = UnitStatus.POST_RELEASE
        if no_post_release:
            self.post_release_required = False
        self.settle_post_release()

    def settle_post_release(self) -> None:
        """Finish the unit by itself as soon as no action is pending."""
        if self.status != UnitStatus.POST_RELEASE or self.pending_actions:
            return
        if any(
            action.status == ActionStatus.CONFIRMED
            for action in self.post_release_actions
        ):
            result = "all post-release actions confirmed"
        elif self.post_release_required is False:
            result = "release recorded; no post-release actions required"
        else:
            result = "all post-release actions were cancelled; none left pending"
        self._end(UnitCompletion.done(Evidence.record_now("backlog", result)))

    def add_action(
        self,
        action_id: str,
        kind: ActionKind,
        description: str,
        instructions: str,
    ) -> Action:
        self._require_open()
        if any(action.id == action_id for action in self.post_release_actions):
            raise Refusal(f"unit {self.id} already has an action {action_id!r}")
        action = Action.new(action_id, kind, description, instructions)
        self.post_release_actions.append(action)
        self.post_release_required = True
        return action

    def confirm_action(self, action_id: str, evidence: Evidence) -> None:
        self._require_post_release("actions are confirmed")
        self.get_action(action_id).confirm(evidence)
        self.settle_post_release()

    def _require_post_release(self, what: str) -> None:
        if self.status == UnitStatus.POST_RELEASE:
            return
        if self.is_terminal:
            raise Refusal(f"unit is {self.status}; {what} only while it is open")
        raise Refusal(
            f"unit is {self.status}; {what} only after the release is recorded"
        )

    def fail_action(
        self,
        action_id: str,
        text: str,
        source: str,
        known_units: list[str],
        at: str | None,
    ) -> Finding:
        """Record a failed check; the action stays pending."""
        self._require_post_release("a check can fail")
        action = self.get_action(action_id)
        if at is not None and self.release is not None:
            Moment.require_not_before(
                at, "--at", self.release.released_at, "the release"
            )
        return action.record_failure(text, source, known_units, at)

    def cancel_action(
        self, action_id: str, reason: str, item_number: int, is_not_needed: bool
    ) -> None:
        """Cancel an action; after a release only when it is not needed."""
        action = self.get_action(action_id)
        if action.is_pending and self.has_release and not is_not_needed:
            address = str(Address(item_number, self.id))
            commands = self.build_failed_check_hint(address, action_id).command
            first, second = commands.splitlines()
            raise Refusal(
                "If the check failed, do not cancel it: record the finding with "
                f"`{first}` and add a fix unit `{second}`. "
                "If the check is really not needed any more, repeat with --not-needed."
            )
        action.cancel(reason)
        if self.release is None and not self.live_actions:
            self.post_release_required = None
        self.settle_post_release()

    def get_pending_obstacles(self, item_number: int) -> list[Obstacle]:
        """A merged unit keeps its pending actions until each one is settled."""
        if self.merge is None or not self.pending_actions:
            return []
        address = str(Address(item_number, self.id))
        reason = (
            "still pending after the recorded release"
            if self.has_release
            else "still pending; the PR is merged"
        )
        return [
            Obstacle(
                f"{address}/{action.id}",
                action.description,
                reason,
                "Pending post-release actions",
                self._build_settle_hint(address, action.id),
                self.build_failed_check_hint(address, action.id)
                if self.has_release
                else None,
            )
            for action in self.pending_actions
        ]

    def _build_settle_hint(self, address: str, action_id: str) -> Hint:
        cancel = f'backlog {address} post_release cancel {action_id} --reason "..."'
        if not self.has_release:
            return Hint("Cancel each pending action with its own reason first", cancel)
        return Hint(
            "Confirm each action, or cancel it explicitly with its own reason, first",
            f"backlog {address} post_release done {action_id} "
            f'--result "..." --source "..."\n{cancel} --not-needed',
        )

    def _end(self, completion: UnitCompletion) -> None:
        if completion.outcome != Outcome.DONE:
            for action in self.pending_actions:
                action.cancel(f"unit {completion.outcome}: {completion.reason}")
        super()._end(completion)

    @staticmethod
    def build_failed_check_hint(address: str, action_id: str) -> Hint:
        """What to do instead of confirming or cancelling a check that failed."""
        item_number = address.split("/")[0]
        return Hint(
            "If a check failed, do not confirm or cancel it: record the finding "
            "and add a fix unit",
            f"backlog {address} post_release fail {action_id} "
            f'--finding "..." --source "..."\n'
            f"backlog {item_number} unit add NAME --kind pr",
        )

    def _get_pending_action_obstacles(
        self, address: str, item_number: int
    ) -> list[Obstacle]:
        sentence = "After performing each check, record its actual result and source"
        return [
            Obstacle(
                f"{address}/{action.id}",
                action.description,
                "not confirmed",
                "Pending actions",
                Hint(
                    sentence,
                    f"backlog {address} post_release done {action.id} "
                    '--result "..." --source "..."',
                ),
                self.build_failed_check_hint(address, action.id),
            )
            for action in self.pending_actions
        ]

    @staticmethod
    def build_release_command(address: str) -> str:
        """The command that records a release."""
        return (
            f'backlog {address} released --at DATE --source "..." '
            f"[--tag TAG] --no-post-release {address}   (or add actions first)"
        )

    def _get_missing_release_obstacle(self, address: str) -> Obstacle:
        hint = Hint(
            "Check that the release is in production, then record it with its source",
            self.build_release_command(address),
        )
        return Obstacle(
            address,
            self.label,
            "no production release recorded",
            "Missing release",
            hint,
        )

    def _get_unmerged_obstacle(self, address: str) -> Obstacle:
        pr_text = str(self.pr) if self.pr else "OWNER/NAME#NUMBER"
        hint = Hint(
            "Check that the PR is merged, then record it with its source",
            f'backlog {address} merged --pr {pr_text} --source "..."',
        )
        if self.status == UnitStatus.TODO:
            hint = Hint(
                "The work has not started: give it to an agent",
                f"backlog {address} assign --agent NAME",
            )
        return Obstacle(
            address,
            self.label,
            f"no merge recorded (status {self.status})",
            "Unmerged work",
            hint,
        )
