"""Tests for metrics.py — TOPIC_MAP and MetricDef."""

import pytest

from metrics import TOPIC_MAP, MetricDef, alarm, gauge, phase_alarm


# ---------------------------------------------------------------------------
# MetricDef helpers
# ---------------------------------------------------------------------------


class TestGaugeHelper:
    def test_type_is_gauge(self):
        m = gauge("my_metric", "help text")
        assert m.metric_type == "gauge"

    def test_name_and_help(self):
        m = gauge("my_metric", "help text")
        assert m.name == "my_metric"
        assert m.help == "help text"

    def test_no_labels_by_default(self):
        m = gauge("my_metric", "")
        assert m.fixed_labels == ()

    def test_labels_are_sorted(self):
        m = gauge("my_metric", "", phase="1", relay="0")
        keys = [k for k, _ in m.fixed_labels]
        assert keys == sorted(keys)

    def test_label_values(self):
        m = gauge("my_metric", "", phase="2")
        assert dict(m.fixed_labels) == {"phase": "2"}


class TestAlarmHelper:
    def test_metric_name_is_alarm(self):
        m = alarm("LowBattery")
        assert m.name == "alarm"

    def test_type_is_gauge(self):
        m = alarm("LowBattery")
        assert m.metric_type == "gauge"

    def test_alarm_label_set(self):
        m = alarm("LowBattery")
        labels = dict(m.fixed_labels)
        assert labels["alarm"] == "LowBattery"

    def test_phase_label_empty_string(self):
        """alarm() must include phase='' for label-set consistency with phase_alarm."""
        m = alarm("LowBattery")
        labels = dict(m.fixed_labels)
        assert "phase" in labels
        assert labels["phase"] == ""


class TestPhaseAlarmHelper:
    def test_metric_name_is_alarm(self):
        m = phase_alarm("1", "Overload")
        assert m.name == "alarm"

    def test_alarm_and_phase_labels(self):
        m = phase_alarm("2", "HighTemperature")
        labels = dict(m.fixed_labels)
        assert labels["alarm"] == "HighTemperature"
        assert labels["phase"] == "2"

    def test_same_label_keys_as_alarm(self):
        """phase_alarm and alarm must have identical label key sets."""
        m_alarm = alarm("LowBattery")
        m_phase = phase_alarm("1", "Overload")
        assert {k for k, _ in m_alarm.fixed_labels} == {
            k for k, _ in m_phase.fixed_labels
        }


# ---------------------------------------------------------------------------
# TOPIC_MAP contents
# ---------------------------------------------------------------------------


class TestTopicMap:
    def test_map_is_not_empty(self):
        assert len(TOPIC_MAP) > 0

    def test_all_values_are_metric_def(self):
        for key, value in TOPIC_MAP.items():
            assert isinstance(value, MetricDef), f"{key} is not a MetricDef"

    def test_all_metric_types_valid(self):
        valid = {"gauge", "counter"}
        for key, mdef in TOPIC_MAP.items():
            assert mdef.metric_type in valid, (
                f"{key} has invalid type {mdef.metric_type!r}"
            )

    def test_all_names_are_snake_case(self):
        import re

        pattern = re.compile(r"^[a-z][a-z0-9_]*$")
        for key, mdef in TOPIC_MAP.items():
            assert pattern.match(mdef.name), (
                f"{key!r} -> metric name {mdef.name!r} is not snake_case"
            )

    def test_fixed_labels_are_sorted(self):
        for key, mdef in TOPIC_MAP.items():
            keys = [k for k, _ in mdef.fixed_labels]
            assert keys == sorted(keys), (
                f"{key!r}: fixed_labels keys are not sorted: {keys}"
            )

    # Spot-checks for well-known topics
    @pytest.mark.parametrize(
        "suffix, expected_name, expected_type",
        [
            ("Dc/Battery/Voltage", "dc_battery_voltage_volts", "gauge"),
            ("Dc/Battery/Soc", "dc_battery_state_of_charge", "gauge"),
            ("Dc/Battery/Current", "dc_battery_current", "gauge"),
            ("Dc/Battery/Power", "dc_battery_power_watts", "gauge"),
            ("Dc/Battery/TimeToGo", "dc_battery_time_to_go_seconds", "gauge"),
            ("Dc/Pv/Power", "dc_pv_power_watts", "gauge"),
            ("Timers/TimeOnGrid", "time_on_grid_seconds_total", "counter"),
            ("Timers/TimeOnInverter", "time_on_inverter_seconds_total", "counter"),
            ("Timers/TimeOnGenerator", "time_on_generator_seconds_total", "counter"),
            ("Timers/TimeOff", "time_off_seconds_total", "counter"),
            ("Yield/Power", "yield_power_watts", "gauge"),
            ("Soc", "state_of_charge", "gauge"),
        ],
    )
    def test_known_topic(self, suffix, expected_name, expected_type):
        assert suffix in TOPIC_MAP, f"{suffix!r} not in TOPIC_MAP"
        mdef = TOPIC_MAP[suffix]
        assert mdef.name == expected_name
        assert mdef.metric_type == expected_type

    @pytest.mark.parametrize(
        "suffix, expected_phase",
        [
            ("Ac/Consumption/L1/Power", "1"),
            ("Ac/Consumption/L2/Power", "2"),
            ("Ac/Consumption/L3/Power", "3"),
            ("Ac/Out/L1/V", "1"),
            ("Ac/L2/Power", "2"),
            ("Ac/L3/Voltage", "3"),
        ],
    )
    def test_phase_label_value(self, suffix, expected_phase):
        mdef = TOPIC_MAP[suffix]
        labels = dict(mdef.fixed_labels)
        assert labels.get("phase") == expected_phase

    def test_relay_0_label(self):
        labels = dict(TOPIC_MAP["Relay/0/State"].fixed_labels)
        assert labels["relay"] == "0"

    def test_relay_1_label(self):
        labels = dict(TOPIC_MAP["Relay/1/State"].fixed_labels)
        assert labels["relay"] == "1"

    def test_dc_n_label(self):
        labels = dict(TOPIC_MAP["Dc/0/Voltage"].fixed_labels)
        assert labels["n"] == "0"

    def test_diagnostics_error_label(self):
        labels = dict(TOPIC_MAP["Diagnostics/LastErrors/3/Error"].fixed_labels)
        assert labels["e"] == "3"

    def test_metrics_sharing_name_have_same_label_keys(self):
        """All entries sharing a metric name must have identical label key sets."""
        name_to_label_keys: dict[str, set] = {}
        for suffix, mdef in TOPIC_MAP.items():
            keys = frozenset(k for k, _ in mdef.fixed_labels)
            if mdef.name not in name_to_label_keys:
                name_to_label_keys[mdef.name] = keys
            else:
                assert name_to_label_keys[mdef.name] == keys, (
                    f"Metric {mdef.name!r} has inconsistent label keys at {suffix!r}"
                )
