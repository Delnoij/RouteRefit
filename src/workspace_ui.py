# SPDX-License-Identifier: GPL-3.0-only
"""File inspection, route statistics and the desktop navigation for RouteRefit."""

from pathlib import Path
import os
import hashlib
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from gpx_core import duration
from route_formats import read_route, SUPPORTED
from i18n import DisplayVar, tr, LANGUAGES
from route_analysis import (
    analyze_route,
    route_statistics as route_statistics,
    nearest_elevation,
    display_samples,
)
from app_version import DISPLAY_VERSION, PRODUCT_NAME


def inspect_folder(folder, recursive=False):
    """Read GPX files independently. Never change files or follow directory links."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("De gekozen map bestaat niet of is niet bereikbaar.")
    rows, errors, hashes = [], [], {}

    def unreadable(exc):
        errors.append(str(exc))

    for root, dirs, files in os.walk(folder, onerror=unreadable, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(root) / d).is_symlink()) if recursive else []
        for name in sorted(files):
            if name.lower().endswith('.controle.json'):
                continue
            if Path(name).suffix.lower() not in SUPPORTED:
                continue
            if len(rows) >= 10000:
                errors.append("Maximaal 10.000 bestanden per controle; kies een kleinere map.")
                return rows, errors
            path = Path(root) / name
            row = dict(
                path=path,
                name=str(path.relative_to(folder)),
                valid=False,
                km=None,
                points=None,
                note="",
                duplicate=False,
            )
            try:
                imported = read_route(path)
                track = imported.track
                stats = track.stats()
                row.update(
                    valid=True,
                    km=stats["km"],
                    points=stats["points"],
                    note="Tijden bruikbaar"
                    if stats["valid_time"]
                    else "Tijden ontbreken / niet oplopend",
                )
                content_hash = hashlib.sha256(imported.original).hexdigest()
                if content_hash in hashes:
                    first = hashes[content_hash]
                    row.update(duplicate=True, note="Zelfde inhoud als " + first["name"])
                    first["duplicate"] = True
                else:
                    hashes[content_hash] = row
            except Exception as exc:
                row["note"] = "Niet te openen: " + str(exc)
            rows.append(row)
    return rows, errors


def apply_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    bg, ink, muted, blue = "#f3f5f9", "#172b45", "#58677b", "#1765c1"
    root.configure(background=bg)
    style.configure(".", font=("Segoe UI", 10), background=bg, foreground=ink)
    style.configure("TFrame", background=bg)
    style.configure("TLabel", background=bg)
    style.configure(
        "TButton", padding=(12, 7), background="white", bordercolor="#d6deea", relief="flat"
    )
    style.map("TButton", background=[("active", "#e5edf8"), ("pressed", "#d7e5f7")])
    style.configure("Accent.TButton", background=blue, foreground="white", bordercolor=blue)
    style.map(
        "Accent.TButton",
        background=[("active", "#10539f"), ("pressed", "#0d447f")],
        foreground=[("disabled", "#b8c8dc"), ("!disabled", "white")],
    )
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", padding=(18, 9), background="#e8edf5")
    style.configure("Settings.TNotebook.Tab", padding=(8, 6))
    style.map("TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", blue)])
    style.configure(
        "Treeview", rowheight=34, background="white", fieldbackground="white", borderwidth=0
    )
    style.configure(
        "Treeview.Heading", padding=(10, 9), background="#e8edf5", font=("Segoe UI", 10, "bold")
    )
    style.map("Treeview", background=[("selected", "#d9e9ff")], foreground=[("selected", ink)])
    style.configure("TLabelframe", background=bg)
    style.configure("Title.TLabel", font=("Segoe UI", 22, "bold"), foreground=ink)
    style.configure("Muted.TLabel", foreground=muted)
    style.configure("Metric.TLabel", font=("Segoe UI", 19, "bold"), foreground=blue)
    style.configure("Export.TButton", font=("Segoe UI", 9), padding=(5, 3))
    root.option_add("*Menu.font", ("Segoe UI", 10))


class WorkspaceUI:
    def build_workspace(self, data):
        self.files_tab = ttk.Frame(self.tabs, padding=20)
        self.tabs.insert(0, self.files_tab, text=tr("Routes"))
        self.tabs.select(self.files_tab)
        ttk.Label(self.files_tab, text="Je routes", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self.files_tab,
            text="Importeer zelf een route of controleer eerst de bestanden in een map.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(5, 18))
        bar = ttk.Frame(self.files_tab)
        bar.pack(fill="x")
        ttk.Button(
            bar, text="Route importeren…", command=self.pick_file, style="Accent.TButton"
        ).pack(side="left")
        ttk.Button(bar, text="Map kiezen…", command=self.choose_folder).pack(side="left", padx=8)
        ttk.Button(bar, text="Map controleren", command=self.scan_folder).pack(side="left")
        self.folder_recursive = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Ook submappen", variable=self.folder_recursive).pack(
            side="left", padx=12
        )
        self.folder_path = Path(data)
        self.folder_label = ttk.Label(
            self.files_tab, text=str(self.folder_path), style="Muted.TLabel", wraplength=1000
        )
        self.folder_label.pack(anchor="w", pady=(15, 10))
        self.folder_summary = DisplayVar(
            value="Kies een map en klik op Map controleren. Er worden geen bestanden gewijzigd."
        )
        ttk.Label(self.files_tab, textvariable=self.folder_summary).pack(anchor="w", pady=(0, 12))
        frame = ttk.Frame(self.files_tab)
        frame.pack(fill="both", expand=True)
        self.file_tree = ttk.Treeview(
            frame, columns=("file", "km", "points", "state"), show="headings", selectmode="browse"
        )
        self.file_tree.localized_columns = {3}
        for key, title, width in [
            ("file", "Bestand", 380),
            ("km", "Afstand", 100),
            ("points", "Punten", 90),
            ("state", "Controle", 390),
        ]:
            self.file_tree.heading(key, text=title)
            self.file_tree.column(key, width=width, minwidth=70, stretch=key in ("file", "state"))
        self.file_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(frame, command=self.file_tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.file_tree.configure(yscrollcommand=scrollbar.set)
        self.file_tree.tag_configure("invalid", foreground="#a4262c")
        self.file_tree.tag_configure("duplicate", foreground="#815500")
        self.file_tree.bind("<Double-1>", lambda e: self.open_folder_file())
        self.file_tree.bind("<Return>", lambda e: self.open_folder_file())
        self.file_tree.bind("<<TreeviewSelect>>", self.show_file_detail)
        self.file_detail = DisplayVar(
            value="Selecteer een bestand voor details. Dubbelklik om het te openen."
        )
        ttk.Button(
            self.files_tab, text="Geselecteerde route openen", command=self.open_folder_file
        ).pack(anchor="w", side="bottom", before=frame)
        ttk.Label(
            self.files_tab, textvariable=self.file_detail, wraplength=1050, style="Muted.TLabel"
        ).pack(anchor="w", side="bottom", before=frame, pady=12)
        self.folder_rows = []
        self.build_statistics()
        self.tabs.insert("end", self.listtab)
        self.build_menu(data)
        from package_ui import PackageUI
        from werkbank import MAPS
        self.packages = PackageUI(self, MAPS)
        self.tabs.bind("<<NotebookTabChanged>>", self.workspace_tab_changed, add="+")
        self.bind("<Control-o>", lambda e: self.pick_file())
        self.bind("<Control-s>", lambda e: self.save())
        self.bind("<F6>", lambda e: self.show_statistics())
        self.bind("<F11>", lambda e: self.toggle_map_focus())
        self.editor_panes.forget(self.settings_panel)
        # Secondary tools remain available through the menu, leaving one compact map bar.
        for name in ("anchorbar", "autobar", "maplegend"):
            getattr(self, name).pack_forget()

    def build_editor_toolbar(self, parent):
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(0, 8))
        primary = ttk.Frame(actions)
        secondary = ttk.Frame(actions)
        self.automatic_button = ttk.Button(primary, text="Automatisch uitlijnen", command=self.automatic_alignment_action, style="Accent.TButton")
        self.automatic_button.pack(side="left")
        self.manual_button = ttk.Button(primary, text="Handmatig uitlijnen", command=self.manual_alignment)
        self.manual_button.pack(side="left", padx=6)
        ttk.Button(secondary, text="GPX opslaan…", command=self.save, style="Accent.TButton").pack(side="right")
        ttk.Button(secondary, text="Hoogte en statistiek", command=self.show_statistics).pack(side="right", padx=6)

        self.responsive_toolbar(actions, (primary, secondary))

        modes = ttk.Frame(parent)
        modes.pack(fill="x", pady=(0, 8))
        self.enrichment_before=modes
        self.enrichment_bar=self.add_enrichment_controls(parent)
        choices = ttk.Frame(modes)
        extras = ttk.Frame(modes)
        self.mapmode = tk.StringVar(value="anchor")
        for value, label in [("view", "Kaart verschuiven"), ("anchor", "Hoofdpunten"), ("edit", "Losse punten"), ("range", "Stuk kiezen")]:
            ttk.Radiobutton(choices, text=label, variable=self.mapmode, value=value,
                            command=self.map_mode_changed).pack(side="left", padx=(0, 8))
        ttk.Button(extras, text="↶ Ongedaan", command=self.undo).pack(side="left", padx=4)
        more = ttk.Menubutton(extras, text="Meer")
        more.pack(side="left", padx=4)
        menu = tk.Menu(more, tearoff=False)
        for label, command in [("Tijdschema berekenen…", self.calculate),
                               ("Routedelen verbinden…", self.connect_segments),
                               ("Toegangsmeldingen…", self.accept_access_issues),
                               ("Uitlijnen stoppen", self.stop_alignment),
                               ("Punt verwijderen", self.delete_selected),
                               ("Waypoint toevoegen", self.waypoint_mode),
                               ("Waypoints beheren", self.waypoint_list),
                               ("Voorstel overnemen", self.adopt_candidate),
                               ("Meldingen en uitleg", self.show_messages)]:
            menu.add_command(label=label, command=command)
        more.configure(menu=menu)
        ttk.Button(extras, text="Instellingen", command=self.toggle_settings).pack(side="right")

        self.responsive_toolbar(modes, (choices, extras))

        navigation = ttk.Frame(parent)
        navigation.pack(fill="x", pady=(0, 6))
        legend = ttk.Frame(navigation)
        view = ttk.Frame(navigation)
        ttk.Label(legend, text="Oranje: origineel · Blauw: bewerkbaar · Groen: voorstel",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(view, text="Grote kaart", command=self.toggle_map_focus).pack(side="right")
        ttk.Button(view, text="Hele route", command=self.reset_view).pack(side="right", padx=4)
        ttk.Button(view, text="+", width=3, command=lambda: self.canvas.zoom_by(1)).pack(side="right")
        ttk.Button(view, text="−", width=3, command=lambda: self.canvas.zoom_by(-1)).pack(side="right", padx=4)

        self.responsive_toolbar(navigation, (legend, view))

        sharing=ttk.Frame(parent);sharing.pack(fill='x',pady=(0,6))
        ttk.Label(sharing,text='Exporteer naar').pack(side='left',padx=(0,8))
        from navigation_upload import SERVICES,show_navigation_upload
        self.navigation_icons=[];self.navigation_buttons={}
        for service,(asset,url,instruction) in SERVICES.items():
            icon=tk.PhotoImage(master=self,file=str(Path(__file__).parent/'assets'/(asset+'.png')))
            if icon.width()>18:icon=icon.subsample(max(1,(icon.width()+17)//18))
            self.navigation_icons.append(icon)
            button=ttk.Button(sharing,text=service,image=icon,compound='left',style='Export.TButton',
                              command=lambda name=service:show_navigation_upload(self,name))
            button.pack(side='left',padx=(0,4));self.navigation_buttons[service]=button
        from file_export import show_file_export
        self.file_export_button=ttk.Button(sharing,text='Bestand…',style='Export.TButton',
                                          command=lambda:show_file_export(self))
        self.file_export_button.pack(side='left',padx=(0,4))

    def responsive_toolbar(self, frame, groups):
        """Wrap related controls as units when a settings panel or translation needs space."""
        for group in groups:
            group.pack_forget()
        previous = [None]

        def layout(event):
            needed = sum(group.winfo_reqwidth() for group in groups) + 12
            narrow = event.width < needed
            if narrow == previous[0]:
                return
            previous[0] = narrow
            for index, group in enumerate(groups):
                group.grid(row=index if narrow else 0, column=0 if narrow else index,
                           sticky="ew", pady=(0, 4))
            for index in range(len(groups)):
                frame.columnconfigure(index, weight=1 if index == 0 else 0)
        frame.bind("<Configure>", layout)

    def choose_folder(self):
        if self.busy:
            return
        folder = filedialog.askdirectory(
            title="Map met GPX-bestanden kiezen", initialdir=self.folder_path
        )
        if folder:
            self.folder_path = Path(folder)
            self.folder_label.configure(text=str(self.folder_path))
            self.scan_folder()

    def scan_folder(self):
        if self.busy:
            return
        folder, recursive = self.folder_path, self.folder_recursive.get()

        def done(result):
            self.folder_rows, errors = result
            self.file_tree.delete(*self.file_tree.get_children())
            for i, row in enumerate(self.folder_rows):
                tag = "invalid" if not row["valid"] else "duplicate" if row["duplicate"] else ""
                self.file_tree.insert(
                    "",
                    "end",
                    iid=str(i),
                    tags=(tag,),
                    values=(
                        row["name"],
                        f"{row['km']:.2f} km" if row["valid"] else "—",
                        row["points"] if row["valid"] else "—",
                        row["note"],
                    ),
                )
            valid = sum(r["valid"] for r in self.folder_rows)
            duplicates = sum(r["duplicate"] for r in self.folder_rows)
            self.folder_summary.set(
                f"{len(self.folder_rows)} bestanden  ·  {valid} leesbaar  ·  {len(self.folder_rows) - valid} ongeldig  ·  {duplicates} met dubbele inhoud"
            )
            self.file_detail.set(
                "\n".join(errors)
                if errors
                else "Controle afgerond. Selecteer zelf de route die je wilt openen."
            )
            self.status.set("Mapcontrole afgerond; bestanden zijn ongewijzigd.")

        self.tabs.select(self.files_tab)
        self.job(
            lambda: inspect_folder(folder, recursive),
            done,
            "GPX-bestanden in de gekozen map controleren…",
        )

    def show_file_detail(self, event=None):
        selection = self.file_tree.selection()
        if selection:
            row = self.folder_rows[int(selection[0])]
            self.file_detail.set(str(row["path"]) + "\n" + row["note"])

    def open_folder_file(self):
        selection = self.file_tree.selection()
        if not selection:
            return
        row = self.folder_rows[int(selection[0])]
        if not row["valid"]:
            messagebox.showerror("GPX niet te openen", row["note"])
            return
        if self.may_replace():
            self.safe_load(row["path"])

    def safe_load(self, path):
        path = Path(path)
        self.job(
            lambda: read_route(path),
            lambda imported: self.load(path, None, imported),
            "Routebestand importeren",
        )

    def build_menu(self, data):
        menu = tk.Menu(self)

        def group(title):
            child = tk.Menu(menu, tearoff=False)
            menu.add_cascade(label=title, menu=child)
            return child

        file = group("Bestand")
        file.add_command(label="Route importeren…", command=self.pick_file, accelerator="Ctrl+O")
        file.add_command(label="Vergelijken met aangepaste route…", command=self.pick_comparison)
        file.add_command(label="Map kiezen en controleren…", command=self.choose_folder)
        file.add_command(label="GPX-bestanden", command=lambda: self.tabs.select(self.files_tab))
        from service_export import show_export, TEXT
        import i18n
        file.add_command(label=TEXT[i18n.language][0], command=lambda: show_export(self))
        from file_export import show_file_export
        file.add_command(label='Routebestand exporteren…', command=lambda: show_file_export(self))
        file.add_separator()
        file.add_command(
            label="Aparte GPX + controlerapport opslaan…", command=self.save, accelerator="Ctrl+S"
        )
        file.add_command(label="Map met mijn bewerkingen", command=lambda: os.startfile(str(data)))
        file.add_checkbutton(
            label="Nieuwe GPX in Downloads automatisch openen",
            variable=self.watch,
            command=self.begin_watch,
        )
        file.add_separator()
        file.add_command(label="Afsluiten", command=self.close)
        route = group("Route")
        route.add_command(
            label="Website-routeoverzicht", command=lambda: self.tabs.select(self.listtab)
        )
        route.add_command(
            label="Route bewerken op kaart", command=lambda: self.tabs.select(self.edit)
        )
        route.add_command(label="Instellingen voor activiteit en tijd", command=self.show_settings)
        route.add_separator()
        route.add_command(label="Ongedaan maken", command=self.undo)
        route.add_command(label="Geselecteerd punt verwijderen", command=self.delete_selected)
        route.add_command(label="Routedelen verbinden…", command=self.connect_segments)
        route.add_command(
            label="Gekozen stuk met tussenpunten vervangen…", command=self.replace_range_with_via
        )
        route.add_command(label="Hoofdpunten opnieuw verdelen", command=self.redistribute_anchors)
        density = tk.Menu(route, tearoff=False)
        route.add_cascade(label="Hoofdpunten verdelen", menu=density)
        for value in ("Weinig", "Normaal", "Veel"):
            density.add_radiobutton(
                label=value, variable=self.density, value=value, command=self.redistribute_anchors
            )
        for target, label in [
            ("start", "Startpunt verplaatsen"),
            ("end", "Eindpunt verplaatsen"),
            ("both", "Start en eind samen verplaatsen"),
        ]:
            route.add_command(label=label, command=lambda t=target: self.menu_endpoint(t))
        route.add_separator()
        route.add_command(label="Waypoint toevoegen", command=self.waypoint_mode)
        route.add_command(label="Waypoints beheren", command=self.waypoint_list)
        route.add_command(label="Voorstel overnemen", command=self.adopt_candidate)
        kaart = group("Kaart")
        kaart.add_command(label="Hele route tonen", command=self.reset_view)
        kaart.add_command(label="Volgende gewijzigde plek", command=self.show_changed_spot)
        kaart.add_command(
            label="Vorige gewijzigde plek", command=lambda: self.show_changed_spot(-1)
        )
        kaart.add_command(label="Inzoomen", command=lambda: self.canvas.zoom_by(1))
        kaart.add_command(label="Uitzoomen", command=lambda: self.canvas.zoom_by(-1))
        kaart.add_separator()
        kaart.add_command(label="Gebiedspakketten…", command=lambda: self.packages.show())
        kaart.add_command(label="Uitlijngegevens ophalen", command=self.get_map)
        kaart.add_command(label="Uitlijngegevens vernieuwen", command=self.refresh_map)
        kaart.add_command(label="Lokaal OSM-bestand importeren…", command=self.import_map)
        kaart.add_checkbutton(
            label="Alle hoofdpunten tonen", variable=self.show_all_anchors, command=self.draw
        )
        control = group("Controle")
        control.add_checkbutton(
            label="Automatisch uitlijnen", variable=self.auto_mode, command=self.automatic_alignment_action
        )
        control.add_command(label="Toegangsmeldingen accepteren…", command=self.accept_access_issues)
        control.add_command(label="Opnieuw controleren", command=self.automatic_alignment_action)
        control.add_command(label="Vorig probleem", command=lambda: self.navigate_problem(-1))
        control.add_command(label="Volgend probleem", command=lambda: self.navigate_problem(1))
        control.add_command(label="Probleemplaats tonen", command=self.show_issue)
        control.add_separator()
        control.add_command(label="Herstelvoorstel voor gekozen stuk", command=self.recover_range)
        control.add_command(label="Gekozen stuk opnieuw uitlijnen", command=self.reroute_range)
        control.add_command(label="Gekozen stuk handmatig behouden", command=self.keep_range)
        control.add_separator()
        control.add_command(label="Pauzes zoeken", command=self.find_pauses)
        control.add_command(label="Tijdprofiel / voorbeeld berekenen", command=self.calculate)
        control.add_checkbutton(
            label="Lijn, tijden en meldingen gecontroleerd", variable=self.approved
        )
        control.add_command(label="Meldingen en uitleg", command=self.show_messages)
        control.add_command(label="Uploadscherm van deze route", command=self.upload_screen)
        view = group("Weergave")
        view.add_command(
            label="Hoogteprofiel en statistieken", command=self.show_statistics, accelerator="F6"
        )
        view.add_command(label="Grote kaart", command=self.toggle_map_focus, accelerator="F11")
        view.add_command(label="Instellingen tonen / verbergen", command=self.toggle_settings)
        view.add_checkbutton(
            label="Snelheidsprofiel onder de kaart", variable=self.show_profile, command=self.draw
        )
        helpmenu = group("Help")
        helpmenu.add_command(label="Handleiding openen (PDF)", command=self.open_manual)
        languages = group("Taal")
        for code, label in LANGUAGES.items():
            languages.add_command(label=label, command=lambda c=code: self.change_language(c))
        helpmenu.add_command(
            label="Over RouteRefit",
            command=lambda: messagebox.showinfo(
                f"{PRODUCT_NAME} {DISPLAY_VERSION}",
                "RouteRefit is een project van Marco Delnoij.\n\n"
                "Uitgebracht in 2026 onder de GNU General Public License versie 3 (GPL-3.0-only).\n\n"
                "Dit programma maakt gebruik van OpenStreetMap.\n"
                "© OpenStreetMap-bijdragers. Kaartgegevens beschikbaar onder de Open Database License (ODbL) 1.0.\n"
                "https://www.openstreetmap.org/copyright",
            ),
        )
        self.configure(menu=menu)

    def open_manual(self):
        import sys
        import i18n
        from app_version import VERSION
        from werkbank import BASE

        root = BASE if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
        path = (
            root
            / "Handleidingen"
            / f"RouteRefit-{VERSION}-handleiding-{i18n.language.upper()}.pdf"
        )
        if not path.is_file():
            return messagebox.showinfo(
                "Handleiding", "De PDF-handleiding ontbreekt. Pak het volledige Windows-pakket uit."
            )
        try:
            os.startfile(str(path))
        except OSError as exc:
            messagebox.showerror("Handleiding", str(exc))

    def change_language(self, code):
        from werkbank import BASE
        import json, sys, subprocess

        if not self.may_replace():
            return
        path = BASE / "voorkeuren.json"
        try:
            from werkbank import replace_cache

            replace_cache(path, json.dumps({"language": code}).encode("utf-8"))
            if getattr(sys, "frozen", False):
                command = [sys.executable]
            else:
                command = [sys.executable, str(BASE / "werkbank.py")]
            if getattr(self, "comparison_paths", None):
                command.extend(["--compare", *[str(p) for p in self.comparison_paths]])
            elif self.source:
                command.append(str(self.source))
            subprocess.Popen(command, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            messagebox.showerror("Taal niet gewijzigd", str(exc))
            return
        self.destroy()

    def menu_endpoint(self, target):
        self.tabs.select(self.edit)
        self.endpoint_mode(target)

    def show_settings(self):
        self.tabs.select(self.edit)
        if str(self.settings_panel) not in self.editor_panes.panes():
            self.editor_panes.insert(0, self.settings_panel, weight=0)

    def toggle_map_focus(self):
        self.tabs.select(self.edit)
        if str(self.settings_panel) in self.editor_panes.panes():
            self.editor_panes.forget(self.settings_panel)

    def build_statistics(self):
        self.stats_tab = ttk.Frame(self.tabs, padding=20)
        self.tabs.add(self.stats_tab, text=tr("Hoogteprofiel en statistieken"))
        top = ttk.Frame(self.stats_tab)
        top.pack(fill="x")
        ttk.Label(top, text="Hoogteprofiel en statistieken", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Naar de kaart", command=lambda: self.tabs.select(self.edit)).pack(
            side="right"
        )
        bar = ttk.Frame(self.stats_tab)
        bar.pack(fill="x", pady=(14, 12))
        self.statistics_source = tk.StringVar(value="Bewerkte route")
        ttk.Label(bar, text="Gegevens van").pack(side="left")
        selector = ttk.Combobox(
            bar,
            textvariable=self.statistics_source,
            values=["Origineel", "Bewerkte route", "Voorstel"],
            state="readonly",
            width=20,
        )
        selector.pack(side="left", padx=10)
        selector.bind("<<ComboboxSelected>>", lambda e: self.refresh_statistics())
        self.statistics_note = tk.StringVar(
            value=tr("Open een GPX om het hoogteprofiel te bekijken.")
        )
        ttk.Label(bar, textvariable=self.statistics_note, style="Muted.TLabel").pack(
            side="left", padx=10
        )
        self.metric_vars = {}
        metrics = ttk.Frame(self.stats_tab)
        metrics.pack(fill="x", pady=(0, 18))
        cards = []
        metric_columns = [3]
        for i, label in enumerate(
            ["Afstand", "Stijging", "Daling", "Laagste / hoogste", "Duur", "Gem. snelheid"]
        ):
            card = ttk.Frame(metrics, padding=(12, 10))
            card.grid(row=i // 3, column=i % 3, sticky="nsew")
            metrics.columnconfigure(i % 3, weight=1)
            ttk.Label(card, text=label, style="Muted.TLabel").pack(anchor="w")
            var = DisplayVar(value="—")
            self.metric_vars[label] = var
            ttk.Label(card, textvariable=var, style="Metric.TLabel").pack(anchor="w", pady=(6, 0))
            cards.append(card)

        def layout_metrics(event):
            columns = 6 if event.width >= 1180 else 3
            if columns == metric_columns[0]:
                return
            metric_columns[0] = columns
            for i, card in enumerate(cards):
                card.grid(row=i // columns, column=i % columns, sticky="nsew")
            for i in range(6):
                metrics.columnconfigure(i, weight=1 if i < columns else 0)

        metrics.bind("<Configure>", layout_metrics)
        self.elevation_canvas = tk.Canvas(
            self.stats_tab,
            background="white",
            highlightthickness=1,
            highlightbackground="#d6deea",
            height=260,
        )
        self.elevation_canvas.pack(fill="both", expand=True)
        self._statistics_cache = {}
        self._statistics_timer = None
        self.elevation_canvas.bind("<Configure>", self.schedule_statistics)
        self.elevation_canvas.bind("<Motion>", self.profile_hover)
        self.elevation_canvas.bind("<Leave>", lambda e: self.elevation_canvas.delete("hover"))
        self.statistics_details = DisplayVar()
        ttk.Label(
            self.stats_tab,
            text="Hoogtemeters op basis van opeenvolgende GPX-punten, zonder ruisfilter. Ontbrekende hoogtes en segmentgrenzen worden niet overbrugd. Gemiddelde snelheid gebruikt de totale duur inclusief pauzes.",
            style="Muted.TLabel",
            wraplength=900,
        ).pack(anchor="w", side="bottom", before=self.elevation_canvas)
        ttk.Label(
            self.stats_tab,
            textvariable=self.statistics_details,
            style="Muted.TLabel",
            wraplength=900,
        ).pack(anchor="w", side="bottom", before=self.elevation_canvas, pady=(12, 6))

    def workspace_tab_changed(self, event=None):
        if self.tabs.select() == str(self.stats_tab):
            self.refresh_statistics()

    def show_statistics(self):
        self.tabs.select(self.stats_tab)
        self.refresh_statistics()

    def schedule_statistics(self, event=None):
        """Coalesce resize events without repeatedly recomputing route distances."""
        if self._statistics_timer is not None:
            self.after_cancel(self._statistics_timer)
        self._statistics_timer = self.after(75, self.refresh_statistics)

    def statistics_analysis(self, source, segments):
        key = (self.track.hash, 0 if source == "Origineel" else self.edit_revision)
        entry = self._statistics_cache.get(source)
        if entry is None or entry[0] != key or entry[1] is not segments:
            entry = (key, segments, analyze_route(segments))
            self._statistics_cache[source] = entry
        return entry[2]

    def refresh_statistics(self):
        if self._statistics_timer is not None:
            self.after_cancel(self._statistics_timer)
            self._statistics_timer = None
        chart = self.elevation_canvas
        chart.delete("all")
        self.profile_samples = []
        for var in self.metric_vars.values():
            var.set("—")
        if not self.track:
            self.statistics_note.set(tr("Open eerst een GPX-bestand."))
            self.statistics_details.set("")
            chart.create_text(
                30,
                35,
                anchor="nw",
                text="Na het importeren verschijnt hier het hoogteprofiel.",
                fill="#58677b",
                font=("Segoe UI", 12),
            )
            return
        source = self.statistics_source.get()
        segments = (
            self.track.segments
            if source == "Origineel"
            else self.candidate
            if source == "Voorstel"
            else self.edit_segments
        )
        if not segments:
            self.statistics_note.set(tr("Er is nog geen voorstel berekend."))
            self.statistics_details.set(
                "Kies Origineel of Bewerkte route, of bereken eerst een voorstel."
            )
            return
        analysis = self.statistics_analysis(source, segments)
        stats = analysis.stats
        self.statistics_note.set(
            self.name.get()
            + (
                tr(" · tijden zijn schattingen")
                if source == "Voorstel" and self.timing.get() == "model"
                else ""
            )
        )
        values = {
            "Afstand": f"{stats['km']:.2f} km",
            "Stijging": f"{stats['ascent']:.0f} m" if stats["ascent"] is not None else "—",
            "Daling": f"{stats['descent']:.0f} m" if stats["descent"] is not None else "—",
            "Laagste / hoogste": f"{stats['minimum']:.0f} / {stats['maximum']:.0f} m"
            if stats["minimum"] is not None
            else "—",
            "Duur": duration(stats["seconds"]) if stats["seconds"] is not None else "—",
            "Gem. snelheid": f"{stats['average']:.1f} km/u"
            if stats["average"] is not None
            else "—",
        }
        for label, value in values.items():
            self.metric_vars[label].set(value)
        details = f"{stats['points']:,} punten · {stats['segments']} routedelen · {stats['elevation_count']:,} punten met hoogte · {len(self.waypoints) if source != 'Origineel' else len(self.track.waypoints)} waypoints"
        if stats["elevation_count"] < stats["points"]:
            details += " · Hoogtegegevens onvolledig; stijging en daling zijn gedeeltelijk."
        if stats["seconds"] is None:
            details += " · Geen volledige, oplopende tijdstempels."
        if stats["peak"] is not None:
            details += f" · Hoogste puntsnelheid {stats['peak']:.1f} km/u."
        self.statistics_details.set(details)
        if stats["minimum"] is None:
            chart.create_text(
                30,
                35,
                anchor="nw",
                text="Deze GPX bevat geen hoogtegegevens.",
                fill="#58677b",
                font=("Segoe UI", 12),
            )
            return
        width = max(1, chart.winfo_width())
        height = max(1, chart.winfo_height())
        if width < 200 or height < 100:
            return
        left, right, top, bottom = 76, width - 30, 35, height - 52
        lo, hi = stats["minimum"], stats["maximum"]
        padding = max(5, (hi - lo) * 0.1)
        lo -= padding
        hi += padding
        xmax = max(stats["km"], 0.001)

        def xy(km, ele):
            return left + km / xmax * (right - left), bottom - (ele - lo) / (hi - lo) * (
                bottom - top
            )

        for i in range(5):
            ele = lo + (hi - lo) * i / 4
            y = xy(0, ele)[1]
            chart.create_line(left, y, right, y, fill="#e5eaf1")
            chart.create_text(left - 12, y, text=f"{ele:.0f} m", anchor="e", fill="#58677b")
            km = stats["km"] * i / 4
            x = xy(km, lo)[0]
            chart.create_text(x, bottom + 22, text=f"{km:.1f} km", fill="#58677b")
        for original_run in analysis.elevation_runs:
            run = [xy(km, ele) for km, ele in display_samples(original_run, xmax, right - left)]
            if len(run) > 1:
                coordinates = [value for pair in run for value in pair]
                chart.create_polygon(
                    run[0][0], bottom, *coordinates, run[-1][0], bottom, fill="#e4efff", outline=""
                )
                chart.create_line(*coordinates, fill="#1765c1", width=2)
            elif run:
                x, y = run[0]
                chart.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#1765c1", outline="")
        self.profile_samples = analysis.samples
        self._profile_analysis = analysis
        self._profile_projection = (xy, xmax)
        self.profile_bounds = (left, right, top, bottom)

    def profile_hover(self, event):
        chart = self.elevation_canvas
        chart.delete("hover")
        if not getattr(self, "profile_samples", []):
            return
        left, right, top, bottom = self.profile_bounds
        if not left <= event.x <= right:
            return
        xy, xmax = self._profile_projection
        km, ele = nearest_elevation(
            self._profile_analysis, (event.x - left) / (right - left) * xmax
        )
        x, y = xy(km, ele)
        chart.create_line(x, top, x, bottom, fill="#8298b4", dash=(3, 3), tags="hover")
        chart.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#1765c1", outline="white", tags="hover")
        chart.create_text(
            right,
            16,
            text=f"{km:.2f} km  ·  {ele:.0f} m",
            anchor="e",
            fill="#172b45",
            font=("Segoe UI", 11, "bold"),
            tags="hover",
        )
