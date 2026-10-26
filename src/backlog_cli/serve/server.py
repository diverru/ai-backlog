"""The HTTP side: a server on 127.0.0.1 that answers GET, HEAD and POST /_/open."""

import queue
import sys
import threading
import traceback
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from backlog_cli.serve.file_routes import Response
from backlog_cli.serve.site import Site


@dataclass
class PendingRequest:
    """A parsed request that waits in the queue for the main thread."""

    method: str
    path: str
    host: str | None
    origin: str | None
    body: bytes
    is_answered: threading.Event = field(default_factory=threading.Event)
    response: Response | None = None


class ViewerHandler(BaseHTTPRequestHandler):
    server: "ViewerServer"
    SECURITY_HEADERS = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
            "form-action 'self'; base-uri 'none'"
        ),
    }

    MAX_BODY = 65536
    # A browser opens spare sockets and leaves them idle; do not wait on one forever.
    timeout = 10

    def do_GET(self) -> None:
        self._answer(self._handle(), True)

    def do_HEAD(self) -> None:
        self._answer(self._handle(), False)

    def do_POST(self) -> None:
        length = min(int(self.headers.get("Content-Length") or 0), self.MAX_BODY)
        self._answer(self._handle(self.rfile.read(length)), True)

    def do_PUT(self) -> None:
        self._answer(self._handle(), True)

    do_DELETE = do_PATCH = do_OPTIONS = do_PUT

    def _handle(self, body: bytes = b"") -> Response:
        pending = PendingRequest(
            self.command,
            self.path,
            self.headers.get("Host"),
            self.headers.get("Origin"),
            body,
        )
        self.server.pending.put(pending)
        pending.is_answered.wait()
        return pending.response

    def _answer(self, response: Response, with_body: bool) -> None:
        body = response.body
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(response.status)
        self.send_header("Content-Type", response.content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in {**self.SECURITY_HEADERS, **response.headers}.items():
            self.send_header(name, value)
        self.end_headers()
        if with_body:
            self.wfile.write(body)


class ViewerServer(ThreadingHTTPServer):
    """Threads accept and read requests, so an idle socket blocks nobody. The
    pages are built one request at a time in the main thread: the search time
    limit is a signal, and signals reach only the main thread.
    """

    daemon_threads = True

    def __init__(self, port: int, site: Site) -> None:
        super().__init__(("127.0.0.1", port), ViewerHandler)
        self.site = site
        self.pending: queue.Queue[PendingRequest] = queue.Queue()
        site.port = self.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"

    def start_accepting(self) -> threading.Thread:
        acceptor = threading.Thread(target=super().serve_forever, daemon=True)
        acceptor.start()
        return acceptor

    def answer_next(self, wait_seconds: float) -> None:
        """Build the page of the oldest waiting request, in the calling thread."""
        try:
            pending = self.pending.get(timeout=wait_seconds)
        except queue.Empty:
            return
        try:
            pending.response = self.site.handle(
                pending.method, pending.path, pending.host, pending.origin, pending.body
            )
        except Exception:
            traceback.print_exc(file=sys.stderr)
            pending.response = Response(
                500, "500 Server Error\n", content_type="text/plain"
            )
        pending.is_answered.set()

    def serve_forever(self, poll_interval: float = 0.5) -> None:
        acceptor = self.start_accepting()
        try:
            while True:
                self.answer_next(poll_interval)
        finally:
            self.shutdown()
            acceptor.join()
