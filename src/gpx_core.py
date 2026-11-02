# SPDX-License-Identifier: GPL-3.0-only
"""Local GPX editing. No routing service or upload is used."""

from __future__ import annotations
import copy, hashlib, math, bisect, uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from app_version import PRODUCT_NAME, DISPLAY_VERSION

NS = "http://www.topografix.com/GPX/1/1"
ET.register_namespace("", NS)


def tag(name):
    return "{" + NS + "}" + name


def local(name):
    return name.rsplit("}", 1)[-1]


@dataclass
class Point:
    lat: float
    lon: float
    ele: float | None = None
    time: datetime | None = None
    element: object = None


@dataclass
class Waypoint:
    lat: float
    lon: float
    name: str = ""
    description: str = ""
    photo: str = ""
    key: str = ""
    element: object = None

    def __post_init__(self):
        if not self.key:
            self.key = uuid.uuid4().hex

    def validate(self):
        if not self.name.strip():
            raise ValueError("Geef het waypoint een naam.")
        if len(self.name) > 200:
            raise ValueError("De naam mag maximaal 200 tekens bevatten.")
        if len(self.description) > 1500:
            raise ValueError("De omschrijving mag maximaal 1.500 tekens bevatten.")
        if (
            not math.isfinite(self.lat + self.lon)
            or not -90 <= self.lat <= 90
            or not -180 <= self.lon <= 180
        ):
            raise ValueError("Ongeldige waypointpositie.")


def route_anchor_edit(
    roadmap,
    segments,
    anchors,
    segment,
    index,
    mode,
    radius,
    position=None,
    remove=False,
    allow_private=False,
):
    controls = anchors[segment]
    if index not in controls:
        raise ValueError("Kies een groter hoofdpunt.")
    ordinal = controls.index(index)
    if remove and ordinal in (0, len(controls) - 1):
        raise ValueError("Begin en einde blijven hoofdpunten. Je kunt ze wel verplaatsen.")
    if len(controls) < 2:
        raise ValueError("Dit routedeel heeft te weinig punten.")
    left = controls[max(0, ordinal - 1)]
    right = controls[min(len(controls) - 1, ordinal + 1)]
    # Discard recorded detour samples: only the remaining controls define the new leg.
    kept_controls = [i for i in controls if left <= i <= right and (not remove or i != index)]
    section = [segments[segment][i] for i in kept_controls]
    if position is not None:
        section = move_point([section], 0, kept_controls.index(index), position)[0]
    local_controls = list(range(len(section)))
    try:
        result, notes, mapped = roadmap.snap(
            [section],
            mode,
            radius,
            control_indices=[local_controls],
            with_controls=True,
            allow_private=allow_private,
        )
    except AlignmentError as exc:
        raise AlignmentError(
            str(exc),
            segment,
            left + exc.index,
            left + exc.end_index if exc.end_index is not None else None,
        ) from exc
    out, new_controls = replace_anchor_section(
        segments, anchors, segment, left, right, result[0], mapped[0]
    )
    selected = left + mapped[0][0 if remove or ordinal == 0 else 1]
    return out, new_controls, selected, notes


class AlignmentError(ValueError):
    def __init__(self, message, segment, index, end_index=None):
        super().__init__(message)
        self.segment = segment
        self.index = index
        self.end_index = end_index


def move_point(segments, segment, index, position):
    out = [list(s) for s in segments]
    if (
        not math.isfinite(position.lat + position.lon)
        or not -85 <= position.lat <= 85
        or not -180 <= position.lon <= 180
    ):
        raise ValueError("Ongeldige kaartpositie.")
    out[segment][index] = replace(out[segment][index], lat=position.lat, lon=position.lon)
    return out


def insert_point(segments, segment, index, fraction, position):
    out = [list(s) for s in segments]
    a, b = out[segment][index : index + 2]
    f = max(0, min(1, fraction))
    elevation = a.ele + f * (b.ele - a.ele) if a.ele is not None and b.ele is not None else None
    time = a.time + (b.time - a.time) * f if a.time is not None and b.time is not None else None
    out[segment].insert(index + 1, Point(position.lat, position.lon, elevation, time))
    return out


def delete_point(segments, segment, index):
    if len(segments[segment]) <= 2:
        raise ValueError("Een routedeel moet ten minste twee punten houden.")
    out = [list(s) for s in segments]
    del out[segment][index]
    return out


ANCHOR_DENSITY = {"Weinig": (40, 600), "Normaal": (25, 400), "Veel": (12, 200)}


