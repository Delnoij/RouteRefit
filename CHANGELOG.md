# Changelog

The entries below describe development versions. The first public GitHub release
is 0.5.15 Beta; earlier entries are not claims of public releases or digital signing.

## 0.5.15 Beta - first public packaging and export controls

- Per-user Windows installer with a stable application filename, privacy disclosure,
  optional shortcuts/launch and an uninstaller that retains personal data.
- Reviewed GitHub build process, installer tests, source provenance and checksums.
- English publication documentation. Copyright © 2026 Marco Delnoij; GitHub @Delnoij.
- Six portrait A4 manuals, each with 47 pages and 33 chapters, including installation
  and local GPX/TCX/KML export. English and Dutch manuals are separate downloads too.
- Export to replaces the navigation label. Smaller service buttons leave room for additions.
- File export supports GPX, TCX courses and KML. GPX/KML navigation exports omit times;
  TCX uses existing or calculated route times. Exports are local and do not overwrite files.
- Private-road controls are easier to find in route settings, with a shortcut from
  activity settings. The saved allow_private option and access policy are unchanged.

## 0.5.14 Beta - activities, local performance and navigation exports

- Activity replaces transport: walking, cycling, MTB, gravel, car and motorcycle.
  Speed pedelecs are excluded. Existing route settings remain readable.
- Separate access hierarchies, directions and preferences for motor activities;
  gravel avoids very rough trails. Generic OSM rules are not a complete national rulebook.
- Standard turn relations with via nodes/ways, activity exceptions and arrival
  direction across anchors. Not every conditional relation is supported.
- Faster spatial coverage selection and turn checks limited to reachable junctions.
- Compact Komoot, Garmin and Strava buttons save a navigation GPX and open import pages.
  Users choose and upload the file themselves. Activity exports with estimated times remain.

## 0.5.13 Beta - continue editing after acceptance

- Accepted alignment proposals open with editable anchors and an explicit anchor mode.
- Timing calculations preserve manual geometry and do not implicitly realign or download roads.
- Editing mode is retained after timing proposals and saved in the review report.
- Undo, review issues and independent road downloads remain available. Downloads
  never apply themselves to an accepted route.

## 0.5.12 Beta - custom areas, preparation and optional background work

- Draw rectangles/polygons across borders and give them a local name.
- Optional SliceOSM extracts with disclosure, bounded waiting, a single extraction
  request and manual resumption of that request.
- Compact exact coordinates, native filters and parallel PBF preparation retain
  points, tags and turn relations needed for later updates.
- Separate downloading, local processing and validation phases.
- Background work after closing is off by default. Explicit opt-in creates a
  current-user Windows task at sign-in and daily at 09:00. Disabling removes it.
- Lower priority and extra pauses under competing load; bounded memory use.
  Custom areas are refreshed manually. Manuals updated in all six languages.

## 0.5.11 Beta - optional regional road packages

- Free Geofabrik extracts, multiple regions/countries and combined border coverage.
- Streaming preparation, a spatial road index and weekly incremental updates.
  Cancellation or failure retains the active package and routes.
- Package/update chapters in six manuals. About identifies Marco Delnoij,
  GPL-3.0-only (2026) and OpenStreetMap/ODbL attribution.

## 0.5.10 Beta - bounded background enrichment

- Separate requests after local proposals allow 45 seconds per request, 60 seconds
  overall and a 25-second server execution setting. Foreground limits stay shorter.
- Elapsed time without repeated countdowns or automatic retries.
- Clear error categories without request URLs, coordinates, personal paths or raw
  service responses. Explicit enrichment, cancellation and data preservation remain.

## 0.5.9 Beta - local proposals first

- Calculate with usable saved roads before separately retrieving missing areas.
- The first proposal does not wait for downloads. Editing remains available.
- Only explicit proposal updates incorporate newly saved roads; stale responses
  never replace a route. Cancellation and changing routes/settings stop old requests.

## 0.5.8 Beta - stop after the first road-service failure

- Removed automatic retries, repeated countdowns, host rotation and resource-failure
  subdivision. Completed areas remain cached; users may retry missing areas later.
- Download stop and late-response handling retain the route and existing proposal.

## 0.5.7 Beta - faster calculation and bounded waiting

