"""Tests for api_server.py — TopicStore, HTTP handler, parse_args."""

import json
import threading
import time
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from api_server import (
    DEFAULT_API_PORT,
    DEFAULT_CCGX_HOST,
    DEFAULT_CLIENT_ID,
    DEFAULT_LISTEN_ADDR,
    DEFAULT_MQTT_PORT,
    ESS_MIN_SOC_PATH,
    TopicStore,
    _make_handler,
    main,
    parse_args,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_store(*entries: tuple) -> TopicStore:
    """Build a TopicStore pre-populated with (portal, service, instance, suffix, value)."""
    store = TopicStore()
    for portal_id, service, instance, suffix, value in entries:
        store.update(portal_id, service, instance, suffix, value)
    return store


class FakeHTTPRequest:
    """Minimal fake to drive BaseHTTPRequestHandler without a real socket."""

    def __init__(self, path: str, body: bytes = b""):
        self.path = path
        self._body = body
        self._response_status: int | None = None
        self._response_headers: dict[str, str] = {}
        self._response_body: bytes = b""
        self._wfile = BytesIO()

    def _build_handler(self, store: TopicStore, mqtt_client=None):
        Handler = _make_handler(store, mqtt_client)

        handler = Handler.__new__(Handler)
        handler.path = self.path
        handler.wfile = self._wfile
        handler.rfile = BytesIO(self._body)

        # Fake headers providing Content-Length
        fake_headers = {"Content-Length": str(len(self._body))}
        handler.headers = fake_headers

        # Capture send_response / send_header / end_headers calls
        def send_response(status, message=None):
            self._response_status = status

        def send_header(key, value):
            self._response_headers[key] = value

        def end_headers():
            pass

        handler.send_response = send_response
        handler.send_header = send_header
        handler.end_headers = end_headers

        return handler

    def get(self, store: TopicStore) -> tuple[int, dict, dict | list]:
        handler = self._build_handler(store)
        handler.do_GET()
        body = json.loads(self._wfile.getvalue())
        return self._response_status, self._response_headers, body

    def post(
        self, store: TopicStore, mqtt_client=None
    ) -> tuple[int, dict, dict | list]:
        handler = self._build_handler(store, mqtt_client)
        handler.do_POST()
        body = json.loads(self._wfile.getvalue())
        return self._response_status, self._response_headers, body


def get(path: str, store: TopicStore) -> tuple[int, dict, dict | list]:
    return FakeHTTPRequest(path).get(store)


def post(
    path: str,
    body: dict,
    store: TopicStore,
    mqtt_client=None,
) -> tuple[int, dict, dict | list]:
    encoded = json.dumps(body).encode("utf-8")
    return FakeHTTPRequest(path, encoded).post(store, mqtt_client)


# ---------------------------------------------------------------------------
# TopicStore.update
# ---------------------------------------------------------------------------


class TestTopicStoreUpdate:
    def test_entry_stored(self):
        store = TopicStore()
        store.update("p", "system", "0", "Dc/Battery/Voltage", 24.7)
        assert len(store.all()) == 1

    def test_entry_fields(self):
        store = TopicStore()
        before = time.time()
        store.update("p1", "vebus", "257", "Ac/Out/L1/P", 1500.0)
        after = time.time()
        entries = store.all()
        e = entries[0]
        assert e.portal_id == "p1"
        assert e.service == "vebus"
        assert e.instance == "257"
        assert e.suffix == "Ac/Out/L1/P"
        assert e.value == 1500.0
        assert before <= e.updated_at <= after

    def test_value_overwritten(self):
        store = TopicStore()
        store.update("p", "system", "0", "Dc/Battery/Soc", 80.0)
        store.update("p", "system", "0", "Dc/Battery/Soc", 90.0)
        assert len(store.all()) == 1
        assert store.all()[0].value == 90.0

    def test_different_portals_coexist(self):
        store = make_store(
            ("p1", "system", "0", "Dc/Battery/Soc", 80.0),
            ("p2", "system", "0", "Dc/Battery/Soc", 60.0),
        )
        assert len(store.all()) == 2

    def test_different_suffixes_coexist(self):
        store = make_store(
            ("p", "system", "0", "Dc/Battery/Voltage", 24.0),
            ("p", "system", "0", "Dc/Battery/Soc", 85.0),
        )
        assert len(store.all()) == 2


# ---------------------------------------------------------------------------
# TopicStore.get
# ---------------------------------------------------------------------------


class TestTopicStoreGet:
    def test_match_single(self):
        store = make_store(("p", "vebus", "257", "Ac/Out/L1/P", 1500.0))
        results = store.get("vebus", "257", "Ac/Out/L1/P")
        assert len(results) == 1
        assert results[0].value == 1500.0

    def test_no_match_returns_empty(self):
        store = make_store(("p", "system", "0", "Dc/Battery/Voltage", 24.0))
        assert store.get("vebus", "257", "Ac/Out/L1/P") == []

    def test_multi_portal_match(self):
        store = make_store(
            ("p1", "system", "0", "Dc/Battery/Soc", 80.0),
            ("p2", "system", "0", "Dc/Battery/Soc", 60.0),
        )
        results = store.get("system", "0", "Dc/Battery/Soc")
        assert len(results) == 2
        assert {r.portal_id for r in results} == {"p1", "p2"}

    def test_does_not_match_wrong_instance(self):
        store = make_store(("p", "solarcharger", "0", "Dc/0/Voltage", 48.0))
        assert store.get("solarcharger", "1", "Dc/0/Voltage") == []

    def test_does_not_match_wrong_service(self):
        store = make_store(("p", "system", "0", "Dc/Battery/Voltage", 24.0))
        assert store.get("vebus", "0", "Dc/Battery/Voltage") == []


# ---------------------------------------------------------------------------
# TopicStore.all
# ---------------------------------------------------------------------------


class TestTopicStoreAll:
    def test_empty(self):
        assert TopicStore().all() == []

    def test_returns_all_entries(self):
        store = make_store(
            ("p", "system", "0", "Dc/Battery/Voltage", 24.0),
            ("p", "system", "0", "Dc/Battery/Soc", 85.0),
            ("p", "vebus", "257", "Ac/Out/L1/P", 1500.0),
        )
        assert len(store.all()) == 3

    def test_returns_copy(self):
        store = make_store(("p", "system", "0", "Dc/Battery/Soc", 85.0))
        first = store.all()
        store.update("p", "system", "0", "Dc/Battery/Voltage", 24.0)
        assert len(first) == 1  # original snapshot unaffected


# ---------------------------------------------------------------------------
# TopicStore.portals
# ---------------------------------------------------------------------------


class TestTopicStorePortals:
    def test_empty_store(self):
        assert TopicStore().portals() == []

    def test_single_portal(self):
        store = make_store(("abc", "system", "0", "Dc/Battery/Soc", 80.0))
        assert store.portals() == ["abc"]

    def test_multiple_portals_sorted(self):
        store = make_store(
            ("zzz", "system", "0", "Dc/Battery/Soc", 80.0),
            ("aaa", "system", "0", "Dc/Battery/Soc", 60.0),
            ("mmm", "system", "0", "Dc/Battery/Voltage", 24.0),
        )
        assert store.portals() == ["aaa", "mmm", "zzz"]

    def test_deduplicates_portals(self):
        store = make_store(
            ("p1", "system", "0", "Dc/Battery/Voltage", 24.0),
            ("p1", "system", "0", "Dc/Battery/Soc", 80.0),
        )
        assert store.portals() == ["p1"]


# ---------------------------------------------------------------------------
# TopicStore — thread safety
# ---------------------------------------------------------------------------


class TestTopicStoreThreadSafety:
    def test_concurrent_updates_do_not_crash(self):
        store = TopicStore()
        errors = []

        def writer():
            try:
                for i in range(200):
                    store.update("p", "system", "0", "Dc/Battery/Soc", float(i))
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(200):
                    store.all()
                    store.portals()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []


# ---------------------------------------------------------------------------
# HTTP handler — GET /portals
# ---------------------------------------------------------------------------


class TestHandlerPortals:
    def test_empty_store(self):
        status, _, body = get("/portals", TopicStore())
        assert status == 200
        assert body == []

    def test_returns_portal_list(self):
        store = make_store(
            ("abc", "system", "0", "Dc/Battery/Soc", 80.0),
            ("xyz", "system", "0", "Dc/Battery/Soc", 60.0),
        )
        status, _, body = get("/portals", store)
        assert status == 200
        assert sorted(body) == ["abc", "xyz"]

    def test_content_type_json(self):
        _, headers, _ = get("/portals", TopicStore())
        assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# HTTP handler — GET /values (list all)
# ---------------------------------------------------------------------------


class TestHandlerValuesList:
    def test_empty_store(self):
        status, _, body = get("/values", TopicStore())
        assert status == 200
        assert body == []

    def test_returns_all_entries(self):
        store = make_store(
            ("p", "system", "0", "Dc/Battery/Voltage", 24.7),
            ("p", "vebus", "257", "Ac/Out/L1/P", 1500.0),
        )
        status, _, body = get("/values", store)
        assert status == 200
        assert len(body) == 2

    def test_entry_structure(self):
        store = make_store(("p", "system", "0", "Dc/Battery/Soc", 85.0))
        _, _, body = get("/values", store)
        entry = body[0]
        assert entry["portal_id"] == "p"
        assert entry["path"] == "system/0/Dc/Battery/Soc"
        assert entry["value"] == 85.0
        assert "updated_at" in entry

    def test_sorted_by_path(self):
        store = make_store(
            ("p", "vebus", "257", "Ac/Out/L1/P", 1.0),
            ("p", "battery", "0", "Soc", 2.0),
            ("p", "system", "0", "Dc/Battery/Voltage", 3.0),
        )
        _, _, body = get("/values", store)
        paths = [e["path"] for e in body]
        assert paths == sorted(paths)

    def test_content_type_json(self):
        _, headers, _ = get("/values", TopicStore())
        assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# HTTP handler — GET /values/<service>/<instance>/<path>
# ---------------------------------------------------------------------------


class TestHandlerValuesSingle:
    def test_existing_topic(self):
        store = make_store(("p", "vebus", "257", "Ac/Out/L1/P", 1500.0))
        status, _, body = get("/values/vebus/257/Ac/Out/L1/P", store)
        assert status == 200
        assert body["portal_id"] == "p"
        assert body["path"] == "vebus/257/Ac/Out/L1/P"
        assert body["value"] == 1500.0
        assert "updated_at" in body

    def test_deep_path(self):
        store = make_store(("p", "system", "0", "Ac/Consumption/L1/Power", 300.0))
        status, _, body = get("/values/system/0/Ac/Consumption/L1/Power", store)
        assert status == 200
        assert body["path"] == "system/0/Ac/Consumption/L1/Power"

    def test_not_found(self):
        status, _, body = get("/values/vebus/257/Ac/Out/L1/P", TopicStore())
        assert status == 404
        assert "error" in body

    def test_multiple_portals_returns_list(self):
        store = make_store(
            ("p1", "system", "0", "Dc/Battery/Soc", 80.0),
            ("p2", "system", "0", "Dc/Battery/Soc", 60.0),
        )
        status, _, body = get("/values/system/0/Dc/Battery/Soc", store)
        assert status == 200
        assert isinstance(body, list)
        assert len(body) == 2
        portal_ids = {e["portal_id"] for e in body}
        assert portal_ids == {"p1", "p2"}

    def test_multiple_portals_entry_structure(self):
        store = make_store(
            ("p1", "system", "0", "Dc/Battery/Soc", 80.0),
            ("p2", "system", "0", "Dc/Battery/Soc", 60.0),
        )
        _, _, body = get("/values/system/0/Dc/Battery/Soc", store)
        for entry in body:
            assert "portal_id" in entry
            assert "path" in entry
            assert "value" in entry
            assert "updated_at" in entry

    def test_content_type_json(self):
        store = make_store(("p", "system", "0", "Dc/Battery/Soc", 85.0))
        _, headers, _ = get("/values/system/0/Dc/Battery/Soc", store)
        assert headers["Content-Type"] == "application/json"


# ---------------------------------------------------------------------------
# HTTP handler — unknown routes
# ---------------------------------------------------------------------------


class TestHandlerUnknownRoutes:
    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/unknown",
            "/values/only_one_part",
            "/values/service/instance",  # path part missing
        ],
    )
    def test_returns_404(self, path):
        status, _, body = get(path, TopicStore())
        assert status == 404
        assert "error" in body


