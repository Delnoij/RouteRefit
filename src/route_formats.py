# SPDX-License-Identifier: GPL-3.0-only
"""Local, bounded route import. The editable working format is GPX 1.1."""

from dataclasses import dataclass
from datetime import timezone
from pathlib import Path
from functools import cached_property
from xml.etree import ElementTree as ET
import io
import json
import math
import zipfile
from gpx_core import Track, Point, distance, parse_time, tag, local
from app_version import PRODUCT_NAME, DISPLAY_VERSION

SUPPORTED = {".gpx", ".kml", ".kmz", ".tcx", ".fit", ".geojson", ".json"}
LIMIT = 50_000_000
FILETYPES = [
    ("Routebestanden", "*.gpx *.kml *.kmz *.tcx *.fit *.geojson *.json"),
    ("GPX", "*.gpx"),
    ("KML / KMZ", "*.kml *.kmz"),
    ("Garmin FIT / TCX", "*.fit *.tcx"),
    ("GeoJSON", "*.geojson *.json"),
]


@dataclass
class ImportedRoute:
    gpx: bytes
    original: bytes
    suffix: str
    converted: bool

    @cached_property
    def track(self):
        """Reuse the validated GPX model instead of parsing its XML again."""
        return Track(self.gpx)


def xml_root(raw):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("XML met entiteiten wordt niet geopend.")
    return ET.fromstring(raw)