def choose_anchors(segments, density="Normaal"):
    """Shape-aware RDP controls plus a maximum arc length; independent of GPS sampling."""
    tolerance, maximum = ANCHOR_DENSITY[density]
    result = []
    for s in segments:
        if len(s) < 2:
            result.append([0])
            continue
        scale = 111195 * math.cos(math.radians(s[0].lat))
        xy = [((p.lon - s[0].lon) * scale, (p.lat - s[0].lat) * 111195) for p in s]
        keep = {0, len(s) - 1}
        stack = [(0, len(s) - 1)]
        while stack:
            a, b = stack.pop()
            if b <= a + 1:
                continue
            ax, ay = xy[a]
            bx, by = xy[b]
            dx = bx - ax
            dy = by - ay
            den = dx * dx + dy * dy
            best = -1
            index = a
            for i in range(a + 1, b):
                x, y = xy[i]
                f = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / den)) if den else 0
                error = (x - ax - f * dx) ** 2 + (y - ay - f * dy) ** 2
                if error > best:
                    best = error
                    index = i
            if best > tolerance * tolerance:
                keep.add(index)
                stack.extend([(a, index), (index, b)])
        cum = cumulative(s)
        shape = sorted(keep)
        for a, b in zip(shape, shape[1:]):
            steps = math.ceil((cum[b] - cum[a]) / maximum)
            for k in range(1, steps):
                i = bisect.bisect_left(cum, cum[a] + (cum[b] - cum[a]) * k / steps)
                if a < i < b:
                    keep.add(i)
        result.append(sorted(keep))
    return result


def replace_anchor_section(
    segments, anchors, segment, left, right, replacement, replacement_controls
):
    """Replace one control interval, preserving every point/control outside it."""
    if (
        not 0 <= left < right < len(segments[segment])
        or left not in anchors[segment]
        or right not in anchors[segment]
    ):
        raise ValueError("Ongeldige grenzen van de hoofdpunten.")
    if (
        len(replacement) < 2
        or not replacement_controls
        or replacement_controls[0] != 0
        or replacement_controls[-1] != len(replacement) - 1
    ):
        raise ValueError("De nieuwe lijn heeft ongeldige hoofdpunten.")
    out = [list(s) for s in segments]
    controls = [list(a) for a in anchors]
    out[segment] = out[segment][:left] + replacement + out[segment][right + 1 :]
    delta = len(replacement) - (right - left + 1)
    controls[segment] = (
        [i for i in anchors[segment] if i < left]
        + [left + i for i in replacement_controls]
        + [i + delta for i in anchors[segment] if i > right]
    )
    return out, controls


def distance(a, b):
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat, dlon = lat2 - lat1, math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 12742000 * math.asin(min(1, math.sqrt(h)))


def cumulative(points):
    out = [0.0]
    for a, b in zip(points, points[1:]):
        out.append(out[-1] + distance(a, b))
    return out


def parse_time(value):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return d.astimezone(timezone.utc) if d.tzinfo else None
    except ValueError:
        return None


