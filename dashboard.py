import json
import math
import threading
import time

import pygame
import paho.mqtt.client as mqtt

from config import BROKER, PORT, PLANT_PROFILES, build_plant_id

WIDTH, HEIGHT = 1120, 760
FPS = 30
PADDING = 20
TOPBAR_H = 56
BOTTOM_H = 52

FONT_TITLE = 28
FONT_HEADER = 20
FONT_SMALL = 14
FONT_TINY = 12

C_BG = (13, 15, 26)
C_CARD = (22, 25, 42)
C_CARD2 = (28, 32, 54)
C_BORDER = (50, 55, 90)
C_TITLE = (235, 240, 255)
C_LABEL = (120, 130, 170)
C_VALUE = (210, 220, 255)
C_DIM = (60, 65, 100)
C_GREEN = (60, 210, 130)
C_YELLOW = (255, 200, 40)
C_RED = (255, 70, 70)
C_BLUE = (60, 160, 255)
C_BLUE_DIM = (35, 55, 90)
C_SEPARATOR = (38, 42, 70)

state: dict[str, dict] = {}
alerts: list[dict] = []
state_lock = threading.Lock()

SENSOR_ORDER = [
    "soil_moisture",
    "temperature",
    "humidity",
    "nitrogen",
    "phosphorus",
    "potassium",
    "soil_ph",
    "salinity",
    "root_temperature",
]

SENSOR_LABELS = {
    "soil_moisture": "Soil Moisture",
    "temperature": "Temperature",
    "humidity": "Humidity",
    "nitrogen": "Nitrogen",
    "phosphorus": "Phosphorus",
    "potassium": "Potassium",
    "soil_ph": "Soil pH",
    "salinity": "Salinity",
    "root_temperature": "Root Temp",
}

SENSOR_UNITS = {
    "soil_moisture": "%",
    "temperature": "°C",
    "humidity": "%",
    "nitrogen": "mg/kg",
    "phosphorus": "mg/kg",
    "potassium": "mg/kg",
    "soil_ph": "",
    "salinity": "dS/m",
    "root_temperature": "°C",
}


def draw_text(surface, text, font, colour, x, y, alpha=255):
    rendered = font.render(str(text), True, colour)
    if alpha < 255:
        rendered.set_alpha(alpha)
    surface.blit(rendered, (x, y))


def draw_rounded_rect(surface, colour, rect, radius=14, border=0, border_colour=None):
    pygame.draw.rect(surface, colour, rect, border_radius=radius)
    if border and border_colour:
        pygame.draw.rect(surface, border_colour, rect, width=border, border_radius=radius)


def glow_rect(surface, colour, rect, radius=14, layers=4):
    r, g, b = colour
    for i in range(layers, 0, -1):
        alpha = int(16 * i)
        expand = i * 3
        glow = pygame.Surface((rect[2] + expand * 2, rect[3] + expand * 2), pygame.SRCALPHA)
        pygame.draw.rect(
            glow,
            (r, g, b, alpha),
            (0, 0, rect[2] + expand * 2, rect[3] + expand * 2),
            border_radius=radius + expand,
        )
        surface.blit(glow, (rect[0] - expand, rect[1] - expand))


def draw_bar(surface, x, y, w, h, value, vmin, vmax, colour):
    pygame.draw.rect(surface, C_SEPARATOR, (x, y, w, h), border_radius=4)
    if value is None or vmin is None or vmax is None or vmax == vmin:
        return
    pct = max(0.0, min(1.0, (float(value) - vmin) / (vmax - vmin)))
    fill = max(4, int(w * pct))
    pygame.draw.rect(surface, colour, (x, y, fill, h), border_radius=4)


def range_for_sensor(sensor_key: str, profile: dict):
    if sensor_key == "soil_moisture":
        return 0, 100
    if sensor_key == "temperature":
        return 15, 40
    if sensor_key == "humidity":
        return 0, 100
    if sensor_key == "nitrogen":
        return profile["nitrogen"]
    if sensor_key == "phosphorus":
        return profile["phosphorus"]
    if sensor_key == "potassium":
        return profile["potassium"]
    if sensor_key == "soil_ph":
        return profile["soil_ph"]
    if sensor_key == "salinity":
        return 0, profile["salinity"][1] * 1.5
    if sensor_key == "root_temperature":
        return profile["root_temperature"]
    return 0, 100


def severity_rank(severity: str) -> int:
    if severity == "CRITICAL":
        return 2
    if severity == "WARNING":
        return 1
    return 0