def number(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Ongeldige coördinaten of hoogte.")
    return result


def point(lon, lat, ele=None, time=None):
    lon, lat = number(lon), number(lat)
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        raise ValueError("Ongeldige coördinaten.")
    return lon, lat, number(ele) if ele is not None else None, time


def child_text(node, name):
    return next((c.text for c in node if local(c.tag) == name), None)


def descendants(node, name):
    return [c for c in node.iter() if local(c.tag) == name]


def make_gpx(name, segments, waypoints=(), activity_type=None):
    segments = [s for s in segments if s]
    if not any(len(s) >= 2 for s in segments):
        raise ValueError("Geen route met minstens twee GPS-punten gevonden.")
    if sum(map(len, segments)) > 500000:
        raise ValueError("Meer dan 500.000 routepunten; kies een kleiner bestand.")
    root = ET.Element(tag("gpx"), version="1.1", creator=f"{PRODUCT_NAME} {DISPLAY_VERSION}")
    for title, p, description in waypoints:
        lon, lat, ele, time = p
        node = ET.SubElement(root, tag("wpt"), lat=str(lat), lon=str(lon))
        if ele is not None:
            ET.SubElement(node, tag("ele")).text = str(ele)
        ET.SubElement(node, tag("name")).text = title or "Waypoint"
        if description:
            ET.SubElement(node, tag("desc")).text = description
    trk = ET.SubElement(root, tag("trk"))
    ET.SubElement(trk, tag("name")).text = name
    if activity_type:
        ET.SubElement(trk, tag("type")).text = activity_type
    for points in segments:
        segment = ET.SubElement(trk, tag("trkseg"))
        for lon, lat, ele, time in points:
            node = ET.SubElement(segment, tag("trkpt"), lat=str(lat), lon=str(lon))
            if ele is not None:
                ET.SubElement(node, tag("ele")).text = str(ele)
            if time:
                ET.SubElement(node, tag("time")).text = str(time)
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return raw


def kml(raw, name):
    root = xml_root(raw)
    if local(root.tag) != "kml":
        raise ValueError("Dit bestand is geen KML.")
    segments = []
    waypoints = []
    for placemark in descendants(root, "Placemark"):
        title = child_text(placemark, "name") or name
        for line in descendants(placemark, "LineString"):
            coords = child_text(line, "coordinates") or ""
            values = []
            for item in coords.split():
                fields = item.split(",")
                if len(fields) < 2:
                    raise ValueError("Ongeldige KML-coördinaten.")
                values.append(
                    point(
                        fields[0], fields[1], fields[2] if len(fields) > 2 and fields[2] else None
                    )
                )
            segments.append(values)
        for track in descendants(placemark, "Track"):
            times = [c.text for c in track if local(c.tag) == "when"]
            coords = [c.text for c in track if local(c.tag) == "coord"]
            if times and len(times) != len(coords):
                raise ValueError("KML-tijden en punten komen niet overeen.")
            values = []
            for i, item in enumerate(coords):
                fields = (item or "").split()
                if len(fields) < 2:
                    raise ValueError("Ongeldige KML-coördinaten.")
                values.append(
                    point(
                        fields[0],
                        fields[1],
                        fields[2] if len(fields) > 2 else None,
                        times[i] if times else None,
                    )
                )
            segments.append(values)
        for geometry in descendants(placemark, "Point"):
            fields = (child_text(geometry, "coordinates") or "").strip().split(",")
            if len(fields) >= 2:
                waypoints.append(
                    (
                        title,
                        point(fields[0], fields[1], fields[2] if len(fields) > 2 else None),
                        child_text(placemark, "description") or "",
                    )
                )
    return make_gpx(name, segments, waypoints)


def tcx(raw, name):
    root = xml_root(raw)
    if local(root.tag) != "TrainingCenterDatabase":
        raise ValueError("Dit bestand is geen TCX.")
    segments = []
    waypoints = []
    parents = {child: parent for parent in root.iter() for child in parent}

    def ancestor(node, kind):
        while node is not None and local(node.tag) != kind:
            node = parents.get(node)
        return node

    def contiguous(a, b):
        ta, tb = parse_time(a[3]), parse_time(b[3])
        if a[:2] == b[:2] and ((ta is None and tb is None) or ta == tb):
            return True
        return bool(
            ta
            and tb
            and 0 < (tb - ta).total_seconds() <= 15
            and distance(Point(a[1], a[0]), Point(b[1], b[0])) <= 100
        )

    previous_owner = previous_lap = None
    previous_clean = False
    for track in descendants(root, "Track"):
        owner, lap = ancestor(track, "Activity"), ancestor(track, "Lap")
        chunks = []
        points = []
        nodes = descendants(track, "Trackpoint")
        starts_clean = bool(nodes and descendants(nodes[0], "Position"))
        ends_clean = bool(nodes and descendants(nodes[-1], "Position"))
        for node in nodes:
            position = next(iter(descendants(node, "Position")), None)
            if position is None:
                if points:
                    chunks.append(points)
                    points = []
                continue
            points.append(
                point(
                    child_text(position, "LongitudeDegrees"),
                    child_text(position, "LatitudeDegrees"),
                    child_text(node, "AltitudeMeters"),
                    child_text(node, "Time"),
                )
            )
        if points:
            chunks.append(points)
        for i, chunk in enumerate(chunks):
            if (
                i == 0
                and segments
                and starts_clean
                and previous_clean
                and owner is not None
                and owner is previous_owner
                and lap is not None
                and previous_lap is not None
                and lap is not previous_lap
                and contiguous(segments[-1][-1], chunk[0])
            ):
                # A lap is a timing division, not a recording discontinuity.
                # Keep duplicate boundary samples and all their measured data.
                segments[-1].extend(chunk)
            else:
                segments.append(chunk)
        previous_owner, previous_lap, previous_clean = owner, lap, ends_clean and bool(chunks)
    for node in descendants(root, "CoursePoint"):
        position = next(iter(descendants(node, "Position")), None)
        if position is not None:
            waypoints.append(
                (
                    child_text(node, "Name") or "Waypoint",
                    point(
                        child_text(position, "LongitudeDegrees"),
                        child_text(position, "LatitudeDegrees"),
                        child_text(node, "AltitudeMeters"),
                    ),
                    child_text(node, "Notes") or "",
                )
            )
    # Keep the declared activity; never guess a shared mode for mixed sessions.
    activities = descendants(root, "Activity")
    sports = {a.get("Sport", "").strip().casefold() for a in activities}
    activity_type = next(iter(sports)) if len(sports) == 1 and "" not in sports else None
    return make_gpx(name, segments, waypoints, activity_type=activity_type)


def geojson(raw, name):
    document = json.loads(raw)
    segments = []
    waypoints = []

    def coords(value):
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            raise ValueError("Ongeldige GeoJSON-coördinaten.")
        return point(value[0], value[1], value[2] if len(value) > 2 else None)

    def visit(obj, title=name, depth=0):
        if depth > 30:
            raise ValueError("GeoJSON is te diep genest.")
        if not isinstance(obj, dict):
            raise ValueError("Ongeldig GeoJSON-object.")
        kind = obj.get("type")
        if kind == "FeatureCollection":
            for feature in obj.get("features", []):
                visit(feature, title, depth + 1)
        elif kind == "Feature":
            props = obj.get("properties") or {}
            if obj.get("geometry") is not None:
                visit(obj["geometry"], str(props.get("name") or title), depth + 1)
        elif kind == "GeometryCollection":
            for geometry in obj.get("geometries", []):
                visit(geometry, title, depth + 1)
        elif kind == "LineString":
            segments.append([coords(c) for c in obj["coordinates"]])
        elif kind == "MultiLineString":
            segments.extend([[coords(c) for c in line] for line in obj["coordinates"]])
        elif kind == "Point":
            waypoints.append((title, coords(obj["coordinates"]), ""))
        elif kind == "MultiPoint":
            waypoints.extend((title, coords(c), "") for c in obj["coordinates"])
        else:
            raise ValueError("Niet-ondersteunde GeoJSON-geometrie; gebruik lijnen en punten.")

    visit(document)
    return make_gpx(name, segments, waypoints)


def fit(raw, name):
    import fitdecode

    segments = []
    points = []
    waypoints = []
    sessions = []
    sports = []
    # Read raw semicircles, avoiding processor-specific degree conversion.
    with fitdecode.FitReader(
        io.BytesIO(raw),
        processor=None,
        check_crc=fitdecode.CrcCheck.RAISE,
        error_handling=fitdecode.ErrorHandling.RAISE,
    ) as reader:
        for frame in reader:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue
            if frame.name not in ("record", "course_point", "event", "session", "sport"):
                continue

            def get(field):
                return frame.get_value(field, fallback=None)

            if frame.name in ("session", "sport"):
                (sessions if frame.name == "session" else sports).append(get("sport"))
                continue

            if frame.name == "event":
                if get("event") in (0, "timer") and get("event_type") in (
                    1,
                    4,
                    8,
                    9,
                    "stop",
                    "stop_all",
                    "stop_disable",
                    "stop_disable_all",
                ):
                    if points:
                        segments.append(points)
                        points = []
                continue
            lat, lon = get("position_lat"), get("position_long")
            if lat is None or lon is None:
                if frame.name == "record" and points:
                    segments.append(points)
                    points = []
                continue
            altitude = get("enhanced_altitude")
            if altitude is None:
                altitude = get("altitude")
            # Field scale/offsets are applied by FitReader even with no processor.
            stamp = get("timestamp")
            if isinstance(stamp, (float, int)):
                from datetime import datetime, timedelta

                stamp = (
                    datetime(1989, 12, 31, tzinfo=timezone.utc) + timedelta(seconds=stamp)
                ).isoformat()
            elif hasattr(stamp, "isoformat"):
                stamp = stamp.isoformat()
            p = point(lon * 180 / (2**31), lat * 180 / (2**31), altitude, stamp)
            if frame.name == "course_point":
                waypoints.append((str(get("name") or "Waypoint"), p, ""))
            else:
                points.append(p)
    if points:
        segments.append(points)
    # Timer stops at (almost) the same GPS position are pauses, not missing
    # stretches of road. Keep all measured samples, including isolated ones.
    continuous = []
    for segment in segments:
        if not segment:
            continue
        a = continuous[-1][-1] if continuous else None
        b = segment[0]
        ta, tb = (parse_time(a[3]), parse_time(b[3])) if a else (None, None)
        if a and ta and tb and tb >= ta and distance(Point(a[1], a[0]), Point(b[1], b[0])) <= 2:
            continuous[-1].extend(segment)
        else:
            continuous.append(segment)
    declared = set(sessions or sports)
    activity_type = next(iter(declared)) if len(declared) == 1 else None
    activity_type = activity_type if isinstance(activity_type, str) else None
    return make_gpx(name, continuous, waypoints, activity_type=activity_type)


def read_route(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError("Bestandsformaat niet ondersteund.")
    with path.open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError("Routebestand groter dan 50 MB.")
    source = raw
    if suffix == ".gpx":
        result = ImportedRoute(raw, source, suffix, False)
        _ = result.track
        return result
    if suffix == ".kmz":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = [
                m
                for m in archive.infolist()
                if m.filename.lower().endswith(".kml") and not m.is_dir()
            ]
            if not members:
                raise ValueError("KMZ bevat geen KML-bestand.")
            if len(members) != 1:
                raise ValueError("KMZ bevat meerdere KML-bestanden; importeer één KML apart.")
            member = members[0]
            if member.file_size > LIMIT:
                raise ValueError("KML in KMZ is groter dan 50 MB.")
            with archive.open(member) as stream:
                raw = stream.read(LIMIT + 1)
            if len(raw) > LIMIT:
                raise ValueError("KML in KMZ is groter dan 50 MB.")
    converter = {
        ".kml": kml,
        ".kmz": kml,
        ".tcx": tcx,
        ".fit": fit,
        ".geojson": geojson,
        ".json": geojson,
    }[suffix]
    result = ImportedRoute(converter(raw, path.stem), source, suffix, True)
    _ = result.track
    return result
