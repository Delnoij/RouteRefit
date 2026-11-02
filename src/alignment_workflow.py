# SPDX-License-Identifier: GPL-3.0-only
"""Explicit alignment actions with local, on-demand road data and safe previews."""
import copy
import math
import queue
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from gpx_core import Point, cumulative, distance, route_anchor_edit, replace_anchor_section
from segment_join import local_connection_map, retime_at_previous_average, average_speed
from proposal_review_ui import same_route
from local_first_ui import LocalFirstRoads

_download_lock = threading.Lock()


def covers_rectangle(bounds, boxes):
    """Prove complete coverage; four covered corners alone are not sufficient."""
    w, s, e, n = bounds
    xs = sorted({w, e, *(max(w, min(e, v)) for b in boxes for v in (b[0], b[2]))})
    for a, b in zip(xs, xs[1:]):
        x = (a + b) / 2
        intervals = sorted((y, z) for l, y, r, z in boxes if l - 1e-7 <= x <= r + 1e-7)
        top = s
        for bottom, end in intervals:
            if bottom > top + 1e-7:
                break
            top = max(top, end)
        if top < n - 1e-7:
            return False
    return bool(boxes)


def merged_osm(paths):
    root, seen = ET.Element("osm", version="0.6"), set()
    for path in paths:
        raw = Path(path).read_bytes()
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError("Ongeldig kaartbestand.")
        tile = ET.fromstring(raw)
        if tile.tag != "osm" or tile.find("remark") is not None:
            raise ValueError("Onvolledige weggegevens.")
        for child in tile:
            key = child.tag, child.get("id")
            if key[1] is not None and key not in seen:
                seen.add(key); root.append(child)
    return ET.tostring(root, encoding="utf-8")


def cached_section(folder, segments):
    from road_provider import cached_road
    from road_index import road_xml
    road=cached_road(folder,segments,"trekking")
    return road_xml(road) if road is not None else None


def road_for_section(folder, segments, download, style, loaded=None, anchors=None, radius=40, emit=None, cancelled=None):
    from road_provider import cached_road
    from gpx_core import RoadMap
    road=cached_road(folder,segments,style,loaded,anchors,radius,emit,cancelled)
    if road is not None:return road
    path=download(segments)
    road=cached_road(folder,segments,style,None,anchors,radius,emit,cancelled)
    if road is None:  # Custom local providers may return an explicit unbounded map.
        road=RoadMap(path.read_bytes())
        road.cycling_style=style
    return road


def alignment_chunks(segments, anchors, maximum=3000):
    """Work in route order, without connecting real recording gaps."""
    for si, (row, controls) in enumerate(zip(segments, anchors)):
        if len(row) < 2:
            yield si, 0, len(row)-1, [0]
            continue
        lengths = cumulative(row)
        start = controls[0]
        group = [start]
        for end in controls[1:]:
            if len(group) > 1 and lengths[end]-lengths[start] > maximum:
                yield si, start, group[-1], [v-start for v in group]
                start = group[-1]; group = [start]
            group.append(end)
        yield si, start, group[-1], [v-start for v in group]


def estimated_schedule(source, proposed):
    if len(source)==len(proposed) and all(len(a)==len(b) and all(distance(p,q)<.02 for p,q in zip(a,b)) for a,b in zip(source,proposed)):
        return source
    return retime_at_previous_average(source, proposed) if average_speed(source) else proposed


def compact_tiles(tiles):
    """Join adjacent rectangles, at most four existing cells and no extra area."""
    remaining = list(tiles)
    groups = []
    while remaining:
        box = remaining.pop(0)
        count = 1
        for _ in range(3):
            for other in remaining:
                w,s,e,n = box; a,b,c,d = other
                joined = min(w,a), min(s,b), max(e,c), max(n,d)
                area = (e-w)*(n-s)+(c-a)*(d-b)
                j,k,l,m = joined
                if abs((l-j)*(m-k)-area)<1e-12 and l-j<=.06000001 and m-k<=.04000001:
                    box = joined; remaining.remove(other); count+=1
                    break
            else: break
        groups.append(box)
    return tuple(groups)


