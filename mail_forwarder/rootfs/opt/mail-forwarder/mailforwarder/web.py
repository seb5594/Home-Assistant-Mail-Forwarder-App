"""The web interface and its JSON API, served through Home Assistant ingress.

Ingress puts the page under a long, changing path, so the page itself only uses relative URLs.
Only the Supervisor's ingress gateway may connect; it has already checked who the user is.
"""
import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import unquote, urlparse

from . import network, settings, supervisor
from .addresses import normalize_address
from .delivery import classify
from .messages import Message
from .presets import PRESETS
from .store import ConfigError

_MAX_BODY_BYTES = 256 * 1024
_CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'self'")


class ApiError(Message):
    """A request the app refuses. The code lets the page answer in the user's language."""

    texts = {
        "json_expected": "Expected a JSON request.",
        "too_large": "The request is too large.",
        "invalid_json": "The request is not valid JSON.",
        "object_expected": "Expected a JSON object.",
        "test_address": "Choose one of your own, enabled addresses for the test.",
        "test_running": "A test is already running. Wait for it to finish.",
        "queue_missing": "That message does not exist (any more).",
        "not_found": "Not found",
        "internal": "Something went wrong inside the app. See the log.",
    }

    def __init__(self, code: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST, **params):
        super().__init__(code, **params)
        self.status = status


class WebServer:
    """Wires the HTTP handler to the application's parts."""

    def __init__(self, app):
        self.app = app
        self._httpd: Optional[ThreadingHTTPServer] = None

    def start(self, host: str, port: int) -> int:
        handler = _handler_for(self)
        self._httpd = ThreadingHTTPServer((host, port), handler)
        threading.Thread(target=self._httpd.serve_forever, name="web", daemon=True).start()
        return self._httpd.server_address[1]

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()

    # ---- API: reading --------------------------------------------------------------------------

    def state(self) -> dict:
        app = self.app
        known, host_port = supervisor.published_port(settings.SMTP_PORT)
        return {
            "version": settings.read_version(),
            "smtp_port": settings.SMTP_PORT,
            "public_ip": network.cached_public_ip(),
            "host_port": host_port if known else None,
            "host_addresses": supervisor.host_addresses(),
            "config": app.store.masked(),
            "queue": app.spool.counts(),
            "stats": app.stats.snapshot(),
            "checks": app.diagnostics.snapshot(),
            "test_mail": app.tests.snapshot(),
            "ddns": app.ddns.status(),
            "presets": PRESETS,
        }

    def queue(self) -> dict:
        return {"queued": [job.public() for job in self.app.spool.queued()],
                "failed": [job.public() for job in self.app.spool.failed()]}

    # ---- API: actions --------------------------------------------------------------------------

    def save_config(self, body: dict) -> dict:
        try:
            masked = self.app.store.replace(body)
        except ConfigError as error:
            raise ApiError(error.code, **error.params) from error
        self.app.ddns.run_soon()
        self.app.diagnostics.run_in_background()
        return masked

    def start_test_mail(self, body: dict) -> dict:
        alias = normalize_address(str(body.get("address", "")))
        if alias is None or alias not in self.app.store.routes():
            raise ApiError("test_address")
        if not self.app.tests.can_start():
            raise ApiError("test_running", HTTPStatus.CONFLICT)
        token = self.app.tests.start(alias)
        threading.Thread(target=self._send_test, args=(alias, token), name="test-mail", daemon=True).start()
        return self.app.tests.snapshot()

    def _send_test(self, alias: str, token: str) -> None:
        try:
            self.app.deliverer.send_test(alias, token)
        except Exception as error:  # noqa: BLE001 - shown to the user in the test card
            failure = classify(error)
            self.app.tests.fail(token, failure)
            self.app.events.warning(f"The test message could not be sent: {failure}", "test_failed",
                                    error_code=failure.code, error_params=failure.params)
        else:
            self.app.tests.mark(token, "sent")
            self.app.events.info(f"Test message to {alias} was handed to the sending service.", "test_sent",
                                 alias=alias)

    def queue_action(self, job_id: str, action: str) -> dict:
        spool = self.app.spool
        done = {"retry": lambda: spool.requeue(job_id) or spool.retry_now(job_id),
                "delete": lambda: spool.discard(job_id)}.get(action)
        if done is None or not done():
            raise ApiError("queue_missing", HTTPStatus.NOT_FOUND)
        self.app.worker.wake()
        return self.queue()


