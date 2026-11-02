# Dependencies and notices

The application source is GPL-3.0-only. Dependency licences are independent and remain in THIRD-PARTY-NOTICES. Windows dependency versions and wheel hashes are recorded in requirements-windows.lock; upstream runtime components remain under their own terms.

| Component | Role | Upstream / licence |
| --- | --- | --- |
| CPython 3.13.12 | Runtime | https://www.python.org/ — PSF terms and bundled notices |
| Tcl/Tk 8.6 | Desktop UI | https://www.tcl-lang.org/ — Tcl/Tk licence |
| Pillow 13.0.0 | Photo validation/preview | https://pypi.org/project/Pillow/13.0.0/ — Pillow and bundled image-library notices |
| fitdecode 0.11.0 | FIT reader | https://pypi.org/project/fitdecode/0.11.0/ — MIT |
| OpenSSL 3.0.18 | Python HTTPS runtime | https://github.com/openssl/openssl/tree/openssl-3.0.18 — Apache-2.0 |
| PyInstaller 6.22.3 | Build/bootloader | https://pypi.org/project/pyinstaller/6.22.3/ — GPL with bootloader exception |
| Inno Setup 7.1.1 x64 | Installer compiler and installer runtime | https://jrsoftware.org/ — Inno Setup licence, THIRD-PARTY-NOTICES/Inno-Setup.txt |
| pyosmium 4.3.2 / libosmium | Streaming regional PBF and OSC reader | https://docs.osmcode.org/pyosmium/latest/ — BSD-2-Clause |

The pyosmium Windows wheel includes standard C/C++ runtime and compression/XML
libraries (MSVC runtime, bzip2, Expat, LZ4 and zlib). The application does not use
pyosmium's optional network replication tools: regional HTTPS requests use the
existing Python standard library and the application's bounded downloader.
Pyosmium's declared Python dependencies (requests, charset_normalizer, idna,
urllib3, certifi) are pinned for installation reproducibility; unused replication
tools are excluded from the Windows executable. Upstream licences supplied with
the packages and pyosmium source archive are included in THIRD-PARTY-NOTICES.

Build-only packages such as setuptools, altgraph, packaging and the Windows build helpers are pinned in the lock file. Their source and package metadata are available from their named PyPI project releases. None is represented as code maintained by Marco Delnoij. The project should only request a signature for its own application EXE; third-party library signatures remain those of their respective publishers or are absent.

The local build uses the same locked Windows dependencies as the prepared workflow. A local build is not thereby a GitHub trusted build. Actual GitHub-run provenance and SignPath configuration must be checked after the maintainer's test and publication approval.