# ---------------------------------------------------------------------------
# HTTP handler — log_message
# ---------------------------------------------------------------------------


class TestHandlerLogMessage:
    def test_log_message_does_not_raise(self):
        Handler = _make_handler(TopicStore())
        handler = Handler.__new__(Handler)
        # Must not raise — exercises the logger.debug path
        handler.log_message("GET %s %s", "/values", "200")


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def _run_main(self, extra_args=None):
        """Run main() with all network calls patched, then trigger shutdown."""
        args = ["--host", "1.2.3.4"] + (extra_args or [])

        with (
            patch("api_server.CCGXMQTTClient") as mock_mqtt_cls,
            patch("api_server.ThreadingHTTPServer") as mock_server_cls,
            patch("api_server.threading.Thread") as mock_thread_cls,
            patch("api_server.signal.signal"),
            patch("sys.argv", ["api_server.py"] + args),
        ):
            mock_mqtt = MagicMock()
            mock_mqtt_cls.return_value = mock_mqtt

            mock_server = MagicMock()
            mock_server_cls.return_value = mock_server

            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            # Patch stop_event.wait() to return immediately
            real_event_cls = threading.Event

            def patched_event():
                ev = real_event_cls()
                ev.set()  # already set → wait() returns immediately
                return ev

            with patch("api_server.threading.Event", side_effect=patched_event):
                main(args)

        return mock_mqtt_cls, mock_mqtt, mock_server_cls, mock_server

    def test_mqtt_client_created_with_host(self):
        mock_mqtt_cls, *_ = self._run_main(["--host", "10.0.0.1"])
        call_kwargs = mock_mqtt_cls.call_args
        assert call_kwargs.kwargs["host"] == "10.0.0.1"

    def test_mqtt_client_connected(self):
        _, mock_mqtt, *_ = self._run_main()
        mock_mqtt.connect.assert_called_once()

    def test_mqtt_client_disconnected_on_shutdown(self):
        _, mock_mqtt, *_ = self._run_main()
        mock_mqtt.disconnect.assert_called_once()

    def test_http_server_created(self):
        *_, mock_server_cls, _ = self._run_main(["--api-port", "5000"])
        assert mock_server_cls.called
        bind_addr = mock_server_cls.call_args.args[0]
        assert bind_addr[1] == 5000

    def test_http_server_shutdown_on_exit(self):
        *_, mock_server = self._run_main()
        mock_server.shutdown.assert_called_once()

    def test_connect_failure_exits(self):
        with (
            patch("api_server.CCGXMQTTClient") as mock_mqtt_cls,
            patch("api_server.ThreadingHTTPServer"),
            patch("api_server.threading.Thread"),
            patch("api_server.signal.signal"),
            patch("sys.argv", ["api_server.py", "--host", "1.2.3.4"]),
        ):
            mock_mqtt_cls.return_value.connect.side_effect = OSError("refused")
            with pytest.raises(SystemExit) as exc_info:
                main([])
            assert exc_info.value.code == 1

    def test_debug_flag_sets_log_level(self):
        import logging

        with patch("logging.getLogger") as mock_get_logger:
            mock_root_logger = MagicMock()
            mock_get_logger.return_value = mock_root_logger
            self._run_main(["--debug"])
            mock_root_logger.setLevel.assert_called_with(logging.DEBUG)


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.host == DEFAULT_CCGX_HOST
        assert args.mqtt_port == DEFAULT_MQTT_PORT
        assert args.api_port == DEFAULT_API_PORT
        assert args.listen_address == DEFAULT_LISTEN_ADDR
        assert args.client_id == DEFAULT_CLIENT_ID
        assert args.debug is False

    def test_custom_host(self):
        args = parse_args(["--host", "10.0.0.1"])
        assert args.host == "10.0.0.1"

    def test_custom_ports(self):
        args = parse_args(["--mqtt-port", "1884", "--api-port", "5000"])
        assert args.mqtt_port == 1884
        assert args.api_port == 5000

    def test_custom_listen_address(self):
        args = parse_args(["--listen-address", "127.0.0.1"])
        assert args.listen_address == "127.0.0.1"

    def test_custom_client_id(self):
        args = parse_args(["--client-id", "my_api"])
        assert args.client_id == "my_api"

    def test_debug_flag(self):
        args = parse_args(["--debug"])
        assert args.debug is True


