# Privacy and network behaviour

## Installer and external services

The per-user installer displays a privacy summary before installation. It installs
the application, documentation, an uninstaller and a Start-menu shortcut. Desktop
shortcut and application launch are optional. It does not download maps, activate
background work, change GPX file associations or send telemetry. Personal data in
Mijn GPX, Kaarten and voorkeuren.json is not included, overwritten or deleted.
Uninstall removes only this installation's optional scheduled task and website
protocol registration, when they point to its executable. Data is retained.

Online features have ordinary service-side logging; RouteRefit does not promise
anonymous network access or control providers' retention. Provider information:

- OSM raster tiles: https://osmfoundation.org/wiki/Privacy_Policy
- Overpass API's operator and usage-policy link: https://overpass-api.de/ and
  https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/
- Geofabrik public downloads: https://www.geofabrik.de/geofabrik/imprint.html
- Optional SliceOSM areas: https://github.com/SliceOSM/.github/blob/main/PRIVACY.md

The map viewer automatically fetches missing visible raster tiles. There is not
yet an in-app global switch to disable every network feature; disconnecting the
network still permits local editing with available data. Package background work
and recurring updates have their own controls. A future signing review must assess
the installed privacy disclosure and network controls against the then-current
provider requirements; the project does not assert approval or full compliance.

## 0.5.11: optional regional packages and updates

The optional package manager downloads public PBF extracts, polygon boundaries,
checksums and replication state/daily changes from `https://download.geofabrik.de/`.
The bundled list of region names is local. No account, route upload, telemetry or
payment is required. The provider sees the selected region and ordinary network
information including the IP address. Other providers and arbitrary redirects are
rejected. Selecting several regions queues them sequentially; stored regions from
different countries can be combined locally for border routes.

Downloaded regions are checked weekly while RouteRefit is open, unless the user
disables this in the package manager. No regions are downloaded automatically
before the user has installed a package. A failed check is not automatically
attempted again for at least 24 hours. Manual checks remain available. There are
no retry countdowns. Already-current packages need only small metadata requests.
Changes are applied to a separate database and published only after validation.
Cancellation/failure retains the active snapshot; updates never alter an open GPX
or proposal. Full refresh after changed boundaries, >90 daily sequences or large
diffs requires the explicit Download again action. Initial downloads are capped
at 500 MB; individual differences at 20 MB and combined differences at 64 MB.

Packages, update preferences and derived route corridors live below the private
Kaarten folder. They must not be distributed with a public application release.
Copies of unchanged regional databases are staged for safe updates, requiring
temporary extra disk space. Raw PBF/diff files are removed after successful use.
The source PBF is streamed into a spatial database; a route reads only nearby
roads. Visible map tiles are separate and may still require online access.
Geofabrik details: https://download.geofabrik.de/technical.html

Routes, converted sources, edited GPX files, photos and control reports are processed and stored locally. There is no analytics, telemetry, automatic crash upload or route-conversion service. Names, file paths and GPS data can be present in the user's own local exports and reports.

The map viewer automatically requests visible raster tiles from `tile.openstreetmap.org`. Opening a route does not prefetch road data. Requesting alignment or a manual road download/refresh may request road-data bounding boxes from the public Overpass service at `overpass-api.de`. These requests reveal the approximate requested map area and ordinary connection information, such as the IP address, to the respective tile or Overpass service operator. The full GPX file and photos are not uploaded. OpenStreetMap's policy applies: https://osmfoundation.org/wiki/Privacy_Policy . Previously fetched tiles and road data are cached locally.

## Public releases start empty

Personal routes, originals, edits, photos, reports, preferences, map tiles, road downloads and local road-index databases belong only to the private test installation. Cached map areas can reveal places visited and must never be included in GitHub source or release downloads. The release route catalogue is `[]`; no personal data is needed to start the program.

`release_tools.py check` excludes private working folders and rejects map/database files, settings, and unreviewed route or media assets. Demonstrations and documentation assets are checked against `release-data-manifest.json`; adding a personal route to `examples` does not bypass the check. A changed demonstration or screenshot needs a deliberate content review and updated checksum. The manifest must never be regenerated from a used installation. The Windows folder and actual source/Windows ZIP members are checked again before release checksums are issued. Already tracked private/build files are rejected when checking a Git checkout; ignore rules alone are insufficient.

The known synthetic examples remain optional documentation assets. They are not the owner's recordings and do not populate the empty route catalogue. Documentation screenshots must show only these demonstrations. Future manual changes require visual review before updating their approved checksums.

Create the eventual GitHub repository from the checked source ZIP in a new folder, with a new Git history. Do not upload the private working folder, a used Windows installation or its Git history. These packaging checks are additional protection, not a general detector of personal information hidden in arbitrary source text.

The optional route-catalogue integration downloads GPX files from `marcodelnoij.nl` when a catalogue route is opened. Website and upload buttons launch the user's browser; publication is manual. No website credentials are stored by this app. The release catalogue is empty.

