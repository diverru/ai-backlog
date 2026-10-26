"""The base of every action that moves a target to a status: done, merged, ..."""

from typing import ClassVar

from tap import Tap

from backlog_cli.command.action import ActionSpec
from backlog_cli.command.base import Change, ListText, MutatingCommand
from backlog_cli.domain.address import Address
from backlog_cli.domain.vocabulary import AddressLevel, MoveFlag, MoveStatus
from backlog_cli.errors import Obstacle, Refusal, UsageError
from backlog_cli.store.registry import Registry, Target
from backlog_cli.store.workspace import Workspace
from backlog_cli.transition.action_move import ActionMove
from backlog_cli.transition.base import Move, MoveContext, MoveRequest
from backlog_cli.transition.item_move import ItemMove
from backlog_cli.transition.unit_move import UnitMove


class TransitionCommand(ActionSpec, MutatingCommand):
    """Moves its targets to STATUS. The flags of the action are its facts."""

    STATUS: ClassVar[MoveStatus]
    MOVE_CLASSES: ClassVar[dict[AddressLevel, type[Move]]] = {
        AddressLevel.ITEM: ItemMove,
        AddressLevel.UNIT: UnitMove,
        AddressLevel.ACTION: ActionMove,
    }

    def make_change(
        self, args: Tap, workspace: Workspace, registry: Registry
    ) -> Change:
        targets = self.resolve_targets(args, registry)
        request = self.build_request(args, registry, targets)
        move_class = self.MOVE_CLASSES[targets[0].address.level]
        move_class.check_request(request)
        self.refuse_archived(targets, args)
        move = move_class(request, MoveContext(registry))
        return Change(self.apply_all(move, targets, args))

    def resolve_targets(self, args: Tap, registry: Registry) -> list[Target]:
        texts = args.address.split(",") if self.MULTI_TARGET else [args.address]
        targets = [registry.resolve_target(Address.parse(text)) for text in texts]
        if self.MULTI_TARGET and any(target.unit is None for target in targets):
            raise UsageError("released takes unit addresses N/U")
        addresses = [str(target.address) for target in targets]
        if len(set(addresses)) != len(addresses):
            raise UsageError("the same target is listed twice; list each one once")
        return targets

    def build_request(
        self, args: Tap, registry: Registry, targets: list[Target]
    ) -> MoveRequest:
        """The facts the user gave; a flag the action does not have stays unset."""
        values = {str(flag): getattr(args, str(flag), None) for flag in MoveFlag}
        given = {name: value for name, value in values.items() if value is not None}
        request = MoveRequest(status=self.STATUS, **given)
        request.batch = [str(target.address) for target in targets]
        request.no_post_release = self.resolve_no_post_release(
            request.no_post_release, registry, targets
        )
        return request

    @staticmethod
    def resolve_no_post_release(
        texts: list[str], registry: Registry, targets: list[Target]
    ) -> list[str]:
        """Canonical addresses of the units that declare no post-release work.

        A bare flag names the only target; with several targets each is named.
        """
        known = [str(target.address) for target in targets]
        named = []
        # A bare flag is "" and stays; the rest may hold several units.
        words = [word for text in texts for word in ListText.split([text]) or [""]]
        for text in words:
            if text == "":
                if len(targets) > 1:
                    raise UsageError(
                        "--no-post-release needs the unit when several are released: "
                        "--no-post-release N/UNIT"
                    )
                named.append(known[0])
                continue
            address = str(registry.resolve_target(Address.parse(text)).address)
            if address not in known:
                raise UsageError(
                    f"--no-post-release {text} is not one of the units being released"
                )
            if address in named:
                raise Refusal(f"{address} is named twice in --no-post-release")
            named.append(address)
        return named

    def refuse_archived(self, targets: list[Target], args: Tap) -> None:
        archived = [target for target in targets if target.is_archived]
        if not archived:
            return
        obstacles = [
            Obstacle(
                str(target.address),
                target.name,
                "the item is archived and read-only; "
                + target.item.describe_next_item_step(),
                "Archived",
            )
            for target in archived
        ]
        raise Refusal(self.build_head(args), obstacles)

    def apply_all(self, move: Move, targets: list[Target], args: Tap) -> list[str]:
        """All or nothing: every target is checked, and one refusal stops them all."""
        lines: list[str] = []
        obstacles: list[Obstacle] = []
        for target in targets:
            try:
                lines += move.apply(target)
            except Refusal as refusal:
                obstacles += self.get_obstacles(refusal, target)
        if obstacles:
            raise Refusal(self.build_head(args), obstacles)
        return lines

    @staticmethod
    def get_obstacles(refusal: Refusal, target: Target) -> list[Obstacle]:
        if refusal.obstacles:
            return refusal.obstacles
        return [Obstacle(str(target.address), target.name, refusal.head, "Not allowed")]

    def build_head(self, args: Tap) -> str:
        return f"Cannot apply '{self.get_key()}' to {args.address}."
