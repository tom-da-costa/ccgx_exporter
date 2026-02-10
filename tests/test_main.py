"""Tests for main.py — parse_args and main()."""

import logging
import threading
from unittest.mock import MagicMock, patch

import pytest

from main import (
    DEFAULT_CCGX_HOST,
    DEFAULT_LISTEN_ADDR,
    DEFAULT_METRICS_PORT,
    DEFAULT_MQTT_PORT,
    main,
    parse_args,
)


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.host == DEFAULT_CCGX_HOST
        assert args.mqtt_port == DEFAULT_MQTT_PORT
        assert args.metrics_port == DEFAULT_METRICS_PORT
        assert args.listen_address == DEFAULT_LISTEN_ADDR
        assert args.prefix == "victron_"
        assert args.debug is False

    def test_custom_host(self):
        args = parse_args(["--host", "10.0.0.1"])
        assert args.host == "10.0.0.1"

    def test_custom_mqtt_port(self):
        args = parse_args(["--mqtt-port", "1884"])
        assert args.mqtt_port == 1884

    def test_custom_metrics_port(self):
        args = parse_args(["--metrics-port", "9999"])
        assert args.metrics_port == 9999

    def test_custom_listen_address(self):
        args = parse_args(["--listen-address", "127.0.0.1"])
        assert args.listen_address == "127.0.0.1"

    def test_custom_prefix(self):
        args = parse_args(["--prefix", "myccgx_"])
        assert args.prefix == "myccgx_"

    def test_debug_flag(self):
        args = parse_args(["--debug"])
        assert args.debug is True


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def _run_main(self, extra_args=None):
        """Run main() with all network calls patched, returns mocks."""
        args = ["--host", "1.2.3.4"] + (extra_args or [])

        real_event = threading.Event()
        real_event.set()  # unblocks wait() immediately

        with (
            patch("main.CCGXMQTTClient") as mock_mqtt_cls,
            patch("main.start_http_server") as mock_http,
            patch("main.signal.signal"),
            patch("main.threading.Event", return_value=real_event),
        ):
            mock_mqtt = MagicMock()
            mock_mqtt_cls.return_value = mock_mqtt
            main(args)

        return mock_mqtt_cls, mock_mqtt, mock_http

    def test_mqtt_client_created_with_host(self):
        mock_mqtt_cls, _, _ = self._run_main(["--host", "10.0.0.5"])
        assert mock_mqtt_cls.call_args.kwargs["host"] == "10.0.0.5"

    def test_mqtt_client_created_with_port(self):
        mock_mqtt_cls, _, _ = self._run_main(["--mqtt-port", "1884"])
        assert mock_mqtt_cls.call_args.kwargs["port"] == 1884

    def test_mqtt_client_connected(self):
        _, mock_mqtt, _ = self._run_main()
        mock_mqtt.connect.assert_called_once()

    def test_mqtt_client_disconnected_on_shutdown(self):
        _, mock_mqtt, _ = self._run_main()
        mock_mqtt.disconnect.assert_called_once()

    def test_http_server_started(self):
        _, _, mock_http = self._run_main()
        mock_http.assert_called_once()

    def test_http_server_uses_metrics_port(self):
        _, _, mock_http = self._run_main(["--metrics-port", "9999"])
        port_arg = mock_http.call_args.args[0]
        assert port_arg == 9999

    def test_http_server_uses_listen_address(self):
        _, _, mock_http = self._run_main(["--listen-address", "127.0.0.1"])
        addr_kwarg = mock_http.call_args.kwargs["addr"]
        assert addr_kwarg == "127.0.0.1"

    def test_collector_prefix_passed(self):
        real_event = threading.Event()
        real_event.set()

        with (
            patch("main.CCGXMQTTClient"),
            patch("main.start_http_server"),
            patch("main.signal.signal"),
            patch("main.threading.Event", return_value=real_event),
            patch("main.CCGXCollector") as mock_collector_cls,
        ):
            mock_collector_cls.return_value = MagicMock()
            main(["--host", "1.2.3.4", "--prefix", "custom_"])

        mock_collector_cls.assert_called_once_with(prefix="custom_")

    def test_connect_failure_exits(self):
        with (
            patch("main.CCGXMQTTClient") as mock_mqtt_cls,
            patch("main.start_http_server"),
            patch("main.signal.signal"),
        ):
            mock_mqtt_cls.return_value.connect.side_effect = OSError("refused")
            with pytest.raises(SystemExit) as exc_info:
                main(["--host", "1.2.3.4"])
            assert exc_info.value.code == 1

    def test_debug_flag_sets_log_level(self):
        real_event = threading.Event()
        real_event.set()

        with (
            patch("main.CCGXMQTTClient"),
            patch("main.start_http_server"),
            patch("main.signal.signal"),
            patch("main.threading.Event", return_value=real_event),
            patch("main.logging.getLogger") as mock_get_logger,
        ):
            mock_root = MagicMock()
            mock_get_logger.return_value = mock_root
            main(["--host", "1.2.3.4", "--debug"])

        mock_root.setLevel.assert_called_with(logging.DEBUG)
