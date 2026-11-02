# Design: creating new routes

Status: design only, not an available application feature. Empty-map route planning
is a separate future step; the existing alignment workflow must remain stable.

## Interaction

A future New route action would create an empty design. Users select an activity
and route preference, then click a start, via points and an end. A proposal shows
distance, estimated time and available ascent before acceptance. Control points
remain draggable; removing one replaces the connection between its surviving
neighbours. Reuse undo, cancellation, waypoints, photos and GPX export.

## Reusable components

- Local road indexing and missing coverage in road_provider.py.
- Prepared activity networks and access/direction rules in prepared_roads.py.
- Activity settings separate from timing; validate each supported activity.
- Proposal review, distance/elevation summaries, map view and editing history.
- GPX/review reports, estimated-time attribution and explicit photo selection.

## Data model

A recorded route retains an immutable source. A design needs explicit planned
provenance, control points and a separate proposal. Do not invent an original GPS
recording. Measured times, actual distance travelled and recorded pauses remain
unknown. Any schedule is an estimate based on speed and an optional start time;
exports and reports must preserve that distinction.

Alignment follows an existing shape with bounded deviation. Planning searches
between newly chosen points. Keep these separate operations above the same local
road network so planning does not silently change repair behaviour. Report missing
local coverage and expand it in a controlled way.

## Decisions and tests

1. Project endpoints onto reachable roads and show a reviewable proposal.
2. Expand coverage for detours while retaining time/download limits.
3. Check every activity's access, direction, turn restrictions and parallel paths.
4. Reopen designs without presenting them as recorded activities.
5. Test point movement/removal, explicit acceptance, cancellation, undo and estimated times.
6. Connect elevation sources separately. Missing ascent remains unknown, not invented.

Do not expose non-working planning buttons. Merging/splitting separate files are
separate future features. SignPath application and signing are separate release decisions.
