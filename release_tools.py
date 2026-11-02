# SPDX-License-Identifier: GPL-3.0-only
"""Check source hygiene and package an unsigned, traceable review build."""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import zipfile
from build_environment import verify_build_environment
from release_privacy import check_archive, check_entry, check_tree, reviewed_data

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from app_version import DISPLAY_VERSION, PRODUCT_NAME, VERSION

SKIP = {
    ".git",
    ".venv",
    "__pycache__",
    ".ruff_cache",
    "build",
    "dist",
    "release",
    "Mijn GPX",
    "Kaarten",
}


def source_files():
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in SKIP for part in relative.parts):
            continue
        # Older manuals must not accumulate in future source downloads.
        if relative.parts[0] == "Handleidingen" and path.suffix.lower() == ".pdf":
            if not path.name.startswith(f"{PRODUCT_NAME}-{VERSION}-handleiding-"):
                continue
        if not path.is_file() or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError("Do not include source links: " + str(relative))
        yield path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_source():
    manifest = reviewed_data(ROOT)
    if (ROOT / "src/routes.json").read_text(encoding="utf-8").strip() != "[]":
        raise ValueError("The release catalogue must be empty.")
    if (
        not (ROOT / "LICENSE")
        .read_text(encoding="utf-8")
        .startswith("                    GNU GENERAL PUBLIC LICENSE")
    ):
        raise ValueError("Official GPLv3 text missing.")
    for path in source_files():
        relative = path.relative_to(ROOT)
        check_entry(relative.as_posix(), path.read_bytes, manifest)
    check_git_index(manifest)
    print("Source hygiene checks passed; this is not a general secret scanner.")


def check_git_index(manifest):
    """Ignore rules do not protect files that Git already tracks."""
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return
    if Path(top).resolve() != ROOT.resolve():
        return
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    for name in filter(None, names):
        if any(part.casefold() in {p.casefold() for p in SKIP} for part in Path(name).parts):
            raise ValueError("Local/build data already tracked by Git: " + name)
        check_entry(name, (ROOT / name).read_bytes, manifest)


def source_commit():
    import re

    sha = os.environ.get("GITHUB_SHA", "")
    if re.fullmatch("[0-9a-fA-F]{40}", sha):
        return sha
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
        if Path(top).resolve() != ROOT.resolve():
            return None
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write_zip(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source, name in files:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, source.read_bytes())
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError("Invalid ZIP: " + str(path))


def package():
    check_source()
    manifest = reviewed_data(ROOT)
    dependencies = verify_build_environment(ROOT)
    name = f"{PRODUCT_NAME}-{VERSION}"
    application = ROOT / "dist" / name
    executable = application / (name + ".exe")
    if not executable.exists():
        raise ValueError("Run build_windows.py first.")
    # Reusing a test installation as a public artifact could expose personal routes.
    for folder in application.rglob("*"):
        if folder.name in {"Mijn GPX", "Kaarten", "voorkeuren.json"}:
            raise ValueError("Do not package a used application folder. Make a clean build.")
    for filename in (
        "LICENSE",
        "README.md",
        "KNOWN-ISSUES.md",
        "PRIVACY.md",
        "CODE-SIGNING-POLICY.md",
        "TESTEN.md",
        "CHANGELOG.md",
        "VALIDATIE.txt",
        "UPDATE-0.5.15.txt",
        "DEPENDENCIES.md",
        "VERTROUWEN.md",
    ):
        shutil.copy2(ROOT / filename, application / filename)
    shutil.copytree(
        ROOT / "THIRD-PARTY-NOTICES", application / "THIRD-PARTY-NOTICES", dirs_exist_ok=True
    )
    shutil.copytree(ROOT / "examples", application / "examples", dirs_exist_ok=True)
    for language in ("NL", "EN", "DE", "FR", "ES", "PT"):
        manual = ROOT / "Handleidingen" / f"{PRODUCT_NAME}-{VERSION}-handleiding-{language}.pdf"
        if not manual.is_file():
            raise ValueError("Missing user manual: " + manual.name)
    manuals = application / "Handleidingen"
    manuals.mkdir(exist_ok=True)
    for manual in (ROOT / "Handleidingen").glob(f"{PRODUCT_NAME}-{VERSION}-handleiding-*.pdf"):
        shutil.copy2(manual, manuals / manual.name)
    (application / "Koppeling instellen.cmd").write_text(
        f'@echo off\n"%~dp0{name}.exe" --register\n', encoding="ascii"
    )
    sources = list(source_files())
    source_hashes = {p.relative_to(ROOT).as_posix(): digest(p) for p in sources}
    build_info = {
        "product": PRODUCT_NAME,
        "version": VERSION,
        "display_version": DISPLAY_VERSION,
        "signing_status": "unsigned",
        "source_commit": source_commit(),
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": dependencies,
        "source_sha256": source_hashes,
    }
    (application / "BUILD-INFO.json").write_text(
        json.dumps(build_info, indent=2) + "\n", encoding="utf-8"
    )
    # Check the actual application tree, including unexpected leftovers.
    check_tree(application, manifest)
    output = ROOT / "release"
    output.mkdir(exist_ok=True)
    standalone_manuals = [output / (name + "-handleiding-" + code + ".pdf") for code in ("EN", "NL")]
    for manual in standalone_manuals:
        shutil.copy2(ROOT / "Handleidingen" / manual.name, manual)
    source_zip = output / (name + "-broncode.zip")
    windows_zip = output / (name + "-Windows.zip")
    write_zip(
        source_zip,
        [(path, "GitHub-broncode/" + path.relative_to(ROOT).as_posix()) for path in sources],
    )
    write_zip(
        windows_zip,
        [
            (path, name + "-Windows/" + path.relative_to(application).as_posix())
            for path in sorted(application.rglob("*"))
            if path.is_file()
        ],
    )
    # Do not issue checksums for an artifact that failed the final privacy gate.
    check_archive(source_zip, manifest)
    check_archive(windows_zip, manifest)
    (output / "SHA256SUMS.txt").write_text(
        "".join(digest(path) + "  " + path.name + "\n" for path in (windows_zip, source_zip, *standalone_manuals)),
        encoding="utf-8",
    )
    (output / "BUILD-INFO.json").write_text(
        json.dumps(build_info, indent=2) + "\n", encoding="utf-8"
    )
    print("Unsigned review artifacts created in " + str(output))


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        check_source()
    elif sys.argv[1:] == ["package"]:
        package()
    else:
        raise SystemExit("Usage: python release_tools.py check|package")