class Track:
    def __init__(self, raw: bytes):
        if len(raw) > 50_000_000:
            raise ValueError("GPX groter dan 50 MB.")
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError("GPX met XML-entiteiten wordt niet geopend.")
        self.raw = raw
        self.hash = hashlib.sha256(raw).hexdigest()
        self.root = ET.fromstring(raw)
        if local(self.root.tag) != "gpx":
            raise ValueError("Dit bestand is geen GPX.")
        self.segments = []
        self.containers = []
        for container in self.root.iter():
            if local(container.tag) not in ("trkseg", "rte"):
                continue
            pts = []
            for node in container:
                if local(node.tag) not in ("trkpt", "rtept"):
                    continue
                lat, lon = float(node.attrib["lat"]), float(node.attrib["lon"])
                if not math.isfinite(lat + lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                    raise ValueError("Ongeldige coördinaten in de GPX.")
                data = {local(c.tag): c.text for c in node}
                try:
                    ele = float(data["ele"]) if data.get("ele") else None
                except ValueError:
                    ele = None
                if ele is not None and not math.isfinite(ele):
                    ele = None
                pts.append(Point(lat, lon, ele, parse_time(data.get("time")), node))
            if pts:
                self.segments.append(pts)
                self.containers.append(container)
        if not self.segments:
            raise ValueError("Geen track- of routepunten gevonden.")
        self.waypoints = []
        for w in self.root:
            if local(w.tag) != "wpt":
                continue
            fields = {local(c.tag): c.text or "" for c in w}
            photo = ""
            for link in w:
                if local(link.tag) == "link" and link.attrib.get("href"):
                    photo = link.attrib["href"]
                    break
            self.waypoints.append(
                Waypoint(
                    float(w.attrib["lat"]),
                    float(w.attrib["lon"]),
                    fields.get("name", ""),
                    fields.get("desc", fields.get("cmt", "")),
                    photo,
                    element=w,
                )
            )
        names = [
            n.text
            for tr in self.root
            if local(tr.tag) in ("trk", "rte")
            for n in tr
            if local(n.tag) == "name" and n.text
        ]
        self.name = names[0] if names else "GPX-route"
        activities = []
        for container in self.root:
            if local(container.tag) not in ("trk", "rte"):
                continue
            for child in container:
                if local(child.tag) == "type" and child.text:
                    activities.append(child.text.strip().casefold().replace("-", "_"))
        bike = {
            "cycling",
            "biking",
            "bike",
            "bicycle",
            "road_biking",
            "mountain_biking",
            "gravel_cycling",
            "e_bike_fitness",
            "e_biking",
            "touring",
        }
        walk = {"walking", "walk", "hiking", "hike", "mountaineering", "trekking"}
        modes = {
            ("bike" if kind in bike else "walk" if kind in walk else
             "motorcar" if kind in {'driving','car','motorcar'} else
             "motorcycle" if kind in {'motorcycle','motorcycling','motorbiking'} else None) for kind in activities
        }
        self.activity_mode = next(iter(modes)) if len(modes) == 1 else None

    def stats(self, segments=None):
        segs = self.segments if segments is None else segments
        timed = all(p.time is not None for s in segs for p in s)
        valid = timed and all(b.time >= a.time for s in segs for a, b in zip(s, s[1:]))
        return dict(
            km=sum(cumulative(s)[-1] for s in segs) / 1000,
            seconds=sum((s[-1].time - s[0].time).total_seconds() for s in segs) if valid else None,
            elevation=all(p.ele is not None for s in segs for p in s),
            points=sum(map(len, segs)),
            segments=len(segs),
            valid_time=valid,
        )

    def export(
        self,
        segments,
        estimated=False,
        waypoints=None,
        photo_links=None,
        modification_note=None,
        preserve_points=False,
        segment_groups=None,
    ):
        root = copy.deepcopy(self.root)
        for n in root.iter():
            if n.tag.startswith(
                ("{http://www.topografix.com/GPX/1/0}", "{http://www.topografix.com/GPX/1/1}")
            ):
                n.tag = tag(local(n.tag))
        root.set("version", "1.1")
        if waypoints is not None:
            for n in list(root):
                if local(n.tag) == "wpt":
                    root.remove(n)
            insertion = next(
                (i for i, n in enumerate(root) if local(n.tag) in ("rte", "trk", "extensions")),
                len(root),
            )
            for w in waypoints:
                w.validate()
                node = copy.deepcopy(w.element) if w.element is not None else ET.Element(tag("wpt"))
                for ch in node.iter():
                    if ch.tag.startswith("{http://www.topografix.com/GPX/1/0}"):
                        ch.tag = tag(local(ch.tag))
                node.tag = tag("wpt")
                node.attrib.update(lat=f"{w.lat:.8f}", lon=f"{w.lon:.8f}")
                for ch in list(node):
                    if local(ch.tag) in ("name", "desc", "cmt", "link"):
                        node.remove(ch)
                for name, value in [("name", w.name.strip()), ("desc", w.description)]:
                    child = ET.Element(tag(name))
                    child.text = value
                    # GPX 1.1: name/desc come after ele/time/etc and before sym/type/extensions.
                    at = next(
                        (
                            i
                            for i, c in enumerate(node)
                            if local(c.tag)
                            in (
                                "sym",
                                "type",
                                "fix",
                                "sat",
                                "hdop",
                                "vdop",
                                "pdop",
                                "ageofdgpsdata",
                                "dgpsid",
                                "extensions",
                            )
                        ),
                        len(node),
                    )
                    node.insert(at, child)
                link = (photo_links or {}).get(w.key, w.photo)
                if link:
                    child = ET.Element(tag("link"), href=link)
                    ET.SubElement(child, tag("text")).text = "Foto bij " + w.name.strip()
                    at = next(
                        (
                            i
                            for i, c in enumerate(node)
                            if local(c.tag)
                            in (
                                "sym",
                                "type",
                                "fix",
                                "sat",
                                "hdop",
                                "vdop",
                                "pdop",
                                "ageofdgpsdata",
                                "dgpsid",
                                "extensions",
                            )
                        ),
                        len(node),
                    )
                    node.insert(at, child)
                root.insert(insertion, node)
                insertion += 1
        containers = [
            n
            for n in root.iter()
            if local(n.tag) in ("trkseg", "rte")
            and any(local(c.tag) in ("trkpt", "rtept") for c in n)
        ]
        if segment_groups is not None:
            if (
                len(segment_groups) != len(segments)
                or any(not isinstance(group, list) or not group for group in segment_groups)
                or [i for group in segment_groups for i in group] != list(range(len(containers)))
                or any(type(i) is not int for group in segment_groups for i in group)
            ):
                raise ValueError("Ongeldige indeling van de verbonden routedelen.")
            parents = {child: parent for parent in root.iter() for child in parent}
            kept = []
            for group in segment_groups:
                first = containers[group[0]]
                kept.append(first)
                for source_index in group[1:]:
                    removed = containers[source_index]
                    # Retain segment extensions when the two recording pieces
                    # become one. Source point extensions are copied below.
                    extension = next((n for n in removed if local(n.tag) == "extensions"), None)
                    if extension is not None:
                        target = next((n for n in first if local(n.tag) == "extensions"), None)
                        if target is None:
                            target = ET.SubElement(first, tag("extensions"))
                        target.extend(list(extension))
                    parents[removed].remove(removed)
            containers = kept
            preserve_points = preserve_points and all(len(g) == 1 for g in segment_groups)
        if len(containers) != len(segments):
            raise ValueError("Aantal routedelen gewijzigd.")
        for container, pts in zip(containers, segments):
            if preserve_points:
                continue
            kind = "rtept" if local(container.tag) == "rte" else "trkpt"
            for n in list(container):
                if local(n.tag) in ("trkpt", "rtept"):
                    container.remove(n)
            for p in pts:
                n = copy.deepcopy(p.element) if p.element is not None else ET.Element(tag(kind))
                for ch in n.iter():
                    if ch.tag.startswith("{http://www.topografix.com/GPX/1/0}"):
                        ch.tag = tag(local(ch.tag))
                n.tag = tag(kind)
                n.attrib.update(lat=f"{p.lat:.8f}", lon=f"{p.lon:.8f}")
                # Derived speed values must agree with the replacement timestamps.
                for par in list(n.iter()):
                    for ch in list(par):
                        if local(ch.tag).lower() in ("time", "ele", "speed", "velocity"):
                            par.remove(ch)
                if p.time is not None:
                    t = ET.Element(tag("time"))
                    t.text = (
                        p.time.astimezone(timezone.utc)
                        .isoformat(timespec="milliseconds")
                        .replace("+00:00", "Z")
                    )
                    n.insert(0, t)
                if p.ele is not None:
                    e = ET.Element(tag("ele"))
                    e.text = f"{p.ele:.2f}"
                    n.insert(0, e)
                extensions_at = next(
                    (i for i, c in enumerate(container) if local(c.tag) == "extensions"),
                    len(container),
                )
                container.insert(extensions_at, n)
        root.set("creator", f"{PRODUCT_NAME} {DISPLAY_VERSION}")
        for par in root.iter():
            for ch in list(par):
                if local(ch.tag) == "bounds":
                    par.remove(ch)
        # Keep source description, waypoints and unrelated extensions.
        for trk in root:
            if local(trk.tag) not in ("trk", "rte"):
                continue
            desc = next((n for n in trk if local(n.tag) == "desc"), None)
            if desc is None:
                desc = ET.Element(tag("desc"))
                index = 0
                for child in trk:
                    if local(child.tag) in ("name", "cmt"):
                        index += 1
                    else:
                        break
                trk.insert(index, desc)
            desc.text = (
                (desc.text or "")
                + " | "
                + (
                    modification_note
                    if modification_note is not None
                    else "Geschatte bewegingstijd; berekend tijdprofiel."
                    if estimated
                    else "Bewerkte tijdlijn; pauzes volgens handmatige selectie verwijderd."
                )
            )
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)


