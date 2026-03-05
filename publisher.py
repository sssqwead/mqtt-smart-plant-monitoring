import json       # for encoding sensor readings as JSON strings
import random     # for simulating realistic sensor value drift
import sys        # for reading CLI argument (plant type)
import time       # for timestamps and sleep between readings

import paho.mqtt.client as mqtt  # MQTT client library

# Import all settings and plant profiles from central config
from config import (
    BROKER, PORT,
    SENSOR_TOPIC, COMMAND_TOPIC, STATUS_TOPIC,
    PLANT_PROFILES, DEFAULT_PLANT,
)

# ── Plant selection ───────────────────────────────────────────────────────────
# Accept plant type as first CLI argument, e.g. "python publisher.py cactus"
# Fall back to DEFAULT_PLANT if no argument is given
PLANT_TYPE = sys.argv[1].lower() if len(sys.argv) > 1 else DEFAULT_PLANT

# Validate the provided plant type against known profiles
if PLANT_TYPE not in PLANT_PROFILES:
    print(f"[publisher] Unknown plant '{PLANT_TYPE}'. Choose: {list(PLANT_PROFILES)}")
    sys.exit(1)

# Build a unique plant ID from the type, e.g. "plant-ficus-001"
PLANT_ID = f"plant-{PLANT_TYPE}-001"

# Load the threshold/range profile for the selected plant
profile = PLANT_PROFILES[PLANT_TYPE]

# Build fully-qualified topic strings for this plant instance
_sensor  = SENSOR_TOPIC.format(plant_id=PLANT_ID)
_command = COMMAND_TOPIC.format(plant_id=PLANT_ID)
_status  = STATUS_TOPIC.format(plant_id=PLANT_ID)

# ── Simulated environment state ───────────────────────────────────────────────
# Initialise moisture halfway between start and stop thresholds plus a buffer
soil_moisture   = (profile["moisture_min"] + profile["moisture_stop"]) / 2 + 10
temperature     = 24.0   # ambient air temperature in °C
humidity        = 60.0   # relative humidity in %
watering_active = False  # tracks whether the pump is currently ON

# Helper: return the midpoint of a (min, max) tuple
def _mid(rng): return (rng[0] + rng[1]) / 2

# Seed extended sensor values at the midpoint of each plant's optimal range
nitrogen         = _mid(profile["nitrogen"])
phosphorus       = _mid(profile["phosphorus"])
potassium        = _mid(profile["potassium"])
soil_ph          = _mid(profile["soil_ph"])
salinity         = _mid(profile["salinity"])
root_temperature = _mid(profile["root_temperature"])

# ── MQTT setup ────────────────────────────────────────────────────────────────
# Use the newer VERSION2 callback API required by paho-mqtt 2.x
app_version2 = mqtt.CallbackAPIVersion.VERSION2
client = mqtt.Client(callback_api_version=app_version2)


def on_message(client, userdata, msg):
    """Handle incoming WATER_ON / WATER_OFF commands from the controller."""
    global watering_active

    try:
        payload = json.loads(msg.payload.decode())  # decode bytes → dict
        action  = payload.get("action", "")
    except json.JSONDecodeError:
        print("[publisher] Invalid command payload")
        return

    # Update pump state based on command received
    if action == "WATER_ON":
        watering_active = True
    elif action == "WATER_OFF":
        watering_active = False

    print(f"[publisher] Command received: {action}, watering_active={watering_active}")

    # Publish actuator status back to the broker so controller and dashboard know
    status = {
        "plant_id":        PLANT_ID,
        "plant_type":      PLANT_TYPE,
        "watering_active": watering_active,
        "timestamp":       time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    client.publish(_status, json.dumps(status))


# Register the message callback before connecting
client.on_message = on_message
client.connect(BROKER, PORT)          # connect to the public MQTT broker
client.subscribe(_command)            # listen for watering commands
client.loop_start()                   # start background network thread

print(f"[publisher] Plant: {profile['display_name']}  |  ID: {PLANT_ID}")
print(f"[publisher] Publishing to:            {_sensor}")
print(f"[publisher] Listening for commands on:{_command}")

# ── Main sensor simulation loop ───────────────────────────────────────────────
try:
    while True:
        # Moisture drops naturally over time; rises faster when pump is ON
        soil_moisture -= random.uniform(0.2, 0.8)
        if watering_active:
            soil_moisture += random.uniform(1.5, 3.0)
        soil_moisture = max(0.0, min(100.0, soil_moisture))  # clamp to 0–100

        # Ambient temperature and humidity drift slightly each cycle
        temperature += random.uniform(-0.2, 0.2)
        humidity    += random.uniform(-1.0,  1.0)
        temperature  = max(15.0, min(40.0, temperature))
        humidity     = max(20.0, min(95.0, humidity))

        # NPK nutrients deplete slowly over time (plant consumption)
        nitrogen   += random.uniform(-2.0, 1.0)
        phosphorus += random.uniform(-1.0, 0.5)
        potassium  += random.uniform(-1.5, 0.8)

        # Clamp NPK to 50%–120% of the plant's optimal range
        n_rng = profile["nitrogen"];   nitrogen   = max(n_rng[0]*0.5, min(n_rng[1]*1.2, nitrogen))
        p_rng = profile["phosphorus"]; phosphorus = max(p_rng[0]*0.5, min(p_rng[1]*1.2, phosphorus))
        k_rng = profile["potassium"];  potassium  = max(k_rng[0]*0.5, min(k_rng[1]*1.2, potassium))

        # pH and salinity change very slowly
        soil_ph  += random.uniform(-0.05, 0.05)
        salinity += random.uniform(-0.02, 0.03)

        # Clamp pH and salinity to slightly outside their optimal bounds
        ph_rng  = profile["soil_ph"];  soil_ph  = max(ph_rng[0]*0.9, min(ph_rng[1]*1.1, soil_ph))
        s_rng   = profile["salinity"]; salinity = max(0.0,            min(s_rng[1]*1.5,  salinity))

        # Root temperature loosely follows ambient temperature
        root_temperature += random.uniform(-0.1, 0.1)
        rt_rng = profile["root_temperature"]
        root_temperature = max(rt_rng[0] - 3, min(rt_rng[1] + 3, root_temperature))

        # Build the full sensor reading payload
        reading = {
            "plant_id":         PLANT_ID,
            "plant_type":       PLANT_TYPE,
            "soil_moisture":    round(soil_moisture,    2),
            "temperature":      round(temperature,      2),
            "humidity":         round(humidity,         2),
            "nitrogen":         round(nitrogen,         2),
            "phosphorus":       round(phosphorus,       2),
            "potassium":        round(potassium,        2),
            "soil_ph":          round(soil_ph,          2),
            "salinity":         round(salinity,         3),
            "root_temperature": round(root_temperature, 2),
            "timestamp":        time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Publish the reading to the sensor topic
        client.publish(_sensor, json.dumps(reading))
        print(
            "[publisher] Sent:",
            f"moisture={reading['soil_moisture']},",
            f"pH={reading['soil_ph']},",
            f"N={reading['nitrogen']},",
            f"temp={reading['temperature']}",
        )

        time.sleep(1)  # wait 1 second before next reading

except KeyboardInterrupt:
    print("\n[publisher] Stopped")
finally:
    # Clean up MQTT connection on exit
    client.loop_stop()
    client.disconnect()
