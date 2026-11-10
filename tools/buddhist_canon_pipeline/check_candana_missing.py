#!/usr/bin/env python3
"""Check downloaded Candana texts in bounded batches; no network, AI or publication."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess

if __package__:
    from .import_candana import ROOT, granted_notice
    from .prepare_candana_batch import safe_relative, write_file
    from .verify_candana_conversion import audit
else:
    from import_candana import ROOT, granted_notice
    from prepare_candana_batch import safe_relative, write_file
    from verify_candana_conversion import audit

OUTPUT = 'build/candana-text-checks'
MARKER = '.candana-text-checks.json'
MARKER_VALUE = {'kind': 'private-candana-text-checks', 'automatic_publication': False}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def candidates(inventory):
    offers = {row['source_url']: row for row in inventory['offers']}
    if len(offers) != len(inventory['offers']):
        raise ValueError('Repeated source URL in inventory')
    result, seen = [], set()
    for group in inventory['next_import_groups']:
        for url in group['source_urls']:
            row = offers[url]
            if url not in seen and row['state'] == 'COLLECTED':
                if row['same_site_reference_has_candana'] or row['exact_source_readers_imported']:
                    raise ValueError('Missing-text list contains an already imported Candana text')
                if not row.get('draft_review'):
                    raise ValueError('Downloaded text lacks a prepared comparison')
                result.append(row); seen.add(url)
    return result


def source_inputs(root, row):
    relative = 'build/candana-batch-review/' + row['draft_review']
    folder = safe_relative(root, relative).parent
    pdf = safe_relative(folder, 'source.pdf')
    text = safe_relative(folder, 'mupdf.txt')
    report = json.loads(safe_relative(folder, 'report.json').read_bytes())
    pdf_hash, text_hash = sha(pdf.read_bytes()), sha(text.read_bytes())
    if (pdf_hash != row['source_sha256'] or report['source_sha256'] != pdf_hash
            or report['output_hashes']['source.pdf'] != pdf_hash
            or report['output_hashes']['mupdf.txt'] != text_hash
            or row['draft_sha256'] != text_hash):
        raise ValueError('Downloaded PDF or converted text changed: ' + row['reference_group'])
    return pdf, text, pdf_hash, text_hash


def check_one(root, directory, row, identity, auditor=audit):
    pdf, text, pdf_hash, text_hash = source_inputs(root, row)
    fingerprint = sha(json_bytes({'pdf': pdf_hash, 'text': text_hash,
                                  'source_url': row['source_url'], 'tools': identity}))
    previous = directory / 'result.json'
    if previous.is_file() and not previous.is_symlink():
        try:
            saved = json.loads(previous.read_bytes())
            output = safe_relative(directory, 'comparison.json')
            if (saved['fingerprint'] == fingerprint and output.is_file()
                    and saved['comparison_sha256'] == sha(output.read_bytes())):
                return saved, True
        except (KeyError, ValueError, OSError):
            pass
    comparison = auditor(pdf, text)
    if comparison['pdf_sha256'] != pdf_hash or comparison['text_sha256'] != text_hash:
        raise ValueError('Comparison result refers to different source bytes')
    raw = text.read_text(encoding='utf-8')
    pages = raw.split('\f')
    if pages and not pages[-1].strip():
        pages.pop()
    notice_pages = [{'pdf_page': n, 'page_text_sha256': sha(page.encode()),
                     'copyright_lines': [line.strip() for line in page.splitlines()
                                         if re.search(r'copyright|©|all rights reserved', line, re.I)]}
                    for n, page in enumerate(pages, 1)
                    if re.search(r'copyright|©|all rights reserved', page, re.I)]
    data = json_bytes(comparison)
    saved = {'schema_version': 1, 'text': row['reference_group'], 'source_url': row['source_url'],
             'source_sha256': pdf_hash, 'text_sha256': text_hash, 'fingerprint': fingerprint,
             'comparison_sha256': sha(data), 'comparison_status': comparison['status'],
             'pdf_pages': comparison['pdf_pages'], 'disagreements': comparison['disagreements'],
             'word_boundary_disagreements': comparison.get('word_boundary_disagreements', []),
             'image_only_pages': comparison['image_only_pages'], 'copyright_notices': notice_pages,
             'same_book_notice_found_somewhere': granted_notice(raw),
             'rights_status': row['rights'], 'permission_approved_by_this_check': False,
             'publication_approved': False, 'full_human_proofreading': False,
             'model_calls': 0, 'network_requests': 0,
             'suggested_pdf_spot_checks': sorted({1, max(1, len(pages)//2), len(pages)}),
             'original': '../candana-batch-review/' + row['draft_review'].removesuffix('index.html') + 'source.pdf',
             'converted': '../candana-batch-review/' + row['draft_review']}
    directory.mkdir(parents=True, exist_ok=True)
    write_file(safe_relative(directory, 'comparison.json'), data)
    write_file(safe_relative(directory, 'result.json'), json_bytes(saved))
    return saved, False


def run_batch(root=ROOT, limit=8, texts=(), auditor=audit, identity=None):
    if not 1 <= limit <= 25:
        raise ValueError('Batch limit must be between one and 25')
    if identity is None:
        import fitz
        version = subprocess.run(['pdftotext', '-v'], check=True, capture_output=True).stderr
        identity = {'pymupdf': fitz.VersionBind, 'poppler_version_sha256': sha(version),
                    'checker_sha256': sha(Path(__file__).read_bytes()),
                    'audit_sha256': sha(Path(audit.__code__.co_filename).read_bytes())}
    inventory_path = safe_relative(root, 'build/candana-corpus/inventory.json')
    rows = candidates(json.loads(inventory_path.read_bytes()))
    if texts:
        unknown = set(texts) - {r['reference_group'] for r in rows}
        if unknown:
            raise ValueError('Unknown text requested: ' + ', '.join(sorted(unknown)))
        rows = [r for r in rows if r['reference_group'] in texts]
    output = safe_relative(root, OUTPUT)
    output.mkdir(parents=True, exist_ok=True)
    marker = safe_relative(output, MARKER)
    if any(output.iterdir()) and (not marker.is_file() or json.loads(marker.read_bytes()) != MARKER_VALUE):
        raise ValueError('Refusing an unmarked text-check output directory')
    write_file(marker, json_bytes(MARKER_VALUE))
    descriptor = os.open(safe_relative(output, '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        checked, reused, waiting, results = 0, 0, [], []
        for row in rows:
            directory = safe_relative(output, sha(row['source_url'].encode()))
            # Known reports still verify the current source bytes and saved comparison.
            if checked >= limit and not (directory / 'result.json').is_file():
                waiting.append(row['reference_group']); continue
            if checked >= limit:
                # A stale report must wait for the next bounded pass, not bypass the limit.
                try:
                    pdf, text, a, b = source_inputs(root, row)
                    old = json.loads((directory / 'result.json').read_bytes())
                    expected = sha(json_bytes({'pdf': a, 'text': b, 'source_url': row['source_url'], 'tools': identity}))
                    valid = (old['fingerprint'] == expected
                             and old['comparison_sha256'] == sha(safe_relative(directory, 'comparison.json').read_bytes()))
                except (ValueError, KeyError, OSError):
                    valid = False
                if not valid:
                    waiting.append(row['reference_group']); continue
            try:
                result, hit = check_one(root, directory, row, identity, auditor)
                reused += hit; checked += not hit; results.append(result)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
                checked += 1
                results.append({'text': row['reference_group'], 'source_url': row['source_url'],
                                'status': 'CHECK_FAILED', 'error': str(error), 'publication_approved': False})
        report = {'schema_version': 1, 'texts_in_this_run': len(rows), 'checked_now': checked,
                  'unchanged_checks_reused': reused, 'waiting': len(waiting),
                  'network_requests': 0, 'model_calls': 0, 'automatic_publication': False,
                  'results': results, 'waiting_texts': waiting}
        write_file(safe_relative(output, 'report.json'), json_bytes(report))
        items = ['<h1>Candana — texts not yet on our website</h1>',
                 '<p>Compare Original PDF and Converted text. Automatic wording checks do not prove permission or complete visual proofreading.</p><ul>']
        for row in results:
            items.append('<li><h2>' + html.escape(row['text']) + '</h2>')
            if row.get('original'):
                state = ('Automatic character comparison passed.' if row['comparison_status'] == 'TEXT_COMPARISON_PASS'
                         else 'The text converters disagree; the marked PDF pages need checking.')
                if row['word_boundary_disagreements']:
                    state += ' Word spacing still needs checking on the listed PDF pages.'
                items.append('<a href="' + html.escape(row['original'], quote=True) + '">Original PDF</a> · '
                             '<a href="' + html.escape(row['converted'], quote=True) + '">Converted text</a>'
                             '<p>' + state + ' Permission to put this text on our website is not approved by this check.</p>')
                flagged = sorted({int(m[1]) for value in row['disagreements'] + row['word_boundary_disagreements']
                                  for m in [re.search(r'page (\d+)', value)] if m})
                if flagged:
                    items.append('<p>PDF pages to check: ' + ', '.join(
                        '<a href="' + html.escape(row['original'], quote=True) + '#page=' + str(n)
                        + '">' + str(n) + '</a>' for n in flagged) + '</p>')
            else:
                items.append('<p>Check failed: ' + html.escape(row['error']) + '</p>')
            items.append('</li>')
        page = ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1">'
                '<title>Candana text checks</title><body>' + ''.join(items) + '</ul></body></html>\n')
        write_file(safe_relative(output, 'index.html'), page.encode())
        return report
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=8)
    parser.add_argument('--text', action='append', default=[])
    args = parser.parse_args()
    report = run_batch(limit=args.limit, texts=args.text)
    print(json.dumps({k: v for k, v in report.items() if k not in {'results', 'waiting_texts'}}, indent=2))
    for row in report['results']:
        print(row['text'] + ': ' + row.get('comparison_status', row.get('status', 'UNKNOWN')))


if __name__ == '__main__':
    main()
