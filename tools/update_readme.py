#!/usr/bin/env python3
"""Rebuild the generated part of README.md from the guide."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backlog_cli.errors import UsageError  # noqa: E402
from backlog_cli.guide.readme_guide import ReadmeGuide  # noqa: E402


def main() -> int:
    readme = Path(__file__).resolve().parents[1] / "README.md"
    old = readme.read_text()
    try:
        new = ReadmeGuide.refresh(old)
    except UsageError as error:
        print(error, file=sys.stderr)
        return error.exit_code
    if new != old:
        readme.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
