# RouteRefit 0.5.15 Beta

RouteRefit is a free, local Windows application by **Marco Delnoij**
([@Delnoij](https://github.com/Delnoij)) for reviewing, repairing and editing routes.

**Available in Dutch, English, German, French, Spanish and European Portuguese.**
The interface and illustrated portrait manuals support all six languages.

## Downloads

- **Setup.exe**: recommended for Windows 11 x64. Installs for the current user
  with a Start-menu shortcut. Python is not required.
- **Windows.zip**: portable version. Extract the entire folder before running it.
- **broncode.zip**: reviewed source code, build scripts and tests.
- **handleiding-EN.pdf / handleiding-NL.pdf**: English and Dutch manuals.
  All six manuals are included in the application downloads.
- **BUILD-INFO.json, INSTALLER-INFO.json and SHA256SUMS.txt**: build provenance
  and checksums for verifying the downloads.

## Features

- Align using local roads first; retrieve missing roads separately and review proposals.
- Optional road packages, multiple regions and continued manual editing.
- Walking, cycling, mountain biking, gravel cycling, driving and motorcycling.
- GPX, TCX and KML export, with import helpers for Komoot, Garmin and Strava.
- Installation, updates and uninstallation designed to retain local user data.

## Existing users

Save your work, close RouteRefit and stop road downloads before updating. Back up
`Mijn GPX`, `Kaarten` and `voorkeuren.json`. Updates reuse the installation folder.
When switching from a portable copy, you can select its existing folder; data is
not moved automatically to a different folder. Background work remains a separate opt-in.

## Privacy and limitations

No telemetry, automatic route upload or paid routing subscription. Map services
can see requested areas and your IP address. See the
[privacy policy](https://github.com/Delnoij/RouteRefit/blob/v0.5.15-beta/PRIVACY.md).
Downloads contain no personal route library or downloaded maps.

This is a beta. External road services may be slow or unavailable. Review proposals
and navigation exports. Calculated activity times remain estimates. Read the
[known limitations](https://github.com/Delnoij/RouteRefit/blob/v0.5.15-beta/KNOWN-ISSUES.md)
and [validation report](https://github.com/Delnoij/RouteRefit/blob/v0.5.15-beta/VALIDATIE.txt).
Testing on a separate Windows 11 PC and real navigation devices remains outstanding;
no real account uploads have been tested.

## Code signing policy

**This release is not digitally signed and has no SignPath Foundation acceptance.**
Windows may warn or block execution. Do not disable security protections.
The [code signing policy](https://github.com/Delnoij/RouteRefit/blob/v0.5.15-beta/CODE-SIGNING-POLICY.md)
describes review and deliberate approval. Checksums verify file contents; they
do not replace a digital signature or verified publisher identity.

**Copyright © 2026 Marco Delnoij.** Licensed under GPL-3.0-only.
Map data: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL.
