# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations
import sys
if __name__=='__main__' and len(sys.argv)==3 and sys.argv[1]=='--package-worker':
    from package_background import run
    from pathlib import Path
    run(Path(sys.argv[2]))
    raise SystemExit(0)
import copy, json, os, re, sys, threading, queue, urllib.request, urllib.error, webbrowser, time, math
from datetime import datetime, timezone
from fluent_progress import FluentProgress
from pathlib import Path
from xml.etree import ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from gpx_core import (
    Track,
    RoadMap,
    PROFILES,
    pauses,
    remove_pauses,
    modeled_times,
    cumulative,
    distance,
    duration,
    write_new,
    Point,
    AlignmentError,
    move_point,
    insert_point,
    delete_point,
    choose_anchors,
    route_anchor_edit,
    ANCHOR_DENSITY,
    Waypoint,
)
from osm_canvas import RouteMap
from routing_repair import leg_key, manual_intervals
from auto_alignment import automatic_alignment, issue_controls
from endpoint_edit import move_endpoints, remap_issues
from endpoint_edit import EndpointChange
from background_roads import BackgroundRoads
from alignment_workflow import AlignmentWorkflow
from access_review_ui import AccessReviewUI
from profile_settings_ui import ProfileSettingsUI
from profile_settings import TRANSPORTS, ROUTE_PREFERENCES
from proposal_review_ui import ProposalReviewUI, same_route
from proposal_summary import proposal_summary, summary_rows
from access_review import ACCESS_REVIEW_WARNING
from local_recovery import find_recovery
from segment_join_ui import SegmentJoinUI
from route_context import RouteContextUI
from gpx_core import replace_anchor_section
from waypoint_ui import WaypointDialog, portable_photo_links, validate_photo
from dataclasses import replace
from urllib.parse import unquote
import zipfile, tempfile
from workspace_ui import WorkspaceUI, apply_theme
from route_formats import read_route, FILETYPES
from i18n import DisplayVar, initialize, tr
from map_plan import plan_route_tiles, map_cache_name
from app_version import VERSION, DISPLAY_VERSION, PRODUCT_NAME
from road_download import road_query_url, fetch_road_data, DownloadBudget
from cycling_policy import BIKE_HEADWAY_WARNING
from auto_alignment import ADAPTED_ROAD_WARNING

