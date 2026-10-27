"""One workspace on disk.

Registry, archive, details files, repository settings and the write lock.
"""

import re
import shutil
from pathlib import Path

import yaml

from backlog_cli.domain.details_file import DetailsFile
from backlog_cli.domain.item import Item
from backlog_cli.domain.vocabulary import DetailsSection
from backlog_cli.errors import Refusal, UsageError
from backlog_cli.store.atomic import AtomicFile, FileLock
from backlog_cli.store.registry import ArchiveContent, Registry
from backlog_cli.store.yamlfile import YamlFile


class Workspace:
    NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

    def __init__(self, home: Path, name: str) -> None:
        self.name = name
        self.root = home / name
        self.backlog_path = self.root / "BACKLOG.yaml"
        self.archive_path = self.root / "ARCHIVE.yaml"
        self.details_dir = self.root / "details"
        # Exists while an item may be in both files: the next load repairs it.
        self.archiving_marker_path = self.root / ".archiving"

    @staticmethod
    def describe_bad_name(name: str) -> str:
        return (
            f"bad workspace name {name[:70]!r}; use lowercase letters, digits, dots, "
            "dashes and underscores, start with a letter or a digit, "
            "at most 64 characters"
        )

    @classmethod
    def open(cls, home: Path, name: str) -> "Workspace":
        if not cls.NAME_PATTERN.match(name):
            raise UsageError(cls.describe_bad_name(name))
        workspace = cls(home, name)
        if not workspace.is_created:
            raise UsageError(
                f"workspace {name!r} does not exist; "
                f"create it with: backlog bind {name}"
            )
        return workspace

    @property
    def is_created(self) -> bool:
        return self.backlog_path.exists()

    def create(self) -> None:
        self.details_dir.mkdir(parents=True, exist_ok=True)
        version = YamlFile.SCHEMA_VERSION
        empty_archive = {"schema_version": version, "items": []}
        empty_backlog = {
            "schema_version": version,
            "next_id": 1,
            "archived_outcomes": {},
            "archived_item_ids": [],
            "items": [],
        }
        AtomicFile.write(self.archive_path, YamlFile.dump(empty_archive))
        AtomicFile.write(self.backlog_path, YamlFile.dump(empty_backlog))

    def acquire_lock(self) -> FileLock:
        return FileLock(self.root / ".lock")

    def load_registry(self) -> Registry:
        """The active items now; the archive only when a command asks for it."""
        return Registry.from_dict(
            YamlFile.load(self.backlog_path),
            self.read_archive,
            self.name,
            is_repair_pending=self.archiving_marker_path.exists(),
        )

    def read_archive(self) -> ArchiveContent:
        try:
            data = YamlFile.load(self.archive_path)
            items = [Item.from_dict(entry) for entry in data["items"]]
            return ArchiveContent(items, data["schema_version"])
        except (
            yaml.YAMLError,
            KeyError,
            TypeError,
            AttributeError,
            ValueError,
        ) as error:
            raise Refusal(
                f"{self.archive_path} cannot be read ({type(error).__name__}). "
                "Do not edit the data files by hand; report this to the user."
            ) from None

    def save(
        self, registry: Registry, new_details: dict[str, str] | None = None
    ) -> None:
        """Write details, then the archive, then the registry.

        A crash between the archive and the registry leaves an item in both files;
        the marker tells the next load to repair it. An item is never lost. The
        archive is touched only when this change archived something.
        """
        registry.require_writable()
        for item_id, text in (new_details or {}).items():
            self.write_details(item_id, text)
        changed_paths = [self.backlog_path]
        if registry.is_archive_changed:
            changed_paths.append(self.archive_path)
            AtomicFile.write(self.archiving_marker_path, "archive write in progress\n")
        for path in changed_paths:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        if registry.is_archive_changed:
            self.write_archive_file(YamlFile.dump(registry.to_archive_dict()))
        self.write_backlog_file(YamlFile.dump(registry.to_backlog_dict()))
        self.archiving_marker_path.unlink(missing_ok=True)
        registry.is_archive_changed = False

    def write_archive_file(self, text: str) -> None:
        AtomicFile.write(self.archive_path, text)

    def write_backlog_file(self, text: str) -> None:
        AtomicFile.write(self.backlog_path, text)

    def get_details_path(self, item_id: str) -> Path:
        return self.details_dir / f"{item_id}.md"

    def read_details(self, item_id: str) -> str:
        return self.get_details_path(item_id).read_text(encoding="utf-8")

    def has_empty_brief(self, item_id: str, text: str | None = None) -> bool:
        """The Problem section is blank, in `text` or else in the file. A file that
        cannot be read or parsed is not empty: the hint must never be an error.
        """
        try:
            details = DetailsFile.parse(
                self.read_details(item_id) if text is None else text
            )
        except (OSError, ValueError, UsageError):
            return False
        return not details.get_section(DetailsSection.PROBLEM).strip()

    def find_empty_brief_ids(self, registry: Registry) -> set[str]:
        return {item.id for item in registry.active if self.has_empty_brief(item.id)}

    def write_details(self, item_id: str, text: str) -> None:
        AtomicFile.write(self.get_details_path(item_id), text)
