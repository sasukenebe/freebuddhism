#!/usr/bin/env python3
"""Compare every built Candana reader with its pinned TXT; no model or publication."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

if __package__:
    from .import_candana import ROOT, verified_manifest
else:
    from import_candana import ROOT, verified_manifest


class SourceText(HTMLParser):
    """Read source text independently of the HTML renderer."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.count = 0
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if 'source-text' in dict(attrs).get('class', '').split():
            if tag != 'pre' or self.count:
                raise ValueError('Expected exactly one plain source container')
            self.count += 1
            self.active = True
        elif self.active:
            raise ValueError('Unexpected markup inside plain source text')

    def handle_endtag(self, tag):
        if self.active:
            if tag != 'pre':
                raise ValueError('Unexpected closing markup inside source text')
            self.active = False

    def handle_data(self, value):
        if self.active:
            self.parts.append(value)

    def body(self):
        if self.count != 1 or self.active:
            raise ValueError('Missing or incomplete source container')
        return ''.join(self.parts)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise ValueError('Unexpected public reader redirect')


def relative_url(value: str) -> str:
    url = urlsplit(value)
    path = unquote(url.path)
    parts = PurePosixPath(path).parts
    if (url.scheme or url.netloc or url.query or url.fragment or not path.startswith('/')
            or path.startswith('//') or '..' in parts or '\\' in path
            or any(ord(c) < 32 for c in path)):
        raise ValueError('Unsafe reader URL')
    return path.lstrip('/')


def compare(index: dict, sources: dict, read) -> dict:
    editions = []
    seen = set()
    for text in index['texts']:
        for edition in text['editions']:
            if edition['id'] != 'candana':
                continue
            identity = text['canonical_id']
            if identity in seen or identity not in sources:
                raise ValueError('Duplicate or unexpected Candana edition: ' + identity)
            seen.add(identity)
            relative_url(edition['url'])
            relative_url(text['url'])
            editions.append((identity, edition['url'], text['url']))
    if seen != set(sources):
        raise ValueError('Reading index is missing imported Candana editions')

    def check(item):
        identity, url, _ = item
        parser = SourceText()
        parser.feed(read(url).decode('utf-8', errors='strict'))
        if parser.body() != sources[identity]['body']:
            raise ValueError('Displayed source differs from pinned TXT: ' + identity)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(check, editions))
    groups = {}
    for item in editions:
        groups.setdefault(sources[item[0]]['book'], []).append(item)
    samples = []
    for book, items in groups.items():
        for i in sorted({0, len(items) // 2, len(items) - 1}):
            identity, url, node = items[i]
            source = sources[identity]
            samples.append({'text': identity, 'book': book, 'original': source['source_url'],
                            'converted': url, 'text_home': node,
                            'human_review': 'NOT_RECORDED_BY_THIS_CHECK'})
    return {'status': 'ALL_READER_TEXT_MATCHES', 'readers_verified': len(editions),
            'counts_by_book': dict(Counter(s['book'] for s in sources.values())),
            'comparison': 'Exact decoded source characters, including whitespace and punctuation.',
            'model_calls': 0, 'human_proofreading_approved': False,
            'layout_checked_by_this_command': False, 'suggested_spot_checks': samples}


def check_release(site_root: Path, public_base: str | None = None) -> dict:
    manifest = verified_manifest(require_review=True)
    sources = {}
    for row in manifest['texts']:
        if row['canonical_id'] in sources:
            raise ValueError('Duplicate imported source ID')
        raw = (ROOT / row['local_path']).read_text(encoding='utf-8')
        sources[row['canonical_id']] = dict(row, body=raw.split('\n\n', 1)[1])
    if public_base:
        if public_base not in {'https://freebuddhism.org', 'https://www.freebuddhism.org'}:
            raise ValueError('Public checks are limited to the project hostnames')

        def read(url):
            target = public_base + '/' + relative_url(url)
            with build_opener(NoRedirect).open(target, timeout=20) as response:
                if response.geturl() != target:
                    raise ValueError('Unexpected public reader redirect')
                return response.read()
    else:
        def read(url):
            path = site_root / relative_url(url)
            if any(p.is_symlink() for p in [path, *path.parents]):
                raise ValueError('Reader check must not follow symlinks')
            path.resolve().relative_to(site_root.resolve())
            return path.read_bytes()
    index = json.loads(read('/theravada/tipitaka/site/reading-index.json'))
    return dict(compare(index, sources, read), target=public_base or str(site_root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-root', type=Path, default=ROOT / 'build/site-root')
    parser.add_argument('--public-base', help='Optional HTTPS check of the project website')
    parser.add_argument('--output', type=Path, help='New JSON report; existing files are never overwritten')
    args = parser.parse_args()
    report = check_release(args.site_root, args.public_base)
    if args.output:
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
