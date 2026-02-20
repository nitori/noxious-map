from http.server import (
    SimpleHTTPRequestHandler,
    ThreadingHTTPServer,
)
from http.server import test  # noqa
import contextlib
import socket
import os
import io

if __name__ == "__main__":
    # ensure dual-stack is not disabled; ref #38907
    class DualStackServerMixin:
        def server_bind(self):
            # suppress exception when protocol is IPv4
            with contextlib.suppress(Exception):
                self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
            return super().server_bind()

        def finish_request(self, request, client_address):
            self.RequestHandlerClass(
                request, client_address, self, directory=os.path.dirname(__file__)
            )

    class HTTPDualStackServer(DualStackServerMixin, ThreadingHTTPServer):
        pass

    class RequestHandler(SimpleHTTPRequestHandler):

        def translate_path(self, path):
            path = super().translate_path(path)
            path = path.replace('.%%METADATA_MTIME%%', '')
            path = path.replace('.%%SCRIPT_MTIME%%', '')
            return path

    ServerClass = HTTPDualStackServer

    test(
        HandlerClass=RequestHandler,
        ServerClass=HTTPDualStackServer,
        port=4354,
        bind="127.0.0.1",
        protocol="HTTP/1.0",
    )
