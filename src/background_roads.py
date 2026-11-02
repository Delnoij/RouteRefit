# SPDX-License-Identifier: GPL-3.0-only
"""Road downloads never lock the editor; obsolete results cannot replace its map."""
import queue
import threading


class BackgroundRoads:
    def road_job(self, fn, done, message, on_error=None):
        track = self.track
        active = getattr(self, "road_loading", None)
        if active is not None and active[0] is track:
            return
        token = (track, object())
        revision = getattr(self, "map_revision", 0)
        self.road_loading = token
        results = queue.Queue()
        self.mapinfo.set(message)
        self.status.set("Weggegevens laden op de achtergrond. Kies Puntjes om direct vrij te bewerken.")

        def work():
            try:
                results.put((fn(), None))
            except Exception as exc:
                results.put((None, exc))

        def poll():
            if self.track is not track or getattr(self, "road_loading", None) is not token:
                return
            if getattr(self, "map_revision", 0) != revision:
                self.road_loading = None
                return
            if self.busy:
                self.after(150, poll)
                return
            try:
                result, error = results.get_nowait()
            except queue.Empty:
                self.after(150, poll)
                return
            self.road_loading = None
            if error is not None:
                if on_error:
                    on_error(error)
            else:
                try:
                    done(result)
                except Exception as exc:
                    if on_error:
                        on_error(exc)

        threading.Thread(target=work, daemon=True, name="RouteRefit-wegen").start()
        self.after(150, poll)
