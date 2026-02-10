"""Tests for collector.py — CCGXCollector."""

import threading

import pytest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from collector import CCGXCollector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def collect_as_dict(collector: CCGXCollector) -> dict:
    """Return {metric_name: {label_values_tuple: value}} from a collect() pass."""
    result = {}
    for family in collector.collect():
        result[family.name] = {
            tuple(sorted(zip(family.samples[0].labels.keys(), lv)))
            if isinstance(lv, (list, tuple))
            else lv: s.value
            for s in family.samples
            for lv in [tuple(s.labels.values())]
        }
    return result


def samples_by_name(collector: CCGXCollector, metric_name: str):
    """Return all samples for a given full metric name."""
    for family in collector.collect():
        if family.name == metric_name:
            return family.samples
    return []


# ---------------------------------------------------------------------------
# Prefix
# ---------------------------------------------------------------------------


class TestPrefix:
    def test_default_prefix(self):
        c = CCGXCollector()
        assert c._prefix == "victron_"

    def test_custom_prefix(self):
        c = CCGXCollector(prefix="mydev_")
        assert c._prefix == "mydev_"

    def test_prefix_underscore_added_if_missing(self):
        c = CCGXCollector(prefix="mydev")
        assert c._prefix == "mydev_"

    def test_prefix_applied_to_metric_name(self):
        c = CCGXCollector(prefix="foo_")
        c.update("p", "system", "0", "Dc/Battery/Voltage", 24.0)
        names = [f.name for f in c.collect()]
        assert "foo_dc_battery_voltage_volts" in names

    def test_default_prefix_applied_to_metric_name(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Voltage", 24.0)
        names = [f.name for f in c.collect()]
        assert "victron_dc_battery_voltage_volts" in names


# ---------------------------------------------------------------------------
# update()
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_unknown_suffix_is_ignored(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Unknown/Path/That/Does/Not/Exist", 1.0)
        assert list(c.collect()) == []

    def test_known_suffix_is_stored(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Voltage", 25.0)
        assert len(list(c.collect())) == 1

    def test_value_is_overwritten_by_latest(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Voltage", 24.0)
        c.update("p", "system", "0", "Dc/Battery/Voltage", 25.5)
        samples = samples_by_name(c, "victron_dc_battery_voltage_volts")
        assert len(samples) == 1
        assert samples[0].value == 25.5

    def test_different_instances_are_separate_entries(self):
        c = CCGXCollector()
        c.update("p", "solarcharger", "0", "Dc/0/Voltage", 48.0)
        c.update("p", "solarcharger", "1", "Dc/0/Voltage", 24.0)
        samples = samples_by_name(c, "victron_dc_voltage_volts")
        assert len(samples) == 2

    def test_different_portals_are_separate_entries(self):
        c = CCGXCollector()
        c.update("portal1", "system", "0", "Dc/Battery/Soc", 80.0)
        c.update("portal2", "system", "0", "Dc/Battery/Soc", 60.0)
        samples = samples_by_name(c, "victron_dc_battery_state_of_charge")
        assert len(samples) == 2

    def test_multiple_suffixes_produce_multiple_families(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Voltage", 24.0)
        c.update("p", "system", "0", "Dc/Battery/Soc", 85.0)
        families = list(c.collect())
        assert len(families) == 2


# ---------------------------------------------------------------------------
# collect() — labels
# ---------------------------------------------------------------------------


class TestLabels:
    def test_dynamic_labels_present(self):
        c = CCGXCollector()
        c.update("myportal", "system", "0", "Dc/Battery/Voltage", 24.0)
        samples = samples_by_name(c, "victron_dc_battery_voltage_volts")
        labels = samples[0].labels
        assert labels["portal_id"] == "myportal"
        assert labels["service"] == "system"
        assert labels["instance"] == "0"

    def test_fixed_label_phase(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Ac/Consumption/L2/Power", 500.0)
        samples = samples_by_name(c, "victron_ac_consumption_phase_power_watts")
        assert samples[0].labels["phase"] == "2"

    def test_fixed_label_relay(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Relay/1/State", 1.0)
        samples = samples_by_name(c, "victron_relay_state")
        assert samples[0].labels["relay"] == "1"

    def test_fixed_label_n(self):
        c = CCGXCollector()
        c.update("p", "vebus", "257", "Dc/0/Voltage", 48.0)
        samples = samples_by_name(c, "victron_dc_voltage_volts")
        assert samples[0].labels["n"] == "0"

    def test_multi_phase_same_family(self):
        """L1/L2/L3 for the same metric should end up in a single family."""
        c = CCGXCollector()
        c.update("p", "system", "0", "Ac/Consumption/L1/Power", 100.0)
        c.update("p", "system", "0", "Ac/Consumption/L2/Power", 200.0)
        c.update("p", "system", "0", "Ac/Consumption/L3/Power", 300.0)
        families = [f for f in c.collect() if "consumption_phase" in f.name]
        assert len(families) == 1
        assert len(families[0].samples) == 3

    def test_alarm_label_present(self):
        c = CCGXCollector()
        c.update("p", "vebus", "257", "Alarms/LowBattery", 1.0)
        samples = samples_by_name(c, "victron_alarm")
        assert samples[0].labels["alarm"] == "LowBattery"

    def test_phase_alarm_has_phase_label(self):
        c = CCGXCollector()
        c.update("p", "vebus", "257", "Alarms/L1/Overload", 1.0)
        samples = samples_by_name(c, "victron_alarm")
        assert samples[0].labels["alarm"] == "Overload"
        assert samples[0].labels["phase"] == "1"

    def test_alarm_and_phase_alarm_in_same_family(self):
        """alarm() and phase_alarm() must share the same label set."""
        c = CCGXCollector()
        c.update("p", "vebus", "257", "Alarms/LowBattery", 0.0)
        c.update("p", "vebus", "257", "Alarms/L2/Overload", 0.0)
        families = [f for f in c.collect() if f.name == "victron_alarm"]
        assert len(families) == 1
        assert len(families[0].samples) == 2


# ---------------------------------------------------------------------------
# collect() — metric types
# ---------------------------------------------------------------------------


class TestMetricTypes:
    def test_gauge_type(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Voltage", 24.0)
        families = list(c.collect())
        assert any(isinstance(f, GaugeMetricFamily) for f in families)

    def test_counter_type(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Timers/TimeOnGrid", 3600.0)
        families = list(c.collect())
        assert any(isinstance(f, CounterMetricFamily) for f in families)

    def test_counter_metric_name(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Timers/TimeOnInverter", 7200.0)
        names = [f.name for f in c.collect()]
        # prometheus_client strips the _total suffix from CounterMetricFamily.name
        assert "victron_time_on_inverter_seconds" in names


# ---------------------------------------------------------------------------
# collect() — values
# ---------------------------------------------------------------------------


class TestValues:
    def test_integer_value(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Soc", 100.0)
        samples = samples_by_name(c, "victron_dc_battery_state_of_charge")
        assert samples[0].value == 100.0

    def test_float_value(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Voltage", 25.68)
        samples = samples_by_name(c, "victron_dc_battery_voltage_volts")
        assert samples[0].value == pytest.approx(25.68)

    def test_zero_value(self):
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Soc", 0.0)
        samples = samples_by_name(c, "victron_dc_battery_state_of_charge")
        assert samples[0].value == 0.0

    def test_negative_value(self):
        """Battery charging current is negative."""
        c = CCGXCollector()
        c.update("p", "system", "0", "Dc/Battery/Current", -12.5)
        samples = samples_by_name(c, "victron_dc_battery_current")
        assert samples[0].value == pytest.approx(-12.5)

    def test_empty_collector_yields_nothing(self):
        c = CCGXCollector()
        assert list(c.collect()) == []


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_updates_do_not_crash(self):
        c = CCGXCollector()
        errors = []

        def writer():
            try:
                for i in range(200):
                    c.update("p", "system", "0", "Dc/Battery/Voltage", float(i))
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(200):
                    list(c.collect())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        threads += [threading.Thread(target=reader) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def test_concurrent_different_keys(self):
        """Multiple writers on different keys should all be visible after join."""
        c = CCGXCollector()
        suffixes = [
            "Dc/Battery/Voltage",
            "Dc/Battery/Soc",
            "Dc/Battery/Current",
            "Dc/Battery/Power",
        ]

        def writer(suffix, value):
            c.update("p", "system", "0", suffix, value)

        threads = [
            threading.Thread(target=writer, args=(s, float(i)))
            for i, s in enumerate(suffixes)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(list(c.collect())) == len(suffixes)
