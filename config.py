# ─────────────────────────────────────────────
#  Plant Monitoring – Central Configuration
#  All constants and plant profiles live here.
#  No other file should hardcode these values.
# ─────────────────────────────────────────────

# MQTT broker address (public HiveMQ broker, no auth required)
BROKER = "broker.hivemq.com"
PORT   = 1883  # default unencrypted MQTT port

# Topic templates — use .format(plant_id=...) before publishing/subscribing
SENSOR_TOPIC  = "smartplant/{plant_id}/sensor"   # publisher → broker → controller
COMMAND_TOPIC = "smartplant/{plant_id}/command"  # controller → broker → publisher
STATUS_TOPIC  = "smartplant/{plant_id}/status"   # publisher → broker (actuator state)
ALERT_TOPIC   = "smartplant/{plant_id}/alerts"   # controller → broker (severity alerts)

# Path to the local SQLite database file
DB_PATH = "plant_monitoring.db"

# Minimum seconds between two watering commands for the same plant
# Prevents rapid ON/OFF toggling while moisture stabilises
COOLDOWN_SECONDS = 20

# ─────────────────────────────────────────────
#  Plant Profiles
#  Each key is a plant type identifier string.
#  Numeric ranges are (min, max) tuples.
#  Adding a new plant only requires a new entry here.
# ─────────────────────────────────────────────
PLANT_PROFILES = {
    "ficus": {
        "display_name": "Ficus",

        # Moisture thresholds (percentage 0–100)
        "moisture_min":      40.0,   # trigger WATER_ON below this
        "moisture_stop":     60.0,   # trigger WATER_OFF above this
        "moisture_warning":  30.0,   # publish WARNING alert below this
        "moisture_critical": 20.0,   # publish CRITICAL alert below this

        # NPK nutrients in mg/kg — optimal range for ficus
        "nitrogen":    (150, 300),
        "phosphorus":  (50,  150),
        "potassium":   (100, 250),

        # Soil chemistry
        "soil_ph":  (5.5, 7.0),   # slightly acidic to neutral
        "salinity": (0.0, 1.5),   # dS/m — ficus is salt-sensitive

        # Root zone temperature in °C
        "root_temperature": (18.0, 28.0),
    },
    "cactus": {
        "display_name": "Cactus",

        # Cactus needs far less water than ficus
        "moisture_min":      15.0,
        "moisture_stop":     25.0,
        "moisture_warning":  10.0,
        "moisture_critical":  5.0,

        # Lower NPK demand — cactus grows slowly
        "nitrogen":   (50,  150),
        "phosphorus": (20,   80),
        "potassium":  (50,  150),

        # Tolerates slightly higher pH and salinity than ficus
        "soil_ph":  (6.0, 7.5),
        "salinity": (0.0, 2.5),

        # Wider temperature tolerance — mimics arid environment
        "root_temperature": (15.0, 35.0),
    },
}

# Plant type used when no CLI argument is provided
DEFAULT_PLANT = "ficus"