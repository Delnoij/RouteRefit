# SPDX-License-Identifier: GPL-3.0-only
"""OSM turn restrictions, retaining arrival context across user control points."""
from collections import defaultdict
import heapq,itertools,math,re,xml.etree.ElementTree as ET
from activity_policy import permission_keys
from routing_runtime import checkpoint

def way_ids(road):
    known=getattr(road,'_index_way_ids',())
    return [known[i] if i<len(known) else -i-1 for i in range(len(road.ways))]

class TurnPolicy:
    def __init__(self,road,mode):
        self.nodes=defaultdict(list);self.entries=defaultdict(list);self.via=[]
        self.conditional=False
        hierarchy=permission_keys(mode)[:-1]
        way_nodes=defaultdict(set)
        for wid,(refs,tags) in zip(way_ids(road),road.ways):way_nodes[wid].update(refs)
        for raw in getattr(road,'_index_relations',()):
            element=ET.fromstring(raw)
            tags={t.get('k'):t.get('v','') for t in element.findall('tag')}
            if tags.get('type')!='restriction':continue
            if {value.strip() for value in tags.get('except','').replace(',',';').split(';')} & set(hierarchy):continue
            base=next(('restriction:'+key for key in hierarchy if 'restriction:'+key in tags or 'restriction:'+key+':conditional' in tags),None)
            if base is None:
                if mode=='walk':continue
                base='restriction'
            kinds=[]
            for key in (base,base+':conditional'):
                for clause in re.split(r';\s*(?=(?:no|only)_)',tags.get(key,'')):
                    kind=clause.split('@',1)[0].strip()
                    if kind.startswith(('no_','only_')):
                        kinds.append(kind);self.conditional |= ':conditional' in key
            if not kinds:continue
            members=[(m.get('role'),m.get('type'),int(m.get('ref'))) for m in element.findall('member')]
            frm={ref for role,typ,ref in members if role=='from' and typ=='way'}
            to={ref for role,typ,ref in members if role=='to' and typ=='way'}
            via_nodes=[ref for role,typ,ref in members if role=='via' and typ=='node']
            via_ways=[ref for role,typ,ref in members if role=='via' and typ=='way']
            if not frm or not to:continue
            if len(via_nodes)==1 and not via_ways:
                self.nodes[via_nodes[0]].extend((kind,frm,to) for kind in kinds)
            elif via_ways and not via_nodes:
                for f in sorted(frm):
                    for t in sorted(to):
                        sequence=(f,*via_ways,t)
                        junctions=tuple(way_nodes.get(a,set()) & way_nodes.get(b,set()) for a,b in zip(sequence,sequence[1:]))
                        if not junctions[0]:continue
                        for kind in kinds:
                            index=len(self.via)
                            self.via.append((kind,sequence,junctions))
                            for node in junctions[0]:self.entries[(f,node)].append(index)

    def __bool__(self):return bool(self.nodes or self.via)

    def reachable(self,coords,start,end,limit,arrival):
        if arrival and arrival[2]:return True
        if not hasattr(self,'locations'):
            nodes=set(self.nodes)|{node for way,node in self.entries}
            self.locations=tuple(coords[n] for n in nodes if n in coords)
        a,b=coords[start],coords[end]
        return any(math.dist(a,p)+math.dist(p,b)<=limit+1e-6 for p in self.locations)

    def step(self,arrival,u,v,eid,edge_ways):
        previous,prior,active=arrival or (-1,-1,())
        current_way=edge_ways[eid]
        previous_way=edge_ways[previous] if previous>=0 else None
        for kind,frm,to in self.nodes.get(u,()):
            if previous_way not in frm:continue
            matches=current_way in to
            if frm==to and kind in ('no_u_turn','only_u_turn'):matches=matches and v==prior
            if frm==to and kind=='no_straight_on':matches=matches and v!=prior
            if kind.startswith('no_') and matches or kind.startswith('only_') and not matches:return None
        pending=[]
        for index,position in active:
            kind,sequence,junctions=self.via[index]
            if current_way==sequence[position]:
                pending.append((index,position));continue
            matches=current_way==sequence[position+1] and u in junctions[position]
            if position==len(sequence)-2:
                if kind.startswith('no_') and matches or kind.startswith('only_') and not matches:return None
            elif matches:pending.append((index,position+1))
            elif kind.startswith('only_'):return None
        for index in self.entries.get((previous_way,u),()):
            kind,sequence,junctions=self.via[index]
            if current_way==sequence[1]:pending.append((index,1))
            elif kind.startswith('only_'):return None
        return eid,u,tuple(sorted(set(pending)))

def restricted_path(graph,edge_ways,policy,start,end,limit,arrival=None):
    """Dijkstra over arrival states, including restrictions spanning several ways."""
    arrival=arrival or (-1,-1,())
    initial=(start,arrival);counter=itertools.count()
    todo=[(0,next(counter),initial)];cost={initial:0.};physical={initial:0.};previous={};visits=0
    while todo:
        weight,_,state=heapq.heappop(todo)
        if weight!=cost[state]:continue
        u,incoming=state;length=physical[state]
        if u==end:
            states=[state]
            while states[-1]!=initial:states.append(previous[states[-1]])
            return [s[0] for s in reversed(states)],length,weight,incoming
        visits+=1
        if visits%256==0:checkpoint()
        if visits>60000:break
        for v,d,factor,eid in graph.get(u,()):
            metres=length+d
            if metres>limit:continue
            following=policy.step(incoming,u,v,eid,edge_ways)
            if following is None:continue
            # A gratuitous about-face must not become a cheap workaround for a
            # forbidden turn. Genuine out-and-back routes remain possible.
            turn_cost=240 if incoming[1]==v else 0
            target=v,following;value=weight+d*factor+turn_cost
            if value<cost.get(target,float('inf')):
                cost[target]=value;physical[target]=metres;previous[target]=state
                heapq.heappush(todo,(value,next(counter),target))
    return None
