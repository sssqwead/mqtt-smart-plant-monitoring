"""
Real-time Pygame dashboard for Smart Plant Monitoring.
Run:  python dashboard.py
Subscribes to all plant MQTT topics and renders a live two-panel display.
Each plant gets its own card showing live sensor values, health state,
alert reasons, and a mini progress bar for every parameter.
"""

import json
import threading
import time
import math

import pygame
import paho.mqtt.client as mqtt

from config import (
    BROKER, PORT,
    PLANT_PROFILES,
)

# Arystan's nutrient module
from nutrient_module import build_npk_alert_reason

# ── Window and layout constants ───────────────────────────────────────────────
WIDTH, HEIGHT = 960, 660
FPS = 30
PADDING = 22
CARD_W = (WIDTH - PADDING * 3) // 2
CARD_H = HEIGHT - 130

# ── Font sizes ────────────────────────────────────────────────────────────────
FONT_TITLE = 30
FONT_HEADER = 21
FONT_BODY = 17
FONT_SMALL = 14
FONT_TINY = 12

# ── Colour palette ────────────────────────────────────────────────────────────
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

# ── Shared state ──────────────────────────────────────────────────────────────
state: dict = {}
water_state: dict = {}
alerts: list = []

state_lock = threading.Lock()


def _health_colour(plant_id):
    """
    Determine the health colour for a plant card.
    Looks at ALL recent alerts for this plant and returns the worst severity colour.
    """
    with state_lock:
        plant_alerts = [a for a in alerts if a.get("plant_id") == plant_id]

    if not plant_alerts:
        return C_GREEN

    severities = {a.get("severity", "INFO") for a in plant_alerts}

    if "CRITICAL" in severities:
        return C_RED
    if "WARNING" in severities:
        return C_YELLOW
    return C_GREEN


# ── MQTT setup ────────────────────────────────────────────────────────────────
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)


def on_message(client, userdata, msg):
    """
    MQTT message callback — called in the MQTT background thread every time
    a message arrives on any subscribed topic.
    """
    try:
        payload = json.loads(msg.payload.decode())
    except Exception:
        return

    plant_id = payload.get("plant_id", "unknown")

    with state_lock:
        if msg.topic.endswith("/sensor"):
            state[plant_id] = payload

        elif msg.topic.endswith("/status"):
            water_state[plant_id] = payload.get("watering_active", False)

        elif msg.topic.endswith("/alerts"):
            alerts.insert(0, payload)
            del alerts[6:]


mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, PORT)
mqtt_client.subscribe("smartplant/+/sensor")
mqtt_client.subscribe("smartplant/+/status")
mqtt_client.subscribe("smartplant/+/alerts")
mqtt_client.loop_start()


# ── Drawing helper functions ──────────────────────────────────────────────────

def draw_text(surface, text, font, colour, x, y, alpha=255):
    rendered = font.render(text, True, colour)
    if alpha < 255:
        rendered.set_alpha(alpha)
    surface.blit(rendered, (x, y))


def draw_rounded_rect(surface, colour, rect, radius=14, border=0, border_colour=None):
    pygame.draw.rect(surface, colour, rect, border_radius=radius)
    if border and border_colour:
        pygame.draw.rect(surface, border_colour, rect, width=border, border_radius=radius)


def draw_bar(surface, x, y, w, h, value, vmin, vmax, colour):
    pygame.draw.rect(surface, C_SEPARATOR, (x, y, w, h), border_radius=4)

    pct = max(0.0, min(1.0, (value - vmin) / (vmax - vmin))) if vmax != vmin else 0
    fill = max(4, int(w * pct))

    pygame.draw.rect(surface, colour, (x, y, fill, h), border_radius=4)


def glow_rect(surface, colour, rect, radius=14, layers=4):
    r, g, b = colour
    for i in range(layers, 0, -1):
        alpha = int(18 * i)
        expand = i * 3
        glow_r = (
            rect[0] - expand,
            rect[1] - expand,
            rect[2] + expand * 2,
            rect[3] + expand * 2,
        )
        glow_s = pygame.Surface((glow_r[2], glow_r[3]), pygame.SRCALPHA)
        pygame.draw.rect(
            glow_s, (r, g, b, alpha),
            (0, 0, glow_r[2], glow_r[3]),
            border_radius=radius + expand,
        )
        surface.blit(glow_s, (glow_r[0], glow_r[1]))


