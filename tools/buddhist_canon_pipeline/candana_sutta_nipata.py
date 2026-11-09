"""Idempotent, offline import of the pinned 391-page Candana Sutta Nipāta."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re

if __package__:
    from .candana_resources import SNP_FOLIOS
    from .public_candana_review import INPUT, SOURCE_URL, checked_data
else:
    from candana_resources import SNP_FOLIOS
    from public_candana_review import INPUT, SOURCE_URL, checked_data

ROOT = Path(__file__).resolve().parents[2]
BOOK_ID = 'sutta-nipata-391'
REPORT = 'metadata/reports/candana-snp-import-2026-11-09.json'
AUDIT = 'metadata/reports/candana-snp-conversion-2026-11-09.json'
AUDIT_SHA = '43a96071d4a19311e673ff7ee162f3b304bee808f46c2a10e1c693b77044d81e'
REFERENCE = 'theravada/tipitaka/sutta/suttacentral-sujato-text-ledger.tsv'
NOTICE = 'Copyright © Bhikkhu Candana, 2023. Free distribution only; do not alter the contents.'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def reader_body(unit: dict) -> tuple[str, list[int]]:
    """Reflow physical wraps, preserving words, stanza gaps and proven hard breaks."""
    paragraphs, removed = [], []
    source = []
    for number, page in enumerate(unit['body'].split('\f'), unit['first_pdf_page']):
        if number in SNP_FOLIOS and page.strip():
            match = re.search(rf'(?m)^[ \t]*{number}[ \t]*\n*\Z', page)
            if match is None:
                raise ValueError('Expected pinned folio missing')
            page = page[:match.start()]
            removed.append(number)
        source.append(page)
        for paragraph in re.split(r'\n[ \t]*\n+', page):
            if not paragraph.strip():
                continue
            parts = (re.split(r'(?m)\n(?=“?Thus, the Bhikkhu)', paragraph)
                     if unit['id'] == 'snp1.1' else [paragraph])
            paragraphs.append('\n'.join(' '.join(part.split()) for part in parts if part.strip()))
    body = '\n\n'.join(paragraphs) + '\n'
    if body.split() != '\f'.join(source).split():
        raise ValueError('Reader reflow changed source words or punctuation')
    return body, removed


def plan(root: Path = ROOT) -> tuple[dict, list[dict], dict, dict[str, bytes]]:
    if __package__:
        from .import_candana import LICENSE
    else:
        from import_candana import LICENSE
    pdf = (root / INPUT / 'original.pdf').read_bytes()
    raw = (root / INPUT / 'converted.txt').read_bytes()
    _, units = checked_data(pdf, raw)
    audit_bytes = (root / AUDIT).read_bytes()
    if sha(audit_bytes) != AUDIT_SHA:
        raise ValueError('The complete source audit is changed or missing')
    audit = json.loads(audit_bytes)
    if (audit['status'] != 'TEXT_COMPARISON_PASS' or audit['pdf_pages'] != 391
            or audit['intervals_verified'] != 80 or audit['individual_suttas_verified'] != 73
            or audit['pdf_sha256'] != sha(pdf) or audit['text_sha256'] != sha(raw)):
        raise ValueError('Incomplete or mismatched Sutta Nipāta source audit')
    references_bytes = (root / REFERENCE).read_bytes()
    rows = list(csv.DictReader(references_bytes.decode('utf-8').splitlines(), dialect='excel-tab'))
    reference_rows = [r for r in rows if r['canonical_id'].startswith('Snp ')]
    reference = {r['canonical_id']: r for r in reference_rows}
    source_units = [u for u in units if u['kind'] == 'SUTTA_SOURCE_INTERVAL']
    ids = ['Snp ' + u['id'].removeprefix('snp') for u in source_units]
    if len(reference_rows) != len(reference) or len(ids) != 73 or set(ids) != set(reference):
        raise ValueError('Source references and existing site references must match exactly')
    book = {'id': BOOK_ID, 'title': 'Sutta Nipāta — A New Translation (391-page source)',
            'collection': 'khuddaka-nikaya/sutta-nipata', 'translator': 'Bhikkhu Candana',
            'source_url': SOURCE_URL, 'sha256': sha(pdf), 'license': LICENSE,
            'local_path': 'theravada/tipitaka/translations/en/candana/books/' + BOOK_ID + '.pdf',
            'permission_pages': [7],
            'conditions': ['Copies must be available free of charge', 'Do not alter the contents'],
            'formats': ['Original PDF', 'Unaltered text in another medium'],
            'plain_text_status': 'VERIFIED_SOURCE_REFERENCES_AND_EXTRACTION'}
    files = {book['local_path']: pdf}
    texts, mappings = [], []
    for unit, canonical_id in zip(source_units, ids):
        body, folios = reader_body(unit)
        paras = body.split('\n\n')
        title = paras[1]
        if len(paras) > 2 and paras[2].startswith('“') and paras[2].endswith('”'):
            title += ' — ' + paras[2][1:-1]
        source_url = SOURCE_URL + '#page=' + str(unit['first_pdf_page'])
        header = '\n'.join((canonical_id + ' - ' + title, 'Translated by Bhikkhu Candana',
                            'Source: ' + source_url, 'License: ' + LICENSE, NOTICE,
                            'Layout: Physical wraps reflowed; proven printed folios omitted; source wording retained.',
                            'Review: Full automatic text-layer comparison plus visual samples; not a complete human proofread.'))
        relative = 'theravada/tipitaka/translations/en/candana/snp/' + unit['id'] + '.txt'
        data = (header + '\n\n' + body).encode('utf-8')
        files[relative] = data
        texts.append({'kind': 'sutta', 'canonical_id': canonical_id, 'collection': book['collection'],
                      'title': title, 'translator': 'Bhikkhu Candana', 'version': 'candana',
                      'source_url': source_url, 'source_revision': book['sha256'], 'license': LICENSE,
                      'license_url': SOURCE_URL, 'local_path': relative, 'sha256': sha(data),
                      'body_sha256': sha(body.encode()), 'book': BOOK_ID,
                      'source_page': unit['first_pdf_page'], 'source_last_page': unit['last_pdf_page'],
                      'source_interval_sha256': unit['sha256'], 'reuse_notice': NOTICE,
                      'rights_status': 'EXPLICIT_PERMISSION_VERIFIED', 'completeness_status': 'UNKNOWN',
                      'completeness_scope': 'Complete numbered source interval; machine text checks and visual samples do not certify a full human proofread.'})
        mappings.append({'canonical_id': canonical_id, 'source_reference': unit['id'],
                         'source_title': title, 'site_title': reference[canonical_id]['label'],
                         'pdf_pages': [unit['first_pdf_page'], unit['last_pdf_page']],
                         'source_interval_sha256': unit['sha256'], 'body_sha256': texts[-1]['body_sha256'],
                         'printed_folios_omitted': folios})
    report = {'schema_version': 1, 'status': 'SOURCE_REFERENCES_AND_TEXT_VERIFIED',
              'pdf_sha256': book['sha256'], 'raw_text_sha256': sha(raw), 'audit_sha256': AUDIT_SHA,
              'reference_ledger_sha256': sha(references_bytes), 'reader_count': len(texts),
              'mapping_basis': 'Exact explicit Snp book/text references match all existing site IDs one-to-one; source names and translated site titles retained separately.',
              'mappings': mappings, 'source_units_not_imported': [u['id'] for u in units if u['kind'] != 'SUTTA_SOURCE_INTERVAL'],
              'layout': 'Whitespace-only reflow and removal of exact-source, geometrically verified folios; 17 Snake refrains retain authored starts. Other verse layout retains source paragraph gaps.',
              'human_proofreading_approved': False, 'translation_accuracy_certified': False}
    return book, texts, report, files


def verify(root: Path, manifest: dict, require_review: bool) -> None:
    extension = manifest.get('snp_extension')
    present = [b for b in manifest['books'] if b['id'] == BOOK_ID]
    rows = [t for t in manifest['texts'] if t['book'] == BOOK_ID]
    if not extension:
        if present or rows:
            raise ValueError('Sutta Nipāta readers lack the checked extension')
        return
    if extension != {'schema_version': 1, 'book': BOOK_ID, 'report': REPORT, 'reader_count': 73}:
        raise ValueError('Sutta Nipāta extension scope changed')
    book, expected, report, files = plan(root)
    if present != [book] or rows != expected:
        raise ValueError('Sutta Nipāta source mapping or metadata changed')
    for relative, data in files.items():
        path = root / relative
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError('Sutta Nipāta reader differs from pinned source: ' + relative)
    if require_review and json.loads((root / REPORT).read_text(encoding='utf-8')) != report:
        raise ValueError('Sutta Nipāta import report missing or stale')


def install(root: Path = ROOT) -> dict:
    """Generate all 73 readers at once. No network, model calls, or daemon publication."""
    if __package__:
        from .import_candana import RIGHTS_BASIS
    else:
        from import_candana import RIGHTS_BASIS
    book, texts, report, outputs = plan(root)
    manifest_path = root / 'metadata/source-manifests/candana.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if not manifest.get('numbered_extension'):
        raise ValueError('Preserve the checked AN imports before extending this manifest')
    # Preflight every translation target before writing anything.
    for relative, data in outputs.items():
        path = root / relative
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('Import must not follow symlinks')
        if path.exists() and path.read_bytes() != data:
            raise ValueError('Refusing to replace a different source or reader: ' + relative)
    for relative, data in outputs.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
    manifest['books'] = [b for b in manifest['books'] if b['id'] != BOOK_ID] + [book]
    manifest['texts'] = [t for t in manifest['texts'] if t['book'] != BOOK_ID] + texts
    manifest['snp_extension'] = {'schema_version': 1, 'book': BOOK_ID, 'report': REPORT, 'reader_count': 73}
    manifest_path.write_bytes(json_bytes(manifest))
    (root / REPORT).write_bytes(json_bytes(report))
    for filename, key, new_rows in (
        ('eligible-texts.json', 'texts', texts),
        ('eligible-assets.json', 'assets', [dict(book, license_url=SOURCE_URL, rights_status='EXPLICIT_PERMISSION_VERIFIED')]),
    ):
        path = root / 'metadata' / filename
        value = json.loads(path.read_text(encoding='utf-8'))
        value[key] = [r for r in value[key] if r.get('book', r.get('id')) != BOOK_ID] + new_rows
        if 'count' in value:
            value['count'] = len(value[key])
        path.write_bytes(json_bytes(value))
    allowlist = root / 'metadata/public-file-allowlist.json'
    value = json.loads(allowlist.read_text(encoding='utf-8'))
    known = {r['path'] for r in value['files']}
    additions = {p: (book['license'], RIGHTS_BASIS) for p in outputs}
    additions[REPORT] = ('CC0-1.0 project metadata', 'Owner-authored project metadata is released under CC0-1.0; excluded source text is not copied.')
    for relative, (scope, basis) in additions.items():
        if relative not in known:
            value['files'].append({'path': relative, 'sha256': sha((root / relative).read_bytes()),
                                   'license_scope': scope, 'rights_basis': basis})
    value['files'].sort(key=lambda r: r['path'])
    allowlist.write_bytes(json_bytes(value))
    return {'snp_readers': len(texts), 'total_candana_readers': len(manifest['texts']),
            'network_requests': 0, 'model_calls': 0, 'status': 'IMPORTED_NOT_YET_DEPLOYED'}
