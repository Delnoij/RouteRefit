# SPDX-License-Identifier: GPL-3.0-only
"""Use proven local coverage after a bounded download; never invent missing roads."""
from urllib.error import HTTPError, URLError
from xml.etree.ElementTree import ParseError
from road_index import RoadIndex, bounds, missing_rectangles
from road_provider import prepare_index, routing_query
from map_plan import plan_route_tiles
from road_download import DownloadBudget, RoadServiceUnavailable
from routing_runtime import checkpoint, RoutingCancelled

MISSING_ROADS = 'Weggegevens ontbreken voor dit stuk. De bestaande lijn, hoogtes en tijden zijn behouden; dit stuk is niet uitgelijnd.'
PARTIAL_NOTICE = 'Gedeeltelijk uitgelijnd: ontbrekende weggegevens. De ongewijzigde stukken blijven onopgelost.'
RETRY_NOTICE = 'Probeer later opnieuw Automatisch uitlijnen; alleen ontbrekende gebieden worden opgehaald. Je kunt ook OSM-weggegevens importeren via Kaart.'
LOCAL_NOTICE = 'Dit voorstel gebruikt opgeslagen wegen. Kies Voorstel aanvullen zodra nieuwe wegen beschikbaar zijn.'
NO_COVERAGE = 'Nog geen bruikbare weggegevens voor deze route. Je route, bewerkingen en instellingen zijn behouden. Probeer later opnieuw of importeer OSM-weggegevens via Kaart.'


class NoUsableRoads(RoadServiceUnavailable):
    pass


def run_local_alignment(folder, source, anchors, mode, style, radius, kept, private,
                        loaded, cancel, emit, matcher=None):
    """No network dependency: return an immutable proposal snapshot and missing-data flag."""
    from road_provider import cached_road
    from alignment_workflow import estimated_schedule
    from auto_alignment import automatic_alignment
    matcher=matcher or automatic_alignment
    emit('Opgeslagen wegen voorbereiden…')
    road=cached_road(folder,source,style,loaded,anchors,radius,emit,cancel.is_set)
    unavailable={}
    if road is None:
        try:
            road,unavailable=partial_road(folder,source,anchors,style,radius,cancel.is_set)
        except NoUsableRoads:
            if cancel.is_set():raise RoutingCancelled('Uitlijnen gestopt.')
            return None,True
    if cancel.is_set():raise RoutingCancelled('Uitlijnen gestopt.')
    emit('Weggegevens gereed. Route uitlijnen…')
    if unavailable:
        out,notes,mapped,issues=matcher(road,source,anchors,mode,radius,kept,private,
                                      unavailable_intervals=unavailable)
        return (out,mapped,issues,list(dict.fromkeys([PARTIAL_NOTICE,LOCAL_NOTICE,*notes])),None),True
    out,notes,mapped,issues=matcher(road,source,anchors,mode,radius,kept,private)
    return (estimated_schedule(source,out),mapped,issues,list(dict.fromkeys(notes)),road),False


def edge_covered(p, q, coverage):
    """Every part of an edge must lie in the union of downloaded rectangles."""
    spans=[]
    for w,s,e,n in coverage.candidates(p,q) if isinstance(coverage,CoverageIndex) else coverage:
        lo,hi=0.,1.
        for start,delta,lower,upper in ((p.lon,q.lon-p.lon,w,e),(p.lat,q.lat-p.lat,s,n)):
            if abs(delta)<1e-15:
                if not lower-1e-7 <= start <= upper+1e-7:
                    hi=-1;break
            else:
                a,b=(lower-1e-7-start)/delta,(upper+1e-7-start)/delta
                lo=max(lo,min(a,b));hi=min(hi,max(a,b))
        if lo<=hi:spans.append((lo,hi))
    end=0.
    for lo,hi in sorted(spans):
        if lo>end+1e-12:return False
        end=max(end,hi)
        if end>=1:return True
    return False