- Reused prepared local road data and bounded road downloads with explicit stopping.
- No new provider, paid backend, route upload or telemetry. Existing source files
  and manual work remain separate from proposals.

## 0.5.6 Beta - exports, calendar and progress

- Service export helpers, local navigation files and activity export with a calendar,
  time picker, average speed and activity-dependent estimated timestamps.
- Calculated times remain identifiable as estimates; no automatic account upload.

## 0.5.5 Beta - six languages and visible progress

- Added Spanish and European Portuguese; six illustrated manuals.
- Visible phase, animated progress, elapsed time and a stop action during alignment.
- Lower memory use and clearer service failures; completed map areas remain usable.
- Local review reports no longer count as invalid GeoJSON in folder checks.
- Prepared a future route-creation design without exposing empty planning controls.
  Older retry behaviour in this version was superseded by 0.5.8.

## 0.5.4 Beta - persistent local road index

- Reuse saved road data after restarting and for changed routes; request only missing areas.
- Read needed roads without reparsing complete regions. Bounded region imports retain
  usable coverage; unbounded imports do not falsely claim complete coverage.
- Refreshes handle changed access and removed roads without older overlaps replacing newer data.
- Public-package checks cover source, application folders, archives and approved examples.

## 0.5.3 Beta - alignment performance

- Reuse road networks and activity costs with map-change checks, one alignment pass
  and bounded path caches. Road preferences and external services remain unchanged.
- Comparison against the frozen 0.5.2 engine produced the same results for 80 variants
  and the selected TCX/FIT examples. Recorded baseline: 249 unit tests.

## 0.5.2 Beta - direct actions and independent settings

- Open routes without a preliminary road download; direct automatic/manual actions.
- Reuse local areas and replace intermediate geometry between remaining anchors.
- Separate activity, route preference and timing settings; migrate existing reports.
- Changing pace does not alter road access. Changing activity requires fresh review.
- Review geometry/timing together before acceptance; cancellation and undo retain
  editable data and the estimated-time status. Recorded unit-test baselines: 226, then 237.

## 0.5.1 Beta - access review

- Missing explicit walking/cycling permission does not automatically prohibit ordinary roads.
- Apply bicycle > vehicle > access and foot > access hierarchies, including road nodes.
- Review only demonstrable access issues after a warning, retaining geometry,
  elevations and times. Persist reviews; geometry/settings/map changes require review again.
- Recorded baseline: 218 unit tests and three desktop checks in four languages.

## 0.5.0 Beta - RouteRefit name and interface

- Continued from GPX-werkbank 0.7.1 without replacing the routing engine.
- Centralised version/name metadata, route-first layout, grouped editing controls,
  wrapping toolbars, additional actions and retained shortcuts.
- Fixed tab translation and statistics text; four illustrated manuals.
- Recorded baseline: 207 regression tests and desktop checks in four languages.

## Earlier internal versions, before the RouteRefit name

- **0.7.1:** segment connections with editable via points; joined adjacent TCX lap
  boundaries and stationary FIT timer stops; retained originals and documented
  reconstructed geometry/times. Removed obsolete routing code and an unused codec.
- **0.9.5:** arrival direction at cycling anchors, U-turn preferences, roundabout
  direction and independent two-way cycle paths; five added regression tests.
- **0.9.4:** surface/width/smoothness/tracktype preferences, conservative barriers,
  driveway/parking penalties and a separate MTB preference; eight added tests.
- **0.9.3:** recorded direction for parallel cycle paths, protected recorded loops,
  local recovery of unintended loops and visible direction arrows; six added tests.
- **0.9.2:** appropriate cycleway preferences, explicit access/direction, real OSM
  topology and activity recognition. Retained data on failed refresh. Its retry
  behaviour was later removed in 0.5.8.
- **0.9.1:** route-corridor downloads, background import, reused elevation analysis,
  duplicate KML detection, GPL-3.0-only, pinned dependencies and build preparation.
- **0.9.0:** initial local Windows beta with menus, large map, manual import,
  folder checking, elevation/statistics, four languages and additional input formats.

Changed-road recovery uses bounded local searches and explicit review; see
KNOWN-ISSUES.md. Merging/splitting separate files remains future work.