def health_colour(plant_id: str):
    with state_lock:
        plant_alerts = [a for a in alerts if a.get("plant_id") == plant_id]

    if not plant_alerts:
        return C_GREEN

    worst = max(severity_rank(a.get("severity", "INFO")) for a in plant_alerts)
    if worst == 2:
        return C_RED
    if worst == 1:
        return C_YELLOW
    return C_GREEN


def merge_sensor_payload(payload: dict) -> None:
    plant_id = payload.get("plant_id", "unknown")
    plant_type = payload.get("plant_type", "ficus")

    if plant_id not in state:
        state[plant_id] = {
            "plant_id": plant_id,
            "plant_type": plant_type,
            "timestamp": payload.get("timestamp", "—"),
        }

    state[plant_id]["plant_type"] = plant_type
    state[plant_id]["timestamp"] = payload.get("timestamp", state[plant_id].get("timestamp", "—"))

    for sensor_key in SENSOR_ORDER:
        if sensor_key in payload:
            state[plant_id][sensor_key] = payload[sensor_key]


mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)


def on_message(client, userdata, msg):
    _ = (client, userdata)
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    with state_lock:
        if msg.topic.endswith("/sensor"):
            merge_sensor_payload(payload)
        elif msg.topic.endswith("/alerts"):
            alerts.insert(0, payload)
            del alerts[20:]


mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, PORT)
mqtt_client.subscribe("smartplant/+/sensor")
mqtt_client.subscribe("smartplant/+/alerts")
mqtt_client.loop_start()


def build_reasons(plant_id: str, data: dict, profile: dict, all_alerts: list[dict]) -> list[str]:
    reasons = []
    seen = set()

    for alert in all_alerts:
        if alert.get("plant_id") != plant_id:
            continue

        atype = alert.get("alert_type", "")
        if atype in seen:
            continue

        if atype == "NITROGEN_OUT_OF_RANGE":
            reason = f"Nitrogen: {data.get('nitrogen', '–')} (ok {profile['nitrogen'][0]}–{profile['nitrogen'][1]})"
        elif atype == "PHOSPHORUS_OUT_OF_RANGE":
            reason = f"Phosphorus: {data.get('phosphorus', '–')} (ok {profile['phosphorus'][0]}–{profile['phosphorus'][1]})"
        elif atype == "POTASSIUM_OUT_OF_RANGE":
            reason = f"Potassium: {data.get('potassium', '–')} (ok {profile['potassium'][0]}–{profile['potassium'][1]})"
        elif atype == "PH_OUT_OF_RANGE":
            reason = f"Soil pH: {data.get('soil_ph', '–')} (ok {profile['soil_ph'][0]}–{profile['soil_ph'][1]})"
        elif atype == "HIGH_SALINITY":
            reason = f"Salinity: {data.get('salinity', '–')} dS/m (max {profile['salinity'][1]})"
        elif atype == "ROOT_TEMP_OUT_OF_RANGE":
            reason = f"Root Temp: {data.get('root_temperature', '–')}°C"
        else:
            reason = alert.get("message", atype)

        reasons.append(reason)
        seen.add(atype)

        if len(reasons) >= 4:
            break

    return reasons


def draw_topbar(surface, f_title, f_small, tick):
    draw_rounded_rect(surface, (20, 22, 40), (0, 0, WIDTH, TOPBAR_H), radius=0)
    pygame.draw.line(surface, C_SEPARATOR, (0, TOPBAR_H), (WIDTH, TOPBAR_H))

    pulse = int(180 + 75 * math.sin(tick * 0.08))
    pygame.draw.circle(surface, (60, pulse, 100), (18, 28), 7)

    draw_text(surface, "Smart Plant Monitoring Dashboard", f_title, C_TITLE, 28, 12)
    draw_text(surface, time.strftime("%H:%M:%S"), f_small, C_LABEL, WIDTH - 90, 20)


def draw_alert_feed(surface, font, alert_list):
    y = HEIGHT - BOTTOM_H + 8
    pygame.draw.line(surface, C_SEPARATOR, (PADDING, HEIGHT - BOTTOM_H), (WIDTH - PADDING, HEIGHT - BOTTOM_H))

    cx = PADDING
    draw_text(surface, "Recent alerts:", font, C_DIM, cx, y)
    cx += 95

    for alert in alert_list[:5]:
        sev = alert.get("severity", "INFO")
        colour = C_RED if sev == "CRITICAL" else (C_YELLOW if sev == "WARNING" else C_GREEN)
        txt = f"[{alert.get('plant_type', '?')}] {alert.get('alert_type', '?')}   "
        if cx + len(txt) * 7 > WIDTH - PADDING:
            break
        draw_text(surface, txt, font, colour, cx, y)
        cx += len(txt) * 7


