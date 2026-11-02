# SPDX-License-Identifier: GPL-3.0-only
"""OSM activity access hierarchy and physical suitability; no online dependencies."""
MOTOR_MODES={'motorcar','motorcycle'}
def permission_keys(mode):
    return {'walk':('foot','access'),'bike':('bicycle','vehicle','access'),
            'motorcar':('motorcar','motor_vehicle','vehicle','access'),
            'motorcycle':('motorcycle','motor_vehicle','vehicle','access')}[mode]

def explicit_permission(tags,mode):
    for key in permission_keys(mode)[:-1]:
        if key in tags:return str(tags[key]).lower() in ('yes','designated','official','permissive')
    return False

def suitable(tags,mode,style='trekking'):
    if mode in MOTOR_MODES:
        if tags.get('highway')=='steps' or tags.get('4wd_only')=='yes':return False
        if tags.get('smoothness') in ('very_bad','horrible','very_horrible','impassable'):return False
        if tags.get('surface') in ('mud','sand','grass','woodchips') or tags.get('tracktype') in ('grade3','grade4','grade5'):return False
    if mode=='bike' and style=='gravel':
        if tags.get('highway')=='steps' or tags.get('surface') in ('mud','sand','grass','woodchips'):return False
        if tags.get('smoothness') in ('very_bad','horrible','very_horrible','impassable') or tags.get('tracktype') in ('grade4','grade5'):return False
        try:
            if float(tags.get('mtb:scale','0'))>=2:return False
        except ValueError:pass
    return True

def motor_cost(tags):
    # RouteRefit follows a recorded line. These weights are preferences, not a
    # claimed legal speed or a fastest-route calculation.
    return {'motorway':1.,'motorway_link':1.15,'trunk':1.,'trunk_link':1.15,
            'primary':1.,'secondary':1.,'tertiary':1.1,'residential':1.2,
            'unclassified':1.2,'living_street':2.,'service':2.5,'track':4.}.get(tags.get('highway'),3.)

def motor_anchor_cost(tags,gap):
    return gap*gap/16+12*(motor_cost(tags)-1)

def barrier_blocked(tags,mode):
    if mode not in MOTOR_MODES:return False
    blocked={'bollard','block','bus_trap','sump_buster','cycle_barrier','stile','kissing_gate','turnstile','wall','fence','jersey_barrier'}
    return tags.get('barrier') in blocked and not explicit_permission(tags,mode)