class CoverageIndex:
    """A spatial preselection; the exact union-of-rectangles check remains unchanged."""
    def __init__(self,rectangles):
        import math
        self.rectangles=list(rectangles)
        self.cells={};self.large=[]
        for i,(w,s,e,n) in enumerate(self.rectangles):
            x0,x1=math.floor((w-1e-7)/.02),math.floor((e+1e-7)/.02)
            y0,y1=math.floor((s-1e-7)/.02),math.floor((n+1e-7)/.02)
            if (x1-x0+1)*(y1-y0+1)>4096:
                self.large.append(i);continue
            for x in range(x0,x1+1):
                for y in range(y0,y1+1):self.cells.setdefault((x,y),[]).append(i)

    def candidates(self,p,q):
        import math
        x0,x1=math.floor(min(p.lon,q.lon)/.02),math.floor(max(p.lon,q.lon)/.02)
        y0,y1=math.floor(min(p.lat,q.lat)/.02),math.floor(max(p.lat,q.lat)/.02)
        if (x1-x0+1)*(y1-y0+1)>4096:return self.rectangles
        found=set(self.large)
        for x in range(x0,x1+1):
            for y in range(y0,y1+1):found.update(self.cells.get((x,y),()))
        return (self.rectangles[i] for i in sorted(found))


def restrict_to_coverage(road, coverage):
    # Drop unknown edges rather than connecting/clipping them into invented nodes.
    coverage=CoverageIndex(coverage)
    ways=[];selected_ids=[]
    from turn_policy import way_ids
    for wid,(refs,tags) in zip(way_ids(road),road.ways):
        checkpoint()
        run=[]
        for a,b in zip(refs,refs[1:]):
            if edge_covered(road.nodes[a],road.nodes[b],coverage):
                if not run:run=[a]
                run.append(b)
            elif run:
                ways.append((run,tags));selected_ids.append(wid);run=[]
        if run:ways.append((run,tags));selected_ids.append(wid)
    road.ways=ways
    road._index_way_ids=selected_ids


def partial_road(folder, source, anchors, style, radius, cancelled=None):
    wanted=[bounds(b) for b in plan_route_tiles(source)]
    query=routing_query(source, anchors, radius)
    available=[];unavailable={}
    with RoadIndex(folder) as index:
        prepare_index(index,source,wanted,query,cancelled=cancelled)
        coverage=[row[:4] for row in index.relevant_coverage(wanted)]
        for si,(row,controls) in enumerate(zip(source,anchors)):
            for left,right in zip(controls,controls[1:]):
                checkpoint()
                if cancelled and cancelled():raise RoutingCancelled('Uitlijnen gestopt.')
                boxes=[bounds(b) for b in plan_route_tiles([row[left:right+1]])]
                if missing_rectangles(boxes,coverage):
                    unavailable[(si,left,right)]=MISSING_ROADS
                else:
                    available.extend(boxes)
        if not available:
            raise NoUsableRoads(NO_COVERAGE)
        # Keep the index's all-or-nothing coverage guarantee. Only proven boxes
        # are requested; the full query preserves junction/path-search context.
        road=index.read(available,query)
        if road is None:raise NoUsableRoads(NO_COVERAGE)
        restrict_to_coverage(road,[row[:4] for row in index.relevant_coverage(query)])
        if not road.ways:raise NoUsableRoads(NO_COVERAGE)
        road.cycling_style=style
        road._partial_coverage=bool(unavailable)
        return road,unavailable


def run_alignment(folder, source, anchors, mode, style, radius, kept, private,
                  loaded, cancel, emit, download, matcher=None):
    from alignment_workflow import road_for_section, estimated_schedule
    from auto_alignment import automatic_alignment
    matcher=matcher or automatic_alignment
    budget=DownloadBudget.foreground(emit)
    unavailable={}
    try:
        road=road_for_section(folder,source,lambda rows:download(rows,emit,cancel,budget),
                              style,loaded,anchors,radius,emit,cancel.is_set)
    except (ValueError, HTTPError, URLError, ParseError):
        if cancel.is_set():raise RoutingCancelled('Uitlijnen gestopt.')
        emit('Wegendienst te traag of niet beschikbaar. Opgeslagen wegen gebruiken…')
        road,unavailable=partial_road(folder,source,anchors,style,radius,cancel.is_set)
    if cancel.is_set():raise RoutingCancelled('Uitlijnen gestopt.')
    if road is None:raise NoUsableRoads(NO_COVERAGE)
    emit('Weggegevens gereed. Route uitlijnen…')
    if unavailable:
        out,notes,mapped,issues=matcher(road,source,anchors,mode,radius,kept,private,
                                      unavailable_intervals=unavailable)
        # Interpolated times on known sections already retain source anchor times.
        # Global retiming would overwrite the preserved times on unknown sections.
        notes=[PARTIAL_NOTICE,RETRY_NOTICE,*notes]
        return out,mapped,issues,list(dict.fromkeys(notes)),None
    out,notes,mapped,issues=matcher(road,source,anchors,mode,radius,kept,private)
    return estimated_schedule(source,out),mapped,issues,list(dict.fromkeys(notes)),road
