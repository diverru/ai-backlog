"""Crash-safe file writes and the one lock that serialises writers."""

import fcntl
import os
import time
from pathlib import Path

from backlog_cli.errors import LockError


class AtomicFile:
    @staticmethod
    def write(path: Path, text: str) -> None:
        """Write a temp file next to the target, fsync, rename, fsync the directory.

        A reader sees the old file or the new one, never half of it.
        """
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            with open(temp, "w", encoding="utf-8") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


class FileLock:
    """Exclusive `flock`, retried for a while.

    Held for the whole read-check-write of a command.
    """

    WAIT_SECONDS = 10

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def __enter__(self) -> "FileLock":
        self._handle = open(self.path, "a")
        deadline = time.monotonic() + self.WAIT_SECONDS
        while True:
            try:
                fcntl.flock(self._handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() > deadline:
                    self._handle.close()
                    raise LockError(
                        "another backlog command is writing; "
                        "wait a moment and run this command again"
                    ) from None
                time.sleep(0.05)

    def __exit__(self, *exception_info: object) -> None:
        fcntl.flock(self._handle, fcntl.LOCK_UN)
        self._handle.close()
