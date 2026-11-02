# SPDX-License-Identifier: GPL-3.0-only
"""Small user-drawn areas; local names and no route, profile or account payloads."""
import math
import uuid


def polygon(points):
    """Validate a simple, bounded polygon before saving or sending anything."""
    points=[(float(x),float(y)) for x,y in points]
    if len(points)>1 and points[0]==points[-1]:points.pop()
    if not 3<=len(points)<=64 or len(set(points))!=len(points):
        raise ValueError('Teken een gebied met 3 tot 64 verschillende hoekpunten.')
    if any(not math.isfinite(x+y) or not -180<x<180 or not -80<y<80 for x,y in points):
        raise ValueError('Ongeldige gebiedsgrenzen.')
    ring=points+[points[0]]
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersect(a,b,c,d):
        # Collinear overlap and touching non-neighbours are invalid too.
        if max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0]):return False
        if max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1]):return False
        return orient(a,b,c)*orient(a,b,d)<=0 and orient(c,d,a)*orient(c,d,b)<=0
    edges=list(zip(ring,ring[1:]))
    for i,(a,b) in enumerate(edges):
        for j,(c,d) in enumerate(edges[i+1:],i+1):
            if j==i+1 or (i==0 and j==len(edges)-1):continue
            if intersect(a,b,c,d):raise ValueError('De gebiedsgrens mag zichzelf niet kruisen.')
    w,s,e,n=min(x for x,y in points),min(y for x,y in points),max(x for x,y in points),max(y for x,y in points)
    scale=111.195**2*math.cos(math.radians((s+n)/2))
    area=abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in edges))/2*scale
    if area<.01:raise ValueError('Het getekende gebied is te klein.')
    if (e-w)*(n-s)*scale>2500 or e-w>10 or n-s>10:
        raise ValueError('Kies een kleiner gebied: maximaal 2500 km² inclusief de omhullende rechthoek.')
    return ring,area


def definition(name,points):
    ring,area=polygon(points)
    name=str(name).strip()
    if not name or len(name)>64 or any(ord(c)<32 for c in name):
        raise ValueError('Geef het gebied een naam van maximaal 64 tekens.')
    return dict(id='eigen-'+uuid.uuid4().hex,name=name,parent='Eigen gebieden · SliceOSM',
                provider='sliceosm',polygon=[[False,ring]],area_km2=round(area,2))
