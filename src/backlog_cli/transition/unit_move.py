"""Unit transitions.

The step back to todo, the recorded merge (`merged`), the recorded release
(`released`), a research result, cancel and supersede. The tool checks nothing
outside its own files.
"""

import shlex
from collections.abc import Callable

from backlog_cli.domain.address import Address
from backlog_cli.domain.part import PrRef
from backlog_cli.domain.release import Release
from backlog_cli.domain.unit import PrUnit, Unit
from backlog_cli.domain.vocabulary import AddressLevel, MoveStatus, UnitStatus
from backlog_cli.errors import Hint, Obstacle, Refusal, UsageError
from backlog_cli.store.registry import Target
from backlog_cli.moment import Moment
from backlog_cli.transition.base import AssigneeNote, Move, MoveRequest


class UnitMove(Move):
    @classmethod
    def check_request(cls, request: MoveRequest) -> None:
        super().check_request(request)
        if request.tag and any(character.isspace() for character in request.tag):
            raise UsageError("--tag must not contain whitespace")

    def apply(self, target: Target) -> list[str]:
        lines = super().apply(target)
        status = self.request.status
        if self.request.correction:
            return lines + self._describe_correction(target)
        if status in (MoveStatus.CANCELLED, MoveStatus.SUPERSEDED):
            notes = AssigneeNote.build_lines(str(target.address), target.unit.assignees)
            return lines + notes
        unit_prefix = f"{Address(target.item.number, target.unit.id)}: "
        if status == MoveStatus.MERGED:
            merge = target.unit.get_pr_unit().merge
            suffix = f" (merged at {merge.merged_at})" if merge.merged_at else ""
        elif status == MoveStatus.RELEASED:
            release = target.unit.release
            tag = f", tag {release.tag}" if release.tag else ""
            suffix = f" (released at {release.released_at}{tag})"
        else:
            return lines
        return [
            line + suffix if line.startswith(unit_prefix) else line for line in lines
        ]

    @staticmethod
    def _describe_correction(target: Target) -> list[str]:
        pr_unit = target.unit.get_pr_unit()
        correction = pr_unit.corrections[-1]
        if correction.subject == "merge":
            stored, verb = pr_unit.merge.merged_at, "merged"
        else:
            stored, verb = pr_unit.release.released_at, "released"
        now = f"; now {verb} at {stored}" if stored else ""
        return [
            f"{target.address}: {correction.subject} corrected "
            f"(was {correction.describe()}{now}); reason: {correction.reason}"
        ]

    def get_handlers(self) -> dict[MoveStatus, Callable[[Target], None]]:
        return {
            MoveStatus.TODO: self.move_to_todo,
            MoveStatus.MERGED: self.move_to_merged,
            MoveStatus.RELEASED: self.move_to_released,
            MoveStatus.DONE: self.move_to_done,
            MoveStatus.CANCELLED: self.move_to_cancelled,
            MoveStatus.SUPERSEDED: self.move_to_superseded,
        }

    def move_to_todo(self, target: Target) -> None:
        target.unit.return_to_todo(self.request.reason)

    def move_to_cancelled(self, target: Target) -> None:
        self._refuse_merged(target)
        self._refuse_pending(target)
        target.unit.cancel(self.request.reason, target.item.number)

    def _refuse_merged(self, target: Target) -> None:
        obstacle = self.get_merged_obstacle(target.item.number, target.unit)
        self.refuse_if_any([obstacle] if obstacle else [])

    @staticmethod
    def get_merged_obstacle(number: int, unit: Unit) -> Obstacle | None:
        """Merged code is in the trunk: only another PR that reverts it undoes it."""
        if unit.status != UnitStatus.MERGED:
            return None
        address = f"{number}/{unit.id}"
        return Obstacle(
            address,
            unit.label,
            "the code is already in the trunk; to undo it, add a revert "
            "unit and release both",
            "Merged",
            Hint(
                "Undo it with a revert unit; release both when they go out "
                "(or each with its own release)",
                f"backlog {number} unit add NAME --kind pr\n"
                f"backlog {address},{number}/NAME released --at DATE "
                '--source "..."',
            ),
        )

    def _refuse_pending(self, target: Target) -> None:
        """Pending actions stop the unit; a failed check gets the fix hint."""
        self.refuse_if_any(
            target.item.refine_obstacles(
                target.unit.get_pending_obstacles(target.item.number)
            )
        )

    def move_to_superseded(self, target: Target) -> None:
        self._refuse_merged(target)
        replacement = self._parse_replacement(target)
        if replacement is not None:
            replacing = target.item.get_unit(replacement)
            if replacement == target.unit.id:
                raise UsageError("a unit cannot supersede itself")
            if replacing.is_terminal:
                raise UsageError(
                    f"--by {replacement}: that unit is {replacing.status}; "
                    "a unit can only be replaced by an open unit"
                )
        self._refuse_pending(target)
        target.unit.supersede(self.request.reason, replacement, target.item.number)

    def _parse_replacement(self, target: Target) -> str | None:
        """`--by` names a unit of the same item: `fix` or `1/fix`."""
        text = self.request.by
        if text is None or "/" not in text:
            return text
        address = Address.parse(text)
        if address.level != AddressLevel.UNIT:
            raise UsageError(
                f"--by must be a unit of this item: fix or {target.item.number}/fix"
            )
        if address.item not in (target.item.number, target.item.id):
            raise UsageError(
                f"--by {text!r} is a unit of another item; a unit can only be "
                f"replaced by a unit of item {target.item.number}"
            )
        return address.unit

    def move_to_done(self, target: Target) -> None:
        target.unit.finish(target.item.number, self.build_done_evidence)

    def move_to_merged(self, target: Target) -> None:
        """Record the merge the agent reports, with its source."""
        unit = self._require_pr_unit(target, MoveStatus.MERGED)
        given = PrRef.from_text(self.request.pr, "--pr") if self.request.pr else None
        if self.request.correction:
            self._correct_merge(target, unit, given)
            return
        address = str(target.address)
        if not unit.status.is_early:
            raise Refusal(
                f"unit is {unit.status}; only a todo or wip unit can be merged. "
                "To replace a wrong merge record, repeat with "
                f'--correction "why": backlog {address} merged ... --correction "why"'
            )
        if given and unit.pr and given != unit.pr:
            raise Refusal(
                f"{address} has PR {unit.pr} recorded, but --pr gives {given}. "
                f"Link the right one first: backlog {address} link pr {given}"
            )
        pr = given or unit.pr
        if pr is None:
            raise Refusal("", [self._build_missing_pr_obstacle(address, target.name)])
        self._require_pr_free(pr, target)
        self.require_observed_not_future("a merge")
        unit.set_pr(pr)
        unit.record_merge(
            self.request.get_observed_at(), self.request.build_evidence("merged")
        )

    def _require_pr_free(self, pr: PrRef, target: Target) -> None:
        """One PR belongs to one unit of the active items."""
        other = self.context.registry.find_other_unit_with_pr(
            pr, target.item, target.unit
        )
        if other is None:
            return
        address = str(target.address)
        hint = Hint(
            "Give the PR of this unit", f"backlog {address} link pr OWNER/NAME#N"
        )
        raise Refusal(
            "",
            [
                Obstacle(
                    address,
                    target.name,
                    f"PR {pr} is already linked to unit {other}",
                    "PR of another unit",
                    hint,
                )
            ],
        )

    def _correct_merge(self, target: Target, unit: PrUnit, given: PrRef | None) -> None:
        if given is not None and unit.release is not None and given != unit.pr:
            raise Refusal(
                f"{target.address} is already released and the release names PR "
                f"{unit.pr}; the PR cannot change now. If the wrong PR went out, "
                "record the real situation with a new unit: "
                f"backlog {target.item.number} unit add NAME --kind pr"
            )
        if given is not None:
            self._require_pr_free(given, target)
        observed = self.request.get_observed_at()
        self.require_observed_not_future("a merge")
        if observed and unit.release is not None:
            if Moment.is_before(unit.release.released_at, observed):
                raise UsageError(
                    f"--at {observed} is later than the release "
                    f"({unit.release.released_at}); a merge cannot follow its release"
                )
        unit.correct_merge(
            given,
            observed,
            self.request.build_evidence(),
            self.request.correction,
        )

    def move_to_released(self, target: Target) -> None:
        """Record the release the agent reports, with its source."""
        unit = self._require_pr_unit(target, MoveStatus.RELEASED)
        address = str(target.address)
        if self.request.correction:
            self._correct_release(target, unit)
            return
        if unit.pr is None:
            raise Refusal(
                f"no PR recorded for {address}; record it first: "
                f"backlog {address} link pr OWNER/NAME#N"
            )
        if unit.status != UnitStatus.MERGED:
            raise Refusal(unit.describe_not_releasable())
        no_post_release = self.request.declares_no_post_release(address)
        self.refuse_if_any(
            self._get_post_release_obstacles(unit, address, no_post_release)
        )
        released_at = self.request.get_observed_at()
        self.require_observed_not_future("a release")
        if unit.merge is not None:
            self.require_observed_not_before(unit.merge.merged_at, "the merge")
        release = Release(
            self.request.tag or None,
            released_at,
            self.request.build_evidence("released"),
        )
        unit.record_release(release, no_post_release)

    def _correct_release(self, target: Target, unit: PrUnit) -> None:
        if unit.release is None:
            raise Refusal(
                f"{target.address} has no release to correct; "
                "record it without --correction"
            )
        released_at = self.request.get_observed_at()
        self.require_observed_not_future("a release")
        if unit.merge is not None:
            self.require_observed_not_before(unit.merge.merged_at, "the merge")
        unit.correct_release(
            self.request.tag,
            released_at,
            self.request.build_evidence("released"),
            self.request.correction,
        )

    def _get_post_release_obstacles(
        self, unit: PrUnit, address: str, no_post_release: bool
    ) -> list[Obstacle]:
        problem = unit.get_post_release_problem(no_post_release)
        if problem is None:
            return []
        if no_post_release:
            cancels = "\n".join(
                f'backlog {address} post_release cancel {action.id} --reason "..."'
                for action in unit.live_actions
            )
            hint = Hint(
                "The unit has actions: cancel them first, or leave this unit out of "
                "--no-post-release so that its actions wait for the check",
                cancels,
            )
            return [
                Obstacle(address, unit.label, problem, "Post-release decision", hint)
            ]
        hint = Hint(
            "Add actions with `backlog N/UNIT post_release add NAME --kind ... "
            "--title ... --instructions ...`, or declare that none are needed",
            self._build_group_release_command(),
        )
        return [Obstacle(address, unit.label, problem, "Post-release decision", hint)]

    def _build_group_release_command(self) -> str:
        """The release command as given, with `--no-post-release` for every unit
        of the group that has no actions: the group stays one release.
        """
        request = self.request
        declared = list(request.no_post_release)
        for address in request.batch:
            pr_unit = self.context.registry.resolve_target(
                Address.parse(address)
            ).unit.get_pr_unit()
            if pr_unit and not pr_unit.live_actions and address not in declared:
                declared.append(address)
        tag = f" --tag {shlex.quote(request.tag)}" if request.tag else ""
        return (
            f"backlog {','.join(request.batch)} released --at {request.at} "
            f"--source {shlex.quote(request.source)}{tag} "
            f"--no-post-release {' '.join(declared)}"
        )

    @staticmethod
    def _build_missing_pr_obstacle(address: str, name: str) -> Obstacle:
        hint = Hint(
            "Say which PR it is",
            f"backlog {address} link pr OWNER/NAME#N\n"
            f'backlog {address} merged --pr OWNER/NAME#N --source "..."',
        )
        return Obstacle(address, name, "no PR is set for this unit", "Missing PR", hint)

    @staticmethod
    def _require_pr_unit(target: Target, status: MoveStatus) -> PrUnit:
        unit = target.unit.get_pr_unit()
        if unit is None:
            address = Address(target.item.number, target.unit.id)
            raise Refusal(
                f"{address} is a research unit; it has no PR, so it is never {status}"
            )
        return unit