def _handler_for(server: WebServer) -> type:
    app = server.app

    class Handler(BaseHTTPRequestHandler):
        server_version = "MailForwarder"

        def log_message(self, format, *args):  # noqa: A002 - signature of the base class
            pass  # requests are not interesting; the activity log covers the real events

        # ---- plumbing ------------------------------------------------------------------------

        def _allowed(self) -> bool:
            return settings.WEB_OPEN_TO_ALL or self.client_address[0] in settings.ALLOWED_WEB_CLIENTS

        def _send(self, status: HTTPStatus, body: bytes, content_type: str, cache: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "max-age=300" if cache else "no-store")
            self.send_header("Content-Security-Policy", _CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _body(self) -> dict:
            if "application/json" not in self.headers.get("Content-Type", ""):
                raise ApiError("json_expected", HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            length = int(self.headers.get("Content-Length") or 0)
            if length > _MAX_BODY_BYTES:
                raise ApiError("too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError as error:
                raise ApiError("invalid_json") from error
            if not isinstance(body, dict):
                raise ApiError("object_expected")
            return body

        def _dispatch(self, routes: dict) -> None:
            if not self._allowed():
                self._send(HTTPStatus.FORBIDDEN, b"Use Home Assistant to open this page.", "text/plain")
                return
            path = urlparse(self.path).path
            try:
                for pattern, handler in routes.items():
                    arguments = _match(pattern, path)
                    if arguments is not None:
                        self._json(handler(self, *arguments))
                        return
                self._json({"error": "Not found", "code": "not_found", "params": {}}, HTTPStatus.NOT_FOUND)
            except ApiError as error:
                self._json({"error": str(error), **error.as_dict()}, error.status)
            except Exception as error:  # noqa: BLE001 - the browser gets a message instead of a hang
                app.events.error(f"Web request {path} failed: {error}", "web_failed", path=path)
                self._json({"error": str(ApiError("internal")), "code": "internal", "params": {}},
                           HTTPStatus.INTERNAL_SERVER_ERROR)

        # ---- verbs ---------------------------------------------------------------------------

        def do_GET(self):  # noqa: N802 - name fixed by BaseHTTPRequestHandler
            if not self._allowed():
                self._send(HTTPStatus.FORBIDDEN, b"Use Home Assistant to open this page.", "text/plain")
            elif urlparse(self.path).path.startswith("/api/"):
                self._dispatch(GET_ROUTES)
            else:
                self._static(urlparse(self.path).path)

        def do_POST(self):  # noqa: N802
            self._dispatch(POST_ROUTES)

        def do_PUT(self):  # noqa: N802
            self._dispatch(PUT_ROUTES)

        def _static(self, path: str) -> None:
            relative = unquote(path).lstrip("/") or "index.html"
            root = settings.WEB_ROOT.resolve()
            target = (root / relative).resolve()
            if root not in target.parents or not target.is_file():
                self._send(HTTPStatus.NOT_FOUND, b"Not found", "text/plain")
                return
            kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if kind.startswith("text/") or kind in ("application/javascript", "application/json"):
                kind += "; charset=utf-8"
            self._send(HTTPStatus.OK, target.read_bytes(), kind, cache=target.suffix in (".png", ".svg"))

    # Routes: URL pattern -> function(handler, *url_arguments). ``<name>`` matches one path part.
    GET_ROUTES: dict = {
        "/api/state": lambda h: server.state(),
        "/api/queue": lambda h: server.queue(),
        "/api/activity": lambda h: {"events": app.events.recent(150)},
    }
    POST_ROUTES: dict = {
        "/api/checks/run": lambda h: {"started": app.diagnostics.run_in_background()},
        "/api/relay/test": lambda h: app.diagnostics.check_login(),
        "/api/test-mail": lambda h: server.start_test_mail(h._body()),
        "/api/ddns/run": lambda h: (app.ddns.run_soon(), {"started": True})[1],
        "/api/queue/<id>/<action>": lambda h, job_id, action: server.queue_action(job_id, action),
    }
    PUT_ROUTES: dict = {
        "/api/config": lambda h: server.save_config(h._body()),
    }
    return Handler


def _match(pattern: str, path: str) -> Optional[tuple]:
    """Returns the values of the ``<...>`` parts when ``path`` fits ``pattern``, else None."""
    wanted, actual = pattern.strip("/").split("/"), path.strip("/").split("/")
    if len(wanted) != len(actual):
        return None
    values = []
    for expected, found in zip(wanted, actual):
        if expected.startswith("<"):
            values.append(found)
        elif expected != found:
            return None
    return tuple(values)
