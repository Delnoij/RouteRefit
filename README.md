# RouteRefit

**A free, local Windows application for reviewing, repairing and editing routes.**

Version **0.5.15 Beta** supports Windows 11, 64-bit. Created and maintained by
**Marco Delnoij**, [@Delnoij](https://github.com/Delnoij).

**Available languages:** Dutch, English, German, French, Spanish and European Portuguese.
The interface and illustrated manuals are available in all six languages.

Review each proposed change before applying it to your editable route. This is
a beta release; please read the [known limitations](KNOWN-ISSUES.md).

## Download and get started

Download the installer from [GitHub Releases](https://github.com/Delnoij/RouteRefit/releases).
Choose **RouteRefit-0.5.15-beta-Setup.exe**. Python is not required.
The source-code downloads are intended for developers.

1. Run the installer, read the licence and privacy information, and choose a folder.
2. Open RouteRefit from the Windows Start menu and choose your interface language.
3. Import a route, then align it automatically or edit it manually. Review the
   result before accepting the proposal.
4. Open the manual from the Help menu. English and Dutch manuals are also separate
   downloads; all six manuals are included in the Windows packages.

For the portable version, extract the entire Windows ZIP and run
`RouteRefit-0.5.15-beta.exe`, keeping its `_internal` folder alongside it.

The downloads are **not digitally signed**. Windows may warn or block execution.
Do not disable Windows security. See [Windows signing](VERTROUWEN.md).

## Keep existing routes, maps and settings

RouteRefit stores user data beside the application. The installer defaults to
`%LOCALAPPDATA%\RouteRefit` for the current user and reuses that folder for updates.
The installed application has the stable name `RouteRefit.exe`. Separate portable
copies have separate data folders; one copy may request roads another copy already has.

When switching from a portable version, you can select its existing folder in the
installer. Data is not moved automatically between folders. Before updating, save
your work, close RouteRefit and stop background downloads. Back up the complete
`Mijn GPX` and `Kaarten` folders and, if present, `voorkeuren.json`. These on-disk
names remain the same in every interface language.

If you move to a different folder, copy your user data there and keep the old
installation until you have checked your routes, edits and settings. Disable
background work in the old copy first and explicitly enable it in the new copy
if wanted. Never include private data in a public download or repository.

Uninstall through Windows Settings. Personal files are retained. Only this
installation's optional scheduled task and website protocol registration are
removed, when they point to this installation. After reinstalling, switch wanted
background work off and on again. Setup does not change GPX file associations
or enable background work automatically.

## Features

- Import GPX, TCX, FIT, KML, KMZ and GeoJSON.
- Align routes automatically, then continue editing manually with anchors,
  individual points, waypoints, segment checks and undo.
- View elevation profiles, distances and statistics, and calculate a time schedule.
- Activities: walking, cycling, mountain biking, gravel cycling, driving and motorcycling.
- Use local roads first. Fetch missing roads separately in the background,
  with bounded waiting and no automatic repeated attempts.
- Download optional road packages, including several regions across national borders.
  Packages are not required, but fetching missing roads can take substantially
  longer without them. Preparing a large package can take several minutes.
- Update regional packages. Continuing after closing is a separate Windows option,
  disabled by default.
- Export navigation routes as GPX, TCX courses or KML. Compact Komoot, Garmin and
  Strava buttons save a GPX and open the service's import page; you complete the upload.
  The separate Strava activity export supports calculated timestamps. Calculated
  times remain estimates and do not establish that an activity was actually completed.

The six manuals use portrait A4 pages. Only reviewed synthetic demonstration data
is included in the public packages.

## Free and privacy-conscious

Route editing and calculation happen locally. RouteRefit has no telemetry and
requires no RouteRefit account or paid routing subscription. It does not automatically
upload personal route files, timestamps or photographs.

Online map and road requests disclose the requested area and ordinary connection
information, including your IP address, to the service provider. Visible map images
can be fetched automatically; there is no global in-app offline switch yet.
Local processing does not make internet access anonymous. Read the [privacy policy](PRIVACY.md).

The optional website catalogue refers to marcodelnoij.nl and is empty in public
downloads. Personal routes, downloaded maps and preferences are not included.
Exporting to an external service remains a user action.

## Build and contribute

Use Python 3.13.12 on Windows and the pinned, hash-checked dependencies:

```text
python -m pip install --require-hashes -r requirements-windows.lock
python release_tools.py check
python -m unittest discover -s tests -v
python build_windows.py
python release_tools.py package
./tools/install_inno.ps1
python build_installer.py --compiler build/inno/ISCC.exe
```

The [Windows workflow](https://github.com/Delnoij/RouteRefit/actions/workflows/windows.yml)
also checks the interface in six languages and tests installation, reinstallation,
uninstallation and preservation of synthetic user data. It creates review artifacts;
it does not automatically publish releases. Run unit and interface checks sequentially.
Packaging checks inspect the source and final archives for disallowed private data.

Manual sources and the generator are in `docs/manuals` and `tools/build_manuals.py`.
Current PDFs are included. See [testing](TESTEN.md), [contributing](CONTRIBUTING.md),
[dependencies](DEPENDENCIES.md) and the [release procedure](RELEASING.md).

## Code signing policy

This release is **unsigned and has not been accepted by SignPath Foundation**.
The [code signing policy](CODE-SIGNING-POLICY.md) describes responsibilities,
review, deliberate approval and privacy. Signing support will only be claimed
after actual acceptance and configuration.

## Licence and map attribution

**Copyright © 2026 Marco Delnoij.** The source code is released under
**GNU General Public License v3.0 only** (`GPL-3.0-only`); see [LICENSE](LICENSE).
Dependency licences are included in `THIRD-PARTY-NOTICES`.

Map data: **© [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)**,
available under the Open Database License (ODbL). Map data retains its own licence.
External service names and logos belong to their respective owners.
RouteRefit is not affiliated with those services.
