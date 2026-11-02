# SPDX-License-Identifier: GPL-3.0-only
"""Bounded, content-checked caches for immutable road preparation and path searches."""
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
import hashlib
import math
import pickle
import threading
import weakref
from contextvars import ContextVar
from contextlib import contextmanager
from access_policy import access_permitted
from cycling_policy import cycling_cost, travel_directions, major_road
from gpx_core import allowed
from activity_policy import MOTOR_MODES, suitable, motor_cost, barrier_blocked, permission_keys
from turn_policy import TurnPolicy, way_ids
from routing_runtime import checkpoint


_locks=weakref.WeakKeyDictionary()
_registry_lock=threading.Lock()
_primary_preparation=ContextVar('primary_preparation', default=None)
_road_snapshot=ContextVar('road_snapshot', default=None)


@contextmanager
def verified_road_snapshot(road):
    """Hash unchanged road content once per operation, and verify before return.

    Any concurrent content change rejects the entire proposal; a later operation
    still checks all geometry/access/direction tags and invalidates stale caches.
    """
    signature=road_signature(road)
    style=getattr(road,"cycling_style","trekking")
    token=_road_snapshot.set((road,signature))
    try:
        yield
        checkpoint()
        if road_signature(road)!=signature or getattr(road,"cycling_style","trekking")!=style:
            raise ValueError('Weggegevens gewijzigd tijdens het rekenen; probeer opnieuw.')
    finally:
        _road_snapshot.reset(token)


@contextmanager
def retain_primary_preparation(road, mode, private, origin):
    """Keep the full-route graph while local recovery tries other origins.

    Still bounded to two graphs. Context-local so simultaneous tasks cannot
    overwrite one another's preference. Content signatures remain mandatory.
    """
    key=(mode,getattr(road,'cycling_style','trekking'),bool(private),origin.lat,origin.lon)
    token=_primary_preparation.set((road,key))
    try:
        yield
    finally:
        _primary_preparation.reset(token)


def cache_lock(owner):
    with _registry_lock:
        lock=_locks.get(owner)
        if lock is None:
            lock=threading.RLock()
            _locks[owner]=lock
        return lock


def road_signature(road):
    # Geometry and every tag are included: in-place access/direction changes and
    # diagnostic copies must never inherit a stale prepared graph.
    content = ([(n,p.lat,p.lon) for n,p in road.nodes.items()], road.ways, road.node_tags,
               way_ids(road),getattr(road,'_index_relations',()))
    return hashlib.blake2b(pickle.dumps(content, protocol=5),digest_size=20).digest()


@dataclass(eq=False)
class PreparedRoads:
    coords: dict
    edges: list
    tags: list
    grid: dict
    directions: list
    factors: list
    charges: dict
    major: list
    graph: dict
    major_pairs: dict
    edge_ways: list = field(default_factory=list)
    turns: object = None
    paths: OrderedDict = field(default_factory=OrderedDict)
    path_weight: int = 0
    stats: dict = field(default_factory=lambda:dict(searches=0,path_hits=0))

    def edge_factor(self,eid,u,v,length):
        factor=self.factors[eid]
        for n in (u,v):
            if n in self.charges:
                factor+=self.charges[n]/max(length,1)
        return factor

    def remember_path(self,key,value):
        with cache_lock(self):
            old=self.paths.pop(key,None)
            if old:self.path_weight-=old[-1]
            self.paths[key]=value
            self.path_weight+=value[-1]
            while len(self.paths)>16384 or self.path_weight>1_000_000:
                _,old=self.paths.popitem(last=False)
                self.path_weight-=old[-1]


def prepare_roads(road,mode,style,allow_private,origin):
    with cache_lock(road):
        return _prepare_roads(road,mode,style,allow_private,origin)


