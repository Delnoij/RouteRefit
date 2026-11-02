# Testing RouteRefit

Use copies and keep original files separately. This beta is intended to reveal
practical problems. Passing automated tests does not guarantee every route or device.

## Local alignment and slow services

Open a route and align automatically. With partial saved coverage, a marked partial
proposal should appear first. The road download has its own status and stop button.
When roads arrive, updating the proposal becomes available; no proposal is replaced
automatically. Only accepting changes the editable route, and undo must restore it.

Cancelling the proposal or stopping the download interrupts the request. Changing
routes/settings or closing cancels the old request. A failure must not start another
countdown. Without local roads, the editor remains usable; explicitly update the
proposal after a successful download.

## Practical checks

1. Install or extract to a separate writable folder. Check version 0.5.15 Beta and
   that the download contains no personal route library or map cache.
2. Import GPX files from supported devices. Compare names, segments, points,
   elevations, timestamps and waypoints with the originals.
3. Check folders with valid, invalid and duplicate inputs, with and without subfolders.
4. Check elevation profiles and statistics for flat routes, missing elevations,
   disconnected segments, missing timestamps and calculated proposals.
5. Test all six interface languages, including menus, activity, timing, messages,
   photo forms and saving. A language change must preserve the chosen activity.
6. Test real KML, KMZ, FIT, TCX and GeoJSON files. Compare timezones, elevations,
   segment boundaries and course points. Sensor channels are not copied into GPX.
7. Test point/anchor editing, endpoints, photographed waypoints, accepting and
   cancelling repairs, undo, pauses and saving separately. Reopen exports in another app.
8. Test road downloads/refresh and offline operation. Failed refreshes must retain
   usable saved data. Test optional packages and explicit background opt-in separately.
9. Close or change language with unsaved work. Choosing to keep working must be respected.
10. Test on a separate Windows 11 PC without Python and at different display scales.
    This second-PC check remains outstanding before a stable release.

Report the application/Windows version, language, input format, steps, expected
result and actual result. Attach only a minimal anonymised example; never publish
private locations, photographs or complete route libraries.

## Automated checks

Run the commands in [README](README.md) and [RELEASING](RELEASING.md). The Windows
workflow runs unit tests and eight interface checks sequentially, using synthetic
data. It also checks installation, locked-file refusal, reinstallation, retained
user data, uninstallation and isolation from other installations' scheduled tasks.

`tests/ui_segment_join.py` checks via points, recalculation, reports, undo and reopening.
`tests/ui_road_index.py` checks persistent local indexing and offline proposal review.
`tests/ui_alignment_progress.py` checks elapsed time, progress, stopping and late results.
Each runs in six languages. See [validation](VALIDATIE.txt) for recorded results;
the release's exact revision and run are recorded in BUILD-INFO.json.