@dataclass
class Pause:
    segment: int
    start: int
    end: int
    seconds: float
    uncertain: bool
    selected: bool = True


def pauses(segments, minimum=120, radius=20, max_speed=1.0):
    """Detect a stationary cluster, not merely low mean speed across a time gap."""
    result = []
    for si, s in enumerate(segments):
        if any(p.time is None for p in s) or any(b.time < a.time for a, b in zip(s, s[1:])):
            raise ValueError(
                "Pauzes verwijderen vereist volledige, oplopende tijden. Kies anders een nieuw tijdprofiel."
            )
        i = 0
        while i < len(s) - 1:
            j = i + 1
            while j < len(s) and distance(s[i], s[j]) <= radius:
                j += 1
            end = j - 1
            dt = (s[end].time - s[i].time).total_seconds()
            walked = sum(distance(a, b) for a, b in zip(s[i:end], s[i + 1 : end + 1]))
            span = distance(s[i], s[end])
            if end > i and dt >= minimum and walked / max(dt, 1) * 3.6 <= max_speed:
                # Sparse records are ambiguous: returning after a loop looks like a pause.
                uncertain = any(
                    (b.time - a.time).total_seconds() > max(90, minimum / 2)
                    for a, b in zip(s[i:end], s[i + 1 : end + 1])
                )
                result.append(Pause(si, i, end, dt, uncertain, not uncertain))
                i = end
            else:
                i += 1
        if si and s[0].time and segments[si - 1][-1].time:
            # Segment gaps are never connected by invented route geometry.
            gap = (s[0].time - segments[si - 1][-1].time).total_seconds()
            if gap > minimum:
                result.append(Pause(si, 0, 0, gap, True, False))
    return result


