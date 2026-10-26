"""The GitHub repository of a directory, read from `.git` files (no git process)."""

import configparser
import re
from pathlib import Path

from backlog_cli.errors import UsageError


class RepoOrigin:
    NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    URL_PATTERN = re.compile(
        r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)"
        r"([^/\s]+/[^/\s]+?)(?:\.git)?/?$",
        re.IGNORECASE,
    )
    SECTION = 'remote "origin"'

    @classmethod
    def require_name(cls, text: str) -> str:
        """A repository name as typed: OWNER/NAME."""
        if not cls.NAME_PATTERN.match(text):
            raise UsageError(f"'{text}' is not a repository; use OWNER/NAME")
        return text

    @classmethod
    def find(cls, directory: Path) -> str | None:
        """OWNER/NAME of the origin of the repository around `directory`."""
        for candidate in (directory, *directory.parents):
            git = candidate / ".git"
            if git.exists():
                config = cls._find_config(git)
                return cls.parse_url(cls._read_origin_url(config)) if config else None
        return None

    @classmethod
    def parse_url(cls, url: str | None) -> str | None:
        match = cls.URL_PATTERN.match(url.strip()) if url else None
        return match.group(1) if match else None

    @staticmethod
    def _find_config(git: Path) -> Path | None:
        """`.git/config`, or for a worktree the config of the common directory."""
        if git.is_dir():
            return git / "config"
        try:
            first = git.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, IndexError, UnicodeDecodeError):
            return None
        if not first.startswith("gitdir:"):
            return None
        git_dir = git.parent / first.removeprefix("gitdir:").strip()
        try:
            common = (git_dir / "commondir").read_text(encoding="utf-8").strip()
        except OSError:
            return git_dir / "config"
        return git_dir / common / "config"

    @classmethod
    def _read_origin_url(cls, config: Path) -> str | None:
        parser = configparser.ConfigParser(strict=False, interpolation=None)
        try:
            parser.read(config, encoding="utf-8")
        except (configparser.Error, OSError, UnicodeDecodeError):
            return None
        return parser.get(cls.SECTION, "url", fallback=None)