def action_download(segments, emit=None, cancel=None, budget=None):
    from werkbank import download_map
    from map_plan import plan_route_tiles
    from road_download import DownloadBudget
    budget=budget or DownloadBudget.foreground(emit)
    budget.check(cancel.is_set if cancel else None)
    while not _download_lock.acquire(timeout=.1):
        budget.check(cancel.is_set if cancel else None)
    try:
        if cancel and cancel.is_set(): raise ValueError("Uitlijnen gestopt.")
        return download_map(segments, tiles=compact_tiles(plan_route_tiles(segments)),
            progress=(lambda a,b: emit(f"Wegen laden: {a}/{b} vakken")) if emit else None,
            cancelled=cancel.is_set if cancel else None, budget=budget)
    finally:
        _download_lock.release()


def combine_roads(roads):
    roads = list({id(road):road for road in roads}.values())
    if len(roads)==1: return roads[0]
    merged = copy.copy(roads[0])
    merged.nodes, merged.node_tags, merged.ways = {}, {}, []
    merged._index_way_ids=[];merged._index_relations=[]
    from turn_policy import way_ids
    seen = set()
    merged.restrictions = max(r.restrictions for r in roads)
    for road in roads:
        merged.nodes.update(road.nodes); merged.node_tags.update(road.node_tags)
        merged._index_relations.extend(raw for raw in getattr(road,'_index_relations',()) if raw not in merged._index_relations)
        for wid,(ids, tags) in zip(way_ids(road),road.ways):
            key = wid, tuple(ids), tuple(sorted(tags.items()))
            if key not in seen:
                seen.add(key); merged.ways.append((ids, tags))
                merged._index_way_ids.append(wid)
    return merged


