import json
import random
import time

import paho.mqtt.client as mqtt

# MQTT settings
BROKER = "broker.hivemq.com"
PORT = 1883
PLANT_ID = "plant-001"

SENSOR_TOPIC = f"smartplant/{PLANT_ID}/sensor"
COMMAND_TOPIC = f"smartplant/{PLANT_ID}/command"
STATUS_TOPIC = f"smartplant/{PLANT_ID}/status"

# Simulated environment state
soil_moisture = 55.0
temperature = 24.0
humidity = 60.0
watering_active = False

app_version2 = mqtt.CallbackAPIVersion.VERSION2
client = mqtt.Client(callback_api_version=app_version2)


def on_message(client, userdata, msg):
    global watering_active

    try:
        payload = json.loads(msg.payload.decode())
        action = payload.get("action", "")
    except json.JSONDecodeError:
        print("[publisher] Invalid command payload")
        return

    if action == "WATER_ON":
        watering_active = True
    elif action == "WATER_OFF":
        watering_active = False

    print(f"[publisher] Command received: {action}, watering_active={watering_active}")

    status = {
        "plant_id": PLANT_ID,
        "watering_active": watering_active,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    client.publish(STATUS_TOPIC, json.dumps(status))


client.on_message = on_message
client.connect(BROKER, PORT)
client.subscribe(COMMAND_TOPIC)
client.loop_start()

print("[publisher] Connected")
print(f"[publisher] Publishing to: {SENSOR_TOPIC}")
print(f"[publisher] Listening for commands on: {COMMAND_TOPIC}")

try:
    while True:
        # Natural moisture drop, increase moisture when watering is active
        soil_moisture -= random.uniform(0.2, 0.8)
        if watering_active:
            soil_moisture += random.uniform(1.5, 3.0)

        # Keep values realistic
        soil_moisture = max(0.0, min(100.0, soil_moisture))
        temperature += random.uniform(-0.2, 0.2)
        humidity += random.uniform(-1.0, 1.0)
        temperature = max(15.0, min(40.0, temperature))
        humidity = max(20.0, min(95.0, humidity))

        reading = {
            "plant_id": PLANT_ID,
            "soil_moisture": round(soil_moisture, 2),
            "temperature": round(temperature, 2),
            "humidity": round(humidity, 2),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        client.publish(SENSOR_TOPIC, json.dumps(reading))
        print(
            "[publisher] Sent:",
            f"moisture={reading['soil_moisture']},",
            f"temp={reading['temperature']},",
            f"humidity={reading['humidity']}",
        )

        time.sleep(5)
except KeyboardInterrupt:
    print("\n[publisher] Stopped")
finally:
    client.loop_stop()
    client.disconnect()
