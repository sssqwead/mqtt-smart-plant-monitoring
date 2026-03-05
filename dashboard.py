"""
Real-time Pygame dashboard for Smart Plant Monitoring.
Run:  python dashboard.py
Subscribes to all plant MQTT topics and renders a live two-panel display.
Each plant gets its own card showing live sensor values, health state,
alert reasons, and a mini progress bar for every parameter.
"""

import json       # for decoding MQTT payloads from bytes to Python dicts
import threading  # for state_lock — protects shared data between MQTT and UI threads
import time       # for the live clock shown in the top bar
import math       # for math.sin() used in the pulsing animation

import pygame                    # GUI library — handles window, drawing, fonts, events
import paho.mqtt.client as mqtt  # MQTT client — receives live sensor data over the network

from config import (
    BROKER, PORT,      # MQTT broker address and port number
    PLANT_PROFILES,    # dict of plant types → threshold profiles
)

# ── Window and layout constants ───────────────────────────────────────────────
WIDTH, HEIGHT = 960, 660    # total window size in pixels
FPS           = 30          # render loop speed — 30 frames per second
PADDING       = 22          # space between window edges and cards, and between the two cards
CARD_W        = (WIDTH - PADDING * 3) // 2   # each card takes up half the width minus padding
CARD_H        = HEIGHT - 130  # card height leaves room for the top bar and bottom alert feed

# ── Font sizes (in points) ────────────────────────────────────────────────────
FONT_TITLE  = 30   # dashboard title in the top bar
FONT_HEADER = 21   # plant name inside the card header
FONT_BODY   = 17   # not used directly but kept for reference
FONT_SMALL  = 14   # sensor value text and badge labels
FONT_TINY   = 12   # sensor row labels, alert reasons, and alert feed

# ── Colour palette (all RGB tuples) ──────────────────────────────────────────
C_BG         = (13,  15,  26)   # deep dark navy — main window background
C_CARD       = (22,  25,  42)   # card outer background layer
C_CARD2      = (28,  32,  54)   # card inner background — slightly lighter for depth illusion
C_BORDER     = (50,  55,  90)   # default border colour when no data has arrived yet
C_TITLE      = (235, 240, 255)  # near-white — used for primary text like plant name and values
C_LABEL      = (120, 130, 170)  # muted blue-purple — used for secondary labels
C_VALUE      = (210, 220, 255)  # bright lavender — used for sensor value numbers
C_DIM        = (60,  65, 100)   # very muted — used for the "Recent alerts:" prefix text
C_GREEN      = (60,  210, 130)  # healthy state — all values within range
C_YELLOW     = (255, 200,  40)  # warning state — at least one value slightly out of range
C_RED        = (255,  70,  70)  # critical state — at least one value far out of range
C_BLUE       = (60,  160, 255)  # active watering badge background
C_BLUE_DIM   = (35,  55,  90)   # idle watering badge background — dark and muted
C_SEPARATOR  = (38,  42,  70)   # thin line colour used between sensor rows

# ── Shared state (modified by MQTT thread, read by UI thread) ─────────────────
state: dict       = {}   # maps plant_id → latest sensor reading dict
water_state: dict = {}   # maps plant_id → bool: True means pump is currently ON
alerts: list      = []   # list of the 6 most recent alert payloads, newest first

# Lock must be acquired before reading or writing any of the three variables above
# because the MQTT callback runs in a separate background thread
state_lock = threading.Lock()


def _health_colour(plant_id):
    """
    Determine the health colour for a plant card.
    Looks at ALL recent alerts for this plant (not just the latest one)
    and returns the colour for the worst severity found.
    This prevents card flickering when alerts of mixed severity arrive.
    """
    with state_lock:
        # Filter alerts to only those belonging to this specific plant
        plant_alerts = [a for a in alerts if a.get("plant_id") == plant_id]

    if not plant_alerts:
        return C_GREEN  # no alerts at all — plant is fully healthy

    # Collect all unique severity strings from this plant's recent alerts
    severities = {a.get("severity", "INFO") for a in plant_alerts}

    # Return the most severe colour present
    if "CRITICAL" in severities:
        return C_RED
    if "WARNING" in severities:
        return C_YELLOW
    return C_GREEN


# ── MQTT setup ────────────────────────────────────────────────────────────────
# Dashboard uses VERSION2 callback API required by paho-mqtt 2.x
mqtt_client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)


