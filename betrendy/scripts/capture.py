#!/usr/bin/env python3
"""Archive public BeTrendy content and original media; never visits account/checkout.

Requires beautifulsoup4. Run from any directory: python capture.py.
Downloaded pages are parsed as data; no remote scripts are executed.
"""
import concurrent.futures as futures
import hashlib
import json
import posixpath
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
from bs4 import BeautifulSoup, Comment

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://betrendy.space/'
CACHE = ROOT / '.cache'
CACHE.mkdir(exist_ok=True)
HEADERS = ['-A', 'Mozilla/5.0 (compatible; BeTrendyMigration/1.0)']
BLOCKED = re.compile(r'/(checkout|profile|cart|search)(/|$)')

def normalize(url):
    p = urlsplit(urljoin(BASE, url))
    if p.hostname not in ('betrendy.space', 'www.betrendy.space') or BLOCKED.search(p.path):
        return None
    path = posixpath.normpath(p.path or '/')
    return 'https://betrendy.space' + path.rstrip('/') + '/'

def download(url, cookie=''):
    cmd = ['curl', '-fsSL', '--retry', '2', '--max-time', '45', *HEADERS]
    cookies = {'challenge_passed': cookie} if cookie else {}
    for attempt in range(3):
        headers = ['-H', 'Cookie: ' + '; '.join(k+'='+v for k,v in cookies.items())] if cookies else []
        r = subprocess.run([*cmd, *headers, url], capture_output=True)
        if r.returncode:
            raise RuntimeError(r.stderr.decode(errors='replace')[-300:])
        if len(r.stdout) >= 2000 or b'const defaultHash' not in r.stdout:
            break
        match = re.search(rb'const defaultHash = "([a-f0-9]+)"', r.stdout)
        name = re.search(rb'document\.cookie = "(challenge_passed(?:_cat)?)=', r.stdout)
        if not match or not name or cookies.get(name.group(1).decode()) == match.group(1).decode():
            break
        # Mirror the public site's own non-interactive cookie check, no scripts executed.
        cookies[name.group(1).decode()] = match.group(1).decode()
    return r.stdout

def clean(node):
    node = BeautifulSoup(str(node or ''), 'html.parser')
    for frame in node.select('iframe[src]'):
        src = urljoin(BASE, frame['src'])
        if urlsplit(src).hostname in ('www.youtube.com','youtube.com','www.youtube-nocookie.com','player.vimeo.com'):
            p = node.new_tag('p')
            a = node.new_tag('a', href=src)
            a.string = src
            if frame.parent and frame.parent.name == 'p':
                frame.replace_with(a)
            else:
                p.append(a)
                frame.replace_with(p)
    for el in node.select('script, style, form, input, button, select, textarea, noscript, svg, iframe'):
        el.decompose()
    for comment in node.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()
    for el in node.find_all(True):
        for key in list(el.attrs):
            if key.startswith('on') or key in ('nonce', 'data-token'):
                del el[key]
        for key in ('src', 'href', 'poster'):
            value = el.get(key)
            if value and not value.startswith(('mailto:', 'tel:', '#')):
                if value.strip().lower().startswith(('javascript:', 'data:')):
                    del el[key]
                else:
                    el[key] = urljoin(BASE, value)
    return str(node)

