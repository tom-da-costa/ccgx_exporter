"""
Custom Prometheus collector for CCGX metrics.

Stores the latest value for every (portal_id, service, instance, path_suffix)
tuple seen over MQTT, and exposes them on /metrics scrape.
"""

import threading
from typing import Iterator

from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    Metric,
)

from metrics import TOPIC_MAP, MetricDef


class CCGXCollector:
    def __init__(self, prefix: str = "victron_") -> None:
        self._prefix = prefix if prefix.endswith("_") else prefix + "_"
        self._lock = threading.Lock()
        # key: (portal_id, service, instance, suffix)
        # value: (numeric_value, MetricDef)
        self._values: dict[tuple[str, str, str, str], tuple[float, MetricDef]] = {}

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

    # ------------------------------------------------------------------
    # Called from the HTTP / Prometheus scrape thread
    # ------------------------------------------------------------------

    def collect(self) -> Iterator[Metric]:
        with self._lock:
            snapshot = dict(self._values)

        # families[(metric_name, metric_type, label_names_tuple)]
        #   -> {"help": str, "samples": [(label_values_tuple, float)]}
        families: dict[tuple, dict] = {}

        for (portal_id, service, instance, suffix), (value, mdef) in snapshot.items():
            fixed = dict(mdef.fixed_labels)
            all_labels: dict[str, str] = {
                "portal_id": portal_id,
                "service": service,
                "instance": instance,
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
