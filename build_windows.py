# SPDX-License-Identifier: GPL-3.0-only
"""Build the unsigned Windows application, with consistent version metadata."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from app_version import COPYRIGHT, DISPLAY_VERSION, PRODUCT_NAME, VERSION, VERSION_TUPLE


def version_resource():
    """Only describe this product; a version resource is not a signature."""
    name = f"{PRODUCT_NAME}-{VERSION}"
    fields = {
        "FileDescription": PRODUCT_NAME,
        "FileVersion": ".".join(map(str, VERSION_TUPLE)),
        "InternalName": name,
        "LegalCopyright": COPYRIGHT,
        "OriginalFilename": name + ".exe",
        "ProductName": PRODUCT_NAME,
        "ProductVersion": DISPLAY_VERSION,
    }
    strings = ",\n".join(f"StringStruct({key!r}, {value!r})" for key, value in fields.items())
    return f"""VSVersionInfo(
ffi=FixedFileInfo(filevers={VERSION_TUPLE!r}, prodvers={VERSION_TUPLE!r},
mask=0x3f, flags=0x2, OS=0x40004, fileType=0x1, subtype=0x0, date=(0,0)),
kids=[StringFileInfo([StringTable('040904B0', [{strings}])]),
VarFileInfo([VarStruct('Translation', [1033,1200])])])
"""


def main():
    from build_environment import verify_build_environment
    from release_tools import check_source

    check_source()
    verify_build_environment(ROOT)
    import PyInstaller.__main__

    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    resource = build / "windows-version.txt"
    resource.write_text(version_resource(), encoding="utf-8")
    PyInstaller.__main__.run(
        [
            "--noconfirm",
            "--windowed",
            "--icon", str(ROOT / "src/assets/routerefit.ico"),
            "--add-data", str(ROOT / "src/assets") + ";assets",
            "--add-data", str(ROOT / "src/regions.json") + ";.",
            "--additional-hooks-dir", str(ROOT / "tools/pyinstaller-hooks"),
            "--exclude-module", "osmium.replication",
            "--exclude-module", "osmium.tools",
            "--noupx",
            # AVIF is not an accepted waypoint photo format. Its optional codec
            # alone adds several MB; retain JPG/PNG/WebP/GIF support in full.
            "--exclude-module",
            "PIL.AvifImagePlugin",
            "--exclude-module",
            "PIL._avif",
            "--name",
            f"{PRODUCT_NAME}-{VERSION}",
            "--version-file",
            str(resource),
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(build),
            "--specpath",
            str(build),
            "--add-data",
            str(ROOT / "src/routes.json") + ";.",
            "--add-data",
            str(ROOT / "src/locales") + ";locales",
            str(ROOT / "src/werkbank.py"),
        ]
    )


if __name__ == "__main__":
    main()