Watching Downloads is disabled by default. If enabled, new local GPX files can be opened automatically. File/folder inspection does not upload files. Photos are included in exports only after explicit selection/approval.

Only anonymized, minimal examples should be attached to public issue reports. Do not submit identity documents, route libraries, signing secrets or personal photographs to GitHub issues. Any future change to network behaviour must update this document.

Road downloads use one read-only Overpass endpoint, reuse completed local tiles and respect cooldowns. From 0.5.8, a failed request stops the download immediately: no automatic retry, countdown, host rotation or resource-failure subdivision. Foreground download paths use a 20-second request wait and a shared 30-second download budget, plus a maximum of 400 requests and 128 MB per operation. Local indexing and calculation take additional time. A later user-initiated attempt respects the server cooldown within the same program session. Completed cached areas can still be used without a new request. This public service is best-effort, may be unavailable and is unsuitable as the sole backend for a large public application. Before a wider release, evaluate hosted/self-managed road data. See https://dev.overpass-api.de/overpass-doc/en/preface/commons.html .

Foreground road requests declare a 15-second server execution timeout and a 64 MiB resource allowance. Earlier 0.5.5 resource-failure subdivision and retry countdowns were removed in 0.5.8. No alternate service hosts are used. The server timeout is a request setting; local preparation and calculation are additional to the bounded download wait.

0.5.6: service export creates a local GPX plus an export report. Navigation export omits timestamps, waypoints, photographs and source metadata. Strava activity export includes newly modeled timestamps from the user-selected date, local start time, transport and average speed. The report records that these are estimates. No automatic upload, account login or token storage is implemented. Import-help buttons open the browser only when clicked. Icons are bundled locally. Geographic positions remain present in exports.
## 0.5.7: performance changes

Performance improvements use local calculations and the existing public road
service. No new provider, route-upload service, advertising or telemetry is added.
Map requests disclose the requested area and connection information such as the
IP address, but do not send GPX files, timestamps, names or photographs. Bounded
downloads and reuse of completed areas reduce requests.

## 0.5.9: local proposal before background road downloads

Choosing Align automatically first computes using saved roads. If data is missing,
a separate download starts after the local result is ready. With no usable local
roads, the editor stays available while that same bounded download runs. Only
missing bounding boxes are requested from the existing Overpass endpoint; no new
provider, analytics, account, route-upload service or paid backend is introduced.
Opening a route alone still does not start a road download.

Stop download or cancelling the proposal cancels the pending request. Accepting
a partial proposal allows its background download to finish, but never applies new
roads automatically. Switching routes, changing settings or closing cancels the
old request. Completed tiles can remain locally cached. Update proposal only reads
saved data and does not start another network attempt; another explicit Align
automatically action can request still-missing areas later, respecting cooldowns.
Late responses never replace a proposal or route. Area/IP disclosure of online map
requests remains unchanged; this is privacy-conscious local processing, not anonymity.

## 0.5.10: bounded background wait and clearer errors

Only the separate background enrichment after a local proposal uses 45 seconds
per request, with a 60-second total download budget and a 25-second server
execution setting. Foreground limits remain 20/30 seconds. A local proposal never
waits for that background response. The endpoint, requested data, cache, resource
limit and single in-flight transport are unchanged. There are no automatic retries
or host rotations. Stop remains interruptible. Error explanations use categories
and durations; they do not display request URLs, coordinates, personal paths or
raw service bodies. No error telemetry or diagnostic upload was added.


## 0.5.12: custom areas and explicit background opt-in

Custom areas use https://slice.openstreetmap.us/ only after the user chooses
Download area via SliceOSM. The JSON request contains a constant name (none) and
the explicitly drawn polygon. It never contains the GPX, local area name, times,
photos or settings. The provider sees the IP and polygon; the polygon can be
retrieved using the extraction link. SliceOSM's privacy policy allows usage logs:
https://github.com/SliceOSM/.github/blob/main/PRIVACY.md . No tracking SDK, cookies,
account credentials, telemetry upload or paid service is introduced in RouteRefit.
The drawing map uses the existing OSM tile provider and cache for visible tiles.

Custom areas are refreshed manually as small full extracts, not with Geofabrik
diffs. A queued request is polled at most every five seconds for ten minutes;
there are no automatic repeated extraction requests. Stop or timeout keeps a
pending job identifier so a manual action can resume it within 23 hours.

Continue after closing is OFF by default. Only an explicit checkbox action creates
a Windows scheduled task for the current user (limited privileges; sign-in and
daily 09:00; no wake from sleep). It handles local area-job queues and due weekly
Geofabrik updates. It does not load personal routes or continue route calculations.
Disabling cancels pending/running background work and unregisters the task. It
needs an active Windows user session; no cloud processing account is involved.
Windows CPU/memory samples are only used locally to cooperate with other apps.