def capture(url, cookie):
    path = urlsplit(url).path.strip('/')
    parts = path.split('/') if path else []
    lang = parts.pop(0) if parts and parts[0] in ('en', 'ru') else 'uk'
    slug = '/'.join(parts) or 'home'
    target = ROOT / 'source' / 'pages' / lang / (slug.replace('/', '__') + '.json')
    if target.exists() and json.loads(target.read_text()).get('capture_schema') == 2:
        record = json.loads(target.read_text())
        if record['type'] == 'product':
            cached = BeautifulSoup(record['main_html'], 'html.parser')
            gallery = list(dict.fromkeys(urljoin(BASE, a.get('data-href') or a.get('href'))
                       for a in cached.select('.gallery__link')
                       if '/content/' in (a.get('data-href') or a.get('href') or '')))
            if gallery:
                record['gallery'] = gallery
                record['images'] = list(dict.fromkeys(record['images'] + gallery))
                target.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        return record
    time.sleep(1.3)
    raw = download(url, cookie)
    if len(raw) < 2000:
        raise RuntimeError('Source returned a challenge or empty response')
    soup = BeautifulSoup(raw, 'html.parser')
    meta = {}
    for el in soup.select('meta'):
        key = el.get('property') or el.get('name') or el.get('itemprop')
        if key and el.get('content') and key not in meta:
            meta[key] = el['content']
    meta['title'] = soup.title.get_text(' ', strip=True) if soup.title else ''
    main = soup.select_one('main') or soup.select_one('#main') or soup.body
    title = soup.select_one('h1')
    product = meta.get('og:type') == 'product'
    description = soup.select_one('.product-description') if product else None
    if not product:
        candidates = main.select('.text, .catalog-seo, .article__body') if main else []
        description = max(candidates, key=lambda n: len(n.get_text()), default=None)
    features = {}
    if product:
        for row in soup.select('.product-features__table tr'):
            key, val = row.find('th'), row.find('td')
            if key and val:
                features[key.get_text(' ', strip=True)] = val.get_text(' ', strip=True)
    gallery = []
    for a in soup.select('.gallery__link'):
        href = a.get('data-href') or a.get('href')
        if href and '/content/' in href:
            gallery.append(urljoin(BASE, href))
    gallery = list(dict.fromkeys(gallery))
    if product and not gallery and meta.get('og:image'):
        gallery = [urljoin(BASE, meta['og:image'])]
    images = gallery.copy()
    image_scope = description if product else (main if slug != 'home' else soup)
    if image_scope:
        images += [urljoin(BASE, img.get('src')) for img in image_scope.select('img[src]')
                   if '/content/' in img.get('src', '')]
    breadcrumbs = []
    for a in soup.select('.breadcrumbs a[href]'):
        breadcrumbs.append({'title': a.get_text(' ', strip=True), 'url': urljoin(BASE, a['href'])})
    links = sorted(set(filter(None, (normalize(a['href']) for a in soup.select('a[href]')))))
    canonical = soup.select_one('link[rel="canonical"]')
    record = {
        'source_url': url, 'canonical_url': urljoin(BASE, canonical['href']) if canonical else url,
        'captured_date': '2026-11-13', 'language': lang, 'slug': slug,
        'capture_schema': 2,
        'type': 'product' if product else 'page',
        'title': title.get_text(' ', strip=True) if title else (meta.get('og:title') or soup.title.get_text()),
        'meta': meta, 'breadcrumbs': breadcrumbs, 'features': features,
        'gallery': gallery, 'images': list(dict.fromkeys(images)), 'links': links,
        'content_html': clean(description), 'main_html': clean(main),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    return record

def save_media(url):
    digest = hashlib.sha256(url.encode()).hexdigest()[:14]
    ext = Path(urlsplit(url).path).suffix.lower()
    if ext not in ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif'):
        return {'url': url, 'error': 'Unsupported media extension'}
    path = ROOT / 'assets' / (digest + ext)
    try:
        if not path.exists():
            data = download(url)
            if data.startswith(b'<script>') or len(data) < 20:
                raise RuntimeError('Invalid image response')
            path.write_bytes(data)
        data = path.read_bytes()
        return {'url': url, 'path': str(path.relative_to(ROOT)), 'bytes': len(data),
                'sha256': hashlib.sha256(data).hexdigest()}
    except Exception as exc:
        return {'url': url, 'error': str(exc)}

def main():
    inventory = json.loads((ROOT / 'source/url-inventory.json').read_text())
    urls = sorted(set(filter(None, (normalize(x['url']) for x in inventory['links']))))
    # Full category listings expose membership beyond the first page; filter combinations
    # add no new product data. Capture the real catalogue landing pages too.
    supplements = set()
    for path in (ROOT/'source/pages').rglob('*.json'):
        row = json.loads(path.read_text())
        for url in row.get('links', []):
            if '/filter/page=all/' in url or urlsplit(url).path.rstrip('/').endswith('/katalog'):
                supplements.add(normalize(url))
    urls = sorted(set(urls) | (supplements - {None}))
    challenge = download(BASE).decode(errors='replace')
    match = re.search(r'const defaultHash = "([a-f0-9]+)"', challenge)
    cookie = match.group(1) if match else ''
    records, errors = [], []
    with futures.ThreadPoolExecutor(max_workers=1) as pool:
        pending = {pool.submit(capture, u, cookie): u for u in urls}
        for future in futures.as_completed(pending):
            try:
                records.append(future.result())
            except Exception as exc:
                errors.append({'url': pending[future], 'error': str(exc)})
            if (len(records) + len(errors)) % 30 == 0:
                print(f'Pages {len(records)} / {len(urls)}, errors {len(errors)}', flush=True)
    media_urls = sorted(set(u for r in records for u in r['images']))
    assets = []
    with futures.ThreadPoolExecutor(max_workers=5) as pool:
        for i, asset in enumerate(pool.map(save_media, media_urls), 1):
            assets.append(asset)
            if i % 100 == 0:
                print(f'Images {i} / {len(media_urls)}', flush=True)
    (ROOT / 'data/media-manifest.json').write_text(json.dumps(assets, ensure_ascii=False, indent=2))
    summary = {'source': BASE, 'date': '2026-11-13', 'requested_pages': len(urls),
               'captured_pages': len(records), 'products_by_language': {}, 'pages_by_language': {},
               'media_files': len([a for a in assets if 'path' in a]),
               'media_bytes': sum(a.get('bytes', 0) for a in assets),
               'page_errors': errors, 'media_errors': [a for a in assets if 'error' in a]}
    for lang in ('uk', 'ru', 'en'):
        summary['products_by_language'][lang] = sum(r['language'] == lang and r['type'] == 'product' for r in records)
        summary['pages_by_language'][lang] = sum(r['language'] == lang and r['type'] != 'product' for r in records)
    (ROOT / 'data/capture-report.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
