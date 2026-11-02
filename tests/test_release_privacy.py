# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import release_privacy as privacy
import release_tools


class ReleasePrivacyTests(unittest.TestCase):
    def assert_rejected(self, name, data=b"private"):
        with self.assertRaises(ValueError, msg=name):
            privacy.check_entry(name, lambda: data, {})

    def test_map_formats_and_database_sidecars_rejected(self):
        for name in ("data/map.osm", "region.osm.gz", "region.pbf", "map.mbtiles",
                     "roads.sqlite3", "roads.sqlite3-wal", "roads.db-shm", "roads.db.backup"):
            self.assert_rejected(name)

    def test_private_folders_and_preferences_case_insensitive(self):
        for name in ("KaArTeN/x.txt", "Mijn GPX/file.txt", "Wegenindex/a.bin",
                     "nested/VOORKEUREN.JSON", "Vakken/a.txt"):
            self.assert_rejected(name)

    def test_examples_folder_is_not_a_route_escape(self):
        self.assert_rejected("examples/my-trip.gpx")
        self.assert_rejected("examples/private-photo.jpg")
        self.assert_rejected("examples/my-notes.txt")

    def test_reviewed_example_must_keep_approved_contents(self):
        name, data = "examples/demo.gpx", b"<gpx/>"
        manifest = {name: hashlib.sha256(data).hexdigest()}
        privacy.check_entry(name, lambda: data, manifest)
        with self.assertRaises(ValueError):
            privacy.check_entry(name, lambda: b"<gpx>personal</gpx>", manifest)

    def test_renamed_database_and_route_detected(self):
        self.assert_rejected("data.bin", b"SQLite format 3\0private")
        self.assert_rejected("my-notes.txt", b'<?xml version="1.0"?><gpx/>')

    def test_catalogue_must_be_empty(self):
        privacy.check_entry("src/routes.json", lambda: b"[]\n", {})
        self.assert_rejected("src/routes.json", b'[{"name":"private"}]')

    def test_unreviewed_photos_reports_and_archives_rejected(self):
        for name in ("waypoint.jpg", "out.controle.json", "backup.zip", "backup.7z"):
            self.assert_rejected(name)

    def test_traversal_paths_rejected(self):
        for name in ("../x", "/private.txt", "C:/private.txt"):
            self.assert_rejected(name)

    def test_final_zip_members_checked(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            archive = Path(folder) / "release.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("RouteRefit/README.md", "code")
                z.writestr("RouteRefit/Kaarten/tile.bin", "private")
            with self.assertRaises(ValueError):
                privacy.check_archive(archive, {})

    def test_nested_runtime_zip_checked(self):
        import io
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as z:
            z.writestr("hidden.gpx", "private")
        self.assert_rejected("_internal/base_library.zip", data.getvalue())

    def test_git_tracked_private_folder_is_not_silently_skipped(self):
        with patch.object(release_tools.subprocess, "check_output", side_effect=[
            str(release_tools.ROOT), b"Kaarten/tile.osm\0"
        ]):
            with self.assertRaises(ValueError):
                release_tools.check_git_index({})

    def test_current_source_passes(self):
        release_tools.check_source()


if __name__ == "__main__":
    unittest.main()
