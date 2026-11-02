# SPDX-License-Identifier: GPL-3.0-only
"""Choose a recording gap, guide a connection with editable via points, review."""

import copy
import math
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import replace
from gpx_core import PROFILES, RoadMap, Waypoint, distance, choose_anchors, replace_anchor_section
from osm_canvas import RouteMap
from i18n import DisplayVar, tr
from proposal_summary import proposal_summary, summary_rows
from segment_join import (
    find_connection,
    merge_connection,
    connection_record,
    average_speed,
    retime_at_previous_average,
)
from routing_repair import manual_intervals, leg_key
from endpoint_edit import EndpointChange, remap_issues


class SegmentJoinUI:
    def connect_segments(self):
        if not self.require_track() or self.busy:
            return
        if len(self.edit_segments) < 2:
            return messagebox.showinfo(
                "Routedelen verbinden", "Deze route heeft geen losse routedelen."
            )
        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        key = self.routing_key()
        chooser = tk.Toplevel(self)
        chooser.title("Routedelen verbinden")
        chooser.geometry("760x440")
        chooser.transient(self)
        ttk.Label(
            chooser,
            text="Kies de onderbreking die je wilt aanvullen. Je kunt het voorstel daarna met tussenpunten aanpassen.",
            wraplength=710,
            padding=12,
        ).pack(fill="x")
        frame = ttk.Frame(chooser)
        frame.pack(fill="both", expand=True, padx=12)
        table = ttk.Treeview(
            frame, columns=("parts", "distance", "time"), show="headings", selectmode="browse"
        )
        for column, label in [
            ("parts", "Routedelen"),
            ("distance", "Afstand tussen einden"),
            ("time", "Opname-onderbreking"),
        ]:
            table.heading(column, text=label)
            table.column(column, width=210, anchor="center")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        table.pack(fill="both", expand=True)
        gaps = []
        for i, (left, right) in enumerate(zip(self.edit_segments, self.edit_segments[1:])):
            a, b = left[-1], right[0]
            gap = distance(a, b)
            gaps.append(gap)
            seconds = (b.time - a.time).total_seconds() if a.time and b.time else None
            timing = f"{seconds / 60:.1f} min" if seconds is not None and seconds >= 0 else "—"
            table.insert(
                "", "end", iid=str(i), values=(f"{i + 1} → {i + 2}", f"{gap:.0f} m", timing)
            )
        selected = (
            self.selection[0]
            if self.selection and self.selection[0] < len(gaps)
            else max(range(len(gaps)), key=gaps.__getitem__)
        )
        table.selection_set(str(selected))
        table.see(str(selected))

        def choose():
            if self.busy or not table.selection():
                return
            if key != self.routing_key():
                chooser.destroy()
                return self.status.set(
                    "Route of instellingen gewijzigd; zoek het herstelvoorstel opnieuw."
                )
            index = int(table.selection()[0])
            chooser.destroy()
            self.connection_editor(index)

        buttons = ttk.Frame(chooser, padding=12)
        buttons.pack(fill="x")
        ttk.Button(
            buttons, text="Verbinding aanpassen…", command=choose, style="Accent.TButton"
        ).pack(side="right")
        ttk.Button(buttons, text="Annuleren", command=chooser.destroy).pack(side="right", padx=8)
        table.bind("<Double-1>", lambda event: choose())
        chooser.grab_set()

    def connection_editor(self, index, section=None):
        from werkbank import MAPS, download_map

        if self.auto_timer:
            self.after_cancel(self.auto_timer)
            self.auto_timer = None
        key = self.routing_key()
        segments = [list(s) for s in self.edit_segments]
        if section is None:
            left, right = segments[index : index + 2]
        else:
            first, last = section
            if not 0 <= first < last < len(segments[index]):
                return
            left, right = segments[index][: first + 1], segments[index][last:]
        old_section = segments[index][section[0] : section[1] + 1] if section else []
        a, b = left[-1], right[0]
        try:
            radius = float(self.snapradius.get().replace(",", "."))
            if not math.isfinite(radius) or not 5 <= radius <= 150:
                raise ValueError()
        except ValueError:
            return messagebox.showinfo("Zoekafstand", "Gebruik een zoekafstand van 5–150 meter.")
        mode = self.routing_mode()
        private = self.private_roads.get()
        style = self.routing_style()
        window = tk.Toplevel(self)
        window.title("Gekozen stuk vervangen" if section else "Verbinding aanpassen")
        width = min(1000, window.winfo_screenwidth() - 80)
        height = min(660, window.winfo_screenheight() - 80)
        window.geometry(f"{width}x{height}")
        window.minsize(min(850, width), min(550, height))
        window.transient(self)
        ttk.Label(
            window,
            text="Klik tussenpunten in de volgorde waarin je hebt gereisd. Sleep een markering om die te verplaatsen. Bereken daarna de verbinding opnieuw.",
            wraplength=1040,
            padding=12,
        ).pack(fill="x")
        note = DisplayVar(
            window,
            value="Blauw: bestaande routedelen · Groen: verbindingsvoorstel. De route verandert pas na overnemen.",
        )
        ttk.Label(window, textvariable=note, wraplength=1040, padding=(12, 0, 12, 8)).pack(fill="x")
        previous_speed = average_speed(segments)
        preserve_speed = tk.BooleanVar(
            window, value=section is not None and previous_speed is not None
        )
        if section:
            ttk.Checkbutton(
                window,
                text="Gemiddelde snelheid behouden (nieuw tijdschema)",
                variable=preserve_speed,
                command=lambda: changed(),
                state="normal" if previous_speed is not None else "disabled",
            ).pack(anchor="w", padx=12)
            ttk.Label(
                window,
                text="Bij een nieuw tijdschema worden de puntentijden op afstand berekend. De oorspronkelijke opname blijft bewaard; pauzes zijn niet afzonderlijk opgenomen.",
                wraplength=1040,
                padding=(12, 4, 12, 6),
            ).pack(fill="x")
        state = dict(via=[], proposal=None, revision=0, selected=None, road=self.roadmap)

        def live():
            return bool(window.winfo_exists()) and key == self.routing_key()

        def redraw():
            points = [
                Waypoint(a.lat, a.lon, tr("Begin verbinding"), key="start"),
                Waypoint(b.lat, b.lon, tr("Einde verbinding"), key="end"),
            ]
            points += [
                Waypoint(p.lat, p.lon, str(i + 1), key=str(i)) for i, p in enumerate(state["via"])
            ]
            proposal = state["proposal"]
            preview.set_layers(
                [],
                [left[-20:], old_section, right[:20]],
                [proposal.line] if proposal else [],
                waypoints=points,
            )
            listing.delete(0, "end")
            for i, p in enumerate(state["via"]):
                listing.insert("end", f"{i + 1} · {p.lat:.5f}, {p.lon:.5f}")
            if state["selected"] is not None and state["selected"] < len(state["via"]):
                listing.selection_set(state["selected"])

        def changed():
            state["revision"] += 1
            state["proposal"] = None
            accept_button.configure(state="disabled")
            note.set(
                "Tussenpunten gewijzigd. Klik op Verbinding berekenen om het nieuwe voorstel te bekijken."
            )
            redraw()

        def add(point):
            if self.busy or not live():
                return
            if len(state["via"]) >= 50:
                return messagebox.showinfo(
                    "Tussenpunten", "Gebruik maximaal 50 tussenpunten.", parent=window
                )
            state["via"].append(point)
            state["selected"] = len(state["via"]) - 1
            changed()

        def select_marker(marker):
            if marker.isdigit():
                state["selected"] = int(marker)
                redraw()

        def move(marker, point):
            if not self.busy and live() and marker.isdigit():
                state["via"][int(marker)] = point
                state["selected"] = int(marker)
                changed()

        controls = ttk.Frame(window, padding=(12, 0, 12, 8))
        controls.pack(fill="x")
        placing = tk.BooleanVar(window, value=True)
        ttk.Checkbutton(
            controls,
            text="Tussenpunten plaatsen",
            variable=placing,
            command=lambda: preview.set_mode("waypoint" if placing.get() else "view"),
        ).pack(side="left")
        ttk.Button(controls, text="−", command=lambda: preview.zoom_by(-1)).pack(side="right")
        ttk.Button(controls, text="+", command=lambda: preview.zoom_by(1)).pack(side="right")
        details_frame = ttk.Frame(window, padding=(12, 0, 12, 8))
        details = tk.Text(details_frame, height=5, wrap="word")
        details.pack(fill="x")
        details.configure(state="disabled")
        show_details = tk.BooleanVar(window, value=False)

        def toggle_details():
            if show_details.get():
                details_frame.pack(fill="x", before=controls)
            else:
                details_frame.pack_forget()

        ttk.Checkbutton(
            controls, text="Details tonen", variable=show_details, command=toggle_details
        ).pack(side="left", padx=12)
        body = ttk.Frame(window)
        body.pack(fill="both", expand=True, padx=12)
        sidebar = ttk.Frame(body, width=230)
        sidebar.pack(side="right", fill="y", padx=(10, 0))
        ttk.Label(sidebar, text="Tussenpunten").pack(anchor="w")
        listing = tk.Listbox(sidebar, width=27, height=12, exportselection=False)
        listing.pack(fill="both", expand=True)

        def selected(event=None):
            if listing.curselection():
                state["selected"] = listing.curselection()[0]

        listing.bind("<<ListboxSelect>>", selected)

        def edit_via(action):
            if self.busy or not live():
                return
            i = state["selected"]
            if i is None or not 0 <= i < len(state["via"]):
                return
            if action == "delete":
                state["via"].pop(i)
                state["selected"] = min(i, len(state["via"]) - 1) if state["via"] else None
            else:
                j = i + action
                if not 0 <= j < len(state["via"]):
                    return
                state["via"][i], state["via"][j] = state["via"][j], state["via"][i]
                state["selected"] = j
            changed()

        for label, action in [("Omhoog", -1), ("Omlaag", 1), ("Tussenpunt verwijderen", "delete")]:
            ttk.Button(sidebar, text=label, command=lambda v=action: edit_via(v)).pack(
                fill="x", pady=3
            )
        preview = RouteMap(
            body,
            MAPS / "Tegels",
            lambda *args: None,
            lambda *args: None,
            lambda *args: None,
            on_waypoint=add,
            on_waypoint_select=select_marker,
            on_waypoint_move=move,
        )
        preview.pack(fill="both", expand=True)
        preview.set_mode("waypoint")
        redraw()
        preview.fit([left[-20:], old_section, [a, b], right[:20]])

        def failed(error):
            if window.winfo_exists():
                note.set(str(error))
                state["proposal"] = None
                accept_button.configure(state="disabled")

        def calculate():
            if self.busy or not live():
                return
            revision = state["revision"]
            via = copy.deepcopy(state["via"])
            state["proposal"] = None
            accept_button.configure(state="disabled")
            note.set("Verbinding berekenen…")

            def work():
                road = state["road"]
                if road is None:
                    caches = sorted(
                        MAPS.glob("*.osm"), key=lambda p: p.stat().st_mtime, reverse=True
                    )
                    if not caches:
                        raise ValueError(
                            "Haal eerst weggegevens voor dit gat op of importeer lokale OSM-weggegevens."
                        )
                    road = RoadMap(caches[0].read_bytes())
                road.cycling_style = style
                return road, find_connection(road, left, right, mode, radius, via, private)

            def done(result):
                if not live() or revision != state["revision"]:
                    return
                state["road"], state["proposal"] = result
                proposal = state["proposal"]
                if section:
                    first, last = section
                    full_preview = [list(s) for s in segments]
                    full_preview[index] = segments[index][:first] + proposal.line + segments[index][last+1:]
                    if preserve_speed.get():
                        full_preview = retime_at_previous_average(segments, full_preview)
                else:
                    full_preview = merge_connection(segments, self.anchor_indices, self.manual_sections, index, proposal)[0]
                try:
                    speed = float(self.flat.get().replace(",", "."))
                except ValueError:
                    speed = None
                metrics = proposal_summary(self.track.segments, segments, full_preview, speed)
                note.set("\n".join(tr(label) + ": " + tr(value) for label, value in summary_rows(metrics))
                         + "\n" + tr(metrics['time_basis']))
                details.configure(state="normal")
                details.delete("1.0", "end")
                details.insert("end", "\n".join(tr(n) for n in proposal.notes))
                details.configure(state="disabled")
                redraw()
                preview.fit([left[-20:], old_section, proposal.line, right[:20]])
                accept_button.configure(state="normal")

            self.job(work, done, "Verbinding berekenen…", on_error=failed)

        def fetch_roads():
            if self.busy or not live():
                return
            revision = state["revision"]
            source = copy.deepcopy([a, *state["via"], b])
            state["proposal"] = None
            accept_button.configure(state="disabled")
            note.set("Weggegevens voor dit gat ophalen…")

            def work():
                path = download_map([source], progress=self.map_progress)
                return RoadMap(path.read_bytes())

            def done(road):
                if not live() or revision != state["revision"]:
                    return
                state["road"] = road
                calculate()

            self.job(work, done, "Weggegevens voor dit gat ophalen…", on_error=failed)

        def accept():
            if self.busy or not live() or state["proposal"] is None:
                return
            proposal = state["proposal"]
            if section is None:
                out, anchors, protected = merge_connection(
                    self.edit_segments, self.anchor_indices, self.manual_sections, index, proposal
                )
            else:
                first, last = section
                anchors = [list(row) for row in self.anchor_indices]
                anchors[index] = sorted(set(anchors[index] + [first, last]))
                protected = {
                    leg_key(si, segments[si][a], segments[si][b])
                    for si, a, b in manual_intervals(segments, anchors, self.manual_sections)
                    if si != index or b <= first or a >= last
                }
                controls = set(choose_anchors([proposal.line])[0])
                controls.update(
                    min(range(len(proposal.line)), key=lambda i: distance(p, proposal.line[i]))
                    for p in proposal.via
                )
                out, anchors = replace_anchor_section(
                    segments, anchors, index, first, last, proposal.line, sorted(controls)
                )
                if preserve_speed.get():
                    out = retime_at_previous_average(segments, out)
            self.remember()
            record = connection_record(index, proposal)
            if section:
                record["kind"] = "replaced_route_section"
                if preserve_speed.get():
                    record["time_status"] = "estimated_distance_schedule_at_previous_average"
                    record["average_speed_kmh"] = previous_speed * 3.6
            self.joined_gaps.append(record)
            if section is None:
                self.segment_groups[index : index + 2] = [
                    self.segment_groups[index] + self.segment_groups[index + 1]
                ]
            self.edit_segments, self.anchor_indices, self.manual_sections = out, anchors, protected
            self.selection = (index, len(left) - 1)
            # Every prior review is invalidated by a topology change. Retain its
            # locations for review rather than silently marking issues resolved.
            issues = list(self.auto_issues)
            offset = len(left) + len(proposal.line) - 2
            self.geometry_changed(
                "Gekozen stuk vervangen; controleer de lijn en het nieuwe tijdschema."
                if section
                else "Routedelen verbonden. Controleer de gereconstrueerde verbinding.",
                automatic=False,
            )
            self.auto_issues = (
                remap_issues(
                    issues, [EndpointChange(index, section[0], section[1], len(proposal.line))]
                )
                if section
                else [
                    replace(p, segment=index, start=p.start + offset, end=p.end + offset)
                    if p.segment == index + 1
                    else replace(p, segment=p.segment - 1)
                    if p.segment > index + 1
                    else p
                    for p in issues
                ]
            )
            applied_notes = list(proposal.notes)
            if section and preserve_speed.get():
                applied_notes = [
                    n for n in applied_notes if not n.startswith("Tijden op de verbinding")
                ]
                applied_notes.append(
                    "Geschat tijdschema opnieuw berekend op afstand; de gemiddelde snelheid is behouden."
                )
            self.auto_notes.extend(applied_notes)
            self.draw()
            self.canvas.fit([proposal.line])
            self.messages.insert("end", "\n\n" + "\n".join(applied_notes))
            window.destroy()

        footer = ttk.Frame(window, padding=12)
        footer.pack(fill="x")
        ttk.Button(footer, text="Verbinding berekenen", command=calculate).pack(side="left")
        ttk.Button(footer, text="Weggegevens voor dit gat ophalen", command=fetch_roads).pack(
            side="left", padx=8
        )
        ttk.Button(footer, text="Annuleren", command=window.destroy).pack(side="right")
        accept_button = ttk.Button(
            footer,
            text="Gebruik dit voorstel" if section else "Verbinding overnemen",
            command=accept,
            style="Accent.TButton",
            state="disabled",
        )
        accept_button.pack(side="right", padx=8)
        ttk.Label(
            window,
            text="Weggegevens ophalen vraagt het kaartgebied op bij OpenStreetMap. Het routebestand blijft lokaal.",
            wraplength=1040,
            padding=(12, 0, 12, 8),
        ).pack(fill="x")
        window.grab_set()
        window.after(250, calculate)
