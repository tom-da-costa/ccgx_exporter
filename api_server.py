"""
CCGX HTTP API Server
====================
Subscribes to the Victron CCGX MQTT broker and exposes the latest topic
values via a simple HTTP/JSON API.

Endpoints
---------
GET /values/<service>/<instance>/<path>   Latest value for that topic
GET /values                               All known topics + values
GET /portals                              Known portal IDs

Examples
--------
    GET http://server:4756/values/vebus/257/Ac/Out/L1/P
    GET http://server:4756/values/system/0/Dc/Battery/Soc
    GET http://server:4756/values

Usage
-----
    python api_server.py --host 192.168.1.210
    python api_server.py --host 192.168.1.210 --mqtt-port 1883 --api-port 4756
"""

import argparse
import json
import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from mqtt_client import CCGXMQTTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_CCGX_HOST = "192.168.1.210"
DEFAULT_MQTT_PORT = 1883
DEFAULT_API_PORT = 4756
DEFAULT_LISTEN_ADDR = "0.0.0.0"


# ---------------------------------------------------------------------------
# Value store
# ---------------------------------------------------------------------------


@dataclass
class TopicEntry:
    portal_id: str
    service: str
    instance: str
    suffix: str
    value: float
    updated_at: float  # Unix timestamp


class TopicStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # key: (portal_id, service, instance, suffix)
        self._entries: dict[tuple[str, str, str, str], TopicEntry] = {}

    def update(
        self,
        portal_id: str,
        service: str,
        instance: str,
        suffix: str,
        value: float,
    ) -> None:
        key = (portal_id, service, instance, suffix)
        entry = TopicEntry(
            portal_id=portal_id,
            service=service,
            instance=instance,
            suffix=suffix,
            value=value,
            updated_at=time.time(),
        )
        with self._lock:
            self._entries[key] = entry

    def get(self, service: str, instance: str, suffix: str) -> list[TopicEntry]:
        """Return all entries matching (service, instance, suffix) across portals."""
        with self._lock:
            return [
                e
                for (pid, svc, inst, sfx), e in self._entries.items()
                if svc == service and inst == instance and sfx == suffix
            ]

    def all(self) -> list[TopicEntry]:
        with self._lock:
            return list(self._entries.values())

    def portals(self) -> list[str]:
        with self._lock:
            return sorted({e.portal_id for e in self._entries.values()})


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


def _json_response(handler: BaseHTTPRequestHandler, status: int, data) -> None:
    body = json.dumps(data, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _make_handler(store: TopicStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            logger.debug("HTTP %s", fmt % args)

        def do_GET(self):
            parsed = urlparse(self.path)
            parts = parsed.path.strip("/").split("/")

            # GET /portals
            if parts == ["portals"]:
                _json_response(self, 200, store.portals())
                return

            # GET /values  (list all)
            if parts == ["values"]:
                entries = [
                    {
                        "portal_id": e.portal_id,
                        "path": f"{e.service}/{e.instance}/{e.suffix}",
                        "value": e.value,
                        "updated_at": e.updated_at,
                    }
                    for e in sorted(
                        store.all(),
                        key=lambda e: f"{e.service}/{e.instance}/{e.suffix}",
                    )
                ]
                _json_response(self, 200, entries)
                return

            # GET /values/<service>/<instance>/<path…>
            if len(parts) >= 4 and parts[0] == "values":
                service = parts[1]
                instance = parts[2]
                suffix = "/".join(parts[3:])

                matches = store.get(service, instance, suffix)
                if not matches:
                    _json_response(self, 404, {"error": "topic not found"})
                    return

                if len(matches) == 1:
                    e = matches[0]
                    _json_response(
                        self,
                        200,
                        {
                            "portal_id": e.portal_id,
                            "path": f"{service}/{instance}/{suffix}",
                            "value": e.value,
                            "updated_at": e.updated_at,
                        },
                    )
                else:
                    # Multiple portals exposing the same topic
                    _json_response(
                        self,
                        200,
                        [
                            {
                                "portal_id": e.portal_id,
                                "path": f"{service}/{instance}/{suffix}",
                                "value": e.value,
                                "updated_at": e.updated_at,
                            }
                            for e in matches
                        ],
                    )
                return

            _json_response(self, 404, {"error": "not found"})

    return Handler


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="HTTP API server exposing live Victron CCGX MQTT topic values",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_CCGX_HOST,
        help="IP address or hostname of the CCGX",
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        default=DEFAULT_MQTT_PORT,
        help="MQTT broker port on the CCGX",
    )
    parser.add_argument(
        "--listen-address",
        default=DEFAULT_LISTEN_ADDR,
        help="Address to bind the HTTP API server to",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=DEFAULT_API_PORT,
        help="TCP port for the HTTP API",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    store = TopicStore()

    mqtt_client = CCGXMQTTClient(
        host=args.host,
        port=args.mqtt_port,
        on_value=store.update,
    )

    try:
        mqtt_client.connect()
    except OSError as exc:
        logger.error(
            "Cannot connect to CCGX at %s:%d: %s", args.host, args.mqtt_port, exc
        )
        sys.exit(1)

    http_server = ThreadingHTTPServer(
        (args.listen_address, args.api_port), _make_handler(store)
    )
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    logger.info(
        "API available at http://%s:%d/values", args.listen_address, args.api_port
    )

    stop_event = threading.Event()

    def _shutdown(signum, frame):
        logger.info("Shutting down…")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    stop_event.wait()
    http_server.shutdown()
    mqtt_client.disconnect()
    logger.info("API server stopped.")


if __name__ == "__main__":
    main()