APP_DIR = (
    Path(sys.executable).parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
BASE = (
    APP_DIR.parent
    if APP_DIR.name
    in (
        "Versie-1.2",
        "Versie-1.3",
        "Versie-1.3.1",
        "Versie-1.4",
        "Versie-1.5",
        "Versie-1.6",
        "Versie-1.7",
        "Versie-1.8",
        "Versie-1.9",
    )
    else APP_DIR
)
RES = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else BASE
DATA = BASE / "Mijn GPX"
DATA.mkdir(exist_ok=True)
MAPS = BASE / "Kaarten"
MAPS.mkdir(exist_ok=True)
CATALOG_PATH = (
    DATA / "routes-actueel.json" if (DATA / "routes-actueel.json").exists() else RES / "routes.json"
)
CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8")) if CATALOG_PATH.exists() else []


def fetch(url, limit=40_000_000, refresh=False, timeout=45, cancelled=None):
    headers = {"User-Agent": f"RouteRefit/{VERSION} (local route editor)"}
    if refresh:
        headers.update({"Cache-Control": "no-cache", "Pragma": "no-cache"})
    request = urllib.request.Request(url, headers=headers)
    deadline=time.monotonic()+timeout
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if cancelled is None:
            raw = response.read(limit + 1)
        else:
            chunks=[];size=0
            while size <= limit:
                if cancelled(): raise TimeoutError('Download gestopt.')
                if time.monotonic() >= deadline: raise TimeoutError('Download duurt te lang.')
                chunk=response.read1(min(65536,limit+1-size))
                if not chunk:break
                chunks.append(chunk);size+=len(chunk)
            raw=b''.join(chunks)
    if len(raw) > limit:
        raise ValueError("Download is te groot; importeer een kleiner bestand.")
    return raw


def route_download(rid):
    if not re.fullmatch(r"\d{1,8}", str(rid)):
        raise ValueError("Ongeldig routenummer.")
    raw = fetch("https://marcodelnoij.nl/?md_gpx=" + str(rid))
    track = Track(raw)
    folder = DATA / str(rid) / "Originelen"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (track.hash[:16] + ".gpx")
    if not dest.exists():
        write_new(dest, raw)
    return dest


def replace_cache(path, raw):
    """Publish complete cache contents atomically; never truncate the old file."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def download_map(segments, refresh=False, progress=None, waiting=None, tiles=None, cancelled=None, budget=None):
    from road_index import RoadIndex, bounds, road_xml
    from road_provider import prepare_index, routing_query
    budget=budget or DownloadBudget.foreground()
    wanted=tuple(bounds(b) for b in (plan_route_tiles(segments) if tiles is None else tiles))
    query=routing_query(segments)
    with RoadIndex(MAPS) as index:
        prepare_index(index,segments,wanted,query,cancelled=cancelled)
        missing=wanted if refresh else index.missing(wanted)
    if missing:
        _download_map_tiles(segments,refresh,progress,waiting,missing,cancelled,budget)
    with RoadIndex(MAPS) as index:
        index.sync([*wanted,*query],cancelled=cancelled)
        if index.missing(wanted):
            raise ValueError("Niet alle benodigde weggegevens zijn beschikbaar. De route blijft behouden.")
        road=index.read(wanted,query)
        if road is None:raise ValueError("Geen wegen gevonden in de kaartgegevens voor dit gebied.")
        raw=road_xml(road)
    dest=MAPS/map_cache_name(wanted)
    if not dest.exists() or dest.read_bytes()!=raw:replace_cache(dest,raw)
    return dest


def _download_map_tiles(segments, refresh=False, progress=None, waiting=None, tiles=None, cancelled=None, budget=None):
    from road_index import validate_osm
    from road_download import RoadServiceUnavailable, DOWNLOAD_STOPPED
    tiles = plan_route_tiles(segments) if tiles is None else tiles
    dest = MAPS / map_cache_name(tiles)
    root = ET.Element("osm", version="0.6", generator="RouteRefit")
    seen = set()
    budget = DownloadBudget() if budget is None else budget
    staged = {}
    tile_boxes = {}
    tilecache = MAPS / "Vakken"
    tilecache.mkdir(exist_ok=True)
    cache_roots = [tilecache]
    # Reuse the previous local test versions' completed downloads, read-only.
    for version in ("0.9.1", "0.9.0"):
        previous = (
            MAPS.parent.parent / f"GPX-werkbank-{version}-beta-Windows" / "Kaarten" / "Vakken"
        )
        if previous != tilecache and previous.is_dir():
            cache_roots.append(previous)

    def read_tile(b):
        if cancelled and cancelled():
            raise ValueError("Uitlijnen gestopt.")
        key = ",".join(f"{v:.7f}" for v in b)
        cached = tilecache / (key + ".osm")
        tile_boxes[cached] = b
        if not refresh:
            for folder in cache_roots:
                previous = folder / cached.name
                if not previous.exists():
                    continue
                try:
                    raw = previous.read_bytes()
                    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():continue
                    tile = validate_osm(raw)
                    if tile.tag != "osm" or tile.find("remark") is not None:
                        continue
                    if previous != cached:
                        replace_cache(cached, raw)
                    return [tile]
                except (OSError, ET.ParseError, ValueError, TypeError):
                    continue
        try:
            url = road_query_url(b, timeout=budget.query_seconds)
            raw = fetch_road_data(fetch, url, refresh, waiting, budget, cancelled)
            if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                raise ValueError("Ongeldig kaartbestand ontvangen.")
            response=ET.fromstring(raw)
            remark=response.find('remark')
            if remark is not None:
                from road_transport import cooldown
                cooldown(url,20)
                raise RoadServiceUnavailable(DOWNLOAD_STOPPED,reason='incomplete')
            tile = validate_osm(raw)
            if tile.tag != "osm":
                raise ValueError("Geen OSM-kaartgegevens ontvangen.")
            if tile.find("remark") is not None:
                raise ValueError(
                    "De wegendienst heeft geen volledige gegevens geleverd. De GPX blijft geopend; probeer later opnieuw."
                )
            if refresh:
                staged[cached] = raw
            else:
                replace_cache(cached, raw)
            return [tile]
        except urllib.error.HTTPError as exc:
            reason = exc.read().decode("utf-8", errors="replace")[:500]
            exc.close()
            if exc.code == 400 and "too many nodes" in reason.lower():
                raise RoadServiceUnavailable(DOWNLOAD_STOPPED,reason='incomplete') from exc
            raise ValueError(f"Kaartdownload niet gelukt ({exc.code}): {reason}") from exc

    for completed, b in enumerate(tiles, 1):
        requests_before = budget.requests
        for tile in read_tile(b):
            for child in tile:
                key = (child.tag, child.attrib.get("id"))
                if key[1] and key not in seen:
                    seen.add(key)
                    root.append(child)
        if progress:
            progress(completed, len(tiles))
        if completed < len(tiles) and budget.requests > requests_before:
            time.sleep(0.5)
    roads = [
        w for w in root.findall("way") if any(t.get("k") == "highway" for t in w.findall("tag"))
    ]
    used = {n.get("ref") for w in roads for n in w.findall("nd")}
    compact = ET.Element("osm", version="0.6", generator="RouteRefit; OpenStreetMap ODbL")
    for node in root.findall("node"):
        if node.get("id") in used:
            compact.append(node)
    for way in roads:
        compact.append(way)
    for relation in root.findall("relation"):
        if any(
            t.get("k") == "type" and t.get("v") == "restriction" for t in relation.findall("tag")
        ):
            compact.append(relation)
    raw = ET.tostring(compact, encoding="utf-8", xml_declaration=True)
    if roads or refresh:RoadMap(raw)
    if refresh:
        # Publish only after the whole response has passed validation. Index
        # readers keep their previous snapshot until all refreshed files commit.
        from road_index import INDEX_LOCK, RoadIndex
        with INDEX_LOCK:
            for cached,tile_raw in staged.items():replace_cache(cached,tile_raw)
            with RoadIndex(MAPS) as index:
                index.ingest_files([(path,[tile_boxes[path]]) for path in staged])
            replace_cache(dest,raw)
    else:
        replace_cache(dest,raw)
    return dest


class App(AlignmentWorkflow, BackgroundRoads, ProfileSettingsUI, ProposalReviewUI, AccessReviewUI, RouteContextUI, SegmentJoinUI, WorkspaceUI, tk.Tk):
    def __init__(self, arg=None, language=None):
        initialize(BASE, RES, language)
        super().__init__()
        self.title(f"{PRODUCT_NAME} {tr(DISPLAY_VERSION)}")
        self._app_icon = tk.PhotoImage(file=str(RES / 'assets/routerefit.png'))
        self.iconphoto(True, self._app_icon)
        # Start compact enough for the tested Windows display scaling; users can maximize.
        width = min(1100, self.winfo_screenwidth() - 60)
        height = min(680, self.winfo_screenheight() - 120)
        self.geometry(f"{width}x{height}+20+20")
        self.minsize(min(1080, width), min(680, height))
        self.configure(bg="#f3f5f1")
        self.tasks = queue.Queue()
        self.progress = queue.Queue()
        self.busy = False
        self.track = None
        self.source = None
        self.candidate = None
        self.applied_time_estimates = False
        self.roadmap = None
        self.row = None
        self.found = []
        self.last_export = None
        self.warnings = []
        self.dirty = False
        self.zoom = 1
        self.pan = [0, 0]
        self.mouse = None
        self.endpoint_edit_key = None
        self.endpoint_fully_checked = False
        self.auto_issues = []
        self.auto_notes = []
        self.comparison_spots = []
        self.comparison_cursor = -1
        self.comparison_paths = None
        self.auto_checked_key = None
        self.auto_timer = None
        self.simple_workflow = True
        self.live_alignment = None
        self.calculate_after_auto = False
        self.issue_cursor = 0
        self.manual_sections = set()
        self.access_reviews = []
        self.edit_segments = []
        self.history = []
        self.joined_gaps = []
        self.segment_groups = []
        self.selection = None
        self.issue = None
        self.range_anchor = None
        self.range_selection = None
        self.edit_revision = 0
        self.anchor_indices = []
        self.candidate_anchors = None
        self.waypoints = []
        self.approved_photos = set()
        self.waypoint_history = []
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("TFrame", background="#f3f5f1")
        style.configure("TLabel", background="#f3f5f1")
        style.configure("TButton", padding=(8, 4))
        style.configure("Accent.TButton", background="#285b46", foreground="white")
        style.configure("Treeview", rowheight=28)
        style.configure("TLabelframe", background="#f3f5f1")
        apply_theme(self)
        head = ttk.Frame(self, padding=(16, 7))
        head.pack(fill="x")
        ttk.Label(
            head, text="RouteRefit", font=("Segoe UI", 18, "bold"), foreground="#172b45"
        ).pack(side="left")
        ttk.Label(
            head, text=DISPLAY_VERSION, foreground="#58677b"
        ).pack(side="left", padx=24)
        ttk.Button(
            head, text="Route importeren…", command=self.pick_file, style="Accent.TButton"
        ).pack(side="right")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.listtab = ttk.Frame(self.tabs, padding=12)
        self.edit = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.listtab, text=tr("Mijn routeoverzicht"))
        self.tabs.add(self.edit, text=tr("Route bewerken"))
        self.build_catalog()
        self.build_editor()
        footer = ttk.Frame(self, padding=(20, 0, 20, 12))
        footer.pack(fill="x", side="bottom", before=self.tabs)
        self.status = DisplayVar(
            value="Kies een route of open een GPX. Originelen worden apart bewaard."
        )
        self.task_spinner = FluentProgress(footer, length=100)
        self.task_spinner.pack(side="right", padx=8)
        ttk.Label(footer, textvariable=self.status, wraplength=760).pack(side="left")
        self.watch = tk.BooleanVar(value=False)
        ttk.Label(
            footer, text="Lokaal werken · origineel apart bewaard", style="Muted.TLabel"
        ).pack(side="right")
        self.alignment_feedback = ttk.Frame(self, padding=(20, 4, 20, 8))
        self.alignment_phase = DisplayVar(value="")
        self.alignment_elapsed = DisplayVar(value="")
        phase_label=ttk.Label(self.alignment_feedback, textvariable=self.alignment_phase, wraplength=600)
        elapsed_label=ttk.Label(self.alignment_feedback, textvariable=self.alignment_elapsed)
        self.alignment_spinner = FluentProgress(self.alignment_feedback, length=100)
        ttk.Button(self.alignment_feedback, text="Uitlijnen stoppen", command=self.stop_alignment).pack(side="right")
        self.alignment_spinner.pack(side="right", padx=8)
        elapsed_label.pack(side="right", padx=8)
        phase_label.pack(side="left", fill="x", expand=True)
        self.alignment_feedback.bind('<Configure>',lambda event:phase_label.configure(
            wraplength=max(160,event.width-elapsed_label.winfo_reqwidth()-320)))
        self.downloads = Path.home() / "Downloads"
        self.known = {}
        self.stable = {}
        self.begin_watch()
        self.build_workspace(DATA)
        self.after(150, self.poll)
        self.after(2500, self.watch_downloads)
        self.protocol("WM_DELETE_WINDOW", self.close)
        if arg:
            self.after(250, lambda: self.open_argument(arg))

    def build_catalog(self):
        controls = ttk.Frame(self.listtab)
        controls.pack(fill="x", pady=(0, 10))
        self.query = tk.StringVar()
        self.kind = tk.StringVar(value="Alle")
        self.only = tk.BooleanVar(value=True)
        ttk.Label(controls, text="Zoeken").pack(side="left")
        ttk.Entry(controls, textvariable=self.query, width=36).pack(side="left", padx=8)
        ttk.Combobox(
            controls,
            textvariable=self.kind,
            values=["Alle", "Wandelen", "Fietsen"],
            state="readonly",
            width=14,
        ).pack(side="left", padx=8)
        ttk.Checkbutton(
            controls, text="Alleen nog te controleren", variable=self.only, command=self.filter_rows
        ).pack(side="left")
        self.count = ttk.Label(controls)
        self.count.pack(side="right")
        self.query.trace_add("write", lambda *a: self.filter_rows())
        self.kind.trace_add("write", lambda *a: self.filter_rows())
        self.catalog_note = ttk.Label(
            self.listtab,
            text="Importeer desgewenst een eigen routeoverzicht. Bestanden en bewerkingen blijven lokaal; publiceren doe je na controle.",
            foreground="#59695d",
        )
        self.catalog_note.pack(anchor="w", pady=(0, 8))
        frame = ttk.Frame(self.listtab)
        frame.pack(fill="both", expand=True)
        self.routes = ttk.Treeview(
            frame,
            columns=("title", "kind", "region", "status"),
            show="headings",
            selectmode="browse",
        )
        self.routes.localized_columns = {1, 3}
        for key, label, width in [
            ("title", "Route", 480),
            ("kind", "Activiteit", 95),
            ("region", "Streek", 250),
            ("status", "Websitecontrole", 180),
        ]:
            self.routes.heading(key, text=label)
            self.routes.column(key, width=width)
        self.routes.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.routes.yview)
        scroll.pack(side="right", fill="y")
        self.routes.configure(yscrollcommand=scroll.set)
        self.routes.bind("<Double-1>", lambda e: self.download_selected())
        buttons = ttk.Frame(self.listtab)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(
            buttons,
            text="Downloaden en lokaal openen",
            command=self.download_selected,
            style="Accent.TButton",
        ).pack(side="left")
        ttk.Button(
            buttons,
            text="Websitecontroleoverzicht",
            command=lambda: webbrowser.open(
                "https://marcodelnoij.nl/wp-admin/edit.php?post_type=md_route&page=mgw-overview"
            ),
        ).pack(side="left", padx=8)
        ttk.Button(buttons, text="Eigen GPX openen…", command=self.pick_file).pack(side="left")
        ttk.Button(buttons, text="Routeoverzicht bijwerken…", command=self.import_catalog).pack(
            side="right"
        )
        self.filter_rows()

    def import_catalog(self):
        if self.busy:
            return
        p = filedialog.askopenfilename(
            title="Actueel routeoverzicht importeren", filetypes=[("Routeoverzicht JSON", "*.json")]
        )
        if not p:
            return
        try:
            raw = Path(p).read_bytes()
            if len(raw) > 5_000_000:
                raise ValueError("Bestand te groot.")
            rows = json.loads(raw)
            if not isinstance(rows, list) or len(rows) > 10000:
                raise ValueError("Ongeldig routeoverzicht.")
            ids = set()
            for r in rows:
                if (
                    not isinstance(r, dict)
                    or type(r.get("id")) is not int
                    or not 0 < r["id"] < 100000000
                    or r["id"] in ids
                    or r.get("kind") not in ("wandel", "fiets")
                    or type(r.get("controlled")) is not bool
                ):
                    raise ValueError("Ongeldige routegegevens.")
                if any(
                    not isinstance(r.get(k), str) or len(r[k]) > 2000
                    for k in ("title", "region", "checked")
                ):
                    raise ValueError("Ongeldige routevelden.")
                ids.add(r["id"])
            (DATA / "routes-actueel.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            CATALOG[:] = rows
            self.filter_rows()
            self.catalog_note.config(
                text="Lokaal routeoverzicht bijgewerkt op "
                + datetime.now().strftime("%d-%m-%Y %H:%M")
                + ". Geen websitegegevens gewijzigd."
            )
        except Exception as exc:
            messagebox.showerror("Niet geïmporteerd", str(exc))

    def filter_rows(self):
        if not hasattr(self, "routes"):
            return
        self.routes.delete(*self.routes.get_children())
        n = 0
        for r in CATALOG:
            if self.only.get() and r["controlled"]:
                continue
            if self.kind.get() != "Alle" and r["kind"] != (
                "wandel" if self.kind.get() == "Wandelen" else "fiets"
            ):
                continue
            if (
                self.query.get().casefold()
                not in (r["title"] + " " + r["region"] + " " + str(r["id"])).casefold()
            ):
                continue
            self.routes.insert(
                "",
                "end",
                iid=str(r["id"]),
                values=(
                    r["title"],
                    "Wandelen" if r["kind"] == "wandel" else "Fietsen",
                    r["region"],
                    r["checked"]
                    or ("Eerder bevestigd" if r["controlled"] else "Nog te controleren"),
                ),
            )
            n += 1
        self.count.config(text=f"{n} routes")

    def build_editor(self):
        main = ttk.Panedwindow(self.edit, orient="horizontal")
        main.pack(fill="both", expand=True)
        panel = ttk.Frame(main, width=340)
        right = ttk.Frame(main)
        main.add(panel, weight=0)
        main.add(right, weight=1)
        self.editor_panes = main
        self.settings_panel = panel
        leftscroll = tk.Canvas(panel, width=330, background="#f3f5f1", highlightthickness=0)
        bar = ttk.Scrollbar(panel, orient="vertical", command=leftscroll.yview)
        bar.pack(side="right", fill="y")
        leftscroll.pack(side="left", fill="both", expand=True)
        leftscroll.configure(yscrollcommand=bar.set)
        left = ttk.Frame(leftscroll)
        panel_id = leftscroll.create_window(0, 0, window=left, anchor="nw")
        left.bind(
            "<Configure>", lambda e: leftscroll.configure(scrollregion=leftscroll.bbox("all"))
        )
        leftscroll.bind("<Configure>", lambda e: leftscroll.itemconfigure(panel_id, width=e.width))

        def panelwheel(e):
            if str(e.widget).startswith(str(panel)) and not isinstance(
                e.widget, (ttk.Combobox, ttk.Treeview)
            ):
                leftscroll.yview_scroll(
                    -int(e.delta / 120) if abs(e.delta) >= 120 else (-1 if e.delta > 0 else 1),
                    "units",
                )

        self.bind_all("<MouseWheel>", panelwheel, add="+")
        self.name = tk.StringVar(value="Nog geen GPX geopend")
        ttk.Label(left, textvariable=self.name, font=("Segoe UI", 13, "bold"), wraplength=350).pack(
            anchor="w", pady=(0, 10)
        )
        self.settings_tabs = ttk.Notebook(left, style="Settings.TNotebook")
        self.settings_tabs.pack(fill="both", expand=True)
        self.transport_settings_tab = ttk.Frame(self.settings_tabs, padding=8)
        self.route_settings_tab = ttk.Frame(self.settings_tabs, padding=8)
        self.time_settings_tab = ttk.Frame(self.settings_tabs, padding=8)
        self.settings_tabs.add(self.transport_settings_tab, text=tr("Activiteit"))
        self.settings_tabs.add(self.route_settings_tab, text=tr("Route"))
        self.settings_tabs.add(self.time_settings_tab, text=tr("Tijdschema"))
        left = self.transport_settings_tab
        ttk.Label(left, text="1  Activiteit", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.profile = tk.StringVar(value="Wandelen · normaal")  # legacy timing preset, not road selection
        self.flat = tk.StringVar(value="4.5")
        self.transport = tk.StringVar(value="Lopen")
        transport_box = ttk.Combobox(left, textvariable=self.transport, values=list(TRANSPORTS), state="readonly", width=31)
        transport_box.pack(fill="x", pady=6)
        transport_box.bind("<<ComboboxSelected>>", self.transport_changed)
        ttk.Label(left, text="Bepaalt toegang en geschiktheid van wegen.", wraplength=310, style="Muted.TLabel").pack(anchor="w")
        ttk.Button(left, text="Toegang en privéwegen…",
                   command=lambda: self.settings_tabs.select(self.route_settings_tab)).pack(fill="x", pady=(12, 0))
        left = self.route_settings_tab
        ttk.Label(left, text="2  Routevoorkeur", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(12,0))
        self.route_preference = tk.StringVar(value="Meest logisch")
        ttk.Combobox(left, textvariable=self.route_preference, values=list(ROUTE_PREFERENCES), state="readonly", width=31).pack(fill="x", pady=6)
        ttk.Label(left, text="Volg de bestaande route met de huidige lokale wegvoorkeuren.", wraplength=310, style="Muted.TLabel").pack(anchor="w")
        access = ttk.LabelFrame(left, text="Toegang", padding=8)
        access.pack(fill="x", pady=(10, 8))
        self.private_roads = tk.BooleanVar(value=False)
        ttk.Checkbutton(access, text="Sta privéwegen en -paden toe", variable=self.private_roads,
                        command=self.routing_settings_changed).pack(anchor="w")
        ttk.Button(access, text="Toegangsmeldingen…", command=self.accept_access_issues).pack(fill="x", pady=(6, 0))
        ttk.Label(access, text="Andere toegangsmeldingen kun je per route beoordelen; de bestaande lijn blijft behouden.",
                  wraplength=285, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        mapbuttons = ttk.Frame(left)
        mapbuttons.pack(fill="x")
        ttk.Button(mapbuttons, text="Uitlijngegevens ophalen", command=self.get_map).pack(
            fill="x"
        )
        ttk.Button(mapbuttons, text="Importeren…", command=self.import_map).pack(
            fill="x", pady=(4, 0)
        )
        ttk.Button(left, text="Uitlijngegevens vernieuwen", command=self.refresh_map).pack(
            anchor="w", pady=(4, 0)
        )
        self.mapinfo = DisplayVar(
            value="De gewone OSM-kaart laadt vanzelf. Alleen automatisch uitlijnen vereist lokale weggegevens."
        )
        ttk.Label(left, textvariable=self.mapinfo, wraplength=280, foreground="#56685b").pack(
            anchor="w", pady=5
        )
        self.snap = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            left,
            text="Uitlijnen op paden en wegen",
            variable=self.snap,
            command=self.routing_settings_changed,
        ).pack(anchor="w")
        search = ttk.Frame(left)
        search.pack(fill="x")
        self.snapradius = tk.StringVar(value="35")
        ttk.Label(search, text="Maximale uitlijnverschuiving (m)", wraplength=210).pack(side="left")
        ttk.Entry(search, textvariable=self.snapradius, width=7).pack(side="left", padx=8)
        left = self.time_settings_tab
        ttk.Label(left, text="3  Tijdschema", font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(14, 5)
        )
        ttk.Label(left, text="Tempo voor het tijdschema").pack(anchor="w")
        self.time_preset = tk.StringVar(value="Normaal")
        self.time_preset_box = ttk.Combobox(left, textvariable=self.time_preset, state="readonly", width=31)
        self.refresh_time_presets()
        self.time_preset.set(tr("Normaal"))
        self.time_preset_box.pack(fill="x", pady=6)
        self.time_preset_box.bind("<<ComboboxSelected>>", self.time_preset_changed)
        ttk.Label(left, text="Tempo en snelheid wijzigen alleen het tijdschema, niet de wegkeuze.", wraplength=310, style="Muted.TLabel").pack(anchor="w")
        self.timing = tk.StringVar(value="pause")
        for value, text in [
            ("pause", "Bestaande opname: pauzes verwijderen"),
            ("model", "Nieuw tijdprofiel berekenen"),
        ]:
            ttk.Radiobutton(
                left, text=text, variable=self.timing, value=value, command=self.invalidate
            ).pack(anchor="w", pady=2)
        settings = ttk.Frame(left)
        settings.pack(fill="x", pady=6)
        self.minimum = tk.StringVar(value="2")
        self.radius = tk.StringVar(value="20")
        ttk.Label(settings, text="Pauze vanaf (min)").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.minimum, width=7).grid(row=0, column=1, padx=8)
        ttk.Label(settings, text="Stilstandsgebied (m)").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(settings, textvariable=self.radius, width=7).grid(row=1, column=1, padx=8)
        ttk.Button(left, text="Pauzes zoeken / opnieuw berekenen", command=self.find_pauses).pack(
            fill="x", pady=3
        )
        self.timehint = DisplayVar()
        ttk.Label(left, textvariable=self.timehint, wraplength=320, foreground="#56685b").pack(
            anchor="w", pady=3
        )
        self.pausebox = ttk.Treeview(
            left,
            columns=("use", "time", "length", "note"),
            show="headings",
            height=4,
            selectmode="browse",
        )
        self.pausebox.localized_columns = {3}
        for key, title, width in [
            ("use", "Weg", 35),
            ("time", "Begin", 65),
            ("length", "Duur", 80),
            ("note", "Beoordeling", 150),
        ]:
            self.pausebox.heading(key, text=title)
            self.pausebox.column(key, width=width, stretch=key == "note")
        self.pausebox.pack(fill="x", pady=5)
        self.pausebox.bind("<Double-1>", self.toggle_pause)
        self.pausebox.bind("<<TreeviewSelect>>", self.pause_selected)
        ttk.Label(
            left,
            text="Dubbelklik op een pauze om die te kiezen.\nMeetgaten staan standaard uit.",
            foreground="#59695d",
        ).pack(anchor="w")
        model = ttk.Frame(left)
        model.pack(fill="x", pady=8)
        self.target = tk.StringVar()
        self.start = tk.StringVar(value="2026-01-01 08:00")
        for i, (label, var) in enumerate(
            [
                ("Vlakke snelheid (km/u)", self.flat),
                ("Gewenste duur (uu:mm, optioneel)", self.target),
                ("Starttijd (UTC)", self.start),
            ]
        ):
            ttk.Label(model, text=label, wraplength=155).grid(row=i, column=0, sticky="w", pady=3)
            ttk.Entry(model, textvariable=var, width=16).grid(row=i, column=1, padx=5)
        ttk.Button(
            left, text="Voorbeeld berekenen", command=self.calculate, style="Accent.TButton"
        ).pack(fill="x", pady=5)
        self.approved = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            left, text="Lijn, tijden en meldingen gecontroleerd", variable=self.approved
        ).pack(anchor="w", pady=5)
        ttk.Button(left, text="Aparte GPX + controlerapport opslaan", command=self.save).pack(
            fill="x", pady=3
        )
        ttk.Button(
            left, text="Uploadscherm van deze route openen", command=self.upload_screen
        ).pack(fill="x", pady=3)
        ttk.Button(
            left, text="Map met mijn bewerkingen", command=lambda: os.startfile(str(DATA))
        ).pack(fill="x", pady=3)
        self.summary = DisplayVar(value="Open een route om te beginnen.")
        ttk.Label(right, textvariable=self.summary, font=("Segoe UI", 11), wraplength=850).pack(
            fill="x", pady=(0, 6)
        )
        # Keep navigation, editing modes and the review/export flow on separate rows.
        self.build_editor_toolbar(right)
        anchorbar = ttk.Frame(right)
        anchorbar.pack(fill="x", pady=(0, 6))
        self.anchorbar = anchorbar
        ttk.Label(anchorbar, text="Verdeling:").pack(side="left")
        self.density = tk.StringVar(value="Normaal")
        density = ttk.Combobox(
            anchorbar,
            textvariable=self.density,
            values=list(ANCHOR_DENSITY),
            state="readonly",
            width=9,
        )
        density.pack(side="left", padx=5)
        density.bind("<<ComboboxSelected>>", self.redistribute_anchors)
        self.anchor_count = ttk.Label(anchorbar, text="0 hoofdpunten")
        self.anchor_count.pack(side="left", padx=8)
        endpoint_button = ttk.Menubutton(anchorbar, text="Start/eind verplaatsen ▾")
        endpoint_button.pack(side="left", padx=4)
        endpoint_menu = tk.Menu(endpoint_button, tearoff=False)
        for target, label in [
            ("start", "Startpunt verplaatsen"),
            ("end", "Eindpunt verplaatsen"),
            ("both", "Start en eind samen verplaatsen"),
        ]:
            endpoint_menu.add_command(label=label, command=lambda t=target: self.endpoint_mode(t))
        endpoint_button.configure(menu=endpoint_menu)
        ttk.Button(anchorbar, text="Voorstel overnemen", command=self.adopt_candidate).pack(
            side="right"
        )
        self.waypoint_button = ttk.Button(
            anchorbar, text="Waypoints (0)", command=self.waypoint_list
        )
        self.waypoint_button.pack(side="right", padx=4)
        ttk.Button(anchorbar, text="+ Waypoint", command=self.waypoint_mode).pack(side="right")
        autob = ttk.Frame(right)
        autob.pack(fill="x", pady=(0, 4))
        self.autobar = autob
        self.auto_mode = tk.BooleanVar(value=True)
        self.show_all_anchors = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            autob,
            text="Automatisch · alleen problemen",
            variable=self.auto_mode,
            command=self.auto_mode_changed,
        ).pack(side="left")
        ttk.Button(autob, text="Opnieuw controleren", command=self.start_auto_alignment).pack(
            side="left", padx=4
        )
        ttk.Button(autob, text="Uitlijngegevens vernieuwen", command=self.refresh_map).pack(
            side="left"
        )
        self.auto_summary = DisplayVar(value="Open een route")
        ttk.Label(autob, textvariable=self.auto_summary).pack(side="left", padx=6)
        ttk.Button(autob, text="Volgende ›", command=lambda: self.navigate_problem(1)).pack(
            side="right"
        )
        ttk.Button(autob, text="‹ Vorige", command=lambda: self.navigate_problem(-1)).pack(
            side="right", padx=4
        )
        ttk.Checkbutton(
            self.route_settings_tab,
            text="Toon alle hoofdpunten op de kaart",
            variable=self.show_all_anchors,
            command=self.draw,
        ).pack(anchor="w", pady=4)
        self.pointinfo = DisplayVar(
            value="Sleep een groter geel hoofdpunt naar het juiste pad. De twee aangrenzende stukken volgen de wegen automatisch."
        )
        ttk.Label(right, textvariable=self.pointinfo, wraplength=950, foreground="#3d6174").pack(
            fill="x", pady=(0, 5)
        )
        self.repairbar = ttk.Frame(right)
        ttk.Button(self.repairbar, text="Zoek herstelvoorstel", command=self.recover_range).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(self.repairbar, text="Opnieuw uitlijnen", command=self.reroute_range).pack(
            side="left"
        )
        ttk.Button(
            self.repairbar, text="Stuk vervangen…", command=self.replace_range_with_via
        ).pack(side="left", padx=4)
        ttk.Button(
            self.repairbar, text="Dit stuk handmatig behouden", command=self.keep_range
        ).pack(side="left", padx=4)
        ttk.Button(self.repairbar, text="Uitleg", command=self.show_messages).pack(side="left")
        self.canvas = RouteMap(
            right,
            MAPS / "OSM-achtergrond",
            self.point_selected,
            self.point_moved,
            self.point_inserted,
            self.status_notice,
            on_waypoint=self.add_waypoint,
            on_waypoint_select=self.edit_waypoint,
            on_waypoint_move=self.move_waypoint,
            on_endpoint=self.place_endpoint,
            height=120,
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Button-3>", self.route_context_menu)
        self.canvas.set_mode("anchor")
        legend = ttk.Frame(right)
        legend.pack(fill="x", pady=4)
        self.maplegend = legend
        ttk.Label(
            legend,
            text="Oranje: origineel · Blauw: bewerkbaar · Groen: voorstel",
            foreground="#526357",
        ).pack(side="left")
        ttk.Button(legend, text="Hele route", command=self.reset_view).pack(side="right")
        ttk.Button(legend, text="Toon probleemplaats", command=self.show_issue).pack(
            side="right", padx=4
        )
        ttk.Button(legend, text="Gekozen stuk uitlijnen", command=self.reroute_range).pack(
            side="right", padx=4
        )
        ttk.Button(legend, text="Meldingen", command=self.show_messages).pack(side="left", padx=5)
        self.show_profile = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            legend, text="Snelheid", variable=self.show_profile, command=self.draw
        ).pack(side="left")
        self.chart = tk.Canvas(
            right,
            height=80,
            background="white",
            highlightthickness=1,
            highlightbackground="#d4dcd1",
        )
        self.messages = tk.Text(
            right,
            height=4,
            wrap="word",
            font=("Segoe UI", 10),
            background="#fffaf0",
            relief="flat",
            padx=10,
            pady=8,
        )
        self.messages.localize = True
        self.messages.insert(
            "end",
            "Origineel blijft bewaard. Websitepublicatie gebeurt via het bestaande uploadscherm, na jouw controle.",
        )
        for var in [self.flat, self.target, self.start, self.minimum, self.radius, self.profile]:
            var.trace_add("write", lambda *a: self.invalidate())
        self.flat.trace_add("write", self.flat_speed_changed)
        self.snapradius.trace_add("write", lambda *a: self.routing_settings_changed())

    def routing_key(self):
        return (
            self.edit_revision,
            self.density.get(),
            self.routing_mode(),
            self.routing_style(),
            self.route_preference.get(),
            self.snapradius.get(),
            self.private_roads.get(),
            self.snap.get(),
            getattr(self, "map_revision", 0),
        )

    def routing_settings_changed(self):
        self.clear_access_reviews()
        self.invalidate()
        self.auto_checked_key = None
        self.schedule_auto()

    def auto_mode_changed(self):
        self.selection = None
        self.invalidate()
        self.auto_checked_key = None
        self.draw()
        if self.auto_mode.get():
            self.schedule_auto()
        else:
            self.auto_summary.set("Handmatig bewerken")
            self.repairbar.pack_forget()

    def schedule_auto(self):
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        if getattr(self, "simple_workflow", False):
            return
        if not self.track or not self.auto_mode.get() or not self.snap.get():
            return
        self.auto_summary.set("Controle wordt voorbereid…")

        def run():
            self.auto_timer = None
            if self.busy:
                self.schedule_auto()
                return
            if self.roadmap:
                self.start_auto_alignment()
            else:
                self.auto_summary.set("Weggegevens nodig")

        self.auto_timer = self.after(600, run)

    def start_auto_alignment(self):
        if not self.require_track() or self.busy:
            return
        if not self.roadmap:
            return self.get_map()
        if not self.snap.get():
            self.snap.set(True)
        try:
            radius = float(self.snapradius.get().replace(",", "."))
            if not math.isfinite(radius) or not 5 <= radius <= 150:
                raise ValueError("Gebruik een uitlijnverschuiving van 5–150 meter.")
        except ValueError as exc:
            return messagebox.showinfo("Zoekafstand controleren", str(exc))
        if not self.auto_mode.get():
            self.auto_mode.set(True)
        segments = copy.deepcopy(self.edit_segments)
        controls = copy.deepcopy(self.anchor_indices)
        kept = manual_intervals(segments, controls, self.manual_sections)
        private = self.private_roads.get()
        mode = self.routing_mode()
        key = self.routing_key()
        road = self.roadmap
        self.auto_summary.set("Alle routedelen controleren…")

        def apply_result(result):
            if key != self.routing_key() or not self.auto_mode.get():
                self.auto_summary.set("Route of instellingen gewijzigd")
                self.schedule_auto()
                return
            out, notes, mapped, issues = result
            unchanged = (
                mapped == self.anchor_indices
                and len(out) == len(self.edit_segments)
                and all(
                    len(a) == len(b) and all(distance(p, q) < 0.02 for p, q in zip(a, b))
                    for a, b in zip(out, self.edit_segments)
                )
            )
            if not unchanged:
                self.remember()
            self.edit_segments = out
            self.anchor_indices = mapped
            self.issue = None
            self.range_selection = None
            self.range_anchor = None
            self.selection = None
            self.repairbar.pack_forget()
            self.found = []
            self.pausebox.delete(*self.pausebox.get_children())
            self.auto_issues = issues
            self.auto_notes = notes
            self.edit_revision += 1
            self.invalidate()
            self.dirty = True
            self.endpoint_edit_key = None
            self.endpoint_fully_checked = False
            self.auto_checked_key = self.routing_key()
            self.issue_cursor = 0
            self.messages.delete("1.0", "end")
            self.messages.insert("end", "\n".join(notes))
            self.update_stats()
            self.draw()
            if issues:
                self.navigate_problem(0)
            else:
                kept_count = len(
                    manual_intervals(self.edit_segments, self.anchor_indices, self.manual_sections)
                )
                self.auto_summary.set(
                    "Geen open problemen"
                    + (f" · {kept_count} handmatig behouden" if kept_count else "")
                )
                self.pointinfo.set(
                    "Uitlijncontrole afgerond. De hoofdpunten zijn verborgen. Je kunt nu het tijdprofiel berekenen."
                )
                self.status.set(
                    "Automatische uitlijning klaar. Geen onopgeloste uitlijnproblemen gevonden."
                )
                if BIKE_HEADWAY_WARNING in notes:
                    self.pointinfo.set(BIKE_HEADWAY_WARNING)
                    self.status.set(
                        "Uitgelijnd met aandachtspunten voor fietswegen; bekijk Controle → Meldingen en uitleg."
                    )
                if ADAPTED_ROAD_WARNING in notes:
                    self.pointinfo.set(ADAPTED_ROAD_WARNING)
                    self.status.set(ADAPTED_ROAD_WARNING)
            continue_calculation = self.calculate_after_auto
            self.calculate_after_auto = False
            if continue_calculation and not issues:
                self.after(0, self.calculate)

        def done(result):
            if key != self.routing_key() or not self.auto_mode.get():
                return
            out, notes, mapped, issues = result
            if self.calculate_after_auto and not issues:
                self.calculate_after_auto = False
                # Build one combined geometry/time preview; the editable route stays intact.
                self.calculate(alignment_ready=True)
                return
            if same_route(self.edit_segments, out):
                apply_result(result)
            else:
                self.review_route_proposal(out, lambda: apply_result(result),
                                           key=self.settings_key(), key_fn=self.settings_key, notes=notes,
                                           on_cancel=lambda: setattr(self, 'calculate_after_auto', False))

        self.job(
            lambda: automatic_alignment(road, segments, controls, mode, radius, kept, private),
            done,
            "Route automatisch uitlijnen; probleemstukken verzamelen…",
        )

    def navigate_problem(self, step=0):
        if not self.auto_issues:
            self.status.set(
                "Geen onopgeloste uitlijnproblemen."
                if self.auto_checked_key == self.routing_key()
                else "Kies Opnieuw controleren."
            )
            return
        self.issue_cursor = (self.issue_cursor + step) % len(self.auto_issues)
        problem = self.auto_issues[self.issue_cursor]
        si, a, b = problem.segment, problem.start, problem.end
        segment = self.edit_segments[si]
        p = segment[a]
        km = (
            sum(cumulative(s)[-1] for s in self.edit_segments[:si]) + cumulative(segment)[a]
        ) / 1000
        self.issue = dict(point=p, segment=si, index=a, label=f"Aandacht · {km:.2f} km")
        self.range_selection = (si, a, b)
        self.range_anchor = None
        self.selection = None
        self.repairbar.pack(fill="x", pady=(0, 4), before=self.canvas)
        self.auto_summary.set(f"Probleem {self.issue_cursor + 1} van {len(self.auto_issues)}")
        self.pointinfo.set(
            f"{km:.2f} km: kies Zoek herstelvoorstel voor een plaatselijke oplossing, verplaats een hoofdpunt of behoud het stuk."
        )
        self.messages.delete("1.0", "end")
        self.messages.insert(
            "end", "\n".join(self.auto_notes) + "\n\nGekozen probleem:\n" + problem.reason
        )
        self.draw()
        self.after_idle(lambda: self.canvas.fit([segment[a : b + 1]]))
        self.status.set("Controleer het paarse stuk. Je kunt de gele hoofdpunten verplaatsen.")

    def toggle_settings(self):
        self.tabs.select(self.edit)
        if str(self.settings_panel) in self.editor_panes.panes():
            self.editor_panes.forget(self.settings_panel)
        else:
            self.editor_panes.insert(0, self.settings_panel, weight=0)

    def show_messages(self):
        window = tk.Toplevel(self)
        window.title("Meldingen en uitleg")
        window.geometry("740x360")
        text = tk.Text(window, wrap="word", font=("Segoe UI", 11), padx=15, pady=15)
        text.pack(fill="both", expand=True)
        text.insert("1.0", self.messages.get("1.0", "end"))
        text.config(state="disabled")
        ttk.Button(window, text="Sluiten", command=window.destroy).pack(pady=6)

    def keep_range(self):
        if self.busy or not self.range_selection:
            return
        si, start, end = self.range_selection
        if start == end:
            return
        self.remember()
        s = self.edit_segments[si]
        indices = sorted(set(self.anchor_indices[si] + [start, end]))
        self.anchor_indices[si] = indices
        for a, b in zip(indices, indices[1:]):
            if start <= a < b <= end:
                self.manual_sections.add(leg_key(si, s[a], s[b]))
        self.geometry_changed(
            "Gekozen stuk handmatig behouden; de rest kan automatisch worden uitgelijnd."
        )
        self.pointinfo.set(
            "Handmatig stuk behouden. Bereken het voorstel opnieuw; dit deel behoudt jouw lijn."
        )

    def invalidate(self):
        self.approved.set(False)
        if self.candidate is not None:
            self.candidate = None
            self.last_export = None
            self.status.set("Instelling gewijzigd: bereken het voorbeeld opnieuw.")
            self.draw()
            self.update_stats()

    def settings_key(self):
        return (
            (self.edit_revision, self.density.get())
            + tuple(
                v.get()
                for v in [
                    self.profile,
                    self.transport,
                    self.route_preference,
                    self.flat,
                    self.target,
                    self.start,
                    self.minimum,
                    self.radius,
                    self.snap,
                    self.timing,
                    self.snapradius,
                    self.private_roads,
                    self.auto_mode,
                ]
            )
            + tuple(p.selected for p in self.found)
        )

    def change_profile(self, event=None):
        # A timing preset never invalidates access review or the route alignment key.
        self.flat.set(str(PROFILES[self.profile.get()][1]))
        self.invalidate()

    def job(self, fn, done, message, on_error=None):
        if self.busy:
            return messagebox.showinfo("Even wachten", "De vorige bewerking loopt nog.")
        self.busy = True
        self.task_spinner.start()
        self.status.set(message)

        def work():
            try:
                self.tasks.put((done, fn(), None))
            except Exception as exc:
                self.tasks.put((on_error, None, exc))

        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        self.after(150, self.poll)
        try:
            for _ in range(100):
                message = self.progress.get_nowait()
                if isinstance(message, tuple):
                    token, message = message
                    if getattr(self, "road_loading", None) is not token:
                        continue
                self.status.set(message)
        except queue.Empty:
            pass
        try:
            for _ in range(100):
                fn, result, error = self.tasks.get_nowait()
                self.busy = False
                self.task_spinner.stop()
                if error:
                    if fn is not None:
                        fn(error)
                    elif isinstance(error, AlignmentError):
                        self.alignment_problem(error)
                    else:
                        self.status.set("Bewerking niet uitgevoerd.")
                        messagebox.showerror("Controle nodig", str(error))
                else:
                    try:
                        fn(result)
                    except Exception as exc:
                        messagebox.showerror("Controle nodig", str(exc))
        except queue.Empty:
            pass

    def may_replace(self):
        if self.busy:
            messagebox.showinfo("Even wachten", "Er loopt nog een bewerking.")
            return False
        return not self.dirty or messagebox.askyesno(
            "Nieuw bestand",
            "De huidige bewerking is nog niet opgeslagen. Wil je toch een ander bestand openen?",
        )

    def pick_file(self):
        if not self.may_replace():
            return
        p = filedialog.askopenfilename(title="Routebestand importeren", filetypes=FILETYPES)
        if p:
            self.safe_load(Path(p))

    def open_argument(self, arg):
        if arg.startswith("gpxwerkbank:"):
            m = re.fullmatch(r"gpxwerkbank://route/(\d{1,8})/?", arg)
            if not m:
                messagebox.showerror(
                    "Ongeldige route",
                    "Alleen een routenummer van marcodelnoij.nl kan worden geopend.",
                )
                return
            self.download_id(int(m.group(1)))
        elif Path(arg).is_file():
            self.safe_load(Path(arg))

    def download_selected(self):
        sel = self.routes.selection()
        if sel:
            self.download_id(int(sel[0]))

    @staticmethod
    def _download_import(rid):
        path = route_download(rid)
        return path, read_route(path)

    def download_id(self, rid):
        if not self.may_replace():
            return
        row = next((r for r in CATALOG if r["id"] == rid), None)
        self.job(
            lambda: self._download_import(rid),
            lambda result: self.load(result[0], row, result[1]),
            "GPX downloaden en origineel bewaren…",
        )

    def load(self, path, row, imported=None, autoload_roads=True):
        self.cancel_road_enrichment(clear=True)
        imported = read_route(path) if imported is None else imported
        raw = imported.gpx
        track = imported.track
        saved = {}
        if imported.converted:
            import hashlib

            sources = DATA / "Bronbestanden"
            sources.mkdir(exist_ok=True)
            archive = sources / (hashlib.sha256(imported.original).hexdigest() + imported.suffix)
            if not archive.exists():
                write_new(archive, imported.original)
        try:
            candidate = json.loads(path.with_suffix(".controle.json").read_text(encoding="utf-8"))
            if isinstance(candidate, dict) and candidate.get("result_sha256") == track.hash:
                saved = candidate
        except (OSError, ValueError, TypeError):
            pass
        if row is None and saved.get("route_id"):
            row = next((r for r in CATALOG if r["id"] == saved["route_id"]), None)
        if row is None:
            for possible in CATALOG:
                archived = DATA / str(possible["id"]) / "Originelen" / (track.hash[:16] + ".gpx")
                if archived.exists() and archived.read_bytes() == raw:
                    row = possible
                    break
        folder = DATA / ("losse-bestanden" if not row else str(row["id"])) / "Originelen"
        folder.mkdir(parents=True, exist_ok=True)
        original = folder / (track.hash[:16] + ".gpx")
        if not original.exists():
            write_new(original, raw)
        self.source = original
        self.track = track
        self.row = row
        self.candidate = None
        self.last_export = None
        self.found = []
        self.roadmap = None
        self.map_path = None
        self._statistics_cache.clear()
        self.endpoint_edit_key = None
        self.endpoint_fully_checked = False
        self.auto_issues = []
        self.auto_notes = []
        self.auto_checked_key = None
        self.calculate_after_auto = False
        self.auto_summary.set("Nog niet gecontroleerd")
        self.comparison_paths = None
        self.comparison_spots = []
        self.comparison_cursor = -1
        self.manual_sections = set()
        self.access_reviews = []
        self.repairbar.pack_forget()
        self.private_roads.set(False)
        self.pointinfo.set(
            "Sleep een groter geel hoofdpunt naar het juiste pad. De aangrenzende stukken volgen de wegen automatisch."
        )
        self.edit_segments = [list(s) for s in track.segments]
        self.history = []
        self.joined_gaps = (
            [g for g in saved.get("reconstructed_gaps", [])[:200] if isinstance(g, dict)]
            if isinstance(saved.get("reconstructed_gaps"), list)
            else []
        )
        self.segment_groups = [[i] for i in range(len(track.segments))]
        self.selection = None
        self.issue = None
        self.range_anchor = None
        self.range_selection = None
        self.edit_revision = 0
        self.anchor_indices = choose_anchors(self.edit_segments, self.density.get())
        self.candidate_anchors = None
        restored = saved.get("main_points")
        if (
            isinstance(restored, list)
            and len(restored) == len(self.edit_segments)
            and all(
                isinstance(a, list)
                and a
                and all(type(i) is int and 0 <= i < len(seg) for i in a)
                and a == sorted(set(a))
                and a[0] == 0
                and a[-1] == len(seg) - 1
                for a, seg in zip(restored, self.edit_segments)
            )
        ):
            self.anchor_indices = restored
        self.manual_sections = {
            tuple(k)
            for k in saved.get("manual_sections", [])
            if isinstance(k, list) and len(k) == 5 and all(type(v) in (int, float) for v in k)
        }
        settings = saved.get("settings", {})
        if not isinstance(settings, dict):
            settings = {}
        self.private_roads.set(settings.get("allow_private") is True)
        selected_profile = settings.get("profile")
        known_activity = isinstance(selected_profile, str) and selected_profile in PROFILES
        if not known_activity:
            mode = ("bike" if row["kind"] == "fiets" else "walk") if row else track.activity_mode
            known_activity = mode in ("walk", "bike", "motorcar", "motorcycle")
            selected_profile = {'bike':'Fietsen · trekking','motorcar':'Auto · normaal',
                                'motorcycle':'Motor · normaal'}.get(mode,'Wandelen · normaal')
        self.auto_mode.set(
            known_activity and settings.get("automatic_alignment", True) is not False
        )
        self.show_all_anchors.set(True)
        self.applied_time_estimates = settings.get("estimated") is True
        self.load_profile_settings(settings, selected_profile)
        self.restore_access_reviews(saved, self.routing_mode())
        self.waypoints = [
            replace(w, name=w.name or f"Waypoint {i + 1}") for i, w in enumerate(track.waypoints)
        ]
        self.approved_photos = set()
        self.waypoint_history = []
        for w in self.waypoints:
            if not w.photo or "://" in w.photo:
                continue
            photo = Path(unquote(w.photo))
            if photo.is_absolute():
                continue
            resolved = (path.parent / photo).resolve()
            if resolved.is_relative_to(path.parent.resolve()) and resolved.is_file():
                try:
                    validate_photo(resolved)
                    w.photo = str(resolved)
                    self.approved_photos.add(w.key)
                except ValueError:
                    pass
        self.dirty = False
        self.approved.set(False)
        self.pausebox.delete(*self.pausebox.get_children())
        self.name.set(row["title"] if row else track.name)
        saved_timing = settings.get("timing_mode")
        self.timing.set(saved_timing if saved_timing in ("pause", "model") else ("pause" if track.stats()["valid_time"] else "model"))
        target_duration = settings.get("target_duration", "")
        self.target.set(target_duration if isinstance(target_duration, str) and (not target_duration or re.fullmatch(r"[0-9]+:[0-5][0-9]", target_duration)) else "")
        if track.segments[0][0].time:
            self.start.set(track.segments[0][0].time.strftime("%Y-%m-%d %H:%M"))
        saved_start = settings.get("start_time_utc")
        if isinstance(saved_start, str):
            try:
                datetime.strptime(saved_start, "%Y-%m-%d %H:%M")
                self.start.set(saved_start)
            except ValueError:
                pass
        self.tabs.select(self.edit)
        self.mapinfo.set(
            "OSM-achtergrond laadt vanzelf. Voor automatisch uitlijnen kun je hieronder weggegevens ophalen."
        )
        self.reset_view()
        self.update_stats()
        editor_mode = settings.get("editor_mode", "anchor")
        if editor_mode not in ("anchor", "edit", "range", "view"):
            editor_mode = "anchor"
        self.mapmode.set(editor_mode)
        self.canvas.set_mode(editor_mode)
        self.draw()
        self.status.set("GPX geopend. De grotere gele punten sturen de route.")
        self.messages.delete("1.0", "end")
        self.messages.insert(
            "end",
            "Sleep een geel hoofdpunt naar een weg of pad: alleen de stukken naar het vorige en volgende hoofdpunt worden opnieuw gelegd. Dubbelklik op de lijn om een extra hoofdpunt toe te voegen.\n“+ Waypoint” plaatst een benoemde plek met foto en maximaal 1.500 tekens omschrijving. De GPX blijft lokaal.",
        )
        if imported.converted:
            self.messages.insert(
                "end",
                "\nGeïmporteerd als GPX: lijn, hoogtes, beschikbare tijden en waypoints. Sensorwaarden, kaartstijlen en apparaatspecifieke velden worden niet overgenomen. Het oorspronkelijke bronbestand is apart bewaard.",
            )
            self.status.set(
                "Route geïmporteerd als GPX. Bronbestand apart bewaard; bekijk Meldingen voor conversiedetails."
            )
        if not known_activity:
            self.status.set(
                "GPX geopend. Activiteit niet herkend: kies Wandelen of Fietsen bij Route-instellingen en start daarna Opnieuw controleren."
            )
        self.cancel_alignment()
        self.auto_mode.set(False)
        self.show_all_anchors.set(True)
        self.status.set("Route geopend. Kies Automatisch uitlijnen of Handmatig uitlijnen.")
        self.draw()

    def load_comparison(self, original, adjusted):
        """Open two local files together without starting a new alignment job."""
        original, adjusted = Path(original), Path(adjusted)
        imported = read_route(adjusted)
        report = {}
        try:
            candidate = json.loads(
                adjusted.with_suffix(".controle.json").read_text(encoding="utf-8")
            )
            if (
                isinstance(candidate, dict)
                and candidate.get("result_sha256") == imported.track.hash
            ):
                report = candidate
        except (OSError, ValueError, TypeError):
            pass
        reference = original
        original_route = read_route(original)
        if len(original_route.track.segments) != len(imported.track.segments) and not report.get(
            "source_segment_groups"
        ):
            # A converter update may join lap boundaries that older comparison
            # files kept separate. Use the hash-verified historical conversion.
            archived = original.with_name("geimporteerd.gpx")
            if archived.is_file():
                archived_route = read_route(archived)
                import hashlib

                if (
                    report.get("converted_sha256") == archived_route.track.hash
                    and report.get("original_sha256")
                    == hashlib.sha256(original_route.original).hexdigest()
                    and len(archived_route.track.segments) == len(imported.track.segments)
                ):
                    reference, original_route = archived, archived_route
        self.load(reference, None, imported=original_route, autoload_roads=False)
        self.comparison_paths = (original, adjusted)
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        self.auto_mode.set(False)
        self.remember()
        self.edit_segments = [list(s) for s in imported.track.segments]
        self.joined_gaps = (
            [g for g in report.get("reconstructed_gaps", [])[:200] if isinstance(g, dict)]
            if isinstance(report.get("reconstructed_gaps"), list)
            else []
        )
        groups = report.get("source_segment_groups")
        if (
            isinstance(groups, list)
            and len(groups) == len(self.edit_segments)
            and all(isinstance(g, list) and g for g in groups)
            and [i for g in groups for i in g] == list(range(len(self.track.segments)))
            and all(type(i) is int for g in groups for i in g)
        ):
            self.segment_groups = groups
        elif len(self.edit_segments) != len(self.track.segments):
            raise ValueError(
                "De aangepaste route heeft een andere indeling. Open deze GPX afzonderlijk om verder te bewerken."
            )
        self.anchor_indices = choose_anchors(self.edit_segments, self.density.get())
        self.manual_sections = set()
        self.access_reviews = []
        self.auto_issues = []
        for item in report.get("issues", []) if isinstance(report.get("issues", []), list) else []:
            if not isinstance(item, dict):
                continue
            si, a, b = (item.get(k) for k in ("segment", "start", "end"))
            if (
                all(type(i) is int for i in (si, a, b))
                and 0 <= si < len(self.edit_segments)
                and 0 <= a <= b < len(self.edit_segments[si])
            ):
                from auto_alignment import ReviewIssue

                self.auto_issues.append(ReviewIssue(si, a, b, str(item.get("reason", ""))[:2000]))
        notes = report.get("notes", [])
        self.auto_notes = (
            [n for n in notes if isinstance(n, str)] if isinstance(notes, list) else []
        )
        self.comparison_spots = []
        self.comparison_cursor = -1
        spots = report.get("review_sections", [])
        for spot in spots if isinstance(spots, list) else []:
            if not isinstance(spot, dict):
                continue
            lat, lon = spot.get("lat"), spot.get("lon")
            if (
                type(lat) in (int, float)
                and type(lon) in (int, float)
                and math.isfinite(lat)
                and math.isfinite(lon)
                and -85 <= lat <= 85
                and -180 <= lon <= 180
            ):
                self.comparison_spots.append((str(spot.get("title", ""))[:200], Point(lat, lon)))
        self.edit_revision += 1
        self.invalidate()
        self.dirty = False
        self.mapmode.set("view")
        self.canvas.set_mode("view")
        self.auto_summary.set("Vergelijking van origineel en aangepaste route")
        legend = "Oranje: originele route · Blauw: aangepaste route · Rood: nog controleren"
        if report.get("previous_sha256") == self.track.hash:
            legend = "Oranje: vorige versie · Blauw: aangepast voorstel · Rood: nog controleren"
        self.pointinfo.set(legend)
        self.status.set(legend)
        self.messages.delete("1.0", "end")
        self.messages.insert("end", legend + "\n\n" + "\n".join(self.auto_notes))
        self.update_stats()
        self.reset_view()
        focus = report.get("focus")
        if (
            isinstance(focus, list)
            and len(focus) == 2
            and all(type(v) in (int, float) and math.isfinite(v) for v in focus)
            and -85 <= focus[0] <= 85
            and -180 <= focus[1] <= 180
        ):
            self.after(300, lambda: self.canvas.focus_point(Point(*focus), 17))
        try:
            cached = MAPS / map_cache_name(plan_route_tiles(self.track.segments))
        except ValueError:
            cached = None
        if cached is not None and cached.is_file():
            self.job(
                lambda: (cached, __import__("road_provider").downloaded_road(MAPS,cached,self.track.segments)),
                self.set_map,
                "Eerder bewaarde uitlijngegevens openen…",
                on_error=self.map_download_unavailable,
            )

    def pick_comparison(self):
        if self.busy or not self.track:
            return messagebox.showinfo("Vergelijken", "Open eerst de originele route.")
        if self.dirty and not messagebox.askyesno(
            "Niet opgeslagen", "De huidige bewerking vervangen door een vergelijking?"
        ):
            return
        path = filedialog.askopenfilename(title="Aangepaste route kiezen", filetypes=FILETYPES)
        if path:
            try:
                self.load_comparison(self.source, Path(path))
            except (OSError, ValueError) as exc:
                messagebox.showerror("Vergelijken", str(exc))

    def show_changed_spot(self, step=1):
        if not self.comparison_spots:
            self.status.set("Geen gewijzigde plekken in dit vergelijkingsrapport.")
            return
        self.comparison_cursor = (self.comparison_cursor + step) % len(self.comparison_spots)
        title, point = self.comparison_spots[self.comparison_cursor]
        self.tabs.select(self.edit)
        self.canvas.focus_point(point, 17)
        self.status.set(
            f"Gewijzigde plek {self.comparison_cursor + 1}/{len(self.comparison_spots)}: {title}"
        )

    def map_progress(self, completed, total):
        message = f"Weggegevens op achtergrond: {completed}/{total} kaartvakken; Puntjes blijft beschikbaar"
        token = getattr(self, "road_loading", None)
        self.progress.put((token, message) if token is not None else message)

    def map_download_unavailable(self, error):
        if getattr(self, "roadmap", None) is not None:
            self.mapinfo.set(
                "Vernieuwen van weggegevens is niet gelukt; de bestaande gegevens zijn behouden. "
                + str(error)
            )
            self.status.set("Wegdownload gestopt. Opnieuw proberen gebeurt alleen als je dat zelf kiest.")
            return
        self.mapinfo.set(
            "Weggegevens niet beschikbaar. De GPX blijft geopend; kaart, hoogteprofiel en handmatig bewerken blijven beschikbaar. "
            + str(error)
        )
        self.auto_summary.set("Wegdownload gestopt")
        self.status.set(
            "Wegdownload gestopt. Opnieuw proberen gebeurt alleen als je dat zelf kiest."
        )

    def require_track(self):
        if not self.track:
            messagebox.showinfo("GPX openen", "Open eerst een GPX-bestand.")
            return False
        return True

    def import_map(self):
        if not self.require_track() or self.busy:
            return
        p = filedialog.askopenfilename(
            title="OSM XML importeren",
            initialdir=MAPS,
            filetypes=[("OpenStreetMap XML", "*.osm *.xml")],
        )
        if p:
            self.job(
                lambda: __import__("road_provider").import_region(MAPS,p),
                self.set_map,
                "Lokale kaart lezen…",
            )

    def get_map(self):
        if not self.require_track() or self.busy:
            return
        if not messagebox.askyesno(
            "Kaartgegevens ophalen",
            "Paden en wegen voor het gebied rond deze route ophalen bij OpenStreetMap? Het gebied wordt opgevraagd; het GPX-bestand wordt niet geüpload. De kaart wordt lokaal bewaard.",
        ):
            return
        segments = copy.deepcopy(self.edit_segments)

        def run():
            p = download_map(segments, progress=self.map_progress)
            return p, __import__("road_provider").downloaded_road(MAPS,p,segments)

        self.road_job(
            run,
            self.set_map,
            "Weggegevens ophalen (maximaal 30 s online).",
            on_error=self.map_download_unavailable,
        )

    def refresh_map(self):
        if not self.require_track() or self.busy:
            return
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        segments = copy.deepcopy(self.edit_segments)

        def run():
            p = download_map(
                segments,
                refresh=True,
                progress=getattr(self, "map_progress", None),
            )
            return p, __import__("road_provider").downloaded_road(MAPS,p,segments)

        def done(result):
            self.set_map(result)
            self.mapinfo.set(self.mapinfo.get() + " Opnieuw opgehaald bij OSM.")
            self.status.set(
                "Actuele uitlijngegevens opgehaald. De uitlijncontrole wordt opnieuw uitgevoerd."
                if self.auto_mode.get() and self.snap.get()
                else "Actuele uitlijngegevens opgehaald. Kies Opnieuw controleren om de route uit te lijnen."
            )

        self.road_job(
            run,
            done,
            "Actuele OSM-wegen en toegangstags ophalen; opgeslagen uitlijngegevens worden overgeslagen…",
            on_error=self.map_download_unavailable,
        )

    def set_map(self, result):
        self.clear_access_reviews()
        self.map_path, self.roadmap = result
        self.roadmap.cycling_style = self.routing_style()
        self.map_revision = getattr(self, "map_revision", 0) + 1
        self.auto_checked_key = None
        self.endpoint_edit_key = None
        self.endpoint_fully_checked = False
        from road_provider import road_information
        self.mapinfo.set(road_information(self.roadmap))
        self.invalidate()
        self.draw()
        self.status.set("Kaart opgeslagen. Uitlijnen kan nu offline.")
        self.schedule_auto()

    def offer_modeled_times(self):
        if not messagebox.askyesno(
            "Nieuw tijdprofiel gebruiken",
            "Deze GPX heeft ontbrekende of niet-oplopende tijdstempels. Daardoor zijn opgenomen pauzes niet betrouwbaar te bepalen.\n\nWil je een nieuw geschat tijdprofiel berekenen? De ingestelde activiteit, snelheid en gewenste duur worden daarvoor gebruikt. Je oorspronkelijke GPX blijft bewaard.",
        ):
            return False
        self.timing.set("model")
        self.found = []
        self.pausebox.delete(*self.pausebox.get_children())
        self.invalidate()
        self.status.set(
            "Nieuw tijdprofiel gekozen. De tijden worden geschat op basis van tempo en helling."
        )
        return True

    def find_pauses(self):
        if not self.require_track() or self.busy:
            return False
        if not self.track.stats(self.edit_segments)["valid_time"]:
            if self.offer_modeled_times():
                self.calculate()
            return False
        try:
            minimum = float(self.minimum.get().replace(",", ".")) * 60
            radius = float(self.radius.get().replace(",", "."))
            if not 30 <= minimum <= 86400 or not 3 <= radius <= 50:
                raise ValueError(
                    "Gebruik minimaal 0,5 minuut en een stilstandsgebied van 3–50 meter."
                )
            self.found = pauses(
                self.edit_segments,
                minimum,
                radius,
                1.0 if self.routing_mode() == "walk" else 2.0,
            )
            self.pausebox.delete(*self.pausebox.get_children())
            for i, p in enumerate(self.found):
                self.render_pause(i)
            self.invalidate()
            self.status.set(
                f"{len(self.found)} mogelijke pauzes. Meetgaten moet je zelf beoordelen."
            )
            return True
        except Exception as exc:
            messagebox.showerror("Pauzes niet bepaald", str(exc))
            return False

    def render_pause(self, i):
        p = self.found[i]
        values = (
            "✓" if p.selected else "—",
            self.edit_segments[p.segment][p.start].time.strftime("%H:%M"),
            duration(p.seconds),
            "Meetgat / segmentgrens" if p.uncertain else "Stilstand",
        )
        if self.pausebox.exists(str(i)):
            self.pausebox.item(str(i), values=values)
        else:
            self.pausebox.insert("", "end", iid=str(i), values=values)

    def toggle_pause(self, event=None):
        sel = self.pausebox.selection()
        if sel:
            i = int(sel[0])
            p = self.found[i]
            if p.start == p.end:
                messagebox.showinfo(
                    "Losse routedelen",
                    "Tijd tussen losse routedelen wordt bij export automatisch buiten de bewegingstijd gehouden. De routedelen worden niet verbonden.",
                )
                return
            p.selected = not p.selected
            self.render_pause(i)
            self.invalidate()
            self.draw()

    def pause_selected(self, event=None):
        sel = self.pausebox.selection()
        if sel and self.found:
            p = self.found[int(sel[0])]
            self.draw()
            self.canvas.focus_point(self.edit_segments[p.segment][p.start], 17)

    def calculate(self, alignment_ready=False):
        if not self.require_track():
            return
        # In the direct-action editor, timing never starts a second routing pass.
        # Geometry is changed only by explicit alignment/edit actions.
        timing_only = getattr(self, "simple_workflow", False) and not alignment_ready
        if self.snap.get() and not self.roadmap and not timing_only:
            return messagebox.showinfo(
                "Uitlijngegevens nodig",
                "De OSM-kaart is klaar om te bewerken. Voor automatisch volgen van wegen heb je daarnaast het lokale wegennet nodig: kies “Uitlijngegevens ophalen”. Of zet automatisch uitlijnen uit en corrigeer de blauwe lijn zelf.",
            )
        local_endpoints = getattr(self, "endpoint_edit_key", None) == self.routing_key()
        if timing_only and self.auto_issues:
            self.navigate_problem(0)
            self.status.set("Los eerst de gemarkeerde stukken op of kies Dit stuk handmatig behouden.")
            return
        if self.auto_mode.get() and self.snap.get() and not local_endpoints and not alignment_ready and not timing_only:
            if self.auto_checked_key != self.routing_key():
                self.calculate_after_auto = True
                self.start_auto_alignment()
                return
            if self.auto_issues:
                self.navigate_problem(0)
                self.status.set(
                    "Los eerst de gemarkeerde stukken op of kies Dit stuk handmatig behouden."
                )
                return
        if local_endpoints and self.snap.get() and self.auto_issues:
            self.navigate_problem(0)
            return
        if self.timing.get() == "pause":
            if not self.track.stats(self.edit_segments)["valid_time"]:
                if not self.offer_modeled_times():
                    return
            elif not self.found and not self.find_pauses():
                return
        try:
            profile = self.profile.get()
            flat = float(self.flat.get().replace(",", "."))
            snapradius = float(self.snapradius.get().replace(",", "."))
            if not math.isfinite(snapradius) or not 5 <= snapradius <= 150:
                raise ValueError("Uitlijnverschuiving moet tussen 5 en 150 meter liggen.")
            start = datetime.strptime(self.start.get(), "%Y-%m-%d %H:%M").replace(
                tzinfo=timezone.utc
            )
            target = None
            if self.target.get().strip():
                parts = self.target.get().strip().split(":")
                if len(parts) != 2 or not 0 <= int(parts[1]) < 60:
                    raise ValueError("Gebruik uu:mm voor de gewenste duur.")
                target = int(parts[0]) * 3600 + int(parts[1]) * 60
                if target <= 0:
                    raise ValueError("Duur moet groter dan nul zijn.")
        except ValueError as exc:
            return messagebox.showerror("Instelling controleren", str(exc))
        original = copy.deepcopy(self.edit_segments)
        controls = copy.deepcopy(self.anchor_indices)
        found = copy.deepcopy(self.found)
        timing = self.timing.get()
        snap = self.snap.get()
        roadmap = self.roadmap
        routing_mode = self.routing_mode()
        automatic = (self.auto_mode.get() or local_endpoints) and snap
        auto_notes = list(self.auto_notes)
        fully_checked = not local_endpoints or self.endpoint_fully_checked
        if timing_only:
            fully_checked = self.auto_checked_key == self.routing_key() or (
                local_endpoints and self.endpoint_fully_checked)
            automatic = snap and fully_checked
        settings_key = self.settings_key()
        private = self.private_roads.get()
        kept = manual_intervals(original, controls, self.manual_sections)

        def run():
            segs = original
            notes = list(auto_notes) if automatic or timing_only else []
            removed = 0
            mapped = controls
            if timing == "pause":
                segs, removed = remove_pauses(segs, found)
            if alignment_ready:
                # Pause indices belong to the source: retime that source first, then align.
                segs, notes, mapped, issues = automatic_alignment(
                    roadmap, segs, controls, routing_mode, snapradius, kept, private)
                if issues:
                    raise ValueError("Het voorstel bevat nog uitlijnproblemen. Controleer de route opnieuw.")
            if snap and not automatic and not timing_only:
                segs, notes, mapped = roadmap.snap(
                    segs,
                    routing_mode,
                    snapradius,
                    control_indices=controls,
                    with_controls=True,
                    keep_intervals=kept,
                    allow_private=private,
                )
            if timing == "model":
                segs = modeled_times(segs, profile, flat, start, target)
                notes.append(
                    "Dit is een geschat snelheidsprofiel op basis van helling en tempo. Ondergrond, wind, drukte en verkeerslichten worden niet gemodelleerd."
                )
            notes.append(
                f"{duration(removed)} pauzetijd verwijderd."
                if timing == "pause"
                else "Nieuwe tijdstempels berekend; bestaande tijden vervangen."
            )
            if timing_only and not fully_checked:
                notes.append("Het tijdschema volgt de bewerkte lijn; de hele route is niet opnieuw op wegen gecontroleerd.")
            elif not snap:
                notes.append("Deze versie is NIET uitgelijnd op wegen/paden.")
            stats = self.track.stats(segs)
            if not stats["valid_time"]:
                raise ValueError("Resultaat heeft onbruikbare tijdstempels; export is geblokkeerd.")
            # Zero duration with real movement is invalid; duplicates at rest may share a time.
            speeds = []
            for s in segs:
                for a, b in zip(s, s[1:]):
                    dt = (b.time - a.time).total_seconds()
                    d = distance(a, b)
                    if dt <= 0 and d > 1:
                        raise ValueError(
                            "Verplaatsing zonder verstreken tijd. Bereken een nieuw tijdprofiel of pas de pauzeselectie aan."
                        )
                    if dt > 0:
                        speeds.append(d / dt * 3.6)
            maximum = max(speeds, default=0)
            if maximum > (12 if routing_mode == "walk" else 180 if routing_mode in ('motorcar','motorcycle') else 75):
                notes.append(
                    f"Hoge berekende pieksnelheid: {maximum:.1f} km/u. Controleer meetfouten en tijdinstellingen."
                )
            return (
                segs,
                notes,
                dict(
                    estimated=timing == "model",
                    snapped=snap and fully_checked,
                    preserved_existing_route=timing_only or local_endpoints,
                    endpoint_connections_aligned=local_endpoints,
                    automatic_alignment=automatic,
                    allow_private=private,
                    manual_sections=len(kept),
                    snap_radius_m=snapradius,
                    profile=profile,
                    flat_speed=flat,
                    removed_seconds=removed,
                    target_seconds=target,
                    max_speed_kmh=maximum,
                    pauses=[p.__dict__ for p in found],
                ),
                settings_key,
                mapped,
            )

        self.job(run, self.calculated, "Voorstel lokaal berekenen…")

    def calculated(self, result):
        if result[3] != self.settings_key():
            self.status.set(
                "Instellingen zijn tijdens berekenen gewijzigd. Bereken het voorbeeld opnieuw."
            )
            return
        previously_dirty = self.dirty
        self.candidate, self.warnings, self.result_info = result[:3]
        self.approved.set(False)
        self.dirty = True
        self.last_export = None
        self.candidate_anchors = result[4]
        self.messages.delete("1.0", "end")
        self.messages.insert("end", "\n".join("• " + s for s in self.warnings))
        self.update_stats()
        self.draw()
        self.status.set("Voorstel klaar. Vergelijk de lijnen, tijden en meldingen vóór opslaan.")
        def cancelled():
            self.invalidate()
            self.dirty = previously_dirty

        self.review_route_proposal(self.candidate, self.adopt_candidate,
                                   key=self.settings_key(), key_fn=self.settings_key,
                                   notes=self.warnings, on_cancel=cancelled)


    def update_stats(self):
        if not self.track:
            return
        a = self.statistics_analysis("Origineel", self.track.segments).stats
        working = self.statistics_analysis("Bewerkte route", self.edit_segments).stats
        text = f"Origineel  {a['km']:.2f} km  ·  {duration(a['seconds'])}  ·  {a['segments']} routedelen"
        if self.history:
            b = working
            text += f"\nBewerkte lijn  {b['km']:.2f} km  ·  {duration(b['seconds'])}"
        if self.candidate:
            b = self.statistics_analysis("Voorstel", self.candidate).stats
            speed = b["km"] / (b["seconds"] / 3600) if b["seconds"] else 0
            text += f"\nVoorstel  {b['km']:.2f} km  ·  {duration(b['seconds'])}  ·  gemiddeld {speed:.1f} km/u"
            if self.result_info["estimated"]:
                text += "  ·  GESCHAT"
        self.summary.set(text)
        self.timehint.set(
            "Geen volledige, oplopende tijden: pauzes zijn niet vast te stellen. Gebruik Nieuw tijdprofiel berekenen."
            if working["seconds"] is None
            else ""
        )
        if hasattr(self, "stats_tab") and self.tabs.select() == str(self.stats_tab):
            self.refresh_statistics()

    def save(self):
        if self.busy:
            return messagebox.showinfo(
                "Even wachten", "Wacht tot de huidige berekening klaar is voordat je opslaat."
            )
        plain = self.candidate is None
        if not self.track:
            return
        if (
            not plain
            and self.auto_mode.get()
            and self.snap.get()
            and (
                self.auto_issues
                or (
                    self.auto_checked_key != self.routing_key()
                    and getattr(self, "endpoint_edit_key", None) != self.routing_key()
                )
            )
        ):
            self.status.set(
                "Rond eerst de automatische controle af. Je kunt de bewerking wel als concept bewaren."
            )
            return
        if not plain and not self.approved.get():
            return messagebox.showinfo(
                "Eerst beoordelen",
                "Controleer de lijnen, tijden en meldingen en vink de controle aan.",
            )
        segments = self.edit_segments if plain else self.candidate
        info = (
            dict(
                estimated=False,
                snapped=False,
                draft=True,
                automatic_alignment=self.auto_mode.get(),
                allow_private=self.private_roads.get(),
            )
            if plain
            else self.result_info
        )
        info = dict(info)
        try:
            report_speed = float(self.flat.get().replace(",", "."))
            if not math.isfinite(report_speed):
                report_speed = None
        except ValueError:
            report_speed = None
        info.update(editor_mode=self.mapmode.get(),activity=self.transport.get(),
                    transport=self.transport.get(), route_preference=self.route_preference.get(),
                    timing_mode=self.timing.get(), timing_profile=self.profile.get(),
                    profile=self.profile.get(), flat_speed=report_speed,
                    start_time_utc=self.start.get(), target_duration=self.target.get())
        info["estimated"] = info.get("estimated", False) or getattr(self, "applied_time_estimates", False) or any(
            str(record.get("time_status", "")).startswith(("estimated", "interpolated"))
            for record in self.joined_gaps
        )
        folder = DATA / (str(self.row["id"]) if self.row else "losse-bestanden") / "Bewerkt"
        folder.mkdir(parents=True, exist_ok=True)
        name = (
            (str(self.row["id"]) if self.row else "route")
            + "-"
            + datetime.now().strftime("%Y%m%d-%H%M%S")
            + ("-concept.gpx" if plain else "-gecontroleerd.gpx")
        )
        p = filedialog.asksaveasfilename(
            title="Aparte GPX opslaan",
            initialdir=folder,
            initialfile=name,
            defaultextension=".gpx",
            filetypes=[("GPX", "*.gpx")],
        )
        if not p:
            return
        path = Path(p)
        try:
            if (
                path.exists()
                or path.with_suffix(".controle.json").exists()
                or path.with_name(path.stem + "-met-fotos.zip").exists()
            ):
                raise ValueError(
                    "Kies een nieuwe bestandsnaam. Bestaande bestanden worden nooit overschreven."
                )
            if self.source.read_bytes() != self.track.raw:
                raise ValueError(
                    "Het bewaarde origineel is tussentijds gewijzigd. Open het bestand opnieuw."
                )
            for w in self.waypoints:
                w.validate()
            photo_links = portable_photo_links(self.waypoints, path, self.approved_photos)
            pristine = (
                plain
                and len(segments) == len(self.track.segments)
                and all(
                    len(a) == len(b)
                    and all(
                        (p.lat, p.lon, p.ele, p.time) == (q.lat, q.lon, q.ele, q.time)
                        for p, q in zip(a, b)
                    )
                    for a, b in zip(segments, self.track.segments)
                )
            )
            raw = self.track.export(
                segments,
                info["estimated"],
                waypoints=self.waypoints,
                photo_links=photo_links,
                modification_note=(
                    ("Concept opgeslagen; geen nieuwe lijn- of tijdcontrole. " if plain else "")
                    + "Route aangepast; nieuwe routepunten, hoogtes en tijden zijn geschat. Zie controlerapport."
                    if self.joined_gaps
                    else "Concept opgeslagen; geen nieuwe lijn- of tijdcontrole."
                    if plain
                    else None
                ),
                preserve_points=pristine,
                segment_groups=self.segment_groups,
            )
            verified = Track(raw)
            if not plain and not verified.stats()["valid_time"]:
                raise ValueError("Exportcontrole mislukt.")
            report = dict(
                version=VERSION,
                manual_edits=self.edit_revision,
                waypoints=len(self.waypoints),
                photos=list(photo_links.values()),
                main_points=self.candidate_anchors if not plain else self.anchor_indices,
                manual_sections=list(self.manual_sections),
                reconstructed_gaps=copy.deepcopy(self.joined_gaps),
                source_segment_groups=copy.deepcopy(self.segment_groups),
                pending_alignment_issues=[p.__dict__ for p in self.auto_issues],
                accepted_access_issues=copy.deepcopy(self.access_reviews),
                route_id=self.row["id"] if self.row else None,
                original=str(self.source),
                original_sha256=self.track.hash,
                original_stats=self.track.stats(),
                result_stats=verified.stats(),
                result_sha256=verified.hash,
                settings=info,
                warnings=list(dict.fromkeys(self.warnings + ([ACCESS_REVIEW_WARNING] if self.access_reviews else []))),
                approved_at=datetime.now(timezone.utc).isoformat() if not plain else None,
                review_scope="Bestands- en kaartcontrole door gebruiker; geen bewijs van actuele toegankelijkheid of een nieuwe veldcontrole."
                if not plain
                else "Concept opgeslagen; geen nieuwe lijn- of tijdcontrole.",
                published=False,
            )
            write_new(path, raw)
            write_new(
                path.with_suffix(".controle.json"),
                json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            if photo_links:
                with zipfile.ZipFile(
                    path.with_name(path.stem + "-met-fotos.zip"), "x", zipfile.ZIP_DEFLATED
                ) as bundle:
                    bundle.write(path, path.name)
                    for link in set(photo_links.values()):
                        relative = unquote(link)
                        bundle.write(path.parent / relative, relative)
            self.last_export = path
            self.dirty = False
            self.status.set("GPX en rapport opgeslagen. Websiteversie is nog niet vervangen.")
            messagebox.showinfo(
                "Opgeslagen",
                f"{path.name}\n\nBewegingstijd: {duration(verified.stats()['seconds'])}\n{len(self.waypoints)} waypoints, {len(photo_links)} foto’s.\nBewaar de GPX samen met de bijbehorende fotomap.\nOrigineel en controlerapport bewaard.",
            )
        except Exception as exc:
            messagebox.showerror("Niet opgeslagen", str(exc))

    def upload_screen(self):
        if not self.row:
            return messagebox.showinfo(
                "Route onbekend",
                "Deze losse GPX is niet gekoppeld aan een websiteroute. Open de juiste route via het overzicht.",
            )
        if not self.last_export:
            return messagebox.showinfo("Eerst opslaan", "Sla het gecontroleerde voorstel eerst op.")
        self.clipboard_clear()
        self.clipboard_append(str(self.last_export))
        self.update()
        webbrowser.open(
            "https://marcodelnoij.nl/wp-admin/edit.php?post_type=md_route&page=md-route-gpx&route="
            + str(self.row["id"])
        )
        messagebox.showinfo(
            "Uploaden",
            f"Het uploadscherm is geopend. Het bestandspad staat op het klembord:\n\n{self.last_export}\n\nPubliceer daar na controle. De werkbank uploadt niets automatisch en vult geen nieuwe zelfcontroledatum in.",
        )

    def status_notice(self, text):
        self.status.set(text)

    def continue_manual_editing(self, mode="anchor"):
        """Expose the adopted line without invalidating its review or road download."""
        self.mapmode.set(mode)
        self.map_mode_changed()

    def map_mode_changed(self):
        if self.mapmode.get() in ("anchor", "edit", "range"):
            if self.auto_timer:
                self.after_cancel(self.auto_timer)
                self.auto_timer = None
            self.calculate_after_auto = False
            self.auto_mode.set(False)
            self.show_all_anchors.set(True)
            self.auto_summary.set("Handmatig bewerken")
        self.canvas.set_mode(self.mapmode.get())
        self.range_anchor = None
        if (
            self.mapmode.get() == "anchor"
            and self.selection
            and self.selection[1] not in self.anchor_indices[self.selection[0]]
        ):
            self.selection = None
            self.draw()
        hints = {
            "view": "Sleep de kaart en zoom met het muiswiel.",
            "anchor": "Sleep een geel hoofdpunt: de twee aangrenzende stukken volgen automatisch wegen en paden. Dubbelklik op de lijn voor een extra hoofdpunt.",
            "edit": "Kies of versleep een los opnamepunt. Dubbelklik op de lijn om een punt toe te voegen.",
            "range": "Klik twee punten op dezelfde blauwe lijn om het tussenliggende stuk te kiezen.",
            "waypoint": "Klik op de kaart om een benoemd waypoint met foto en omschrijving toe te voegen. Sleep een paars waypoint om het te verplaatsen.",
        }
        self.pointinfo.set(hints[self.mapmode.get()])
        self.draw()

    def point_selected(self, segment, index):
        self.selection = (segment, index)
        p = self.edit_segments[segment][index]
        km = (
            sum(cumulative(s)[-1] for s in self.edit_segments[:segment])
            + cumulative(self.edit_segments[segment])[index]
        ) / 1000
        self.pointinfo.set(
            f"{'Hoofdpunt' if self.mapmode.get() == 'anchor' else 'Gekozen plek'} op {km:.2f} km · {p.lat:.6f}, {p.lon:.6f} · versleep de markering om de lijn aan te passen."
        )
        if self.mapmode.get() == "range":
            if self.range_anchor is None or self.range_anchor[0] != segment:
                self.range_anchor = (segment, index)
                self.range_selection = None
                self.pointinfo.set(
                    f"Eerste grens gekozen op {km:.2f} km. Klik nu de tweede grens op dezelfde lijn."
                )
            else:
                start, end = sorted((self.range_anchor[1], index))
                self.range_selection = (segment, start, end)
                self.range_anchor = None
                self.repairbar.pack(fill="x", pady=(0, 4), before=self.canvas)
                self.pointinfo.set(
                    "Het paarse stuk is gekozen. Klik “Gekozen stuk uitlijnen” om alleen dit deel opnieuw over de wegen te laten lopen."
                )
        self.draw()

    def remember(self):
        self.history.append(
            (
                [list(s) for s in self.edit_segments],
                self.selection,
                [list(a) for a in self.anchor_indices],
                set(self.manual_sections),
                copy.deepcopy(getattr(self, "joined_gaps", [])),
                list(getattr(self, "auto_notes", [])),
                copy.deepcopy(getattr(self, "segment_groups", [])),
                copy.deepcopy(getattr(self, "access_reviews", [])),
                getattr(self, "applied_time_estimates", False),
            )
        )
        if len(self.history) > 20:
            self.history.pop(0)

    def geometry_changed(self, message, automatic=True):
        self.clear_access_reviews()
        self.endpoint_edit_key = None
        self.endpoint_fully_checked = False
        self.repairbar.pack_forget()
        self.auto_issues = []
        self.auto_checked_key = None
        self.edit_revision += 1
        self.invalidate()
        self.dirty = True
        self.issue = None
        self.range_selection = None
        self.range_anchor = None
        self.found = []
        self.pausebox.delete(*self.pausebox.get_children())
        self.status.set(message + " Bereken daarna de tijden opnieuw.")
        self.draw()
        self.update_stats()
        self.messages.delete("1.0", "end")
        self.messages.insert(
            "end",
            message
            + " Het origineel is behouden. Bereken het voorstel en de tijden opnieuw om deze bewerking te controleren.",
        )
        if automatic:
            self.schedule_auto()
        elif self.auto_mode.get():
            self.auto_summary.set("Kies Opnieuw controleren")

    def point_moved(self, segment, index, p):
        if self.busy:
            return
        if self.mapmode.get() == "anchor":
            return self.edit_anchor(segment, index, p)
        self.remember()
        self.edit_segments = move_point(self.edit_segments, segment, index, p)
        self.selection = (segment, index)
        self.geometry_changed("Punt verplaatst.")
        self.point_selected(segment, index)

    def point_inserted(self, segment, index, fraction, p):
        if self.busy:
            return
        if self.mapmode.get() == "anchor":
            a, b = self.edit_segments[segment][index : index + 2]
            p = Point(a.lat + fraction * (b.lat - a.lat), a.lon + fraction * (b.lon - a.lon))
        self.remember()
        self.edit_segments = insert_point(self.edit_segments, segment, index, fraction, p)
        self.selection = (segment, index + 1)
        self.anchor_indices[segment] = [
            i + 1 if i > index else i for i in self.anchor_indices[segment]
        ]
        if self.mapmode.get() == "anchor":
            self.anchor_indices[segment] = sorted(set(self.anchor_indices[segment] + [index + 1]))
        self.geometry_changed("Punt toegevoegd.")
        self.point_selected(segment, index + 1)

    def delete_selected(self):
        if self.busy:
            return
        if self.selection is None:
            return messagebox.showinfo(
                "Kies een punt", "Kies “Lijn bewerken” en klik op een punt op de blauwe lijn."
            )
        if self.mapmode.get() == "anchor":
            return self.edit_anchor(*self.selection, remove=True)
        try:
            si, i = self.selection
            new = delete_point(self.edit_segments, si, i)
            self.remember()
            self.edit_segments = new
            self.anchor_indices[si] = sorted(
                set(
                    [j - 1 if j > i else j for j in self.anchor_indices[si] if j != i]
                    + [0, len(new[si]) - 1]
                )
            )
            self.selection = (si, min(i, len(new[si]) - 1))
            self.geometry_changed("Punt verwijderd; de aangrenzende punten zijn verbonden.")
        except ValueError as exc:
            messagebox.showinfo("Punt behouden", str(exc))

    def undo(self):
        if self.busy or not self.history:
            return
        state = self.history.pop()
        if isinstance(state, dict) and state.get("action") == "access_review":
            self.undo_access_review(state)
            return
        self.clear_access_reviews()
        self.edit_segments, self.selection, self.anchor_indices, self.manual_sections = state[:4]
        if len(state) > 4:
            self.joined_gaps = state[4]
            self.auto_notes = state[5]
            self.segment_groups = state[6]
        self.geometry_changed("Laatste lijnbewerking ongedaan gemaakt.", automatic=False)
        self.access_reviews = copy.deepcopy(state[7]) if len(state) > 7 else []
        self.applied_time_estimates = state[8] if len(state) > 8 else False
        if self.selection and self.mapmode.get() != "range":
            self.point_selected(*self.selection)

    def recover_range(self):
        if self.busy:
            return
        if not self.range_selection:
            return messagebox.showinfo(
                "Kies een stuk", "Kies een probleem of klik twee grenspunten met Stuk kiezen."
            )
        if not self.roadmap:
            return messagebox.showinfo("Wegennet nodig", "Kies eerst Uitlijngegevens ophalen.")
        si, a, b = self.range_selection
        if a == b:
            return
        try:
            radius = float(self.snapradius.get().replace(",", "."))
        except ValueError:
            return messagebox.showinfo("Zoekafstand", "Vul een getal tussen 5 en 150 meter in.")
        key = self.routing_key()
        source = list(self.edit_segments[si][a : b + 1])
        road = self.roadmap
        controls = [i - a for i in self.anchor_indices[si] if a <= i <= b]
        mode = self.routing_mode()
        private = self.private_roads.get()
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None

        def done(proposal):
            if key != self.routing_key():
                return self.status.set(
                    "Route of instellingen gewijzigd; zoek het herstelvoorstel opnieuw."
                )
            window = tk.Toplevel(self)
            window.title("Herstelvoorstel controleren")
            window.geometry("1000x660")
            window.transient(self)
            text = (
                f"Blauw: bestaande lijn · Groen: herstelvoorstel\n"
                f"{proposal.old_length / 1000:.2f} → {proposal.new_length / 1000:.2f} km · "
                f"zoekafstand {proposal.radius:g} m · grootste afwijking circa {proposal.deviation:.0f} m\n"
                + (
                    "Tussenliggende hoofdpunten zijn losgelaten. Controleer dat het voorstel de bedoelde paden volgt."
                    if proposal.relaxed_controls
                    else "De bestaande hoofdpunten zijn gebruikt."
                )
                + "\nAlleen dit stuk verandert. De activiteit en toegangskeuze blijven gelden. Hoogtes zijn benaderd; bereken daarna de tijden opnieuw."
            )
            full_preview = [list(row) for row in self.edit_segments]
            full_preview[si] = full_preview[si][:a] + proposal.line + full_preview[si][b+1:]
            try:
                speed = float(self.flat.get().replace(",", "."))
            except ValueError:
                speed = None
            metrics = proposal_summary(self.track.segments, self.edit_segments, full_preview, speed)
            text += "\n" + " · ".join(tr(label) + ": " + tr(value) for label, value in summary_rows(metrics))
            ttk.Label(window, text=text, wraplength=920, padding=12).pack(fill="x")
            preview = RouteMap(
                window, MAPS / "Tegels", lambda *x: None, lambda *x: None, lambda *x: None
            )
            preview.pack(fill="both", expand=True, padx=12)
            preview.set_layers([], [source], [proposal.line])
            preview.fit([source, proposal.line])
            buttons = ttk.Frame(window, padding=12)
            buttons.pack(fill="x")

            def accept():
                if key != self.routing_key():
                    window.destroy()
                    self.status.set(
                        "Route of instellingen gewijzigd; zoek het herstelvoorstel opnieuw."
                    )
                    return
                checked = self.auto_checked_key == key
                issues = list(self.auto_issues)
                notes = list(self.auto_notes)
                self.remember()
                anchors = [list(row) for row in self.anchor_indices]
                anchors[si] = sorted(set(anchors[si] + [a, b]))
                kept = manual_intervals(
                    self.edit_segments, anchors, getattr(self, "manual_sections", set())
                )
                self.manual_sections = {
                    leg_key(sj, self.edit_segments[sj][left], self.edit_segments[sj][right])
                    for sj, left, right in kept
                    if sj != si or right <= a or left >= b
                }
                self.edit_segments, self.anchor_indices = replace_anchor_section(
                    self.edit_segments,
                    anchors,
                    si,
                    a,
                    b,
                    proposal.line,
                    choose_anchors([proposal.line], self.density.get())[0],
                )
                self.geometry_changed("Plaatselijk herstelvoorstel overgenomen.", automatic=False)
                self.auto_issues = remap_issues(
                    issues, [EndpointChange(si, a, b, len(proposal.line))]
                )
                summary = (
                    f"Herstelvoorstel overgenomen: zoekafstand {proposal.radius:g} m, afwijking circa {proposal.deviation:.0f} m"
                    + (
                        "; tussenliggende hoofdpunten losgelaten."
                        if proposal.relaxed_controls
                        else "."
                    )
                )
                self.auto_notes = notes + proposal.notes + [summary]
                if checked:
                    self.auto_checked_key = self.routing_key()
                self.auto_summary.set(
                    f"{len(self.auto_issues)} open problemen"
                    if checked
                    else "Kies Opnieuw controleren"
                )
                self.messages.delete("1.0", "end")
                self.messages.insert("end", "\n".join(proposal.notes + [summary]))
                self.draw()
                window.destroy()
                if checked and self.auto_issues:
                    self.navigate_problem(0)

            ttk.Button(
                buttons, text="Gebruik dit voorstel", command=accept, style="Accent.TButton"
            ).pack(side="right")
            ttk.Button(buttons, text="Annuleren", command=window.destroy).pack(side="right", padx=8)
            ttk.Button(
                buttons, text="Toon hele stuk", command=lambda: preview.fit([source, proposal.line])
            ).pack(side="left")
            window.grab_set()
            self.status.set(
                "Bekijk het herstelvoorstel. De route verandert pas bij Gebruik dit voorstel."
            )

        self.job(
            lambda: find_recovery(road, source, controls, mode, radius, private),
            done,
            "Herstelvoorstel zoeken voor alleen dit stuk…",
        )

    def reroute_range(self):
        if self.busy:
            return
        if not self.range_selection:
            return messagebox.showinfo(
                "Kies een stuk", "Kies “Stuk kiezen” en klik de twee grenzen op de blauwe lijn."
            )
        if not self.roadmap:
            return messagebox.showinfo(
                "Wegennet nodig",
                "Kies eerst “Uitlijngegevens ophalen” voor automatisch volgen van de wegen.",
            )
        si, start, end = self.range_selection
        if start == end:
            return
        source = self.edit_segments[si]
        profile = self.routing_mode()
        private = self.private_roads.get()
        try:
            radius = float(self.snapradius.get().replace(",", "."))
        except ValueError:
            return

        def run():
            try:
                return self.roadmap.snap(
                    [source[start : end + 1]],
                    profile,
                    radius,
                    control_indices=[[0, end - start]],
                    allow_private=private,
                )
            except AlignmentError as exc:
                raise AlignmentError(
                    str(exc),
                    si,
                    start + exc.index,
                    start + exc.end_index if exc.end_index is not None else None,
                ) from exc

        def apply_result(result):
            corrected, notes = result
            self.remember()
            self.edit_segments[si] = source[:start] + corrected[0] + source[end + 1 :]
            self.selection = (si, start)
            self.anchor_indices = choose_anchors(self.edit_segments, self.density.get())
            self.geometry_changed("Gekozen stuk opnieuw over de wegen gelegd.")
            self.messages.delete("1.0", "end")
            self.messages.insert("end", "\n".join(notes))

        key = self.settings_key()

        def done(result):
            corrected, notes = result
            proposed = [list(row) for row in self.edit_segments]
            proposed[si] = source[:start] + corrected[0] + source[end+1:]
            self.review_route_proposal(proposed, lambda: apply_result(result),
                                       key=key, key_fn=self.settings_key, notes=notes)

        self.job(run, done, "Alleen het gekozen stuk over de wegen leggen…")

    def alignment_problem(self, error):
        if not self.track or error.segment >= len(self.edit_segments):
            return
        si = error.segment
        i = min(error.index, len(self.edit_segments[si]) - 1)
        p = self.edit_segments[si][i]
        km = (
            sum(cumulative(s)[-1] for s in self.edit_segments[:si])
            + cumulative(self.edit_segments[si])[i]
        ) / 1000
        indices = self.anchor_indices[si]
        start = max((j for j in indices if j <= i), default=0)
        end = min(
            (j for j in indices if j >= max(i + 1, error.end_index or i + 1)),
            default=len(self.edit_segments[si]) - 1,
        )
        self.range_selection = (si, start, end)
        self.range_anchor = None
        self.repairbar.pack(fill="x", pady=(0, 4), before=self.canvas)
        self.issue = dict(point=p, segment=si, index=i, label=f"Hier controleren · {km:.2f} km")
        self.selection = (
            (si, i) if self.mapmode.get() != "anchor" or i in self.anchor_indices[si] else None
        )
        self.tabs.select(self.edit)
        self.messages.delete("1.0", "end")
        self.messages.insert(
            "end",
            f"Probleemplaats op {km:.2f} km is rood gemarkeerd en ingezoomd.\n\n{error}\n\nJe kunt de lijn hier bewerken of een stuk kiezen voor een plaatselijke correctie. Je origineel blijft behouden.",
        )
        self.status.set(f"Controle nodig op {km:.2f} km. Zie de rode markering op de kaart.")
        self.draw()
        self.canvas.focus_point(p, 17)

    def show_issue(self):
        if self.auto_issues:
            return self.navigate_problem(0)
        if self.issue:
            self.canvas.focus_point(self.issue["point"], 17)
        else:
            self.status.set("Er is nu geen probleemplaats gemarkeerd.")

    def reset_view(self):
        if self.track:
            self.draw()
            self.canvas.fit(self.edit_segments)

    def draw(self):
        if not hasattr(self, "canvas") or not self.track:
            return
        pause = None
        selected = self.pausebox.selection()
        if selected and self.found:
            found = self.found[int(selected[0])]
            pause = self.edit_segments[found.segment][found.start]
        self.canvas.set_layers(
            self.track.segments,
            self.edit_segments,
            self.candidate or getattr(self, "live_alignment", None),
            self.selection,
            self.issue,
            pause,
            self.range_selection,
            controls=(
                []
                if self.mapmode.get() == "view"
                else issue_controls(self.anchor_indices, self.auto_issues)
                if self.auto_mode.get() and not self.show_all_anchors.get()
                else self.anchor_indices
            ),
            problem_ranges=[(p.segment, p.start, p.end) for p in self.auto_issues],
            waypoints=self.waypoints,
            manual_ranges=manual_intervals(
                self.edit_segments, self.anchor_indices, self.manual_sections
            ),
        )
        self.anchor_count.config(
            text=(
                (
                    f"{len(self.auto_issues)} {'probleemstuk' if len(self.auto_issues) == 1 else 'probleemstukken'}"
                    if self.auto_checked_key == self.routing_key()
                    else "Controle nodig"
                )
                if self.auto_mode.get()
                else f"{sum(map(len, self.anchor_indices))} hoofdpunten"
            )
        )
        self.waypoint_button.config(text=f"Waypoints ({len(self.waypoints)})")
        self.chart.delete("all")
        self.draw_chart()

    def redistribute_anchors(self, event=None):
        if not self.track or self.busy:
            return
        self.remember()
        preserved = manual_intervals(self.edit_segments, self.anchor_indices, self.manual_sections)
        self.anchor_indices = choose_anchors(self.edit_segments, self.density.get())
        for si, a, b in preserved:
            self.anchor_indices[si] = sorted(set(self.anchor_indices[si] + [a, b]))
        self.selection = None
        self.edit_revision += 1
        self.invalidate()
        self.draw()
        self.status.set(
            "Hoofdpunten opnieuw verdeeld op basis van routevorm en afstand. De lijn is behouden."
        )
        self.auto_checked_key = None
        self.schedule_auto()

    def edit_anchor(self, segment, index, position=None, remove=False):
        return self.quick_anchor_edit(segment, index, position, remove)

    def adopt_candidate(self):
        if self.busy or not self.candidate:
            return messagebox.showinfo("Voorstel nodig", "Bereken eerst een voorstel.")
        checked = self.result_info.get('automatic_alignment') and self.result_info.get('snapped')
        estimated = self.result_info.get('estimated', False)
        self.remember()
        self.edit_segments = [list(s) for s in self.candidate]
        self.anchor_indices = (
            [list(a) for a in self.candidate_anchors]
            if self.candidate_anchors
            else choose_anchors(self.edit_segments, self.density.get())
        )
        self.selection = None
        self.geometry_changed("Voorstel overgenomen als bewerkbare lijn met hoofdpunten.", automatic=False)
        self.applied_time_estimates = getattr(self, 'applied_time_estimates', False) or estimated
        if checked:
            self.auto_checked_key = self.routing_key()
        mode = self.mapmode.get()
        self.continue_manual_editing(mode if mode in ("anchor", "edit", "range") else "anchor")
        self.status.set("Voorstel overgenomen. Je kunt direct verder met Hoofdpunten of Losse punten.")

    def endpoint_mode(self, target):
        if not self.require_track() or self.busy:
            return
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        self.mapmode.set(target)
        self.canvas.set_mode(target)
        self.selection = None
        label = {
            "start": "nieuwe startpunt",
            "end": "nieuwe eindpunt",
            "both": "nieuwe gezamenlijke start- en eindpunt",
        }[target]
        self.pointinfo.set(
            "Klik op de kaart voor het "
            + label
            + ". Alleen de korte aansluiting verandert; de rest blijft behouden. Kies Kaart om te annuleren."
        )
        self.status.set("Start/eind verplaatsen: klik de gewenste plek op een weg of pad.")
        si = 0 if target != "end" else len(self.edit_segments) - 1
        index = 0 if target != "end" else len(self.edit_segments[si]) - 1
        self.draw()
        self.canvas.focus_point(self.edit_segments[si][index], 16)

    def place_endpoint(self, target, position):
        if self.busy or not self.track:
            return
        if not self.roadmap:
            self.status.set(
                "Haal eerst de uitlijngegevens op en kies daarna opnieuw het nieuwe start/eindpunt."
            )
            return self.get_map()
        try:
            radius = float(self.snapradius.get().replace(",", "."))
            if not math.isfinite(radius) or not 5 <= radius <= 150:
                raise ValueError("Gebruik een uitlijnverschuiving van 5–150 meter.")
        except ValueError as exc:
            return messagebox.showinfo("Zoekafstand controleren", str(exc))
        segments = copy.deepcopy(self.edit_segments)
        controls = copy.deepcopy(self.anchor_indices)
        key = self.settings_key()
        road = self.roadmap
        map_path = self.map_path
        private = self.private_roads.get()
        mode = self.routing_mode()
        old_issues = copy.deepcopy(self.auto_issues)
        old_notes = list(self.auto_notes)
        checked = (
            self.auto_checked_key == self.routing_key()
            or self.endpoint_edit_key == self.routing_key()
            and self.endpoint_fully_checked
        )

        def run():
            roads = road
            path = map_path
            nodes = list(roads.nodes.values())
            if nodes and not (
                min(p.lat for p in nodes) <= position.lat <= max(p.lat for p in nodes)
                and min(p.lon for p in nodes) <= position.lon <= max(p.lon for p in nodes)
            ):
                path = download_map(segments + [[position]])
                roads = RoadMap(path.read_bytes())
            return (
                move_endpoints(roads, segments, controls, target, position, mode, radius, private),
                roads,
                path,
            )

        def apply_result(result):
            if key != self.settings_key():
                return self.status.set(
                    "Route of instellingen gewijzigd; kies het start/eindpunt opnieuw."
                )
            (out, anchors, notes, changes), roads, path = result
            self.remember()
            self.edit_segments = out
            self.anchor_indices = anchors
            self.roadmap = roads
            self.map_path = path
            self.geometry_changed(
                "Start/eind verplaatst; de overige route is behouden.", automatic=False
            )
            self.auto_issues = remap_issues(old_issues, changes)
            self.auto_notes = list(dict.fromkeys(old_notes + notes))
            self.endpoint_edit_key = self.routing_key()
            self.endpoint_fully_checked = checked
            if checked:
                self.auto_checked_key = self.routing_key()
            if not checked:
                self.auto_notes.insert(
                    0,
                    "Alleen de nieuwe start/eindaansluiting is uitgelijnd. De overige bestaande lijn is behouden en niet opnieuw gecontroleerd.",
                )
            self.mapmode.set("anchor")
            self.canvas.set_mode("anchor")
            self.auto_summary.set(
                f"{len(self.auto_issues)} open problemen · overige route behouden"
                if self.auto_issues
                else "Start/eind aangepast · overige route behouden"
            )
            self.pointinfo.set(
                "Start/eind verplaatst. Alle punten buiten de nieuwe aansluiting zijn behouden. Bereken de tijden opnieuw."
            )
            self.messages.delete("1.0", "end")
            self.messages.insert("end", "\n".join(self.auto_notes))
            self.draw()
            self.update_stats()
            part = changes[0]
            self.canvas.fit(
                [self.edit_segments[part.segment][part.left : part.left + part.new_count]]
            )

        def done(result):
            self.review_route_proposal(result[0][0], lambda: apply_result(result),
                                       key=key, key_fn=self.settings_key)

        self.job(run, done, "Alleen de aansluiting op de bestaande route berekenen…")

    def waypoint_mode(self):
        if not self.require_track():
            return
        self.mapmode.set("waypoint")
        self.map_mode_changed()

    def add_waypoint(self, p):
        if not self.track or self.busy:
            return
        w = Waypoint(p.lat, p.lon, name=f"Waypoint {len(self.waypoints) + 1}")
        WaypointDialog(self, w, self.store_waypoint)

    def edit_waypoint(self, key):
        if self.busy:
            return
        w = next((w for w in self.waypoints if w.key == key), None)
        if w:
            WaypointDialog(self, w, self.store_waypoint, w.key in self.approved_photos)

    def store_waypoint(self, w, photo_approved):
        w.validate()
        self.waypoint_history.append(
            ([replace(a) for a in self.waypoints], set(self.approved_photos))
        )
        index = next((i for i, a in enumerate(self.waypoints) if a.key == w.key), None)
        if index is None:
            self.waypoints.append(w)
        else:
            self.waypoints[index] = w
        if photo_approved:
            self.approved_photos.add(w.key)
        else:
            self.approved_photos.discard(w.key)
        self.waypoints_changed("Waypoint bewaard.")
        self.canvas.focus_point(w, 16)

    def move_waypoint(self, key, p):
        if self.busy:
            return
        w = next((w for w in self.waypoints if w.key == key), None)
        if w:
            self.store_waypoint(replace(w, lat=p.lat, lon=p.lon), w.key in self.approved_photos)

    def waypoints_changed(self, text):
        self.dirty = True
        self.last_export = None
        self.approved.set(False)
        self.draw()
        self.status.set(text + " Sla de GPX op om de wijziging te bewaren.")

    def waypoint_list(self):
        if not self.require_track() or self.busy:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Waypoints")
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=14)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("name", "photo"), show="headings", height=9)
        tree.localized_columns = {1}
        tree.heading("name", text="Naam")
        tree.column("name", width=360)
        tree.heading("photo", text="Foto")
        tree.column("photo", width=80)
        tree.pack(fill="both", expand=True)

        def populate():
            tree.delete(*tree.get_children())
            for w in self.waypoints:
                tree.insert("", "end", iid=w.key, values=(w.name, "Ja" if w.photo else "—"))

        def select():
            return tree.selection()[0] if tree.selection() else None

        def edit():
            key = select()
            if key:
                dialog.destroy()
                self.edit_waypoint(key)

        def show():
            key = select()
            w = next((w for w in self.waypoints if w.key == key), None)
            if w:
                self.canvas.focus_point(w, 17)

        def delete():
            key = select()
            if key:
                self.waypoint_history.append(
                    ([replace(w) for w in self.waypoints], set(self.approved_photos))
                )
                self.waypoints = [w for w in self.waypoints if w.key != key]
                self.approved_photos.discard(key)
                self.waypoints_changed("Waypoint verwijderd.")
                populate()

        def undo_waypoint():
            if self.waypoint_history:
                self.waypoints, self.approved_photos = self.waypoint_history.pop()
                self.waypoints_changed("Waypointbewerking ongedaan gemaakt.")
                populate()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(10, 0))
        for text, command in [
            ("Bewerken", edit),
            ("Toon op kaart", show),
            ("Verwijderen", delete),
            ("Ongedaan", undo_waypoint),
        ]:
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=3)
        tree.bind("<Double-1>", lambda e: edit())
        populate()

    def draw_chart(self):
        if not self.show_profile.get():
            self.chart.pack_forget()
            return
        chart = self.chart
        w = max(300, chart.winfo_width())
        h = max(60, chart.winfo_height())
        segs = self.candidate or self.edit_segments
        data = []
        at = 0
        for s in segs:
            for a, b in zip(s, s[1:]):
                d = distance(a, b)
                at += d
                if a.time and b.time:
                    dt = (b.time - a.time).total_seconds()
                    if dt > 0:
                        data.append((at, d / dt * 3.6))
        if not data:
            chart.pack_forget()
            return
        if not chart.winfo_manager():
            chart.pack(fill="x", pady=(3, 6))
        maximum = max(v for _, v in data) or 1
        chart.create_text(
            12, 12, text=f"Snelheid · piek {maximum:.1f} km/u", anchor="nw", fill="#526357"
        )
        line = [
            v
            for x, y in data
            for v in (35 + x / max(at, 1) * (w - 50), h - 12 - y / maximum * (h - 40))
        ]
        if len(line) >= 4:
            chart.create_line(*line, fill="#176447", width=1.5)

    def begin_watch(self):
        self.known = {
            str(p): (p.stat().st_mtime_ns, p.stat().st_size)
            for p in self.downloads.glob("*.gpx")
            if p.is_file()
        }
        self.stable = {}

    def watch_downloads(self):
        if self.watch.get() and not self.busy and not self.dirty:
            for p in self.downloads.glob("*.gpx"):
                try:
                    value = (p.stat().st_mtime_ns, p.stat().st_size)
                    key = str(p)
                    if value == self.known.get(key):
                        continue
                    if (
                        p.with_suffix(p.suffix + ".part").exists()
                        or p.with_suffix(p.suffix + ".crdownload").exists()
                    ):
                        continue
                    if self.stable.get(key) == value:
                        self.known[key] = value
                        self.stable.pop(key, None)
                        try:
                            self.safe_load(p)
                        except Exception as exc:
                            self.status.set(f"Download niet geopend: {exc}")
                        break
                    self.stable[key] = value
                except OSError:
                    pass
        self.after(2500, self.watch_downloads)

    def close(self):
        if self.busy and not messagebox.askyesno(
            "Bewerking loopt", "Een lokale bewerking loopt nog. Toch afsluiten?"
        ):
            return
        if self.dirty and not messagebox.askyesno(
            "Voorstel niet opgeslagen", "Afsluiten zonder dit voorstel op te slaan?"
        ):
            return
        self.destroy()

    def destroy(self):
        if hasattr(self, 'packages'):self.packages.close()
        self.cancel_road_enrichment(clear=True)
        self.cancel_alignment()
        # Cancel callbacks owned by the closing Tcl interpreter before destroying widgets.
        try:
            for callback in self.tk.splitlist(self.tk.call("after", "info")):
                self.tk.call("after", "cancel", callback)
        except tk.TclError:
            pass
        super().destroy()


def register_protocol():
    import winreg

    exe = str(Path(sys.executable))
    command = (
        f'"{exe}" "%1"'
        if getattr(sys, "frozen", False)
        else f'"{exe.replace("python.exe", "pythonw.exe")}" "{Path(__file__).resolve()}" "%1"'
    )
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\gpxwerkbank") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:RouteRefit")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER, r"Software\Classes\gpxwerkbank\shell\open\command"
    ) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


if __name__ == "__main__":
    if "--register" in sys.argv or "--register-silent" in sys.argv:
        register_protocol()
        if "--register-silent" not in sys.argv:
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "Gekoppeld",
                "De knop “Lokaal openen” kan nu de RouteRefit starten. Je bestaande GPX-bestandskoppeling is behouden.",
            )
            root.destroy()
    else:
        if len(sys.argv) == 4 and sys.argv[1] == "--compare":
            app = App()

            def compare():
                try:
                    app.load_comparison(sys.argv[2], sys.argv[3])
                except (OSError, ValueError) as exc:
                    messagebox.showerror("Vergelijken", str(exc))

            app.after(250, compare)
            app.mainloop()
        else:
            App(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()
