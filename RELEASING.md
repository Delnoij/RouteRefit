# Reviewed beta releases

The first public release is **0.5.15-beta**, including a per-user Windows installer
and a portable ZIP. It remains a beta, is unsigned and has not been accepted by
SignPath. Do not describe local builds as GitHub trusted builds.

## Reproduce the build

Use Windows x64, Python 3.13.12 and the locked, hash-checked dependencies:

```text
python -m pip install --require-hashes -r requirements-windows.lock
python release_tools.py check
python -m unittest discover -s tests -v
python build_windows.py
python release_tools.py package
./tools/install_inno.ps1
python build_installer.py --compiler build/inno/ISCC.exe
./tests/installer_smoke.ps1 -Installer release/RouteRefit-0.5.15-beta-Setup.exe
```

The installer test uses a new folder below `build`, synthetic data, triggerless
temporary Windows tasks and a temporary per-user installation registration.
It refuses to run when this installer is already registered on the machine.
Run it on a clean test user or a disposable GitHub-hosted runner. It never uses
the maintainer's route library. It retains synthetic fixtures and logs in `build`
for inspection; they are excluded from source and release downloads.

The pinned Inno Setup 7.1.1 download is checked against a SHA-256 digest and a
valid Authenticode signature from Pyrsys B.V. before execution. Its licence is
in `THIRD-PARTY-NOTICES/Inno-Setup.txt`. This is a build dependency only.

The GitHub workflow also runs the existing offline UI checks. All source
files are recorded by hash in BUILD-INFO.json. Package again after any source or
documentation edit: the installer builder rejects stale source provenance.
This records traceable inputs; it is not a claim of bit-for-bit reproducibility
across different Windows machines or timestamps.

## First public release

1. Create the repository from the clean `Broncode` tree or source ZIP, with new
   history. Never upload a used installation, private working folder or map cache.
2. Use multifactor authentication on the owner account. Enable private
   vulnerability reporting. Protect `main` against deletion and force pushes,
   and require successful build checks where available. CODEOWNERS alone does
   not enable protection. With one maintainer, do not claim independent review.
3. Push the exact reviewed source and wait for the GitHub-hosted workflow to pass.
   Review that run's logs, installer tests and artifacts. A local pass is not a
   substitute for an actual GitHub run.
4. Test the installer on a separate Windows 11 computer without Python. Record
   actual results and remaining limitations. Do not invent adoption or testing.
5. Create tag `v0.5.15-beta` at that exact revision. Draft a release, mark it
   **pre-release**, and include the installer, portable ZIP, source ZIP, English and Dutch
   manuals, BUILD-INFO.json, INSTALLER-INFO.json and matching SHA256SUMS.txt from that build. All six
   manuals are also inside the Windows packages. Use RELEASE-NOTES.md as the
   draft text. Convert its document links to the actual repository's tagged source
   URLs before pasting it into the release page. Review the exact files before publishing.
6. Keep issue reporting focused on reproducible, anonymized examples. Retain
   original reports privately when location details cannot be safely shared.

If extra manual PDFs are attached separately, add their hashes to the same
published SHA256SUMS.txt. GitHub automatically provides its own source archives;
the additional checked source ZIP is tied to the recorded build input hashes.

## Code signing policy

See [Code signing policy](CODE-SIGNING-POLICY.md) and [privacy policy](PRIVACY.md).
Only after a real public release, reviewed hosted build and sufficient project
history should the maintainer apply to SignPath Foundation. See
[SIGNPATH-VOORBEREIDING.md](SIGNPATH-VOORBEREIDING.md) for outstanding steps.

The proposed signing targets are RouteRefit's own EXE, installer and uninstaller.
Upstream DLLs must retain their own provenance and must not be signed as our
code. Configure artifact metadata restrictions and manual signing approval with
SignPath after acceptance. An embedded uninstaller and the application must be
signed before the enclosing installer is finalized; an approved nested-artifact
configuration or ordered build/sign steps is needed. Signing only Setup.exe does
not automatically sign its contents. Recompute hashes after signing.

No signing workflow, token, certificate or approval integration is active now.
Do not add claims of SignPath sponsorship before actual acceptance.