def _prepare_roads(road,mode,style,allow_private,origin):
    checkpoint()
    snapshot=_road_snapshot.get()
    signature=snapshot[1] if snapshot is not None and snapshot[0] is road else road_signature(road)
    if getattr(road,'_prepared_owner',lambda:None)() is not road or getattr(road,'_prepared_signature',None)!=signature:
        road._prepared_owner=weakref.ref(road)
        road._prepared_signature=signature
        road._prepared_roads=OrderedDict()
        road._preparation_stats=dict(builds=0,hits=0)
    key=mode,style,bool(allow_private),origin.lat,origin.lon
    cached=road._prepared_roads.get(key)
    if cached is not None:
        road._prepared_roads.move_to_end(key)
        road._preparation_stats['hits']+=1
        return cached
    scale=111195*math.cos(math.radians(origin.lat))
    coords={n:((p.lon-origin.lon)*scale,(p.lat-origin.lat)*111195) for n,p in road.nodes.items()}
    blocked=set();charges={}
    for n,tags in road.node_tags.items():
        permission=next((tags[key] for key in permission_keys(mode) if key in tags),None)
        if not access_permitted(tags,mode,allow_private):blocked.add(n)
        if barrier_blocked(tags,mode):blocked.add(n)
        if mode=='bike' and tags.get('barrier') in ('kissing_gate','stile','turnstile') and tags.get('bicycle') not in ('yes','designated','official','permissive'):blocked.add(n)
        if tags.get('barrier') in ('wall','fence','block','jersey_barrier') and permission not in ('yes','designated','permissive'):blocked.add(n)
        if mode=='bike' and tags.get('barrier') in ('gate','cycle_barrier','lift_gate','bump_gate','chain'):
            charges[n]=20 if tags.get('bicycle') in ('yes','designated','official','permissive') else 80
    edges=[];tags_all=[];grid={};directions=[];factors=[];major=[];edge_ways=[]
    for wid,(ids,tags) in zip(way_ids(road),road.ways):
        checkpoint()
        if not allowed(tags,mode,allow_private) or not suitable(tags,mode,style):continue
        forward,backward=travel_directions(tags,mode,allow_private)
        if not(forward or backward):continue
        direction='no' if forward and backward else 'yes' if forward else '-1'
        factor=cycling_cost(tags,style) if mode=='bike' else motor_cost(tags) if mode in MOTOR_MODES else 1.0
        is_major=mode=='bike' and major_road(tags)
        for a,b in zip(ids,ids[1:]):
            if a==b or a not in coords or b not in coords or a in blocked or b in blocked:continue
            eid=len(edges);edges.append((a,b,direction));tags_all.append(tags)
            edge_ways.append(wid)
            factors.append(factor);major.append(is_major);directions.append((forward,backward))
            ax,ay=coords[a];bx,by=coords[b]
            for gx in range(math.floor(min(ax,bx)/80)-1,math.floor(max(ax,bx)/80)+2):
                for gy in range(math.floor(min(ay,by)/80)-1,math.floor(max(ay,by)/80)+2):
                    grid.setdefault((gx,gy),[]).append(eid)
    result=PreparedRoads(coords,edges,tags_all,grid,directions,factors,charges,major,{}, {})
    result.edge_ways=edge_ways
    result.turns=TurnPolicy(road,mode)
    graph=defaultdict(list);major_pairs=defaultdict(set)
    for eid,(a,b,_) in enumerate(edges):
        length=math.dist(coords[a],coords[b]);factor=result.edge_factor(eid,a,b,length)
        forward,backward=directions[eid]
        for u,v in ((a,b),) if forward and not backward else ((b,a),) if backward and not forward else ((a,b),(b,a)):
            graph[u].append((v,length,factor,eid))
            if major[eid]:major_pairs[(u,v)].add(eid)
    result.graph={n:tuple(arcs) for n,arcs in graph.items()}
    result.major_pairs=dict(major_pairs)
    road._prepared_roads[key]=result
    road._preparation_stats['builds']+=1
    pinned=_primary_preparation.get()
    protected=pinned[1] if pinned is not None and pinned[0] is road else None
    while len(road._prepared_roads)>2:
        victim=next(k for k in road._prepared_roads if k != protected)
        del road._prepared_roads[victim]
    return result


def split_graph(prepared,splits,coords):
    """Overlay route projections; never modify the reusable base network."""
    from collections import ChainMap
    overridden={};extra=defaultdict(list)
    for eid,points in splits.items():
        a,b,_=prepared.edges[eid]
        chain=[(0,a)]+sorted(points)+[(1,b)]
        for (_,u),(_,v) in zip(chain,chain[1:]):
            length=math.dist(coords[u],coords[v]);factor=prepared.edge_factor(eid,u,v,length)
            if prepared.directions[eid][0]:extra[u].append((v,length,factor,eid))
            if prepared.directions[eid][1]:extra[v].append((u,length,factor,eid))
        for n in (a,b):extra.setdefault(n,[])
    for n,arcs in extra.items():
        unchanged=[arc for arc in prepared.graph.get(n,()) if arc[3] not in splits]
        overridden[n]=tuple(sorted(unchanged+arcs,key=lambda arc:arc[3]))
    busy={pair for pair,eids in prepared.major_pairs.items() if any(eid not in splits for eid in eids)}
    for n,arcs in extra.items():
        busy.update((n,v) for v,length,factor,eid in arcs if prepared.major[eid])
    return ChainMap(overridden,prepared.graph),busy


def recovery_endpoints_possible(road, segments, section, mode, radius, allow_private):
    """Reject impossible recovery endpoints before building another whole graph.

    The primary grid only selects a superset of edges. Final distances use the
    exact same projection as the local matcher, with the same allowed edges.
    No heading, access or radius rule is relaxed.
    """
    origin=segments[0][0]
    prepared=prepare_roads(road,mode,getattr(road,'cycling_style','trekking'),allow_private,origin)
    primary_scale=111195*math.cos(math.radians(origin.lat))
    local_origin=section[0]
    scale=111195*math.cos(math.radians(local_origin.lat))
    if abs(scale)<1e-6:
        return True  # Leave polar edge cases to the original matcher.
    reach=math.ceil(radius*max(1,abs(primary_scale/scale))/80)+1
    for point in (section[0],section[-1]):
        gx=math.floor((point.lon-origin.lon)*primary_scale/80)
        gy=math.floor((point.lat-origin.lat)*111195/80)
        nearby={eid for dx in range(-reach,reach+1) for dy in range(-reach,reach+1)
                for eid in prepared.grid.get((gx+dx,gy+dy),())}
        x=(point.lon-local_origin.lon)*scale
        y=(point.lat-local_origin.lat)*111195
        found=False
        for eid in nearby:
            a,b,_=prepared.edges[eid]
            p,q=road.nodes[a],road.nodes[b]
            ax,ay=(p.lon-local_origin.lon)*scale,(p.lat-local_origin.lat)*111195
            bx,by=(q.lon-local_origin.lon)*scale,(q.lat-local_origin.lat)*111195
            dx,dy=bx-ax,by-ay
            den=dx*dx+dy*dy
            if not den:continue
            fraction=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/den))
            if math.hypot(x-ax-fraction*dx,y-ay-fraction*dy)<=radius:
                found=True;break
        if not found:return False
    return True
