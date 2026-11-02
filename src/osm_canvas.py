# SPDX-License-Identifier: GPL-3.0-only
"""Native OSM slippy map: only visible tiles, disk cache, two download workers."""

from __future__ import annotations
import base64, collections, concurrent.futures, json, math, queue, threading, time
from pathlib import Path
from urllib.request import Request, urlopen
import tkinter as tk
from gpx_core import Point
from app_version import VERSION

TILE = 256


def world(lat, lon, z):
    lat = max(-85.05112878, min(85.05112878, lat))
    size = TILE * 2**z
    return (lon + 180) / 360 * size, (
        1 - math.asinh(math.tan(math.radians(lat))) / math.pi
    ) / 2 * size


def location(x, y, z):
    size = TILE * 2**z
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / size)))), (
        x / size * 360 - 180 + 180
    ) % 360 - 180


class TileStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="OSM-kaart"
        )
        self.results = queue.Queue()
        self.pending = set()
        self.lock = threading.Lock()
        self.closed = False
        self.provider = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

    def request(self, key, is_visible):
        with self.lock:
            if self.closed or key in self.pending:
                return
            self.pending.add(key)
        self.pool.submit(self.load, key, is_visible)

    def load(self, key, is_visible):
        cached = None
        try:
            if not is_visible(key):
                return
            z, x, y = key
            p = self.folder / str(z) / str(x) / (str(y) + ".png")
            meta = p.with_suffix(".json")
            headers = {}
            fresh = False
            if p.exists():
                cached = p.read_bytes()
                try:
                    info = json.loads(meta.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    info = {}
                fresh = time.time() < info.get("expires", p.stat().st_mtime + 7 * 86400)
                if fresh:
                    self.results.put((key, cached, None))
                    return
                if info.get("etag"):
                    headers["If-None-Match"] = info["etag"]
                if info.get("last_modified"):
                    headers["If-Modified-Since"] = info["last_modified"]
            if not is_visible(key):
                return
            headers["User-Agent"] = f"RouteRefit/{VERSION} (local route editor)"
            from urllib.error import HTTPError

            try:
                with urlopen(
                    Request(self.provider.format(z=z, x=x, y=y), headers=headers), timeout=12
                ) as response:
                    raw = response.read(2_000_001)
                    if len(raw) > 2_000_000 or not raw.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("Geen geldige kaarttegel ontvangen.")
                    cache = response.headers.get("Cache-Control", "")
                    age = 7 * 86400
                    for part in cache.split(","):
                        if part.strip().startswith("max-age="):
                            try:
                                age = max(age, int(part.strip().split("=")[1]))
                            except ValueError:
                                pass
                    info = dict(
                        expires=time.time() + age,
                        etag=response.headers.get("ETag"),
                        last_modified=response.headers.get("Last-Modified"),
                    )
            except HTTPError as exc:
                if exc.code != 304 or not p.exists():
                    raise
                raw = p.read_bytes()
                info["expires"] = time.time() + 7 * 86400
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                tmp = p.with_suffix(".tmp")
                tmp.write_bytes(raw)
                tmp.replace(p)
                meta.write_text(json.dumps(info), encoding="utf-8")
            except OSError:
                # A cache write failure must not hide a successfully downloaded tile.
                pass
            self.results.put((key, raw, None))
        except Exception as exc:
            if cached is not None:
                self.results.put((key, cached, None))
            else:
                self.results.put((key, None, str(exc)))
        finally:
            with self.lock:
                self.pending.discard(key)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)


