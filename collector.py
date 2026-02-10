"""
Custom Prometheus collector for CCGX metrics.

Stores the latest value for every (portal_id, component_type, component_id, path_suffix)
tuple seen over MQTT, and exposes them on /metrics scrape.
"""

import threading
import time
from typing import Iterator

from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    Metric,
)

from metrics import TOPIC_MAP, MetricDef


class CCGXCollector:
    def __init__(
        self, prefix: str = "victron_", client_id: str = "ccgx_exporter"
    ) -> None:
        self._prefix = prefix if prefix.endswith("_") else prefix + "_"
        self._client_id = client_id
        self._lock = threading.Lock()
        # key: (portal_id, component_type, component_id, suffix)
        # value: (numeric_value, MetricDef)
        self._values: dict[tuple[str, str, str, str], tuple[float, MetricDef]] = {}

        # Internal MQTT metrics
        self._update_count: int = 0
        self._connected: bool = False
        self._connected_since: float = 0.0

    # ------------------------------------------------------------------
    # Called from the MQTT thread
    # ------------------------------------------------------------------

    def update(
        self,
        portal_id: str,
        service: str,
        instance: str,
        suffix: str,
        value: float,
    ) -> None:
        mdef = TOPIC_MAP.get(suffix)
        if mdef is None:
            return
        with self._lock:
            self._values[(portal_id, service, instance, suffix)] = (value, mdef)
            self._update_count += 1

    def set_connection_state(self, connected: bool) -> None:
        with self._lock:
            self._connected = connected
            self._connected_since = time.time()

    # ------------------------------------------------------------------
    # Called from the HTTP / Prometheus scrape thread
    # ------------------------------------------------------------------

    def collect(self) -> Iterator[Metric]:
        with self._lock:
            snapshot = dict(self._values)
            update_count = self._update_count
            connected = self._connected
            connected_since = self._connected_since

        # families[(metric_name, metric_type, label_names_tuple)]
        #   -> {"help": str, "samples": [(label_values_tuple, float)]}
        families: dict[tuple, dict] = {}

        for (portal_id, component_type, component_id, suffix), (
            value,
            mdef,
        ) in snapshot.items():
            fixed = dict(mdef.fixed_labels)
            all_labels: dict[str, str] = {
                "portal_id": portal_id,
                "component_type": component_type,
                "component_id": component_id,
                **fixed,
            }
            label_names = tuple(sorted(all_labels.keys()))
            key = (mdef.name, mdef.metric_type, label_names)

            if key not in families:
                families[key] = {"help": mdef.help, "samples": []}

            label_values = tuple(all_labels[k] for k in label_names)
            families[key]["samples"].append((label_values, value))

        for (name, mtype, label_names), info in families.items():
            full_name = self._prefix + name
            labels = list(label_names)
            if mtype == "counter":
                fam: Metric = CounterMetricFamily(
                    full_name, info["help"], labels=labels
                )
            else:
                fam = GaugeMetricFamily(full_name, info["help"], labels=labels)

            for label_values, value in info["samples"]:
                fam.add_metric(list(label_values), value)

            yield fam

        # Internal MQTT metrics
        client_labels = ["client_id"]
        client_values = [self._client_id]

        conn_fam = GaugeMetricFamily(
            self._prefix + "mqtt_connection_state",
            "0=Disconnected; 1=Connected",
            labels=client_labels,
        )
        conn_fam.add_metric(client_values, float(connected))
        yield conn_fam

        since_fam = GaugeMetricFamily(
            self._prefix + "mqtt_connection_state_since_time_seconds",
            "Time since last change to mqtt_connection_state",
            labels=client_labels,
        )
        since_fam.add_metric(client_values, connected_since)
        yield since_fam

        updates_fam = CounterMetricFamily(
            self._prefix + "mqtt_subscription_updates_total",
            "MQTT subscription updates received",
            labels=client_labels,
        )
        updates_fam.add_metric(client_values, float(update_count))
        yield updates_fam
