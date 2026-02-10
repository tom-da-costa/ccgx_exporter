"""
MQTT client for the Victron CCGX.

Topic format:  N/<portalId>/<service>/<deviceInstance>/<dbuspath>
Keepalive:     publish empty payload to R/<portalId>/keepalive every 30 s
               (must arrive within 55 s or CCGX stops republishing values)

Payload format: {"value": <number|null|string>}
"""

import json
import logging
import threading
from typing import Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# Seconds between keepalive publishes (must be < 55 s per Victron docs)
KEEPALIVE_INTERVAL = 30


class CCGXMQTTClient:
    def __init__(
        self,
        host: str,
        port: int,
        on_value: Callable[[str, str, str, str, float], None],
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        host                : IP / hostname of the CCGX
        port                : MQTT port (default 1883)
        on_value            : callback(portal_id, service, instance, suffix, value)
                              called for every numeric message received
        on_connection_change: callback(connected) called when MQTT state changes
        """
        self._host = host
        self._port = port
        self._on_value = on_value
        self._on_connection_change = on_connection_change

        self._portal_ids: set[str] = set()
        self._keepalive_timer: threading.Timer | None = None

        self._client = mqtt.Client(
            client_id="ccgx_exporter",
            clean_session=True,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect and start the background network loop."""
        logger.info("Connecting to CCGX at %s:%d", self._host, self._port)
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def disconnect(self) -> None:
        """Stop the keepalive timer and disconnect cleanly."""
        self._cancel_keepalive()
        self._client.loop_stop()
        self._client.disconnect()

    # ------------------------------------------------------------------
    # MQTT callbacks (run in the paho network thread)
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            logger.error("MQTT connection refused (rc=%d)", rc)
            return
        logger.info("Connected to CCGX at %s:%d", self._host, self._port)
        client.subscribe("N/#")
        self._schedule_keepalive()
        if self._on_connection_change:
            self._on_connection_change(True)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._cancel_keepalive()
        if self._on_connection_change:
            self._on_connection_change(False)
        if rc != 0:
            logger.warning(
                "Unexpected MQTT disconnect (rc=%d), will auto-reconnect", rc
            )

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        topic: str = msg.topic
        parts = topic.split("/")

        # Expected: N / <portalId> / <service> / <instance> / <path...>
        if len(parts) < 5 or parts[0] != "N":
            return

        portal_id = parts[1]
        service = parts[2]
        instance = parts[3]
        suffix = "/".join(parts[4:])

        # Track portal IDs so we can send targeted keepalives
        if portal_id not in self._portal_ids:
            logger.info("Discovered portal ID: %s", portal_id)
            self._portal_ids.add(portal_id)

        value = self._parse_value(msg.payload)
        if value is None:
            return

        self._on_value(portal_id, service, instance, suffix, value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_value(payload: bytes) -> float | None:
        """Return the numeric value from a Victron JSON payload, or None."""
        try:
            data = json.loads(payload.decode("utf-8"))
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        raw = data.get("value")
        if raw is None:
            return None

        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _send_keepalive(self) -> None:
        for portal_id in list(self._portal_ids):
            topic = f"R/{portal_id}/keepalive"
            self._client.publish(topic, payload="", qos=0, retain=False)
            logger.debug("Sent keepalive for portal %s", portal_id)
        self._schedule_keepalive()

    def _schedule_keepalive(self) -> None:
        self._cancel_keepalive()
        self._keepalive_timer = threading.Timer(
            KEEPALIVE_INTERVAL, self._send_keepalive
        )
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def _cancel_keepalive(self) -> None:
        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None
