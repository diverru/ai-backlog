"""The active registry and the archive as objects.

Lookup by address, id allocation, archiving, dependency rules.
"""

from collections.abc import Callable
from dataclasses import dataclass

from backlog_cli.domain.action import Action
from backlog_cli.domain.address import Address
from backlog_cli.domain.item import Item
from backlog_cli.domain.part import PrRef
from backlog_cli.domain.situation import ItemSituation
from backlog_cli.domain.unit import PrUnit, Unit
from backlog_cli.domain.vocabulary import Outcome, UnitStatus
from backlog_cli.errors import Refusal, UsageError
from backlog_cli.moment import Moment
from backlog_cli.store.yamlfile import YamlFile


@dataclass(frozen=True)
class ArchiveContent:
    """What ARCHIVE.yaml holds."""

    items: list[Item]
    schema_version: int


@dataclass(frozen=True)
class ItemLocation:
    item: Item
    is_archived: bool


@dataclass(frozen=True)
class Target:
    """What an address points at."""

    address: Address
    item: Item
    unit: Unit | None
    action: Action | None
    is_archived: bool

    @property
    def name(self) -> str:
        """The short title used in messages."""
        if self.action:
            return self.action.description
        return self.unit.label if self.unit else self.item.title

    def require_active(self) -> None:
        if self.is_archived:
            raise Refusal(
                f"{self.address}: item {self.item.number} is archived and read-only; "
                + self.item.describe_next_item_step()
            )


@dataclass(frozen=True)
class PrSibling:
    """Another unit that carries the same PR."""

    address: str
    unit: PrUnit