def on_message(client, userdata, msg):
    """
    MQTT message callback — called in the MQTT background thread every time
    a message arrives on any subscribed topic.
    Updates shared state protected by state_lock.
    """
    try:
        payload = json.loads(msg.payload.decode())  # decode raw bytes → Python dict
    except Exception:
        return  # silently ignore any malformed non-JSON messages

    plant_id = payload.get("plant_id", "unknown")

    with state_lock:  # acquire lock before touching shared state
        if msg.topic.endswith("/sensor"):
            # Overwrite with the latest sensor reading for this plant
            state[plant_id] = payload

        elif msg.topic.endswith("/status"):
            # Update whether the watering pump is currently ON or OFF
            water_state[plant_id] = payload.get("watering_active", False)

        elif msg.topic.endswith("/alerts"):
            # Prepend new alert so index 0 is always the most recent
            alerts.insert(0, payload)
            del alerts[6:]  # cap the list at 6 entries to save memory


# Connect to MQTT broker and subscribe to all plant topics via wildcards
# '+' is a single-level wildcard — matches any plant ID like "plant-ficus-001"
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, PORT)
mqtt_client.subscribe("smartplant/+/sensor")   # live sensor readings
mqtt_client.subscribe("smartplant/+/status")   # pump on/off status
mqtt_client.subscribe("smartplant/+/alerts")   # threshold violation alerts
mqtt_client.loop_start()  # starts a background thread that handles all MQTT networking


# ── Drawing helper functions ──────────────────────────────────────────────────

def draw_text(surface, text, font, colour, x, y, alpha=255):
    """
    Render a text string onto a surface at pixel position (x, y).
    Optional alpha parameter makes the text semi-transparent (0=invisible, 255=opaque).
    """
    rendered = font.render(text, True, colour)
    if alpha < 255:
        rendered.set_alpha(alpha)
    surface.blit(rendered, (x, y))


def draw_rounded_rect(surface, colour, rect, radius=14, border=0, border_colour=None):
    """
    Draw a filled rounded rectangle.
    If border > 0 and border_colour is provided, also draws an outline.
    radius controls how rounded the corners are in pixels.
    """
    pygame.draw.rect(surface, colour, rect, border_radius=radius)
    if border and border_colour:
        pygame.draw.rect(surface, border_colour, rect, width=border, border_radius=radius)


def draw_bar(surface, x, y, w, h, value, vmin, vmax, colour):
    """
    Draw a horizontal mini progress bar at (x, y) with size (w × h).
    The fill amount represents where 'value' sits between vmin and vmax.
    A dark background track is drawn first, then the coloured fill on top.
    """
    # Draw the empty track (dark background)
    pygame.draw.rect(surface, C_SEPARATOR, (x, y, w, h), border_radius=4)

    # Calculate fill fraction clamped between 0 and 1
    pct  = max(0.0, min(1.0, (value - vmin) / (vmax - vmin))) if vmax != vmin else 0
    fill = max(4, int(w * pct))  # minimum 4px so the bar is always visible

    # Draw the coloured fill representing the current value
    pygame.draw.rect(surface, colour, (x, y, fill, h), border_radius=4)


def glow_rect(surface, colour, rect, radius=14, layers=4):
    """
    Draw a soft glowing halo effect around a rectangle.
    Achieved by drawing multiple semi-transparent expanding rectangles.
    'layers' controls how thick/soft the glow appears.
    Each layer gets slightly more transparent and slightly larger.
    """
    r, g, b = colour
    for i in range(layers, 0, -1):
        alpha  = int(18 * i)    # outermost layer is most transparent
        expand = i * 3          # each layer expands 3px beyond the previous
        glow_r = (
            rect[0] - expand,
            rect[1] - expand,
            rect[2] + expand * 2,
            rect[3] + expand * 2,
        )
        # Create a transparent surface the size of this glow layer
        glow_s = pygame.Surface((glow_r[2], glow_r[3]), pygame.SRCALPHA)
        pygame.draw.rect(
            glow_s, (r, g, b, alpha),
            (0, 0, glow_r[2], glow_r[3]),
            border_radius=radius + expand,
        )
        surface.blit(glow_s, (glow_r[0], glow_r[1]))


