from __future__ import annotations

import json
import time

import paho.mqtt.client as mqtt

from config import ALERT_TOPIC, BROKER, PLANT_PROFILES, PORT, SENSOR_TOPIC


class SensorController:
    def __init__(self) -> None:
        self.sensor_key = "soil_ph"
        self.alert_type = "PH_OUT_OF_RANGE"
        self.topic_sub = SENSOR_TOPIC.replace("{plant_id}", "+")
        self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_message = self.on_message
        self.active_alerts: dict[str, str] = {}

    def _severity_for_value(self, value: float, low: float, high: float) -> tuple[str, bool]:
        margin_warn = 0.10
        margin_crit = 0.20
        span = high - low if high != low else 1.0

        if value < low:
            deviation = (low - value) / span
        elif value > high:
            deviation = (value - high) / span
        else:
            return "INFO", False

        if deviation >= margin_crit:
            return "CRITICAL", True
        return "WARNING", True

    def _publish_alert(self, plant_id: str, plant_type: str, severity: str, value: float, low: float, high: float) -> None:
        if self.active_alerts.get(plant_id) == severity:
            return

        self.active_alerts[plant_id] = severity

        topic = ALERT_TOPIC.format(plant_id=plant_id)
        payload = {
            "plant_id": plant_id,
            "plant_type": plant_type,
            "alert_type": self.alert_type,
            "severity": severity,
            "message": f"Soil pH out of range: {value} (optimal {low}–{high})",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.client.publish(topic, json.dumps(payload))
        print(f"[controller_ph] ALERT [{severity}] {payload['message']}")

    def _clear_alert(self, plant_id: str) -> None:
        self.active_alerts.pop(plant_id, None)

    def on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        _ = (client, userdata)
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            return

        if self.sensor_key not in payload:
            return

        plant_id = payload.get("plant_id", "unknown")
        plant_type = payload.get("plant_type", "ficus")
        profile = PLANT_PROFILES.get(plant_type)
        if profile is None:
            return

        value = float(payload[self.sensor_key])
        low, high = profile["soil_ph"]

        print(
            "[controller_ph]",
            payload.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
            plant_id,
            f"soil_ph={value}",
        )

        severity, out_of_range = self._severity_for_value(value, low, high)
        if out_of_range:
            self._publish_alert(plant_id, plant_type, severity, value, low, high)
        else:
            self._clear_alert(plant_id)

    def run(self) -> None:
        self.client.connect(BROKER, PORT)
        self.client.subscribe(self.topic_sub)
        print(f"[controller_ph] listening: {self.topic_sub}")
        self.client.loop_forever()


def main() -> int:
    controller = SensorController()
    try:
        controller.run()
    except KeyboardInterrupt:
        print("\n[controller_ph] stopped")
        controller.client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
