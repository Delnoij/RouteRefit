# SPDX-License-Identifier: GPL-3.0-only
"""Keep route-affecting selections separate from timing-only changes."""
from tkinter import ttk
from gpx_core import PROFILES
from profile_settings import TRANSPORTS, TIME_PRESETS, DEFAULT_PRESET, restored_settings
from i18n import tr


class ProfileSettingsUI:
    def routing_mode(self):
        return TRANSPORTS[self.transport.get()][0]

    def routing_style(self):
        return TRANSPORTS[self.transport.get()][1]

    def refresh_time_presets(self):
        values = list(TIME_PRESETS[self.transport.get()]) + ['Eigen snelheid']
        self.time_preset_box.configure(values=[tr(v) for v in values])

    def transport_changed(self, event=None):
        transport = self.transport.get()
        if transport not in TRANSPORTS:
            return
        # Retain the user's speed; changing vehicle does not silently change the clock.
        self.time_preset.set(DEFAULT_PRESET[transport])
        self.profile.set(TIME_PRESETS[transport][self.time_preset.get()])
        self.refresh_time_presets()
        self.flat_speed_changed()
        self.clear_access_reviews()
        self.auto_checked_key = None
        self.endpoint_edit_key = None
        if self.roadmap:
            self.roadmap.cycling_style = self.routing_style()
        self.invalidate()
        self.found = []
        self.pausebox.delete(*self.pausebox.get_children())
        self.schedule_auto()

    def time_preset_changed(self, event=None):
        # This combobox deliberately has no localization proxy: its choices change per vehicle.
        choices = TIME_PRESETS[self.transport.get()]
        displayed = self.time_preset.get()
        if displayed in ('Eigen snelheid', tr('Eigen snelheid')):
            self.invalidate()
            return
        selected = next((label for label in choices if tr(label) == displayed), displayed)
        if selected not in choices:
            return
        self.time_preset.set(selected)
        self.profile.set(choices[selected])
        self.time_preset.set(tr(selected))
        self.change_profile()

    def flat_speed_changed(self, *args):
        choices = TIME_PRESETS[self.transport.get()]
        selected = 'Eigen snelheid'
        try:
            if float(self.flat.get().replace(',', '.')) == PROFILES[self.profile.get()][1]:
                selected = next((label for label, profile in choices.items() if profile == self.profile.get()), selected)
        except ValueError:
            pass
        self.time_preset.set(tr(selected))

    def load_profile_settings(self, settings, fallback_profile):
        transport, preference, preset, profile = restored_settings(settings, fallback_profile)
        self.transport.set(transport)
        self.route_preference.set(preference)
        self.time_preset.set(preset)
        self.profile.set(profile)
        self.refresh_time_presets()
        self.time_preset.set(tr(preset))
        # Existing reports stored flat_speed; do not discard a custom value on reopen.
        flat = settings.get("flat_speed")
        maximum=160 if self.routing_mode() in ('motorcar','motorcycle') else 60
        self.flat.set(str(flat if type(flat) in (int, float) and 0.5 <= flat <= maximum else PROFILES[profile][1]))
