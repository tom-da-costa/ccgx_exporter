"""
CCGX Prometheus Exporter
========================
Subscribes to the Victron CCGX MQTT broker and exposes metrics for Prometheus.

Usage
-----
    python main.py --host 192.168.1.210
    python main.py --host 192.168.1.210 --mqtt-port 1883 --metrics-port 9877

Metrics are available at http://0.0.0.0:<metrics-port>/metrics
"""

import argparse
import logging
import signal
import sys

from prometheus_client import start_http_server
from prometheus_client.core import CollectorRegistry

from collector import CCGXCollector
from mqtt_client import CCGXMQTTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_CCGX_HOST = "192.168.1.210"
DEFAULT_MQTT_PORT = 1883
DEFAULT_METRICS_PORT = 9877
DEFAULT_LISTEN_ADDR = "0.0.0.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prometheus exporter for the Victron Color Control GX (CCGX)",
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
        help="Address to bind the metrics HTTP server to",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=DEFAULT_METRICS_PORT,
        help="TCP port to expose Prometheus metrics on",
    )
    parser.add_argument(
        "--prefix",
        default="victron_",
        help="Prefix for all Prometheus metric names",
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

    # Use a dedicated registry so the default Go-style process metrics
    # (gc, memory, …) are not included.
    registry = CollectorRegistry()
    collector = CCGXCollector(prefix=args.prefix)
    registry.register(collector)

    mqtt_client = CCGXMQTTClient(
        host=args.host,
        port=args.mqtt_port,
        on_value=collector.update,
    )

    # Start the Prometheus HTTP server
    start_http_server(args.metrics_port, addr=args.listen_address, registry=registry)
    logger.info(
        "Metrics available at http://%s:%d/metrics",
        args.listen_address,
        args.metrics_port,
    )

    # Connect to CCGX
    try:
        mqtt_client.connect()
    except OSError as exc:
        logger.error(
            "Cannot connect to CCGX at %s:%d: %s", args.host, args.mqtt_port, exc
        )
        sys.exit(1)

    # Block until SIGINT / SIGTERM
    stop_event = __import__("threading").Event()

    def _shutdown(signum, frame):
        logger.info("Shutting down…")
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    stop_event.wait()
    mqtt_client.disconnect()
    logger.info("Exporter stopped.")


if __name__ == "__main__":
    main()
