"""`/_/file` and `/_/raw`: what the preview dialog shows for a path on disk."""

import codecs
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote

from backlog_cli.serve.text import HtmlText


@dataclass(frozen=True)
class Preview:
    kind: str  # md, text, image or binary
    html: str
    note: str = ""


class FilePreview:
    LIMIT_BYTES = 1024 * 1024
    MARKDOWN_SUFFIXES = (".md", ".markdown")
    IMAGE_TYPES = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }

    @classmethod
    def get_image_type(cls, absolute_path: str) -> str | None:
        return cls.IMAGE_TYPES.get(os.path.splitext(absolute_path)[1].lower())

    @classmethod
    def build(
        cls, absolute_path: str, render_markdown: Callable[[str], str]
    ) -> Preview:
        """Read at most the first megabyte of the file; never write."""
        if cls.get_image_type(absolute_path):
            raw = quote(absolute_path, safe="")
            return Preview(
                "image", f'<img class="preview-image" src="/_/raw?path={raw}" alt="">'
            )
        with open(absolute_path, "rb") as stream:
            data = stream.read(cls.LIMIT_BYTES + 1)
        note = "first 1 MB shown" if len(data) > cls.LIMIT_BYTES else ""
        text = cls._decode(data[: cls.LIMIT_BYTES])
        if text is None:
            return Preview("binary", '<p class="sub">no preview</p>')
        if absolute_path.lower().endswith(cls.MARKDOWN_SUFFIXES):
            return Preview(
                "md",
                '<div class="brief"><div class="doc">'
                f"{render_markdown(text)}</div></div>",
                note,
            )
        return Preview(
            "text", f'<pre class="preview-text">{HtmlText.esc(text)}</pre>', note
        )

    @staticmethod
    def _decode(data: bytes) -> str | None:
        """The text, or None when the bytes are not UTF-8 text."""
        if b"\0" in data:
            return None
        try:
            # final=False: a cut at the 1 MB limit may end inside a character
            return codecs.getincrementaldecoder("utf-8")().decode(data, final=False)
        except UnicodeDecodeError:
            return None

    @classmethod
    def to_json(cls, absolute_path: str, preview: Preview) -> str:
        return json.dumps(
            {
                "path": absolute_path,
                "kind": preview.kind,
                "html": preview.html,
                "note": preview.note,
            }
        )