class RouteMap(tk.Canvas):
    def __init__(
        self,
        master,
        cache,
        on_select,
        on_move,
        on_insert,
        on_pan_notice=None,
        on_waypoint=None,
        on_waypoint_select=None,
        on_waypoint_move=None,
        on_endpoint=None,
        **kwargs,
    ):
        super().__init__(master, background="#e5e8e3", highlightthickness=0, **kwargs)
        self.center = (50.923, 5.99)
        self.zoom = 13
        self.store = TileStore(cache)
        self.images = collections.OrderedDict()
        self.visible = frozenset()
        self.failed = {}
        self.scheduled = None
        self.original = []
        self.working = []
        self.proposal = []
        self.selected = None
        self.issue = None
        self.pause = None
        self.range = None
        self.mode = "view"
        self.on_select = on_select
        self.on_move = on_move
        self.on_insert = on_insert
        self.controls = []
        self.waypoints = []
        self.on_waypoint = on_waypoint
        self.on_waypoint_select = on_waypoint_select
        self.on_waypoint_move = on_waypoint_move
        self.on_endpoint = on_endpoint
        self.on_pan_notice = on_pan_notice
        self.dragging = None
        self.hitpoints = []
        self.moved = False
        self.fit_pending = None
        self.tile_problem = ""
        self.bind("<Configure>", self.resize)
        self.bind("<MouseWheel>", self.wheel)
        self.bind("<ButtonPress-1>", self.down)
        self.bind("<B1-Motion>", self.motion)
        self.bind("<ButtonRelease-1>", self.up)
        self.bind("<Double-Button-1>", self.double)
        self.bind("<Destroy>", self.destroyed)
        self.after(100, self.poll)

    def destroyed(self, e):
        if e.widget is self:
            self.store.close()

    def resize(self, e):
        if self.fit_pending and e.width > 200 and e.height > 100:
            segments = self.fit_pending
            self.fit_pending = None
            self.fit(segments)
        else:
            self.render()

    def fit(self, segments):
        pts = [p for s in segments for p in s]
        if not pts:
            return
        if self.winfo_width() < 200 or self.winfo_height() < 100:
            self.fit_pending = segments
            return
        for z in range(19, 1, -1):
            positions = [world(p.lat, p.lon, z) for p in pts]
            x0 = min(x for x, y in positions)
            x1 = max(x for x, y in positions)
            y0 = min(y for x, y in positions)
            y1 = max(y for x, y in positions)
            margin = min(40, self.winfo_width() * 0.12, self.winfo_height() * 0.12)
            if (
                x1 - x0 < self.winfo_width() - 2 * margin
                and y1 - y0 < self.winfo_height() - 2 * margin
            ):
                break
        self.zoom = z
        self.center = location((x0 + x1) / 2, (y0 + y1) / 2, z)
        self.render()

    def focus_point(self, p, zoom=17):
        self.center = (p.lat, p.lon)
        self.zoom = max(self.zoom, zoom)
        self.render()

    def pixel(self, p):
        x, y = world(p.lat, p.lon, self.zoom)
        cx, cy = world(*self.center, self.zoom)
        dx = x - cx
        size = TILE * 2**self.zoom
        if dx > size / 2:
            dx -= size
        if dx < -size / 2:
            dx += size
        return self.winfo_width() / 2 + dx, self.winfo_height() / 2 + y - cy

    def point(self, x, y):
        cx, cy = world(*self.center, self.zoom)
        lat, lon = location(
            cx + x - self.winfo_width() / 2, cy + y - self.winfo_height() / 2, self.zoom
        )
        return Point(lat, lon)

    def set_layers(
        self,
        original,
        working,
        proposal,
        selected=None,
        issue=None,
        pause=None,
        range_selection=None,
        controls=None,
        waypoints=None,
        manual_ranges=None,
        problem_ranges=None,
    ):
        self.original = original
        self.working = working
        self.proposal = proposal or []
        self.selected = selected
        self.issue = issue
        self.pause = pause
        self.range = range_selection
        self.problem_ranges = problem_ranges or []
        self.manual_ranges = manual_ranges or set()
        self.controls = controls or []
        self.waypoints = waypoints or []
        self.overlays()

    def set_mode(self, mode):
        self.mode = mode
        self.configure(cursor="hand2" if mode == "view" else "crosshair")
        self.overlays()

    def wheel(self, e):
        target = self.point(e.x, e.y)
        new = max(2, min(19, self.zoom + (1 if e.delta > 0 else -1)))
        if new == self.zoom:
            return
        self.zoom = new
        tx, ty = world(target.lat, target.lon, new)
        self.center = location(
            tx - e.x + self.winfo_width() / 2, ty - e.y + self.winfo_height() / 2, new
        )
        self.render()
        return "break"

    def zoom_by(self, delta):
        self.zoom = max(2, min(19, self.zoom + delta))
        self.render()

    def nearest(self, x, y):
        if self.selected and self.mode in ("edit", "anchor"):
            si, i = self.selected
            if si < len(self.working) and i < len(self.working[si]):
                px, py = self.pixel(self.working[si][i])
                if (px - x) ** 2 + (py - 21 - y) ** 2 < 225:
                    return self.selected
        best = None
        # Uses the source index of the visible edit line, never a drawing index.
        for si, s in enumerate(self.working):
            indices = (
                self.controls[si]
                if self.mode == "anchor" and si < len(self.controls)
                else range(len(s))
            )
            for i in indices:
                p = s[i]
                px, py = self.pixel(p)
                d = (px - x) ** 2 + (py - y) ** 2
                if d < 225 and (best is None or d < best[0]):
                    best = (d, si, i)
        return (best[1], best[2]) if best else None

    def down(self, e):
        if self.mode in ("view", "waypoint"):
            hit = next(
                (w for w in reversed(self.waypoints) if math.dist(self.pixel(w), (e.x, e.y)) < 14),
                None,
            )
            if hit:
                px, py = self.pixel(hit)
                self.dragging = dict(
                    x=e.x,
                    y=e.y,
                    center=self.center,
                    hit=None,
                    waypoint=hit,
                    offset=(px - e.x, py - e.y),
                )
                self.moved = False
                return
        hit = self.nearest(e.x, e.y) if self.mode != "view" else None
        if self.mode in ("waypoint", "start", "end", "both"):
            hit = None
        offset = (0, 0)
        if hit:
            px, py = self.pixel(self.working[hit[0]][hit[1]])
            offset = (px - e.x, py - e.y)
        self.dragging = dict(x=e.x, y=e.y, center=self.center, hit=hit, offset=offset)
        self.moved = False
        if hit:
            self.selected = hit
            self.on_select(*hit)
            self.overlays()

    def motion(self, e):
        if not self.dragging:
            return
        d = self.dragging
        dx = e.x - d["x"]
        dy = e.y - d["y"]
        if abs(dx) + abs(dy) > 3:
            self.moved = True
        if (
            d.get("waypoint")
            and self.mode == "waypoint"
            or d["hit"]
            and self.mode in ("edit", "anchor")
        ):
            x, y = e.x + d["offset"][0], e.y + d["offset"][1]
            self.delete("drag-marker")
            self.create_oval(
                x - 8,
                y - 8,
                x + 8,
                y + 8,
                fill="#0878b5",
                outline="white",
                width=3,
                tags="drag-marker",
            )
        elif not d["hit"]:
            cx, cy = world(*d["center"], self.zoom)
            self.center = location(cx - dx, cy - dy, self.zoom)
            self.render()

    def up(self, e):
        d = self.dragging
        self.dragging = None
        self.delete("drag-marker")
        if d and d.get("waypoint"):
            if self.mode == "waypoint" and self.moved and self.on_waypoint_move:
                self.on_waypoint_move(
                    d["waypoint"].key, self.point(e.x + d["offset"][0], e.y + d["offset"][1])
                )
            elif not self.moved and self.on_waypoint_select:
                self.on_waypoint_select(d["waypoint"].key)
            return
        if d and self.mode in ("start", "end", "both") and not self.moved:
            if self.on_endpoint:
                self.on_endpoint(self.mode, self.point(e.x, e.y))
            return
        if d and self.mode == "waypoint" and not self.moved:
            if self.on_waypoint:
                self.on_waypoint(self.point(e.x, e.y))
            return
        if d and d["hit"] and self.mode in ("edit", "anchor") and self.moved:
            self.on_move(*d["hit"], self.point(e.x + d["offset"][0], e.y + d["offset"][1]))
        elif d and not self.moved and self.mode != "view" and not d["hit"]:
            # Selection requires a route point; blank clicks never move arbitrary data.
            if self.on_pan_notice:
                self.on_pan_notice(
                    "Klik op de blauwe lijn om een punt te kiezen; zoom in voor nauwkeuriger bewerken."
                )

    def double(self, e):
        if self.mode in ("waypoint", "start", "end", "both"):
            return "break"
        if self.mode in ("edit", "anchor"):
            # Insert into the nearest visible segment, projected from the actual mouse position.
            best = None
            for si, s in enumerate(self.working):
                for i, (a, b) in enumerate(zip(s, s[1:])):
                    ax, ay = self.pixel(a)
                    bx, by = self.pixel(b)
                    dx = bx - ax
                    dy = by - ay
                    den = dx * dx + dy * dy
                    f = max(0, min(1, ((e.x - ax) * dx + (e.y - ay) * dy) / den)) if den else 0
                    gap = math.hypot(e.x - ax - f * dx, e.y - ay - f * dy)
                    if gap < 15 and (best is None or gap < best[0]):
                        best = gap, si, i, f
            if best:
                self.on_insert(best[1], best[2], best[3], self.point(e.x, e.y))
            self.dragging = None
            return "break"
        self.zoom_by(1)
        return "break"

    def render(self, redraw_overlays=True):
        if not self.winfo_exists():
            return
        self.delete("tiles")
        w, h = self.winfo_width(), self.winfo_height()
        cx, cy = world(*self.center, self.zoom)
        left = cx - w / 2
        top = cy - h / 2
        keys = set()
        n = 2**self.zoom
        for xx in range(math.floor(left / TILE), math.floor((left + w) / TILE) + 1):
            for yy in range(math.floor(top / TILE), math.floor((top + h) / TILE) + 1):
                if not 0 <= yy < n:
                    continue
                key = (self.zoom, xx % n, yy)
                keys.add(key)
                x = xx * TILE - left
                y = yy * TILE - top
                if key in self.images:
                    self.create_image(x, y, image=self.images[key], anchor="nw", tags="tiles")
                else:
                    self.create_rectangle(
                        x, y, x + TILE, y + TILE, fill="#e9ede6", outline="#dce2d8", tags="tiles"
                    )
                    if key in self.failed:
                        self.create_text(
                            x + 12,
                            y + 20,
                            text="Kaart niet geladen",
                            anchor="nw",
                            fill="#7d5750",
                            tags="tiles",
                        )
        self.visible = frozenset(keys)
        self.tag_lower("tiles")
        if redraw_overlays:
            self.overlays()
        if self.scheduled:
            self.after_cancel(self.scheduled)
        self.scheduled = self.after(220, self.request_visible)

    def request_visible(self):
        self.scheduled = None
        for key in self.visible:
            if key not in self.images and time.time() - self.failed.get(key, 0) > 30:
                self.store.request(key, lambda k: k in self.visible)

    def poll(self):
        changed = False
        try:
            while True:
                key, raw, error = self.store.results.get_nowait()
                if error:
                    self.failed[key] = time.time()
                    self.tile_problem = "Kaartachtergrond tijdelijk niet geladen. Nieuwe poging volgt automatisch; routebewerking blijft beschikbaar."
                else:
                    try:
                        self.images[key] = tk.PhotoImage(data=base64.b64encode(raw))
                        self.images.move_to_end(key)
                        self.failed.pop(key, None)
                        while len(self.images) > 180:
                            old = next((k for k in self.images if k not in self.visible), None)
                            if old is None:
                                break
                            del self.images[old]
                    except tk.TclError:
                        self.failed[key] = time.time()
                if key in self.visible:
                    changed = True
        except queue.Empty:
            pass
        if changed:
            self.render(redraw_overlays=False)
        self.retry_failed_tiles()
        if self.winfo_exists():
            self.after(100, self.poll)

    def retry_failed_tiles(self):
        # Retry even when the user leaves the map untouched after a transient outage.
        for key in self.visible:
            if key in self.failed and time.time() - self.failed[key] > 30:
                self.store.request(key, lambda k: k in self.visible)

    def line(self, points, color, width, dash=()):
        if len(points) > 1:
            self.create_line(
                *[v for p in points for v in self.pixel(p)],
                fill=color,
                width=width,
                dash=dash,
                tags="overlay",
            )

    def pin(self, p, text, color):
        x, y = self.pixel(p)
        self.create_line(x, y, x, y - 18, fill=color, width=4, tags="overlay")
        self.create_oval(
            x - 10, y - 31, x + 10, y - 11, fill=color, outline="white", width=2, tags="overlay"
        )
        label = self.create_text(
            x + 15,
            y - 24,
            text=text,
            anchor="w",
            fill="white",
            font=("Segoe UI", 10, "bold"),
            tags="overlay",
        )
        b = self.bbox(label)
        rect = self.create_rectangle(
            b[0] - 6, b[1] - 4, b[2] + 6, b[3] + 4, fill=color, outline="", tags="overlay"
        )
        self.tag_lower(rect, label)

    def overlays(self):
        self.delete("overlay")
        w, h = self.winfo_width(), self.winfo_height()
        for s in self.original:
            self.line(s, "#e59a50", 5)
        for s in self.working:
            self.line(s, "#0878b5", 3)
            if self.zoom >= 15:
                # Visible direction cues help review separate one-way cycle paths.
                travelled = 0.0
                next_arrow = 70.0
                for a, b in zip(s, s[1:]):
                    ax, ay = self.pixel(a)
                    bx, by = self.pixel(b)
                    length = math.hypot(bx - ax, by - ay)
                    while length and next_arrow <= travelled + length:
                        fraction = (next_arrow - travelled) / length
                        x, y = ax + fraction * (bx - ax), ay + fraction * (by - ay)
                        if 15 < x < w - 15 and 15 < y < h - 15:
                            dx, dy = (bx - ax) / length, (by - ay) / length
                            self.create_line(
                                x - 9 * dx,
                                y - 9 * dy,
                                x + 5 * dx,
                                y + 5 * dy,
                                fill="#0878b5",
                                width=3,
                                arrow=tk.LAST,
                                arrowshape=(10, 12, 5),
                                tags="overlay",
                            )
                        next_arrow += 120
                    travelled += length
        for s in self.proposal:
            self.line(s, "#13734d", 3)
        for si, a, b in getattr(self, "manual_ranges", ()):
            self.line(self.working[si][a : b + 1], "#bc6415", 5, dash=(7, 5))
        for si, a, b in getattr(self, "problem_ranges", ()):
            self.line(self.working[si][a : b + 1], "#b7342d", 5, dash=(6, 5))
        if self.range:
            si, start, end = self.range
            self.line(self.working[si][start : end + 1], "#8548b1", 6)
        if self.mode in ("edit", "range") and self.zoom >= 16:
            for s in self.working:
                visible = []
                for i, p in enumerate(s):
                    x, y = self.pixel(p)
                    if -10 < x < w + 10 and -10 < y < h + 10:
                        visible.append((x, y))
                stride = max(1, math.ceil(len(visible) / 300))
                for x, y in visible[::stride]:
                    self.create_oval(
                        x - 3, y - 3, x + 3, y + 3, fill="white", outline="#0878b5", tags="overlay"
                    )
        for si, indices in enumerate(self.controls):
            if si >= len(self.working):
                continue
            for i in indices:
                if i >= len(self.working[si]):
                    continue
                x, y = self.pixel(self.working[si][i])
                if -12 < x < w + 12 and -12 < y < h + 12:
                    radius = 7 if self.zoom >= 15 else 4
                    self.create_oval(
                        x - radius,
                        y - radius,
                        x + radius,
                        y + radius,
                        fill="#fff4b3",
                        outline="#125f82",
                        width=2,
                        tags="overlay",
                    )
        for s in self.working:
            if not s:
                continue
            for p, label in [(s[0], "Start"), (s[-1], "Einde")]:
                x, y = self.pixel(p)
                self.create_oval(
                    x - 6,
                    y - 6,
                    x + 6,
                    y + 6,
                    fill="white",
                    outline="#234f3b",
                    width=2,
                    tags="overlay",
                )
        if self.pause:
            self.pin(self.pause, "Pauze / meetgat", "#8548b1")
        if self.selected:
            si, i = self.selected
            if si < len(self.working) and i < len(self.working[si]):
                self.pin(
                    self.working[si][i],
                    "Hoofdpunt" if self.mode == "anchor" else "Gekozen punt",
                    "#0878b5",
                )
        if self.issue:
            self.pin(self.issue["point"], self.issue.get("label", "Hier controleren"), "#b7342d")
        for waypoint in self.waypoints:
            x, y = self.pixel(waypoint)
            if -15 < x < w + 15 and -15 < y < h + 15:
                self.create_polygon(
                    x,
                    y - 10,
                    x + 9,
                    y,
                    x,
                    y + 10,
                    x - 9,
                    y,
                    fill="#713c91",
                    outline="white",
                    width=2,
                    tags="overlay",
                )
                label = self.create_text(
                    x + 13,
                    y,
                    text=waypoint.name[:55],
                    anchor="w",
                    fill="#53256e",
                    font=("Segoe UI", 10, "bold"),
                    tags="overlay",
                )
                b = self.bbox(label)
                rect = self.create_rectangle(
                    b[0] - 3, b[1] - 2, b[2] + 3, b[3] + 2, fill="white", outline="", tags="overlay"
                )
                self.tag_lower(rect, label)
        if self.tile_problem and any(k in self.failed for k in self.visible):
            self.create_rectangle(4, 4, w - 4, 36, fill="#fff4e1", outline="", tags="overlay")
            self.create_text(
                12,
                20,
                text=self.tile_problem,
                anchor="w",
                fill="#744f26",
                font=("Segoe UI", 9),
                tags="overlay",
            )
        # Attribution is always visible, independent of route/overlay availability.
        text = "© OpenStreetMap-bijdragers  |  openstreetmap.org/copyright"
        label = self.create_text(
            w - 8,
            h - 9,
            text=text,
            anchor="se",
            fill="#224c65",
            font=("Segoe UI", 9),
            tags="overlay",
        )
        b = self.bbox(label)
        rect = self.create_rectangle(
            b[0] - 5, b[1] - 3, b[2] + 5, b[3] + 3, fill="white", outline="", tags="overlay"
        )
        self.tag_lower(rect, label)