def draw_card(surface, rect, _unused, title, health_col, watering,
              alert_reasons, profile, data, fonts):
    """
    Render a complete plant card including:
    - Glow halo around the card border
    - Two-tone card background for depth
    - Coloured accent stripe at the top
    - Plant name and watering badge
    - Health status label and alert reason lines
    - Separator line between alerts and sensor rows
    - Sensor rows with labels, values, and mini progress bars
    """
    x, y, w, h = rect
    f_hdr, f_body, f_lbl, f_tiny = fonts  # unpack the four font sizes used in the card

    # -- Glow effect behind the card --
    # Draws expanding semi-transparent rectangles in the health colour
    glow_rect(surface, health_col, (x, y, w, h), radius=16)

    # -- Card background (two layers for a subtle depth effect) --
    draw_rounded_rect(surface, C_CARD,  (x,     y,     w,     h),     radius=16)
    draw_rounded_rect(surface, C_CARD2, (x + 2, y + 2, w - 4, h - 4), radius=14)

    # -- Coloured accent stripe at the top of the card --
    # Uses a transparent surface so the card background shows through slightly
    stripe_h = 48
    stripe_s = pygame.Surface((w - 4, stripe_h), pygame.SRCALPHA)
    r, g, b  = health_col
    pygame.draw.rect(stripe_s, (r, g, b, 55),       # 55/255 alpha ≈ 22% opacity
                     (0, 0, w - 4, stripe_h), border_radius=13)
    surface.blit(stripe_s, (x + 2, y + 2))

    # -- Outer border in the health colour --
    draw_rounded_rect(surface, C_CARD, (x, y, w, h),
                      radius=16, border=2, border_colour=health_col)

    # -- Plant name in the top-left --
    draw_text(surface, title, f_hdr, C_TITLE, x + 16, y + 12)

    # -- Watering status badge in the top-right --
    if watering:
        badge_col = C_BLUE       # bright blue when pump is ON
        badge_txt = "WATERING"
    else:
        badge_col = C_BLUE_DIM   # dark muted when pump is OFF
        badge_txt = "  idle"
    bx, by, bw, bh = x + w - 138, y + 10, 128, 28
    draw_rounded_rect(surface, badge_col, (bx, by, bw, bh), radius=9)
    draw_text(surface, badge_txt, f_lbl, C_TITLE, bx + 10, by + 7)

    # -- Health status label below the stripe --
    if health_col == C_GREEN:
        hlabel, dot = "Healthy",  "●"
    elif health_col == C_YELLOW:
        hlabel, dot = "Warning",  "!"
    else:
        hlabel, dot = "Critical", "X"
    draw_text(surface, f"{dot} {hlabel}", f_lbl, health_col, x + 16, y + 52)

    # -- Alert reason lines (one per active alert, max 3) --
    # Each reason shows the LIVE sensor value, not the frozen value from when the alert fired
    reason_y = y + 70
    for reason in alert_reasons:
        draw_text(surface, f"  → {reason}", f_tiny, health_col, x + 16, reason_y)
        reason_y += 15  # 15px between each alert reason line

    # -- Separator line between alert section and sensor rows --
    sep_y = reason_y + 4
    pygame.draw.line(surface, C_SEPARATOR, (x + 12, sep_y), (x + w - 12, sep_y))
    cy = sep_y + 10  # sensor rows start 10px below the separator

    # -- Sensor value rows with mini progress bars --
    # Each tuple: (display label, live value, unit string, bar min, bar max)
    # bar min/max define the range shown in the progress bar — taken from the plant profile
    bar_rows = [
        ("Soil Moisture",  data.get("soil_moisture",    "–"), "%",      0,    100),
        ("Temperature",    data.get("temperature",      "–"), "°C",    15,     40),
        ("Humidity",       data.get("humidity",         "–"), "%",      0,    100),
        ("Nitrogen",       data.get("nitrogen",         "–"), "mg/kg", *profile["nitrogen"]),
        ("Phosphorus",     data.get("phosphorus",       "–"), "mg/kg", *profile["phosphorus"]),
        ("Potassium",      data.get("potassium",        "–"), "mg/kg", *profile["potassium"]),
        ("Soil pH",        data.get("soil_ph",          "–"), "",      *profile["soil_ph"]),
        ("Salinity",       data.get("salinity",         "–"), "dS/m",   0,    profile["salinity"][1] * 1.5),
        ("Root Temp",      data.get("root_temperature", "–"), "°C",   *profile["root_temperature"]),
    ]

    for label, value, unit, vmin, vmax in bar_rows:
        if cy + 22 > y + h - 8:
            break  # stop drawing rows if we've reached the bottom of the card

        # Sensor label on the left (e.g. "Nitrogen")
        draw_text(surface, label, f_tiny, C_LABEL, x + 14, cy)

        # Sensor value + unit in the middle (e.g. "214.3 mg/kg")
        val_str = f"{value} {unit}".strip()
        draw_text(surface, val_str, f_lbl, C_VALUE, x + 178, cy)

        # Mini horizontal bar on the right — skipped if value is not yet numeric
        try:
            draw_bar(surface, x + w - 98, cy + 3, 82, 7,
                     float(value), vmin, vmax, health_col)
        except (ValueError, TypeError):
            pass  # value is "–" or None — bar not drawn yet

        cy += 22  # move down 22px to the next row

        # Thin separator line between rows for visual clarity
        pygame.draw.line(surface, C_SEPARATOR,
                         (x + 12, cy - 2), (x + w - 12, cy - 2))


