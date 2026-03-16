import json      # for encoding/decoding MQTT payloads
import sqlite3   # for persisting sensor data and activity logs
import time      # for timestamps and cooldown tracking

import paho.mqtt.client as mqtt  # MQTT client library

# Import all settings and plant profiles from central config
from config import (
    BROKER, PORT, DB_PATH, COOLDOWN_SECONDS,
    SENSOR_TOPIC, COMMAND_TOPIC, STATUS_TOPIC, ALERT_TOPIC,
    PLANT_PROFILES,
)

# Arystan's nutrient module
from nutrient_module import evaluate_npk

# Wildcard subscriptions — '+' matches any single topic level
# This allows one controller to handle all plant types simultaneously
SENSOR_TOPIC_SUB = "smartplant/+/sensor"
STATUS_TOPIC_SUB = "smartplant/+/status"

# Use the newer VERSION2 callback API required by paho-mqtt 2.x
app_version2 = mqtt.CallbackAPIVersion.VERSION2
client = mqtt.Client(callback_api_version=app_version2)

# Per-plant watering state — keyed by plant_id string
# Stored as dicts so multiple plants are tracked independently
is_watering: dict[str, bool] = {}
last_cmd_time: dict[str, float] = {}

# Tracks active alert types per plant to avoid re-publishing every cycle
# Format: { plant_id: { alert_type: severity } }
active_alerts: dict[str, dict] = {}


# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    """Create database tables if they don't exist yet, and migrate old schemas."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    # Main sensor readings table — extended with new parameters
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_data (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp        TEXT,
            plant_id         TEXT,
            plant_type       TEXT,
            soil_moisture    REAL,
            temperature      REAL,
            humidity         REAL,
            nitrogen         REAL,
            phosphorus       REAL,
            potassium        REAL,
            soil_ph          REAL,
            salinity         REAL,
            root_temperature REAL
        )
        """
    )

    # Activity log — records commands, alerts, and system events
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp  TEXT,
            event_type TEXT,
            details    TEXT,
            severity   TEXT DEFAULT 'INFO'
        )
        """
    )

    # Backward-compatible migration: add any missing columns to existing databases
    _add_column_if_missing(cursor, "sensor_data", "plant_type", "TEXT")
    _add_column_if_missing(cursor, "sensor_data", "nitrogen", "REAL")
    _add_column_if_missing(cursor, "sensor_data", "phosphorus", "REAL")
    _add_column_if_missing(cursor, "sensor_data", "potassium", "REAL")
    _add_column_if_missing(cursor, "sensor_data", "soil_ph", "REAL")
    _add_column_if_missing(cursor, "sensor_data", "salinity", "REAL")
    _add_column_if_missing(cursor, "sensor_data", "root_temperature", "REAL")
    _add_column_if_missing(cursor, "activity_log", "severity", "TEXT DEFAULT 'INFO'")

    connection.commit()
    connection.close()


