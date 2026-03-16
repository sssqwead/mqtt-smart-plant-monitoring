import json
import random
import time

import paho.mqtt.client as mqtt

# MQTT settings
BROKER = "broker.hivemq.com"
PORT = 1883
PLANT_ID = "plant-001"

SENSOR_TOPIC = f"smartplant/{PLANT_ID}/sensor/danial"
STATUS_TOPIC = f"smartplant/{PLANT_ID}/status/danial"

# Simulated sensor values
soil_ph = 6.4
salinity = 1.4
root_zone_temperature = 23.0

app_version2 = mqtt.CallbackAPIVersion.VERSION2
client = mqtt.Client(callback_api_version=app_version2)


def publish_status(message: str):
    payload = {
        "plant_id": PLANT_ID,
        "module": "danial_publisher",
        "message": message,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    client.publish(STATUS_TOPIC, json.dumps(payload), qos=1)


def main():
    try:
        client.connect(BROKER, PORT, 60)
        client.loop_start()
    except Exception as e:
        print("Connection failed:", e)
        return

    print("Danial Publisher connected")
    print("Publishing to topic:", SENSOR_TOPIC)

    publish_status("Danial sensor publisher started")

    global soil_ph, salinity, root_zone_temperature

    try:
        while True:

            # simulate sensor change
            soil_ph += random.uniform(-0.08, 0.08)
            salinity += random.uniform(-0.10, 0.10)
            root_zone_temperature += random.uniform(-0.30, 0.30)

            # realistic limits
            soil_ph = max(4.5, min(8.5, soil_ph))
            salinity = max(0.2, min(4.0, salinity))
            root_zone_temperature = max(10.0, min(35.0, root_zone_temperature))

            reading = {
                "plant_id": PLANT_ID,
                "sensor_owner": "Danial",
                "soil_ph": round(soil_ph, 2),
                "salinity": round(salinity, 2),
                "root_zone_temperature": round(root_zone_temperature, 2),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            client.publish(SENSOR_TOPIC, json.dumps(reading), qos=1)

            print(
                "Sent:",
                "pH =", reading["soil_ph"],
                "salinity =", reading["salinity"],
                "root_temp =", reading["root_zone_temperature"],
            )

            time.sleep(5)

    except KeyboardInterrupt:
        print("Publisher stopped")

    finally:
        try:
            publish_status("Danial sensor publisher stopped")
            client.loop_stop()
            client.disconnect()
        except:
            pass


if __name__ == "__main__":
    main()