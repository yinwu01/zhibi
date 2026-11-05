"""Scan reachable Git blobs and release archives without printing secret values.

This detects selected credential signatures and packaging mistakes. It is not a
proof that arbitrary user data or every secret format is absent.
"""
import argparse
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import zipfile

PATTERNS = {
    'private_key': re.compile(rb'-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----'),
    'github_token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{70,})'),
    'anthropic_token': re.compile(rb'sk-ant-[A-Za-z0-9_-]{40,}'),
    'aws_access_id': re.compile(rb'AKIA[A-Z0-9]{16}'),
    'local_user_path': re.compile(rb'/Users/[A-Za-z0-9_.-]+/(?:Desktop|Documents|\.ssh)/'),
}


def scan(data, source, findings):
    for kind, pattern in PATTERNS.items():
        if pattern.search(data):
            findings.append({'source': source, 'kind': kind})


def history(findings):
    entries = subprocess.check_output(['git', 'rev-list', '--objects', '--all'], text=True).splitlines()
    count = total = 0
    proc = subprocess.Popen(['git', 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for entry in entries:
            oid, _, path = entry.partition(' ')
            proc.stdin.write((oid + '\n').encode()); proc.stdin.flush()
            header = proc.stdout.readline().split()
            size = int(header[2]); data = proc.stdout.read(size)
            if len(data) != size or proc.stdout.read(1) != b'\n':
                raise ValueError('Incomplete Git object stream')
            if header[1] == b'blob':
                count += 1; total += size
                scan(data, 'git:' + oid + ':' + path, findings)
    finally:
        proc.stdin.close(); proc.stdout.close()
        proc.wait()
    return {'blobs': count, 'bytes': total}


def member(data, name, findings, depth, label):
    source = label + '/' + name
    parts = PurePosixPath(name).parts
    if PurePosixPath(name).is_absolute() or '..' in parts:
        findings.append({'source': source, 'kind': 'unsafe_archive_path'})
    base = parts[-1] if parts else ''
    if (base.endswith(('.private.json', '.pem', '.key', '.p12', '.ppk'))
            or base in ('.env', 'id_rsa', 'id_ed25519', '.credentials.json')):
        findings.append({'source': source, 'kind': 'private_file_name'})
    if data.startswith((b'\x7fELF', b'\xcf\xfa\xed\xfe', b'MZ')):
        findings.append({'source': source, 'kind': 'unexpected_native_binary'})
    scan(data, source, findings)
    if name.endswith(('.zip', '.pyz')) and depth < 2:
        return archive(io.BytesIO(data), source, findings, depth + 1)
    return 1


def archive(source, label, findings, depth=0):
    count = 0
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as package:
            for info in package.infolist():
                if info.is_dir():
                    continue
                if info.file_size > 20_000_000:
                    raise ValueError('Unexpected oversized archive member: ' + info.filename)
                count += member(package.read(info), info.filename, findings, depth, label)
    else:
        with tarfile.open(source) as package:
            for info in package:
                if info.issym() or info.islnk():
                    findings.append({'source': label + '/' + info.name, 'kind': 'archive_link'})
                if info.isfile():
                    if info.size > 20_000_000:
                        raise ValueError('Unexpected oversized archive member: ' + info.name)
                    count += member(package.extractfile(info).read(), info.name, findings, depth, label)
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--git-history', action='store_true')
    parser.add_argument('--artifact', action='append', default=[])
    args = parser.parse_args()
    if not args.git_history and not args.artifact:
        parser.error('Select --git-history and/or --artifact')
    findings = []
    report = {'history': history(findings) if args.git_history else None,
              'artifacts': {str(path): archive(path, str(path), findings) for path in args.artifact},
              'findings': findings}
    print(json.dumps(report, indent=2))
    return int(bool(findings))


if __name__ == '__main__':
    raise SystemExit(main())
