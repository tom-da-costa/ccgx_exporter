"""Tests for mqtt_client.py — CCGXMQTTClient."""

import json
from unittest.mock import MagicMock, patch

import pytest

from mqtt_client import KEEPALIVE_INTERVAL, CCGXMQTTClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_client(on_value=None):
    """Return a CCGXMQTTClient with a mocked paho client and a capture callback."""
    received = []
    if on_value is None:

        def on_value(*args):
            received.append(args)

    with patch("mqtt_client.mqtt.Client") as mock_mqtt_cls:
        mock_paho = MagicMock()
        mock_mqtt_cls.return_value = mock_paho
        client = CCGXMQTTClient(host="1.2.3.4", port=1883, on_value=on_value)
        client._paho = mock_paho  # expose for assertions
    return client, received


def make_message(topic: str, payload: dict | None) -> MagicMock:
    msg = MagicMock()
    msg.topic = topic
    msg.payload = json.dumps(payload).encode() if payload is not None else b""
    return msg


# ---------------------------------------------------------------------------
# _parse_value
# ---------------------------------------------------------------------------


class TestParseValue:
    @pytest.mark.parametrize(
        "payload, expected",
        [
            (b'{"value": 24.7}', 24.7),
            (b'{"value": 0}', 0.0),
            (b'{"value": -12.5}', -12.5),
            (b'{"value": 100}', 100.0),
            # Integer encoded as string
            (b'{"value": "42"}', 42.0),
        ],
    )
    def test_valid_numeric(self, payload, expected):
        assert CCGXMQTTClient._parse_value(payload) == pytest.approx(expected)

    def test_null_value_returns_nan(self):
        import math

        result = CCGXMQTTClient._parse_value(b'{"value": null}')
        assert result is not None
        assert math.isnan(result)

    @pytest.mark.parametrize(
        "payload",
        [
            b'{"value": "not_a_number"}',
            b'{"other_key": 1}',
            b"not json at all",
            b"",
            b"[]",
            b'{"value": [1, 2]}',
        ],
    )
    def test_invalid_returns_none(self, payload):
        assert CCGXMQTTClient._parse_value(payload) is None


# ---------------------------------------------------------------------------
# _on_message — topic parsing
# ---------------------------------------------------------------------------


class TestOnMessage:
    def _make_client_with_spy(self):
        received = []
        client = CCGXMQTTClient(
            host="1.2.3.4",
            port=1883,
            on_value=lambda *a: received.append(a),
        )
        # Prevent real timer from firing
        client._schedule_keepalive = MagicMock()
        return client, received

    def test_valid_topic_dispatches_callback(self):
        client, received = self._make_client_with_spy()
        msg = make_message("N/abc/system/0/Dc/Battery/Voltage", {"value": 24.7})
        client._on_message(None, None, msg)
        assert len(received) == 1
        assert received[0] == ("abc", "system", "0", "Dc/Battery/Voltage", 24.7)

    def test_multi_segment_suffix(self):
        client, received = self._make_client_with_spy()
        msg = make_message("N/abc/vebus/257/Ac/Out/L1/P", {"value": 1500.0})
        client._on_message(None, None, msg)
        assert received[0][3] == "Ac/Out/L1/P"

    def test_non_N_prefix_ignored(self):
        client, received = self._make_client_with_spy()
        msg = make_message("W/abc/system/0/Dc/Battery/Voltage", {"value": 24.7})
        client._on_message(None, None, msg)
        assert received == []

    def test_too_short_topic_ignored(self):
        client, received = self._make_client_with_spy()
        msg = make_message("N/abc/system/0", {"value": 1.0})
        client._on_message(None, None, msg)
        assert received == []

    def test_null_value_dispatched_as_nan(self):
        import math

        client, received = self._make_client_with_spy()
        msg = make_message("N/abc/system/0/Dc/Battery/Voltage", {"value": None})
        client._on_message(None, None, msg)
        assert len(received) == 1
        assert received[0][:4] == ("abc", "system", "0", "Dc/Battery/Voltage")
        assert math.isnan(received[0][4])

    def test_portal_id_registered_on_first_message(self):
        client, _ = self._make_client_with_spy()
        assert "abc" not in client._portal_ids
        msg = make_message("N/abc/system/0/Dc/Battery/Voltage", {"value": 1.0})
        client._on_message(None, None, msg)
        assert "abc" in client._portal_ids

    def test_portal_id_registered_only_once(self):
        client, _ = self._make_client_with_spy()
        msg = make_message("N/abc/system/0/Dc/Battery/Voltage", {"value": 1.0})
        client._on_message(None, None, msg)
        client._on_message(None, None, msg)
        assert len(client._portal_ids) == 1

    def test_multiple_portals_tracked(self):
        client, _ = self._make_client_with_spy()
        for portal in ("p1", "p2", "p3"):
            msg = make_message(
                f"N/{portal}/system/0/Dc/Battery/Voltage", {"value": 1.0}
            )
            client._on_message(None, None, msg)
        assert client._portal_ids == {"p1", "p2", "p3"}