def draw_card(surface, rect, plant_id, data, all_alerts, fonts):
    x, y, w, h = rect
    f_hdr, f_lbl, f_tiny = fonts

    plant_type = data.get("plant_type", "ficus")
    profile = PLANT_PROFILES.get(plant_type, PLANT_PROFILES["ficus"])
    hcol = health_colour(plant_id)
    reasons = build_reasons(plant_id, data, profile, all_alerts)

    glow_rect(surface, hcol, rect, radius=16)
    draw_rounded_rect(surface, C_CARD, rect, radius=16)
    draw_rounded_rect(surface, C_CARD2, (x + 2, y + 2, w - 4, h - 4), radius=14)
    draw_rounded_rect(surface, C_CARD, rect, radius=16, border=2, border_colour=hcol)

    stripe_h = 48
    stripe_s = pygame.Surface((w - 4, stripe_h), pygame.SRCALPHA)
    r, g, b = hcol
    pygame.draw.rect(stripe_s, (r, g, b, 55), (0, 0, w - 4, stripe_h), border_radius=13)
    surface.blit(stripe_s, (x + 2, y + 2))

    draw_text(surface, f"{profile['display_name']} ({plant_id})", f_hdr, C_TITLE, x + 16, y + 12)

    status_text = "Healthy" if hcol == C_GREEN else ("Warning" if hcol == C_YELLOW else "Critical")
    draw_text(surface, f"Status: {status_text}", f_lbl, hcol, x + 16, y + 52)
    draw_text(surface, f"Last update: {data.get('timestamp', '—')}", f_tiny, C_LABEL, x + 16, y + 72)

    ry = y + 92
    for reason in reasons:
        draw_text(surface, f"• {reason}", f_tiny, hcol, x + 16, ry)
        ry += 16

    sep_y = ry + 4
    pygame.draw.line(surface, C_SEPARATOR, (x + 12, sep_y), (x + w - 12, sep_y))
    cy = sep_y + 10

    for sensor_key in SENSOR_ORDER:
        label = SENSOR_LABELS[sensor_key]
        unit = SENSOR_UNITS[sensor_key]
        value = data.get(sensor_key, "–")
        vmin, vmax = range_for_sensor(sensor_key, profile)

        draw_text(surface, label, f_tiny, C_LABEL, x + 14, cy)
        draw_text(surface, f"{value} {unit}".strip(), f_lbl, C_VALUE, x + 170, cy)

        try:
            draw_bar(surface, x + w - 96, cy + 4, 82, 7, float(value), vmin, vmax, hcol)
        except Exception:
            pass

        cy += 22
        pygame.draw.line(surface, C_SEPARATOR, (x + 12, cy - 2), (x + w - 12, cy - 2))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Smart Plant Monitor")
    clock = pygame.time.Clock()

    f_title = pygame.font.SysFont("segoeui", FONT_TITLE, bold=True)
    f_hdr = pygame.font.SysFont("segoeui", FONT_HEADER, bold=True)
    f_lbl = pygame.font.SysFont("segoeui", FONT_SMALL)
    f_tiny = pygame.font.SysFont("segoeui", FONT_TINY)

    tick = 0
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill(C_BG)
        draw_topbar(screen, f_title, f_lbl, tick)

        with state_lock:
            snap_state = dict(state)
            snap_alerts = list(alerts)

        plant_ids = sorted(snap_state.keys())
        if not plant_ids:
            plant_ids = [build_plant_id(ptype) for ptype in PLANT_PROFILES.keys()]

        content_top = TOPBAR_H + 14
        content_bottom = HEIGHT - BOTTOM_H - 12
        content_h = content_bottom - content_top

        cols = 2
        rows = max(1, math.ceil(len(plant_ids) / cols))
        card_w = (WIDTH - PADDING * (cols + 1)) // cols
        card_h = max(240, (content_h - PADDING * (rows - 1)) // rows)

        for idx, plant_id in enumerate(plant_ids):
            col = idx % cols
            row = idx // cols
            x = PADDING + col * (card_w + PADDING)
            y = content_top + row * (card_h + PADDING)

            data = snap_state.get(plant_id)
            if not data:
                continue

            draw_card(screen, (x, y, card_w, card_h), plant_id, data, snap_alerts, (f_hdr, f_lbl, f_tiny))

        draw_alert_feed(screen, f_tiny, snap_alerts)

        pygame.display.flip()
        clock.tick(FPS)
        tick += 1

    pygame.quit()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()


if __name__ == "__main__":
    main()