# ---------------------------------------------------------------------------
# HTTP handler — POST /ess/min-soc
# ---------------------------------------------------------------------------


class TestHandlerEssMinSoc:
    def _mqtt(self):
        from unittest.mock import MagicMock

        return MagicMock()

    def test_sets_value_publishes_to_mqtt(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        mqtt = self._mqtt()
        status, _, body = post("/ess/min-soc", {"value": 20}, store, mqtt)
        assert status == 200
        mqtt.publish_value.assert_called_once_with(
            "p1", "settings", "0", ESS_MIN_SOC_PATH, 20.0
        )

    def test_response_body(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        _, _, body = post("/ess/min-soc", {"value": 35}, store, self._mqtt())
        assert body["portal_id"] == "p1"
        assert body["value"] == 35.0
        assert body["path"] == ESS_MIN_SOC_PATH

    def test_explicit_portal_id(self):
        store = make_store(
            ("p1", "system", "0", "Dc/Battery/Soc", 80.0),
            ("p2", "system", "0", "Dc/Battery/Soc", 60.0),
        )
        mqtt = self._mqtt()
        status, _, body = post(
            "/ess/min-soc", {"value": 10, "portal_id": "p2"}, store, mqtt
        )
        assert status == 200
        mqtt.publish_value.assert_called_once_with(
            "p2", "settings", "0", ESS_MIN_SOC_PATH, 10.0
        )

    def test_multiple_portals_without_portal_id_returns_400(self):
        store = make_store(
            ("p1", "system", "0", "Dc/Battery/Soc", 80.0),
            ("p2", "system", "0", "Dc/Battery/Soc", 60.0),
        )
        status, _, body = post("/ess/min-soc", {"value": 20}, store, self._mqtt())
        assert status == 400
        assert "portal_id" in body["error"]
        assert "portals" in body

    def test_no_portal_known_returns_503(self):
        status, _, body = post(
            "/ess/min-soc", {"value": 20}, TopicStore(), self._mqtt()
        )
        assert status == 503

    def test_missing_value_field_returns_400(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        status, _, body = post("/ess/min-soc", {}, store, self._mqtt())
        assert status == 400
        assert "value" in body["error"]

    def test_value_above_100_returns_400(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        status, _, body = post("/ess/min-soc", {"value": 101}, store, self._mqtt())
        assert status == 400

    def test_value_below_0_returns_400(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        status, _, body = post("/ess/min-soc", {"value": -1}, store, self._mqtt())
        assert status == 400

    def test_non_numeric_value_returns_400(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        status, _, body = post("/ess/min-soc", {"value": "high"}, store, self._mqtt())
        assert status == 400

    def test_invalid_json_returns_400(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        raw = FakeHTTPRequest("/ess/min-soc", b"not-json").post(store, self._mqtt())
        assert raw[0] == 400

    def test_no_mqtt_client_returns_503(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        status, _, body = post("/ess/min-soc", {"value": 20}, store, mqtt_client=None)
        assert status == 503

    def test_unknown_post_route_returns_404(self):
        store = make_store(("p1", "system", "0", "Dc/Battery/Soc", 80.0))
        status, _, body = post("/unknown", {"value": 20}, store, self._mqtt())
        assert status == 404
