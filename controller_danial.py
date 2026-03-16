import json
import sqlite3
import time

import paho.mqtt.client as mqtt

# MQTT settings
BROKER = "broker.hivemq.com"
PORT = 1883
PLANT_ID = "plant-001"

SENSOR_TOPIC = f"smartplant/{PLANT_ID}/sensor/danial"
STATUS_TOPIC = f"smartplant/{PLANT_ID}/status/danial"
ALERT_TOPIC = f"smartplant/{PLANT_ID}/alert/danial"

DB_PATH = "plant_monitoring.db"

app_version2 = mqtt.CallbackAPIVersion.VERSION2
client = mqtt.Client(callback_api_version=app_version2)


def init_db():
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS environmental_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            plant_id TEXT,
            soil_ph REAL,
            salinity REAL,
            root_zone_temperature REAL,
            ph_status TEXT,
            salinity_status TEXT,
            temperature_status TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS environmental_activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event_type TEXT,
            details TEXT
        )
        """
    )

    connection.commit()
    connection.close()


def log_activity(event_type, details):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO environmental_activity_log (timestamp, event_type, details)
        VALUES (?, ?, ?)
        """,
        (time.strftime("%Y-%m-%d %H:%M:%S"), event_type, details),
    )

    connection.commit()
    connection.close()


def classify_ph(value):
    if value < 5.5:
        return "LOW"
    elif value > 7.5:
        return "HIGH"
    else:
        return "NORMAL"


def classify_salinity(value):
    if value < 0.8:
        return "LOW"
    elif value > 2.5:
        return "HIGH"
    else:
        return "NORMAL"


def classify_root_temp(value):
    if value < 18:
        return "LOW"
    elif value > 28:
        return "HIGH"
    else:
        return "NORMAL"


def save_environmental_data(data, ph_status, salinity_status, temp_status):
    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO environmental_data (
            timestamp, plant_id, soil_ph, salinity, root_zone_temperature,
            ph_status, salinity_status, temperature_status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("timestamp"),
            data.get("plant_id"),
            data.get("soil_ph"),
            data.get("salinity"),
            data.get("root_zone_temperature"),
            ph_status,
            salinity_status,
            temp_status,
        ),
    )

    connection.commit()
    connection.close()


def publish_alert(message_type, details):
    payload = {
        "plant_id": PLANT_ID,
        "type": message_type,
        "details": details,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    client.publish(ALERT_TOPIC, json.dumps(payload), qos=1)
    log_activity("alert_sent", json.dumps(payload))


def handle_sensor_message(data):
    soil_ph = float(data.get("soil_ph", 0))
    salinity = float(data.get("salinity", 0))
    root_temp = float(data.get("root_zone_temperature", 0))

    ph_status = classify_ph(soil_ph)
    salinity_status = classify_salinity(salinity)
    temp_status = classify_root_temp(root_temp)

    save_environmental_data(data, ph_status, salinity_status, temp_status)

    print(
        "Received:",
        "pH =", soil_ph, f"({ph_status})",
        "salinity =", salinity, f"({salinity_status})",
        "root_temp =", root_temp, f"({temp_status})",
    )

    if ph_status != "NORMAL":
        publish_alert(
            "PH_WARNING",
            {
                "soil_ph": soil_ph,
                "status": ph_status,
                "message": "Soil pH out of safe range"
            },
        )

    if salinity_status != "NORMAL":
        publish_alert(
            "SALINITY_WARNING",
            {
                "salinity": salinity,
                "status": salinity_status,
                "message": "Salinity out of normal range"
            },
        )

    if temp_status != "NORMAL":
        publish_alert(
            "ROOT_TEMP_WARNING",
            {
                "root_zone_temperature": root_temp,
                "status": temp_status,
                "message": "Root-zone temperature out of normal range"
            },
        )


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
    except Exception as e:
        print("Invalid JSON:", e)
        return

    if msg.topic == SENSOR_TOPIC:
        handle_sensor_message(payload)

    elif msg.topic == STATUS_TOPIC:
        print("Status update:", payload)
        log_activity("status_received", json.dumps(payload))


def main():
    init_db()

    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
        client.subscribe(SENSOR_TOPIC, qos=1)
        client.subscribe(STATUS_TOPIC, qos=1)
    except Exception as e:
        print("Controller connection failed:", e)
        return

    print("Danial Controller connected")
    print("Listening to:", SENSOR_TOPIC)
    print("Listening to:", STATUS_TOPIC)
    print("Publishing alerts to:", ALERT_TOPIC)

    log_activity("controller_started", "Danial controller started")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("Controller stopped")
    finally:
        try:
            log_activity("controller_stopped", "Danial controller stopped")
            client.disconnect()
        except:
            pass


if __name__ == "__main__":
    main()