# ---------------------------------------------------------------------------
# _on_connect
# ---------------------------------------------------------------------------


class TestOnConnect:
    def test_subscribes_on_success(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        mock_paho = MagicMock()
        client._schedule_keepalive = MagicMock()
        client._on_connect(mock_paho, None, None, rc=0)
        mock_paho.subscribe.assert_called_once_with("N/#")

    def test_schedules_keepalive_on_success(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        client._schedule_keepalive = MagicMock()
        client._on_connect(MagicMock(), None, None, rc=0)
        client._schedule_keepalive.assert_called_once()

    def test_does_not_subscribe_on_failure(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        mock_paho = MagicMock()
        client._on_connect(mock_paho, None, None, rc=1)
        mock_paho.subscribe.assert_not_called()

    def test_calls_on_connection_change_true_on_success(self):
        cb = MagicMock()
        client = CCGXMQTTClient(
            host="h", port=1883, on_value=MagicMock(), on_connection_change=cb
        )
        client._schedule_keepalive = MagicMock()
        client._on_connect(MagicMock(), None, None, rc=0)
        cb.assert_called_once_with(True)

    def test_does_not_call_on_connection_change_on_failure(self):
        cb = MagicMock()
        client = CCGXMQTTClient(
            host="h", port=1883, on_value=MagicMock(), on_connection_change=cb
        )
        client._on_connect(MagicMock(), None, None, rc=1)
        cb.assert_not_called()


# ---------------------------------------------------------------------------
# _on_disconnect
# ---------------------------------------------------------------------------


class TestOnDisconnect:
    def test_cancels_keepalive_on_disconnect(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        client._cancel_keepalive = MagicMock()
        client._on_disconnect(None, None, rc=0)
        client._cancel_keepalive.assert_called_once()

    def test_cancels_keepalive_on_unexpected_disconnect(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        client._cancel_keepalive = MagicMock()
        client._on_disconnect(None, None, rc=1)
        client._cancel_keepalive.assert_called_once()

    def test_calls_on_connection_change_false(self):
        cb = MagicMock()
        client = CCGXMQTTClient(
            host="h", port=1883, on_value=MagicMock(), on_connection_change=cb
        )
        client._cancel_keepalive = MagicMock()
        client._on_disconnect(None, None, rc=0)
        cb.assert_called_once_with(False)


# ---------------------------------------------------------------------------
# Keepalive
# ---------------------------------------------------------------------------


class TestKeepalive:
    def test_send_keepalive_publishes_for_each_portal(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        client._portal_ids = {"p1", "p2"}
        client._schedule_keepalive = MagicMock()
        mock_paho = MagicMock()
        client._client = mock_paho

        client._send_keepalive()

        published_topics = {c.args[0] for c in mock_paho.publish.call_args_list}
        assert published_topics == {"R/p1/keepalive", "R/p2/keepalive"}

    def test_send_keepalive_reschedules(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        client._portal_ids = set()
        client._schedule_keepalive = MagicMock()
        client._send_keepalive()
        client._schedule_keepalive.assert_called_once()

    def test_cancel_keepalive_cancels_timer(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        mock_timer = MagicMock()
        client._keepalive_timer = mock_timer
        client._cancel_keepalive()
        mock_timer.cancel.assert_called_once()
        assert client._keepalive_timer is None

    def test_cancel_keepalive_noop_when_no_timer(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        assert client._keepalive_timer is None
        client._cancel_keepalive()  # must not raise

    def test_schedule_keepalive_creates_timer(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        client._cancel_keepalive = MagicMock()
        with patch("mqtt_client.threading.Timer") as mock_timer_cls:
            mock_timer = MagicMock()
            mock_timer_cls.return_value = mock_timer
            client._schedule_keepalive()
            mock_timer_cls.assert_called_once_with(
                KEEPALIVE_INTERVAL, client._send_keepalive
            )
            mock_timer.start.assert_called_once()

    def test_schedule_keepalive_cancels_existing_first(self):
        client = CCGXMQTTClient(host="h", port=1883, on_value=MagicMock())
        existing = MagicMock()
        client._keepalive_timer = existing
        with patch("mqtt_client.threading.Timer", return_value=MagicMock()):
            client._schedule_keepalive()
        existing.cancel.assert_called_once()