class Registry:
    """The active items, and the archive that is read only when it is needed.

    `archived_outcomes` keeps the outcome of each archived item that an active
    item depends on, so the dependency checks never open the archive.
    """

    def __init__(
        self,
        next_id: int,
        active: list[Item],
        load_archive: Callable[[], ArchiveContent],
        archived_outcomes: dict[str, Outcome],
        archived_item_ids: list[str],
        workspace_name: str,
        schema_version: int,
        is_repair_pending: bool = False,
    ) -> None:
        self.next_id = next_id
        self.active = active
        self.workspace_name = workspace_name
        self.schema_versions = [schema_version]
        self.recovered_ids: list[str] = []
        self.is_archive_changed = False
        self._load_archive = load_archive
        self._archived: list[Item] | None = None
        self.archived_outcomes = dict(archived_outcomes)
        self.archived_item_ids = list(archived_item_ids)
        if is_repair_pending:
            self._read_archive()

    @classmethod
    def from_dict(
        cls,
        backlog: dict,
        load_archive: Callable[[], ArchiveContent],
        workspace_name: str,
        is_repair_pending: bool = False,
    ) -> "Registry":
        """Build from BACKLOG.yaml; the archive is read later, if at all."""
        return cls(
            next_id=backlog["next_id"],
            active=[Item.from_dict(entry) for entry in backlog["items"]],
            load_archive=load_archive,
            archived_outcomes={
                key: Outcome(value)
                for key, value in backlog["archived_outcomes"].items()
            },
            archived_item_ids=list(backlog["archived_item_ids"]),
            workspace_name=workspace_name,
            schema_version=backlog["schema_version"],
            is_repair_pending=is_repair_pending,
        )

    @property
    def archived(self) -> list[Item]:
        """The archived items; reading the archive file happens here, once."""
        if self._archived is None:
            self._read_archive()
        return self._archived

    def _read_archive(self) -> None:
        """An id found in both files is an interrupted archive: the archive copy
        wins and the stale active copy is dropped (`recovered_ids`).
        """
        content = self._load_archive()
        self.schema_versions.append(content.schema_version)
        self._archived = content.items
        archived_ids = {item.id for item in content.items}
        self.recovered_ids = [
            item.id for item in self.active if item.id in archived_ids
        ]
        self.active = [item for item in self.active if item.id not in archived_ids]
        for item in content.items:
            if item.id in self.recovered_ids:
                self._record_archived(item)

    @property
    def is_from_newer_schema(self) -> bool:
        return max(self.schema_versions) > YamlFile.SCHEMA_VERSION

    def require_writable(self) -> None:
        if self.is_from_newer_schema:
            raise Refusal(
                "This workspace was written by a newer backlog "
                f"(schema {max(self.schema_versions)}, this code knows "
                f"{YamlFile.SCHEMA_VERSION}). Update backlog."
            )

    def to_backlog_dict(self) -> dict:
        referenced = {dep for item in self.active for dep in item.depends_on}
        outcomes = {
            item_id: str(outcome)
            for item_id, outcome in self.archived_outcomes.items()
            if item_id in referenced
        }
        return {
            "schema_version": YamlFile.SCHEMA_VERSION,
            "next_id": self.next_id,
            "archived_outcomes": outcomes,
            "archived_item_ids": self.archived_item_ids,
            "items": [item.to_dict() for item in self.active],
        }

    def to_archive_dict(self) -> dict:
        return {
            "schema_version": YamlFile.SCHEMA_VERSION,
            "items": [item.to_dict() for item in self.archived],
        }

    @property
    def all_items(self) -> list[Item]:
        return [*self.active, *self.archived]

    def find_item(self, reference: int | str) -> ItemLocation:
        """Find by number or exact id: the active items first, then the archive."""
        for item in self.active:
            if reference in (item.number, item.id):
                return ItemLocation(item, is_archived=False)
        for item in self.archived:
            if reference in (item.number, item.id):
                return ItemLocation(item, is_archived=True)
        message = (
            f"no item {reference} in workspace {self.workspace_name!r} "
            "(active or archive); See: backlog list --archive"
        )
        if not self.all_items:
            message += (
                "\nThe workspace is empty. "
                'Add the first item: backlog add SLUG --title "..."'
            )
        raise UsageError(message)

    def resolve_target(self, address: Address) -> Target:
        location = self.find_item(address.item)
        unit = location.item.get_unit(address.unit) if address.unit else None
        action = unit.get_action(address.action) if address.action else None
        canonical = Address(location.item.number, address.unit, address.action)
        return Target(canonical, location.item, unit, action, location.is_archived)

    def require_free_slug(self, slug: str) -> None:
        """A slug names one item for good, active or archived."""
        taken = [
            item_id
            for item_id in [item.id for item in self.active] + self.archived_item_ids
            if item_id.split("_", 1)[1] == slug
        ]
        if taken:
            number = Item.get_number(taken[0])
            raise Refusal(f"slug {slug!r} is already used by item {number}")

    def allocate_id(self, slug: str) -> str:
        item_id = f"{self.next_id:04d}_{slug}"
        self.next_id += 1
        return item_id

    def archive(self, item: Item) -> None:
        archived = self.archived
        self.active.remove(item)
        archived.append(item)
        self.is_archive_changed = True
        self._record_archived(item)

    def _record_archived(self, item: Item) -> None:
        """The indexes of BACKLOG.yaml for an archived item; a normal archive and
        the recovery of an interrupted one both come here.
        """
        if item.id not in self.archived_item_ids:
            self.archived_item_ids.append(item.id)
        if any(item.id in other.depends_on for other in self.active):
            self.archived_outcomes[item.id] = item.completion.outcome

    def get_dependency_outcomes(self, item: Item) -> dict[str, Outcome | None]:
        """For each dependency: its archive outcome, or None while it is active."""
        active_ids = {other.id for other in self.active}
        outcomes: dict[str, Outcome | None] = {}
        for dependency_id in item.depends_on:
            outcomes[dependency_id] = (
                None
                if dependency_id in active_ids
                else self.archived_outcomes.get(dependency_id)
            )
        return outcomes

    def get_archived_dependency_outcomes(self, item: Item) -> dict[str, Outcome | None]:
        """For an archived item: the real outcome of each dependency, read from
        the archive (the registry keeps only what active items need).
        """
        known = {other.id: other.completion.outcome for other in self.archived}
        active_ids = {other.id for other in self.active}
        return {
            dependency_id: None
            if dependency_id in active_ids
            else known.get(dependency_id)
            for dependency_id in item.depends_on
        }

    def find_units_sharing_pr(
        self, pr: PrRef, item: Item, unit: Unit
    ) -> list[PrSibling]:
        """The other open or finished units of the active items with this PR."""
        found = []
        for other_item in self.active:
            for other in other_item.work:
                pr_unit = other.get_pr_unit()
                if pr_unit is None or pr_unit.pr != pr:
                    continue
                if (other_item is item and other is unit) or other.status in (
                    UnitStatus.CANCELLED,
                    UnitStatus.SUPERSEDED,
                ):
                    continue
                found.append(PrSibling(f"{other_item.number}/{other.id}", pr_unit))
        return found

    def get_situation(self, item: Item) -> ItemSituation:
        return ItemSituation.of(
            item,
            self.get_dependency_outcomes(item),
            Moment.now(),
            self._find_unblocked_by(item),
        )

    def _find_unblocked_by(self, item: Item) -> tuple[int, ...]:
        """Active items for which `item` is the only dependency not yet done."""
        found = []
        for other in self.active:
            if item.id not in other.depends_on:
                continue
            outcomes = self.get_dependency_outcomes(other)
            unmet = [
                dep for dep in other.depends_on if outcomes.get(dep) != Outcome.DONE
            ]
            if unmet == [item.id]:
                found.append(other.number)
        return tuple(sorted(found))

    def take_snapshot(self) -> dict[str, dict]:
        """The active items as plain data, to tell afterwards which changed."""
        return {item.id: item.to_dict() for item in self.active}

    def settle_changed(self, snapshot: dict[str, dict], extra_ids: set[str]) -> None:
        """Recalculate the status and the update time of every touched item.

        Touched: its data changed since the snapshot, it is new, or `extra_ids`
        names it (its details file was rewritten).
        """
        loaded_archive = self._archived or []
        for item in [*self.active, *loaded_archive]:
            before = snapshot.get(item.id)
            is_new = before is None and item in self.active
            is_changed = before is not None and before != item.to_dict()
            if is_new or is_changed or item.id in extra_ids:
                item.settle()

    def get_active_dependents(self, item: Item) -> list[Item]:
        return [other for other in self.active if item.id in other.depends_on]

    def get_dependents(self, item: Item) -> list[Item]:
        dependents = [other for other in self.all_items if item.id in other.depends_on]
        return sorted(dependents, key=lambda dependent: dependent.number)

    def accept_dependency(
        self, location: ItemLocation, dependent: Item | None = None
    ) -> Item:
        """Refuse a dependency that was archived without being done; note an
        archived one in the outcome map. `dependent` is the item that depends on
        it, or None for an item that is being created.
        """
        dependency = location.item
        if not location.is_archived:
            return dependency
        outcome = dependency.completion.outcome
        if outcome != Outcome.DONE:
            raise UsageError(
                f"item {dependency.number} is archived as {outcome} and will never "
                "be done; depend on an active item or one archived as done"
                + self._describe_successor(dependency, dependent)
            )
        self.archived_outcomes[dependency.id] = outcome
        return dependency

    def _find_last_successor(self, dependency: Item) -> Item | None:
        """Follow `superseded by` to the last item that is active or done."""
        current, seen = dependency, {dependency.id}
        while current.completion is not None and current.completion.outcome != (
            Outcome.DONE
        ):
            follow_up = current.completion.follow_up
            if (
                current.completion.outcome != Outcome.SUPERSEDED
                or not follow_up
                or follow_up in seen
            ):
                return None
            seen.add(follow_up)
            current = self.find_item(Item.get_number(follow_up)).item
        return current

    def _describe_successor(self, dependency: Item, dependent: Item | None) -> str:
        """Where the work of a superseded dependency went, with the commands."""
        last = self._find_last_successor(dependency)
        if last is None or last.id == dependency.id:
            return ""
        successor = last.number
        if dependent is None:
            return f"\nIts work went to item {successor}: use --depends-on {successor}"
        if last.id == dependent.id:
            # The item itself continues that work: nothing to depend on.
            return (
                "\nThis item continues its work; drop the dependency:\n"
                f"backlog {dependent.number} dependency remove {dependency.number}"
            )
        commands = f"backlog {dependent.number} dependency add {successor}"
        if dependency.id in dependent.depends_on:
            commands = (
                f"backlog {dependent.number} dependency remove {dependency.number}\n"
                + commands
            )
        return f"\nIts work went to item {successor}; move the dependency:\n{commands}"

    def require_valid_dependency(self, item: Item, location: ItemLocation) -> Item:
        """Refuse a dependency on the item itself, a dead one, or a cycle."""
        dependency = self.accept_dependency(location, item)
        if dependency.id == item.id:
            raise UsageError(f"item {item.number} cannot depend on itself")
        chain = self.find_dependency_chain(start=dependency, goal=item)
        if chain:
            cycle = " -> ".join([item.id, *chain])
            raise UsageError(f"this would create a dependency cycle: {cycle}")
        return dependency

    def find_dependency_chain(self, start: Item, goal: Item) -> list[str]:
        """Ids from `start` down to `goal` along depends_on, or [] if unreachable.

        Only active items are walked: an archived item can depend only on items
        archived as done, which never lead back to an active one.
        """
        by_id = {candidate.id: candidate for candidate in self.active}
        visited: set[str] = set()
        stack = [(start, [start.id])]
        while stack:
            current, chain = stack.pop()
            if current.id == goal.id:
                return chain
            if current.id in visited:
                continue
            visited.add(current.id)
            for next_id in current.depends_on:
                if next_id in by_id:
                    stack.append((by_id[next_id], [*chain, next_id]))
        return []
