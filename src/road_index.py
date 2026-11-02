# SPDX-License-Identifier: GPL-3.0-only
"""Private, rebuildable spatial road index. No GPX data or network client lives here."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import math
import re
import sqlite3
import time
import threading
import xml.etree.ElementTree as ET
EPS = 1e-07
MAX_BYTES = 128000000
INDEX_LOCK = threading.RLock()

def validate_osm(raw):
    """Empty areas are valid; incomplete ways and service error pages are not."""
    if len(raw) > MAX_BYTES:
        raise ValueError('Kaartbestand is te groot voor de lokale index.')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('Ongeldig kaartbestand.')
    root = ET.fromstring(raw)
    if root.tag != 'osm' or root.find('remark') is not None:
        raise ValueError('Onvolledige weggegevens.')
    ids = set()
    for node in root.findall('node'):
        ident = int(node.get('id'))
        lat = float(node.get('lat'))
        lon = float(node.get('lon'))
        if not math.isfinite(lat + lon) or not -90 <= lat <= 90 or (not -180 <= lon <= 180):
            raise ValueError('Ongeldige kaartpositie.')
        ids.add(ident)
    for way in root.findall('way'):
        if not any((tag.get('k') == 'highway' for tag in way.findall('tag'))):
            continue
        refs = [int(node.get('ref')) for node in way.findall('nd')]
        if len(refs) < 2 or not set(refs) <= ids:
            raise ValueError('Onvolledige weggegevens: wegpunten ontbreken.')
    return root

def bounds(value):
    if len(value) != 4:
        raise ValueError('Ongeldige gebiedsgrenzen.')
    w, s, e, n = (round(float(v), 7) for v in value)
    if not all((math.isfinite(v) for v in (w, s, e, n))) or not -180 <= w < e <= 180 or (not -90 <= s < n <= 90):
        raise ValueError('Ongeldige gebiedsgrenzen.')
    return (w, s, e, n)

def subtract(box, cover):
    w, s, e, n = box
    a, b, c, d = cover
    l, r = (max(w, a), min(e, c))
    bottom, top = (max(s, b), min(n, d))
    if r - l <= EPS or top - bottom <= EPS:
        return [box]
    return [v for v in [(w, s, l, n), (r, s, e, n), (l, s, r, bottom), (l, top, r, n)] if v[2] - v[0] > EPS and v[3] - v[1] > EPS]

def missing_rectangles(wanted, coverage):
    remaining = list(wanted)
    for cover in coverage:
        remaining = [part for box in remaining for part in subtract(box, cover)]
        if not remaining:
            break
    return remaining

def xml_bounds(path):
    with Path(path).open('rb') as stream:
        head = stream.read(65536)
    if b'<!DOCTYPE' in head.upper() or b'<!ENTITY' in head.upper():
        raise ValueError('Ongeldig kaartbestand.')
    match = re.search(b'<bounds\\b[^>]*/>', head)
    if not match:
        return None
    item = ET.fromstring(match[0])
    a = item.attrib
    return bounds((a['minlon'], a['minlat'], a['maxlon'], a['maxlat']))

def chunks(values, size=800):
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i:i + size]

class RoadIndex:

    def __init__(self, folder):
        self.folder = Path(folder).resolve()
        private = self.folder / 'Wegenindex'
        private.mkdir(parents=True, exist_ok=True)
        self.path = private / 'wegen.sqlite3'
        try:
            self._open()
        except sqlite3.DatabaseError:
            # Preserve damaged index files; originals and raw maps stay intact.
            if hasattr(self, 'db'):
                self.db.close()
            self.path.replace(private / f'wegen-beschadigd-{time.time_ns()}.sqlite3')
            self._open()

    def _open(self):
        self.db = sqlite3.connect(self.path, timeout=30)
        # Opening an existing index is read-only work. Avoid schema/DML locks
        # while another worker is publishing a new batch of roads.
        try:
            version=self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            identity=self.db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
            if version == (1,) and identity:
                self.identity=identity[0]
                return
        except sqlite3.OperationalError as exc:
            if 'no such table' not in str(exc):raise
        self.db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value INTEGER NOT NULL);
        INSERT OR IGNORE INTO meta VALUES('generation',0);
        CREATE TABLE IF NOT EXISTS sources(path TEXT PRIMARY KEY,mtime INTEGER,size INTEGER,digest TEXT,stamp INTEGER);
        CREATE TABLE IF NOT EXISTS coverage(source TEXT,w REAL,s REAL,e REAL,n REAL,stamp INTEGER,PRIMARY KEY(source,w,s,e,n));
        CREATE INDEX IF NOT EXISTS coverage_west ON coverage(w,e);
        CREATE TABLE IF NOT EXISTS nodes(id INTEGER PRIMARY KEY,lat REAL,lon REAL,tags TEXT,stamp INTEGER);
        CREATE INDEX IF NOT EXISTS nodes_lat_lon ON nodes(lat,lon);
        CREATE TABLE IF NOT EXISTS ways(id INTEGER PRIMARY KEY,refs TEXT,tags TEXT,stamp INTEGER);
        CREATE TABLE IF NOT EXISTS way_nodes(way INTEGER,node INTEGER,PRIMARY KEY(way,node));
        CREATE INDEX IF NOT EXISTS way_nodes_node ON way_nodes(node,way);
        CREATE VIRTUAL TABLE IF NOT EXISTS way_bounds USING rtree(id,w,e,s,n);
        CREATE TABLE IF NOT EXISTS removed_ways(id INTEGER PRIMARY KEY,stamp INTEGER);
        CREATE TABLE IF NOT EXISTS removed_relations(id INTEGER PRIMARY KEY,stamp INTEGER);
        CREATE TABLE IF NOT EXISTS relations(id INTEGER PRIMARY KEY,xml TEXT,stamp INTEGER);
        CREATE TABLE IF NOT EXISTS relation_ways(relation INTEGER,way INTEGER,PRIMARY KEY(relation,way));
        """)
        import secrets
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO meta VALUES('identity',?)", (secrets.randbits(63),))
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('schema',1)")
        self.identity = self.db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()[0]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    @property
    def generation(self):
        return self.db.execute("SELECT value FROM meta WHERE key='generation'").fetchone()[0]

    def relevant_coverage(self, wanted):
        rows = {}
        for w, s, e, n in wanted:
            for row in self.db.execute('SELECT w,s,e,n,stamp,source FROM coverage WHERE w<? AND e>? AND s<? AND n>?', (e, w, n, s)):
                rows[row[:4] + (row[5],)] = row
        return sorted(rows.values(), key=lambda row: row[4], reverse=True)

    def missing(self, wanted):
        return missing_rectangles(wanted, [row[:4] for row in self.relevant_coverage(wanted)])

    def sync(self, wanted, progress=None, cancelled=None):
        with INDEX_LOCK:
            return self._sync(wanted, progress, cancelled)

    def _sync(self, wanted, progress=None, cancelled=None):
        """Catalogue cheaply; parse only new/changed files relevant to this route."""
        candidates = []
        for directory in ('Vakken', 'Regios'):
            for path in (self.folder / directory).glob('*.osm'):
                try:
                    b = bounds(path.stem.split(',')) if directory == 'Vakken' else xml_bounds(path)
                    if not b:
                        continue
                    if not any((b[0] < e and b[2] > w and (b[1] < n) and (b[3] > s) for w, s, e, n in wanted)):
                        continue
                    stat = path.stat()
                    relative = path.relative_to(self.folder).as_posix()
                    old = self.db.execute('SELECT mtime,size FROM sources WHERE path=?', (relative,)).fetchone()
                    if old == (stat.st_mtime_ns, stat.st_size):
                        continue
                    candidates.append((stat.st_mtime_ns, path, [b]))
                except (ValueError, OSError, ET.ParseError, KeyError):
                    continue
        for count, (_, path, boxes) in enumerate(sorted(candidates, key=lambda row: (row[0], str(row[1]))), 1):
            if cancelled and cancelled():
                raise ValueError('Uitlijnen gestopt.')
            try:
                self.ingest_files([(path, boxes)])
            except (ValueError, OSError, ET.ParseError, TypeError):
                continue
            if progress:
                progress(count, len(candidates))

    def ingest_files(self, items, legacy=False):
        """Publish all supplied files in one database transaction."""
        changed = False
        with INDEX_LOCK, self.db:
            for path, boxes in items:
                changed = self._ingest(Path(path), [bounds(b) for b in boxes], legacy) or changed
            if changed:
                self.db.execute("UPDATE meta SET value=value+1 WHERE key='generation'")

    def _ingest(self, path, boxes, legacy):
        """Prefer OSM snapshot time to copy time; older overlaps never win.

        Absence proves removal only if an old node was inside the refreshed
        box, matching Overpass selection. Tombstones prevent resurrection by
        older cached tiles. Shared node movements update every affected bbox.
        """
        stat = path.stat()
        if stat.st_size > MAX_BYTES:
            raise ValueError('Kaartbestand is te groot voor de lokale index.')
        raw = path.read_bytes()
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('Ongeldig kaartbestand.')
        digest = hashlib.sha256(raw).hexdigest()
        relative = path.resolve().relative_to(self.folder).as_posix()
        old = self.db.execute('SELECT digest FROM sources WHERE path=?', (relative,)).fetchone()
        if old and old[0] == digest:
            self.db.execute('UPDATE sources SET mtime=?,size=? WHERE path=?', (stat.st_mtime_ns, stat.st_size, relative))
            return False
        root = validate_osm(raw)
        stamp = stat.st_mtime_ns
        metadata = root.find('meta')
        if metadata is not None and metadata.get('osm_base'):
            try:
                stamp = int(datetime.fromisoformat(metadata.get('osm_base').replace('Z', '+00:00')).timestamp() * 1000000000.0)
            except ValueError:
                pass
        if legacy:
            overlaps = self.relevant_coverage(boxes)
            if overlaps:
                stamp = min(stamp, min((row[4] for row in overlaps)) - 1)
        ways = []
        present = set()
        for element in root.findall('way'):
            tags = {t.get('k'): t.get('v') for t in element.findall('tag')}
            if 'highway' not in tags:
                continue
            ident = int(element.get('id'))
            refs = [int(n.get('ref')) for n in element.findall('nd')]
            ways.append((ident, refs, tags))
            present.add(ident)
        node_elements = root.findall('node')
        present_nodes = {int(element.get('id')) for element in node_elements}
        if any((len(refs) < 2 or not set(refs) <= present_nodes for _, refs, _ in ways)):
            raise ValueError('Onvolledige weggegevens: wegpunten ontbreken.')
        absent = set()
        if not legacy:
            for w, s, e, n in boxes:
                absent.update((row[0] for row in self.db.execute('SELECT DISTINCT wn.way FROM way_nodes wn\n                    JOIN nodes nd ON nd.id=wn.node JOIN ways wy ON wy.id=wn.way\n                    WHERE nd.lon>=? AND nd.lon<=? AND nd.lat>=? AND nd.lat<=? AND wy.stamp<=?', (w, e, s, n, stamp))))
        node_rows = []
        moved = set()
        previous_nodes = {}
        for batch in chunks(present_nodes):
            marks = ','.join(('?' for _ in batch))
            previous_nodes.update(((row[0], row[1:]) for row in self.db.execute(f'SELECT id,lat,lon,stamp FROM nodes WHERE id IN ({marks})', batch)))
        for element in node_elements:
            ident = int(element.get('id'))
            lat = float(element.get('lat'))
            lon = float(element.get('lon'))
            if not math.isfinite(lat + lon) or not -90 <= lat <= 90 or (not -180 <= lon <= 180):
                raise ValueError('Ongeldige kaartpositie.')
            previous = previous_nodes.get(ident)
            if previous and previous[2] > stamp:
                continue
            if previous and previous[:2] != (lat, lon):
                moved.add(ident)
            tags = {t.get('k'): t.get('v') for t in element.findall('tag')}
            node_rows.append((ident, lat, lon, json.dumps(tags, separators=(',', ':')), stamp))
        self.db.executemany('INSERT INTO nodes VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET lat=excluded.lat,lon=excluded.lon,tags=excluded.tags,stamp=excluded.stamp WHERE excluded.stamp>=nodes.stamp', node_rows)
        touched = set()
        for ident, refs, tags in ways:
            removed = self.db.execute('SELECT stamp FROM removed_ways WHERE id=?', (ident,)).fetchone()
            previous = self.db.execute('SELECT stamp FROM ways WHERE id=?', (ident,)).fetchone()
            if removed and removed[0] > stamp or (previous and previous[0] > stamp):
                continue
            self.db.execute('INSERT OR REPLACE INTO ways VALUES(?,?,?,?)', (ident, json.dumps(refs), json.dumps(tags, separators=(',', ':')), stamp))
            self.db.execute('DELETE FROM removed_ways WHERE id=?', (ident,))
            self.db.execute('DELETE FROM way_nodes WHERE way=?', (ident,))
            self.db.executemany('INSERT OR IGNORE INTO way_nodes VALUES(?,?)', ((ident, node) for node in refs))
            touched.add(ident)
        for ident in absent - present:
            self.db.execute('INSERT INTO removed_ways VALUES(?,?) ON CONFLICT(id) DO UPDATE SET stamp=max(stamp,excluded.stamp)', (ident, stamp))
            self.db.execute('DELETE FROM ways WHERE id=? AND stamp<=?', (ident, stamp))
            self.db.execute('DELETE FROM way_nodes WHERE way=?', (ident,))
            self.db.execute('DELETE FROM way_bounds WHERE id=?', (ident,))
        for batch in chunks(moved):
            marks = ','.join(('?' for _ in batch))
            touched.update((row[0] for row in self.db.execute(f'SELECT DISTINCT way FROM way_nodes WHERE node IN ({marks})', batch)))
        for ident in touched:
            extent = self.db.execute('SELECT min(nd.lon),min(nd.lat),max(nd.lon),max(nd.lat) FROM nodes nd JOIN way_nodes wn ON wn.node=nd.id WHERE wn.way=?', (ident,)).fetchone()
            if extent[0] is not None:
                w, s, e, n = extent
                self.db.execute('INSERT OR REPLACE INTO way_bounds VALUES(?,?,?,?,?)', (ident, w, e, s, n))
        present_relations={int(element.get('id')) for element in root.findall('relation')}
        for batch in chunks(absent):
            marks=','.join('?' for _ in batch)
            stale={row[0] for row in self.db.execute(
                f'SELECT DISTINCT r.id FROM relations r JOIN relation_ways rw ON rw.relation=r.id WHERE rw.way IN ({marks}) AND r.stamp<=?',
                [*batch,stamp])}-present_relations
            for ident in stale:
                self.db.execute('INSERT INTO removed_relations VALUES(?,?) ON CONFLICT(id) DO UPDATE SET stamp=max(stamp,excluded.stamp)',(ident,stamp))
                self.db.execute('DELETE FROM relations WHERE id=?',(ident,))
                self.db.execute('DELETE FROM relation_ways WHERE relation=?',(ident,))
        for element in root.findall('relation'):
            if not any((t.get('k') == 'type' and t.get('v') == 'restriction' for t in element.findall('tag'))):
                continue
            ident = int(element.get('id'))
            previous = self.db.execute('SELECT stamp FROM relations WHERE id=?', (ident,)).fetchone()
            removed = self.db.execute('SELECT stamp FROM removed_relations WHERE id=?', (ident,)).fetchone()
            if (previous and previous[0] > stamp) or (removed and removed[0] > stamp):
                continue
            self.db.execute('DELETE FROM removed_relations WHERE id=?',(ident,))
            self.db.execute('INSERT OR REPLACE INTO relations VALUES(?,?,?)', (ident, ET.tostring(element, encoding='unicode'), stamp))
            self.db.execute('DELETE FROM relation_ways WHERE relation=?', (ident,))
            self.db.executemany('INSERT OR IGNORE INTO relation_ways VALUES(?,?)', ((ident, int(m.get('ref'))) for m in element.findall('member') if m.get('type') == 'way'))
        self.db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?)', (relative, stat.st_mtime_ns, stat.st_size, digest, stamp))
        self.db.execute('DELETE FROM coverage WHERE source=?', (relative,))
        self.db.executemany('INSERT INTO coverage VALUES(?,?,?,?,?,?)', ((relative, *box, stamp) for box in boxes))
        return True

    def read(self, wanted, query=None):
        """Return a RoadMap directly, avoiding reparsing region-sized XML files."""
        self.db.execute('BEGIN')
        try:
            return self._read(wanted, query)
        finally:
            self.db.rollback()

    def _read(self, wanted, query):
        if self.missing(wanted):
            return None
        from gpx_core import RoadMap, Point
        selected = {}
        for w, s, e, n in query or wanted:
            for row in self.db.execute('SELECT wy.id,wy.refs,wy.tags FROM ways wy JOIN way_bounds b ON b.id=wy.id WHERE b.w<=? AND b.e>=? AND b.s<=? AND b.n>=?', (e, w, n, s)):
                selected[row[0]] = row
        if not selected:
            return None
        ways = []
        ids = set()
        for ident, refs, tags in sorted(selected.values()):
            refs = json.loads(refs)
            ids.update(refs)
            ways.append((ident, refs, json.loads(tags)))
        nodes = {}
        node_tags = {}
        for batch in chunks(ids):
            marks = ','.join(('?' for _ in batch))
            for ident, lat, lon, tags in self.db.execute(f'SELECT id,lat,lon,tags FROM nodes WHERE id IN ({marks})', batch):
                nodes[ident] = Point(lat, lon)
                node_tags[ident] = json.loads(tags) if tags != '{}' else {}
        road = RoadMap.__new__(RoadMap)
        road.nodes, road.node_tags = (nodes, node_tags)
        valid = [(ident, refs, tags) for ident, refs, tags in ways if len(refs) > 1 and all((n in nodes for n in refs))]
        road.ways = [(refs, tags) for ident, refs, tags in valid]
        road._index_way_ids = [ident for ident, refs, tags in valid]
        if not road.ways:
            return None
        relations = set()
        for batch in chunks(selected):
            marks = ','.join(('?' for _ in batch))
            relations.update((row[0] for row in self.db.execute(f'SELECT DISTINCT relation FROM relation_ways WHERE way IN ({marks})', batch)))
        road.restrictions = len(relations)
        road._index_identity = self.identity
        road._index_generation = self.generation
        road._index_folder = str(self.folder)
        road._index_query = tuple(query or wanted)
        road._index_relations = [row[0] for ident in relations for row in self.db.execute('SELECT xml FROM relations WHERE id=?', (ident,))]
        coverage = self.relevant_coverage(wanted)
        remaining = list(wanted)
        used = []
        for row in coverage:
            reduced = missing_rectangles(remaining, [row[:4]])
            if reduced != remaining:
                used.append(row[4])
            remaining = reduced
            if not remaining:
                break
        road._index_stamp = min(used) if used else 0
        return road

    def statistics(self):
        return dict(ways=self.db.execute('SELECT count(*) FROM ways').fetchone()[0], nodes=self.db.execute('SELECT count(*) FROM nodes').fetchone()[0], areas=self.db.execute('SELECT count(*) FROM coverage').fetchone()[0], sources=self.db.execute('SELECT count(*) FROM sources').fetchone()[0])

def road_xml(road):
    root = ET.Element('osm', version='0.6', generator='RouteRefit local road index')
    for ident, p in road.nodes.items():
        node = ET.SubElement(root, 'node', id=str(ident), lat=str(p.lat), lon=str(p.lon))
        for k, v in road.node_tags.get(ident, {}).items():
            ET.SubElement(node, 'tag', k=k, v=v)
    for ident, (refs, tags) in zip(road._index_way_ids, road.ways):
        way = ET.SubElement(root, 'way', id=str(ident))
        for n in refs:
            ET.SubElement(way, 'nd', ref=str(n))
        for k, v in tags.items():
            ET.SubElement(way, 'tag', k=k, v=v)
    for item in getattr(road, '_index_relations', ()):
        root.append(ET.fromstring(item))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)
