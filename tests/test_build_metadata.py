# SPDX-License-Identifier: GPL-3.0-only
"""Check the version resource consumed by the actual Windows build."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_windows


class BuildMetadataTests(unittest.TestCase):
    def test_windows_can_serialize_the_version_resource(self):
        from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file

        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as tmp:
            path = Path(tmp) / "version.txt"
            path.write_text(build_windows.version_resource(), encoding="utf-8")
            version = load_version_info_from_text_file(path)
            self.assertTrue(version.toRaw())
            self.assertEqual(version.ffi.fileFlags & 0x2, 0x2)
            self.assertEqual(version.ffi.fileVersionLS, 15 << 16)
            self.assertEqual(version.ffi.fileVersionMS, 5)


if __name__ == "__main__":
    unittest.main()