def _add_column_if_missing(cursor, table, column, col_type):
    """Add a column to a table only if it does not already exist."""
    existing = [r[1] for r in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def log_activity(event_type, details, severity="INFO"):
    """Insert a row into activity_log with an optional severity level."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    cursor.execute(
        "INSERT INTO activity_log (timestamp, event_type, details, severity) VALUES (?, ?, ?, ?)",
        (time.strftime("%Y-%m-%d %H:%M:%S"), event_type, details, severity),
    )
    connection.commit()
    connection.close()


def save_sensor_data(data):
    """Persist a full sensor reading dict to the sensor_data table."""
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO sensor_data
            (timestamp, plant_id, plant_type, soil_moisture, temperature, humidity,
             nitrogen, phosphorus, potassium, soil_ph, salinity, root_temperature)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("timestamp"),
            data.get("plant_id"),
            data.get("plant_type"),
            data.get("soil_moisture"),
            data.get("temperature"),
            data.get("humidity"),
            data.get("nitrogen"),
            data.get("phosphorus"),
            data.get("potassium"),
            data.get("soil_ph"),
            data.get("salinity"),
            data.get("root_temperature"),
        ),
    )
    connection.commit()
    connection.close()


# ── Alert helpers ─────────────────────────────────────────────────────────────

def _severity_for_value(value, low, high):
    """
    Determine alert severity for a value measured against an optimal [low, high] range.
    Returns a (severity_string, is_out_of_range) tuple.
    Deviation is calculated as a fraction of the range span.
    """
    margin_warn = 0.10   # 10% beyond range boundary → WARNING
    margin_crit = 0.20   # 20% beyond range boundary → CRITICAL
    span = high - low if high != low else 1  # avoid division by zero

    if value < low:
        deviation = (low - value) / span
    elif value > high:
        deviation = (value - high) / span
    else:
        return "INFO", False

    if deviation >= margin_crit:
        return "CRITICAL", True
    return "WARNING", True


def publish_alert(plant_id, plant_type, alert_type, severity, message):
    """
    Publish a structured alert only if it is new or its severity has changed.
    Prevents flooding the broker with duplicate alerts every sensor cycle.
    """
    plant_active = active_alerts.setdefault(plant_id, {})

    # Skip if this exact alert type with the same severity is already active
    if plant_active.get(alert_type) == severity:
        return

    # Register the alert as active so it won't be re-published next cycle
    plant_active[alert_type] = severity

    topic = ALERT_TOPIC.format(plant_id=plant_id)
    payload = {
        "plant_id": plant_id,
        "plant_type": plant_type,
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    client.publish(topic, json.dumps(payload))
    log_activity("alert_published", json.dumps(payload), severity)
    print(f"[controller] ALERT [{severity}] {alert_type}: {message}")


def clear_alert(plant_id, alert_type):
    """Remove an alert from the active registry when its value returns to normal."""
    active_alerts.setdefault(plant_id, {}).pop(alert_type, None)


# ── Watering commands ─────────────────────────────────────────────────────────

def send_command(plant_id, action, reason, severity="INFO"):
    """Publish a WATER_ON or WATER_OFF command and update local watering state."""
    topic = COMMAND_TOPIC.format(plant_id=plant_id)
    payload = {
        "plant_id": plant_id,
        "action": action,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    client.publish(topic, json.dumps(payload))
    log_activity("command_sent", json.dumps(payload), severity)
    last_cmd_time[plant_id] = time.time()

    if action == "WATER_ON":
        is_watering[plant_id] = True
    elif action == "WATER_OFF":
        is_watering[plant_id] = False

    print(f"[controller] Command sent: {action} ({reason})")


# ── Core evaluation logic ─────────────────────────────────────────────────────

def evaluate_plant(data, profile, plant_id, plant_type):
    """
    Run all threshold checks for a single sensor reading.
    Publishes alerts only when state changes — not on every cycle.
    Clears alerts when values return to the normal range.
    """
    moisture = float(data.get("soil_moisture", 0))
    now = time.time()
    watering = is_watering.get(plant_id, False)

    # -- Moisture alerts --
    if moisture < profile["moisture_critical"] and not watering:
        publish_alert(
            plant_id, plant_type, "LOW_MOISTURE", "CRITICAL",
            f"Soil moisture critically low: {moisture}%"
        )
    elif moisture < profile["moisture_warning"] and not watering:
        publish_alert(
            plant_id, plant_type, "LOW_MOISTURE", "WARNING",
            f"Soil moisture low: {moisture}%"
        )
    else:
        clear_alert(plant_id, "LOW_MOISTURE")

    # -- Watering control --
    if (
        moisture < profile["moisture_min"]
        and not watering
        and (now - last_cmd_time.get(plant_id, 0)) >= COOLDOWN_SECONDS
    ):
        send_command(plant_id, "WATER_ON", "Soil moisture below threshold")

    elif moisture >= profile["moisture_stop"] and watering:
        send_command(plant_id, "WATER_OFF", "Soil moisture reached stop level")

    # -- Arystan's NPK checks --
    evaluate_npk(
        data,
        profile,
        plant_id,
        plant_type,
        _severity_for_value,
        publish_alert,
        clear_alert,
    )

    # -- pH check --
    ph = data.get("soil_ph")
    if ph is not None:
        sev, out = _severity_for_value(float(ph), *profile["soil_ph"])
        if out:
            publish_alert(
                plant_id, plant_type, "PH_OUT_OF_RANGE", sev,
                f"Soil pH out of range: {ph} (optimal {profile['soil_ph'][0]}–{profile['soil_ph'][1]})"
            )
        else:
            clear_alert(plant_id, "PH_OUT_OF_RANGE")

    # -- Salinity check --
    sal = data.get("salinity")
    if sal is not None:
        if float(sal) > profile["salinity"][1]:
            sev = "CRITICAL" if float(sal) > profile["salinity"][1] * 1.3 else "WARNING"
            publish_alert(
                plant_id, plant_type, "HIGH_SALINITY", sev,
                f"Salinity too high: {sal} dS/m (max {profile['salinity'][1]})"
            )
        else:
            clear_alert(plant_id, "HIGH_SALINITY")

    # -- Root temperature check --
    rt = data.get("root_temperature")
    if rt is not None:
        sev, out = _severity_for_value(float(rt), *profile["root_temperature"])
        if out:
            publish_alert(
                plant_id, plant_type, "ROOT_TEMP_OUT_OF_RANGE", sev,
                f"Root temperature out of range: {rt}°C (optimal {profile['root_temperature'][0]}–{profile['root_temperature'][1]})"
            )
        else:
            clear_alert(plant_id, "ROOT_TEMP_OUT_OF_RANGE")


# ── MQTT callbacks ────────────────────────────────────────────────────────────

def handle_sensor_message(data):
    """Save incoming sensor data to DB and run plant evaluation logic."""
    save_sensor_data(data)

    plant_id = data.get("plant_id", "unknown")
    plant_type = data.get("plant_type", "ficus")
    profile = PLANT_PROFILES.get(plant_type)

    if profile is None:
        print(f"[controller] Unknown plant type '{plant_type}', skipping evaluation")
        return

    print(
        f"[controller] [{plant_type}] moisture={data.get('soil_moisture')}, "
        f"pH={data.get('soil_ph')}, N={data.get('nitrogen')}, "
        f"P={data.get('phosphorus')}, K={data.get('potassium')}, "
        f"temp={data.get('temperature')}"
    )

    evaluate_plant(data, profile, plant_id, plant_type)


def on_message(client, userdata, msg):
    """Route incoming MQTT messages to the correct handler."""
    if not msg.topic.startswith("smartplant/plant-"):
        return

    try:
        payload = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        return

    if msg.topic.endswith("/sensor"):
        handle_sensor_message(payload)
    elif msg.topic.endswith("/status"):
        print(f"[controller] Status update: {payload}")
        log_activity("status_received", json.dumps(payload))


# ── Startup ───────────────────────────────────────────────────────────────────

init_db()
client.on_message = on_message
client.connect(BROKER, PORT)
client.subscribe(SENSOR_TOPIC_SUB)
client.subscribe(STATUS_TOPIC_SUB)

print("[controller] Connected")
print(f"[controller] Listening on: {SENSOR_TOPIC_SUB}")
print(f"[controller] Listening on: {STATUS_TOPIC_SUB}")

log_activity("controller_started", "Controller started and subscribed")

try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\n[controller] Stopped")
finally:
    log_activity("controller_stopped", "Controller stopped")
    client.disconnect()