class AlignmentWorkflow(LocalFirstRoads):
    def alignment_key(self):
        return id(self.track), getattr(self,"map_revision",0), self.settings_key()

    def alignment_radius(self):
        try:
            value=float(self.snapradius.get().replace(",", "."))
            if not math.isfinite(value) or not 5<=value<=150: raise ValueError()
            return value
        except ValueError:
            from tkinter import messagebox
            messagebox.showinfo("Zoekafstand", "Gebruik een zoekafstand van 5–150 meter.")
            return None

    def cancel_alignment(self):
        event = getattr(self, "alignment_cancel", None)
        if event: event.set()
        self.alignment_token = None
        self.live_alignment = None
        self.finish_alignment_feedback()

    def finish_alignment_feedback(self):
        if hasattr(self,"alignment_feedback"):
            self.alignment_spinner.stop()
            self.alignment_feedback.pack_forget()

    def update_alignment_feedback(self, phase, started):
        if hasattr(self,"alignment_feedback"):
            self.alignment_phase.set(phase)
            elapsed=max(0,int(time.monotonic()-started))
            self.alignment_elapsed.set(f"Verstreken: {elapsed//60:02d}:{elapsed%60:02d}")

    def stop_alignment(self):
        self.cancel_road_enrichment()
        self.cancel_alignment()
        self.draw()
        self.status.set("Uitlijnen gestopt. De bewerkbare route is behouden.")

    def manual_alignment(self):
        if not self.require_track(): return
        self.cancel_road_enrichment(clear=True)
        self.cancel_alignment()
        self.continue_manual_editing()
        self.status.set("Handmatig uitlijnen: klaar. Benodigde wegen worden vanzelf per bewerking geladen.")

    def alignment_task(self, work, done, message, progress=None):
        self.cancel_alignment()
        event = threading.Event()
        token = object()
        self.alignment_cancel, self.alignment_token = event, token
        key = self.alignment_key()
        results = queue.Queue()
        self.status.set(message)
        started=time.monotonic()
        phase=message
        if hasattr(self,"alignment_feedback"):
            self.alignment_feedback.pack(fill="x",before=self.tabs)
            self.alignment_spinner.start(80)
            self.update_alignment_feedback(phase,started)

        def run():
            from routing_runtime import routing_runtime
            try:
                emit = lambda value: results.put(("progress", value))
                with routing_runtime(event.is_set, emit):
                    value = work(event, emit)
                results.put(("done", value))
            except Exception as exc: results.put(("error", exc))

        def poll():
            nonlocal phase
            if self.alignment_token is not token: return
            self.update_alignment_feedback(phase,started)
            if key != self.alignment_key():
                self.cancel_alignment()
                self.draw()
                self.status.set("Route of instellingen gewijzigd; het oude voorstel is gestopt.")
                return
            if self.busy:
                self.after(100, poll); return
            try:
                while True:
                    kind, value = results.get_nowait()
                    if kind == "progress":
                        if isinstance(value,str):
                            phase=value
                            self.status.set(value)
                            self.update_alignment_feedback(phase,started)
                        elif progress: progress(value)
                    else:
                        self.alignment_token = None
                        self.live_alignment = None
                        self.finish_alignment_feedback()
                        self.draw()
                        if kind == "error":
                            self.status.set("Uitlijnen niet voltooid. Je route is behouden.")
                            from tkinter import messagebox
                            from road_download import RoadServiceUnavailable
                            if isinstance(value,RoadServiceUnavailable):
                                messagebox.showinfo('Weggegevens nog niet beschikbaar', str(value))
                            else:
                                messagebox.showerror("Uitlijnen niet voltooid", str(value))
                        else: done(value)
                        return
            except queue.Empty: pass
            self.after(100, poll)
        threading.Thread(target=run, daemon=True, name="RouteRefit-uitlijnen").start()
        self.after(100, poll)

    def automatic_alignment_action(self, download_missing=True):
        if not self.require_track() or self.busy: return
        if getattr(self,"alignment_token",None) is not None and getattr(self,"alignment_kind",None)=="auto":
            return
        self.alignment_kind="auto"
        from werkbank import MAPS, download_map, automatic_alignment, manual_intervals
        self.auto_mode.set(True)
        self.snap.set(True)
        active=getattr(self,'enrichment_job',None)
        if not (active and active['running'] and self.enrichment_current(active)):
            self.cancel_road_enrichment(clear=True)
        source = copy.deepcopy(self.edit_segments)
        anchors = copy.deepcopy(self.anchor_indices)
        kept = manual_intervals(source, anchors, self.manual_sections)
        mode, style = self.routing_mode(), self.routing_style()
        private = self.private_roads.get()
        radius = self.alignment_radius()
        if radius is None: return
        loaded = self.roadmap
        key = self.alignment_key()

        def work(cancel, emit):
            from resilient_alignment import run_local_alignment
            return run_local_alignment(MAPS,source,anchors,mode,style,radius,kept,private,
                                       loaded,cancel,emit,automatic_alignment)

        def done(local_result):
            result,missing=local_result
            if result is None:
                from local_first_ui import NO_LOCAL,NO_LOCAL_IDLE
                self.status.set(NO_LOCAL if download_missing else NO_LOCAL_IDLE)
                if download_missing:self.start_road_enrichment(source,action_download)
                else:
                    self.enrichment_message.set(NO_LOCAL_IDLE)
                    self.refresh_enrichment_controls()
                return
            out, mapped, issues, notes, road = result
            if road is not None and self.roadmap is not road:
                self.roadmap = road
                self.map_revision = getattr(self, "map_revision", 0)+1
                from road_provider import road_information
                self.mapinfo.set(road_information(road))
            def apply():
                previous_key=self.alignment_key()
                estimated = not same_route(self.edit_segments, out)
                self.remember()
                self.edit_segments, self.anchor_indices = out, mapped
                self.applied_time_estimates = self.applied_time_estimates or estimated
                self.geometry_changed("Automatisch uitlijnen overgenomen.", automatic=False)
                self.auto_issues, self.auto_notes = issues, notes
                self.auto_checked_key = self.routing_key()
                self.continue_manual_editing()
                from resilient_alignment import PARTIAL_NOTICE
                self.status.set(PARTIAL_NOTICE if PARTIAL_NOTICE in notes else
                    "Uitlijnvoorstel overgenomen. Het tijdschema behoudt de beschikbare gemiddelde snelheid.")
                if issues: self.navigate_problem(0)
                self.retain_enrichment_after_accept(previous_key)
            self.review_route_proposal(out, apply, key=self.alignment_key(), key_fn=self.alignment_key, notes=notes,
                                       enrichment=missing,on_cancel=self.cancel_road_enrichment if missing else None)
            self.status.set('Lokaal uitlijnvoorstel gereed. Je route is nog niet gewijzigd.')
            if missing and download_missing:self.start_road_enrichment(source,action_download)
            elif missing:
                self.enrichment_message.set('Voorstel aangevuld met opgeslagen wegen. Er ontbreken nog wegen; probeer later zelf opnieuw.')
                self.refresh_enrichment_controls()
        self.alignment_task(work, done, "Eerst uitlijnen met opgeslagen wegen…")

    def quick_anchor_edit(self, segment, index, position=None, remove=False):
        from werkbank import MAPS, download_map
        if self.busy: return
        self.alignment_kind="manual"
        source = copy.deepcopy(self.edit_segments)
        anchors = copy.deepcopy(self.anchor_indices)
        controls = anchors[segment]
        if index not in controls: return
        ordinal = controls.index(index)
        if remove and ordinal in (0, len(controls)-1):
            self.status.set("Begin en einde blijven behouden. Je kunt ze wel verplaatsen."); return
        left, right = controls[max(0,ordinal-1)], controls[min(len(controls)-1,ordinal+1)]
        request = [source[segment][left]]
        if not remove and position is not None: request.append(position)
        request.append(source[segment][right])
        mode, style = self.routing_mode(), self.routing_style()
        private = self.private_roads.get()
        radius = self.alignment_radius()
        if radius is None: return
        loaded = self.roadmap
        key = self.alignment_key()
        def work(cancel, emit):
            road = road_for_section(MAPS, [request], lambda rows:action_download(rows,emit,cancel), style, loaded, radius=radius, emit=emit, cancelled=cancel.is_set)
            if cancel.is_set(): return None
            from segment_join import local_connection_map
            road = local_connection_map(road, request, radius)
            try:
                result = route_anchor_edit(road, source, anchors, segment, index, mode, radius, position, remove, allow_private=private)
            except ValueError:
                if loaded is None or cancel.is_set(): raise
                # Moving beyond a previously loaded area needs local data, not
                # another manual download action from the user.
                road = road_for_section(MAPS, [request], lambda rows:action_download(rows,emit,cancel), style, radius=radius, emit=emit, cancelled=cancel.is_set)
                result = route_anchor_edit(road, source, anchors, segment, index, mode, radius, position, remove, allow_private=private)
            out, mapped, selected, notes = result
            return estimated_schedule(source, out), mapped, selected, notes
        def done(result):
            if result is None: return
            out, mapped, selected, notes = result
            def apply():
                estimated = not same_route(self.edit_segments, out)
                self.remember()
                self.edit_segments, self.anchor_indices = out, mapped
                self.selection = segment, selected
                self.applied_time_estimates = self.applied_time_estimates or estimated
                self.geometry_changed("Hoofdpunt verwijderd en tussenstuk opnieuw uitgelijnd." if remove else "Hoofdpunt verplaatst en aansluitingen opnieuw uitgelijnd.", automatic=False)
                self.status.set("Aansluiting overgenomen. Het tijdschema behoudt de beschikbare gemiddelde snelheid.")
                self.auto_notes.extend(notes)
                self.point_selected(segment, selected)
            self.review_route_proposal(out, apply, key=key, key_fn=self.alignment_key, notes=notes)
        self.alignment_task(work, done, "Aansluiting tussen hoofdpunten berekenen…")

    def quick_section_alignment(self, segment, left, right):
        from werkbank import MAPS, download_map
        from segment_join import find_connection
        if self.busy or left >= right: return
        self.alignment_kind="manual"
        source = copy.deepcopy(self.edit_segments)
        anchors = copy.deepcopy(self.anchor_indices)
        anchors[segment] = sorted(set(anchors[segment]+[left,right]))
        mode, style = self.routing_mode(), self.routing_style()
        radius = self.alignment_radius()
        if radius is None: return
        private, loaded = self.private_roads.get(), self.roadmap
        key = self.alignment_key()
        request = [[source[segment][left], source[segment][right]]]
        def work(cancel, emit):
            road = road_for_section(MAPS, request, lambda rows:action_download(rows,emit,cancel), style, loaded, radius=radius, emit=emit, cancelled=cancel.is_set)
            if cancel.is_set(): return None
            proposal = find_connection(road, source[segment][:left+1], source[segment][right:], mode, radius, allow_private=private)
            out, mapped = replace_anchor_section(source, anchors, segment, left, right, proposal.line, [0,len(proposal.line)-1])
            return estimated_schedule(source,out), mapped, proposal.notes
        def done(result):
            if result is None: return
            out,mapped,notes = result
            def apply():
                estimated = not same_route(self.edit_segments, out)
                self.remember()
                self.edit_segments,self.anchor_indices = out,mapped
                self.applied_time_estimates=self.applied_time_estimates or estimated
                self.auto_notes.extend(notes)
                self.geometry_changed("Gekozen omweg vervangen door een nieuwe verbinding.", automatic=False)
                self.status.set("Nieuwe verbinding overgenomen. Het tijdschema behoudt de beschikbare gemiddelde snelheid.")
            self.review_route_proposal(out,apply,key=key,key_fn=self.alignment_key,notes=notes)
        self.alignment_task(work,done,"Gekozen stuk opnieuw verbinden…")
