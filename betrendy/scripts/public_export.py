#!/usr/bin/env python3
"""Create a redacted GitHub copy without changing the private migration package.

Requires beautifulsoup4. Financial values are discovered from the private content,
kept only in process memory, and never included in the report or upload manifest.
No network operations or GitHub writes are performed by this script.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile
import csv

from bs4 import BeautifulSoup, Comment, NavigableString

ROOT = Path(__file__).resolve().parents[2]
MARKER = '[PAYMENT DETAILS OMITTED]'
OMIT_DIRS = {'.git', '.cache', 'packages', 'assets', '__pycache__', 'node_modules', '.venv'}
GENERATED_PAYLOAD = Path('betrendy/wordpress/plugins/betrendy-import/data')
TEXT_SUFFIXES = {'.py', '.php', '.json', '.html', '.css', '.js', '.mjs', '.cjs', '.md', '.txt', '.csv', '.yml', '.yaml', '.xml', '.toml', '.ini', '.sh'}
IBAN = re.compile(r'(?<![A-Za-z0-9])(?:UA(?:[\s\u00a0-]*\d){27}|[A-Z]{2}\d{2}[A-Z0-9]{11,30})(?![A-Za-z0-9])', re.I)
IBAN_LENGTHS = {'UA': 29, 'AE': 23, 'AT': 20, 'BE': 16, 'BG': 22, 'CH': 21, 'CY': 28,
                'CZ': 24, 'DE': 22, 'DK': 18, 'EE': 20, 'ES': 24, 'FI': 18, 'FR': 27,
                'GB': 22, 'GE': 22, 'GR': 27, 'HR': 21, 'HU': 28, 'IE': 22, 'IL': 23,
                'IS': 26, 'IT': 27, 'LT': 20, 'LU': 20, 'LV': 21, 'MD': 24, 'MT': 31,
                'NL': 18, 'NO': 15, 'PL': 28, 'PT': 25, 'RO': 24, 'RS': 22, 'SE': 24,
                'SI': 19, 'SK': 24, 'TR': 26}
TAX = re.compile(r'(?:РНОКПП|RNOKPP|ІПН|ИНН|tax\s+(?:ID|number|identification\s+number)|ідентифікаційний\s+код|идентификационный\s+код)[^\d<>]{0,70}((?:\d[ \u00a0-]*){9}\d)(?!\d)', re.I)
BANK_CODE = re.compile(r'(?:(?:МФО|MFO)(?:\s+(?:банку|банка|bank))?|код\s+банку|код\s+банка|bank\s+code)\s*[:：]?\s*((?:\d[ \u00a0-]*){5}\d)(?!\d)', re.I)
SWIFT = re.compile(r'(?:SWIFT|BIC)(?:\s+code)?\s*[:：]\s*([A-Z0-9]{8}(?:[A-Z0-9]{3})?)(?![A-Z0-9])', re.I)
WORD = r'[A-ZА-ЯІЇЄҐЁ][A-Za-zА-Яа-яІіЇїЄєҐґЁё\u2019\u0027.\-]*'
NAME = WORD+r'(?:\s+'+WORD+r'){2}'
ENTREPRENEUR = re.compile(r'(?:ФОП|ФЛП|Individual\s+entrepreneur|Sole\s+proprietor|Фізична\s+особа[\s-]+підприємець|Физическое\s+лицо[\s-]+предприниматель)\s*[«"“]?\s*('+NAME+r')')
RECIPIENT = re.compile(r'(?:Отримувач|Одержувач|Получатель|Recipient|Beneficiary|Payee)\s*[:：]\s*('+NAME+r')')
BANK_NAME = re.compile(r'(?:Банк\s+(?:отримувача|одержувача|получателя)|(?:Recipient|Beneficiary|Receiver)(?:’s|\x27s)?\s+bank|Bank)\s*[:：]\s*([^\n<>]{3,140})', re.I)
BANK_ENTITY = re.compile(r'(?<!\w)(?:(?:АТ|АО|ПАТ|ПАО|JSC|PJSC)\s+[«"“]?[^\n<>]{0,90}?(?:Банк|БАНК|Bank|BANK)[»"”]?)')
FINANCIAL_PATTERNS = {'iban': IBAN, 'personal_tax_id': TAX, 'bank_code': BANK_CODE, 'swift_bic': SWIFT,
                      'payment_recipient': ENTREPRENEUR, 'recipient_label': RECIPIENT,
                      'bank_name': BANK_NAME, 'bank_entity': BANK_ENTITY}
PRIVACY_NOTE = '''

## Публичная копия без платёжных реквизитов

Это очищенный экспорт для публичного GitHub. Из текстов, HTML, JSON и CSV удалены банковские счета (IBAN), банковские коды/названия, данные получателя оплаты и его личный налоговый идентификатор. В местах удаления используется маркер `[PAYMENT DETAILS OMITTED]`. Рабочие телефоны, email и адрес магазина сохранены.

Полные исходники и данные для импорта в WordPress остаются локально; архивы в `betrendy/packages/` не входят в этот публичный экспорт. Перед запуском магазина нужно сверить юридические и платёжные страницы с полным локальным пакетом и актуальными данными владельца. Публичную копию платёжных/юридических страниц с пропусками нельзя считать готовой к публикации на рабочем сайте.

Сгенерированные deployment-данные `betrendy/wordpress/plugins/betrendy-import/data/` также исключены: они дублируют данные импорта и могут содержать полный локальный платёжный текст. Код плагина и `scripts/package-import-plugin.py` сохранены. При сборке из этого публичного репозитория используйте очищенные `betrendy/data/`; сборщик создаст payload и контрольные суммы заново.

Для следующих обновлений GitHub сначала запускайте `python3 betrendy/scripts/public_export.py` и используйте только результат в `betrendy/.cache/github-public/`. Не переносите неочищенные локальные `source/`, `data/` или копии данных внутри плагинов напрямую в публичный репозиторий.
'''


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def candidate_files():
    candidates = []
    for path in ROOT.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in OMIT_DIRS for part in rel.parts):
            continue
        if GENERATED_PAYLOAD == rel.parent or GENERATED_PAYLOAD in rel.parents:
            continue
        if path.name == '.DS_Store' or path.name.startswith('.env') or path.name == 'wp-config.php':
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {'.gitignore', '.gitattributes', 'requirements.txt'}:
            candidates.append(rel)
    # Respect the repository's existing exclusions for raw browser responses and samples.
    check = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin'], cwd=ROOT,
                           input=''.join(str(p)+'\n' for p in candidates), text=True, capture_output=True)
    if check.returncode not in (0, 1):
        raise RuntimeError('Cannot inspect repository exclusions; no public export was created.')
    ignored = set(check.stdout.splitlines())
    return sorted(p for p in candidates if str(p) not in ignored)


def strings_in(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (str, int, float)):
                yield str(key)+': '+str(item)
            yield from strings_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings_in(item)
    elif isinstance(value, str):
        yield value


def visible(text):
    if re.search(r'</?[A-Za-z][^>]*>', text):
        return BeautifulSoup(text, 'html.parser').get_text('\n')
    return html.unescape(text)


def iban_matches(text):
    """Reject random HTML identifiers that only resemble an international account."""
    for match in IBAN.finditer(text):
        compact = re.sub(r'[\s\u00a0-]', '', match.group(0)).upper()
        if compact.startswith('UA') and re.fullmatch(r'UA\d{27}', compact):
            yield match
        elif IBAN_LENGTHS.get(compact[:2]) == len(compact):
            rearranged = compact[4:]+compact[:4]
            digits = ''.join(str(ord(char)-55) if char.isalpha() else char for char in rearranged)
            if int(digits) % 97 == 1:
                yield match


def financial_values(text):
    """Yield financial categories and values, never writing the values anywhere."""
    for match in iban_matches(text):
        yield 'iban', match.group(0)
    for kind, pattern in [('personal_tax_id', TAX), ('bank_code', BANK_CODE), ('swift_bic', SWIFT),
                          ('payment_recipient', ENTREPRENEUR), ('payment_recipient', RECIPIENT),
                          ('bank_name', BANK_NAME), ('bank_name', BANK_ENTITY)]:
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)
            value = re.split(r'\b(?:МФО|MFO|IBAN|РНОКПП|RNOKPP|SWIFT|BIC)\b', value)[0].strip()
            value = re.sub(r'\s+', ' ', value)
            if value and MARKER not in value:
                yield kind, value


def discover(documents):
    values = {}
    for rel, content in documents.items():
        # Data copies within wordpress/plugins are deliberately included.
        if rel.suffix.lower() == '.json':
            try:
                texts = strings_in(json.loads(content))
            except json.JSONDecodeError:
                raise RuntimeError('Invalid source JSON: '+str(rel))
        elif rel.suffix.lower() == '.csv':
            texts = (field for row in csv.reader(io.StringIO(content)) for field in row)
        elif rel.suffix.lower() in {'.html', '.md', '.txt', '.xml'}:
            texts = [content]
        else:
            continue
        for text in texts:
            for kind, value in financial_values(visible(text)):
                values.setdefault(kind, set()).add(value)
    return values


def compile_values(values):
    patterns = []
    for kind, entries in values.items():
        for value in sorted(entries, key=len, reverse=True):
            if kind in {'iban', 'personal_tax_id', 'bank_code'}:
                compact = re.sub(r'[\s\u00a0-]', '', value)
                body = r'[\s\u00a0-]*'.join(re.escape(c) for c in compact)
            else:
                body = r'\s+'.join(re.escape(part) for part in value.split())
            patterns.append((kind, re.compile(r'(?<![A-Za-z0-9А-Яа-яІіЇїЄєҐґ])'+body+r'(?![A-Za-z0-9А-Яа-яІіЇїЄєҐґ])', re.I)))
    return patterns


def matched_spans(text, patterns):
    matches = []
    for kind, pattern in patterns:
        matches.extend((m.start(), m.end(), kind) for m in pattern.finditer(text))
    # Prefer the longest match at the same position (e.g. full bank name).
    matches.sort(key=lambda x: (x[0], -(x[1]-x[0])))
    selected = []
    for start, end, kind in matches:
        if selected and start < selected[-1][1]:
            continue
        selected.append((start, end, kind))
    return selected


def redact_plain(text, patterns, counts):
    spans = matched_spans(text, patterns)
    for start, end, kind in reversed(spans):
        text = text[:start]+MARKER+text[end:]
        counts[kind] += 1
    return text


def redact_html(markup, patterns, counts):
    soup = BeautifulSoup(markup, 'html.parser')
    nodes = [node for node in soup.find_all(string=True) if not isinstance(node, Comment)]
    mapping, chunks, offset = [], [], 0
    for node in nodes:
        text = str(node)
        mapping.append((node, offset, offset+len(text)))
        chunks.append(text)
        offset += len(text)+1
    flat = '\n'.join(chunks)
    spans = matched_spans(flat, patterns)
    changes = {}
    for start, end, kind in spans:
        placed = False
        for index, (_, node_start, node_end) in enumerate(mapping):
            left, right = max(start, node_start), min(end, node_end)
            if left < right:
                changes.setdefault(index, []).append((left-node_start, right-node_start, MARKER if not placed else ''))
                placed = True
        counts[kind] += 1
    changed = bool(changes)
    for index, replacements in changes.items():
        node, _, _ = mapping[index]
        text = str(node)
        for start, end, replacement in sorted(replacements, reverse=True):
            text = text[:start]+replacement+text[end:]
        node.replace_with(NavigableString(text))
    for tag in soup.find_all(True):
        for key, value in list(tag.attrs.items()):
            if isinstance(value, str):
                cleaned = redact_plain(value, patterns, counts)
                if cleaned != value:
                    tag[key] = cleaned
                    changed = True
    for comment in soup.find_all(string=lambda node: isinstance(node, Comment)):
        cleaned = redact_plain(str(comment), patterns, counts)
        if cleaned != str(comment):
            comment.replace_with(Comment(cleaned))
            changed = True
    return str(soup) if changed else markup


def redact_value(value, patterns, counts):
    if isinstance(value, dict):
        return {key: redact_value(item, patterns, counts) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, patterns, counts) for item in value]
    if isinstance(value, str):
        if re.search(r'</?[A-Za-z][^>]*>', value):
            return redact_html(value, patterns, counts)
        return redact_plain(value, patterns, counts)
    if isinstance(value, (int, float)):
        string = str(value)
        cleaned = redact_plain(string, patterns, counts)
        return cleaned if cleaned != string else value
    return value


def redact_document(rel, content, patterns):
    counts = Counter()
    if rel.suffix.lower() == '.json':
        cleaned = redact_value(json.loads(content), patterns, counts)
        output = json.dumps(cleaned, ensure_ascii=False, indent=2)+'\n'
    elif rel.suffix.lower() == '.csv':
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        for row in csv.reader(io.StringIO(content)):
            writer.writerow([redact_value(field, patterns, counts) for field in row])
        output = stream.getvalue()
    elif rel.suffix.lower() in {'.html', '.xml'}:
        output = redact_html(content, patterns, counts)
    else:
        output = redact_plain(content, patterns, counts)
    return output, counts


def contacts_in(content):
    """Compare published operational contacts without including their values in reports."""
    return set(re.findall(r'(?:\+?380\d{9}|0\d{2}[- ]\d{3}[- ]\d{2}[- ]\d{2}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})', content))


def verify_export(documents, patterns):
    failures = []
    for rel, content in documents.items():
        if rel.suffix.lower() == '.json':
            texts = list(strings_in(json.loads(content)))
        elif rel.suffix.lower() == '.csv':
            texts = [field for row in csv.reader(io.StringIO(content)) for field in row]
        else:
            texts = [content]
        for text in texts:
            display = visible(text) if rel.suffix.lower() not in {'.py', '.php', '.js', '.css'} else text
            remaining = matched_spans(display, patterns)
            iban_detected = bool(list(iban_matches(display)))
            # Independent wider checks catch new label variants that discovery may miss.
            contextual_code = bool(re.search(r'(?:МФО|MFO)[^\d<>]{0,60}\d{6}(?!\d)', display, re.I))
            contextual_tax = bool(re.search(r'(?:РНОКПП|RNOKPP|ІПН|ИНН)[^\d<>]{0,80}\d{10}(?!\d)', display, re.I))
            if remaining or iban_detected or contextual_code or contextual_tax:
                failures.append({'path': str(rel), 'remaining_matches': len(remaining), 'iban_detected': iban_detected,
                                 'contextual_bank_code': contextual_code, 'contextual_personal_tax_id': contextual_tax})
                break
    if failures:
        # Deliberately do not print the text/value that failed validation.
        raise RuntimeError('Financial redaction verification failed: '+json.dumps(failures, ensure_ascii=False))


def write_batches(documents, batch_dir, target_bytes=350000, part_chars=80000):
    batch_dir.mkdir(parents=True, exist_ok=True)
    batches, current, size = [], [], len('{"tree_elements":[]}')
    for rel, content in sorted(documents.items(), key=lambda row: str(row[0])):
        item = {'path': str(rel), 'mode': '100644', 'type': 'blob', 'content': content}
        item_bytes = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))+1
        if current and size+item_bytes > target_bytes:
            batches.append(current)
            current, size = [], len('{"tree_elements":[]}')
        current.append(item)
        size += item_bytes
    if current:
        batches.append(current)
    manifest = {'target_batch_bytes': target_bytes, 'part_characters': part_chars, 'batches': [],
                'note': 'A file cannot be split into multiple tree entries; an individually oversized file has its own batch.'}
    for number, items in enumerate(batches, 1):
        name = 'batch-'+str(number).zfill(3)
        raw = json.dumps({'tree_elements': items}, ensure_ascii=False, separators=(',', ':'))
        (batch_dir/(name+'.json')).write_text(raw, encoding='utf-8')
        parts = []
        for index, start in enumerate(range(0, len(raw), part_chars), 1):
            part_name = name+'-'+str(index).zfill(3)+'.part'
            (batch_dir/part_name).write_text(json.dumps(raw[start:start+part_chars], ensure_ascii=False), encoding='utf-8')
            parts.append(part_name)
        rebuilt = ''.join(json.loads((batch_dir/p).read_text()) for p in parts)
        if rebuilt != raw or json.loads(rebuilt)['tree_elements'] != items:
            raise RuntimeError('Batch reconstruction failed: '+name)
        manifest['batches'].append({'file': name+'.json', 'bytes': len(raw.encode('utf-8')), 'characters': len(raw),
                                    'sha256': sha256(raw.encode('utf-8')), 'files': len(items),
                                    'oversized_single_file': len(raw.encode('utf-8')) > target_bytes,
                                    'paths': [item['path'] for item in items], 'parts': parts})
    (batch_dir/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-private', action='store_true', help='Also preserve the unredacted source files in an ignored local ZIP.')
    options = parser.parse_args()
    files = candidate_files()
    documents = {rel: (ROOT/rel).read_text(encoding='utf-8-sig') for rel in files}
    values = discover(documents)
    patterns = compile_values(values)
    public, changed, totals = {}, [], Counter()
    for rel, content in documents.items():
        output, counts = redact_document(rel, content, patterns)
        if not contacts_in(content).issubset(contacts_in(output)):
            raise RuntimeError('A working contact would be removed from: '+str(rel))
        if counts:
            changed.append({'path': str(rel), 'redactions': dict(counts)})
            totals.update(counts)
        public[rel] = output
    for readme in (Path('README.md'), Path('betrendy/README.md')):
        if readme in public:
            public[readme] = public[readme].rstrip()+PRIVACY_NOTE
    verify_export(public, patterns)
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'public_export': True,
              'source_files_modified': False, 'file_count_before_report': len(public),
              'financial_values_discovered_by_category': {kind: len(entries) for kind, entries in values.items()},
              'redaction_occurrences_by_category': dict(totals), 'changed_files': changed,
              'verification': {'remaining_discovered_financial_values': 0, 'remaining_iban': 0,
                               'working_phone_and_email_values_preserved': True},
              'excluded_directories': sorted(OMIT_DIRS),
              'excluded_generated_payload': str(GENERATED_PAYLOAD),
              'notice': 'Removed values are deliberately absent from this report. Full source/data remains local.'}
    public[Path('PUBLIC_EXPORT_REPORT.json')] = json.dumps(report, ensure_ascii=False, indent=2)+'\n'
    export_dir = ROOT/'betrendy/.cache/github-public'
    batch_dir = ROOT/'betrendy/.cache/github-public-batches'
    # These two directories are generated output only; original source/data is never modified.
    for directory in (export_dir, batch_dir):
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
    manifest = []
    for rel, content in public.items():
        destination = export_dir/rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode('utf-8')
        destination.write_bytes(encoded)
        manifest.append({'path': str(rel), 'bytes': len(encoded), 'sha256': sha256(encoded)})
    manifest_path = ROOT/'betrendy/.cache/github-public-manifest.json'
    manifest_path.write_text(json.dumps({'files': manifest, 'report': 'PUBLIC_EXPORT_REPORT.json'}, ensure_ascii=False, indent=2)+'\n')
    batches = write_batches(public, batch_dir)
    archive = None
    if options.archive_private:
        archive = ROOT/'betrendy/packages/betrendy-private-text-source.zip'
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
            for rel, content in documents.items():
                output.writestr(str(rel), content.encode('utf-8'))
        # Existing media and complete migration archives stay alongside this exact text snapshot.
    print(json.dumps({'export_directory': str(export_dir), 'manifest': str(manifest_path),
                      'batch_manifest': str(batch_dir/'manifest.json'), 'files': len(public),
                      'batches': len(batches['batches']), 'parts': sum(len(b['parts']) for b in batches['batches']),
                      'redacted_files': len(changed), 'redaction_categories': dict(totals),
                      'oversized_single_file_batches': [b['file'] for b in batches['batches'] if b['oversized_single_file']],
                      'private_text_archive': str(archive) if archive else None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
