# SPDX-License-Identifier: GPL-3.0-only
"""Fail closed on private data in public source and Windows artifacts.

The reviewed-data manifest contains only synthetic examples and documentation
assets. It must be reviewed when those assets change, never refreshed from a
used installation. This is a release-data check, not a general secret scanner.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath

PRIVATE_PARTS = {"mijn gpx", "kaarten", "wegenindex", "regios", "vakken", "gebiedspakketten", "pakketcorridors"}
PRIVATE_NAMES = {"voorkeuren.json", ".env", "thumbs.db", "desktop.ini"}
MAP_SUFFIXES = {".osm", ".pbf", ".mbtiles", ".sqlite", ".sqlite3", ".db"}
ROUTE_SUFFIXES = {".gpx", ".fit", ".tcx", ".kml", ".kmz", ".geojson"}
MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".heic",
                  ".tif", ".tiff", ".bmp", ".mp4", ".mov", ".pdf"}
SECRET_SUFFIXES = {".pfx", ".p12", ".key", ".pem"}


def reviewed_data(root):
    data = json.loads((Path(root) / "release-data-manifest.json").read_text(encoding="utf-8"))
    return data["sha256"]


def check_entry(name, read_bytes, manifest):
    """Check an artifact-relative path and lazily read its bytes."""
    name = str(name).replace("\\", "/")
    path = PurePosixPath(name)
    parts = [part.casefold() for part in path.parts]
    lower = path.name.casefold()
    suffix = path.suffix.casefold()
    if path.is_absolute() or ".." in parts or ":" in name:
        raise ValueError("Unsafe release path: " + name)
    if (any(part in PRIVATE_PARTS for part in parts)
            or lower in PRIVATE_NAMES or suffix in SECRET_SUFFIXES
            or suffix in MAP_SUFFIXES
            or any(marker in lower for marker in (".sqlite", ".mbtiles", ".osm.", ".db-"))
            or lower.endswith((".db.bak", ".db.backup"))):
        raise ValueError("Private map, settings or key in release: " + name)
    # No arbitrary file, report or photograph may hide in the examples folder.
    reviewed = (parts and parts[0] == "examples") or suffix in ROUTE_SUFFIXES | MEDIA_SUFFIXES or lower.endswith(".controle.json")
    if reviewed and name not in manifest:
        raise ValueError("Unreviewed route, report or media in release: " + name)
    if suffix in {".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".tar"} and name != "_internal/base_library.zip":
        raise ValueError("Unexpected nested archive in release: " + name)
    data = read_bytes()
    if name == "_internal/base_library.zip":
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(data)) as library:
            for info in library.infolist():
                if not info.is_dir():
                    check_entry(info.filename, lambda: library.read(info), {})
    if reviewed and hashlib.sha256(data).hexdigest() != manifest[name]:
        raise ValueError("Reviewed demonstration/documentation asset changed: " + name)
    if data.startswith(b"SQLite format 3\x00"):
        raise ValueError("SQLite data in release: " + name)
    # Also catch route/map XML accidentally renamed to a text file.
    prefix = data[:4096].lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if prefix.startswith((b"<?xml", b"<gpx", b"<osm", b"<kml")):
        if any(tag in prefix for tag in (b"<gpx", b"<osm", b"<kml")) and name not in manifest:
            raise ValueError("Unreviewed route/map XML in release: " + name)
    if lower == "routes.json" and data.strip() != b"[]":
        raise ValueError("The release catalogue must be empty: " + name)


def check_tree(root, manifest):
    root = Path(root)
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Do not include links in a release: " + str(path))
        if path.is_file():
            check_entry(path.relative_to(root).as_posix(), path.read_bytes, manifest)


def check_archive(archive, manifest):
    """Check actual ZIP members after writing, stripping its one outer folder."""
    import zipfile
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len(names) != len(set(name.casefold() for name in names)):
            raise ValueError("Duplicate or case-ambiguous archive paths")
        roots = {PurePosixPath(name).parts[0] for name in names if name}
        if len(roots) != 1:
            raise ValueError("Expected a single release root folder")
        for info in package.infolist():
            original = PurePosixPath(info.filename)
            if original.is_absolute() or ".." in original.parts or ":" in info.filename or "\\" in info.filename:
                raise ValueError("Unsafe archive path: " + info.filename)
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Links are not allowed in release archives")
            if info.is_dir():
                continue
            parts = PurePosixPath(info.filename).parts
            if len(parts) < 2:
                raise ValueError("Expected a single release root folder")
            check_entry("/".join(parts[1:]), lambda: package.read(info), manifest)
