# SPDX-License-Identifier: GPL-3.0-only
"""Conservative coverage for published .poly extracts, including islands/holes."""
import math


def parse_poly(text):
    lines=iter(text.strip().splitlines());next(lines)
    rings=[]
    for label in lines:
        if label.strip()=='END':break
        points=[]
        for line in lines:
            if line.strip()=='END':break
            x,y=map(float,line.split())
            if not math.isfinite(x+y) or not -180<=x<=180 or not -90<=y<=90:
                raise ValueError('Ongeldige gebiedsgrenzen.')
            points.append((x,y))
        if len(points)<4 or points[0]!=points[-1]:
            raise ValueError('Onvolledige gebiedsgrenzen.')
        rings.append((label.strip().startswith('!'),points))
    if not rings or not any(not hole for hole,_ in rings):
        raise ValueError('Gebiedsgrenzen ontbreken.')
    return rings


def inside(point,ring):
    x,y=point;result=False
    for (a,b),(c,d) in zip(ring,ring[1:]):
        if (b>y)!=(d>y) and x<(c-a)*(y-b)/(d-b)+a:result=not result
    return result


def segment_hits_box(a,b,box):
    lo,hi=0.,1.
    for start,end,lower,upper in ((a[0],b[0],box[0],box[2]),(a[1],b[1],box[1],box[3])):
        delta=end-start
        if abs(delta)<1e-15:
            if start<lower or start>upper:return False
        else:
            p,q=(lower-start)/delta,(upper-start)/delta
            lo=max(lo,min(p,q));hi=min(hi,max(p,q))
        if lo>hi:return False
    return True


def classify(box,rings):
    """1 fully covered, -1 outside, 0 crosses a boundary (never claim coverage)."""
    for _,ring in rings:
        if any(segment_hits_box(a,b,box) for a,b in zip(ring,ring[1:])):return 0
    point=((box[0]+box[2])/2,(box[1]+box[3])/2)
    return 1 if any(inside(point,r) for h,r in rings if not h) and not any(inside(point,r) for h,r in rings if h) else -1


def covered_boxes(boxes,rings,depth=5):
    result=[]
    def visit(box,level):
        state=classify(box,rings)
        if state==1:result.append(box)
        elif state==0 and level:
            w,s,e,n=box;x=(w+e)/2;y=(s+n)/2
            for part in ((w,s,x,y),(x,s,e,y),(w,y,x,n),(x,y,e,n)):visit(part,level-1)
    for box in boxes:visit(box,depth)
    return result