def remove_pauses(segments, found):
    out = []
    removed = 0.0
    cursor = None
    for si, s in enumerate(segments):
        intervals = [p for p in found if p.selected and p.segment == si and p.end > p.start]
        dst = []
        for i, p in enumerate(s):
            shift = sum(
                q.seconds
                if i >= q.end
                else max(0, (p.time - s[q.start].time).total_seconds())
                if i > q.start
                else 0
                for q in intervals
            )
            dst.append(replace(p, time=p.time - timedelta(seconds=shift)))
        # Selected sparse intervals are a user decision. Keep a small real travel duration
        # between different endpoints, avoiding infinite speed at an identical timestamp.
        for q in intervals:
            if distance(dst[q.start], dst[q.end]) > 0.05:
                rate = 5 / 3.6
                for ni in (q.start - 1, q.end):
                    if 0 <= ni < len(s) - 1:
                        dt = (s[ni + 1].time - s[ni].time).total_seconds()
                        d = distance(s[ni], s[ni + 1])
                        if dt > 0 and d > 0:
                            rate = d / dt
                            break
                needed = distance(dst[q.start], dst[q.end]) / max(rate, 0.1)
                if needed >= q.seconds:
                    raise ValueError("Geselecteerde pauze bevat te veel verplaatsing.")
                for k in range(q.start + 1, len(dst)):
                    fraction = min(1, (s[k].time - s[q.start].time).total_seconds() / q.seconds)
                    dst[k] = replace(
                        dst[k], time=dst[k].time + timedelta(seconds=needed * fraction)
                    )
                removed += q.seconds - needed
            else:
                removed += q.seconds
        # Website import sums segment durations; close inter-segment time gaps too.
        if cursor is not None:
            offset = dst[0].time - cursor
            dst = [replace(p, time=p.time - offset) for p in dst]
        cursor = dst[-1].time
        out.append(dst)
    return out, removed


PROFILES = {
    "Wandelen · rustig": ("walk", 3.5),
    "Wandelen · normaal": ("walk", 4.5),
    "Wandelen · stevig": ("walk", 5.5),
    "Fietsen · recreatief": ("bike", 16),
    "Fietsen · trekking": ("bike", 20),
    "Fietsen · sportief": ("bike", 27),
    "Fietsen · mountainbike": ("bike", 14),
    "Gravel · rustig": ("bike", 16),
    "Gravel · normaal": ("bike", 21),
    "Gravel · sportief": ("bike", 26),
    "Auto · normaal": ("motorcar", 50),
    "Motor · normaal": ("motorcycle", 50),
}


