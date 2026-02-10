"""
Mapping between Victron MQTT topic suffixes and Prometheus metric definitions.
Sources: https://github.com/victronenergy/venus/wiki/dbus
         and the Go exporter's topics.go
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDef:
    name: str
    help: str
    metric_type: str  # 'gauge' or 'counter'
    # Immutable sorted tuple of (label_key, label_value) pairs from ConstLabels
    fixed_labels: tuple[tuple[str, str], ...]


def gauge(name: str, help: str, **labels) -> MetricDef:
    return MetricDef(name, help, "gauge", tuple(sorted(labels.items())))


def counter(name: str, help: str, **labels) -> MetricDef:
    return MetricDef(name, help, "counter", tuple(sorted(labels.items())))


def alarm(alarm_name: str) -> MetricDef:
    return MetricDef(
        "alarm", "0=OK; 1=Warning; 2=Alarm", "gauge", (("alarm", alarm_name),)
    )


def phase_alarm(phase: str, alarm_name: str) -> MetricDef:
    return MetricDef(
        "phase_alarm",
        "0=OK; 1=Warning; 2=Alarm",
        "gauge",
        (("alarm", alarm_name), ("phase", phase)),
    )


# Maps the D-Bus path suffix (after N/<portalId>/<service>/<instance>/) to a MetricDef.
# Taken from the Go exporter's suffixTopicMap.
TOPIC_MAP: dict[str, MetricDef] = {
    # --- com.victronenergy.system ---
    "Ac/ActiveIn/Source": gauge(
        "ac_activein_source",
        "The active AC-In source of the multi",
    ),
    "Ac/Consumption/NumberOfPhases": gauge("ac_consumption_number_of_phases", ""),
    "Ac/Consumption/L1/Power": gauge(
        "ac_consumption_phase_power_watts",
        "Total of ConsumptionOnInput & ConsumptionOnOutput",
        phase="1",
    ),
    "Ac/Consumption/L2/Power": gauge(
        "ac_consumption_phase_power_watts",
        "Total of ConsumptionOnInput & ConsumptionOnOutput",
        phase="2",
    ),
    "Ac/Consumption/L3/Power": gauge(
        "ac_consumption_phase_power_watts",
        "Total of ConsumptionOnInput & ConsumptionOnOutput",
        phase="3",
    ),
    "Ac/ConsumptionOnInput/NumberOfPhases": gauge(
        "ac_consumption_on_input_number_of_phases", ""
    ),
    "Ac/ConsumptionOnInput/L1/Power": gauge(
        "ac_consumption_on_input_phase_power_watts", "W", phase="1"
    ),
    "Ac/ConsumptionOnInput/L2/Power": gauge(
        "ac_consumption_on_input_phase_power_watts", "W", phase="2"
    ),
    "Ac/ConsumptionOnInput/L3/Power": gauge(
        "ac_consumption_on_input_phase_power_watts", "W", phase="3"
    ),
    "Ac/ConsumptionOnOutput/NumberOfPhases": gauge(
        "ac_consumption_on_output_number_of_phases", ""
    ),
    "Ac/ConsumptionOnOutput/L1/Power": gauge(
        "ac_consumption_on_output_phase_power_watts", "W", phase="1"
    ),
    "Ac/ConsumptionOnOutput/L2/Power": gauge(
        "ac_consumption_on_output_phase_power_watts", "W", phase="2"
    ),
    "Ac/ConsumptionOnOutput/L3/Power": gauge(
        "ac_consumption_on_output_phase_power_watts", "W", phase="3"
    ),
    "Dc/Battery/Alarms/CircuitBreakerTripped": gauge(
        "dc_battery_alarms_circuit_breaker_tripped", ""
    ),
    "Dc/Battery/ConsumedAmphours": gauge("dc_battery_consumed_amphours", "Ah"),
    "Dc/Battery/Current": gauge("dc_battery_current", ""),
    "Dc/Battery/Power": gauge("dc_battery_power_watts", ""),
    "Dc/Battery/Soc": gauge("dc_battery_state_of_charge", ""),
    "Dc/Battery/State": gauge("dc_battery_state", ""),
    "Dc/Battery/TimeToGo": gauge("dc_battery_time_to_go_seconds", ""),
    "Dc/Battery/Voltage": gauge("dc_battery_voltage_volts", ""),
    "Dc/Battery/Temperature": gauge("dc_battery_temperature_celsius", ""),
    "Dc/Charger/Power": gauge("dc_charger_power_watts", ""),
    "Dc/Pv/Current": gauge("dc_pv_current_amps", ""),
    "Dc/Pv/Power": gauge("dc_pv_power_watts", ""),
    "Dc/System/Power": gauge("dc_system_power_watts", ""),
    "Dc/Vebus/Current": gauge("dc_vebus_current_amps", ""),
    "Dc/Vebus/Power": gauge(
        "dc_vebus_power_watts", "Charge/discharge power from the VE.Bus system"
    ),
    "Buzzer/State": gauge("buzzer_state", ""),
    "Relay/0/State": gauge("relay_state", "", relay="0"),
    "Relay/1/State": gauge("relay_state", "", relay="1"),
    "SystemState/State": gauge("system_state", ""),
    "Timers/TimeOnGrid": counter("time_on_grid_seconds_total", "Time spent on grid"),
    "Timers/TimeOnGenerator": counter(
        "time_on_generator_seconds_total", "Time spent on generator"
    ),
    "Timers/TimeOnInverter": counter(
        "time_on_inverter_seconds_total", "Time spent on inverter"
    ),
    "Timers/TimeOff": counter("time_off_seconds_total", "Time spent off"),
    # --- Settings/CGwacs ---
    "Settings/CGwacs/AcPowerSetPoint": gauge(
        "settings_cgwacs_ac_power_set_point", "User setting: Grid set-point"
    ),
    "Settings/CGwacs/BatteryLife/DischargedSoc": gauge(
        "settings_cgwacs_battery_life_discharged_state_of_charge", "Deprecated"
    ),
    "Settings/CGwacs/BatteryLife/DischargedTime": gauge(
        "settings_cgwacs_battery_life_discharged_time", "Internal"
    ),
    "Settings/CGwacs/BatteryLife/Flags": gauge(
        "settings_cgwacs_battery_life_flags", "Internal"
    ),
    "Settings/CGwacs/BatteryLife/MinimumSocLimit": gauge(
        "settings_cgwacs_battery_life_minimum_state_of_charge_limit",
        "User setting: Minimum Discharge SOC",
    ),
    "Settings/CGwacs/BatteryLife/SocLimit": gauge(
        "settings_cgwacs_battery_life_state_of_charge_limit",
        "Output of the BatteryLife algorithm (read only)",
    ),
    "Settings/CGwacs/BatteryLife/State": gauge(
        "settings_cgwacs_battery_life_state", "ESS state (read & write)"
    ),
    "Settings/CGwacs/Hub4Mode": gauge(
        "settings_cgwacs_hub4_mode", "ESS mode (read & write)"
    ),
    "Settings/CGwacs/MaxChargePercentage": gauge(
        "settings_cgwacs_max_charge_percentage", "Deprecated"
    ),
    "Settings/CGwacs/MaxChargePower": gauge(
        "settings_cgwacs_max_charge_power_watts", "User setting: Max Charge Power"
    ),
    "Settings/CGwacs/MaxDischargePercentage": gauge(
        "settings_cgwacs_max_discharge_percentage", "Deprecated"
    ),
    "Settings/CGwacs/MaxDischargePower": gauge(
        "settings_cgwacs_max_discharge_power_watts", "User setting: Max Inverter Power"
    ),
    "Settings/CGwacs/OvervoltageFeedIn": gauge(
        "settings_cgwacs_overvoltage_feed_in",
        "User setting: Feed-in excess solar charger power",
    ),
    "Settings/CGwacs/PreventFeedback": gauge(
        "settings_cgwacs_prevent_feedback",
        "User setting: PV Inverter Zero Feed-in (on/off)",
    ),
    "Settings/CGwacs/RunWithoutGridMeter": gauge(
        "settings_cgwacs_run_without_grid_meter",
        "User setting: Grid meter installed (on/off)",
    ),
    # --- com.victronenergy.vebus ---
    "Ac/ActiveIn/L1/F": gauge("ac_active_input_phase_freq_hz", "Frequency", phase="1"),
    "Ac/ActiveIn/L1/I": gauge(
        "ac_active_input_phase_current_amps", "Current", phase="1"
    ),
    "Ac/ActiveIn/L1/P": gauge(
        "ac_active_input_phase_power_watts", "Real power", phase="1"
    ),
    "Ac/ActiveIn/L1/V": gauge("ac_active_input_phase_voltage_volts", "", phase="1"),
    "Ac/ActiveIn/P": gauge("ac_active_input_power_watts", "Total power"),
    "Ac/ActiveIn/Connected": gauge(
        "ac_active_input_connected",
        "0 when inverting, 1 when connected to an AC in",
    ),
    "Ac/ActiveIn/ActiveInput": gauge(
        "ac_active_input_active_input",
        "Active input: 0=ACin-1, 1=ACin-2, 240=none (inverting)",
    ),
    "Ac/In/1/CurrentLimit": gauge("ac_input_current_limit", "", input="1"),
    "Ac/In/1/CurrentLimitIsAdjustable": gauge(
        "ac_input_current_limit_is_adjustable", "", input="1"
    ),
    "Ac/In/2/CurrentLimit": gauge("ac_input_current_limit", "", input="2"),
    "Ac/In/2/CurrentLimitIsAdjustable": gauge(
        "ac_input_current_limit_is_adjustable", "", input="2"
    ),
    "Ac/PowerMeasurementType": gauge(
        "ac_power_measurement_type",
        "Indicates the type of power measurement used by the system",
    ),
    "Alarms/LowBattery": alarm("LowBattery"),
    "Alarms/PhaseRotation": alarm("PhaseRotation"),
    "Alarms/Ripple": alarm("Ripple"),
    "Alarms/TemperatureSensor": alarm("TemperatureSensor"),
    "Alarms/L1/HighTemperature": phase_alarm("1", "HighTemperature"),
    "Alarms/L1/LowBattery": phase_alarm("1", "LowBattery"),
    "Alarms/L1/Overload": phase_alarm("1", "Overload"),
    "Alarms/L1/Ripple": phase_alarm("1", "Ripple"),
    "Alarms/L2/HighTemperature": phase_alarm("2", "HighTemperature"),
    "Alarms/L2/LowBattery": phase_alarm("2", "LowBattery"),
    "Alarms/L2/Overload": phase_alarm("2", "Overload"),
    "Alarms/L2/Ripple": phase_alarm("2", "Ripple"),
    "Alarms/L3/HighTemperature": phase_alarm("3", "HighTemperature"),
    "Alarms/L3/LowBattery": phase_alarm("3", "LowBattery"),
    "Alarms/L3/Overload": phase_alarm("3", "Overload"),
    "Alarms/L3/Ripple": phase_alarm("3", "Ripple"),
    "Dc/0/Voltage": gauge("dc_voltage_volts", "V DC", n="0"),
    "Dc/0/Current": gauge("dc_current_amps", "A DC", n="0"),
    "Dc/0/Power": gauge("dc_power_watts", "", n="0"),
    "Dc/0/Temperature": gauge("dc_temperature_celsius", "Battery temperature", n="0"),
    "Dc/0/MidVoltage": gauge(
        "dc_midvoltage_volts",
        "V DC Mid voltage (BMV-702 midpoint voltage)",
        n="0",
    ),
    "Dc/0/MidVoltageDeviation": gauge(
        "dc_midvoltage_deviation_percent", "Percentage deviation", n="0"
    ),
    "Dc/1/Voltage": gauge("dc_voltage_volts", "V DC", n="1"),
    "Dc/1/Current": gauge("dc_current_amps", "A DC", n="1"),
    "Dc/1/Temperature": gauge("dc_temperature_celsius", "Battery temperature", n="1"),
    "Dc/2/Voltage": gauge("dc_voltage_volts", "V DC", n="2"),
    "Dc/2/Current": gauge("dc_current_amps", "A DC", n="2"),
    "Dc/2/Temperature": gauge("dc_temperature_celsius", "Battery temperature", n="2"),
    "Mode": gauge(
        "mode",
        "Switch position: 1=Charger Only; 2=Inverter Only; 3=On; 4=Off",
    ),
    "ModeIsAdjustable": gauge("mode_is_adjustable", ""),
    "VebusChargeState": gauge(
        "vebus_charge_state",
        "1=Bulk 2=Absorption 3=Float 4=Storage 5=Repeat absorption "
        "6=Forced absorption 7=Equalise 8=Bulk stopped",
    ),
    "VebusSetChargeState": gauge(
        "vebus_set_charge_state",
        "1=Force Equalise 2=Force Absorption 3=Force Float",
    ),
    "Leds/Mains": gauge("led_mains", "0=Off 1=On 2=Blinking 3=Blinking inverted"),
    "Leds/Bulk": gauge("led_bulk", "0=Off 1=On 2=Blinking 3=Blinking inverted"),
    "Leds/Absorption": gauge(
        "led_absorption", "0=Off 1=On 2=Blinking 3=Blinking inverted"
    ),
    "Leds/Float": gauge("led_float", "0=Off 1=On 2=Blinking 3=Blinking inverted"),
    "Leds/Inverter": gauge("led_inverter", "0=Off 1=On 2=Blinking 3=Blinking inverted"),
    "Leds/Overload": gauge("led_overload", "0=Off 1=On 2=Blinking 3=Blinking inverted"),
    "Leds/LowBattery": gauge(
        "led_low_battery", "0=Off 1=On 2=Blinking 3=Blinking inverted"
    ),
    "Leds/Temperature": gauge(
        "led_temperature", "0=Off 1=On 2=Blinking 3=Blinking inverted"
    ),
    # --- com.victronenergy.inverter ---
    "Alarms/LowVoltage": alarm("LowVoltage"),
    "Alarms/HighVoltage": alarm("HighVoltage"),
    "Alarms/LowTemperature": alarm("LowTemperature"),
    "Alarms/HighTemperature": alarm("HighTemperature"),
    "Alarms/Overload": alarm("Overload"),
    "Alarms/LowVoltageAcOut": alarm("LowVoltageAcOut"),
    "Alarms/HighVoltageAcOut": alarm("HighVoltageAcOut"),
    "Ac/Out/P": gauge("ac_output_power_watts", "AC Output power"),
    "Ac/Out/L1/V": gauge("ac_output_phase_volts", "AC Output voltage", phase="1"),
    "Ac/Out/L1/I": gauge(
        "ac_output_phase_current_amps", "AC Output current", phase="1"
    ),
    "Ac/Out/L1/F": gauge("ac_output_phase_freq_hz", "AC Output frequency", phase="1"),
    "Ac/Out/L1/P": gauge("ac_output_phase_power_watts", "", phase="1"),
    "State": gauge("state", ""),
    # --- com.victronenergy.battery ---
    "ConsumedAmphours": gauge("consumed_amphours", "Ah"),
    "Soc": gauge("state_of_charge", "0 to 100% (BMV, BYD, Lynx BMS)"),
    "TimeToGo": gauge(
        "time_to_go_seconds",
        "Time to go in seconds. Max 864000 when not discharging.",
    ),
    "Info/MaxChargeCurrent": gauge(
        "max_charge_current_amps", "Charge Current Limit (CCL)"
    ),
    "Info/MaxDischargeCurrent": gauge(
        "max_discharge_current_amps", "Discharge Current Limit (DCL)"
    ),
    "Info/MaxChargeVoltage": gauge(
        "max_charge_voltage_volts", "Maximum voltage to charge to"
    ),
    "Info/BatteryLowVoltage": gauge("battery_low_voltage", ""),
    "Ac/Alarms/GridLost": alarm("GridLost"),
    "Alarms/Alarm": alarm("Alarm"),
    "Alarms/LowStarterVoltage": alarm("LowStarterVoltage"),
    "Alarms/HighStarterVoltage": alarm("HighStarterVoltage"),
    "Alarms/LowSoc": alarm("LowSoc"),
    "Alarms/HighChargeCurrent": alarm("HighChargeCurrent"),
    "Alarms/HighDischargeCurrent": alarm("HighDischargeCurrent"),
    "Alarms/CellImbalance": alarm("CellImbalance"),
    "Alarms/InternalFailure": alarm("InternalFailure"),
    "Alarms/HighChargeTemperature": alarm("HighChargeTemperature"),
    "Alarms/LowChargeTemperature": alarm("LowChargeTemperature"),
    "Alarms/LowCellVoltage": alarm("LowCellVoltage"),
    "Alarms/MidVoltage": alarm("MidVoltage"),
    "Settings/HasTemperature": gauge("settings_has_temperature", ""),
    "Settings/HasStarterVoltage": gauge("settings_has_starter_voltage", ""),
    "Settings/HasMidVoltage": gauge("settings_has_mid_voltage", ""),
    "History/DeepestDischarge": gauge("history_deepest_discharge", ""),
    "History/LastDischarge": gauge("history_last_discharge", ""),
    "History/AverageDischarge": gauge("history_avg_discharge", ""),
    "History/ChargeCycles": gauge("history_charge_cycles", ""),
    "History/FullDischarges": gauge("history_full_discharges", ""),
    "History/TotalAhDrawn": gauge("history_total_drawn_amphours", ""),
    "History/MinimumVoltage": gauge("history_min_voltage_volts", ""),
    "History/MaximumVoltage": gauge("history_max_voltage_volts", ""),
    "History/TimeSinceLastFullCharge": gauge(
        "history_time_since_full_charge_seconds", ""
    ),
    "History/AutomaticSyncs": gauge("history_automatic_syncs", ""),
    "History/LowVoltageAlarms": gauge("history_low_voltage_alarms", ""),
    "History/HighVoltageAlarms": gauge("history_high_voltage_alarms", ""),
    "History/LowStarterVoltageAlarms": gauge("history_low_starter_voltage_alarms", ""),
    "History/HighStarterVoltageAlarms": gauge(
        "history_high_starter_voltage_alarms", ""
    ),
    "History/MinimumStarterVoltage": gauge("history_min_starter_voltage", ""),
    "History/MaximumStarterVoltage": gauge("history_max_starter_voltage", ""),
    "History/DischargedEnergy": gauge("history_discharge_energy_kwh", ""),
    "History/ChargedEnergy": gauge("history_charged_energy_kwh", ""),
    "ErrorCode": gauge("error_code", ""),
    "SystemSwitch": gauge("system_switch", ""),
    "Balancing": gauge("balancing", ""),
    "System/NrOfBatteries": gauge("system_battery_count", ""),
    "System/BatteriesParallel": gauge("system_batteries_parallel_count", ""),
    "System/BatteriesSeries": gauge("system_batteries_series_count", ""),
    "System/NrOfCellsPerBattery": gauge("system_cells_per_battery_count", ""),
    "System/MinCellVoltage": gauge("system_min_cell_voltage_volts", ""),
    "System/MaxCellVoltage": gauge("system_max_cell_voltage_volts", ""),
    "Diagnostics/ShutDownsDueError": gauge(
        "diagnostics_shutdowns_due_to_error_count", ""
    ),
    "Diagnostics/LastErrors/1/Error": gauge("diagnostics_last_error", "", e="1"),
    "Diagnostics/LastErrors/2/Error": gauge("diagnostics_last_error", "", e="2"),
    "Diagnostics/LastErrors/3/Error": gauge("diagnostics_last_error", "", e="3"),
    "Diagnostics/LastErrors/4/Error": gauge("diagnostics_last_error", "", e="4"),
    "Io/AllowToCharge": gauge("io_allow_to_charge", ""),
    "Io/AllowToDischarge": gauge("io_allow_to_discharge", ""),
    "Io/ExternalRelay": gauge("io_external_relay", ""),
    "History/MinimumCellVoltage": gauge("history_min_cell_voltage_volts", ""),
    "History/MaximumCellVoltage": gauge("history_max_cell_voltage_volts", ""),
    # --- com.victronenergy.solarcharger ---
    "Pv/V": gauge("pv_array_voltage_volts", "PV array voltage"),
    "Pv/I": gauge("pv_array_current_amps", "PV current"),
    "Yield/Power": gauge("yield_power_watts", "Actual input power"),
    "Yield/User": gauge("yield_user_total_kwh", "Total kWh produced (user resettable)"),
    "Yield/System": gauge(
        "yield_system_total_kwh", "Total kWh produced (not resettable)"
    ),
    "Load/State": gauge("load_state", "Whether the load is on or off"),
    "Load/I": gauge("load_current_amps", "Current from the load output"),
    "MppOperationMode": gauge(
        "mpp_operation_mode", "0=Off 1=Voltage/Current limited 2=MPPT active"
    ),
    # --- com.victronenergy.pvinverter ---
    "Ac/Energy/Forward": gauge(
        "ac_energy_forward_kwh", "Total produced energy over all phases"
    ),
    "Ac/Energy/Reverse": gauge("ac_energy_reverse_kwh", ""),
    "Ac/Power": gauge("ac_power_watts", "Total power of all phases"),
    "Ac/L1/Current": gauge("ac_phase_current", "A AC", phase="1"),
    "Ac/L1/Energy/Forward": gauge("ac_phase_energy_forward_kwh", "kWh", phase="1"),
    "Ac/L1/Energy/Reverse": gauge("ac_phase_energy_reverse_kwh", "", phase="1"),
    "Ac/L1/Power": gauge("ac_phase_power_watts", "W", phase="1"),
    "Ac/L1/Voltage": gauge("ac_phase_voltage_volts", "V AC", phase="1"),
    "Ac/L2/Current": gauge("ac_phase_current", "A AC", phase="2"),
    "Ac/L2/Energy/Forward": gauge("ac_phase_energy_forward_kwh", "kWh", phase="2"),
    "Ac/L2/Energy/Reverse": gauge("ac_phase_energy_reverse_kwh", "", phase="2"),
    "Ac/L2/Power": gauge("ac_phase_power_watts", "W", phase="2"),
    "Ac/L2/Voltage": gauge("ac_phase_voltage_volts", "V AC", phase="2"),
    "Ac/L3/Current": gauge("ac_phase_current", "A AC", phase="3"),
    "Ac/L3/Energy/Forward": gauge("ac_phase_energy_forward_kwh", "kWh", phase="3"),
    "Ac/L3/Energy/Reverse": gauge("ac_phase_energy_reverse_kwh", "", phase="3"),
    "Ac/L3/Power": gauge("ac_phase_power_watts", "W", phase="3"),
    "Ac/L3/Voltage": gauge("ac_phase_voltage_volts", "V AC", phase="3"),
    "Ac/Current": gauge("ac_current_amps", "A AC - Deprecated"),
    "Ac/Voltage": gauge("ac_voltage_volts", "V AC - Deprecated"),
    "Ac/MaxPower": gauge("ac_max_power_watts", "Max rated power of the inverter"),
    "Ac/PowerLimit": gauge(
        "ac_power_limit_watts", "Used by the Fronius Zero-feedin feature"
    ),
    "FroniusDeviceType": gauge("fronius_device_type", "Fronius specific product id"),
    "Position": gauge("position", "0=AC input 1; 1=AC output; 2=AC input 2"),
    "StatusCode": gauge(
        "status_code",
        "0-6=Startup; 7=Running; 8=Standby; 9=Boot loading; 10=Error",
    ),
    # --- com.victronenergy.charger ---
    "Ac/In/L1/I": gauge("ac_input_phase_current_amps", "A AC", phase="1"),
    "Ac/In/L1/P": gauge("ac_input_phase_power_watts", "W", phase="1"),
    "Ac/In/CurrentLimit": gauge("ac_input_current_limit_amps", "A AC"),
    "NrOfOutputs": gauge("output_count", "The actual number of outputs"),
    # --- com.victronenergy.grid ---
    "Ac/Grid/L1/Power": gauge("ac_grid_phase_power_watts", "", phase="1"),
    "Ac/Grid/L2/Power": gauge("ac_grid_phase_power_watts", "", phase="2"),
    "Ac/Grid/L3/Power": gauge("ac_grid_phase_power_watts", "", phase="3"),
    "Ac/Grid/NumberOfPhases": gauge("ac_grid_number_of_phases", ""),
}
