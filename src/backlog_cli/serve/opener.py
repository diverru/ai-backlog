"""The one program the viewer starts: macOS `open`, for a file or folder the
reader clicked. The path goes in as one argument, never through a shell.
"""

import subprocess


class Opener:
    @staticmethod
    def open(absolute_path: str, reveal: bool) -> None:
        """Open the path in its default app, or show it in Finder when `reveal`."""
        command = ["open", "-R", absolute_path] if reveal else ["open", absolute_path]
        subprocess.run(command, check=False)