def draw_topbar(surface, fonts, tick):
    """
    Draw the top title bar across the full window width.
    Contains a pulsing dot animation, the dashboard title, and a live clock.
    'tick' is the frame counter used to drive the sine-wave pulse animation.
    """
    f_title, f_small = fonts

    # Solid dark strip as the bar background
    draw_rounded_rect(surface, (20, 22, 40), (0, 0, WIDTH, 56), radius=0)

    # Thin separator line at the bottom of the top bar
    pygame.draw.line(surface, C_SEPARATOR, (0, 56), (WIDTH, 56))

    # Pulsing circle: brightness oscillates using a sine wave over time
    # tick increases by 1 every frame; 0.08 controls the speed of the pulse
    pulse = int(180 + 75 * math.sin(tick * 0.08))   # brightness cycles between 105 and 255
    pygame.draw.circle(surface, (60, pulse, 100), (18, 28), 7)

    # Dashboard title text next to the pulsing dot
    draw_text(surface, "Smart Plant Monitoring Dashboard", f_title, C_TITLE, 28, 12)

    # Live time displayed in the top-right corner
    ts = time.strftime("%H:%M:%S")
    draw_text(surface, ts, f_small, C_LABEL, WIDTH - 80, 20)


def draw_alert_feed(surface, font, alert_list, y):
    """
    Draw a compact single-line alert feed at the bottom of the window.
    Shows the type and plant of up to 4 recent alerts in their severity colour.
    Stops adding alerts if they would overflow the window width.
    """
    # Horizontal divider line above the feed
    pygame.draw.line(surface, C_SEPARATOR, (PADDING, y), (WIDTH - PADDING, y))

    # Static prefix label
    cx = PADDING
    draw_text(surface, "Recent alerts: ", font, C_DIM, cx, y + 6)
    cx += 105  # move cursor right past the prefix

    for a in alert_list[:4]:  # show at most 4 alerts in the feed
        sev = a.get("severity", "INFO")

        # Colour each alert entry by severity
        col = C_RED if sev == "CRITICAL" else (C_YELLOW if sev == "WARNING" else C_GREEN)

        txt = f"[{a.get('plant_type','?')}] {a.get('alert_type','?')}  "

        # Stop if this entry would go beyond the right edge of the window
        if cx + len(txt) * 7 > WIDTH - PADDING:
            break

        draw_text(surface, txt, font, col, cx, y + 6)
        cx += len(txt) * 7  # advance cursor by approximate text width


# ── Main render loop ──────────────────────────────────────────────────────────

