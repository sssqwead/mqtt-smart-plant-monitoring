# MQTT Smart Plant Monitoring System

## Overview

This project implements a Smart Plant Monitoring and Automatic Watering System using the MQTT protocol.

The system simulates IoT sensor data (soil moisture, temperature, humidity) and uses a publish/subscribe architecture to control watering automatically.

Data is stored persistently using SQLite.

---

## System Architecture

The system consists of two main components:

### 1. Publisher (Simulated IoT Device)

- Generates sensor data
- Publishes data to MQTT broker
- Listens for watering commands
- Sends actuator status updates

### 2. Controller

- Subscribes to sensor data
- Applies watering logic
- Publishes WATER_ON / WATER_OFF commands
- Stores all data in SQLite database
- Logs system activity

---

## Project Files

- `publisher.py`
- `controller.py`
- `main.py`
- `inspect_db.py`
- `plant_monitoring.db`

---

## MQTT Topics

- smartplant/plant-001/sensor  
- smartplant/plant-001/command  
- smartplant/plant-001/status  

---

## Technologies Used

- Python
- MQTT (HiveMQ public broker)
- SQLite
- JSON
- paho-mqtt

---

## Installation

Install dependencies:

pip install -r requirements.txt
---

## Running the System

### Recommended (run both services)

python main.py

### Run separately

Terminal 1:
python controller.py

Terminal 2:
python publisher.py
---

## Database

The SQLite database file is created automatically:
plant_monitoring.db

Tables:
- sensor_data  
- activity_log  

---

## Inspect Database
python inspect_db.py
This will display:
- Latest sensor readings
- Latest system activity




