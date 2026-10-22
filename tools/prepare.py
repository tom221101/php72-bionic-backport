#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare the pinned vendor source plus C patch in a NEW directory; Python 3.6+."""
import argparse
import json
import pathlib
import shlex
import subprocess
import sys
import tarfile

from verify import ROOT, require, sha256


def extract(archive, destination):
    destination = destination.resolve()
    with tarfile.open(str(archive)) as source:
        for entry in source.getmembers():
            name = pathlib.PurePosixPath(entry.name)
            require(not name.is_absolute() and '..' not in name.parts, 'Unsafe archive member')
            require(not entry.isdev() and not entry.isfifo(), 'Unexpected special archive member')
            if entry.issym() or entry.islnk():
                link = pathlib.PurePosixPath(entry.linkname)
                require(not link.is_absolute() and '..' not in link.parts, 'Unsafe archive link')
        source.extractall(str(destination))


def apply_patch(source, patch, options, log):
    with open(str(log), 'a') as stream:
        result = subprocess.run(['patch', '-f', '-F0'] + options + ['-i', str(patch)],
                                cwd=str(source), stdout=stream, stderr=subprocess.STDOUT)
    require(result.returncode == 0, 'Patch failed; see ' + str(log))


def verify_files(source, manifest, key):
    for entry in manifest['sourceFiles']:
        require(sha256(source / entry['path']) == entry[key],
                'Source baseline mismatch: ' + entry['path'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloads', type=pathlib.Path, default=ROOT / 'downloads')
    parser.add_argument('--work', type=pathlib.Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    require(not args.work.exists(), 'Work directory already exists; choose a new one')
    for entry in manifest['sourceArchives']:
        require(sha256(args.downloads / entry['filename']) == entry['sha256'], 'Source archive checksum mismatch')
    patch = ROOT / manifest['patch']['path']
    require(sha256(patch) == manifest['patch']['sha256'], 'C patch checksum mismatch')
    args.work.mkdir(parents=True)
    work = args.work.resolve()
    extract(args.downloads / manifest['sourceArchives'][0]['filename'], work)
    source = work / 'php-7.2.24'
    extract(args.downloads / manifest['sourceArchives'][1]['filename'], source)
    series = source / 'debian/patches/series'
    require(sha256(series) == manifest['vendorPatchSeries']['sha256'], 'Vendor series checksum mismatch')
    rows = [shlex.split(line, comments=True) for line in series.read_text().splitlines()]
    rows = [row for row in rows if row]
    require(len(rows) == manifest['vendorPatchSeries']['count'], 'Vendor patch count mismatch')
    for row in rows:
        require(not pathlib.PurePosixPath(row[0]).is_absolute() and '..' not in pathlib.PurePosixPath(row[0]).parts,
                'Unsafe vendor patch path')
        apply_patch(source, source / 'debian/patches' / row[0], row[1:] or ['-p1'], work / 'vendor-patches.log')
    verify_files(source, manifest, 'baseSha256')
    apply_patch(source, patch, ['-p1'], work / 'security-patch.log')
    verify_files(source, manifest, 'patchedSha256')
    result = {'ok': True, 'source': str(source), 'vendorPatches': len(rows),
              'verifiedPatchedFiles': len(manifest['sourceFiles'])}
    (work / 'preparation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, tarfile.TarError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        sys.exit(2)
