import random


def clamp(value, low, high):
    """Clamp a numeric value into the inclusive [low, high] range."""
    return max(low, min(high, value))


def mid_range(rng):
    """Return the midpoint of a (min, max) tuple."""
    return (rng[0] + rng[1]) / 2


def init_npk(profile):
    """Initialise NPK values at the midpoint of the optimal plant range."""
    return {
        "nitrogen": mid_range(profile["nitrogen"]),
        "phosphorus": mid_range(profile["phosphorus"]),
        "potassium": mid_range(profile["potassium"]),
    }


def update_npk(profile, nitrogen, phosphorus, potassium):
    """
    Simulate realistic NPK drift over time.
    Nutrients slowly deplete as the plant consumes them, with slight random variation.
    """
    nitrogen += random.uniform(-2.0, 1.0)
    phosphorus += random.uniform(-1.0, 0.5)
    potassium += random.uniform(-1.5, 0.8)

    n_rng = profile["nitrogen"]
    p_rng = profile["phosphorus"]
    k_rng = profile["potassium"]

    nitrogen = clamp(nitrogen, n_rng[0] * 0.5, n_rng[1] * 1.2)
    phosphorus = clamp(phosphorus, p_rng[0] * 0.5, p_rng[1] * 1.2)
    potassium = clamp(potassium, k_rng[0] * 0.5, k_rng[1] * 1.2)

    return nitrogen, phosphorus, potassium


def evaluate_npk(data, profile, plant_id, plant_type, severity_fn, publish_alert_fn, clear_alert_fn):
    """
    Validate NPK values against the plant profile and publish alerts.
    severity_fn, publish_alert_fn, clear_alert_fn are injected from controller.py
    so this module stays decoupled from MQTT/controller internals.
    """
    nutrients = [
        ("Nitrogen", "nitrogen"),
        ("Phosphorus", "phosphorus"),
        ("Potassium", "potassium"),
    ]

    for nutrient_name, key in nutrients:
        value = data.get(key)
        if value is None:
            continue

        severity, out_of_range = severity_fn(float(value), *profile[key])

        if out_of_range:
            publish_alert_fn(
                plant_id,
                plant_type,
                f"{key.upper()}_OUT_OF_RANGE",
                severity,
                f"{nutrient_name} out of range: {value} mg/kg "
                f"(optimal {profile[key][0]}–{profile[key][1]})",
            )
        else:
            clear_alert_fn(plant_id, f"{key.upper()}_OUT_OF_RANGE")


def build_npk_alert_reason(alert_type, data, profile):
    """Return dashboard-friendly alert text for NPK alerts."""
    if alert_type == "NITROGEN_OUT_OF_RANGE":
        return (
            f"Nitrogen: {data.get('nitrogen', '–')} mg/kg "
            f"(ok {profile['nitrogen'][0]}–{profile['nitrogen'][1]})"
        )

    if alert_type == "PHOSPHORUS_OUT_OF_RANGE":
        return (
            f"Phosphorus: {data.get('phosphorus', '–')} mg/kg "
            f"(ok {profile['phosphorus'][0]}–{profile['phosphorus'][1]})"
        )

    if alert_type == "POTASSIUM_OUT_OF_RANGE":
        return (
            f"Potassium: {data.get('potassium', '–')} mg/kg "
            f"(ok {profile['potassium'][0]}–{profile['potassium'][1]})"
        )

    return None
