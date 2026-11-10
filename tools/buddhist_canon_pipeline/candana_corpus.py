#!/usr/bin/env python3
"""List Candana's downloaded works and texts not yet on our website; never publish."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import urlopen

if __package__:
    from .candana_queue import checked_url, FORMATS
    from .import_candana import ROOT
    from .prepare_candana_batch import safe_relative, write_file
else:
    from candana_queue import checked_url, FORMATS
    from import_candana import ROOT
    from prepare_candana_batch import safe_relative, write_file

REFERENCE = re.compile(r'(?<!\w)(Snp|Thag|Thig|Dhp|Mil|DN|MN|SN|AN|Sn|Ud)\.?\s*'
                       r'(\d+(?:\.\d+){0,2}(?:\s*[-–]\s*\d+(?:\.\d+)*)?)(?![\w.])')
MARKER = '.candana-corpus.json'
MARKER_VALUE = {'kind': 'private-candana-corpus', 'automatic_publication': False}
ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6,
         'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10, 'XI': 11}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def references(value: str) -> list[str]:
    result = set()
    for match in REFERENCE.finditer(value):
        prefix = 'Snp' if match[1] == 'Sn' else match[1]
        number = re.sub(r'\s+', '', match[2]).replace('–', '-')
        result.add(prefix + ' ' + number)
    for match in re.finditer(r'\bAN\s+([IVX]+)\s*[:,]?\s*Suttas?\s+(\d+)\s*[-–]\s*(\d+)\b', value):
        if match[1] in ROMAN:
            result.add(f'AN {ROMAN[match[1]]}.{match[2]}-{match[3]}')
    return sorted(result)


def rights_signals(text):
    """Search all cached pages for leads, not just the first ten; never approve rights."""
    result = []
    for number, page in enumerate(text.split('\f'), 1):
        match = re.search(r'\b(?:redistribut\w*|republish\w*|permission|creative commons|licen[cs]e|reproduc\w*)\b', page, re.I)
        if match:
            result.append({'pdf_page': number, 'page_text_sha256': sha(page.encode()),
                           'keyword': match[0],
                           'excerpt': ' '.join(page[max(0, match.start()-100):match.end()+220].split()),
                           'permission_approved': False})
    return result


class Offers(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.active, self.parts, self.links = base, None, [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.active = dict(attrs).get('href')
            self.parts = []

    def handle_data(self, value):
        if self.active is not None:
            self.parts.append(value)

    def handle_endtag(self, tag):
        if tag != 'a' or self.active is None:
            return
        try:
            url = checked_url(urljoin(self.base, self.active))
            if Path(urlsplit(url).path).suffix.lower() in FORMATS:
                self.links.append({'source_url': url, 'page_url': self.base,
                                   'label': ' '.join(''.join(self.parts).split())})
        except ValueError:
            pass
        self.active = None


def group_offer(labels: list[str], heading: str, filename: str) -> tuple[str, str, list[str]]:
    """Group explicit references, never guess numbers from compressed filenames."""
    label_refs = sorted({r for label in labels for r in references(label)})
    nonempty = [line.strip() for line in heading.splitlines() if line.strip()]
    # References in later prose/footnotes do not identify the work being offered.
    first = nonempty[0] if nonempty else ''
    printed = references(first) if len(first) < 80 else []
    roman_range = references(' '.join(nonempty[:8]))
    if not printed and re.search(r'\bAN\s+[IVX]+\s*[:,]?\s*Suttas?', ' '.join(nonempty[:8])):
        printed = roman_range
    issues = []
    if len(label_refs) > 1 or len(printed) > 1:
        issues.append('MULTIPLE_REFERENCES_REQUIRE_SCOPE_CHECK')
    if len(label_refs) == len(printed) == 1 and label_refs != printed:
        issues.append('PUBLISHER_LABEL_AND_PDF_REFERENCE_DISAGREE')
    if issues:
        return 'unresolved:' + filename, 'REFERENCE_REVIEW', issues
    if len(label_refs) == 1:
        return label_refs[0], 'PUBLISHER_REFERENCE', []
    if len(printed) == 1:
        return printed[0], 'PDF_OPENING_REFERENCE', []
    return 'unresolved:' + filename, 'REFERENCE_REVIEW', ['NO_UNAMBIGUOUS_PRINTED_OR_PUBLISHER_REFERENCE']


def census(queue: dict, inventory: list, manifest: dict, read, live_index=None) -> dict:
    by_url = {r['source_url']: r for r in inventory}
    if len(by_url) != len(inventory):
        raise ValueError('Duplicate source URL in draft inventory')
    links = defaultdict(list)
    discovery = []
    jobs = {r['url']: r for r in queue['jobs']}
    if len(jobs) != len(queue['jobs']):
        raise ValueError('Duplicate source URL in collector queue')
    for job in jobs.values():
        if job['state'] != 'COLLECTED' or not job.get('cache', '').endswith('.html'):
            continue
        raw = read(job['cache'])
        if sha(raw) != job['sha256']:
            raise ValueError('Cached publisher page changed')
        discovery.append({'url': job['url'], 'sha256': sha(raw)})
        parser = Offers(job['url']); parser.feed(raw.decode('utf-8', errors='strict'))
        for link in parser.links:
            if link not in links[link['source_url']]:
                links[link['source_url']].append(link)
    imported = {r['canonical_id']: r for r in manifest['texts']}
    if len(imported) != len(manifest['texts']):
        raise ValueError('Imported reader IDs are duplicated')
    live_ids = ({t['canonical_id'] for t in live_index['texts']
                 if any(e['id'] == 'candana' for e in t['editions'])}
                if live_index is not None else None)
    book_urls = {b['source_url']: b for b in manifest['books']}
    offers, grouped = [], defaultdict(list)
    for job in jobs.values():
        filename = unquote(Path(urlsplit(job['url']).path).name)
        if Path(filename).suffix.lower() not in FORMATS:
            continue
        row = by_url.get(job['url'], {})
        labels = [l['label'] for l in links[job['url']] if l['label']]
        source_hash = None
        heading = ''
        draft_hash = None
        permission_leads = []
        if job['state'] == 'COLLECTED':
            raw = read(job['cache'])
            source_hash = sha(raw)
            if source_hash != job['sha256']:
                raise ValueError('Cached source changed: ' + filename)
            key = sha(job['url'].encode())
            draft = row.get('text_paths', {}).get('mupdf.txt')
            if draft:
                draft_path = 'build/candana-batch-review/' + draft
                text = read(draft_path)
                report = json.loads(read('build/candana-batch-review/sources/' + key + '/report.json'))
                if (report['source_sha256'] != source_hash
                        or report['output_hashes']['mupdf.txt'] != sha(text)):
                    raise ValueError('Changed or mismatched extraction draft: ' + filename)
                draft_hash = sha(text)
                heading = text.decode('utf-8', errors='strict').split('\f', 1)[0]
                permission_leads = rights_signals(text.decode('utf-8', errors='strict'))
        if job['url'] in book_urls:
            book = book_urls[job['url']]
            group = 'book:' + ('sutta-nipata' if book['id'].startswith('sutta-nipata') else book['id'])
            basis, issues = 'EXACT_BOOK_MANIFEST', []
        elif any(l['page_url'].endswith('/manual') for l in links[job['url']]):
            # One work, multiple language editions; never infer an edition's permission.
            group, basis, issues = 'resource:manual', 'PUBLISHER_MANUAL_PAGE', []
        elif 'Dissertation' in filename:
            group, basis, issues = 'resource:dissertation', 'SOURCE_FILENAME_REQUIRES_AUTHOR_CHECK', []
        else:
            group, basis, issues = group_offer(labels, heading, filename)
            if group.startswith('unresolved:'):
                group += ':' + sha(job['url'].encode())[:8]
        canonical = group if not ':' in group else None
        count = sum(t['source_revision'] == source_hash for t in manifest['texts']) if source_hash else 0
        offer = {'source_url': job['url'], 'source_sha256': source_hash, 'filename': filename,
                 'publisher_links': links[job['url']], 'state': job['state'],
                 'reference_group': group, 'group_basis': basis, 'reference_issues': issues,
                 'publisher_references': sorted({r for label in labels for r in references(label)}),
                 'opening_pdf_references': references(next((l.strip() for l in heading.splitlines() if l.strip()), '')),
                 'exact_source_readers_imported': count,
                 'same_site_reference_has_candana': bool(canonical and canonical in imported),
                 'same_reference_is_live': bool(canonical and live_ids is not None and canonical in live_ids),
                 'same_reference_is_not_edition_equivalence': True,
                 'rights': row.get('rights', 'NOT_YET_REVIEWED'),
                 'draft_issues': row.get('issues', []), 'draft_sha256': draft_hash,
                 'rights_keyword_pages': permission_leads,
                 'draft_review': row.get('review_path'), 'source_body_rewritten': False,
                 'publication_approved_by_census': False}
        offers.append(offer); grouped[group].append(offer)
    groups = []
    for identity, editions in sorted(grouped.items()):
        groups.append({'reference_group': identity, 'offer_count': len(editions),
                       'source_urls': [e['source_url'] for e in editions],
                       'source_hashes': sorted({e['source_sha256'] for e in editions if e['source_sha256']}),
                       'same_reference_is_live': any(e['same_reference_is_live'] for e in editions),
                       'same_reference_is_imported': any(e['same_site_reference_has_candana'] for e in editions),
                       'has_imported_source': any(e['exact_source_readers_imported'] for e in editions),
                       'needs_reference_review': identity.startswith('unresolved:')})
    hashes = defaultdict(list)
    for offer in offers:
        if offer['source_sha256']:
            hashes[offer['source_sha256']].append(offer['source_url'])
    canonical_groups = [g for g in groups if ':' not in g['reference_group']]
    historical = []
    for book in manifest['books']:
        if book['source_url'] in jobs:
            continue
        raw = read(book['local_path'])
        if sha(raw) != book['sha256']:
            raise ValueError('Historical manifest source changed')
        historical.append({'book': book['id'], 'source_url': book['source_url'],
                           'source_sha256': book['sha256'],
                           'status': 'MANIFEST_SOURCE_NOT_IN_CURRENT_COLLECTOR_QUEUE',
                           'reader_entries_from_exact_source': sum(t['source_revision'] == book['sha256'] for t in manifest['texts'])})
    priorities = {'MN 1': 0, 'DN 1': 1, 'DN 2': 2, 'DN 16': 3, 'MN 10': 4,
                  'SN 22.59': 5, 'SN 56.11': 6}
    missing = sorted([g for g in canonical_groups if not g['same_reference_is_imported']],
                     key=lambda g: (priorities.get(g['reference_group'], 100), g['reference_group']))
    return {'schema_version': 1, 'scope': 'Every offer in the bounded existing collector queue, not every work on the internet.',
            'automatic_publication': False, 'publisher_network_requests': 0, 'model_calls': 0,
            'queue_sha256': sha(json.dumps(queue, sort_keys=True).encode()),
            'manifest_sha256': sha(json.dumps(manifest, sort_keys=True).encode()),
            'publisher_pages': discovery, 'offers': offers, 'groups': groups,
            'historical_manifest_sources': historical,
            'next_import_groups': missing,
            'exact_file_aliases': [urls for urls in hashes.values() if len(urls) > 1],
            'uncollected_linked_offers': sorted(set(links) - set(jobs)),
            'summary': {'written_offers': len(offers), 'downloaded_offers': sum(o['state'] == 'COLLECTED' for o in offers),
                        'distinct_downloaded_file_hashes': len(hashes),
                        'additional_historical_manifest_sources': len(historical),
                        'imported_reader_entries': len(imported), 'live_reader_entries': len(live_ids) if live_ids is not None else None,
                        'identified_standalone_reference_groups': len(canonical_groups),
                        'standalone_groups_with_existing_candana_reader': sum(g['same_reference_is_imported'] for g in canonical_groups),
                        'standalone_groups_without_live_candana_reader': sum(not g['same_reference_is_live'] for g in canonical_groups) if live_ids is not None else None,
                        'unresolved_offer_references': sum(g['needs_reference_review'] for g in groups),
                        'permission_keyword_leads_not_approvals': sum(bool(o['rights_keyword_pages']) for o in offers),
                        'whole_corpus_percentage': None,
                        'percentage_limit': 'Books, source-number groups, standalone passages and language editions are different units. Unknown references and undiscovered works prevent a whole-corpus percentage.'}}


def render(report):
    summary = report['summary']
    lines = ['CANDANA — WHAT IS ON OUR WEBSITE AND WHAT IS STILL MISSING',
             f"Candana text pages on our website: {summary['live_reader_entries'] if summary['live_reader_entries'] is not None else 'Not checked'}",
             f"Downloaded files: {summary['downloaded_offers']} of {summary['written_offers']} found links",
             'Different files may contain the same text or different versions of it.', '']
    body = ['<h1>Candana — what is on our website and what is still missing</h1>',
            '<p>This lists the texts found so far. It does not claim we have found everything Candana has published or have permission to publish every text.</p>',
            ''.join('<p>' + html.escape(line) + '</p>' for line in lines if line) + '<ol>']
    for group in report['groups']:
        state = ('Which text this file contains still needs checking.' if group['needs_reference_review'] else
                 'This book supplies texts already added to the website.' if group['has_imported_source'] else
                 'Candana’s translation is already on our website; this separate edition may differ.' if group['same_reference_is_live'] else
                 'The text is prepared, but this check has not confirmed it is live.' if group['same_reference_is_imported'] else
                 'Candana’s translation is not yet on our website.')
        lines.extend([group['reference_group'] + ' — ' + state,
                      *('  ' + u for u in group['source_urls']), ''])
        body.append('<li><h2>' + html.escape(group['reference_group']) + '</h2><p>' + state + '</p><ul>')
        for edition, url in enumerate(group['source_urls'], 1):
            offer = next(o for o in report['offers'] if o['source_url'] == url)
            label = 'Original PDF' + (f' {edition}' if len(group['source_urls']) > 1 else '')
            body.append('<li><a href="' + html.escape(url, quote=True) + '" title="'
                        + html.escape(offer['filename'], quote=True) + '">' + label
                        + '</a> — ' + html.escape(offer['rights']))
            if offer['draft_review']:
                link = '../candana-batch-review/' + offer['draft_review']
                body.append(' · <a href="' + html.escape(link, quote=True) + '">Converted text</a>')
            body.append('</li>')
        body.append('</ul></li>')
    body.append('</ol>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Candana corpus inventory</title><body>' + ''.join(body) + '</body></html>\n'), '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', help='One read-only request to our own public reading index')
    args = parser.parse_args()
    queue = json.loads((ROOT / 'build/candana-audit/queue.json').read_bytes())
    inventory = json.loads((ROOT / 'build/candana-batch-review/inventory.json').read_bytes())
    manifest = json.loads((ROOT / 'metadata/source-manifests/candana.json').read_bytes())
    index = None
    if args.live:
        with urlopen('https://freebuddhism.org/theravada/tipitaka/site/reading-index.json', timeout=30) as response:
            index = json.load(response)
    report = census(queue, inventory, manifest, lambda p: safe_relative(ROOT, p).read_bytes(), index)
    destination = ROOT / 'build/candana-corpus'
    safe_relative(ROOT, 'build/candana-corpus')
    marker = destination / MARKER
    if destination.exists() and (not marker.is_file() or json.loads(marker.read_bytes()) != MARKER_VALUE):
        raise ValueError('Refusing an unmarked corpus output directory')
    destination.mkdir(exist_ok=True)
    write_file(marker, (json.dumps(MARKER_VALUE) + '\n').encode())
    page, plain = render(report)
    for name, data in [('inventory.json', json.dumps(report, ensure_ascii=False, indent=2)),
                       ('next-imports.json', json.dumps(report['next_import_groups'], ensure_ascii=False, indent=2)),
                       ('index.html', page), ('inventory.txt', plain)]:
        write_file(safe_relative(destination, name), data.encode('utf-8'))
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
