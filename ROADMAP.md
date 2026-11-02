# RouteRefit roadmap

## Available in 0.5.15 Beta

- Local Windows editor, six interface languages, OSM map, large-map view,
  elevation/statistics and manual import/folder checks.
- Automatic/manual alignment, anchors, local repairs, context-menu actions and undo.
- Review before acceptance, then continue editing the accepted route manually.
- Connect segments, move endpoints, adjust pauses/timing and add named waypoints
  with descriptions/photos. Save GPX and a review report.
- Walking, cycling, mountain biking, gravel cycling, driving and motorcycling.
  Access, direction and supported OSM turn relations are checked separately.
- Persistent local road index, downloads for missing areas, bounded waiting and
  local proposals before separate background requests.
- Multiple regions and custom drawn areas, compact preparation, regional updates
  and background work after explicit Windows opt-in.
- Processing adapts to competing Windows load; no fixed runtime or full use of
  every processor core is promised.
- GPX navigation exports for Komoot, Garmin, Strava and Wikiloc. Three compact logo
  buttons open import pages; the user completes uploads. File export also supports
  TCX courses and KML. Existing exports are not overwritten.
- Activity export with calculated timestamps, a calendar and time picker.
- Six portrait manuals, GPL-3.0-only licensing and OpenStreetMap attribution.

## Planned or incomplete

1. Shortest/fastest preferences alongside the current balanced road choice.
2. Least-climbing, scenic and quiet-route alternatives.
3. Research suitable, licensed heatmap data. No Garmin/Strava heatmap integration
   or guarantee of access currently exists.
4. Create a new route from an empty map with clicked points. A design exists;
   there is no active empty-map route planner yet.
5. Merge separate files and split them into separate files. Connecting segments
   within an open route is already available.
6. More complete national default rules and conditional access across Europe.
7. Automatic incremental refresh for custom drawn areas. These currently need
   manual full refresh; regional packages already support periodic differences.
8. Direct account uploads, broader device compatibility and practical verification
   of how receiving services handle calculated activity timestamps.
9. Integrated website uploads with review date/statistics. Manual exchange exists.
10. Further measurement of routing quality and speed. GraphHopper is a comparison
    point, not a required paid service or an established quality claim.

Automatic local recovery drafts and a dedicated MTB terrain-difficulty control
were proposed but are not implemented. Manually saving/reopening edits is available.
Speed-pedelec support has been dropped and is not a planned feature.

## Publication

The public project is [Delnoij/RouteRefit](https://github.com/Delnoij/RouteRefit).
The first release is an unsigned beta. A SignPath application is a later, separate
step after reviewed builds, practical testing and genuine public history.
Public packages must remain free of personal routes, maps and preferences.
Version 1.0 will follow sufficient practical testing.