def draw_card(surface, rect, _unused, title, health_col, watering,
              alert_reasons, profile, data, fonts):
    x, y, w, h = rect
    f_hdr, f_body, f_lbl, f_tiny = fonts

    glow_rect(surface, health_col, (x, y, w, h), radius=16)

    draw_rounded_rect(surface, C_CARD, (x, y, w, h), radius=16)
    draw_rounded_rect(surface, C_CARD2, (x + 2, y + 2, w - 4, h - 4), radius=14)

    stripe_h = 48
    stripe_s = pygame.Surface((w - 4, stripe_h), pygame.SRCALPHA)
    r, g, b = health_col
    pygame.draw.rect(stripe_s, (r, g, b, 55), (0, 0, w - 4, stripe_h), border_radius=13)
    surface.blit(stripe_s, (x + 2, y + 2))

    draw_rounded_rect(surface, C_CARD, (x, y, w, h),
                      radius=16, border=2, border_colour=health_col)

    draw_text(surface, title, f_hdr, C_TITLE, x + 16, y + 12)

    if watering:
        badge_col = C_BLUE
        badge_txt = "WATERING"
    else:
        badge_col = C_BLUE_DIM
        badge_txt = "  idle"
    bx, by, bw, bh = x + w - 138, y + 10, 128, 28
    draw_rounded_rect(surface, badge_col, (bx, by, bw, bh), radius=9)
    draw_text(surface, badge_txt, f_lbl, C_TITLE, bx + 10, by + 7)

    if health_col == C_GREEN:
        hlabel, dot = "Healthy", "●"
    elif health_col == C_YELLOW:
        hlabel, dot = "Warning", "!"
    else:
        hlabel, dot = "Critical", "X"
    draw_text(surface, f"{dot} {hlabel}", f_lbl, health_col, x + 16, y + 52)

    reason_y = y + 70
    for reason in alert_reasons:
        draw_text(surface, f"  → {reason}", f_tiny, health_col, x + 16, reason_y)
        reason_y += 15

    sep_y = reason_y + 4
    pygame.draw.line(surface, C_SEPARATOR, (x + 12, sep_y), (x + w - 12, sep_y))
    cy = sep_y + 10

    bar_rows = [
        ("Soil Moisture", data.get("soil_moisture", "–"), "%", 0, 100),
        ("Temperature", data.get("temperature", "–"), "°C", 15, 40),
        ("Humidity", data.get("humidity", "–"), "%", 0, 100),
        ("Nitrogen", data.get("nitrogen", "–"), "mg/kg", *profile["nitrogen"]),
        ("Phosphorus", data.get("phosphorus", "–"), "mg/kg", *profile["phosphorus"]),
        ("Potassium", data.get("potassium", "–"), "mg/kg", *profile["potassium"]),
        ("Soil pH", data.get("soil_ph", "–"), "", *profile["soil_ph"]),
        ("Salinity", data.get("salinity", "–"), "dS/m", 0, profile["salinity"][1] * 1.5),
        ("Root Temp", data.get("root_temperature", "–"), "°C", *profile["root_temperature"]),
    ]

    for label, value, unit, vmin, vmax in bar_rows:
        if cy + 22 > y + h - 8:
            break

        draw_text(surface, label, f_tiny, C_LABEL, x + 14, cy)

        val_str = f"{value} {unit}".strip()
        draw_text(surface, val_str, f_lbl, C_VALUE, x + 178, cy)

        try:
            draw_bar(surface, x + w - 98, cy + 3, 82, 7,
                     float(value), vmin, vmax, health_col)
        except (ValueError, TypeError):
            pass

        cy += 22
        pygame.draw.line(surface, C_SEPARATOR, (x + 12, cy - 2), (x + w - 12, cy - 2))


def draw_topbar(surface, fonts, tick):
    f_title, f_small = fonts

    draw_rounded_rect(surface, (20, 22, 40), (0, 0, WIDTH, 56), radius=0)
    pygame.draw.line(surface, C_SEPARATOR, (0, 56), (WIDTH, 56))

    pulse = int(180 + 75 * math.sin(tick * 0.08))
    pygame.draw.circle(surface, (60, pulse, 100), (18, 28), 7)

    draw_text(surface, "Smart Plant Monitoring Dashboard", f_title, C_TITLE, 28, 12)

    ts = time.strftime("%H:%M:%S")
    draw_text(surface, ts, f_small, C_LABEL, WIDTH - 80, 20)


