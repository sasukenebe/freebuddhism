#!/usr/bin/env python3
"""Read-only conversion audit; persist page coverage, never approve proofreading."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import unicodedata


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compact(text: str, nfc: bool = False) -> str:
    return ''.join((unicodedata.normalize('NFC', text) if nfc else text).split())


class SourceHTML(HTMLParser):
    """Collect only source containers; labels are explicit and never compared as source."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.editorial = False
        self.section = None
        self.parts = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'section':
            self.section = attrs.get('id')
        if tag == 'div' and attrs.get('class') == 'converted-text':
            self.active = True
            key = self.section or 'individual'
            if key in self.parts:
                raise ValueError('Repeated source text container')
            self.parts[key] = []
        if tag == 'span' and attrs.get('class') == 'editorial':
            self.editorial = True
        if self.active and tag in {'br', 'p', 'td'}:
            self.parts[self.section or 'individual'].append(' ')

    def handle_endtag(self, tag):
        if self.active and tag in {'p', 'td'}:
            self.parts[self.section or 'individual'].append(' ')
        if tag == 'div':
            self.active = False
        if tag == 'span':
            self.editorial = False
        if tag == 'section':
            self.section = None

    def handle_data(self, data):
        if self.active and not self.editorial:
            self.parts[self.section or 'individual'].append(data)


def source_html(data: bytes) -> dict[str, str]:
    parser = SourceHTML()
    parser.feed(data.decode('utf-8', errors='strict'))
    return {key: ''.join(value) for key, value in parser.parts.items()}


def compare_pages(reference: list[str], actual: list[str]) -> list[dict]:
    if len(reference) != len(actual):
        raise ValueError('Extractor page count mismatch')
    return [{'pdf_page': n, 'exact_nonspace_match': compact(a) == compact(b),
             'nfc_nonspace_match': compact(a, True) == compact(b, True)}
            for n, (a, b) in enumerate(zip(reference, actual), 1)]


def audit(pdf: Path, text: Path, metadata: Path | None = None) -> dict:
    import fitz  # Optional audit dependency, not a website build dependency.

    pdf_bytes, raw = pdf.read_bytes(), text.read_bytes()
    pages = raw.decode('utf-8', errors='strict').split('\f')
    if not pages[-1].strip():
        pages.pop()
    with fitz.open(pdf) as document:
        pymupdf = [page.get_text('text', sort=False) for page in document]
        no_text = [n for n, page in enumerate(document, 1) if not page.get_text().strip()]
        image_only = [n for n, page in enumerate(document, 1)
                      if not page.get_text().strip() and page.get_images()]
    result = subprocess.run(['pdftotext', '-raw', str(pdf), '-'], check=True,
                            capture_output=True, timeout=120)
    poppler = result.stdout.decode('utf-8', errors='strict').split('\f')
    if not poppler[-1].strip():
        poppler.pop()
    comparisons = {'pymupdf': compare_pages(pages, pymupdf),
                   'poppler_raw': compare_pages(pages, poppler)}
    report = {'schema_version': 1, 'pdf_sha256': sha(pdf_bytes), 'text_sha256': sha(raw),
              'pdf_pages': len(pages), 'engines': comparisons,
              'versions': {'pymupdf': fitz.VersionBind,
                           'poppler': subprocess.run(['pdftotext', '-v'], capture_output=True,
                                                     text=True, check=True).stderr.splitlines()[0]},
              'method': 'Ordered characters; exact and NFC-only comparisons, whitespace ignored. No NFKC, inventory sorting, punctuation repair or numeric suppression.',
              'engine_limit': 'PyMuPDF shares the MuPDF engine with mutool; Poppler is the independent engine.',
              'pages_without_text': no_text, 'image_only_pages': image_only,
              'visual_pages_approved': [], 'human_proofreading_approved': False,
              'canonical_mapping_approved': False}
    failures = [f'{engine}: page {row["pdf_page"]}' for engine, rows in comparisons.items()
                for row in rows if not row['nfc_nonspace_match']]
    if metadata is not None:
        manifest = json.loads(metadata.read_text(encoding='utf-8'))
        if manifest['pdf_sha256'] != sha(pdf_bytes) or manifest['text_sha256'] != sha(raw):
            raise ValueError('Source hashes differ from conversion metadata')
        for name, expected in manifest['output_hashes'].items():
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('Unsafe artifact path in conversion metadata')
            if sha((metadata.parent / path).read_bytes()) != expected:
                raise ValueError('Generated artifact hash mismatch: ' + name)
        shown = source_html((metadata.parent / 'converted.html').read_bytes())
        source = raw.decode('utf-8')
        position = 0
        individual_count = 0
        for unit in manifest['units']:
            start, end = unit['start_character'], unit['end_character']
            body = source[start:end]
            if start != position or end <= start or sha(body.encode()) != unit['sha256']:
                raise ValueError('Noncontiguous, changed or missing interval')
            if source[:start].count('\f') + 1 != unit['first_pdf_page']:
                raise ValueError('Interval PDF page start changed')
            last = min(len(pages), source[:max(start, start + len(body.rstrip()) - 1)].count('\f') + 1)
            if last != unit['last_pdf_page']:
                raise ValueError('Interval PDF page end changed')
            if shown.get(unit['id'], '').split() != body.split():
                raise ValueError('HTML changed source word boundaries: ' + unit['id'])
            if unit['kind'] == 'SUTTA_SOURCE_INTERVAL':
                prefix = metadata.parent / 'suttas' / unit['id']
                if prefix.with_suffix(prefix.suffix + '.txt').read_bytes() != body.encode():
                    raise ValueError('Individual raw text differs')
                single = source_html(prefix.with_suffix(prefix.suffix + '.html').read_bytes())
                if single.get('individual', '').split() != body.split():
                    raise ValueError('Individual HTML differs: ' + unit['id'])
                individual_count += 1
            position = end
        if position != len(source) or list(shown) != [unit['id'] for unit in manifest['units']]:
            raise ValueError('HTML interval order/count or source coverage changed')
        report.update(intervals_verified=len(shown), individual_suttas_verified=individual_count,
                      artifact_hashes_verified=len(manifest['output_hashes']),
                      html_word_boundaries='PASS')
    report.update(status='TEXT_COMPARISON_PASS' if not failures else 'DISAGREEMENTS_RETAINED',
                  disagreements=failures)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', type=Path, required=True)
    parser.add_argument('--text', type=Path, required=True)
    parser.add_argument('--metadata', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.pdf, args.text, args.metadata)
    # Audit reports are versioned evidence: never overwrite a prior result.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'pdf_pages', 'disagreements')}))
    raise SystemExit(bool(report['disagreements']))


if __name__ == '__main__':
    main()