def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Smart Plant Monitor")
    clock  = pygame.time.Clock()
    tick   = 0  # frame counter used for animations

    # Initialise all fonts used throughout the dashboard
    f_title = pygame.font.SysFont("segoeui", FONT_TITLE,  bold=True)  # top bar title
    f_hdr   = pygame.font.SysFont("segoeui", FONT_HEADER, bold=True)  # card plant name
    f_body  = pygame.font.SysFont("segoeui", FONT_BODY)               # (reserved)
    f_lbl   = pygame.font.SysFont("segoeui", FONT_SMALL)              # values and badges
    f_tiny  = pygame.font.SysFont("segoeui", FONT_TINY)               # labels and alerts

    # Plant types to render — order determines left/right position of cards
    known_plants = list(PLANT_PROFILES.keys())  # ["ficus", "cactus"]

    running = True
    while running:
        # Process OS events — check if the user closed the window
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Clear the screen with the background colour before drawing this frame
        screen.fill(C_BG)

        # Draw the top bar with animated dot and clock
        draw_topbar(screen, (f_title, f_lbl), tick)

        # Take a consistent snapshot of all shared state under a single lock acquisition
        # This prevents partial reads where some data is newer than other data
        with state_lock:
            snap_state  = dict(state)
            snap_water  = dict(water_state)
            snap_alerts = list(alerts)

        # Draw one card for each plant type
        for idx, ptype in enumerate(known_plants):
            pid      = f"plant-{ptype}-001"   # build plant ID from type name
            data     = snap_state.get(pid, {}) # latest sensor reading, empty if none yet
            watering = snap_water.get(pid, False)
            hcol     = _health_colour(pid)     # green / yellow / red based on alerts
            profile  = PLANT_PROFILES[ptype]   # threshold config for this plant type

            # Calculate card position — cards are placed side by side with padding
            cx = PADDING + idx * (CARD_W + PADDING)
            cy = 66  # top of card, below the top bar

            if not data:
                # No sensor data received yet — draw a placeholder card
                glow_rect(screen, C_BORDER, (cx, cy, CARD_W, CARD_H), radius=16)
                draw_rounded_rect(screen, C_CARD, (cx, cy, CARD_W, CARD_H),
                                  radius=16, border=2, border_colour=C_BORDER)
                draw_text(screen, profile["display_name"], f_hdr, C_TITLE, cx+16, cy+14)
                draw_text(screen, "Waiting for data…",    f_lbl, C_LABEL, cx+16, cy+52)
                continue

            # Build live alert reason strings using current sensor values
            # We look up the live value from 'data' so it updates every 2 seconds,
            # rather than showing the frozen value from when the alert was first published
            reasons = []
            seen    = set()
            for a in snap_alerts:
                if a.get("plant_id") == pid:
                    atype = a.get("alert_type", "")
                    if atype in seen:
                        continue  # skip duplicates — only show each alert type once

                    # Match alert type to the corresponding live sensor field
                    if atype == "NITROGEN_OUT_OF_RANGE":
                        short = f"Nitrogen: {data.get('nitrogen','–')} mg/kg (ok {profile['nitrogen'][0]}–{profile['nitrogen'][1]})"
                    elif atype == "PHOSPHORUS_OUT_OF_RANGE":
                        short = f"Phosphorus: {data.get('phosphorus','–')} mg/kg (ok {profile['phosphorus'][0]}–{profile['phosphorus'][1]})"
                    elif atype == "POTASSIUM_OUT_OF_RANGE":
                        short = f"Potassium: {data.get('potassium','–')} mg/kg (ok {profile['potassium'][0]}–{profile['potassium'][1]})"
                    elif atype == "PH_OUT_OF_RANGE":
                        short = f"Soil pH: {data.get('soil_ph','–')} (ok {profile['soil_ph'][0]}–{profile['soil_ph'][1]})"
                    elif atype == "HIGH_SALINITY":
                        short = f"Salinity: {data.get('salinity','–')} dS/m (max {profile['salinity'][1]})"
                    elif atype == "ROOT_TEMP_OUT_OF_RANGE":
                        short = f"Root Temp: {data.get('root_temperature','–')}°C (ok {profile['root_temperature'][0]}–{profile['root_temperature'][1]})"
                    elif atype == "LOW_MOISTURE":
                        short = f"Moisture: {data.get('soil_moisture','–')}% (min {profile['moisture_warning']}%)"
                    else:
                        short = atype  # fallback for any unknown alert types

                    reasons.append(short)
                    seen.add(atype)

                if len(reasons) >= 3:
                    break  # cap at 3 reasons to avoid overflowing the card

            # Draw the full plant card with all data
            draw_card(screen, (cx, cy, CARD_W, CARD_H),
                      None, profile["display_name"], hcol, watering,
                      reasons, profile, data,
                      (f_hdr, f_body, f_lbl, f_tiny))

        # Draw the compact alert feed below the cards if there is enough space
        feed_y = 66 + CARD_H + 8
        if feed_y + 30 <= HEIGHT:
            draw_alert_feed(screen, f_tiny, snap_alerts, feed_y)

        pygame.display.flip()   # swap back buffer to screen — shows the completed frame
        clock.tick(FPS)         # wait to maintain target FPS — prevents 100% CPU usage
        tick += 1               # increment frame counter for animation calculations

    # ── Cleanup on window close ───────────────────────────────────────────────
    pygame.quit()               # shut down pygame window and display system
    mqtt_client.loop_stop()     # stop the MQTT background networking thread
    mqtt_client.disconnect()    # cleanly close the connection to the broker


if __name__ == "__main__":
    main()