"""`serve`: a read-only web viewer of every workspace in the data root."""

import errno

from backlog_cli.command.base import Command, ShortHelpParser
from backlog_cli.errors import UsageError
from backlog_cli.serve.server import ViewerServer
from backlog_cli.serve.site import Site


class ServeParser(ShortHelpParser):
    port: int = 8765  # Port on 127.0.0.1.


class ServeCommand(Command):
    NAME = "serve"
    SUMMARY = "Show every workspace in a browser; read-only, local."
    USAGE = "backlog serve [--port N]"
    EXAMPLES = "Example: backlog serve --port 8765"
    Parser = ServeParser

    def run(self, args: ServeParser) -> int:
        if not 0 <= args.port <= 65535:
            raise UsageError(f"--port {args.port} is not a port; use 1-65535")
        try:
            server = ViewerServer(args.port, Site(self.session.home))
        except OSError as error:
            if error.errno != errno.EADDRINUSE:
                raise
            raise UsageError(
                f"port {args.port} is in use; pick another with --port N"
            ) from None
        self.print_lines(f"Serving {self.session.home} at {server.url}")
        self.session.out.flush()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
