"""`/_/file`, `/_/raw` and `/_/open`: the preview of a path and the click-to-open."""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from backlog_cli.serve.file_preview import FilePreview
from backlog_cli.serve.opener import Opener


@dataclass
class Response:
    status: int
    body: str | bytes = ""
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str = "text/html; charset=utf-8"


class FileRoutes:
    JSON = "application/json; charset=utf-8"

    @classmethod
    def find_existing(cls, text: str | None) -> str | None:
        """The absolute path for the text, or None unless it exists."""
        if not text:
            return None
        absolute = os.path.expanduser(text)
        if not os.path.isabs(absolute) or not os.path.exists(absolute):
            return None
        return absolute

    @classmethod
    def build_json(cls, status: int, data: dict) -> Response:
        return Response(status, json.dumps(data), content_type=cls.JSON)

    @classmethod
    def preview(
        cls, params: dict[str, str], render_markdown: Callable[[str], str]
    ) -> Response:
        absolute = cls.find_existing(params.get("path"))
        if absolute is None or not os.path.isfile(absolute):
            return cls.build_json(404, {"error": "no such file"})
        try:
            preview = FilePreview.build(absolute, render_markdown)
        except OSError as error:
            return cls.build_json(404, {"error": error.strerror or "cannot be read"})
        return Response(
            200, FilePreview.to_json(absolute, preview), content_type=cls.JSON
        )

    @classmethod
    def raw(cls, params: dict[str, str]) -> Response:
        """The bytes of an image, for the `<img>` of the preview."""
        absolute = cls.find_existing(params.get("path"))
        image_type = FilePreview.get_image_type(absolute or "")
        if absolute is None or image_type is None or not os.path.isfile(absolute):
            return Response(404, "not found\n", content_type="text/plain")
        try:
            with open(absolute, "rb") as stream:
                data = stream.read()
        except OSError:
            return Response(404, "not found\n", content_type="text/plain")
        # `sandbox` keeps a script inside an SVG from running if it is opened alone
        sandbox = {"Content-Security-Policy": "default-src 'none'; sandbox"}
        return Response(200, data, sandbox, image_type)

    @classmethod
    def open(cls, form: dict[str, str], is_same_origin: bool) -> Response:
        if not is_same_origin:
            return cls.build_json(403, {"error": "request from another origin"})
        absolute = cls.find_existing(form.get("path"))
        if absolute is None:
            return cls.build_json(404, {"error": "no such path"})
        Opener.open(absolute, form.get("reveal") == "1")
        return cls.build_json(200, {"ok": True})
