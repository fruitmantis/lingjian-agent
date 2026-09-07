#!/usr/bin/env python3
"""Fetch the two official, hash-pinned UI fonts; never install system fonts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/ui/huawei-cloud-font-manifest.json'
DESTINATION = ROOT / 'frontend/public/fonts/huawei-cloud'
OFFICIAL_PREFIX = 'https://portal.hc-cdn.com/cnpm-baseui/3.0.18/style/core/fonts/'
CONTENT_TYPES = {'font/woff2', 'application/font-woff2', 'application/octet-stream', 'binary/octet-stream'}


def verify(data: bytes, entry: dict) -> str:
    if len(data) < 48 or data[:4] != b'wOF2':
        raise ValueError('Invalid or empty WOFF2 file')
    if struct.unpack('>I', data[8:12])[0] != len(data) or not struct.unpack('>H', data[12:14])[0]:
        raise ValueError('Incomplete WOFF2 header/length')
    digest = hashlib.sha256(data).hexdigest()
    if len(data) != entry['size'] or digest != entry['sha256']:
        raise ValueError('Font size/SHA-256 differs from the inspected official version')
    return digest


def fetch_all(destination: Path = DESTINATION, check_only: bool = False) -> list[dict]:
    entries = json.loads(MANIFEST.read_text())['fonts']
    downloads = []
    # Validate the complete set before replacing any existing local font.
    for entry in entries:
        url = entry['url']
        filename = entry['local_filename']
        if not url.startswith(OFFICIAL_PREFIX) or Path(filename).name != filename:
            raise ValueError('Unapproved font source or filename')
        if check_only:
            data = (destination / filename).read_bytes()
        else:
            with urllib.request.urlopen(url, timeout=45) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError('Unexpected HTTP status or redirected font source')
                content_type = response.headers.get('Content-Type', '').split(';')[0].strip().lower()
                if content_type not in CONTENT_TYPES:
                    raise ValueError('Unexpected font Content-Type')
                data = response.read(entry['size'] + 1)
        digest = verify(data, entry)
        downloads.append((entry, data, digest))
    if not check_only:
        destination.mkdir(parents=True, exist_ok=True)
        for entry, data, _ in downloads:
            with tempfile.NamedTemporaryFile(dir=destination, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
            try:
                temporary.chmod(0o644)
                os.replace(temporary, destination / entry['local_filename'])
            finally:
                temporary.unlink(missing_ok=True)
    return [{'file': entry['local_filename'], 'bytes': len(data), 'sha256': digest, 'weight': entry['weight']}
            for entry, data, digest in downloads]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate local files without network access')
    args = parser.parse_args()
    try:
        print(json.dumps(fetch_all(check_only=args.check), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f'Font fetch/check failed: {error}\n')
