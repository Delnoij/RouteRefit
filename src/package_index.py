# SPDX-License-Identifier: GPL-3.0-only
"""Stream regional PBFs and daily OSC diffs into a private, staged road index."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import os
# Native PBF decoding already runs in parallel. Reserve two logical processors
# and bound the queue/memory footprint even on very large workstations.
os.environ.setdefault('OSMIUM_POOL_THREADS',str(max(1,min(32,(os.cpu_count() or 2)-2))))
import time
import xml.etree.ElementTree as ET
import osmium
from road_index import RoadIndex
from package_resources import Resources


class PackageCancelled(ValueError):
    pass


def check(cancelled):
    if cancelled():raise PackageCancelled('Gebiedstaak gestopt. Het bestaande pakket blijft behouden.')


class Importer(osmium.SimpleHandler):
    def __init__(self,db,stamp,cancelled,progress,updating=False,resources=None):
        super().__init__()
        self.db,self.stamp,self.cancelled,self.progress=db,stamp,cancelled,progress
        self.updating=updating;self.nodes=[];self.count=0;self.last=0
        self.resources=resources
        self.compact=db.execute("SELECT value FROM meta WHERE key='package_schema'").fetchone()==(2,)
        self.table='package_nodes' if self.compact else 'nodes'
        self.insert=('INSERT OR REPLACE INTO package_nodes VALUES(?,?,?,?)' if self.compact
                     else 'INSERT OR REPLACE INTO nodes VALUES(?,?,?,?,?)')
        db.execute('CREATE TEMP TABLE IF NOT EXISTS touched(id INTEGER PRIMARY KEY)')

    def tick(self):
        self.count+=1
        if self.count%1000==0:
            check(self.cancelled)
            if self.resources:self.resources.cooperate()
            if time.monotonic()-self.last>.5:
                self.progress('Wegen lokaal voorbereiden…',self.count,0);self.last=time.monotonic()

    def flush(self):
        if self.nodes:
            self.db.executemany(self.insert,self.nodes)
            self.nodes.clear()

    def node(self,node):
        self.tick()
        if self.updating:
            self.db.execute('INSERT OR IGNORE INTO touched SELECT way FROM way_nodes WHERE node=?',(node.id,))
        if node.deleted:
            self.flush();self.db.execute('DELETE FROM '+self.table+' WHERE id=?',(node.id,));return
        node_tags=node.tags
        tags=json.dumps(dict(node_tags),separators=(',',':')) if len(node_tags) else None
        location=node.location
        if self.compact:
            # OSM's native integer coordinates are exact to 1e-7 degrees. Keep
            # every point for future diffs, without duplicating a timestamp and
            # empty tag object millions of times.
            self.nodes.append((node.id,location.y,location.x,tags))
        else:self.nodes.append((node.id,location.lat,location.lon,tags or '{}',self.stamp))
        if len(self.nodes)>=16000:self.flush()

    def way(self,way):
        self.tick();self.flush()
        if self.updating:
            self.db.execute('DELETE FROM ways WHERE id=?',(way.id,))
            self.db.execute('DELETE FROM way_nodes WHERE way=?',(way.id,))
            self.db.execute('DELETE FROM way_bounds WHERE id=?',(way.id,))
        if way.deleted or 'highway' not in way.tags:return
        refs=[n.ref for n in way.nodes]
        if len(refs)<2:return
        self.db.execute('INSERT OR REPLACE INTO ways VALUES(?,?,?,?)',
                        (way.id,json.dumps(refs),json.dumps(dict(way.tags),separators=(',',':')),self.stamp))
        self.db.executemany('INSERT OR IGNORE INTO way_nodes VALUES(?,?)',((way.id,n) for n in refs))
        if self.updating:self.db.execute('INSERT OR IGNORE INTO touched VALUES(?)',(way.id,))

    def relation(self,rel):
        self.tick()
        if self.updating:
            self.db.execute('DELETE FROM relations WHERE id=?',(rel.id,))
            self.db.execute('DELETE FROM relation_ways WHERE relation=?',(rel.id,))
        if rel.deleted or rel.tags.get('type')!='restriction':return
        element=ET.Element('relation',id=str(rel.id))
        types={'n':'node','w':'way','r':'relation'}
        for m in rel.members:ET.SubElement(element,'member',type=types[m.type],ref=str(m.ref),role=m.role)
        for t in rel.tags:ET.SubElement(element,'tag',k=t.k,v=t.v)
        self.db.execute('INSERT OR REPLACE INTO relations VALUES(?,?,?)',(rel.id,ET.tostring(element,encoding='unicode'),self.stamp))
        self.db.executemany('INSERT OR IGNORE INTO relation_ways VALUES(?,?)',((rel.id,m.ref) for m in rel.members if m.type=='w'))


def ingest(folder,path,stamp,cancelled,progress,updating=False):
    """Only operate on a staging database. Publishing is the caller's final step."""
    check(cancelled)
    if updating:
        # Do not let the general cache repair path turn a damaged package into
        # an empty-but-published incremental update.
        source=(Path(folder)/'Wegenindex/wegen.sqlite3').resolve()
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as verify:
            if verify.execute('PRAGMA quick_check').fetchone()!=('ok',):
                raise ValueError('Controle van het gebiedspakket mislukt.')
            if not verify.execute("SELECT value FROM meta WHERE key='schema'").fetchone():
                raise ValueError('Controle van het gebiedspakket mislukt.')
    with RoadIndex(folder) as index,Resources() as resources:
        db=index.db
        db.execute(f'PRAGMA cache_size=-{resources.cache_kib}')
        db.set_progress_handler(lambda: int(cancelled()),5000)
        with db:
            if not updating:
                db.execute('DROP TABLE nodes')
                db.execute('CREATE TABLE package_nodes(id INTEGER PRIMARY KEY,y INTEGER,x INTEGER,tags TEXT)')
                db.execute("CREATE VIEW nodes AS SELECT id,y/10000000.0 AS lat,x/10000000.0 AS lon,coalesce(tags,'{}') AS tags,0 AS stamp FROM package_nodes")
                db.execute("INSERT INTO meta VALUES('package_schema',2)")
                db.execute('DROP INDEX IF EXISTS way_nodes_node')
            handler=Importer(db,stamp,cancelled,progress,updating,resources)
            progress('Wegen lokaal voorbereiden…',0,0)
            if updating:
                reader=osmium.MergeInputReader();reader.add_file(str(path));reader.apply(handler)
            else:handler.apply_file(str(path),filters=[
                osmium.filter.KeyFilter('highway').enable_for(osmium.osm.WAY),
                osmium.filter.TagFilter(('type','restriction')).enable_for(osmium.osm.RELATION)])
            handler.flush();check(cancelled)
            progress('Zoekindex opbouwen…',0,0)
            db.execute('CREATE INDEX IF NOT EXISTS way_nodes_node ON way_nodes(node,way)')
            # All nodes are retained, including non-road nodes: a later diff may
            # turn an existing non-road way into a highway without repeating them.
            scope='JOIN touched t ON t.id=wn.way' if updating else ''
            table='package_nodes' if handler.compact else 'nodes'
            missing=db.execute(f'SELECT wn.way FROM way_nodes wn {scope} LEFT JOIN {table} n ON n.id=wn.node WHERE n.id IS NULL LIMIT 1').fetchone()
            if missing:raise ValueError('Het gebied bevat onvolledige wegen. Het bestaande pakket blijft behouden.')
            coordinates='min(n.x)/10000000.0,max(n.x)/10000000.0,min(n.y)/10000000.0,max(n.y)/10000000.0' if handler.compact else 'min(n.lon),max(n.lon),min(n.lat),max(n.lat)'
            db.execute(f'''INSERT OR REPLACE INTO way_bounds
                SELECT wn.way,{coordinates}
                FROM way_nodes wn {scope} JOIN {table} n ON n.id=wn.node GROUP BY wn.way''')
            db.execute('CREATE INDEX IF NOT EXISTS relation_ways_way ON relation_ways(way,relation)')
            db.execute("UPDATE meta SET value=value+1 WHERE key='generation'")
        check(cancelled);progress('Wegenindex controleren…',0,0)
        if db.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Controle van het gebiedspakket mislukt.')
        return index.statistics()
