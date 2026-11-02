# SPDX-License-Identifier: GPL-3.0-only
"""Check the installed build packages against the committed Windows lock file."""

from importlib.metadata import version
from pathlib import Path
import re
import sys


def verify_build_environment(root):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13):
        raise RuntimeError("This build targets Windows x64 with CPython 3.13.")
    installed = {}
    for line in (Path(root) / "requirements-windows.lock").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^ ]+) --hash=sha256:[0-9a-f]{64}", line)
        if not match:
            raise ValueError("Unexpected lock-file entry: " + line)
        package, wanted = match.groups()
        actual = version(package)
        if actual != wanted:
            raise RuntimeError(
                f"{package}: expected {wanted}, installed {actual}. Install requirements-windows.lock with --require-hashes."
            )
        installed[package] = actual
    return installed
