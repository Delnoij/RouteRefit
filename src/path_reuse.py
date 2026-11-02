# SPDX-License-Identifier: GPL-3.0-only
"""Reuse unchanged searches while checking their explored graph dependencies."""
from prepared_roads import cache_lock


class PathReuse:
    def __init__(self,prepared,splits):
        self.prepared=prepared
        self.splits=splits
        self.signatures={eid:tuple(f for f,n in sorted(points)) for eid,points in splits.items()}
        self.virtual={}
        for eid,points in splits.items():
            for ordinal,(fraction,node) in enumerate(sorted(points)):
                self.virtual[node]=('v',eid,fraction,ordinal)
        self.current={key:n for n,key in self.virtual.items()}
        # Temporary, negative OSM ids can overlap the matcher's virtual ids.
        self.enabled=all(n>=0 for n in prepared.coords)

    def canonical(self,node):
        return self.virtual.get(node,('n',node))

    def key(self,start,end,limit):
        return self.canonical(start),self.canonical(end),round(limit,3)

    def virtual_order(self,eids):
        nodes=[n for eid in eids for f,n in self.splits.get(eid,())]
        return tuple(self.virtual[n] for n in sorted(nodes))

    def lookup(self,start,end,limit):
        if not self.enabled:return False,None
        key=self.key(start,end,limit)
        with cache_lock(self.prepared):
            value=self.prepared.paths.get(key)
        if value is None:return False,None
        answer,dependencies,order,lower,upper,size=value
        # The interval records every accepted/rejected distance cutoff in the
        # original search, so tiny prefix-length rounding changes remain safe.
        if not lower<=limit<upper:return False,None
        if any(self.signatures.get(eid,())!=signature for eid,signature in dependencies):return False,None
        if self.virtual_order(eid for eid,signature in dependencies)!=order:return False,None
        if answer is None:
            result=None
        else:
            path,length,cost=answer
            try:result=([node[1] if node[0]=='n' else self.current[node] for node in path],length,cost)
            except KeyError:return False,None
        with cache_lock(self.prepared):
            if key in self.prepared.paths:self.prepared.paths.move_to_end(key)
            self.prepared.stats['path_hits']+=1
        return True,result

    def store(self,start,end,limit,answer,eids,lower,upper):
        if not self.enabled:return
        dependencies=tuple((eid,self.signatures.get(eid,())) for eid in sorted(eids))
        path=None if answer is None else (tuple(self.canonical(n) for n in answer[0]),answer[1],answer[2])
        size=len(dependencies)+(len(path[0]) if path else 0)
        if size>100000:return
        value=path,dependencies,self.virtual_order(eids),lower,upper,size
        self.prepared.remember_path(self.key(start,end,limit),value)
