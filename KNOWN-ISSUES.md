# Known limitations of 0.5.15 Beta

## Alignment and road downloads

- The first proposal may be partial. Complete alignment needs sufficient local road
  data. Downloads never replace a proposal automatically; missing sections remain
  unresolved. Without usable coverage, the existing route is retained.
- Faster initial proposals do not guarantee a particular completion time or a fully
  aligned route. Public road services can be slow or unavailable.
- Background enrichment after a local proposal allows 45 seconds per request and
  60 seconds in total. Other download paths allow 20/30 seconds. Local indexing and
  calculation take additional time. An exceptionally stalled system call may still
  finish internally; at most one network worker is retained for it.
- Failed requests are not automatically retried or subdivided. Retry explicitly
  later; server cooldowns are respected within the same application session.
- Planning is limited to 200 base areas and 400 network requests. Route length alone
  does not determine coverage or guarantee that a route fits these limits.
- Visible map images are separate from road data. They require network access
  unless already cached. Road packages do not bulk-download background map images.

## Route quality and access

Automatic changed-road recovery relaxes intermediate anchors within a local window
of at most 1,500 metres. Endpoints retain the chosen search radius. Connections use
OSM access, direction and topology. Geometric deviation in both directions is
limited to 150 metres; section length must remain between 50% and 180% of the old
section. Manual sections and segment boundaries are protected. Combined results
are checked again; rejected sections remain review issues. Accepted adaptations
are listed in the checks and can be undone. Major changes may still be rejected.

Travel direction is a candidate preference, not lane-level navigation. OSM road
centrelines do not establish a cyclist's lateral position. Cycling quality uses
available surface, width, smoothness and tracktype tags; missing tags do not prove
usability. Mountain biking has its own rough-surface preference. Driveways and
parking aisles are discouraged, but remain available for genuine destinations.

Activities use generic explicit OSM access and direction rules across Europe.
There is no complete database of implicit national rules, vehicle dimensions,
environmental zones, live closures or speed limits. Standard no/only turn relations
with a via node or sequence of via ways are supported; unusual or combined
conditional relations are not fully supported. Recognised conditional prohibitions
are applied without evaluating their time windows. Motor profiles conservatively
avoid unclear motor access on tracks and footpaths and may reject a legal connection.
There is no speed-pedelec profile. Motor time estimates do not model traffic or speed limits.

Reconstructed gaps may differ from the actual journey. Via points guide the proposal;
connection times include any unrecorded pause. Actual moving time cannot be recovered
from missing samples. Connections are limited to 50 km and 50 via points. Review
maps and real-world conditions; a successful calculation is not a terrain check.

## Packages and offline use

The local index is prepared once from saved OSM files. Manual XML region imports
are limited to 128 MB per file; the separate package manager also supports PBF.
The data date is the OSM snapshot date or, if unavailable, the file date. Cached
data does not guarantee current access rules.

Regional packages are optional. Without them, saved roads remain usable but
retrieving missing roads may take much longer. Border routes may need several
packages. Initial preparation can take minutes and needs extra disk space;
downloads are limited to 500 MB per package. Weekly updates normally run while
the app is open. Changed boundaries, more than 90 daily updates or excessive
changes require an explicit full download.

Compact storage is used for newly prepared packages. Existing packages remain
usable and are not silently rebuilt. Custom drawn areas use small full extracts
and manual refresh, not incremental regional feeds. SliceOSM is a volunteer
service and may be unavailable. Leave a margin around routes when drawing an area.

Continuing work after closing requires explicit opt-in and Windows Task Scheduler.
If Windows policy rejects registration, the option stays off and an error is shown.
Sleep, sign-out, shutdown or missing connectivity prevent work; interrupted jobs
need review. There is no global in-app switch for all network features.

## Formats, exports and timing

- Not every device format has been tested. Controlled fixtures cover known cases,
  but unusual variants may fail. The original imported file is retained separately.
- Export supports GPX, TCX courses and KML, but not FIT. KML needs at least two
  points per segment. TCX needs usable timestamps or a date/speed calculation;
  calculated walking/cycling times require complete elevations.
- Sensor channels, map styling and device-specific fields are not preserved in
  conversion. KMZ supports one KML; external resources, overlays and polygons are
  not route inputs. GeoJSON supports lines and points, not polygons.
- Isolated samples within an otherwise usable route are retained. A file containing
  only isolated points or waypoints is not an editable route.
- Elevation totals use unfiltered source elevations and are affected by noise.
  Missing elevations yield partial totals. Average speed includes pauses.
- The main start-time field uses UTC. The separate activity-export dialog uses
  the selected local date/time. GPX timestamps are normalised to UTC. Calculated
  timestamps remain estimates, not proof of a completed activity.
- Navigation buttons save a GPX and open official import pages; they do not upload
  through an API. You sign in, select the file and confirm with the service.
  Services may apply fees, terms and limits; Strava route planning may require a
  subscription. The recipient may recalculate the route. Turn instructions and
  offline navigation are provided by that service or device.
- Sports services are not generally suitable for car/motorcycle navigation; use
  a compatible navigator. No real account uploads have been tested. TCX/KML and
  compatibility with all navigation devices still need practical testing.

## Platform and signing

The Windows downloads are unsigned. SmartScreen or Smart App Control may warn
or block execution; publisher identity is not verified. The GitHub workflow builds
unsigned packages. SignPath acceptance and integration are not in place.

Windows 11 is the target platform. Linux, macOS, every display scale and large-font
configuration are not fully tested. Some Windows/XML/FIT errors may appear in the
library's original language; user content is not translated. The optional website
integration refers to marcodelnoij.nl; public downloads have an empty catalogue.
