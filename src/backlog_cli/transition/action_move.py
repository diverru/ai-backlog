"""Post-release action transitions. Users say `done`; the file stores `confirmed`."""

from collections.abc import Callable

from backlog_cli.domain.part import Evidence
from backlog_cli.errors import Obstacle
from backlog_cli.domain.vocabulary import AddressLevel, MoveStatus, UnitStatus
from backlog_cli.store.registry import Target
from backlog_cli.transition.base import Move, StatusSnapshot


class ActionMove(Move):
    def get_handlers(self) -> dict[MoveStatus, Callable[[Target], None]]:
        return {
            MoveStatus.DONE: self.move_to_done,
            MoveStatus.CANCELLED: self.move_to_cancelled,
        }

    def describe_change(self, old: StatusSnapshot, new: StatusSnapshot) -> str:
        line = super().describe_change(old, new)
        if new.level == AddressLevel.UNIT and new.status == UnitStatus.DONE:
            return f"{line} (all post-release actions settled)"
        return line

    def move_to_done(self, target: Target) -> None:
        self._require_fix_released(target)
        target.unit.confirm_action(target.action.id, self.build_action_evidence(target))

    def _require_fix_released(self, target: Target) -> None:
        """A failed check is settled only after a unit added later has been released."""
        action, item = target.action, target.item
        if not action.is_failed:
            return
        last = action.findings[-1]
        if item.has_fix_after(last):
            return
        address = str(target.address)
        hint = item.build_fix_hint(last)
        self.refuse_if_any(
            [
                Obstacle(
                    address,
                    action.description,
                    f'the check failed ("{last.text}", {last.at}); release a unit '
                    "added after the finding to unlock it",
                    "Failed check",
                    hint,
                )
            ]
        )

    def build_action_evidence(self, target: Target) -> Evidence:
        """A result cannot predate the release it follows."""
        release = target.unit.release
        if release is not None:
            self.require_observed_not_before(release.released_at, "the release")
        if target.action.findings:
            self.require_observed_not_before(
                target.action.findings[-1].at, "the last finding of the action"
            )
        return self.build_done_evidence()

    def move_to_cancelled(self, target: Target) -> None:
        self._require_fix_released(target)
        target.unit.cancel_action(
            target.action.id,
            self.request.reason,
            target.item.number,
            self.request.not_needed,
        )
