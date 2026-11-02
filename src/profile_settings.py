# SPDX-License-Identifier: GPL-3.0-only
"""Independent transport, routing intent and timing presets, with legacy migration."""

TRANSPORTS = {
    "Lopen": ("walk", "trekking"),
    "Fiets": ("bike", "trekking"),
    "MTB": ("bike", "mountainbike"),
    "Gravelfiets": ("bike", "gravel"),
    "Auto": ("motorcar", "road"),
    "Motor": ("motorcycle", "road"),
}
ROUTE_PREFERENCES = {"Meest logisch": "follow_original"}
TIME_PRESETS = {
    "Lopen": {"Rustig": "Wandelen · rustig", "Normaal": "Wandelen · normaal", "Stevig": "Wandelen · stevig"},
    "Fiets": {"Recreatief": "Fietsen · recreatief", "Trekking": "Fietsen · trekking", "Sportief": "Fietsen · sportief"},
    "MTB": {"Normaal": "Fietsen · mountainbike"},
    "Gravelfiets": {"Rustig": "Gravel · rustig", "Normaal": "Gravel · normaal", "Sportief": "Gravel · sportief"},
    "Auto": {"Normaal": "Auto · normaal"},
    "Motor": {"Normaal": "Motor · normaal"},
}
DEFAULT_PRESET = {name: "Trekking" if name=="Fiets" else "Normaal" for name in TRANSPORTS}


def transport_from_profile(profile):
    for activity,presets in TIME_PRESETS.items():
        if profile in presets.values():return activity
    if profile == "Fietsen · mountainbike":
        return "MTB"
    return "Fiets" if isinstance(profile, str) and profile.startswith("Fietsen ·") else "Lopen"


def restored_settings(settings, fallback_profile):
    """Old profile names select the initial transport only when no new fields exist."""
    settings = settings if isinstance(settings, dict) else {}
    transport = settings.get("activity",settings.get("transport"))
    if not isinstance(transport, str) or transport not in TRANSPORTS:
        transport = transport_from_profile(fallback_profile)
    profile = settings.get("timing_profile", fallback_profile)
    presets = TIME_PRESETS[transport]
    preset = next((label for label, value in presets.items() if value == profile), DEFAULT_PRESET[transport])
    return transport, "Meest logisch", preset, presets[preset]