def draw_alert_feed(surface, font, alert_list, y):
    pygame.draw.line(surface, C_SEPARATOR, (PADDING, y), (WIDTH - PADDING, y))

    cx = PADDING
    draw_text(surface, "Recent alerts: ", font, C_DIM, cx, y + 6)
    cx += 105

    for a in alert_list[:4]:
        sev = a.get("severity", "INFO")
        col = C_RED if sev == "CRITICAL" else (C_YELLOW if sev == "WARNING" else C_GREEN)

        txt = f"[{a.get('plant_type','?')}] {a.get('alert_type','?')}  "

        if cx + len(txt) * 7 > WIDTH - PADDING:
            break

        draw_text(surface, txt, font, col, cx, y + 6)
        cx += len(txt) * 7


# ── Main render loop ──────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Smart Plant Monitor")
    clock = pygame.time.Clock()
    tick = 0

    f_title = pygame.font.SysFont("segoeui", FONT_TITLE, bold=True)
    f_hdr = pygame.font.SysFont("segoeui", FONT_HEADER, bold=True)
    f_body = pygame.font.SysFont("segoeui", FONT_BODY)
    f_lbl = pygame.font.SysFont("segoeui", FONT_SMALL)
    f_tiny = pygame.font.SysFont("segoeui", FONT_TINY)

    known_plants = list(PLANT_PROFILES.keys())

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill(C_BG)
        draw_topbar(screen, (f_title, f_lbl), tick)

        with state_lock:
            snap_state = dict(state)
            snap_water = dict(water_state)
            snap_alerts = list(alerts)

        for idx, ptype in enumerate(known_plants):
            pid = f"plant-{ptype}-001"
            data = snap_state.get(pid, {})
            watering = snap_water.get(pid, False)
            hcol = _health_colour(pid)
            profile = PLANT_PROFILES[ptype]

            cx = PADDING + idx * (CARD_W + PADDING)
            cy = 66

            if not data:
                glow_rect(screen, C_BORDER, (cx, cy, CARD_W, CARD_H), radius=16)
                draw_rounded_rect(screen, C_CARD, (cx, cy, CARD_W, CARD_H),
                                  radius=16, border=2, border_colour=C_BORDER)
                draw_text(screen, profile["display_name"], f_hdr, C_TITLE, cx + 16, cy + 14)
                draw_text(screen, "Waiting for data…", f_lbl, C_LABEL, cx + 16, cy + 52)
                continue

            reasons = []
            seen = set()
            for a in snap_alerts:
                if a.get("plant_id") == pid:
                    atype = a.get("alert_type", "")
                    if atype in seen:
                        continue

                    # Arystan's NPK alert formatting
                    npk_reason = build_npk_alert_reason(atype, data, profile)

                    if npk_reason is not None:
                        short = npk_reason
                    elif atype == "PH_OUT_OF_RANGE":
                        short = f"Soil pH: {data.get('soil_ph','–')} (ok {profile['soil_ph'][0]}–{profile['soil_ph'][1]})"
                    elif atype == "HIGH_SALINITY":
                        short = f"Salinity: {data.get('salinity','–')} dS/m (max {profile['salinity'][1]})"
                    elif atype == "ROOT_TEMP_OUT_OF_RANGE":
                        short = f"Root Temp: {data.get('root_temperature','–')}°C (ok {profile['root_temperature'][0]}–{profile['root_temperature'][1]})"
                    elif atype == "LOW_MOISTURE":
                        short = f"Moisture: {data.get('soil_moisture','–')}% (min {profile['moisture_warning']}%)"
                    else:
                        short = atype

                    reasons.append(short)
                    seen.add(atype)

                if len(reasons) >= 3:
                    break

            draw_card(
                screen, (cx, cy, CARD_W, CARD_H),
                None, profile["display_name"], hcol, watering,
                reasons, profile, data,
                (f_hdr, f_body, f_lbl, f_tiny)
            )

        feed_y = 66 + CARD_H + 8
        if feed_y + 30 <= HEIGHT:
            draw_alert_feed(screen, f_tiny, snap_alerts, feed_y)

        pygame.display.flip()
        clock.tick(FPS)
        tick += 1

    pygame.quit()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()


if __name__ == "__main__":
    main()
