#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read-only host/package checks and isolated CLI smoke; Python 3.6+."""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha256(path):
    with open(str(path), 'rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def command(args, timeout=20):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            universal_newlines=True, timeout=timeout,
                            env=dict(os.environ, LC_ALL='C'))
    if result.returncode:
        raise RuntimeError('%s exited %s' % (args[0], result.returncode))
    return result.stdout.strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def require_build_manifest(manifest):
    expected = {'usr/bin/php7.2', 'usr/lib/cgi-bin/php7.2', 'usr/sbin/php-fpm7.2'}
    entries = manifest.get('patchedPackages', [])
    require(len(entries) == 3 and {entry.get('binary') for entry in entries} == expected,
            'Use --manifest <build-directory>/manifest.json from a completed local build')


def host_checks(manifest, patched):
    release = dict(line.split('=', 1) for line in pathlib.Path('/etc/os-release').read_text().splitlines() if '=' in line)
    require(release.get('ID', '').strip('"') == 'ubuntu', 'Not Ubuntu')
    require(release.get('VERSION_ID', '').strip('"') == '18.04', 'Not the supported Bionic baseline')
    require(command(['dpkg', '--print-architecture']) == 'amd64', 'Not amd64')
    target = manifest['target']
    expected = target['patchedPackageVersion'] if patched else target['basePackageVersion']
    packages = {}
    for name in ['php7.2-cli', 'php7.2-cgi', 'php7.2-fpm', 'php7.2-common']:
        actual = command(['dpkg-query', '-W', '-f=${Version}', name])
        wanted = target['basePackageVersion'] if name == 'php7.2-common' else expected
        require(actual == wanted, '%s version mismatch: %s' % (name, actual))
        packages[name] = actual
    entries = manifest['patchedPackages'] if patched else manifest['originalBinaries']
    files = []
    for entry in entries:
        name = entry['binary'] if patched else entry['path']
        expected_hash = entry['binarySha256'] if patched else entry['sha256']
        require(sha256('/' + name) == expected_hash, 'Executable baseline mismatch: ' + name)
        files.append(name)
    return {'packages': packages, 'verifiedExecutables': files}


def package_checks(manifest, directory):
    results = []
    for entry in manifest['patchedPackages']:
        path = directory / entry['package']
        require(path.is_file(), 'Missing package: ' + entry['package'])
        require(sha256(path) == entry['sha256'], 'Package checksum mismatch: ' + entry['package'])
        fields = command(['dpkg-deb', '-f', str(path), 'Version', 'Architecture'])
        require(manifest['target']['patchedPackageVersion'] in fields and 'amd64' in fields,
                'Package control mismatch')
        results.append(entry['package'])
    return {'verifiedPackages': results}


def process_checks(manifest):
    require(os.geteuid() == 0, 'Run installed verification with sudo to inspect every PHP 7.2 process')
    hashes = collections.defaultdict(set)
    for entry in manifest['patchedPackages']:
        hashes[pathlib.Path(entry['binary']).name].add(entry['binarySha256'])
    processes = []
    for path in pathlib.Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            image = os.readlink(str(path / 'exe'))
            name = pathlib.Path(image.replace(' (deleted)', '')).name
            if name not in hashes:
                continue
            digest = sha256(path / 'exe')
            processes.append({'pid': int(path.name), 'kind': name,
                              'deletedImage': image.endswith(' (deleted)'),
                              'patched': digest in hashes[name], 'sha256': digest})
        except (FileNotFoundError, ProcessLookupError):
            continue
    master = int(command(['systemctl', 'show', 'php7.2-fpm.service', '-p', 'MainPID', '--value']))
    fpms = [entry for entry in processes if entry['kind'] == 'php-fpm7.2']
    require(master > 0 and any(entry['pid'] == master for entry in fpms), 'Actual FPM master not observed')
    require(len(fpms) > 1, 'No FPM worker observed; verify an assigned normal web request first')
    for unit in ['php7.2-fpm.service', 'nginx.service']:
        require(command(['systemctl', 'is-active', unit]) == 'active', unit + ' is not active')
    remaining = [entry for entry in processes if not entry['patched'] or entry['deletedImage']]
    return {'observedPhp72Processes': processes, 'fpmMasterPid': master,
            'webFpmPatched': all(entry['patched'] and not entry['deletedImage'] for entry in fpms),
            'remainingProcesses': remaining, 'ok': not remaining}


def smoke(manifest, php):
    cli = next(entry for entry in manifest['patchedPackages'] if entry['binary'] == 'usr/bin/php7.2')
    require(sha256(php) == cli['binarySha256'], 'Smoke requires the verified candidate CLI binary')
    code = r'''
function check($value) { if (!$value) { throw new RuntimeException('smoke assertion failed'); } }
$a = []; $b = $a; $a[] = 'alpha'; check($b === [] && $a === ['alpha']);
$a['mixed'] = 42; check($a['mixed'] === 42);
$copy = unserialize(serialize($a)); check($copy === $a);
$object = (object) ['a' => 1]; $array = (array) clone $object; $array['b'] = 2; check($array === ['a' => 1, 'b' => 2]);
$s = 'start'; for ($i = 0; $i < 10; $i++) { $s .= ':' . $i; } check($s === 'start:0:1:2:3:4:5:6:7:8:9');
session_id('php72kitsynthetic'); check(session_start()); $_SESSION['qa'] = $a; check(session_write_close());
$_SESSION = [];
check(session_start()); check($_SESSION['qa'] === $a); session_write_close();
echo 'OK|', PHP_VERSION, '|9';
'''
    with tempfile.TemporaryDirectory(prefix='php72-kit-smoke-') as directory:
        text = command([str(php), '-n', '-d', 'session.save_path=' + directory,
                        '-d', 'session.use_cookies=0', '-d', 'session.cache_limiter=',
                        '-d', 'memory_limit=64M', '-r', code])
        parts = text.split('|')
        require(len(parts) == 3 and parts[0] == 'OK', 'Unexpected isolated smoke output')
        result = {'ok': True, 'runtimeVersion': parts[1], 'checks': int(parts[2])}
    require(result.get('runtimeVersion') == manifest['target']['runtimeVersion'], 'Runtime tag mismatch')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=pathlib.Path, default=ROOT / 'manifest.json')
    sub = parser.add_subparsers(dest='mode')
    sub.add_parser('baseline')
    package = sub.add_parser('packages')
    package.add_argument('directory', type=pathlib.Path)
    sub.add_parser('installed')
    probe = sub.add_parser('smoke')
    probe.add_argument('--php', required=True, type=pathlib.Path)
    args = parser.parse_args()
    if not args.mode:
        parser.error('Choose baseline, packages, installed, or smoke')
    manifest = json.loads(args.manifest.read_text())
    if args.mode != 'baseline':
        require_build_manifest(manifest)
    result = {'mode': args.mode, 'ok': True}
    if args.mode == 'baseline':
        result.update(host_checks(manifest, False))
    elif args.mode == 'packages':
        result.update(package_checks(manifest, args.directory))
    elif args.mode == 'installed':
        result.update(host_checks(manifest, True))
        result.update(process_checks(manifest))
    else:
        result.update(smoke(manifest, args.php))
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        sys.exit(2)
