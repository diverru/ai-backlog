"""`~/.bklg/config.yaml`: which directory or repository belongs to which workspace."""

from pathlib import Path

from backlog_cli.errors import Refusal, UsageError
from backlog_cli.store.atomic import AtomicFile
from backlog_cli.store.yamlfile import YamlFile


class BindingConfig:
    def __init__(
        self, path: Path, bindings: dict[str, str], repos: dict[str, str]
    ) -> None:
        self.path = path
        self.bindings = bindings
        self.repos = repos

    @classmethod
    def load(cls, home: Path) -> "BindingConfig":
        path = home / "config.yaml"
        if not path.exists():
            return cls(path, {}, {})
        data = YamlFile.load(path)
        # A file written before repositories existed has no `repos`.
        return cls(path, data["bindings"], data.get("repos") or {})

    def get_workspace_for(self, directory: Path) -> str | None:
        """The nearest bound directory, walking up from `directory`, wins."""
        for candidate in (directory, *directory.parents):
            if str(candidate) in self.bindings:
                return self.bindings[str(candidate)]
        return None

    def bind(self, directory: Path, workspace: str) -> bool:
        """Bind it; False when it was already bound to this workspace."""
        current = self.bindings.get(str(directory))
        if current not in (None, workspace):
            raise Refusal(
                f"{directory} is already bound to workspace {current}; "
                f"run: backlog unbind --dir {directory}"
            )
        self.bindings[str(directory)] = workspace
        return current is None

    def unbind(self, directory: Path) -> str:
        if str(directory) not in self.bindings:
            bound = ", ".join(self.bindings) or "none"
            raise UsageError(f"{directory} is not bound; bound directories: {bound}")
        return self.bindings.pop(str(directory))

    def find_repo(self, repo: str) -> tuple[str, str] | None:
        """(the name as stored, its workspace); names compare case-insensitively."""
        for stored, workspace in self.repos.items():
            if stored.lower() == repo.lower():
                return stored, workspace
        return None

    def get_workspace_for_repo(self, repo: str) -> str | None:
        found = self.find_repo(repo)
        return found[1] if found else None

    def bind_repo(self, repo: str, workspace: str) -> bool:
        """Bind it; False when it was already bound to this workspace."""
        found = self.find_repo(repo)
        if found and found[1] != workspace:
            raise Refusal(
                f"{found[0]} is already bound to workspace {found[1]}; "
                f"run: backlog unbind --repo {found[0]}"
            )
        if found:
            return False
        self.repos[repo] = workspace
        return True

    def unbind_repo(self, repo: str) -> str:
        found = self.find_repo(repo)
        if not found:
            bound = ", ".join(self.repos) or "none"
            raise UsageError(f"{repo} is not bound; bound repositories: {bound}")
        return self.repos.pop(found[0])

    def save(self) -> None:
        document: dict = {
            "schema_version": YamlFile.SCHEMA_VERSION,
            "bindings": self.bindings,
        }
        if self.repos:
            document["repos"] = self.repos
        AtomicFile.write(self.path, YamlFile.dump(document))