def modeled_times(segments, profile, flat_speed, start, target_seconds=None):
    mode = PROFILES[profile][0]
    motor=mode in ('motorcar','motorcycle')
    maximum=160 if motor else 60
    if not math.isfinite(flat_speed) or not 0.5 <= flat_speed <= maximum:
        raise ValueError(f"Snelheid moet tussen 0,5 en {maximum} km/u liggen.")
    if start.tzinfo is None:
        raise ValueError("Starttijd heeft geen tijdzone.")
    out = []
    clock = start
    durations = []
    for s in segments:
        cum = cumulative(s)
        # Slope on a ~60 m window suppresses single-point altitude noise.
        heights = []
        missing = [0]
        for point in s:
            missing.append(missing[-1] + (point.ele is None))
        for i, p in enumerate(s):
            lo = max(0, bisect.bisect_right(cum, cum[i] - 30) - 1)
            hi = min(len(s) - 1, bisect.bisect_left(cum, cum[i] + 30))
            if missing[hi + 1] != missing[lo]:
                if motor:
                    heights.append(0.);continue
                raise ValueError(
                    "Voor een terreinprofiel zijn volledige hoogtegegevens nodig. Importeer een GPX met hoogte; er worden geen hoogtes verzonnen."
                )
            slope = (s[hi].ele - s[lo].ele) / max(1, cum[hi] - cum[lo])
            heights.append(max(-0.45, min(0.45, slope)))
        ds = []
        for i, (a, b) in enumerate(zip(s, s[1:])):
            slope = (heights[i] + heights[i + 1]) / 2
            if mode == "walk":
                speed = flat_speed * math.exp(-3.5 * (abs(slope + 0.05) - 0.05))
                speed = max(0.7, min(flat_speed * 1.25, speed))
            elif motor:
                speed=flat_speed*math.exp(-.8*max(0,slope))
            else:
                speed = max(3, min(flat_speed * 1.8, flat_speed * math.exp(-5 * slope)))
            ds.append(distance(a, b) / (speed / 3.6))
        durations.append(ds)
    total = sum(map(sum, durations))
    if total <= 0:
        raise ValueError("De route bevat geen afstand.")
    if target_seconds is not None and (not math.isfinite(target_seconds) or target_seconds <= 0):
        raise ValueError("Ongeldige gewenste bewegingstijd.")
    factor = target_seconds / total if target_seconds else 1
    for s, ds in zip(segments, durations):
        dst = [replace(s[0], time=clock)]
        for p, dt in zip(s[1:], ds):
            clock += timedelta(seconds=dt * factor)
            dst.append(replace(p, time=clock))
        out.append(dst)
    return out


def allowed(tags, mode, allow_private=False):
    from access_policy import way_permitted

    return way_permitted(tags, mode, allow_private)


class RoadMap:
    """OSM XML road network. Every match is a reviewable candidate."""

    def __init__(self, raw):
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError("Ongeldig kaartbestand.")
        root = ET.fromstring(raw)
        if root.tag != "osm":
            raise ValueError("Importeer een .osm XML-bestand, geen PBF of afbeelding.")
        self.nodes = {
            int(n.attrib["id"]): Point(float(n.attrib["lat"]), float(n.attrib["lon"]))
            for n in root.findall("node")
        }
        self.node_tags = {
            int(n.attrib["id"]): {t.attrib["k"]: t.attrib["v"] for t in n.findall("tag")}
            for n in root.findall("node")
        }
        self.ways = []
        self._index_way_ids = []
        self._index_relations = []
        self.restrictions = 0
        for w in root.findall("way"):
            tags = {t.attrib["k"]: t.attrib["v"] for t in w.findall("tag")}
            if "highway" in tags:
                self.ways.append(([int(n.attrib["ref"]) for n in w.findall("nd")], tags))
                self._index_way_ids.append(int(w.attrib['id']))
        for r in root.findall("relation"):
            tags = {t.attrib["k"]: t.attrib["v"] for t in r.findall("tag")}
            if tags.get("type") == "restriction":
                self.restrictions += 1
                self._index_relations.append(ET.tostring(r,encoding='unicode'))
        if not self.ways:
            raise ValueError("Geen wegen of paden in dit kaartbestand.")

    def snap(
        self,
        segments,
        mode,
        radius=35,
        control_indices=None,
        with_controls=False,
        keep_intervals=None,
        allow_private=False,
        endpoint_radius=None,
    ):
        from routing_repair import robust_snap

        return robust_snap(
            self,
            segments,
            mode,
            radius,
            control_indices,
            with_controls,
            keep_intervals,
            allow_private,
            endpoint_radius,
        )


def write_new(path, data):
    with Path(path).open("xb") as f:
        f.write(data)


def duration(seconds):
    if seconds is None:
        return "ontbreekt / onbruikbaar"
    m = round(seconds / 60)
    return f"{m // 60} u {m % 60:02d} min"
