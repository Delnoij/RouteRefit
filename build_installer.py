# SPDX-License-Identifier: GPL-3.0-only
"""Build an unsigned per-user installer from an already reviewed release payload."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from app_version import VERSION
from release_tools import check_source, source_files, digest
from release_privacy import check_tree, reviewed_data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', required=True, type=Path)
    args = parser.parse_args()
    check_source()
    payload = ROOT / 'dist' / ('RouteRefit-' + VERSION)
    check_tree(payload, reviewed_data(ROOT))
    info = json.loads((payload / 'BUILD-INFO.json').read_text(encoding='utf-8'))
    actual = {p.relative_to(ROOT).as_posix(): digest(p) for p in source_files()}
    if actual != info['source_sha256']:
        raise ValueError('Source changed after packaging; run release_tools.py package again.')
    compiler = args.compiler.resolve(strict=True)
    compiler_version = subprocess.check_output([str(compiler), '--version'], text=True).strip()
    if compiler_version != '7.1.1':
        raise ValueError('Use the pinned Inno Setup 7.1.1 compiler.')
    output = ROOT / 'release'
    subprocess.run([str(compiler), '/Qp', '/DProductVersion=' + VERSION.split('-')[0],
                    '/DPayload=' + str(payload), '/DOutputFolder=' + str(output),
                    str(ROOT / 'installer/RouteRefit.iss')], check=True)
    setup = output / ('RouteRefit-' + VERSION + '-Setup.exe')
    if not setup.is_file():
        raise ValueError('Installer output missing')
    installer_info = {
        'product': 'RouteRefit', 'version': VERSION, 'signing_status': 'unsigned',
        'compiler': 'Inno Setup ' + compiler_version,
        'source_commit': info['source_commit'],
        'github_run_id': info['github_run_id'],
        'source_build_info_sha256': digest(payload / 'BUILD-INFO.json'),
        'application_exe_sha256': digest(payload / ('RouteRefit-' + VERSION + '.exe')),
        'setup_sha256': digest(setup),
    }
    (output / 'INSTALLER-INFO.json').write_text(json.dumps(installer_info, indent=2) + '\n', encoding='utf-8')
    hashes = sorted(p for p in output.iterdir() if p.suffix in {'.zip', '.exe', '.json'})
    (output / 'SHA256SUMS.txt').write_text(''.join(digest(p) + '  ' + p.name + '\n' for p in hashes), encoding='utf-8')
    print('Unsigned installer created: ' + setup.name)


if __name__ == '__main__':
    main()
