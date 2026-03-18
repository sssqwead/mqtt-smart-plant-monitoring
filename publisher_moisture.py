from __future__ import annotations

import json
import random
import sys
import time

import paho.mqtt.client as mqtt

from config import (
    BROKER,
    DEFAULT_PLANT,
    PLANT_PROFILES,
    PORT,
    SENSOR_TOPIC,
    COMMAND_TOPIC,
    STATUS_TOPIC,
    build_plant_id,
)


class SensorPublisher:
    def __init__(self, plant_type: str) -> None:
        plant_type = plant_type.lower()
        if plant_type not in PLANT_PROFILES:
            raise ValueError(f"Unknown plant type: {plant_type}")

        self.plant_type = plant_type
        self.plant_id = build_plant_id(plant_type)
        self.sensor_topic = SENSOR_TOPIC.format(plant_id=self.plant_id)
        self.command_topic = COMMAND_TOPIC.format(plant_id=self.plant_id)
        self.status_topic = STATUS_TOPIC.format(plant_id=self.plant_id)

        profile = PLANT_PROFILES[self.plant_type]
        self.value = random.uniform(profile["moisture_min"], profile["moisture_stop"])
        self.watering_active = False

        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self.on_message

    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        _ = (client, userdata)
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            return

        action = payload.get("action", "")
        if action == "WATER_ON":
            self.watering_active = True
        elif action == "WATER_OFF":
            self.watering_active = False

        print(f"[publisher_moisture] command={action} watering_active={self.watering_active}")
        self.publish_status()

    def _next_value(self) -> float:
        self.value -= random.uniform(0.4, 1.0)
        if self.watering_active:
            self.value += random.uniform(2.0, 4.0)
        self.value = max(0.0, min(100.0, self.value))
        return round(self.value, 2)

    def publish_status(self) -> None:
        payload = {
            "plant_id": self.plant_id,
            "plant_type": self.plant_type,
            "watering_active": self.watering_active,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.client.publish(self.status_topic, json.dumps(payload))

    def publish(self) -> None:
        self.client.connect(BROKER, PORT)
        self.client.subscribe(self.command_topic)
        self.client.loop_start()
        print(f"[publisher_moisture] sensor topic: {self.sensor_topic}")
        print(f"[publisher_moisture] command topic: {self.command_topic}")

        try:
            while True:
                payload = {
                    "plant_id": self.plant_id,
                    "plant_type": self.plant_type,
                    "soil_moisture": self._next_value(),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                self.client.publish(self.sensor_topic, json.dumps(payload))
                self.publish_status()
                print(
                    f"[publisher_moisture] sent: {payload['soil_moisture']}% "
                    f"watering={self.watering_active}"
                )
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[publisher_moisture] stopped")
        finally:
            self.client.loop_stop()
            self.client.disconnect()


def main() -> int:
    plant_type = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PLANT
    publisher = SensorPublisher(plant_type)
    publisher.publish()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
