# MQTT Smart Plant Monitoring System

## Aims

This project aims to design and implement an enhanced IoT-based smart plant monitoring system that simulates real-world sensor behaviour, applies plant-specific intelligent watering logic, and provides a real-time graphical interface for environmental health assessment.

---

## Objectives

1. Extend the existing MQTT publish/subscribe architecture to support advanced soil parameters (NPK, pH, salinity, root temperature).
2. Implement multi-plant support with configurable, species-specific threshold profiles.
3. Develop a severity-based alerting system (INFO / WARNING / CRITICAL) published over dedicated MQTT topics.
4. Persist all sensor readings and system events in a structured SQLite database, including severity metadata.
5. Deliver a real-time Pygame dashboard that visually reflects plant health and watering status.

---

## Research Questions

- How can a lightweight MQTT architecture be extended to support heterogeneous IoT sensor data without redesigning the core system?
- To what extent can species-specific threshold profiles improve the accuracy and appropriateness of automated watering decisions compared to a single universal threshold?
- How effectively can a local simulation reproduce biologically realistic sensor behaviour for multiple plant types?

---

## Methodology

The system follows an incremental extension methodology. The original two-component architecture (Publisher + Controller) was retained and extended rather than replaced, in order to preserve system stability and demonstrate iterative software development practice.

A centralised configuration file (`config.py`) was introduced to define all plant profiles and MQTT constants, eliminating magic numbers and making the system maintainable. Sensor simulation was extended to include six additional parameters, each modelled with realistic drift behaviours. The controller was upgraded with per-plant evaluation functions and a dedicated alert publishing pipeline. A new Pygame dashboard component was added as a passive subscriber, consuming live MQTT data without interfering with the core control loop.

---

## System Architecture

```
Publisher (ficus)  ──┐
                     ├──► MQTT Broker (HiveMQ) ──► Controller ──► SQLite DB
Publisher (cactus) ──┘         │
                               └──────────────────► Dashboard (Pygame)
```

### Components

**publisher.py** — Simulated IoT device. Accepts a plant type argument (`ficus` or `cactus`), generates biologically realistic sensor readings, publishes them to the sensor topic, and responds to WATER_ON / WATER_OFF commands.

**controller.py** — Subscribes to all plant sensor topics via wildcard. Evaluates each reading against the plant-specific profile. Sends watering commands and publishes structured alerts with severity levels to `smartplant/{plant_id}/alerts`.

**dashboard.py** — Real-time Pygame GUI. Subscribes to sensor, status, and alert topics. Renders a two-panel display with live sensor values, watering state, and a colour-coded health indicator (green / yellow / red).

**config.py** — Central configuration. Defines MQTT settings, topic templates, and all plant threshold profiles.

**inspect_db.py** — CLI utility to query and display recent sensor data and activity logs.

---

## Multi-Plant Logic

Each plant type is defined as a profile dictionary in `config.py` containing thresholds for all monitored parameters. The controller resolves the correct profile from the `plant_type` field in each incoming sensor message and applies that profile's thresholds exclusively.

| Parameter        | Ficus 🌿            | Cactus 🌵           |
|------------------|---------------------|---------------------|
| Moisture start   | 40 %                | 15 %                |
| Moisture stop    | 60 %                | 25 %                |
| Nitrogen (mg/kg) | 150 – 300           | 50 – 150            |
| Phosphorus       | 50 – 150            | 20 – 80             |
| Potassium        | 100 – 250           | 50 – 150            |
| Soil pH          | 5.5 – 7.0           | 6.0 – 7.5           |
| Salinity (dS/m)  | 0.0 – 1.5           | 0.0 – 2.5           |
| Root temp (°C)   | 18 – 28             | 15 – 35             |

Adding a new plant type requires only a new entry in `PLANT_PROFILES` inside `config.py` — no other files need modification.

---

## Alert System

Alerts are published to `smartplant/{plant_id}/alerts` and stored in `activity_log` with a `severity` field.

| Severity | Condition |
|----------|-----------|
| INFO     | All values within range |
| WARNING  | Value deviates up to 20 % beyond threshold |
| CRITICAL | Value deviates more than 20 % beyond threshold |

---

## Technologies Used

- Python 3.10+
- MQTT via HiveMQ public broker
- paho-mqtt 2.1.0
- SQLite (via standard library)
- Pygame 2.5+
- JSON

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Running the System

### Recommended (all services at once)
```bash
python main.py
```

---

## Database

Tables:

- `sensor_data` — stores all sensor readings including plant type and extended parameters
- `activity_log` — stores commands, alerts, and system events with severity

```bash
python inspect_db.py
```
