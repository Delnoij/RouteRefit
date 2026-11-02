# SPDX-License-Identifier: GPL-3.0-only
"""Resolve road corridors from the private spatial index before using the network."""
import math
from datetime import datetime
from pathlib import Path
from gpx_core import RoadMap, cumulative
from map_plan import plan_route_tiles, map_cache_name
from road_index import RoadIndex, bounds, missing_rectangles

def routing_query(segments, anchors=None, radius=40):
    """Select every locally known edge the unchanged matcher could reach.

    Padding enlarges only the SQL query, never the downloaded corridor.
    """
    points = [p for row in segments for p in row]
    longest = 0
    for si, row in enumerate(segments):
        if not row:
            continue
        controls = anchors[si] if anchors is not None else list(range(len(row)))
        lengths = cumulative(row)
        longest = max(longest, max((lengths[b] - lengths[a] for a, b in zip(controls, controls[1:])), default=0))
        # Automatic changed-road recovery can relax interior anchors across a
        # 1,500 m section; retain every edge that fallback could explore too.
        longest = max(longest, min(1500, lengths[-1]))
    margin = max(150, longest * 2.5 + 60) + 2 * radius + 20
    dy = margin / 110000
    dx = margin / (110000 * math.cos(math.radians(min(89.9, max((abs(p.lat) for p in points)) + dy))))
    return [bounds((max(-180, min((p.lon for p in points)) - dx), max(-90, min((p.lat for p in points)) - dy), min(180, max((p.lon for p in points)) + dx), min(90, max((p.lat for p in points)) + dy)))]

def prepare_index(index, segments, wanted, query=None, progress=None, cancelled=None):
    """Migrate raw tiles and exact-hash legacy corridors without false coverage.

    A road envelope cannot prove that the area between roads was fetched.
    """
    index.sync([*wanted, *(query or ())], progress, cancelled)
    from region_packages import sync_packages
    sync_packages(index,wanted,query,
                  (lambda message: progress(1,1)) if progress else None,cancelled)
    exact = index.folder / map_cache_name(plan_route_tiles(segments))
    if index.missing(wanted) and exact.is_file():
        try:
            RoadMap(exact.read_bytes())
            index.ingest_files([(exact, wanted)], legacy=True)
        except (OSError, ValueError):
            pass

def cached_road(folder, segments, style, loaded=None, anchors=None, radius=40, emit=None, cancelled=None):
    if loaded is not None and (not hasattr(loaded, '_index_generation')):
        return loaded
    wanted = [bounds(b) for b in plan_route_tiles(segments)]
    query = routing_query(segments, anchors, radius)
    with RoadIndex(folder) as index:
        prepare_index(index, segments, wanted, query, (lambda a, b: emit(f'Lokale wegen voorbereiden: {a}/{b} bestanden')) if emit else None, cancelled)
        if cancelled and cancelled():
            raise ValueError('Uitlijnen gestopt.')
        if index.missing(wanted):
            return None
        if loaded is not None and loaded._index_folder == str(index.folder) and (getattr(loaded, '_index_identity', None) == index.identity) and (loaded._index_generation == index.generation) and (not missing_rectangles(query, loaded._index_query)):
            road = loaded
        else:
            road = index.read(wanted, query)
        if road is None:
            raise ValueError('Geen wegen gevonden in de opgeslagen kaartgegevens voor dit gebied.')
        road.cycling_style = style
        if emit:
            date = datetime.fromtimestamp(road._index_stamp / 1000000000.0).strftime('%d-%m-%Y')
            emit(f'Lokale wegen beschikbaar (gegevens van {date}).')
        return road

def import_region(folder, path):
    """Keep original imports untouched; bounded extracts can serve future routes."""
    import hashlib
    from road_index import xml_bounds, INDEX_LOCK
    from werkbank import replace_cache
    source = Path(path)
    raw = source.read_bytes()
    road = RoadMap(raw)
    region_bounds = xml_bounds(source)
    if region_bounds:
        dest = Path(folder) / 'Regios' / (hashlib.sha256(raw).hexdigest() + '.osm')
        with INDEX_LOCK:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                replace_cache(dest, raw)
            with RoadIndex(folder) as index:
                index.ingest_files([(dest, [region_bounds])])
        return (dest, road)
    return (source, road)

def road_information(road):
    text = f'{len(road.ways):,} wegen/paden lokaal beschikbaar. © OpenStreetMap-bijdragers.'
    if getattr(road, '_index_stamp', None):
        date = datetime.fromtimestamp(road._index_stamp / 1000000000.0).strftime('%d-%m-%Y')
        text += f' Gegevens van {date}. Ververs via Kaart indien nodig.'
    return text

def downloaded_road(folder, path, segments):
    road = cached_road(folder, segments, 'trekking')
    return road if road is not None else RoadMap(path.read_bytes())
