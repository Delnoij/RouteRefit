# SPDX-License-Identifier: GPL-3.0-only
"""Select OSM road-data tiles around a route, rather than its empty bounding box."""

import hashlib
import math

LAT_MARGIN = 0.004
LON_MARGIN = 0.006
MAX_ROUTE_TILES = 200


def plan_route_tiles(segments, max_tiles=MAX_ROUTE_TILES):
    points = [point for segment in segments for point in segment]
    if not points:
        raise ValueError("Geen routepunten.")
    south = max(-90, min(p.lat for p in points) - LAT_MARGIN)
    north = min(90, max(p.lat for p in points) + LAT_MARGIN)
    west = max(-180, min(p.lon for p in points) - LON_MARGIN)
    east = min(180, max(p.lon for p in points) + LON_MARGIN)
    ny = max(1, math.ceil((north - south) / 0.02))
    nx = max(1, math.ceil((east - west) / 0.03))
    dx, dy = (east - west) / nx, (north - south) / ny
    cells = set()

    def add(lat, lon):
        first_x = max(0, math.floor((lon - LON_MARGIN - west) / dx))
        last_x = min(nx - 1, math.floor((lon + LON_MARGIN - west) / dx))
        first_y = max(0, math.floor((lat - LAT_MARGIN - south) / dy))
        last_y = min(ny - 1, math.floor((lat + LAT_MARGIN - south) / dy))
        for iy in range(first_y, last_y + 1):
            for ix in range(first_x, last_x + 1):
                cells.add((iy, ix))
        if len(cells) > max_tiles:
            raise ValueError(
                "Meer dan 200 kaartvakken langs de route nodig. De GPX blijft geopend. Kies een kleiner routestuk of importeer lokale OSM-weggegevens."
            )

    for segment in segments:
        for i, point in enumerate(segment):
            add(point.lat, point.lon)
            if i:
                previous = segment[i - 1]
                # Include sparsely recorded edges; never connect separate segments.
                steps = math.ceil(
                    max(
                        abs(point.lat - previous.lat) / 0.002, abs(point.lon - previous.lon) / 0.003
                    )
                )
                if steps > 100000:
                    raise ValueError(
                        "Dit routestuk beslaat een uitzonderlijk groot gebied. De GPX blijft geopend; importeer lokale OSM-weggegevens."
                    )
                for step in range(1, steps):
                    fraction = step / steps
                    add(
                        previous.lat + fraction * (point.lat - previous.lat),
                        previous.lon + fraction * (point.lon - previous.lon),
                    )

    return tuple(
        (west + ix * dx, south + iy * dy, west + (ix + 1) * dx, south + (iy + 1) * dy)
        for iy, ix in sorted(cells)
    )


def map_cache_name(tiles):
    """Different route corridors with the same outer bounds must not share a map."""
    signature = ";".join(",".join(f"{v:.7f}" for v in tile) for tile in tiles)
    digest = hashlib.sha256(signature.encode("ascii")).hexdigest()[:24]
    return f"route-{digest}.osm"
