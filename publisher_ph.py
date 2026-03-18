from __future__ import annotations

import json
import random
import sys
import time

import paho.mqtt.client as mqtt

from config import BROKER, DEFAULT_PLANT, PLANT_PROFILES, PORT, SENSOR_TOPIC, build_plant_id


class SensorPublisher:
    def __init__(self, plant_type: str) -> None:
        plant_type = plant_type.lower()
        if plant_type not in PLANT_PROFILES:
            raise ValueError(f"Unknown plant type: {plant_type}")

        self.plant_type = plant_type
        self.plant_id = build_plant_id(plant_type)
        self.topic = SENSOR_TOPIC.format(plant_id=self.plant_id)

        low, high = PLANT_PROFILES[self.plant_type]["soil_ph"]
        self.value = random.uniform(low, high)

        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    def _next_value(self) -> float:
        low, high = PLANT_PROFILES[self.plant_type]["soil_ph"]
        self.value += random.uniform(-0.08, 0.08)
        self.value = max(low * 0.8, min(high * 1.2, self.value))
        return round(self.value, 2)

    def publish(self) -> None:
        self.client.connect(BROKER, PORT)
        self.client.loop_start()
        print(f"[publisher_ph] topic: {self.topic}")

        try:
            while True:
                payload = {
                    "plant_id": self.plant_id,
                    "plant_type": self.plant_type,
                    "soil_ph": self._next_value(),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                self.client.publish(self.topic, json.dumps(payload))
                print(f"[publisher_ph] sent: {payload['soil_ph']}")
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[publisher_ph] stopped")
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
