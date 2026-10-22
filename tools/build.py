#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build/package the prepared source without installing it; Python 3.6+."""
import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

from prepare import verify_files
from verify import ROOT, command, require, sha256


def run(args, cwd, log, env):
    with open(str(log), 'w') as stream:
        result = subprocess.run(args, cwd=str(cwd), env=env, stdout=stream, stderr=subprocess.STDOUT)
    require(result.returncode == 0, 'Build step failed; see ' + str(log))


def package(root, source_binary, target, original, version, manifest):
    sapi = {'usr/sbin/php-fpm7.2': 'fpm', 'usr/bin/php7.2': 'cli', 'usr/lib/cgi-bin/php7.2': 'cgi'}[target]
    unpacked = root / ('package-' + sapi)
    require(not unpacked.exists(), 'Package work directory already exists')
    subprocess.check_call(['dpkg-deb', '-R', str(original), str(unpacked)])
    baseline = unpacked / target
    def exports(path):
        return set(line.split()[-1] for line in command(['nm', '-D', '--defined-only', str(path)]).splitlines()
                   if len(line.split()) >= 3)
    old_exports = exports(baseline)
    old_modules = command([str(baseline), '-n', '-m'])
    shutil.copyfile(str(source_binary), str(unpacked / target))
    (unpacked / target).chmod(0o755)
    subprocess.check_call(['strip', '--strip-unneeded', str(unpacked / target)])
    require(old_exports.issubset(exports(unpacked / target)), 'Original exported symbols removed')
    require(command([str(unpacked / target), '-n', '-m']) == old_modules, 'Builtin module set changed')
    require('not found' not in command(['ldd', str(unpacked / target)]), 'Missing runtime shared library')
    require('GNU_RELRO' in command(['readelf', '-W', '-l', str(unpacked / target)]), 'RELRO missing')
    require('BIND_NOW' in command(['readelf', '-d', str(unpacked / target)]), 'BIND_NOW missing')
    doc = unpacked / ('usr/share/doc/php72-bionic-backport/' + sapi + '.txt')
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text('LOCAL SECURITY REBUILD; NOT AN OFFICIAL UBUNTU PACKAGE.\n'
                   'Base: ' + manifest['target']['basePackageVersion'] + '\n'
                   'C patch SHA256: ' + manifest['patch']['sha256'] + '\n'
                   'Existing shared extensions and configuration are preserved.\n')
    files = sorted(path for path in unpacked.rglob('*')
                   if path.is_file() and not path.is_symlink() and 'DEBIAN' not in path.relative_to(unpacked).parts)
    control = unpacked / 'DEBIAN/control'
    text = re.sub(r'^Version: .*$', 'Version: ' + version, control.read_text(), flags=re.M)
    text = re.sub(r'^Maintainer: .*$', 'Maintainer: Local PHP security rebuild <root@localhost>', text, flags=re.M)
    text = re.sub(r'^Installed-Size: .*$', 'Installed-Size: ' + str((sum(path.stat().st_size for path in files) + 1023) // 1024), text, flags=re.M)
    control.write_text(text.rstrip() + '\nX-Local-Security-Patch: CVE-2026-109618 CVE-2026-109619\n')
    import hashlib
    (unpacked / 'DEBIAN/md5sums').write_text(''.join(
        hashlib.md5(path.read_bytes()).hexdigest() + '  ' + str(path.relative_to(unpacked)) + '\n'
        for path in files))
    dest = root / ('php7.2-' + sapi + '_' + version + '_amd64.deb')
    subprocess.check_call(['fakeroot', 'dpkg-deb', '-b', str(unpacked), str(dest)])
    return {'package': dest.name, 'sha256': sha256(dest), 'binary': target,
            'binarySha256': sha256(unpacked / target)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=pathlib.Path, help='Directory created by prepare.py')
    parser.add_argument('--original-packages', type=pathlib.Path, default=ROOT / 'downloads')
    parser.add_argument('--configure-only', action='store_true')
    args = parser.parse_args()
    release = pathlib.Path('/etc/os-release').read_text()
    require('ID=ubuntu' in release and 'VERSION_ID="18.04"' in release, 'Build only on isolated Ubuntu 18.04')
    require(command(['dpkg', '--print-architecture']) == 'amd64', 'Build only on amd64')
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    work = args.work.resolve()
    source = work / 'php-7.2.24'
    require(json.loads((work / 'preparation.json').read_text()).get('ok'), 'Source preparation did not pass')
    verify_files(source, manifest, 'patchedSha256')
    for entry in manifest['originalPackages']:
        require(sha256(args.original_packages / entry['package']) == entry['sha256'], 'Original package checksum mismatch')
    # Only build metadata changes here; the C patch remains byte-identical.
    configure = source / 'configure.ac'
    text = configure.read_text()
    tag = manifest['target']['runtimeVersion'][len('7.2.24'):]
    if 'PHP_EXTRA_VERSION=""' in text:
        configure.write_text(text.replace('PHP_EXTRA_VERSION=""', 'PHP_EXTRA_VERSION="' + tag + '"', 1))
    else:
        require('PHP_EXTRA_VERSION="' + tag + '"' in text, 'Unexpected engine tag')
    if (source / 'ext/ext_skel').exists():
        (source / 'ext/ext_skel').rename(source / 'ext/ext_skel.in')
    env = dict(os.environ, DEB_BUILD_MAINT_OPTIONS='hardening=+all', EXTENSION_DIR='/usr/lib/php/20170718')
    opcode_names = ['Zend/zend_vm_opcodes.c', 'Zend/zend_vm_opcodes.h']
    opcode_hashes = {name: sha256(source / name) for name in opcode_names}
    run(['php7.2', '-n', 'Zend/zend_vm_gen.php'], source, work / 'vm-generator.log', env)
    verify_files(source, manifest, 'patchedSha256')
    require(all(sha256(source / name) == value for name, value in opcode_hashes.items()), 'VM opcode files changed')
    run(['./buildconf', '--force'], source, work / 'buildconf.log', env)
    for name in ['CFLAGS', 'CPPFLAGS', 'LDFLAGS']:
        env[name] = subprocess.check_output(['dpkg-buildflags', '--get', name], env=env,
                                            universal_newlines=True).strip()
    env['CFLAGS'] += ' -Wall -pedantic -fsigned-char -fno-strict-aliasing -g'
    env['LDFLAGS'] += ' -Wl,--as-needed'
    common = ['--build=x86_64-linux-gnu', '--host=x86_64-linux-gnu', '--prefix=/usr',
              '--with-libdir=lib/x86_64-linux-gnu', '--libdir=/usr/lib/php', '--libexecdir=/usr/lib/php',
              '--datadir=/usr/share/php/7.2', '--program-suffix=7.2', '--localstatedir=/var',
              '--mandir=/usr/share/man', '--disable-all', '--disable-debug', '--disable-rpath',
              '--disable-static', '--with-pic', '--with-layout=GNU', '--without-pear',
              '--enable-filter', '--with-openssl=yes', '--with-password-argon2=/usr',
              '--with-pcre-regex=/usr', '--enable-hash', '--with-mhash=/usr', '--enable-libxml',
              '--enable-session', '--with-sodium', '--with-system-tzdata', '--with-zlib=/usr',
              '--with-zlib-dir=/usr', '--enable-dtrace']
    extras = {
        'fpm': ['--enable-fpm', '--enable-cli', '--disable-cgi', '--disable-phpdbg', '--with-fpm-user=www-data',
                '--with-fpm-group=www-data', '--with-libevent-dir=/usr', '--with-fpm-systemd'],
        'cli': ['--enable-cli', '--disable-cgi', '--disable-phpdbg', '--enable-pcntl', '--with-libedit=shared,/usr'],
        'cgi': ['--enable-cgi', '--enable-cli', '--disable-phpdbg', '--enable-force-cgi-redirect',
                '--enable-fastcgi', '--enable-pcntl']}
    targets = {'fpm': 'sapi/fpm/php-fpm', 'cli': 'sapi/cli/php', 'cgi': 'sapi/cgi/php-cgi'}
    destinations = {'fpm': 'usr/sbin/php-fpm7.2', 'cli': 'usr/bin/php7.2', 'cgi': 'usr/lib/cgi-bin/php7.2'}
    version = manifest['target']['patchedPackageVersion'] + '+rebuild' + datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')
    results = []
    for sapi in ['fpm', 'cli', 'cgi']:
        directory = work / (sapi + '-build')
        directory.mkdir(exist_ok=True)
        options = common + extras[sapi] + ['--with-config-file-path=/etc/php/7.2/' + sapi,
                  '--with-config-file-scan-dir=/etc/php/7.2/' + sapi + '/conf.d', '--sysconfdir=/etc']
        run([str(source / 'configure')] + options, directory, work / (sapi + '-configure.log'), env)
        header = (directory / 'main/build-defs.h').read_text()
        require(re.search(r'#define\s+PHP_SYSCONFDIR\s+"/etc"', header), 'FPM/engine default sysconfdir is not /etc')
        if args.configure_only:
            continue
        run(['make', '-j1', targets[sapi]], directory, work / (sapi + '-compile.log'), env)
        original = next(entry for entry in manifest['originalPackages'] if entry['package'].startswith('php7.2-' + sapi + '_'))
        results.append(package(work, directory / targets[sapi], destinations[sapi],
                               args.original_packages / original['package'], version, manifest))
    if args.configure_only:
        print(json.dumps({'ok': True, 'configured': ['fpm', 'cli', 'cgi'], 'compiled': False}))
        return
    manifest['target']['patchedPackageVersion'] = version
    manifest['patchedPackages'] = results
    manifest['kitVersion'] = 'local-' + version
    manifest['releaseAssets'] = [{'filename': entry['package'], 'sha256': entry['sha256']} for entry in results]
    (work / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'ok': True, 'version': version, 'manifest': str(work / 'manifest.json')}))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        sys.exit(2)
